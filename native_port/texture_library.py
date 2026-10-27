"""Immutable campaign libraries; runtime loads only matching material DDS files.

The library index contains paths, dimensions and hashes, never guest assets.
Preparation is outside gameplay and uses the same reviewed per-material cache.
"""
from __future__ import annotations
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from .errors import PortError
from .tasks import Cancellation
from .texture_enhance import prepare_texture, validate_prepared_pack, sha
from .texture_pack import (CHILD_FILES, SOURCE_XEX_SHA256, _HEX32, _HEX64,
                           _json, _relative, load_material_catalog)

MAX_MATERIALS = 16384
MAX_DDS_BYTES = 64 * 1024**3
MAX_LIBRARY_BYTES = 256 * 1024**3
MAX_INDEX_BYTES = 4 * 1024**2


def _error(message):
    return PortError('HD_LIBRARY', message)


def _read(path):
    return _json(path, 32 * 1024**2)


def _index_line(bc, meta, dds):
    parts = (dds.parent / 'texture.index').read_text(encoding='ascii').split()
    return f'{bc} {bc} {parts[1]} {parts[2]} {parts[3]} {parts[5]} {dds.stat().st_size}\n'


def validate_texture_library(directory, expected_xex_sha256=None, cancel=None):
    cancel = cancel or Cancellation(); cancel.check()
    try:
        path = Path(directory).expanduser().absolute()
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise _error('Biblioteca com link não é aceita.')
        data = _read(path / 'library.json')
        if (data.get('schema') != 1 or data.get('state') != 'prepared' or
                data.get('source_xex_sha256') != (expected_xex_sha256 or SOURCE_XEX_SHA256) or
                data.get('runtime_rendered') is not False):
            raise _error('Manifesto de biblioteca inválido.')
        materials = data.get('materials'); files = data.get('files'); recipe = data.get('recipe', {})
        if (not isinstance(materials, list) or not 1 <= len(materials) <= MAX_MATERIALS or
                not isinstance(files, dict) or recipe.get('producer') != 'aster-campaign-library-v1' or
                recipe.get('source_xex_sha256') != data['source_xex_sha256'] or
                type(recipe.get('host_scale')) is not int or recipe['host_scale'] not in (2, 4) or
                not isinstance(recipe.get('catalog_sha256'), str) or not _HEX64.fullmatch(recipe['catalog_sha256'])):
            raise _error('Identidade da biblioteca inválida.')
        counts, excluded = data.get('counts', {}), data.get('excluded')
        if (not isinstance(counts, dict) or not isinstance(excluded, list) or
                counts.get('included') != len(materials) or counts.get('excluded') != len(excluded) or
                counts.get('total') != len(materials) + len(excluded) or counts['total'] > MAX_MATERIALS):
            raise _error('Contagem da biblioteca divergente.')
        seen = set(); expected = {'texture-library.index'}; lines = []; identity = []; total = dds_total = 0
        for item in materials:
            cancel.check(); bc = item['bc']
            if not isinstance(bc, str) or not _HEX32.fullmatch(bc) or bc in seen:
                raise _error('Material duplicado ou inválido.')
            seen.add(bc); child = _relative(path, bc)
            validate_prepared_pack(child, cancel=cancel); meta = _json(child / 'manifest.json', 65536)
            if (meta['recipe']['original_bc'] != bc or meta['recipe']['original'] != item['original'] or
                    meta['dimensions'] != item['dimensions'] or meta['recipe']['host_scale'] != recipe['host_scale'] or
                    meta.get('source_xex_sha256') != data['source_xex_sha256']):
                raise _error('Material divergente da biblioteca.')
            hashes = {}
            for name in sorted(CHILD_FILES):
                member = _relative(child, name); digest = sha(member, cancel)
                if files.get(bc + '/' + name) != digest:
                    raise _error('Arquivo da biblioteca alterado.')
                expected.add(bc + '/' + name); hashes[name] = digest; total += member.stat().st_size
            dds = child / 'texture.dds'; dds_total += dds.stat().st_size
            if total > MAX_LIBRARY_BYTES or dds_total > MAX_DDS_BYTES:
                raise _error('Biblioteca excede o limite de armazenamento.')
            identity.append({**item, 'files': hashes}); lines.append(_index_line(bc, meta, dds))
        index = _relative(path, 'texture-library.index')
        if index.stat().st_size > MAX_INDEX_BYTES or index.read_text(encoding='ascii') != 'ASTERHDLIB1 ' + str(len(materials)) + '\n' + ''.join(lines):
            raise _error('Índice da biblioteca divergente.')
        if set(files) != expected or files['texture-library.index'] != sha(index, cancel) or recipe.get('materials') != identity:
            raise _error('Tabela de arquivos/receita da biblioteca divergente.')
        actual = set()
        for member in path.rglob('*'):
            cancel.check()
            if member.is_symlink(): raise _error('Link inesperado na biblioteca.')
            if member.is_file(): actual.add(member.relative_to(path).as_posix())
        if actual != expected | {'library.json'}:
            raise _error('Arquivo inesperado na biblioteca.')
        return path.resolve()
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise _error('Biblioteca inválida: ' + str(exc)) from exc


