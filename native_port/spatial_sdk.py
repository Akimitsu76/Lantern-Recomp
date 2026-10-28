"""Source-build the pinned SDK's embedded spatial shaders, without temporal FFX.

This builds an entire ABI-consistent SDK in an isolated, content-addressed
prefix. Never replace a DLL in an existing install or reuse an older CPU host.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import tarfile
import tempfile

from .errors import PortError
from .tasks import run_process

SDK_REVISION = 'f5337cdc947ff6d4c4196737e2c807a48f2a1fc2'
SDK_REPOSITORY = 'https://github.com/rexglue/rexglue-sdk.git'
PATCHES = ('integrations/rexglue/patches/0004-embedded-spatial-sdk.patch',
           'integrations/rexglue/patches/0005-texture-inspection-capture.patch',
           'integrations/rexglue/patches/0006-reviewed-hd-texture-override.patch',
           'integrations/rexglue/patches/0007-isolated-sdk-install.patch',
           'integrations/rexglue/patches/0008-hd-selection-cache.patch',
           'integrations/rexglue/patches/0009-multi-material-hd-pack.patch',
           'integrations/rexglue/patches/0010-gameplay-texture-capture-arm.patch',
           'integrations/rexglue/patches/0011-hd-texture-scales.patch',
           'integrations/rexglue/patches/0012-campaign-texture-library.patch', 'integrations/rexglue/patches/0013-windows-hd-library-path.patch', 'integrations/rexglue/patches/0014-portable-mspack-source-path.patch',
           'integrations/rexglue/patches/0015-scaled-resolve-diagnostics.patch',
           'integrations/rexglue/patches/0016-reviewed-ui-alpha-atlas.patch',
           'integrations/rexglue/patches/0017-scaled-texture-offset-flag-parity.patch',
           'integrations/rexglue/patches/0018-effects-sampling-diagnostics.patch',
           'integrations/rexglue/patches/0019-armed-effects-source-index.patch',
           'integrations/rexglue/patches/0020-effects-decision-diagnostics.patch',
           'integrations/rexglue/patches/0021-d3d12-blocking-shader-prewarm.patch',
           'integrations/rexglue/patches/0022-idle-notification-presentation.patch',
           'integrations/rexglue/patches/0023-guest-vblank-video-mode-clock.patch',
           'integrations/rexglue/patches/0024-scaled-pixel-parameter-centers.patch',
           'integrations/rexglue/patches/0025-known-shader-preload-selection.patch',
           'integrations/rexglue/patches/0026-presenter-pipeline-format-cache.patch',
           'integrations/rexglue/patches/0027-worker-only-async-submissions.patch',
           'integrations/rexglue/patches/0028-startup-fullscreen-focus-retry.patch',
           'integrations/rexglue/patches/0029-effects-pixel-constants.patch',
           'integrations/rexglue/patches/0030-ui-uncompressed-coverage.patch',
           'integrations/rexglue/patches/0031-vulkan-fxaa-quality-parity.patch',
           'integrations/rexglue/patches/0032-refresh-unchanged-surface-size.patch',
           'integrations/rexglue/patches/0033-retire-present-queue.patch')
CAPABILITY = 'sdk-spatial-fsr1'
# Bump only when build semantics change. Logging/comments must not invalidate
# gigabytes of correctly compiled source or force another source download.
BUILDER_REVISION = 2
BASELINE_FLAGS = '-march=x86-64-v2'  # pinned windows-base and linux-base presets


def spatial_sdk_recipe(root, target):
    from .native_build import file_hash
    return {'revision': SDK_REVISION, 'patches': {Path(p).name: file_hash(Path(root) / p) for p in PATCHES},
            'platform': target, 'builder_revision': BUILDER_REVISION, 'schema': 2,
            'baseline_flags': BASELINE_FLAGS, 'configurations': ['Release', 'RelWithDebInfo'],
            'generator': 'Ninja Multi-Config', 'spatial_filters': True,
            'temporal_fidelityfx': False, 'user_package_registry': False, 'tests': False}


def verify_product(prefix, recipe):
    """Only accept exact complete artifacts; a capability is never inferred."""
    from .native_build import file_hash
    manifest = prefix / 'aster-spatial-sdk.json'
    try:
        data = json.loads(manifest.read_text(encoding='utf8'))
        if data.get('recipe') != recipe or data.get('capability') != CAPABILITY:
            return False
        files = data.get('files')
        if not isinstance(files, dict) or not files:
            return False
        for relative, expected in files.items():
            path = (prefix / relative).resolve()
            if not path.is_relative_to(prefix.resolve()) or not path.is_file() or file_hash(path) != expected:
                return False
        generator = 'rexglue.exe' if recipe['platform'] == 'win-amd64' else 'rexglue'
        runtime = 'bin/rexruntimerd.dll' if recipe['platform'] == 'win-amd64' else 'lib/librexruntimerd.so'
        return ('bin/' + generator in files and runtime in files and
                any(name.endswith('rexglueConfig.cmake') for name in files))
    except (OSError, ValueError, TypeError):
        return False


def normalized_patch(text):
    """Inventory both Git and plain unified patches accepted by apply_patch_exact."""
    sections, current, source_header = {}, None, None
    for line in text.splitlines():
        if line.startswith('diff --git '):
            current, source_header = None, None
        elif line.startswith(('--- a/', '--- /dev/null')):
            current, source_header = None, line
        elif line.startswith('+++ b/') and source_header is not None:
            current = line[6:]
            if current in sections:
                raise PortError('SDK_PATCH', 'Arquivo repetido no diff do SDK.')
            sections[current] = [source_header, line]
            source_header = None
        elif current is not None and not line.startswith('index '):
            if line.startswith('@@ '):
                line = line[:line.index('@@', 3) + 2]
            sections[current].append(line)
    return sections


def build_spatial_sdk(root, work, tools, cancel, emit, allow_download=False, jobs=2, resume_base=None):
    from .native_build import file_hash, host_platform
    from .native_cache import apply_patch_exact
    root = Path(root)
    target = host_platform()
    recipe = spatial_sdk_recipe(root, target)
    key = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()[:20]
    builds = work.path('tools/spatial-sdk')
    base = builds / key
    # A successfully resumed old CMake tree remains at its absolute location.
    # Reuse it later only when its new semantic recipe and all hashes verify.
    if builds.is_dir():
        for candidate in sorted(builds.iterdir()):
            if not candidate.is_dir() or not candidate.resolve().is_relative_to(builds.resolve()):
                continue
            if verify_product(candidate / 'install', recipe):
                return candidate / 'install'
            request = candidate / 'aster-build-request.json'
            try:
                if json.loads(request.read_text(encoding='utf8')) == recipe:
                    base = candidate
            except (OSError, ValueError):
                pass
    build_origin = base
    if resume_base is not None:
        build_origin = Path(resume_base).resolve()
        if not build_origin.is_relative_to(builds.resolve()) or not (build_origin / 'source/.git').is_dir():
            raise PortError('SDK_RESUME', 'Retomada exige uma árvore isolada existente dentro do cache espacial.')
        # Preserve an already verified install; reuse only its source/build tree
        # and let Ninja rebuild changed objects into a new recipe's prefix.
        if not (build_origin / 'install/aster-spatial-sdk.json').is_file():
            base = build_origin
    prefix, build = base / 'install', build_origin / 'build'
    source_key = hashlib.sha256(json.dumps({'revision': SDK_REVISION, 'patches': recipe['patches'],
                                           'platform': target}, sort_keys=True).encode()).hexdigest()[:20]
    shared = work.path('tools/spatial-sdk-sources/' + source_key)
    source = build_origin / 'source' if (build_origin / 'source/.git').is_dir() else shared / 'source'
    pointer = shared / 'source-location.json'
    if not (source / '.git').is_dir() and pointer.is_file():
        try:
            previous_source = Path(json.loads(pointer.read_text(encoding='utf8'))['source']).resolve()
            if previous_source.is_relative_to(work.root) and (previous_source / '.git').is_dir():
                source = previous_source
        except (OSError, ValueError, KeyError, TypeError):
            pass
    if verify_product(prefix, recipe):
        return prefix
    if (prefix / 'aster-spatial-sdk.json').exists():
        raise PortError('SDK_CHANGED', 'O SDK espacial verificado foi alterado; artefatos preservados em ' + str(prefix))
    cmake, ninja, compiler, env = tools
    git = shutil.which('git', path=env.get('PATH'))
    if not git:
        raise PortError('BUILD_TOOLS', 'O runtime espacial requer Git, além de Clang/CMake e Windows SDK no Windows.')
    if not allow_download and not (source / '.git').is_dir():
        raise PortError('SDK_MISSING', 'Habilite baixar SDK para compilar o runtime espacial público fixado.')
    base.mkdir(parents=True, exist_ok=True)
    shared.mkdir(parents=True, exist_ok=True)
    logs = base / 'logs'
    logs.mkdir(exist_ok=True)
    def run(name, command, timeout=14400):
        cancel.check()
        emit({'stage': 'tools', 'task': name, 'state': 'running', 'message': name})
        # All paths/arguments are passed directly, with no shell or credential access.
        def progress(line):
            event = {'stage': 'tools', 'state': 'running', 'message': line[:180]}
            match = re.search(r'\[(\d+)/(\d+)\]', line)
            if match:
                event.update(completed=int(match[1]), total=int(match[2]), unit='targets')
            emit(event)
        try:
            result = run_process(list(map(str, command)), root, cancel, env=env, timeout=timeout,
                                 on_output=progress)
        except PortError as exc:
            (logs / (name.replace(' ', '-') + '-failure.json')).write_text(json.dumps(exc.as_dict(), indent=2), encoding='utf8')
            raise
        (logs / (name.replace(' ', '-') + '.log')).write_text(result['stdout'] + result['stderr'], encoding='utf8')
        emit({'stage': 'tools', 'task': name, 'state': 'completed'})
        return result['stdout'].strip()
    if not (source / '.git').is_dir():
        run('Clonar SDK espacial', [git, 'clone', '--filter=blob:none', '--no-checkout', SDK_REPOSITORY, source])
        run('Fixar revisão SDK', [git, '-C', source, 'checkout', '--detach', SDK_REVISION])
    if run('Conferir revisão SDK', [git, '-C', source, 'rev-parse', 'HEAD']) != SDK_REVISION:
        raise PortError('SDK_HASH', 'A revisão do SDK espacial não corresponde à versão fixada.')
    # Only the selected platform's dependencies: avoid downloading MoltenVK,
    # tests and the entire unused Vulkan stack on Windows.
    dependencies = ['cli11', 'libmspack', 'FFmpeg', 'tomlplusplus', 'simde',
                    'xxHash', 'spdlog', 'fmt', 'utfcpp', 'imgui', 'sdl3',
                    'tracy', 'o1heap', 'inja']
    if target == 'linux-amd64':
        dependencies.extend(['vulkan-headers', 'vulkan-memory-allocator',
                             'spirv-headers', 'spirv-tools', 'glslang'])
    paths = ['thirdparty/' + name for name in dependencies]
    if allow_download:
        run('Obter dependências fixadas', [git, '-C', source, '-c', 'submodule.fetchJobs=4',
                                          'submodule', 'update', '--init', '--recursive', '--', *paths])
    status = run('Conferir dependências SDK', [git, '-C', source, 'submodule', 'status', '--recursive', '--', *paths])
    # git prefixes an initialized, exact gitlink with a blank; str.strip above
    # removes it from the first line only, so inspect the remaining indicators.
    if not status or any(line.startswith(('-', '+', 'U')) for line in status.splitlines()):
        raise PortError('SDK_MISSING', 'Dependências ausentes ou fora das revisões fixadas no SDK.')
    marker = (build_origin / 'patched.json') if source == build_origin / 'source' else shared / 'patched.json'
    if not marker.exists():
        changed = []
        for patch in PATCHES:
            changed.extend(apply_patch_exact(source, (root / patch).read_text(encoding='utf8')))
        marker.write_text(json.dumps({path.relative_to(source).as_posix(): file_hash(path) for path in changed}), encoding='utf8')
    for relative, expected in json.loads(marker.read_text(encoding='utf8')).items():
        if file_hash(source / relative) != expected:
            raise PortError('SDK_CHANGED', 'O patch espacial foi alterado; fontes preservadas para diagnóstico.')
    # Reject extra source edits or a stale patch marker before adopting a
    # previous build directory. CMake/Ninja must then recompile every object
    # affected by the actual flag changes; no artifact identity is rewritten.
    expected_paths = {name for patch in PATCHES for name in normalized_patch((root / patch).read_text(encoding='utf8'))}
    actual_paths = set(run('Conferir alterações SDK', [git, '-C', source, 'diff', '--name-only', '--no-ext-diff']).splitlines())
    actual_paths.update(run('Conferir arquivos novos SDK', [git, '-C', source, 'ls-files', '--others', '--exclude-standard']).splitlines())
    if actual_paths != expected_paths:
        raise PortError('SDK_CHANGED', 'O SDK contém alterações fora do conjunto exato de patches públicos.')
    # Reconstruct expected final files from the immutable Git revision. Diff
    # context can slide around adjacent blank lines, so compare resulting bytes
    # instead of accepting a marker or relying on textual diff equivalence.
    tracked_paths = set(run('Conferir arquivos originais SDK', [git, '-C', source, 'ls-tree', '-r', '--name-only', SDK_REVISION, '--', *sorted(expected_paths)]).splitlines())
    with tempfile.TemporaryDirectory(prefix='verify-source-', dir=base) as temporary:
        temporary = Path(temporary)
        archive = temporary / 'original.tar'
        run('Conferir fontes originais SDK', [git, '-C', source, 'archive', '--format=tar',
                                             '--output=' + str(archive), SDK_REVISION, '--', *sorted(tracked_paths)])
        with tarfile.open(archive) as original:
            for relative in tracked_paths:
                path = temporary / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                with original.extractfile(relative) as content:
                    path.write_bytes(content.read())
        for patch in PATCHES:
            apply_patch_exact(temporary, (root / patch).read_text(encoding='utf8'))
        if any(file_hash(temporary / relative) != file_hash(source / relative) for relative in expected_paths):
            raise PortError('SDK_CHANGED', 'As fontes finais não correspondem exatamente aos patches aplicados à revisão fixada.')
    pointer.write_text(json.dumps({'source': str(source.resolve())}), encoding='utf8')
    (base / 'aster-build-request.json').write_text(json.dumps(recipe, sort_keys=True), encoding='utf8')
    flags = [f'-DCMAKE_CXX_COMPILER={compiler}', f'-DCMAKE_MAKE_PROGRAM={ninja}',
             f'-DCMAKE_C_FLAGS={BASELINE_FLAGS}', f'-DCMAKE_CXX_FLAGS={BASELINE_FLAGS}',
             '-DCMAKE_CONFIGURATION_TYPES=Release;RelWithDebInfo', f'-DCMAKE_INSTALL_PREFIX={prefix}',
             '-DASTER_ENABLE_SPATIAL_FILTERS=ON', '-DASTER_SKIP_USER_PACKAGE_REGISTRY=ON', '-DREXGLUE_ENABLE_FIDELITYFX=OFF',
             '-DREXGLUE_BUILD_TESTS=OFF', '-DREXGLUE_USE_D3D12=' + ('ON' if os.name == 'nt' else 'OFF'),
             '-DREXGLUE_USE_VULKAN=' + ('OFF' if os.name == 'nt' else 'ON')]
    from .native_build import companion_c_compiler
    cc = companion_c_compiler(compiler)
    flags.append(f'-DCMAKE_C_COMPILER={cc}')
    run('Configurar SDK espacial', [cmake, '-S', source, '-B', build, '-G', 'Ninja Multi-Config', *flags])
    # The SDK installs its generator only in Release, while native game hosts
    # use RelWithDebInfo and matching debug-postfixed runtime/GPU DLLs. Build
    # and install both, rather than silently mixing those configurations.
    for config in ('Release', 'RelWithDebInfo'):
        run('Compilar SDK espacial ' + config, [cmake, '--build', build, '--config', config,
                                              '--parallel', str(max(1, min(int(jobs), 16)))])
        run('Instalar SDK espacial ' + config, [cmake, '--install', build, '--config', config])
    files = {path.relative_to(prefix).as_posix(): file_hash(path) for path in prefix.rglob('*') if path.is_file()}
    manifest = {'recipe': recipe, 'capability': CAPABILITY, 'files': files,
                'submodules': status, 'validation': 'compiled-not-gameplay-validated'}
    (prefix / 'aster-spatial-sdk.json').write_text(json.dumps(manifest, indent=2), encoding='utf8')
    if not verify_product(prefix, recipe):
        raise PortError('SDK_BUILD', 'O SDK espacial não gerou todos os artefatos esperados.')
    return prefix
