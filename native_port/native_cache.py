"""Reproduce the Vulkan driver-cache plugin against the pinned public SDK."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import urllib.request

from .errors import PortError

SOURCES = (
    ('rexglue-source-f5337cdc.zip',
     'https://github.com/rexglue/rexglue-sdk/archive/f5337cdc947ff6d4c4196737e2c807a48f2a1fc2.zip',
     'e116dd1561f1e163600e6393d3c3df12ceaf089771b23b41d0e572056e9db394',
     'rexglue-sdk-f5337cdc947ff6d4c4196737e2c807a48f2a1fc2'),
    ('glslang-f4f1d8a3.zip',
     'https://github.com/KhronosGroup/glslang/archive/f4f1d8a352ca1908943aea2ad8c54b39b4879080.zip',
     'c149464d54d840ddceab33fc0ea0cf36b2e22a7634aa1166d56cfaed583e41ea',
     'glslang-f4f1d8a352ca1908943aea2ad8c54b39b4879080'),
)


def apply_patch_exact(root, patch_text):
    """Validate all exact hunks before writing; allow reviewed new text files."""
    root = Path(root).resolve()
    lines = patch_text.splitlines(keepends=True)
    pending = {}
    i = 0
    while i < len(lines):
        if not lines[i].startswith('--- '):
            i += 1
            continue
        old = lines[i][4:].strip()
        i += 1
        if i >= len(lines) or not lines[i].startswith('+++ b/'):
            raise PortError('CACHE_PATCH', 'Cabeçalho inválido no patch do SDK.')
        relative = lines[i][6:].strip()
        raw = Path(relative)
        if raw.is_absolute() or '..' in raw.parts or '\\' in relative or ':' in relative:
            raise PortError('CACHE_PATCH', 'Caminho inválido no patch do SDK.')
        path = root / raw
        if (not raw.parts or not path.resolve().is_relative_to(root) or
                any(p.is_symlink() for p in (path, *path.parents)) or path in pending):
            raise PortError('CACHE_PATCH', 'Caminho inválido ou repetido no patch do SDK.')
        new_file = old == '/dev/null'
        if (new_file and path.exists()) or (not new_file and (old != 'a/' + relative or not path.is_file())):
            raise PortError('CACHE_PATCH', 'Origem inválida no patch do SDK.')
        original = [] if new_file else path.read_text(encoding='utf8').splitlines(keepends=True)
        output, position, hunks = [], 0, 0
        i += 1
        while i < len(lines) and not lines[i].startswith(('diff --git ', '--- ')):
            match = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', lines[i])
            if not match:
                i += 1
                continue
            old_start, old_count, new_start, new_count = (int(match[1]), int(match[2] or 1), int(match[3]), int(match[4] or 1))
            start = old_start - 1 if old_count else old_start
            if start < position or start > len(original) or (new_file and (old_start or old_count)):
                raise PortError('CACHE_PATCH', 'Offset inválido no patch do SDK.')
            output.extend(original[position:start])
            position = start
            if new_start != len(output) + 1:
                raise PortError('CACHE_PATCH', 'Offset de destino inválido no patch do SDK.')
            consumed = produced = 0
            i += 1
            while i < len(lines) and lines[i][:1] in (' ', '+', '-'):
                kind, text = lines[i][0], lines[i][1:]
                if kind in (' ', '-'):
                    if position >= len(original) or original[position] != text:
                        raise PortError('CACHE_PATCH', 'O contexto do patch não corresponde ao SDK fixado.')
                    position += 1; consumed += 1
                if kind in (' ', '+'):
                    output.append(text); produced += 1
                i += 1
                if consumed == old_count and produced == new_count:
                    break
            if consumed != old_count or produced != new_count:
                raise PortError('CACHE_PATCH', 'Contagem inválida no hunk do SDK.')
            hunks += 1
        if not hunks:
            raise PortError('CACHE_PATCH', 'Arquivo sem hunks no patch do SDK.')
        output.extend(original[position:])
        pending[path] = ''.join(output)
    if not pending:
        raise PortError('CACHE_PATCH', 'Patch vazio ou não reconhecido.')
    # A later context failure cannot leave earlier files partially patched.
    for path, content in pending.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf8')
    return list(pending)


def build_cache_plugin(root, work, prefix, tools, cancel, emit, run, allow_download):
    from .native_build import file_hash, safe_extract, companion_c_compiler
    patches = [root / ('integrations/rexglue/patches/' + name) for name in (
        '0001-vulkan-driver-pipeline-cache.patch', '0003-vulkan-deferred-pipelines.patch',
        '0005-texture-inspection-capture.patch', '0006-reviewed-hd-texture-override.patch',
        '0008-hd-selection-cache.patch', '0009-multi-material-hd-pack.patch',
        '0010-gameplay-texture-capture-arm.patch', '0011-hd-texture-scales.patch', '0012-campaign-texture-library.patch', '0013-windows-hd-library-path.patch',
        '0015-scaled-resolve-diagnostics.patch', '0016-reviewed-ui-alpha-atlas.patch',
        '0017-scaled-texture-offset-flag-parity.patch', '0018-effects-sampling-diagnostics.patch',
        '0019-armed-effects-source-index.patch', '0020-effects-decision-diagnostics.patch',
        '0021-d3d12-blocking-shader-prewarm.patch',
        '0022-idle-notification-presentation.patch',
        '0023-guest-vblank-video-mode-clock.patch',
        '0024-scaled-pixel-parameter-centers.patch',
        '0025-linux-known-shader-preload-selection.patch',
        '0027-linux-worker-only-async-submissions.patch')]
    sdk_abi = prefix / 'aster-spatial-sdk.json'
    abi_identity = file_hash(sdk_abi) if sdk_abi.is_file() else 'official-sdk-0.10.0'
    recipe = hashlib.sha256((''.join(file_hash(patch) for patch in patches) + file_hash(root / 'integrations/rexglue/plugin-only/CMakeLists.txt') + abi_identity).encode()).hexdigest()[:20]
    cache_root = work.path('tools/cache-plugin/' + recipe)
    product = cache_root / 'build/isolated-runtime/librexgpu-xenosrd.so'
    identity = cache_root / 'product.json'
    if product.is_file() and identity.is_file():
        if json.loads(identity.read_text(encoding='utf8')).get('sha256') == file_hash(product):
            return product
    cache_root.mkdir(parents=True, exist_ok=True)
    extracted = []
    for filename, url, checksum, directory in SOURCES:
        archive = work.path('tools/downloads/' + filename)
        archive.parent.mkdir(parents=True, exist_ok=True)
        if not archive.is_file() or file_hash(archive) != checksum:
            if not allow_download:
                raise PortError('SDK_MISSING', 'As fontes públicas do cache estão ausentes; habilite baixar SDK.')
            emit({'task': 'Baixar fontes públicas do cache', 'state': 'running', 'message': url})
            fd, temporary = tempfile.mkstemp(dir=archive.parent)
            try:
                with os.fdopen(fd, 'wb') as output, urllib.request.urlopen(url, timeout=30) as response:
                    total = int(response.headers.get('Content-Length', 0))
                    while block := response.read(1024 * 1024):
                        cancel.check()
                        output.write(block)
                        emit({'stage': 'cache', 'state': 'running', 'message': 'Baixando fontes do cache gráfico',
                              'completed': output.tell(), 'total': total, 'unit': 'bytes'})
                        if output.tell() > 256 * 1024**2:
                            raise PortError('SDK_DOWNLOAD', 'Arquivo excedeu o tamanho previsto.')
                if file_hash(Path(temporary)) != checksum:
                    raise PortError('SDK_HASH', 'Hash inválido nas fontes públicas do SDK.')
                os.replace(temporary, archive)
            finally:
                Path(temporary).unlink(missing_ok=True)
        destination = cache_root / directory
        if not destination.is_dir():
            safe_extract(archive, cache_root)
        extracted.append(destination)
    source, glslang = extracted
    marker = cache_root / 'patched.json'
    if not marker.is_file():
        changed = []
        for patch in patches:
            changed.extend(apply_patch_exact(source, patch.read_text(encoding='utf8')))
        marker.write_text(json.dumps({str(p.relative_to(source)): file_hash(p) for p in changed}), encoding='utf8')
    for relative, expected in json.loads(marker.read_text(encoding='utf8')).items():
        if file_hash(source / relative) != expected:
            raise PortError('CACHE_CHANGED', 'As fontes verificadas do cache foram alteradas.')
    cmake, ninja, compiler, _ = tools
    run('Configurar cache persistente', [cmake, '-S', root / 'integrations/rexglue/plugin-only',
        '-B', cache_root / 'build', '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=RelWithDebInfo',
        f'-DCMAKE_C_COMPILER={companion_c_compiler(compiler)}',
        f'-DCMAKE_CXX_COMPILER={compiler}', f'-DCMAKE_MAKE_PROGRAM={ninja}',
        f'-DASTER_REX_SOURCE={source}', f'-DASTER_REX_PREFIX={prefix}',
        f'-DASTER_GLSLANG_SOURCE={glslang}', '-DASTER_PINNED_ARCHIVE_SOURCES=ON'])
    run('Compilar cache persistente', [cmake, '--build', cache_root / 'build', '--parallel', '2'])
    if not product.is_file():
        raise PortError('CACHE_BUILD', 'Plugin de cache não foi gerado.')
    identity.write_text(json.dumps({'sha256': file_hash(product)}), encoding='utf8')
    return product


def build_presenter_filter(root, work, prefix, tools, cancel, run):
    """Build the host presenter (original adapters plus MIT AMD EASU) for the pinned SDK."""
    from .native_build import file_hash
    source = root / 'integrations/rexglue/presenter-filter'
    recipe = hashlib.sha256(''.join(file_hash(p) for p in sorted(source.iterdir()) if p.is_file()).encode()).hexdigest()[:20]
    build = work.path('tools/presenter-filter/' + recipe + '/build')
    product = build / 'libaster_presenter_compat.so'
    identity = build.parent / 'product.json'
    if product.is_file() and identity.is_file():
        if json.loads(identity.read_text(encoding='utf8')).get('sha256') == file_hash(product):
            return product
    cmake, ninja, compiler, _ = tools
    cancel.check()
    run('Configurar cache persistente e filtro de saída', [cmake, '-S', source, '-B', build, '-G', 'Ninja',
        '-DCMAKE_BUILD_TYPE=RelWithDebInfo', f'-DCMAKE_PREFIX_PATH={prefix}',
        f'-DCMAKE_CXX_COMPILER={compiler}', f'-DCMAKE_MAKE_PROGRAM={ninja}'])
    run('Compilar cache persistente e filtro de saída', [cmake, '--build', build, '--parallel', '2'])
    if not product.is_file():
        raise PortError('CACHE_BUILD', 'O filtro de apresentação não foi gerado.')
    identity.write_text(json.dumps({'sha256': file_hash(product)}), encoding='utf8')
    return product


def build_arena_lifetime(root, work, tools, cancel, run):
    """Build just shm_open ownership cleanup; no SDK headers or ABI dependency."""
    from .native_build import file_hash
    source = root / 'integrations/rexglue/presenter-filter'
    inputs = [source / 'CMakeLists.txt', source / 'arena_lifetime.cpp']
    recipe = hashlib.sha256(''.join(file_hash(p) for p in inputs).encode()).hexdigest()[:20]
    build = work.path('tools/arena-lifetime/' + recipe + '/build')
    product = build / 'libaster_arena_lifetime.so'
    identity = build.parent / 'product.json'
    if product.is_file() and identity.is_file():
        if json.loads(identity.read_text(encoding='utf8')).get('sha256') == file_hash(product):
            return product
    cmake, ninja, compiler, _ = tools
    cancel.check()
    run('Configurar cache persistente de arenas', [cmake, '-S', source, '-B', build, '-G', 'Ninja',
        '-DCMAKE_BUILD_TYPE=Release', '-DASTER_ARENA_ONLY=ON',
        f'-DCMAKE_CXX_COMPILER={compiler}', f'-DCMAKE_MAKE_PROGRAM={ninja}'])
    run('Compilar cache persistente de arenas', [cmake, '--build', build, '--parallel', '2'])
    if not product.is_file():
        raise PortError('CACHE_BUILD', 'O módulo de liberação automática das arenas não foi gerado.')
    identity.write_text(json.dumps({'sha256': file_hash(product)}), encoding='utf8')
    return product
