"""Build bounded texture helpers against the same verified SDK as the port.

Helpers and their dependencies live in a content-addressed workspace cache.
Neither the dump nor the SDK's source/install trees are modified here.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil

from .errors import PortError
from .tasks import Cancellation, run_process
from .workspace import Workspace

HELPERS = {'decoder': 'aster_xctd_decode', 'untile': 'aster_untile_capture'}
SOURCES = ('CMakeLists.txt', 'xctd_decode.c', 'untile_capture.cpp')
MSPACK_REVISION = '305907723a4e7ab2018e58040059ffb5e77db837'


def _digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def _source_directory(prefix, work, recipe):
    """Accept only a source tree recorded within this workspace cache."""
    source_key = hashlib.sha256(json.dumps({key: recipe[key] for key in
                                           ('revision', 'patches', 'platform')}, sort_keys=True).encode()).hexdigest()[:20]
    pointer = work.path('tools/spatial-sdk-sources/' + source_key + '/source-location.json')
    candidates = [Path(prefix).parent / 'source']
    if pointer.is_file():
        try:
            if pointer.stat().st_size > 16384:
                raise ValueError('source pointer too large')
            candidates.append(Path(json.loads(pointer.read_text(encoding='utf8'))['source']))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise PortError('TEXTURE_TOOLS_SOURCE', 'Referência de fonte do SDK inválida; cache preservado.') from exc
    tools_root = work.path('tools')
    for candidate in candidates:
        source = candidate.resolve()
        if not source.is_relative_to(tools_root):
            raise PortError('TEXTURE_TOOLS_SOURCE', 'Fonte do SDK fora do cache de ferramentas; cache preservado.')
        headers = source / 'thirdparty/libmspack/libmspack/mspack'
        if (source / '.git').is_dir() and headers.is_dir():
            for name in ('mspack.h', 'lzx.h'):
                path = headers / name
                if not path.is_file() or not path.resolve().is_relative_to(source):
                    raise PortError('TEXTURE_TOOLS_SOURCE', 'Headers libmspack inválidos no cache do SDK.')
            return source
    raise PortError('TEXTURE_TOOLS_SOURCE', 'Fonte fixada de libmspack não encontrada; gere o SDK espacial neste workspace.')


def _validate_pinned_headers(source, recipe, cancel, env):
    """Headers expose libmspack internals, so require its exact SDK gitlink."""
    git = shutil.which('git', path=env.get('PATH'))
    if not git:
        raise PortError('BUILD_TOOLS', 'Git é necessário para validar os headers fixados de libmspack.')
    def read(directory, *args):
        return run_process([git, '-C', str(directory), *args], directory, cancel, env=env)['stdout'].strip()
    if read(source, 'rev-parse', 'HEAD') != recipe['revision']:
        raise PortError('TEXTURE_TOOLS_SOURCE', 'A fonte do SDK não corresponde à revisão fixada.')
    tree = read(source, 'ls-tree', 'HEAD', 'thirdparty/libmspack')
    if tree != f'160000 commit {MSPACK_REVISION}\tthirdparty/libmspack':
        raise PortError('TEXTURE_TOOLS_SOURCE', 'Gitlink libmspack incompatível com o SDK fixado.')
    mspack = source / 'thirdparty/libmspack'
    if read(mspack, 'rev-parse', 'HEAD') != MSPACK_REVISION:
        raise PortError('TEXTURE_TOOLS_SOURCE', 'Revisão de libmspack alterada; cache preservado.')
    headers = mspack / 'libmspack/mspack'
    hashes = {}
    for name in ('mspack.h', 'lzx.h'):
        relative = 'libmspack/mspack/' + name
        # git's own object hash compares exact bytes (no text decoding or EOL conversion).
        if read(mspack, 'hash-object', str(headers / name)) != read(mspack, 'rev-parse', 'HEAD:' + relative):
            raise PortError('TEXTURE_TOOLS_SOURCE', 'Header libmspack alterado: ' + name + '. Cache preservado.')
        hashes[name] = _digest(headers / name)
    return headers, hashes


def _verified_files(base, recipe):
    manifest = base / 'texture-tools.json'
    if not manifest.is_file():
        return None
    try:
        if manifest.stat().st_size > 1024 * 1024:
            raise ValueError('manifest too large')
        data = json.loads(manifest.read_text(encoding='utf8'))
        if not isinstance(data, dict) or data.get('recipe') != recipe or not isinstance(data.get('files'), dict):
            raise ValueError('recipe changed')
        files = data['files']
        suffix = '.exe' if recipe['platform'] == 'win-amd64' else ''
        expected = {f'bin/{name}{suffix}' for name in HELPERS.values()}
        if not expected.issubset(files):
            raise ValueError('missing helpers')
        for relative, digest in files.items():
            raw = Path(relative)
            path = base / raw
            if raw.is_absolute() or '..' in raw.parts or not path.resolve().is_relative_to(base.resolve()):
                raise ValueError('unsafe output path')
            if not path.is_file() or path.is_symlink() or _digest(path) != digest:
                raise ValueError('helper changed')
        return {key: base / 'bin' / (name + suffix) for key, name in HELPERS.items()}
    except (OSError, ValueError, TypeError) as exc:
        raise PortError('TEXTURE_TOOLS_CHANGED', 'Ferramentas de texturas verificadas foram alteradas; cache preservado em ' + str(base)) from exc


def ensure_texture_tools(root, work, cancel=None, emit=None, allow_download=False):
    from .native_build import host_platform, toolchain
    from .spatial_sdk import build_spatial_sdk, spatial_sdk_recipe
    root = Path(root).resolve()
    if not isinstance(work, Workspace):
        work = Workspace(work, root)
    cancel = cancel or Cancellation()
    emit = emit or (lambda event: None)
    cancel.check()
    tools = toolchain(root, work)
    cmake, ninja, compiler, env = tools
    prefix = build_spatial_sdk(root, work, tools, cancel, emit, allow_download=allow_download, jobs=2)
    target = host_platform()
    sdk_recipe = spatial_sdk_recipe(root, target)
    source = _source_directory(prefix, work, sdk_recipe)
    headers, header_hashes = _validate_pinned_headers(source, sdk_recipe, cancel, env)
    if target == 'win-amd64':
        c_compiler = compiler  # clang-cl recognizes .c as C; requires native VS environment.
    else:
        from .native_build import companion_c_compiler
        sibling = Path(companion_c_compiler(compiler))
        c_compiler = str(sibling) if sibling.is_file() else shutil.which('clang', path=env.get('PATH'))
        if not c_compiler:
            raise PortError('BUILD_TOOLS', 'Clang C é necessário para o descompressor de texturas.')
    helper_source = root / 'integrations/rexglue/texture-inspection'
    recipe = {'schema': 1, 'platform': target, 'configuration': 'Release',
              'sdk_manifest_sha256': _digest(prefix / 'aster-spatial-sdk.json'),
              'sources': {name: _digest(helper_source / name) for name in SOURCES},
              'headers': header_hashes, 'mspack_revision': MSPACK_REVISION,
              'compiler': str(Path(compiler).resolve()), 'c_compiler': str(Path(c_compiler).resolve()),
              'compiler_sha256': _digest(compiler), 'c_compiler_sha256': _digest(c_compiler)}
    key = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()[:20]
    base = work.path('tools/texture-tools/' + key)
    cached = _verified_files(base, recipe)
    if cached:
        emit({'stage': 'textures', 'message': 'Ferramentas de texturas verificadas · cache reutilizado'})
        return {**cached, 'sdk': prefix}
    base.mkdir(parents=True, exist_ok=True)
    for name in ('bin', 'build'):
        path = base / name
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise PortError('TEXTURE_TOOLS_BUILD', 'Diretório de compilação inesperado; cache preservado.')
    for name in HELPERS.values():
        path = base / 'bin' / (name + ('.exe' if target == 'win-amd64' else ''))
        if path.is_symlink():
            raise PortError('TEXTURE_TOOLS_BUILD', 'Saída de helper é um link; cache preservado.')
    build = base / 'build'
    commands = [
        ('Configurar ferramentas de texturas', [cmake, '-S', str(helper_source), '-B', str(build), '-G', 'Ninja',
            '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_CXX_STANDARD=23', '-DCMAKE_CXX_EXTENSIONS=OFF',
            '-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF', '-DCMAKE_FIND_PACKAGE_NO_PACKAGE_REGISTRY=ON',
            f'-DCMAKE_PREFIX_PATH={prefix}', f'-DCMAKE_CXX_COMPILER={compiler}',
            f'-DCMAKE_C_COMPILER={c_compiler}', f'-DCMAKE_MAKE_PROGRAM={ninja}',
            f'-DASTER_MSPACK_SOURCE={headers}', f'-DCMAKE_RUNTIME_OUTPUT_DIRECTORY={base / "bin"}',
            f'-DCMAKE_BUILD_RPATH={prefix / "lib"}']),
        ('Compilar ferramentas de texturas', [cmake, '--build', str(build), '--parallel', '2'])]
    for index, (name, command) in enumerate(commands):
        cancel.check()
        emit({'stage': 'textures', 'message': name, 'completed': index, 'total': len(commands)})
        result = run_process(command, root, cancel, env=env, timeout=600,
                             on_output=lambda line: emit({'stage': 'textures', 'message': line[:180]}))
        (base / f'build-{index}.log').write_text(result['stdout'] + result['stderr'], encoding='utf8')
    suffix = '.exe' if target == 'win-amd64' else ''
    outputs = {key: base / 'bin' / (name + suffix) for key, name in HELPERS.items()}
    if any(not path.is_file() or path.is_symlink() for path in outputs.values()):
        raise PortError('TEXTURE_TOOLS_BUILD', 'A compilação não produziu ambos os helpers esperados.')
    # Native Windows needs the verified SDK runtime beside the untile executable.
    if target == 'win-amd64':
        sdk_manifest = json.loads((prefix / 'aster-spatial-sdk.json').read_text(encoding='utf8'))
        for relative, digest in sdk_manifest['files'].items():
            path = Path(relative)
            if path.parent == Path('bin') and path.suffix.lower() == '.dll':
                original = prefix / path
                if _digest(original) != digest:
                    raise PortError('TEXTURE_TOOLS_BUILD', 'DLL do SDK alterada durante a preparação.')
                destination = base / 'bin' / path.name
                if destination.is_symlink():
                    raise PortError('TEXTURE_TOOLS_BUILD', 'Destino inesperado para DLL; cache preservado.')
                shutil.copyfile(original, destination)
    files = {str(path.relative_to(base)).replace('\\', '/'): _digest(path)
             for path in (base / 'bin').iterdir() if path.is_file()}
    work.write_json('tools/texture-tools/' + key + '/texture-tools.json', {'recipe': recipe, 'files': files})
    verified = _verified_files(base, recipe)
    emit({'stage': 'textures', 'message': 'Ferramentas de texturas preparadas', 'completed': 2, 'total': 2})
    return {**verified, 'sdk': prefix}
