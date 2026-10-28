#!/usr/bin/env python3
"""Build a portable launcher with the host platform's Python/PyInstaller.

Run on Linux for ELF, Windows Python (or Windows Python under Wine) for PE.
Only the explicit public source/resource allowlist is copied, never .aster.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import zipfile

PUBLIC_DIRS = ['native_port', 'games', 'integrations/rexglue']
PUBLIC_SCRIPTS = ['play_green_lantern.py']
FORBIDDEN_SUFFIXES = {'.xex', '.iso', '.xexp', '.lvl_760', '.pdb', '.xdb', '.vkcache', '.xsh', '.xpso', '.usm'}


def launcher_resource_arguments(root):
    """Data must sit beside frozen modules as well as in the public payload.

    PyInstaller's module importer can load native_port from _MEIPASS even after
    the bootstrap adds the persistent app directory to sys.path.
    """
    resources = Path(root) / 'native_port/resources'
    required = ['fonts/DejaVuSans.ttf', 'fonts/DejaVuSans-Bold.ttf',
                'fonts/DejaVuSansCondensed-Bold.ttf', 'fonts/LICENSE-DejaVu.txt']
    if (resources.is_symlink() or (resources / 'fonts').is_symlink() or
            any(not (resources / name).is_file() or (resources / name).is_symlink() for name in required)):
        raise ValueError('Bundled launcher fonts/license are missing or linked')
    return ['--add-data', str(resources) + os.pathsep + 'native_port/resources']


def single_file(bundle, work, output, command, env, root, args):
    payload = work / 'aster-payload.zip'
    with zipfile.ZipFile(payload, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for p in (bundle / 'app').rglob('*'):
            if p.is_file():
                z.write(p, p.relative_to(bundle / 'app'))
        for p in (bundle / 'LICENSES').rglob('*'):
            if p.is_file():
                z.write(p, Path('LICENSES') / p.relative_to(bundle / 'LICENSES'))
    if os.name == 'nt':
        packed = list(command)
        packed[packed.index('--onedir')] = '--onefile'
        packed[packed.index('--name') + 1] = 'AsterNative-windows-x64'
        packed[packed.index('--distpath') + 1] = str(output)
        packed[packed.index('--workpath') + 1] = str(work / 'onefile-build')
        packed[-1:-1] = ['--add-data', str(payload) + os.pathsep + '.']
        subprocess.run(packed, check=True, cwd=root, env=env)
        artifact = output / 'AsterNative-windows-x64.exe'
    else:
        if not args.appimagetool or not args.appimage_runtime:
            raise ValueError('--single-file Linux requires --appimagetool and --appimage-runtime')
        appdir = work / 'AppDir'
        # Only public packaged files are copied. No generated game build enters AppDir.
        if appdir.exists():
            shutil.rmtree(appdir)
        appdir.mkdir()
        shutil.copy2(bundle / 'AsterNative', appdir / 'AsterNative')
        shutil.copytree(bundle / '_internal', appdir / '_internal')
        shutil.copy2(payload, appdir / '_internal/aster-payload.zip')
        (appdir / 'AppRun').write_text('#!/bin/sh\nexec "$APPDIR/AsterNative" "$@"\n')
        (appdir / 'AppRun').chmod(0o755)
        (appdir / 'aster-native.desktop').write_text(
            '[Desktop Entry]\nType=Application\nName=Aster Native\n'
            'Exec=AsterNative\nIcon=aster-native\nCategories=Game;\nTerminal=false\n')
        (appdir / 'aster-native.svg').write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">'
            '<rect width="256" height="256" rx="48" fill="#101e20"/>'
            '<path d="M128 40 222 216h-42l-18-36H94l-18 36H34L128 40zm0 74-20 34h40z" fill="#71eea2"/></svg>')
        artifact = output / 'AsterNative-linux-x86_64.AppImage'
        app_env = env.copy()
        app_env.update({'ARCH': 'x86_64', 'APPIMAGE_EXTRACT_AND_RUN': '1'})
        subprocess.run([str(args.appimagetool.resolve()), '--runtime-file',
                        str(args.appimage_runtime.resolve()), str(appdir), str(artifact)],
                       check=True, env=app_env, cwd=root)
        artifact.chmod(0o755)
    print(json.dumps({'single_file': str(artifact), 'bytes': artifact.stat().st_size,
                      'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest()}))


def copy_public(root, destination):
    destination.mkdir(parents=True, exist_ok=True)
    copied = []
    for directory in PUBLIC_DIRS:
        for source in (root / directory).rglob('*'):
            if not source.is_file() or '__pycache__' in source.parts or source.suffix in ('.pyc', '.log'):
                continue
            if source.is_symlink() or source.suffix.lower() in FORBIDDEN_SUFFIXES:
                raise ValueError('Forbidden distribution input: ' + str(source))
            relative = source.relative_to(root)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(str(relative))
    for name in PUBLIC_SCRIPTS:
        (destination / 'scripts').mkdir(exist_ok=True)
        shutil.copy2(root / 'scripts' / name, destination / 'scripts' / name)
        copied.append('scripts/' + name)
    (destination / 'docs').mkdir(exist_ok=True)
    for name in ['PORTABLE_BUILD.md', 'THIRD_PARTY_NOTICES.md', 'HD_TEXTURES.md', 'WINDOWS_SPATIAL_SDK.md', 'SHADER_PREPARATION.md', 'LAUNCHER.md', 'LAUNCHER_UPDATES.md']:
        shutil.copy2(root / 'docs' / name, destination / 'docs' / name)
        copied.append('docs/' + name)
    for name in ['pyproject.toml']:
        shutil.copy2(root / name, destination / name)
        copied.append(name)
    shutil.copy2(root / 'docs/PORTABLE_BUILD.md', destination / 'README.md')
    copied.append('README.md')
    return copied


def prune_optional_linux_avif(bundle):
    """Remove Pillow's unused AVIF plugin and host C++ runtime from Linux.

    PyInstaller may copy the build host's libstdc++, which can require a newer
    glibc than the portable Python runtime. The launcher only needs Pillow for
    DDS/PNG/JPEG texture work; AVIF is not part of the supported release path.
    """
    if os.name == 'nt':
        return
    internal = bundle / '_internal'
    for path in [*internal.glob('PIL/_avif*.so'), *internal.glob('pillow.libs/libavif*'),
                 *internal.glob('libavif*')]:
        path.unlink(missing_ok=True)
    for name in ('libstdc++.so.6', 'libgcc_s.so.1'):
        (internal / name).unlink(missing_ok=True)


def apply_tk_runtime(bundle, prefix):
    """Overlay the audited Tk9/Xft closure, never system Tk8 or host libraries."""
    prefix = Path(prefix).resolve()
    manifest_path = prefix / 'TK_RUNTIME.json'
    manifest = json.loads(manifest_path.read_text())
    if (manifest.get('schema') != 1 or manifest.get('tk') != '9.0.4' or
            manifest.get('abi') != 'Tcl9' or manifest.get('xft') is not True or
            manifest.get('glibc_ceiling') != '2.27'):
        raise ValueError('Unsupported Tk runtime manifest')
    expected = manifest.get('files', {})
    if not expected or len(expected) > 5000:
        raise ValueError('Invalid Tk runtime file inventory')
    actual = {p.relative_to(prefix).as_posix() for p in prefix.rglob('*') if p.is_file()
              and p != manifest_path}
    if set(expected) != actual:
        raise ValueError('Tk runtime inventory changed')
    for relative, sha256 in expected.items():
        path = prefix / relative
        if (not path.resolve().is_relative_to(prefix) or path.is_symlink() or
                any(parent.is_symlink() for parent in path.parents if parent != prefix) or
                hashlib.sha256(path.read_bytes()).hexdigest() != sha256):
            raise ValueError('Tk runtime file changed: ' + relative)
    internal = bundle / '_internal'
    tk = internal / 'libtcl9tk9.0.so'
    if not tk.is_file():
        raise ValueError('Tk9 overlay requires a Tcl9/Tk9 portable Python build')
    for path in (prefix / 'lib').iterdir():
        if not path.is_file() or path.name.startswith(('libc.so', 'libm.so', 'libpthread.so', 'ld-linux')):
            raise ValueError('Forbidden runtime library: ' + path.name)
        shutil.copy2(path, internal / path.name)
    shutil.copytree(prefix / 'tk_data', internal / '_tk_data', dirs_exist_ok=True)
    shutil.copy2(prefix / 'launcher_fontconfig.conf', internal / 'launcher_fontconfig.conf')
    shutil.copytree(prefix / 'LICENSES', bundle / 'LICENSES/Tk9-Xft', dirs_exist_ok=True)
    shutil.copy2(manifest_path, bundle / 'LICENSES/Tk9-Xft/TK_RUNTIME.json')


def needs_tk_xft_overlay(base_prefix):
    """Known portable Tk9 builds omit scalable fonts; fail before packaging."""
    library = Path(base_prefix) / 'lib/libtcl9tk9.0.so'
    return library.is_file() and b'XftFontOpen' not in library.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('dist'))
    parser.add_argument('--cmake-data', type=Path)
    parser.add_argument('--ninja', type=Path)
    parser.add_argument('--single-file', action='store_true')
    parser.add_argument('--appimagetool', type=Path)
    parser.add_argument('--appimage-runtime', type=Path)
    parser.add_argument('--tk-runtime-prefix', type=Path,
                        help='Linux: audited Tk9/Xft overlay from build_launcher_tk.py')
    args = parser.parse_args()
    if os.name == 'nt' and args.tk_runtime_prefix:
        parser.error('--tk-runtime-prefix applies only to Linux')
    if os.name != 'nt' and not args.tk_runtime_prefix and needs_tk_xft_overlay(sys.base_prefix):
        parser.error('Portable Tk9 lacks Xft. Build scripts/build_launcher_tk.py and supply --tk-runtime-prefix.')
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    target = 'windows-x64' if os.name == 'nt' else 'linux-x86_64'
    work = root / '.aster/packaging' / target
    work.mkdir(parents=True, exist_ok=True)
    entry = root / 'apps/launcher/portable_entry.py'
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
               '--name', 'AsterNative', '--distpath', str(output / target),
               '--workpath', str(work / 'build'), '--specpath', str(work),
               '--paths', str(root), '--collect-submodules', 'native_port',
               '--collect-submodules', 'games', '--collect-submodules', 'tkinter',
               '--hidden-import', 'ssl', '--hidden-import', 'tomllib',
               '--hidden-import', 'urllib.request', '--hidden-import', 'zipfile',
               '--hidden-import', 'shlex', str(entry)]
    command[-1:-1] = launcher_resource_arguments(root)
    if args.tk_runtime_prefix:
        command[-1:-1] = ['--runtime-hook', str(root / 'scripts/launcher_tk_hook.py')]
    if os.name == 'nt':
        command.insert(4, '--windowed')
    else:
        command[4:4] = ['--hidden-import', 'resource', '--hidden-import', 'PIL._tkinter_finder']
    env = os.environ.copy()
    env['PYINSTALLER_CONFIG_DIR'] = str(work / 'cache')
    subprocess.run(command, check=True, cwd=root, env=env)
    bundle = output / target / 'AsterNative'
    prune_optional_linux_avif(bundle)
    if args.tk_runtime_prefix:
        apply_tk_runtime(bundle, args.tk_runtime_prefix)
    sources = copy_public(root, bundle / 'app')
    if args.cmake_data:
        cmake = bundle / 'app/tools/cmake'
        for directory in ('bin', 'share'):
            shutil.copytree(args.cmake_data / directory, cmake / directory, dirs_exist_ok=True)
    if args.ninja:
        ninja = bundle / 'app/tools/ninja'
        ninja.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.ninja, ninja / args.ninja.name)
    licenses = bundle / 'LICENSES'
    licenses.mkdir(exist_ok=True)
    shutil.copy2(root / 'native_port/resources/fonts/LICENSE-DejaVu.txt', licenses / 'DejaVu-LICENSE.txt')
    candidates = [Path(sys.base_prefix) / 'LICENSE.txt',
                  Path(sys.base_prefix) / 'lib' / ('python' + str(sys.version_info.major) + '.' + str(sys.version_info.minor)) / 'LICENSE.txt']
    for candidate in candidates:
        if candidate.is_file():
            shutil.copy2(candidate, licenses / 'Python-LICENSE.txt')
    import importlib.metadata
    distribution = importlib.metadata.distribution('pyinstaller')
    for relative in distribution.files or []:
        if relative.name in ('COPYING.txt', 'LICENSE', 'LICENSE.txt'):
            source = Path(distribution.locate_file(relative))
            if source.is_file():
                shutil.copy2(source, licenses / ('PyInstaller-' + source.name))
    for dependency in ('Pillow', 'xxhash', 'capstone'):
        distribution = importlib.metadata.distribution(dependency)
        for relative in distribution.files or []:
            if '.dist-info' in str(relative) and ('license' in relative.name.lower() or relative.name in ('COPYING', 'COPYING.txt')):
                source = Path(distribution.locate_file(relative))
                if source.is_file():
                    destination = licenses / dependency / relative.name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    if args.cmake_data and (args.cmake_data / 'doc').is_dir():
        shutil.copytree(args.cmake_data / 'doc', licenses / 'CMake', dirs_exist_ok=True)
    if args.ninja:
        wheel_root = args.ninja.resolve().parents[2]
        for directory in wheel_root.glob('ninja-*.dist-info'):
            for source in directory.rglob('*'):
                if source.is_file() and ('license' in str(source).lower() or 'copying' in source.name.lower()):
                    shutil.copy2(source, licenses / ('Ninja-' + source.name))
    for base in [Path(sys.base_prefix) / 'tcl', Path(sys.base_prefix) / 'lib']:
        if base.is_dir():
            for terms in base.glob('*/license.terms'):
                shutil.copy2(terms, licenses / ('TclTk-' + terms.parent.name + '.txt'))
    shutil.copy2(root / 'docs/THIRD_PARTY_NOTICES.md', bundle / 'THIRD_PARTY_NOTICES.md')
    if args.appimage_runtime:
        runtime_license = args.appimage_runtime.parent / 'appimage-runtime-LICENSE'
        if not runtime_license.is_file():
            raise ValueError('Supply appimage-runtime-LICENSE alongside the AppImage runtime')
        shutil.copy2(runtime_license, licenses / 'AppImage-runtime-LICENSE')
    notice = bundle / 'LEIA-ME.txt' 
    notice.write_text('Aster Native - launcher experimental\n\n'
        'Extraia TODA a pasta. Abra AsterNative.exe (Windows) ou AsterNative (Linux).\n'
        'Selecione seu dump extraido, abra Jogo e arquivos e clique Gerar port nativo.\n'
        'A geracao requer Clang >=18 / C++23. Ao confirmar Gerar port, o launcher\n'
        'prepara requisitos ausentes pelos instaladores oficiais conhecidos.\n'
        'Pode exigir administrador e varios GB. Windows requer WinGet; Linux\n'
        'requer distribuicao suportada e PolicyKit. Drivers nao sao instalados.\n'
        'O SDK ReXGlue fixado e baixado com verificacao de hash. Nenhum arquivo do\n'
        'jogo ou codigo recompilado e distribuido neste pacote.\n'
        'Revisao suportada: SHA256 do default.xex\n'
        '3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1\n'
        'Use uma pasta gravavel. Veja app/docs/PORTABLE_BUILD.md.\n', encoding='utf8')
    manifest = {'platform': target, 'public_sources': sources, 'game_content_included': False,
                'files': {str(p.relative_to(bundle)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in bundle.rglob('*') if p.is_file()}}
    (bundle / 'PACKAGE.json').write_text(json.dumps(manifest, indent=2) + '\n')
    if args.single_file:
        single_file(bundle, work, output, command, env, root, args)
        return
    if os.name == 'nt':
        archive = output / 'AsterNative-windows-x64.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            for p in bundle.rglob('*'):
                if p.is_file():
                    z.write(p, Path('AsterNative') / p.relative_to(bundle))
    else:
        archive = output / 'AsterNative-linux-x86_64.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            tar.add(bundle, arcname='AsterNative')
    print(json.dumps({'bundle': str(bundle), 'archive': str(archive),
                      'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
