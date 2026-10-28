"""Prepare reviewed originals from an owned dump before gameplay, on both OSes.

The shipped profile contains hashes/layouts only. Coverage is explicit and
bounded; materials outside the reviewed list retain their original appearance.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import tempfile

from .errors import PortError
from .tasks import Cancellation, run_process
from .texture_enhance import sha
from .texture_pack import SOURCE_XEX_SHA256, _relative, prepare_texture_pack

PROFILE = 'games/green_lantern_textures.json'
_HEX = re.compile('[0-9a-f]{64}\\Z')


def load_source_profile(root):
    path = Path(root) / PROFILE
    if path.is_symlink() or path.stat().st_size > 16 * 1024**2:
        raise PortError('HD_PROFILE', 'Perfil de texturas inválido.')
    data = json.loads(path.read_text(encoding='utf8'))
    if data.get('schema') != 1 or data.get('source_xex_sha256') != SOURCE_XEX_SHA256:
        raise PortError('HD_PROFILE', 'Perfil não corresponde à revisão suportada.')
    if 'runtime_library' in data and type(data['runtime_library']) is not bool:
        raise PortError('HD_PROFILE', 'Seletor de biblioteca deve ser booleano.')
    entries = data.get('entries')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 16384:
        raise PortError('HD_PROFILE', 'Quantidade de materiais inválida.')
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise PortError('HD_PROFILE', 'Entrada de material inválida.')
        for key in ('compressed_sha256', 'decoded_sha256', 'raw_sha256', 'canonical_rgba8_sha256', 'original_dds_sha256'):
            if not isinstance(entry.get(key), str) or not _HEX.fullmatch(entry[key]):
                raise PortError('HD_PROFILE', 'Hash de origem inválido.')
        if entry.get('classification') != 'color-opaque' or entry.get('reviewed') is not True:
            raise PortError('HD_PROFILE', 'Material sem revisão de cor opaca.')
        for key in ('compressed_size', 'decoded_size', 'raw_offset', 'raw_size'):
            if type(entry.get(key)) is not int or entry[key] < 0:
                raise PortError('HD_PROFILE', 'Limite de origem inválido.')
        if (not 0 < entry['compressed_size'] <= 512 * 1024**2 or
                not 0 < entry['decoded_size'] <= 1024**3 or
                not 0 < entry['raw_size'] <= 16 * 1024**2 or
                entry['raw_offset'] + entry['raw_size'] > entry['decoded_size']):
            raise PortError('HD_PROFILE', 'Material fora dos limites do contêiner.')
        meta = entry.get('capture_metadata')
        if (not isinstance(meta, dict) or meta.get('schema') != 1 or
                meta.get('purpose') != 'inspection-only' or meta.get('gpu_written_pages') is not False or
                type(meta.get('tiled')) is not bool or
                any(type(meta.get(k)) is not int for k in ('width', 'height', 'format', 'endian', 'base_size', 'base_row_pitch_bytes', 'mip_max_level', 'packed_level'))):
            raise PortError('HD_PROFILE', 'Layout de material inválido.')
        if (meta['format'] not in (18, 20) or meta['endian'] not in range(4) or
                meta['base_size'] != entry['raw_size'] or meta['mip_max_level'] < 1 or meta['packed_level'] < 1 or
                any(n < 64 or n > 2048 or n & (n - 1) for n in (meta['width'], meta['height'])) or
                not 0 < meta['base_row_pitch_bytes'] <= 1024**2):
            raise PortError('HD_PROFILE', 'Dimensões/layout de material fora dos limites.')
        _relative(Path(root), entry.get('source_relative'))
        if entry['canonical_rgba8_sha256'] in seen:
            raise PortError('HD_PROFILE', 'Material repetido.')
        seen.add(entry['canonical_rgba8_sha256'])
    return data, sha(path)


def _check_file(path, size, digest, cancel):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != size or sha(path, cancel) != digest:
        raise PortError('HD_SOURCE_CHANGED', 'Origem ausente ou diferente da revisão revisada: ' + str(path))


def _original_matches(folder, entry, cancel):
    from .texture_enhance import load_reviewed_source
    if not folder.exists():
        return False
    if folder.is_symlink():
        raise PortError('HD_CACHE_CHANGED', 'Cache de originais contém link.')
    cancel.check()
    try:
        _, _, data, _, _ = load_reviewed_source(folder / 'inspection.json', True, cancel=cancel)
        valid = (data['canonical_rgba8_sha256'] == entry['canonical_rgba8_sha256'] and
                 data['dds_sha256'] == entry['original_dds_sha256'] and
                 data.get('game_xex_sha256') == SOURCE_XEX_SHA256)
    except (OSError, ValueError, PortError) as exc:
        if isinstance(exc, PortError) and exc.code == 'CANCELLED':
            raise
        raise PortError('HD_CACHE_CHANGED', 'Originais em cache alterados; preservados: ' + str(folder)) from exc
    if not valid:
        raise PortError('HD_CACHE_CHANGED', 'Identidade do cache de originais divergente.')
    return True


def _extract_original(decoded, entry, destination, helper, root, cancel):
    from PIL import Image
    meta = entry['capture_metadata']
    stage = Path(tempfile.mkdtemp(prefix='.original-', dir=destination.parent))
    try:
        with decoded.open('rb') as source:
            source.seek(entry['raw_offset']); raw = source.read(entry['raw_size'])
        if len(raw) != entry['raw_size'] or hashlib.sha256(raw).hexdigest() != entry['raw_sha256']:
            raise PortError('HD_SOURCE_CHANGED', 'Blocos originais divergentes do perfil.')
        if (meta.get('schema') != 1 or meta.get('gpu_written_pages') is not False or
                meta.get('format') not in (18, 20) or meta.get('endian') not in range(4) or
                meta.get('base_size') != len(raw) or type(meta.get('tiled')) is not bool):
            raise PortError('HD_PROFILE', 'Layout original inválido.')
        raw_path = stage / 'original.base.bin'; raw_path.write_bytes(raw)
        dds = stage / 'original.dds'
        run_process([str(helper), str(raw_path), str(meta['width']), str(meta['height']),
                     str(meta['base_row_pitch_bytes']), str(meta['format']), str(meta['endian']),
                     str(int(meta['tiled'])), str(dds)], root, cancel)
        if sha(dds, cancel) != entry['original_dds_sha256']:
            raise PortError('HD_SOURCE_CHANGED', 'Conversão dos blocos divergiu do DDS revisado.')
        with Image.open(dds) as image:
            rgba = image.convert('RGBA')
            canonical = hashlib.sha256(b'aster-texture-rgba8-v1\0' + struct.pack('<II', *rgba.size) + rgba.tobytes()).hexdigest()
            if canonical != entry['canonical_rgba8_sha256'] or rgba.getchannel('A').getextrema() != (255, 255):
                raise PortError('HD_SOURCE_CHANGED', 'Pixels originais divergentes ou transparência não revisada.')
            rgba.save(stage / 'original.png')
        record = {'schema': 1, 'status': 'original-inspection-only', 'runtime_replacement': False,
                  'canonical_rgba8_sha256': canonical, 'dds_sha256': entry['original_dds_sha256'],
                  'game_xex_sha256': SOURCE_XEX_SHA256, 'capture_metadata': meta,
                  'raw_sha256': entry['raw_sha256'], 'classification': 'color-opaque',
                  'provenance': {'source': entry['source_relative'], 'compressed_sha256': entry['compressed_sha256'],
                                 'decoded_sha256': entry['decoded_sha256'], 'offset': entry['raw_offset']}}
        (stage / 'inspection.json').write_text(json.dumps(record, indent=2), encoding='utf8')
        cancel.check()
        try:
            os.rename(stage, destination)
        except FileExistsError:
            _original_matches(destination, entry, cancel)
    finally:
        if stage.exists(): shutil.rmtree(stage)


def ensure_graphics_textures(source, graphics_data, root, work, *, cancel=None, emit=None, allow_download=False,
                             full_validation=False):
    cancel = cancel or Cancellation(); emit = emit or (lambda event: None)
    quality = graphics_data.get('texture_quality', 'default')
    if quality not in ('low', 'default', 'high', 'ultra'):
        raise PortError('GRAPHICS_VALUE', 'Qualidade de texturas inválida.')
    cancel.check()
    if quality in ('low', 'default'):
        return {'pack': None, 'material_count': 0, 'state': 'original', 'host_scale': 1}
    from .sources import source_path
    from .texture_tools import ensure_texture_tools
    from .texture_validation import ValidationReceipt, safe_path
    from .xctd import decode_container
    root = Path(root).resolve()
    profile, profile_hash = load_source_profile(root)
    candidate = Path(source).expanduser()
    safe_path(candidate)
    if candidate.is_dir():
        matches = [path for path in candidate.iterdir() if path.name.lower() == 'default.xex']
        if len(matches) != 1:
            raise PortError('HD_XEX', 'Selecione uma pasta com um único default.xex.')
        candidate = matches[0]
    safe_path(candidate)
    xex = source_path(candidate)
    dump = xex.parent
    entries = profile['entries']
    scale = 4 if quality == 'ultra' else 2
    safe_path(work.root / ('textures/originals/' + profile_hash), allow_missing=True)
    home = work.path('textures/originals/' + profile_hash)
    producer_kind = 'libraries' if profile.get('runtime_library') is True else 'packs'
    safe_path(work.root / ('textures/' + producer_kind), allow_missing=True)
    output_home = work.path('textures/' + producer_kind)
    safe_path(work.root / 'cache/texture-validation', allow_missing=True)
    receipt = ValidationReceipt(work.path('cache/texture-validation'),
        {'purpose': 'graphics-textures-v1', 'profile_sha256': profile_hash, 'source': str(xex),
         'source_xex_sha256': SOURCE_XEX_SHA256, 'host_scale': scale,
         'originals': str(home), 'output_home': str(output_home)}, cancel)

    def dependencies(pack):
        return [root / PROFILE, xex, home, pack,
                *{_relative(dump, e['source_relative']) for e in entries}]

    cached = None if full_validation else receipt.read()
    if cached:
        result = cached.get('result')
        if isinstance(result, dict) and isinstance(result.get('pack'), str):
            pack = Path(result['pack'])
            expected = {'pack': str(pack), 'material_count': len(entries), 'state': 'prepared',
                        'host_scale': scale, 'coverage': profile.get('coverage', 'reviewed-materials-only')}
            if (pack.parent == output_home and _HEX.fullmatch(pack.name) and result == expected and
                    receipt.matches(cached, dependencies(pack))):
                emit({'stage': 'hd-batch', 'message': 'Texturas HD verificadas anteriormente; arquivos inalterados.',
                      'completed': len(entries), 'total': len(entries), 'unit': 'materials', 'state': 'completed'})
                return result
    if sha(xex, cancel) != SOURCE_XEX_SHA256:
        raise PortError('HD_XEX', 'Texturas HD ainda não revisadas para este XEX.')
    tools = None; decoded_files = {}; checked_sources = set()
    home.mkdir(parents=True, exist_ok=True)
    for index, entry in enumerate(entries):
        cancel.check()
        emit({'stage': 'hd-batch', 'message': f'Verificando originais {index + 1}/{len(entries)}',
              'completed': index, 'total': len(entries), 'unit': 'materials'})
        source_file = _relative(dump, entry['source_relative'])
        if entry['compressed_sha256'] not in checked_sources:
            _check_file(source_file, entry['compressed_size'], entry['compressed_sha256'], cancel)
            checked_sources.add(entry['compressed_sha256'])
        target = home / entry['canonical_rgba8_sha256']
        if _original_matches(target, entry, cancel):
            continue
        if tools is None:
            tools = ensure_texture_tools(root, work, cancel=cancel, emit=emit, allow_download=allow_download)
        decoded = work.path('textures/decoded/' + entry['decoded_sha256'] + '.bin')
        if entry['decoded_sha256'] not in decoded_files:
            if decoded.exists():
                _check_file(decoded, entry['decoded_size'], entry['decoded_sha256'], cancel)
            else:
                decoded.parent.mkdir(parents=True, exist_ok=True)
                decode_container(source_file, decoded, tools['decoder'], cancel=cancel, emit=emit,
                                 expected_source_sha256=entry['compressed_sha256'], expected_output_sha256=entry['decoded_sha256'])
            decoded_files[entry['decoded_sha256']] = decoded
        _extract_original(decoded, entry, target, tools['untile'], root, cancel)
    catalog = {'schema': 1, 'source_xex_sha256': SOURCE_XEX_SHA256, 'entries': [
        {'inspection': e['canonical_rgba8_sha256'] + '/inspection.json', 'classification': 'color-opaque',
         'reviewed': True, 'canonical_rgba8_sha256': e['canonical_rgba8_sha256'], 'dds_sha256': e['original_dds_sha256']}
        for e in entries]}
    catalog_path = home / 'catalog.json'
    if catalog_path.exists():
        if catalog_path.is_symlink() or json.loads(catalog_path.read_text(encoding='utf8')) != catalog:
            raise PortError('HD_CACHE_CHANGED', 'Catálogo automático alterado; preservado.')
    else:
        # Workspace publication uses exclusive temporaries and atomic replacement.
        work.write_json(catalog_path.relative_to(work.root), catalog)
    producer = prepare_texture_pack
    if profile.get('runtime_library') is True:
        from .texture_library import prepare_texture_library
        producer = prepare_texture_library
    pack = producer(catalog_path, root, work, host_scale=scale,
                                cancel=cancel, emit=emit, allow_download=allow_download)
    result = {'pack': str(pack), 'material_count': len(entries), 'state': 'prepared', 'host_scale': scale,
              'coverage': profile.get('coverage', 'reviewed-materials-only')}
    # New outputs did not exist before preparation. Validate the completed tree
    # once between stable inventories before it can authorize later fast starts.
    # This is intentionally more work on the first run, with no AI on validation.
    def verify_complete():
        from .texture_pack import validate_texture_pack_cached
        if load_source_profile(root)[1] != profile_hash or sha(xex, cancel) != SOURCE_XEX_SHA256:
            raise PortError('HD_SOURCE_CHANGED', 'A identidade das texturas mudou durante a preparação.')
        checked = set()
        for entry in entries:
            cancel.check()
            source_file = _relative(dump, entry['source_relative'])
            if source_file not in checked:
                _check_file(source_file, entry['compressed_size'], entry['compressed_sha256'], cancel)
                checked.add(source_file)
            if not _original_matches(home / entry['canonical_rgba8_sha256'], entry, cancel):
                raise PortError('HD_CACHE_CHANGED', 'Originais HD ausentes após a preparação.')
        validate_texture_pack_cached(pack, work.path('cache/texture-validation'),
                                    expected_xex_sha256=SOURCE_XEX_SHA256, cancel=cancel, full=True)

    if Path(pack).is_dir():
        receipt.publish(result, dependencies(pack), verify_complete)
    return result