def _link_or_copy(source, destination):
    # Verified caches are immutable. Hard links save disk without symlink lookup
    # or references outside the portable library. Unsupported volumes copy bytes.
    try:
        os.link(source, destination)
    except OSError as exc:
        if exc.errno not in (errno.EXDEV, errno.EPERM, errno.ENOSYS, errno.EOPNOTSUPP):
            raise
        shutil.copyfile(source, destination)


def prepare_texture_library(catalog, root, work, *, host_scale=2, cancel=None, emit=None, allow_download=False):
    cancel = cancel or Cancellation(); emit = emit or (lambda event: None)
    if type(host_scale) is not int or host_scale not in (2, 4):
        raise _error('Escala da biblioteca inválida.')
    catalog = load_material_catalog(catalog['path'] if isinstance(catalog, dict) else catalog, maximum=MAX_MATERIALS)
    if not catalog['entries']: raise _error('Biblioteca sem materiais revisados.')
    prepared = []; seen = set(); total = dds_total = 0
    for i, entry in enumerate(catalog['entries']):
        cancel.check()
        emit({'stage': 'hd-batch', 'message': f'Preparando material da campanha {i + 1}/{len(catalog["entries"])}',
              'completed': i, 'total': len(catalog['entries']), 'unit': 'materials'})
        child = prepare_texture(entry['inspection_path'], root, work, reviewed_color_opaque=True,
            allow_download=allow_download, cancel=cancel, emit=emit, host_scale=host_scale)
        validate_prepared_pack(child, cancel=cancel); meta = _json(child / 'manifest.json', 65536)
        bc = meta['recipe']['original_bc']
        if (bc in seen or meta['recipe']['original'] != entry['canonical_rgba8_sha256'] or
                meta.get('source_xex_sha256') != SOURCE_XEX_SHA256):
            raise _error('Material duplicado ou divergente.')
        seen.add(bc)
        hashes = {name: sha(child / name, cancel) for name in sorted(CHILD_FILES)}
        total += sum((child / name).stat().st_size for name in CHILD_FILES)
        dds_total += (child / 'texture.dds').stat().st_size
        if total > MAX_LIBRARY_BYTES or dds_total > MAX_DDS_BYTES:
            raise _error('Biblioteca excede o limite de armazenamento.')
        prepared.append({'bc': bc, 'original': entry['canonical_rgba8_sha256'],
                         'dimensions': meta['dimensions'], 'files': hashes, 'path': child})
    recipe = {'producer': 'aster-campaign-library-v1', 'host_scale': host_scale,
              'source_xex_sha256': SOURCE_XEX_SHA256, 'catalog_sha256': catalog['catalog_sha256'],
              'materials': [{k: v for k, v in item.items() if k != 'path'} for item in prepared]}
    key = hashlib.sha256(json.dumps(recipe, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    home = work.path('textures/libraries'); home.mkdir(parents=True, exist_ok=True); output = home / key
    if output.exists():
        validate_texture_library(output, cancel=cancel)
        if _read(output / 'library.json')['recipe'] != recipe: raise _error('Cache divergente.')
        return output
    stage = Path(tempfile.mkdtemp(prefix='.library-', dir=home))
    try:
        files = {}; materials = []; lines = []
        for item in prepared:
            cancel.check(); child = stage / item['bc']; child.mkdir()
            for name, digest in item['files'].items():
                source = item['path'] / name
                if source.is_symlink() or sha(source, cancel) != digest: raise _error('Cache alterado durante montagem.')
                _link_or_copy(source, child / name); files[item['bc'] + '/' + name] = digest
            meta = _json(child / 'manifest.json', 65536)
            lines.append(_index_line(item['bc'], meta, child / 'texture.dds'))
            materials.append({k: item[k] for k in ('bc', 'original', 'dimensions')})
        (stage / 'texture-library.index').write_text('ASTERHDLIB1 ' + str(len(materials)) + '\n' + ''.join(lines), encoding='ascii')
        files['texture-library.index'] = sha(stage / 'texture-library.index', cancel)
        (stage / 'library.json').write_text(json.dumps({'schema': 1, 'state': 'prepared', 'runtime_rendered': False,
            'source_xex_sha256': SOURCE_XEX_SHA256, 'recipe': recipe, 'materials': materials,
            'counts': catalog['counts'], 'excluded': catalog['excluded'], 'files': files}, sort_keys=True, indent=2), encoding='utf8')
        validate_texture_library(stage, cancel=cancel); cancel.check()
        try: os.rename(stage, output)
        except FileExistsError:
            validate_texture_library(output, cancel=cancel)
            if _read(output / 'library.json')['recipe'] != recipe:
                raise _error('Publicação concorrente com identidade divergente.')
    finally:
        if stage.exists(): shutil.rmtree(stage)
    emit({'stage': 'hd-batch', 'message': 'Biblioteca da campanha preparada e verificada.',
          'completed': len(prepared), 'total': len(prepared), 'unit': 'materials', 'state': 'completed'})
    return output
