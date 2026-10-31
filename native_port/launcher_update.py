"""Opt-in installation of GitHub launcher releases; no game/profile migration."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from . import __version__
from .errors import PortError
from .portable import user_data_root

# Repository identity survives the Green-Lantern-Recomp -> Lantern-Recomp rename.
REPOSITORY_ID = 1431033413
RELEASES_API = f'https://api.github.com/repositories/{REPOSITORY_ID}/releases?per_page=100'
REPOSITORIES = {'/Akimitsu76/Lantern-Recomp', '/Akimitsu76/Green-Lantern-Recomp'}
ASSETS = {'linux': 'AsterNative-linux-x86_64.AppImage', 'win32': 'AsterNative-windows-x64.exe'}
MAX_BINARY = 512 * 1024**2
VERSION_RE = re.compile(r'^v?(\d+)\.(\d+)\.(\d+)(?:[-.]?(alpha|beta|rc)[.-]?(\d+))?$')


def version_key(value):
    match = VERSION_RE.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise ValueError('Versão de release não reconhecida.')
    major, minor, patch, kind, number = match.groups()
    return (int(major), int(minor), int(patch),
            {None: 3, 'rc': 2, 'beta': 1, 'alpha': 0}[kind], int(number or 0))


def asset_name(platform=None):
    try:
        return ASSETS[platform or sys.platform]
    except KeyError as exc:
        raise PortError('UPDATE_PLATFORM', 'Atualização disponível somente para Linux x64 e Windows x64.') from exc


def release_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or parsed.netloc != 'github.com' or
            not any(parsed.path.startswith(repo + '/releases/') for repo in REPOSITORIES)):
        raise PortError('UPDATE_URL', 'O release não pertence ao repositório do projeto.')
    return url


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != 'https' or parsed.netloc not in {
                'api.github.com', 'github.com', 'release-assets.githubusercontent.com',
                'objects.githubusercontent.com'}:
            raise PortError('UPDATE_URL', 'Redirecionamento de download não permitido.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'AsterNative/' + __version__, 'Accept': 'application/vnd.github+json'})
    return urllib.request.build_opener(_Redirects()).open(request, timeout=20)


def _read(url, limit):
    with _open(url) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise PortError('UPDATE_SIZE', 'Resposta do servidor excede o limite permitido.')
    return raw


def select_release(releases, current=__version__, platform=None, include_prerelease=True):
    """Select a newer, fully published release with this platform and checksums."""
    candidates = []
    name = asset_name(platform)
    for release in releases:
        try:
            tag = release['tag_name']
            version = version_key(tag)
            if (release.get('draft') or version <= version_key(current) or
                    (not include_prerelease and (release.get('prerelease') or version[3] < 3))):
                continue
            html = release_url(release['html_url'])
            assets = release['assets']
            binary = [a for a in assets if a.get('name') == name and a.get('state', 'uploaded') == 'uploaded']
            sums = [a for a in assets if a.get('name') == 'SHA256SUMS' and a.get('state', 'uploaded') == 'uploaded']
            if len(binary) != 1 or len(sums) != 1:
                continue
            binary, sums = binary[0], sums[0]
            size = binary['size']
            if type(size) is not int or not 0 < size <= MAX_BINARY:
                continue
            # Pin the tag and file names in asset URLs too; no arbitrary commands/URLs.
            base = html.split('/releases/')[0] + '/releases/download/' + urllib.parse.quote(tag, safe='') + '/'
            if (binary['browser_download_url'] != base + name or
                    sums['browser_download_url'] != base + 'SHA256SUMS'):
                continue
            candidates.append((version, {'tag': tag, 'url': html, 'asset': name, 'size': size,
                'download_url': release_url(binary['browser_download_url']),
                'sums_url': release_url(sums['browser_download_url']),
                'digest': binary.get('digest'), 'notes': str(release.get('body') or '')[:12000],
                'prerelease': bool(release.get('prerelease') or version[3] < 3)}))
        except (KeyError, TypeError, ValueError, PortError):
            continue
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def check_release(include_prerelease=True):
    try:
        data = json.loads(_read(RELEASES_API, 4 * 1024**2))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise PortError('UPDATE_NETWORK', 'Não foi possível consultar o GitHub. Verifique a conexão e tente novamente.') from exc
    if not isinstance(data, list):
        raise PortError('UPDATE_RESPONSE', 'Não foi possível consultar os releases do GitHub.')
    return select_release(data, include_prerelease=include_prerelease)


def checksum_for(content, name):
    matches = []
    for line in content.decode('utf8').splitlines():
        match = re.fullmatch(r'([0-9a-fA-F]{64})\s+\*?([^\r\n]+)', line.strip())
        if match and match[2] == name:
            matches.append(match[1].lower())
    if len(matches) != 1:
        raise PortError('UPDATE_CHECKSUM', 'SHA256SUMS ausente, ambíguo ou incompatível com o download.')
    return matches[0]


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.update-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as output:
            json.dump(value, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def verify_binary(path, expected, name):
    path = Path(path)
    with path.open('rb') as source:
        header = source.read(64)
        valid = False
        if len(header) == 64 and name.endswith('.exe') and header.startswith(b'MZ'):
            offset = struct.unpack_from('<I', header, 60)[0]
            if 64 <= offset <= 1024 * 1024:
                source.seek(offset)
                pe = source.read(26)
                valid = (len(pe) == 26 and pe[:4] == b'PE\0\0' and
                         struct.unpack_from('<H', pe, 4)[0] == 0x8664 and
                         struct.unpack_from('<H', pe, 22)[0] & 2 != 0 and
                         struct.unpack_from('<H', pe, 24)[0] == 0x20b)
        elif len(header) == 64 and not name.endswith('.exe'):
            valid = (header.startswith(b'\x7fELF\x02\x01') and header[8:11] == b'AI\x02' and
                     struct.unpack_from('<H', header, 18)[0] == 62)
    if not valid or file_hash(path) != expected:
        raise PortError('UPDATE_CHECKSUM', 'O executável baixado falhou na verificação. A versão atual foi mantida.')


def download_release(release, cancel, emit=lambda _: None, directory=None):
    name = asset_name()
    if release['asset'] != name:
        raise PortError('UPDATE_PLATFORM', 'O download não corresponde a este sistema.')
    expected = checksum_for(_read(release_url(release['sums_url']), 65536), name)
    digest = release.get('digest')
    if digest and digest != 'sha256:' + expected:
        raise PortError('UPDATE_CHECKSUM', 'Os hashes publicados no GitHub e no SHA256SUMS divergem.')
    folder = Path(directory) if directory else user_data_root() / 'updates'
    folder.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='download-', dir=folder))
    part, output = staging / (name + '.part'), staging / name
    try:
        cancel.check()
        count = 0
        with _open(release_url(release['download_url'])) as response, part.open('xb') as destination:
            while chunk := response.read(256 * 1024):
                cancel.check()
                count += len(chunk)
                if count > release['size'] or count > MAX_BINARY:
                    raise PortError('UPDATE_SIZE', 'O download excede o tamanho publicado.')
                destination.write(chunk)
                emit({'completed': count, 'total': release['size']})
            destination.flush()
            os.fsync(destination.fileno())
        if count != release['size']:
            raise PortError('UPDATE_SIZE', 'Download incompleto. Tente novamente.')
        verify_binary(part, expected, name)
        cancel.check()
        part.replace(output)
        output.chmod(0o755)
        return {'path': str(output), 'sha256': expected, 'version': release['tag'], 'asset': name}
    except BaseException:
        # Only the fresh download directory belongs to this operation.
        shutil.rmtree(staging)
        raise


def installed_executable():
    if not getattr(sys, 'frozen', False):
        return None
    if not (Path(sys._MEIPASS) / 'aster-payload.zip').is_file():
        return None
    if sys.platform == 'linux':
        return Path(os.environ['APPIMAGE']).resolve() if os.environ.get('APPIMAGE') else None
    return Path(sys.executable).resolve() if sys.platform == 'win32' else None


def clean_env():
    from .paths import external_env
    env = external_env()
    for key in ('APPIMAGE', 'APPDIR', 'ARGV0', 'FONTCONFIG_FILE', 'TK_LIBRARY', 'TCL_LIBRARY',
                'ASTER_UPDATE_HEALTH_FILE', 'ASTER_UPDATE_NONCE'):
        env.pop(key, None)
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return env


def executable_command(path):
    return [str(path), *(['--appimage-extract-and-run'] if sys.platform == 'linux' else [])]


def stage_install(download, target, parent_pid=None):
    """Copy the current single-file launcher to run the updater after it exits."""
    target = Path(target).resolve()
    source = Path(download['path']).resolve()
    if target.suffix.lower() not in ('.exe', '.appimage') or not target.is_file():
        raise PortError('UPDATE_TARGET', 'Abra o EXE ou AppImage oficial para instalar pelo launcher.')
    if not os.access(target.parent, os.W_OK):
        raise PortError('UPDATE_TARGET', 'Mova o launcher para uma pasta gravável antes de atualizar.')
    verify_binary(source, download['sha256'], download['asset'])
    folder = source.parent
    helper = folder / ('updater' + target.suffix)
    shutil.copy2(target, helper)
    helper.chmod(0o755)
    plan = {'schema': 1, 'source': str(source), 'target': str(target),
        'old_sha256': file_hash(target), 'sha256': download['sha256'],
        'version': download['version'], 'asset': download['asset'],
        'parent_pid': parent_pid or os.getpid(), 'nonce': secrets.token_hex(24)}
    path = folder / 'install.json'
    _write_json(path, plan)
    command = [*executable_command(helper), '--aster-apply-update', str(path)]
    kwargs = {'env': clean_env(), 'stdin': subprocess.DEVNULL,
              'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL}
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs['start_new_session'] = True
    process = subprocess.Popen(command, **kwargs)
    return path, process


def _atomic_copy(source, target):
    fd, temporary = tempfile.mkstemp(prefix='.aster-update-', suffix=target.suffix, dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as out, Path(source).open('rb') as src:
            shutil.copyfileobj(src, out)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(temporary, 0o755)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


PREVIOUS_RE = re.compile(r'\.previous-(?P<hash>[0-9a-f]{12})$')


def previous_backups(target):
    """Older launcher copies adjacent to the executable, from releases before rc.6."""
    target = Path(target)
    found = []
    for path in target.parent.glob(target.name + '.previous-*'):
        match = PREVIOUS_RE.search(path.name)
        if match and path.is_file() and not path.is_symlink():
            found.append((path, match.group('hash')))
    return found


def prune_previous(target):
    """Remove older launchers kept next to the executable; only hash-matching copies."""
    for path, expected in previous_backups(target):
        try:
            if file_hash(path).startswith(expected):
                path.unlink()
        except OSError:
            continue


def commit_install(plan):
    source, target = Path(plan['source']), Path(plan['target'])
    verify_binary(source, plan['sha256'], plan['asset'])
    if file_hash(target) != plan['old_sha256']:
        raise PortError('UPDATE_CHANGED', 'O launcher foi alterado durante a atualização. Instalação cancelada.')
    # Rollback copy lives in the private staging folder, never beside the user's launcher.
    backup = source.parent / ('previous-' + plan['old_sha256'][:12])
    if backup.exists() or backup.is_symlink():
        if backup.is_symlink() or file_hash(backup) != plan['old_sha256']:
            raise PortError('UPDATE_BACKUP', 'Existe outro arquivo no destino do backup. Instalação cancelada.')
    else:
        _atomic_copy(target, backup)
    # Windows keeps the original onefile bootloader briefly after Python exits.
    deadline = time.monotonic() + 45
    while True:
        try:
            if file_hash(target) != plan['old_sha256']:
                raise PortError('UPDATE_CHANGED', 'O executável atual mudou; instalação cancelada.')
            _atomic_copy(source, target)
            return backup
        except PermissionError:
            if time.monotonic() >= deadline:
                raise PortError('UPDATE_LOCKED', 'O launcher ainda está em uso. Feche outras janelas e tente novamente.')
            time.sleep(.3)


def _wait_parent(pid):
    if type(pid) is not int or pid <= 0:
        raise ValueError('PID inválido no plano local.')
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if handle:
            try:
                kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
                if kernel.WaitForSingleObject(handle, 120000) != 0:
                    raise TimeoutError('O launcher anterior não foi encerrado.')
            finally:
                kernel.CloseHandle.argtypes = [ctypes.c_void_p]
                kernel.CloseHandle(handle)
        elif ctypes.get_last_error() != 87:  # ERROR_INVALID_PARAMETER: process exited.
            raise OSError('Não foi possível aguardar o launcher anterior.')
    else:
        deadline = time.monotonic() + 120
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            if time.monotonic() >= deadline:
                raise TimeoutError('O launcher anterior não foi encerrado.')
            time.sleep(.1)


def signal_started():
    path, nonce = os.environ.pop('ASTER_UPDATE_HEALTH_FILE', None), os.environ.pop('ASTER_UPDATE_NONCE', None)
    if path and nonce:
        _write_json(path, {'nonce': nonce, 'version': __version__})


def stop_child(process):
    if process.poll() is None:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            import signal
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        process.wait(timeout=10)


def _restore(backup, target):
    deadline = time.monotonic() + 45
    while True:
        try:
            _atomic_copy(backup, target)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(.3)


def previous_result():
    try:
        path = user_data_root() / 'updates/last-result.json'
        if path.stat().st_size <= 16384:
            return json.loads(path.read_text(encoding='utf8'))
    except (OSError, ValueError):
        pass
    return None


LAUNCHER_SUFFIXES = ('.exe', '.appimage')


def cleanup_downloads(directory=None):
    """Retire owned updater staging; never leave extra launcher binaries behind."""
    base = Path(directory) if directory else user_data_root() / 'updates'
    if not base.is_dir() or base.is_symlink():
        return
    now = time.time()
    for folder in list(base.glob('download-*'))[:100]:
        if not folder.is_dir() or folder.is_symlink():
            continue
        try:
            plan = json.loads((folder / 'install.json').read_text(encoding='utf8'))
            if Path(plan['source']).resolve().parent != folder.resolve():
                continue
            nonce = plan.get('nonce')
            if not isinstance(nonce, str) or not re.fullmatch('[0-9a-f]{48}', nonce):
                continue
            receipt = folder / 'finished.json'
            if receipt.is_file() and now - receipt.stat().st_mtime >= 10:
                result = json.loads(receipt.read_text(encoding='utf8'))
                if (result.get('nonce') == nonce and isinstance(result.get('success'), bool)):
                    shutil.rmtree(folder)
                    continue
            # Interrupted or failed attempt: keep small diagnostics, drop launcher copies.
            if now - folder.stat().st_mtime > 3600:
                for path in folder.iterdir():
                    if path.is_file() and path.suffix.lower() in LAUNCHER_SUFFIXES:
                        path.unlink(missing_ok=True)
        except (OSError, ValueError, TypeError, KeyError):
            continue


def _retire(path):
    """Best effort removal of a temporary launcher binary; never fatal."""
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def apply_update(plan_path):
    """Private frozen-entry dispatch. Only replaces the launcher, then reopens UI."""
    path = Path(plan_path).resolve()
    plan = json.loads(path.read_text(encoding='utf8'))
    folder = path.parent
    # Windows temp paths can be 8.3 short names (RUNNER~1); compare canonical paths.
    source = Path(plan['source']).resolve()
    if (plan.get('schema') != 1 or source.parent != folder or
            plan.get('asset') != asset_name() or not re.fullmatch('[0-9a-f]{48}', plan.get('nonce', ''))):
        raise ValueError('Plano local de atualização inválido.')
    plan['source'] = str(source)
    ready, health = folder / 'ready.json', folder / 'health.json'
    _write_json(ready, {'nonce': plan['nonce']})
    backup = None
    result = {'version': plan['version'], 'success': False}
    try:
        _wait_parent(plan['parent_pid'])
        backup = commit_install(plan)
        env = clean_env()
        env.update(ASTER_UPDATE_HEALTH_FILE=str(health), ASTER_UPDATE_NONCE=plan['nonce'])
        process = subprocess.Popen(executable_command(plan['target']), env=env,
                                   start_new_session=(os.name != 'nt'))
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if health.is_file():
                data = json.loads(health.read_text(encoding='utf8'))
                if data.get('nonce') == plan['nonce'] and version_key(data.get('version')) == version_key(plan['version']):
                    result['success'] = True
                    break
            if process.poll() is not None:
                break
            time.sleep(.2)
        if not result['success']:
            stop_child(process)
            raise PortError('UPDATE_START', 'A nova interface não iniciou corretamente; versão anterior restaurada.')
    except Exception as exc:
        result['error'] = str(exc)
        if backup:
            _restore(backup, Path(plan['target']))
        # Keep the failure note, never a second launcher binary.
        _retire(backup)
        _retire(plan['source'])
        _retire(folder / ('updater' + Path(plan['target']).suffix))
        result['backup'] = None
        _write_json(folder.parent / 'last-result.json', result)
        _write_json(folder / 'finished.json', {**result, 'nonce': plan['nonce']})
        if file_hash(plan['target']) == plan['old_sha256']:
            subprocess.Popen(executable_command(plan['target']), env=clean_env(),
                             start_new_session=(os.name != 'nt'))
        return 1
    # One launcher only: retire the rollback copy and the downloaded package, and remove
    # leftovers from releases that kept *.previous-<hash> beside the executable.
    _retire(backup)
    _retire(plan['source'])
    _retire(folder / ('updater' + Path(plan['target']).suffix))
    prune_previous(plan['target'])
    result['backup'] = None
    _write_json(folder.parent / 'last-result.json', result)
    _write_json(folder / 'finished.json', {**result, 'nonce': plan['nonce']})
    return 0 if result['success'] else 1
