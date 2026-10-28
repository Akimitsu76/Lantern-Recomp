"""Bounded, reviewed HD material batches shared by Linux and Windows.

Catalogs never classify textures automatically. Only ``color-opaque`` entries
with ``reviewed: true`` are prepared; other materials remain counted exclusions.
Inspection paths are relative to the catalog tree. Preparation delegates immutable
per-texture caching to texture_enhance, then publishes a verified batch atomically.
No inference is performed by validation or during gameplay.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile

from .errors import PortError
from .tasks import Cancellation
from .texture_enhance import prepare_texture, sha, validate_prepared_pack

MAX_ENTRIES = 256
MAX_DDS_BYTES = 256 * 1024**2
MAX_FILE_BYTES = 256 * 1024**2
MAX_PACK_BYTES = 2 * 1024**3
SOURCE_XEX_SHA256 = '3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1'
_HEX64 = re.compile(r'[0-9a-f]{64}\Z')
_HEX32 = re.compile(r'[0-9a-f]{32}\Z')
CHILD_FILES = {'manifest.json', 'texture.index', 'texture.dds', 'enhanced-x2.png', 'enhanced-x4.png', 'inference.json'}


def _error(message):
    return PortError('HD_CATALOG', message)


def _json(path, maximum=1024 * 1024):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise _error('Arquivo HD ausente, excessivo ou com link: ' + str(path))
    return json.loads(path.read_text(encoding='utf8'))


def _relative(base, name):
    """Reject Windows and POSIX traversal and all symlink components."""
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise _error('Caminho relativo HD inválido.')
    pure = PurePosixPath(name)
    if pure.is_absolute() or any(p in ('', '.', '..') for p in name.split('/')):
        raise _error('Caminho HD fora do catálogo.')
    target = base
    for part in pure.parts:
        target = target / part
        if target.is_symlink():
            raise _error('Links não são aceitos em pacotes HD.')
    if not target.resolve().is_relative_to(base.resolve()):
        raise _error('Caminho HD fora do catálogo.')
    return target


def load_material_catalog(path, *, maximum=MAX_ENTRIES):
    """Validate reviewed source identities before any AI call; return a catalog dict."""
    try:
        path = Path(path).expanduser()
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise _error('Catálogo com link não é aceito.')
        path = path.absolute()
        data = _json(path, 16 * 1024**2 if maximum > MAX_ENTRIES else 1024**2)
        if data.get('schema') != 1 or data.get('source_xex_sha256') != SOURCE_XEX_SHA256:
            raise _error('Catálogo ou XEX original não suportado.')
        entries = data.get('entries')
        if not isinstance(entries, list) or not 1 <= len(entries) <= maximum:
            raise _error(f'O catálogo deve conter de 1 a {maximum} materiais.')
        accepted, excluded, seen_paths, seen_pixels, seen_dds = [], [], set(), set(), set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise _error('Entrada de material inválida.')
            inspection = _relative(path.parent, entry.get('inspection'))
            canonical, dds = entry.get('canonical_rgba8_sha256'), entry.get('dds_sha256')
            if not isinstance(canonical, str) or not _HEX64.fullmatch(canonical) or not isinstance(dds, str) or not _HEX64.fullmatch(dds):
                raise _error('Identidade original do material inválida.')
            if inspection in seen_paths or canonical in seen_pixels or dds in seen_dds:
                raise _error('Material duplicado no catálogo.')
            seen_paths.add(inspection); seen_pixels.add(canonical); seen_dds.add(dds)
            classification = entry.get('classification', 'unknown')
            if classification != 'color-opaque' or entry.get('reviewed') is not True:
                excluded.append({'inspection': entry['inspection'], 'classification': str(classification)[:64],
                                 'reason': 'not-reviewed-color-opaque'})
                continue
            source = _json(inspection, 65536)
            for name in ('original.png', 'original.dds'):
                original = _relative(inspection.parent, name)
                if not original.is_file() or original.stat().st_size > 64 * 1024**2:
                    raise _error('Origem ausente ou excessiva.')
            if (source.get('canonical_rgba8_sha256') != canonical or source.get('dds_sha256') != dds or
                    sha(inspection.parent / 'original.dds') != dds or source.get('game_xex_sha256') != SOURCE_XEX_SHA256):
                raise _error('Identidade da inspeção diverge do catálogo ou XEX.')
            accepted.append({**entry, 'inspection_path': inspection})
        return {'schema': 1, 'path': path, 'source_xex_sha256': SOURCE_XEX_SHA256,
                'catalog_sha256': sha(path), 'entries': accepted, 'excluded': excluded,
                'counts': {'total': len(entries), 'included': len(accepted), 'excluded': len(excluded)}}
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise _error('Catálogo HD inválido: ' + str(exc)) from exc


def _write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n', encoding='utf8')


def prepare_texture_pack(catalog, root, work, *, allow_download=False, cancel=None, emit=None, host_scale=2):
    """Prepare reviewed entries once, publish a content-addressed batch and return it.

    Cancellation leaves completed immutable child caches available for the next
    invocation. Batch staging is removed only when owned by this invocation.
    """
    if type(host_scale) is not int or host_scale not in (2, 4):
        raise _error('A resolução HD deve ser 2x ou 4x.')
    cancel = cancel or Cancellation(); emit = emit or (lambda event: None)
    # Always reread on-disk catalog; never trust a caller-mutated validation dict.
    catalog = load_material_catalog(catalog['path'] if isinstance(catalog, dict) else catalog)
    if not catalog['entries']:
        raise _error('Nenhum material de cor opaca foi revisado neste catálogo.')
    prepared, bc_seen, dds_total, file_total = [], set(), 0, 0
    for index, entry in enumerate(catalog['entries']):
        cancel.check()
        emit({'stage': 'hd-batch', 'message': f'Preparando material {index + 1}/{len(catalog["entries"])}',
              'completed': index, 'total': len(catalog['entries']), 'unit': 'materials'})
        child = validate_prepared_pack(prepare_texture(entry['inspection_path'], root, work,
            reviewed_color_opaque=True, allow_download=allow_download, cancel=cancel, emit=emit, host_scale=host_scale))
        metadata = _json(child / 'manifest.json', 65536)
        if (metadata.get('source_xex_sha256') != SOURCE_XEX_SHA256 or
                metadata['recipe'].get('original') != entry['canonical_rgba8_sha256']):
            raise _error('A textura preparada diverge da origem revisada.')
        bc = metadata['recipe']['original_bc']
        if not isinstance(bc, str) or not _HEX32.fullmatch(bc) or bc in bc_seen:
            raise _error('Blocos originais duplicados ou inválidos.')
        bc_seen.add(bc)
        files = {}
        for name in sorted(CHILD_FILES):
            file = child / name
            if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_FILE_BYTES:
                raise _error('Cache de material inválido.')
            files[name] = sha(file); file_total += file.stat().st_size
        dds_total += (child / 'texture.dds').stat().st_size
        if dds_total > MAX_DDS_BYTES or file_total > MAX_PACK_BYTES:
            raise _error('O lote excede o limite de armazenamento HD.')
        prepared.append({'bc': bc, 'path': child, 'files': files,
                         'dimensions': metadata['dimensions'], 'original': entry['canonical_rgba8_sha256']})
    identity = {'schema': 1, 'catalog_sha256': catalog['catalog_sha256'], 'source_xex_sha256': SOURCE_XEX_SHA256,
                'producer': 'aster-reviewed-batch-v1', 'host_scale': host_scale,
                'materials': [{k: p[k] for k in ('bc', 'files', 'dimensions', 'original')} for p in prepared]}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    packs = work.path('textures/packs'); packs.mkdir(parents=True, exist_ok=True)
    output = packs / key
    if output.exists():
        validate_texture_pack(output, cancel=cancel)
        if _json(output / 'pack.json')['recipe'] != identity:
            raise _error('Identidade do cache do lote divergente.')
        return output
    temporary = Path(tempfile.mkdtemp(prefix='.prepare-', dir=packs))
    try:
        materials, files = [], {}
        for item in prepared:
            cancel.check(); target = temporary / item['bc']; target.mkdir()
            for name, digest in item['files'].items():
                source = item['path'] / name
                if source.is_symlink() or sha(source) != digest:
                    raise _error('Cache alterado durante a montagem.')
                shutil.copyfile(source, target / name)
                if sha(target / name) != digest:
                    raise _error('Falha ao verificar a cópia do material.')
                files[item['bc'] + '/' + name] = digest
            materials.append({k: item[k] for k in ('bc', 'dimensions', 'original')})
        index = 'ASTERHDPACK1 ' + str(len(materials)) + '\n' + ''.join(p['bc'] + ' ' + p['bc'] + '\n' for p in materials)
        (temporary / 'texture-pack.index').write_text(index, encoding='ascii')
        files['texture-pack.index'] = sha(temporary / 'texture-pack.index')
        _write_json(temporary / 'pack.json', {'schema': 1, 'state': 'prepared', 'runtime_rendered': False,
            'source_xex_sha256': SOURCE_XEX_SHA256, 'recipe': identity, 'materials': materials,
            'counts': catalog['counts'], 'excluded': catalog['excluded'], 'files': files})
        validate_texture_pack(temporary, cancel=cancel); cancel.check()
        try:
            os.rename(temporary, output)
        except FileExistsError:
            # Another preparation may have published this same immutable identity.
            validate_texture_pack(output, cancel=cancel)
            if _json(output / 'pack.json')['recipe'] != identity:
                raise _error('Publicação concorrente com identidade divergente.')
    finally:
        if temporary.exists(): shutil.rmtree(temporary)
    emit({'stage': 'hd-batch', 'message': 'Pacote HD preparado e verificado.',
          'completed': len(prepared), 'total': len(prepared), 'unit': 'materials', 'state': 'completed'})
    return output


def validate_texture_pack_cached(directory, cache_directory, expected_xex_sha256=None, cancel=None, *, full=False):
    """Reuse a stable validation receipt; ``validate_texture_pack`` always rehashes.

    Callers choose a workspace cache outside the pack. Both dry-run and actual
    startup can reuse this check without decoding images or rereading DDS bytes.
    """
    from .texture_validation import ValidationReceipt, safe_path
    cancel = cancel or Cancellation()
    path = safe_path(directory)
    receipt = ValidationReceipt(cache_directory,
        {'purpose': 'texture-pack-v1', 'directory': str(path),
         'source_xex_sha256': expected_xex_sha256 or SOURCE_XEX_SHA256}, cancel)
    previous = None if full else receipt.read()
    if previous and previous.get('result') == str(path) and receipt.matches(previous, [path]):
        return path
    receipt.publish(str(path), [path],
        lambda: validate_texture_pack(path, expected_xex_sha256, cancel))
    return path


def validate_texture_pack(directory, expected_xex_sha256=None, cancel=None):
    """Verify an entire batch (or a legacy single material) without running AI."""
    cancel = cancel or Cancellation()
    cancel.check()
    try:
        path = Path(directory).expanduser().absolute()
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise _error('Pacote com link não é aceito.')
        if (path / 'library.json').exists():
            from .texture_library import validate_texture_library
            return validate_texture_library(path, expected_xex_sha256, cancel)
        if not (path / 'pack.json').exists():
            legacy = validate_prepared_pack(path, cancel=cancel)
            if _json(legacy / 'manifest.json', 65536).get('source_xex_sha256') != (expected_xex_sha256 or SOURCE_XEX_SHA256):
                raise _error('XEX do pacote divergente.')
            return legacy
        data = _json(path / 'pack.json')
        if (data.get('schema') != 1 or data.get('state') != 'prepared' or data.get('runtime_rendered') is not False or
                data.get('source_xex_sha256') != (expected_xex_sha256 or SOURCE_XEX_SHA256)):
            raise _error('Manifesto de pacote HD não suportado.')
        materials, files = data['materials'], data['files']
        counts, excluded = data.get('counts', {}), data.get('excluded')
        if (not isinstance(counts, dict) or not isinstance(excluded, list) or
                len(excluded) > MAX_ENTRIES or counts.get('included') != len(materials) or
                counts.get('excluded') != len(excluded) or counts.get('total') != len(materials) + len(excluded) or
                counts['total'] > MAX_ENTRIES):
            raise _error('Contagem de materiais divergente.')
        if not isinstance(materials, list) or not 1 <= len(materials) <= MAX_ENTRIES or not isinstance(files, dict):
            raise _error('Quantidade de materiais HD inválida.')
        expected = {'texture-pack.index'}; seen = set(); dds_total = total = 0
        recipe_materials = []
        recipe_scale = data.get('recipe', {}).get('host_scale', 2)
        if type(recipe_scale) is not int or recipe_scale not in (2, 4):
            raise _error('Escala do lote HD inválida.')
        if _relative(path, 'texture-pack.index').stat().st_size > 65536:
            raise _error('Índice HD excessivo.')
        lines = []
        for material in materials:
            cancel.check()
            bc = material['bc']
            if (not isinstance(bc, str) or not _HEX32.fullmatch(bc) or bc in seen or
                    not isinstance(material.get('original'), str) or not _HEX64.fullmatch(material['original'])):
                raise _error('Material duplicado ou inválido.')
            seen.add(bc); child = _relative(path, bc)
            expected.update(bc + '/' + name for name in CHILD_FILES)
            for name in CHILD_FILES:
                file = _relative(child, name)
                if not file.is_file() or file.stat().st_size > MAX_FILE_BYTES:
                    raise _error('Arquivo de material ausente ou excessivo.')
                total += file.stat().st_size
            dds_total += (child / 'texture.dds').stat().st_size
            if dds_total > MAX_DDS_BYTES or total > MAX_PACK_BYTES:
                raise _error('Pacote HD excede o limite de tamanho.')
            validate_prepared_pack(child, cancel=cancel)
            meta = _json(child / 'manifest.json', 65536)
            if (meta['recipe']['original_bc'] != bc or meta['recipe']['original'] != material['original'] or
                    meta['dimensions'] != material['dimensions'] or meta['recipe']['host_scale'] != recipe_scale or meta.get('source_xex_sha256') != data['source_xex_sha256']):
                raise _error('Manifestos de material divergentes.')
            recipe_materials.append({**material, 'files': {name: sha(child / name, cancel) for name in sorted(CHILD_FILES)}})
            lines.append(bc + ' ' + bc + '\n')
        recipe = data.get('recipe', {})
        if (recipe.get('schema') != 1 or recipe.get('producer') != 'aster-reviewed-batch-v1' or
                recipe.get('source_xex_sha256') != data['source_xex_sha256'] or
                not isinstance(recipe.get('catalog_sha256'), str) or not _HEX64.fullmatch(recipe['catalog_sha256']) or
                recipe.get('materials') != recipe_materials):
            raise _error('Receita do lote divergente dos materiais.')
        if set(files) != expected:
            raise _error('Tabela de arquivos HD incompleta ou inesperada.')
        for name, digest in files.items():
            cancel.check()
            file = _relative(path, name)
            if not isinstance(digest, str) or not _HEX64.fullmatch(digest) or sha(file, cancel) != digest:
                raise _error('Arquivo HD alterado.')
        index = _relative(path, 'texture-pack.index')
        if index.stat().st_size > 65536 or index.read_text(encoding='ascii') != 'ASTERHDPACK1 ' + str(len(materials)) + '\n' + ''.join(lines):
            raise _error('Índice do lote HD divergente.')
        # No additional files can silently influence the runtime loader.
        actual = set()
        for file in path.rglob('*'):
            cancel.check()
            if file.is_symlink(): raise _error('Link inesperado no pacote HD.')
            if file.is_file(): actual.add(file.relative_to(path).as_posix())
        if actual != expected | {'pack.json'}:
            raise _error('Arquivos extras no pacote HD.')
        return path.resolve()
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise PortError('HD_PACK', 'Pacote HD inválido: ' + str(exc)) from exc
