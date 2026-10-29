"""Generate and compile a local port from the supported, user-provided XEX.

No generated source or game binary is shipped. Downloads are pinned SDK tools.
The build lives in a new content-addressed directory, never in the old builds.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import tempfile
import urllib.request
import zipfile

from .errors import PortError
from .paths import external_env
from .sources import digest_source, inspect_source
from .tasks import Cancellation, run_process
from .workspace import Workspace

XEX_SHA256 = '3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1'
SDK_VERSION = '0.10.0'
INTEGRATION_VERSION = 23
SDK_ASSETS = {
    'linux-amd64': '0388edb3f8fb1444f1b0ad5d440cb02d9690ac20a76b04fd6b7dcc19f59328a6',
    'win-amd64': 'ad4485da853fbe932e9f5dbb643f9b5fe85dc73775ebbad4df6879fe6df0c11b',
}
INSTALL = 'config/native-install.json'


def host_platform():
    if platform.machine().lower() not in ('amd64', 'x86_64'):
        raise PortError('BUILD_PLATFORM', 'O port atual requer um PC x86-64.')
    if os.name == 'nt':
        return 'win-amd64'
    if platform.system() == 'Linux':
        return 'linux-amd64'
    raise PortError('BUILD_PLATFORM', 'Geração disponível para Linux x86-64 e Windows x64.')


def file_hash(path):
    return digest_source(path, Cancellation())


def safe_extract(archive, destination):
    """Reject absolute paths, traversal, links and unexpectedly large archives."""
    with zipfile.ZipFile(archive) as package:
        members = package.infolist()
        if sum(m.file_size for m in members) > 3 * 1024**3:
            raise PortError('SDK_ARCHIVE', 'SDK excede o limite de extração.')
        for member in members:
            name = PurePosixPath(member.filename.replace('\\', '/'))
            mode = member.external_attr >> 16
            if (name.is_absolute() or '..' in name.parts or ':' in str(name)
                    or stat.S_ISLNK(mode)):
                raise PortError('SDK_ARCHIVE', 'Arquivo inseguro no pacote do SDK.')
        package.extractall(destination)
        for member in members:
            mode = member.external_attr >> 16
            if mode & stat.S_IXUSR and not member.is_dir():
                (destination / member.filename).chmod(0o755)


def ensure_sdk(work, cancel, emit, allow_download=False):
    target = host_platform()
    prefix = work.path(f'tools/rexglue-{SDK_VERSION}/{target}')
    generator = prefix / 'bin' / ('rexglue.exe' if os.name == 'nt' else 'rexglue')
    if generator.is_file() and (prefix / 'lib/cmake/rexglue').is_dir():
        return prefix
    if not allow_download:
        raise PortError('SDK_MISSING', 'SDK ausente. Habilite baixar SDK oficial e tente novamente.')
    filename = f'rexglue-sdk-{SDK_VERSION}-{target}.zip'
    archive = work.path(f'tools/downloads/{filename}')
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.is_file() or file_hash(archive) != SDK_ASSETS[target]:
        url = f'https://github.com/rexglue/rexglue-sdk/releases/download/v{SDK_VERSION}/{filename}'
        emit({'task': 'Baixar SDK oficial', 'state': 'running', 'message': url})
        fd, temporary = tempfile.mkstemp(dir=archive.parent, prefix='.download-')
        try:
            with os.fdopen(fd, 'wb') as output, urllib.request.urlopen(url, timeout=30) as response:
                total = int(response.headers.get('Content-Length', 0))
                while block := response.read(1024 * 1024):
                    cancel.check()
                    output.write(block)
                    emit({'task': 'Baixar SDK oficial', 'stage': 'tools', 'state': 'running',
                          'completed': output.tell(), 'total': total, 'unit': 'bytes'})
                    if output.tell() > 512 * 1024**2:
                        raise PortError('SDK_DOWNLOAD', 'Pacote maior que o esperado.')
            if file_hash(Path(temporary)) != SDK_ASSETS[target]:
                raise PortError('SDK_HASH', 'O hash do SDK não corresponde à versão fixada.')
            os.replace(temporary, archive)
        finally:
            Path(temporary).unlink(missing_ok=True)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=prefix.parent) as temporary:
        safe_extract(archive, Path(temporary))
        extracted = Path(temporary) / target
        if not (extracted / 'bin' / generator.name).is_file():
            raise PortError('SDK_ARCHIVE', 'SDK sem gerador esperado.')
        # Existing incomplete directories are retained for diagnosis.
        if prefix.exists():
            raise PortError('SDK_INCOMPLETE', f'SDK incompleto preservado em {prefix}; selecione outro workspace.')
        shutil.move(str(extracted), prefix)
    return prefix


def companion_c_compiler(compiler):
    path = Path(compiler)
    if path.name in ('clang-cl', 'clang-cl.exe'):
        return str(path)
    name = path.name.replace('clang++', 'clang', 1) if path.name.startswith('clang++') else 'clang'
    return str(path.with_name(name))


def toolchain(root, work):
    suffix = '.exe' if os.name == 'nt' else ''
    env = external_env()
    if os.name == 'nt':
        env = {key.upper(): value for key, value in env.items()}
        # Newly installed tools may not be in this launcher's inherited PATH.
        program_files = Path(env.get('PROGRAMFILES', 'C:/Program Files'))
        additions = [program_files / 'Git/cmd', program_files / 'CMake/bin']
        env['PATH'] = os.pathsep.join(str(p) for p in additions if p.is_dir()) + os.pathsep + env.get('PATH', '')
    if os.name == 'nt' and not env.get('VCTOOLSINSTALLDIR'):
        finder = Path(env.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
        if finder.is_file():
            result = run_process([str(finder), '-latest', '-products', '*', '-requires',
                                  'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
                                  '-property', 'installationPath'], root, Cancellation(), env=env)
            installation = result['stdout'].strip()
            vcvars = Path(installation) / 'VC/Auxiliary/Build/vcvars64.bat'
            if vcvars.is_file():
                result = run_process(['cmd.exe', '/d', '/s', '/c', f'""{vcvars}" >nul && set"'],
                                     root, Cancellation(), env=env)
                env.update((line.split('=', 1)[0].upper(), line.split('=', 1)[1]) for line in result['stdout'].splitlines() if '=' in line and not line.startswith('='))
                llvm = Path(installation) / 'VC/Tools/Llvm/x64/bin'
                cmake_tools = Path(installation) / 'Common7/IDE/CommonExtensions/Microsoft/CMake'
                env['PATH'] = os.pathsep.join(map(str, [llvm, cmake_tools/'CMake/bin', cmake_tools/'Ninja'])) + os.pathsep + env.get('PATH', '')
    def find(name):
        candidates = [root / f'tools/{name}/bin/{name}{suffix}',
                      root / f'tools/{name}/{name}{suffix}']
        if name == 'cmake':
            candidates.append(work.path(f'tools/cmake-runtime/cmake/data/bin/cmake{suffix}'))
        return next((str(p) for p in candidates if p.is_file()), None) or shutil.which(name, path=env.get('PATH'))
    cmake, ninja = find('cmake'), find('ninja')
    compiler_names = ['clang-cl'] if os.name == 'nt' else ['clang++', *('clang++-'+str(v) for v in range(22, 17, -1))]
    candidates = []
    for name in compiler_names:
        path = shutil.which(name, path=env.get('PATH'))
        if not path:
            continue
        try:
            probe = run_process([path, '--version'], root, Cancellation(), env=env, timeout=10)
            match = re.search(r'clang version (\d+)', probe['stdout'] + probe['stderr'])
            if match and int(match[1]) >= 18:
                candidates.append((int(match[1]), path))
        except PortError:
            continue
    compiler = max(candidates, default=(0, None), key=lambda item: item[0])[1]
    missing = [name for name, value in [('CMake >=3.25', cmake), ('Ninja', ninja), ('Clang >=18 + C++23', compiler)] if not value]
    if os.name == 'nt' and not env.get('VCTOOLSINSTALLDIR'):
        missing.append('Visual Studio Build Tools: C++ x64 + Windows SDK + Clang')
    if missing:
        raise PortError('BUILD_TOOLS', 'Instale as ferramentas de compilação: ' + ', '.join(missing)
                        + '. Veja docs/PORTABLE_BUILD.md. O launcher e os saves foram preservados.')
    return cmake, ninja, compiler, env


def read_install(root):
    path = Path(root) / '.aster' / INSTALL
    if not path.is_file():
        return None
    try:
        if path.stat().st_size > 1024 * 1024:
            raise ValueError('manifest too large')
        data = json.loads(path.read_text(encoding='utf8'))
        if data.get('schema') != 1 or data.get('xex_sha256') != XEX_SHA256 or data.get('state') != 'built':
            raise ValueError('invalid manifest')
        if (not isinstance(data.get('files'), dict) or not isinstance(data.get('binary'), str)
                or data['binary'] not in data['files'] or not isinstance(data.get('game_root'), str)
                or data.get('renderer') not in ('vulkan-fsi', 'd3d12-rov')
                or any(not isinstance(k, str) or not isinstance(v, str) or not re.fullmatch(r'[0-9a-f]{64}', v)
                       for k, v in data['files'].items())):
            raise ValueError('invalid artifacts')
        for value in [data['binary'], *data['files']]:
            p = (Path(root) / value).resolve()
            if not p.is_relative_to((Path(root) / '.aster').resolve()):
                raise ValueError('path outside workspace')
        return data
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise PortError('BUILD_MANIFEST', 'Manifesto do build local inválido: ' + str(exc)) from exc


def backend_update_reason(data):
    """Use the same backend compatibility gate in the GUI and play script.

    Replacing a launcher does not replace a previously compiled renderer.
    The Linux quality filter and the shared surface fix must actually be in
    the installed SDK; D3D12 already uses the quality filter.
    """
    if not data:
        return ''
    recipe = data.get('recipe', {})
    version = recipe.get('integration', 0)
    if type(version) is not int or version < INTEGRATION_VERSION:
        return (f'Backend {version} instalado; este launcher exige backend '
                f'{INTEGRATION_VERSION}. Use Gerar port/Atualizar port.')
    if data.get('presentation_backend') != 'sdk-spatial-fsr1':
        return 'Atualize o backend espacial em Gerar port/Atualizar port.'
    patches = recipe.get('sdk_spatial', {}).get('patches', {})
    required = {'0032-refresh-unchanged-surface-size.patch',
                '0033-retire-present-queue.patch',
                '0034-bounded-hd-source-cache.patch'}
    if data.get('renderer') == 'vulkan-fsi':
        required.add('0031-vulkan-fxaa-quality-parity.patch')
    if required.difference(patches):
        return 'Faltam correções de texto/apresentação no backend. Use Gerar port/Atualizar port.'
    return ''


def verify_install(root, data):
    if data.get('platform') != host_platform():
        raise PortError('BUILD_PLATFORM', 'Este port foi compilado para outro sistema operacional.')
    for relative, expected in data['files'].items():
        p = (Path(root) / relative).resolve()
        if not p.is_relative_to((Path(root) / '.aster').resolve()) or not p.is_file() or file_hash(p) != expected:
            raise PortError('BUILD_CHANGED', f'Arquivo do port ausente ou alterado: {relative}. Gere-o novamente.')


def cpu_sdk_identity(recipe):
    """Exclude audited implementation-only changes from CPU host reuse.

    Patches 0023/0024 change no public type or layout. Patch 0025 adds one CVar
    declaration and GPU-only selection branches, with no existing ABI change.
    Patch 0027 changes Vulkan submission scheduling and protects memory exports;
    no declarations, data members or layouts change.
    Patch 0033 drains the existing presentation queue on swapchain retirement;
    no header, class layout or normal frame scheduling changes.
    Patch 0032 refreshes the existing presenter connection on repeated native
    size notifications, within window.cpp; no header/ABI change.
    Patch 0031 replaces Vulkan postprocess shader source only; all existing
    types, layouts and shader descriptors stay unchanged.
    Patch 0030 adds inline UI storage validation/selection without fields, types
    or virtual function changes; existing replacement/mip layouts are unchanged.
    Patch 0029 adds optional raw pixel constants to an existing bounded diagnostic
    in texture/cache.cpp; no public type changes.
    Patch 0028 stores a once-only window retry in SDL properties, changing only
    the focus event implementation and no class layout.
    Patch 0026 only stores an existing presenter's pipeline format after creation;
    no header, public type or layout changes. Presenter/UI patches 0004 and 0022
    remain ABI-sensitive. Patch 0034 adds HDTexturePack storage in a public
    header and conservatively requires a new host as well. Unknown future patches force a
    new host; guest hints, hook, platform and binary hashes are checked separately.
    """
    if recipe is None:
        return None
    result = dict(recipe)
    gpu_only = {'0005-texture-inspection-capture.patch', '0006-reviewed-hd-texture-override.patch',
                '0007-isolated-sdk-install.patch', '0008-hd-selection-cache.patch',
                '0009-multi-material-hd-pack.patch', '0010-gameplay-texture-capture-arm.patch', '0011-hd-texture-scales.patch', '0012-campaign-texture-library.patch', '0013-windows-hd-library-path.patch', '0014-portable-mspack-source-path.patch',
                '0015-scaled-resolve-diagnostics.patch', '0016-reviewed-ui-alpha-atlas.patch',
                '0017-scaled-texture-offset-flag-parity.patch', '0018-effects-sampling-diagnostics.patch',
                '0019-armed-effects-source-index.patch', '0020-effects-decision-diagnostics.patch',
                '0021-d3d12-blocking-shader-prewarm.patch',
                '0023-guest-vblank-video-mode-clock.patch',
                '0024-scaled-pixel-parameter-centers.patch',
                '0025-known-shader-preload-selection.patch',
                '0026-presenter-pipeline-format-cache.patch',
                '0027-worker-only-async-submissions.patch',
                '0028-startup-fullscreen-focus-retry.patch',
                '0029-effects-pixel-constants.patch',
                '0030-ui-uncompressed-coverage.patch',
                '0031-vulkan-fxaa-quality-parity.patch',
                '0032-refresh-unchanged-surface-size.patch',
                '0033-retire-present-queue.patch'}
    result['patches'] = {name: digest for name, digest in recipe.get('patches', {}).items() if name not in gpu_only}
    return result


def _build_native(source, workspace, cancel=None, emit=None, jobs=2, allow_download=False, install_dependencies=False):
    cancel, emit = cancel or Cancellation(), emit or (lambda event: None)
    root = workspace.project
    if workspace.root != root / '.aster':
        raise PortError('BUILD_WORKSPACE', 'A geração nativa usa o workspace .aster padrão do launcher.')
    if type(jobs) is not int or not 1 <= jobs <= 64:
        raise PortError('BUILD_JOBS', 'Número de tarefas inválido.')
    info = inspect_source(source, cancel)
    if not info.get('game_directory') or Path(info['path']).name.lower() != 'default.xex':
        raise PortError('BUILD_DUMP', 'Selecione a pasta extraída contendo default.xex e os assets.')
    game, xex = Path(info['game_directory']), Path(info['path'])
    if workspace.root.is_relative_to(game) or game.is_relative_to(workspace.root):
        raise PortError('SOURCE_OVERLAP', 'O dump deve ficar fora do workspace.')
    emit({'task': 'Verificar dump', 'state': 'running'})
    if digest_source(xex, cancel) != XEX_SHA256:
        raise PortError('BUILD_REVISION', 'Revisão do XEX ainda não suportada. O original não foi alterado.')
    hints = root / 'games/green_lantern_rex_hints.toml'
    hook = root / 'integrations/rexglue/portable_timing.cpp'
    # Both platforms use the same complete spatial SDK; only developers may
    # explicitly select the old Linux ABI for regression comparisons.
    use_spatial_sdk = os.name == 'nt' or os.environ.get('ASTER_USE_LEGACY_SDK') != '1'
    from .spatial_sdk import spatial_sdk_recipe, build_spatial_sdk
    spatial_recipe = spatial_sdk_recipe(root, host_platform()) if use_spatial_sdk else None
    recipe = {'sdk': SDK_VERSION, 'sdk_spatial': spatial_recipe, 'platform': host_platform(), 'xex': XEX_SHA256,
              'hints': file_hash(hints), 'hook': file_hash(hook), 'integration': INTEGRATION_VERSION,
              'cache_project': file_hash(root / 'integrations/rexglue/plugin-only/CMakeLists.txt') if os.name != 'nt' else None,
              'driver_cache_patch': file_hash(root / 'integrations/rexglue/patches/0001-vulkan-driver-pipeline-cache.patch') if os.name != 'nt' else None,
              'deferred_pipeline_patch': file_hash(root / 'integrations/rexglue/patches/0003-vulkan-deferred-pipelines.patch') if os.name != 'nt' else None,
              'texture_inspection_patch': file_hash(root / 'integrations/rexglue/patches/0005-texture-inspection-capture.patch'),
              'hd_texture_patch': file_hash(root / 'integrations/rexglue/patches/0006-reviewed-hd-texture-override.patch'),
              'presenter_filter': {p.name: file_hash(p) for p in sorted((root / 'integrations/rexglue/presenter-filter').iterdir()) if p.is_file()} if os.name != 'nt' else None}
    key = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()[:20]
    try:
        current = read_install(root)
    except PortError:
        import time
        backup = workspace.path(f'reports/native-install-invalid-{time.time_ns()}.json')
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / '.aster' / INSTALL, backup)
        current = None
    if current and current.get('recipe') == recipe:
        try:
            verify_install(root, current)
            if current.get('game_root') != str(game):
                current['game_root'] = str(game)
                workspace.write_json(INSTALL, current)
            emit({'task': 'Port já compilado', 'state': 'completed', 'message': 'Cache de compilação íntegro; nada foi recompilado.'})
            return current
        except PortError:
            pass
    # Implementation-only SDK updates reuse the compiled CPU host when the
    # public ABI, hints and timing hook match. Runtime libraries are restaged
    # and hashed for the new SDK. A modified/missing host is never reused.
    reusable_host = None
    if current:
        previous = current.get('recipe', {})
        host_fields = ('sdk', 'platform', 'xex', 'hints', 'hook')
        candidate = root / current['binary']
        if (all(previous.get(key) == recipe[key] for key in host_fields)
                and cpu_sdk_identity(previous.get('sdk_spatial')) == cpu_sdk_identity(recipe.get('sdk_spatial'))
                and previous.get('integration') in (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23)
                and candidate.is_file()
                and current.get('files', {}).get(current['binary']) == file_hash(candidate)):
            reusable_host = candidate
    emit({'stage': 'tools', 'state': 'running', 'message': 'Verificando ferramentas e SDK'})
    if install_dependencies:
        from .prerequisites import ensure_build_dependencies
        ensure_build_dependencies(root, workspace, cancel, emit, allowed=True)
    cmake, ninja, compiler, env = toolchain(root, workspace)
    prefix = (build_spatial_sdk(root, workspace, (cmake, ninja, compiler, env), cancel, emit, allow_download, jobs)
              if use_spatial_sdk else ensure_sdk(workspace, cancel, emit, allow_download))
    emit({'stage': 'tools', 'state': 'completed'})
    generator = prefix / 'bin' / ('rexglue.exe' if os.name == 'nt' else 'rexglue')
    project = workspace.path(f'native/{key}/project')
    build = workspace.path(f'native/{key}/build')
    logs = workspace.path(f'native/{key}/logs')
    logs.mkdir(parents=True, exist_ok=True)
    def run(name, command, timeout=7200):
        cancel.check()
        emit({'task': name, 'state': 'running', 'message': name})
        stage = 'cache' if 'cache persistente' in name else 'compile' if name in ('Configurar build', 'Compilar port local') else 'codegen'
        def output(line):
            match = re.search(r'\[(\d+)/(\d+)\]', line)
            if match:
                emit({'stage': stage, 'state': 'running', 'message': line[:160],
                      'completed': int(match[1]), 'total': int(match[2]), 'unit': 'targets'})
        try:
            result = run_process(list(map(str, command)), root, cancel, timeout=timeout, env=env, on_output=output)
        except PortError as exc:
            workspace.write_json(f'native/{key}/logs/failure.json', exc.as_dict())
            raise
        (logs / (re.sub(r'[^a-zA-Z0-9]+', '-', name) + '.log')).write_text(result['stdout'] + result['stderr'], encoding='utf8')
        emit({'task': name, 'state': 'completed'})
    cache_plugin = None
    presenter_filter = None
    arena_lifetime = None
    emit({'stage': 'cache', 'state': 'running', 'message': 'Preparando cache gráfico'})
    if os.name != 'nt':
        from .native_cache import build_cache_plugin, build_presenter_filter, build_arena_lifetime
        cache_plugin = build_cache_plugin(root, workspace, prefix, (cmake, ninja, compiler, env),
                                          cancel, emit, run, allow_download)
        if use_spatial_sdk:
            arena_lifetime = build_arena_lifetime(root, workspace, (cmake, ninja, compiler, env), cancel, run)
        else:
            presenter_filter = build_presenter_filter(root, workspace, prefix, (cmake, ninja, compiler, env), cancel, run)
    emit({'stage': 'cache', 'state': 'completed', 'message': 'Cache pronto' if cache_plugin else 'Etapa dispensada nesta plataforma'})
    emit({'stage': 'codegen', 'state': 'running', 'message': 'Gerando o código nativo'})
    if reusable_host:
        emit({'stage': 'codegen', 'state': 'completed', 'message': 'CPU já gerada e verificada; reutilizando'})
        emit({'stage': 'compile', 'state': 'running', 'message': 'Atualizando somente componentes gráficos'})
        build.mkdir(parents=True, exist_ok=True)
        destination = build / reusable_host.name
        if reusable_host.resolve() != destination.resolve():
            shutil.copy2(reusable_host, destination)
    else:
        manifest = project / 'aster_green_lantern_manifest.toml'
        if not manifest.is_file():
            run('Criar projeto nativo', [generator, 'init', '--project-name', 'aster_green_lantern',
                                        '--xex-path', xex, '--game-root', game, '--project-root', project])
            shutil.copy2(hints, project / 'hints.toml')
            # SDK init lowercases asset paths and emits an empty includes list.
            # Preserve the actual case on Linux and write one unambiguous manifest.
            def relative(path):
                try:
                    return Path(os.path.relpath(path, project)).as_posix()
                except ValueError:  # Different Windows drives.
                    return path.as_posix()
            manifest.write_text('[project]\nname = "aster_green_lantern"\nsdk_version = "0.10.0"\n'
                                + 'game_root = ' + json.dumps(relative(game), ensure_ascii=False) + '\n\n'
                                + '[entrypoint]\nfile_path = ' + json.dumps(relative(xex), ensure_ascii=False)
                                + '\nout_directory_path = "generated/default"\nincludes = ["hints.toml"]\n', encoding='utf8')
            shutil.copy2(hook, project / 'aster_timing.cpp')
            cmake_file = project / 'CMakeLists.txt'
            content = cmake_file.read_text(encoding='utf8')
            content = content.replace('rexglue_setup_target(aster_green_lantern)',
                                      'rexglue_setup_target(aster_green_lantern GPU_PLUGINS xenos)')
            content += '\ntarget_sources(aster_green_lantern PRIVATE aster_timing.cpp)\n'
            cmake_file.write_text(content, encoding='utf8')
        stamp = project / 'aster-codegen.json'
        valid_codegen = False
        if stamp.is_file():
            try:
                recorded = json.loads(stamp.read_text(encoding='utf8'))
                valid_codegen = bool(recorded) and all(
                    (project / name).resolve().is_relative_to((project / 'generated').resolve())
                    and (project / name).is_file() and file_hash(project / name) == sha
                    for name, sha in recorded.items())
            except (ValueError, OSError, AttributeError):
                pass
        if not valid_codegen:
            run('Recompilar PowerPC para C++', [generator, 'codegen', manifest])
            generated = [p for p in (project / 'generated').rglob('*') if p.is_file()]
            if not generated:
                raise PortError('BUILD_CODEGEN', 'O gerador não produziu arquivos C++.')
            stamp.write_text(json.dumps({str(p.relative_to(project)): file_hash(p) for p in generated}), encoding='utf8')
        else:
            emit({'task': 'Reutilizar C++ já gerado', 'state': 'completed'})
        emit({'stage': 'codegen', 'state': 'completed'})
        emit({'stage': 'compile', 'state': 'running', 'message': 'Configurando a compilação'})
        run('Configurar build', [cmake, '-S', project, '-B', build, '-G', 'Ninja',
                                 '-DCMAKE_BUILD_TYPE=RelWithDebInfo', f'-DCMAKE_PREFIX_PATH={prefix}',
                                 f'-DCMAKE_CXX_COMPILER={compiler}', f'-DCMAKE_MAKE_PROGRAM={ninja}',
                                 '-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF', '-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF'])
        run('Compilar port local', [cmake, '--build', build, '--parallel', str(jobs)])
    emit({'stage': 'compile', 'state': 'completed'})
    emit({'stage': 'verify', 'state': 'running', 'message': 'Conferindo o executável e as bibliotecas'})
    suffix = '.exe' if os.name == 'nt' else ''
    binary = build / ('aster_green_lantern' + suffix)
    if not binary.is_file():
        raise PortError('BUILD_ARTIFACT', 'A compilação não gerou o executável esperado.')
    for directory in [prefix / 'bin', prefix / 'lib']:
        for library in directory.iterdir():
            if library.is_file() and (library.suffix == '.dll' if os.name == 'nt' else '.so' in library.name):
                shutil.copy2(library, build / library.name)
    if cache_plugin:
        shutil.copy2(cache_plugin, build / cache_plugin.name)
    if presenter_filter:
        shutil.copy2(presenter_filter, build / presenter_filter.name)
    if arena_lifetime:
        shutil.copy2(arena_lifetime, build / arena_lifetime.name)
    if os.name != 'nt':
        run('Verificar bibliotecas', ['ldd', binary], timeout=30)
        result = run_process(['ldd', str(binary)], root, cancel, timeout=30, env=env)
        if 'not found' in result['stdout'] + result['stderr']:
            raise PortError('BUILD_DEPENDENCIES', 'Faltam bibliotecas de execução: ' + result['stdout'])
    if digest_source(xex, cancel) != XEX_SHA256:
        raise PortError('SOURCE_CHANGED', 'O XEX foi alterado durante a compilação.')
    artifacts = [binary, *[p for p in build.iterdir() if p.is_file() and
                          (p.suffix == '.dll' if os.name == 'nt' else '.so' in p.name)]]
    data = {'schema': 1, 'state': 'built', 'ready': False, 'gameplay_verified': False,
            'platform': host_platform(), 'recipe': recipe, 'xex_sha256': XEX_SHA256,
            'game_root': str(game), 'binary': str(binary.relative_to(root)),
            'files': {str(p.relative_to(root)): file_hash(p) for p in artifacts},
            'renderer': 'd3d12-rov' if os.name == 'nt' else 'vulkan-fsi',
            'presentation_backend': 'sdk-spatial-fsr1' if use_spatial_sdk else 'linux-spatial-shim',
            'message': 'Port compilado localmente; execução e campanha ainda precisam de validação.'}
    workspace.write_json(INSTALL, data)
    emit({'stage': 'verify', 'state': 'completed'})
    emit({'task': 'Port gerado', 'state': 'completed', 'message': data['message']})
    return data


def build_native(source, workspace, cancel=None, emit=None, jobs=2, allow_download=False, install_dependencies=False):
    # Validate the input before creating even a lock in the workspace.
    cancel = cancel or Cancellation()
    emit = emit or (lambda event: None)
    emit({'stage': 'dump', 'state': 'running', 'message': 'Conferindo os arquivos do seu dump'})
    info = inspect_source(source, cancel)
    if not info.get('game_directory'):
        raise PortError('BUILD_DUMP', 'Selecione a pasta extraída com default.xex e os assets.')
    if digest_source(info['path'], cancel) != XEX_SHA256:
        raise PortError('BUILD_REVISION', 'Revisão do XEX ainda não suportada. O original não foi alterado.')
    game = Path(info['game_directory']).resolve()
    if workspace.root.is_relative_to(game) or game.is_relative_to(workspace.root):
        raise PortError('SOURCE_OVERLAP', 'O dump deve ficar fora do workspace.')
    emit({'stage': 'dump', 'state': 'completed'})
    from .locking import lock_session
    lock = workspace.path('native/build.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = lock_session(lock)
    except BlockingIOError as exc:
        raise PortError('BUILD_BUSY', 'Já existe uma geração do port neste workspace.') from exc
    try:
        try:
            return _build_native(source, workspace, cancel, emit, jobs, allow_download, install_dependencies)
        except (OSError, zipfile.BadZipFile) as exc:
            raise PortError('BUILD_IO', 'Falha de leitura/download/extração: ' + str(exc)) from exc
    finally:
        os.close(descriptor)
