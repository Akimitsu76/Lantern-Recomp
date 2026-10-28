"""Anticipate reviewed pipelines using only shaders from the user's dump.

The public profile contains hashes, locations, vertex layout operands and scalar
pipeline state. No guest program, translated shader or driver cache is shipped.
Both APIs keep learning other pipelines through their existing persistent cache.
Preparation holds the same play lock as the game and never replaces valid cache
records. Native cache formats are pinned and covered by a C++ layout contract.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile

from .errors import PortError
from .locking import lock_session
from .tasks import Cancellation

PROFILE = 'games/green_lantern_shader_prewarm.json'
SHADER_HEADER = b'XESH' + bytes.fromhex('20201219')
VK_HEADER = b'XEPS' + struct.pack('<I', 1) + bytes.fromhex('20260228')
DX_HEADER = b'XEPSDXRO' + bytes.fromhex('20260226')
MAX_SHADER_CACHE = 256 * 1024**2
MAX_PIPELINE_CACHE = 32 * 1024**2
# Only vertex-fetch layout operands, never opcodes, branches or ALU instructions.
FETCH_FIELDS = {
    'const_index': (0, 20, 5), 'const_index_sel': (0, 25, 2),
    'prefetch_count': (0, 27, 3), 'dst_swizzle': (1, 0, 12),
    'signed': (1, 12, 1), 'non_normalized': (1, 13, 1),
    'signed_rf_mode': (1, 14, 1), 'index_rounded': (1, 15, 1),
    'format': (1, 16, 6), 'exp_adjust': (1, 24, 6),
    'mini': (1, 30, 1), 'stride': (2, 0, 8), 'offset': (2, 8, 23),
}


def _error(message):
    return PortError('SHADER_PREPARE', message)


def _plain(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise _error('Links não são aceitos na preparação de shaders; arquivos preservados.')
    return path


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _read(path, limit):
    path = _plain(path)
    if not path.exists():
        return b''
    if not path.is_file() or path.stat().st_size > limit:
        raise _error('Arquivo de shaders inválido ou excessivo: ' + str(path))
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise _error('Arquivo de shaders excedeu o limite durante a leitura.')
    return data


def load_profile(root):
    from .spatial_sdk import SDK_REVISION
    from .native_build import XEX_SHA256
    data = json.loads(_read(Path(root) / PROFILE, 256 * 1024))
    if (data.get('schema') != 1 or data.get('sdk_revision') != SDK_REVISION or
            data.get('source_xex_sha256') != XEX_SHA256 or
            data.get('source_relative') != 'gl/x360/egraphics/shaders_xbox360.pak' or
            not 0 < len(data.get('shaders', [])) <= 1024 or
            not 0 < len(data.get('pipelines', [])) <= 4096):
        raise _error('Perfil de preparação incompatível com esta revisão do port.')
    return data


def reconstruct_shaders(bank, profile):
    import xxhash
    if len(bank) != profile['decoded_size'] or _sha(bank) != profile['decoded_sha256']:
        raise _error('O banco de shaders não corresponde ao dump revisado.')
    result = {}
    for item in profile['shaders']:
        start, size, stage = item['source_offset'], item['byte_count'], item['stage']
        if (type(start) is not int or start < 0 or type(size) is not int or
                size <= 0 or size % 12 or start + size > len(bank) or stage not in (0, 1)):
            raise _error('Limites de programa inválidos no perfil de shaders.')
        code = bytearray(bank[start:start + size])
        if _sha(code) != item['source_sha256']:
            raise _error('Programa original não confere; cache preservado.')
        seen = set()
        for edit in item['vertex_layout']:
            offset = edit['instruction_byte_offset']
            if stage != 0 or offset % 12 or not 0 <= offset <= size - 12 or offset in seen:
                raise _error('Edição de layout fora de uma instrução de vértice.')
            seen.add(offset)
            words = list(struct.unpack_from('>III', code, offset))
            if words[0] & 31 or not words[0] >> 19 & 1:
                raise _error('A instrução original não é vertex-fetch; cache preservado.')
            for name, value in edit['fields'].items():
                if name not in FETCH_FIELDS:
                    raise _error('O perfil tentou alterar um operando de shader não permitido.')
                word, bit, width = FETCH_FIELDS[name]
                if type(value) is not int or not 0 <= value < 1 << width:
                    raise _error('Valor de operando de vértice inválido.')
                mask = ((1 << width) - 1) << bit
                words[word] = (words[word] & ~mask) | (value << bit)
            struct.pack_into('>III', code, offset, *words)
        digest = xxhash.xxh3_64_intdigest(code)
        if f'{digest:016x}' != item['hash'] or digest in result:
            raise _error('O shader reconstruído não confere com a revisão conhecida.')
        result[digest] = struct.pack('<QI', digest, len(code) // 4 | stage << 31) + code
    return result


def pipeline_records(profile, renderer):
    """Serialize only the reviewed, non-tessellated FSI / ROV state subset.

    Windows MS bitfield allocation has separate 32-bit words. Linux Vulkan's
    packed raster/depth state occupies six bytes. Never exchange their blobs.
    ROV ForcedSampleCount differs from Vulkan FSI; prepare both supported 1x/4x
    variants rather than guessing the guest's dynamically selected MSAA value.
    """
    import xxhash
    if renderer not in ('vulkan-fsi', 'd3d12-rov'):
        raise _error('Backend sem perfil de preparação revisado.')
    records = {}
    for item in profile['pipelines']:
        if (item['topology'] not in ('triangle-list', 'triangle-strip') or
                item['geometry_shader'] != 'none' or item['cull_mode'] != 'none' or
                item['front_clockwise'] is not False or item['depth_clip'] is not True or
                item['msaa_samples'] != 1):
            raise _error('Estado de pipeline fora do subconjunto revisado.')
        vs, ps = int(item['vertex_shader'], 16), int(item['pixel_shader'], 16)
        mask, dynamic = item['interpolator_mask'], item['pixel_dynamic_register_count']
        enabled, index, point = (item['pixel_param_gen_enable'],
                                 item['pixel_param_gen_interpolator'], item['pixel_param_gen_point'])
        if (type(mask) is not int or not 0 <= mask <= 0xffff or
                type(dynamic) is not int or not 0 <= dynamic <= 255 or
                type(index) is not int or not 0 <= index <= 15 or
                type(enabled) is not bool or type(point) is not bool or
                {shader['hash']: shader['stage'] for shader in profile['shaders']}.get(item['vertex_shader']) != 0 or
                {shader['hash']: shader['stage'] for shader in profile['shaders']}.get(item['pixel_shader']) != 1):
            raise _error('Modificação de shader inválida no perfil.')
        if renderer == 'vulkan-fsi':
            modification = mask | dynamic << 32 | enabled << 40 | index << 41 | point << 45
            topology = 3 if item['topology'] == 'triangle-list' else 4
            descriptions = [struct.pack('<QQQQI', vs, mask, ps, modification, 0) +
                            (topology << 2).to_bytes(6, 'little') + bytes(16)]
        else:
            modification = mask | enabled << 32 | index << 33 | point << 37 | dynamic << 38
            prefix = struct.pack('<QQQQif', vs, mask, ps, modification, 0, 0.0)
            # Triangle topology type, CCW front faces, depth clipping; ROV has
            # no host RT blend/depth/stencil state. MSAA enum 0=1x, 2=4x.
            descriptions = [prefix + struct.pack('<II', 2 << 2 | 1 << 9 | 1 << 10 | samples << 11, 0)
                            + bytes(16) for samples in (0, 2)]
        for description in descriptions:
            digest = xxhash.xxh3_64_intdigest(description)
            records[digest] = struct.pack('<Q', digest) + description
    return records


def _merge_shaders(existing, additions):
    import xxhash
    if not existing:
        existing = SHADER_HEADER
    if existing[:8] != SHADER_HEADER:
        raise _error('Versão de cache de shaders desconhecida; arquivo preservado.')
    offset, present = 8, set()
    while offset < len(existing):
        if offset + 12 > len(existing):
            raise _error('Cache de shaders truncado; arquivo preservado.')
        digest, count = struct.unpack_from('<QI', existing, offset)
        end = offset + 12 + (count & 0x7fffffff) * 4
        if end > len(existing) or end == offset + 12 or xxhash.xxh3_64_intdigest(existing[offset + 12:end]) != digest:
            raise _error('Cache de shaders corrompido; arquivo preservado.')
        present.add(digest)
        offset = end
    return existing + b''.join(data for digest, data in additions.items() if digest not in present)


def _merge_pipelines(existing, additions, renderer):
    import xxhash
    header, size = (VK_HEADER, 66) if renderer == 'vulkan-fsi' else (DX_HEADER, 72)
    if not existing:
        existing = header
    if existing[:12] != header or (len(existing) - 12) % size:
        raise _error('Versão ou tamanho de cache de pipelines desconhecido; arquivo preservado.')
    present = set()
    for offset in range(12, len(existing), size):
        digest = struct.unpack_from('<Q', existing, offset)[0]
        if xxhash.xxh3_64_intdigest(existing[offset + 8:offset + size]) != digest:
            raise _error('Cache de pipelines corrompido; arquivo preservado.')
        present.add(digest)
    return existing + b''.join(data for digest, data in additions.items() if digest not in present)


def _publish(path, before, after):
    if after == before:
        return
    path = _plain(path)
    if _read(path, max(MAX_SHADER_CACHE, len(after))) != before:
        raise _error('Cache alterado por outra sessão; preparação cancelada.')
    if before:
        backup = _plain(path.with_name(path.name + '.before-prewarm-' + _sha(before)))
        if not backup.exists():
            with backup.open('xb') as stream:
                stream.write(before)
        elif _read(backup, MAX_SHADER_CACHE) != before:
            raise _error('Backup de shaders inesperado; cache preservado.')
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.prewarm-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(after)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        if _read(path, MAX_SHADER_CACHE) != before:
            raise _error('Cache alterado antes da publicação; preparação cancelada.')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def merge_cache(cache, shaders, pipelines, renderer):
    """Caller owns the play lock. Publish programs before any new references."""
    cache = _plain(cache)
    cache.mkdir(parents=True, exist_ok=True)
    shader_path = cache / '575207E9.xsh'
    pipeline_path = cache / ('575207E9.fsi.vk.xpso' if renderer == 'vulkan-fsi'
                             else '575207E9.rov.d3d12.xpso')
    old_shaders, old_pipelines = _read(shader_path, MAX_SHADER_CACHE), _read(pipeline_path, MAX_PIPELINE_CACHE)
    new_shaders = _merge_shaders(old_shaders, shaders)
    new_pipelines = _merge_pipelines(old_pipelines, pipelines, renderer)
    if len(new_shaders) > MAX_SHADER_CACHE or len(new_pipelines) > MAX_PIPELINE_CACHE:
        raise _error('Cache ampliado excederia o limite; arquivos preservados.')
    _publish(shader_path, old_shaders, new_shaders)
    _publish(pipeline_path, old_pipelines, new_pipelines)
    return {'shader_bytes_added': (len(new_shaders) - len(old_shaders or SHADER_HEADER)),
            'pipelines_added': (len(new_pipelines) - len(old_pipelines or new_pipelines[:12])) //
                               (66 if renderer == 'vulkan-fsi' else 72)}


def prepare_game_shaders(source, runtime, root, work, installation, *, cancel=None, emit=None):
    """Prepare the reviewed local cache; called before launching the executable."""
    from .native_build import file_hash
    from .texture_tools import ensure_texture_tools
    from .xctd import decode_container
    cancel, emit = cancel or Cancellation(), emit or (lambda event: None)
    profile = load_profile(root)
    if installation.get('recipe', {}).get('sdk_spatial', {}).get('revision') != profile['sdk_revision']:
        raise _error('O perfil de shaders exige o SDK da revisão instalada.')
    source = _plain(Path(source))
    if source.is_file():
        source = source.parent
    if file_hash(source / 'default.xex') != profile['source_xex_sha256']:
        raise _error('O XEX não corresponde ao perfil de preparação.')
    runtime = _plain(runtime)
    runtime.mkdir(parents=True, exist_ok=True)
    lock_path = _plain(runtime / 'play.lock')
    try:
        descriptor = lock_session(lock_path)
    except BlockingIOError as exc:
        raise _error('Feche a sessão do jogo antes de preparar shaders.') from exc
    try:
        cancel.check()
        emit({'stage': 'shader-prepare', 'message': 'Preparando shaders revisados a partir do seu dump',
              'completed': 0, 'total': 3})
        container = _plain(source / profile['source_relative'])
        if file_hash(container) != profile['source_sha256']:
            raise _error('O banco de shaders original não corresponde à revisão suportada.')
        decoded = _plain(work.path('shaders/decoded/' + profile['decoded_sha256'] + '.bin'))
        if not decoded.exists():
            tools = ensure_texture_tools(root, work, cancel=cancel, emit=emit, allow_download=False)
            decoded.parent.mkdir(parents=True, exist_ok=True)
            decode_container(container, decoded, tools['decoder'], cancel=cancel, emit=emit,
                             expected_source_sha256=profile['source_sha256'],
                             expected_output_sha256=profile['decoded_sha256'])
        bank = _read(decoded, profile['decoded_size'])
        shaders = reconstruct_shaders(bank, profile)
        pipelines = pipeline_records(profile, installation['renderer'])
        cancel.check()
        emit({'stage': 'shader-prepare', 'message': 'Preservando o cache e acrescentando os pipelines revisados',
              'completed': 2, 'total': 3})
        result = merge_cache(runtime / 'cache/shaders/shareable', shaders, pipelines, installation['renderer'])
        emit({'stage': 'shader-prepare', 'message': 'Shaders preparados; o backend compilará antes de entrar no jogo',
              'completed': 3, 'total': 3})
        return {**result, 'profile_sha256': file_hash(Path(root) / PROFILE),
                'coverage': profile['scope'], 'renderer': installation['renderer']}
    finally:
        os.close(descriptor)
