"""Versioned, project-local preferences. Only explicit typed fields are accepted."""
from pathlib import Path
import json
import sys
from . import graphics
from .errors import PortError
from .workspace import Workspace

SCHEMA = 2


def defaults(project):
    return {'schema': SCHEMA, 'workspace': str(Path(project) / '.aster'),
            'source': '', 'build_type': 'Release', 'jobs': 1, 'hd_texture_pack': '', 'hd_texture_catalog': '',
            'graphics': graphics.defaults()}


def validate(data, project):
    # Schema 1 was the original launcher-only settings file. It is accepted
    # and upgraded in memory so existing installations keep their dump path.
    if not isinstance(data, dict) or data.get('schema') not in (1, SCHEMA):
        raise PortError('SETTINGS_SCHEMA', 'Configuração incompatível.')
    result = defaults(project)
    for field in result:
        if field == 'schema':
            continue
        if field in data:
            result[field] = data[field]
    # Schema 1 files are upgraded in memory; the next save writes schema 2.
    result['schema'] = SCHEMA
    if not isinstance(result['workspace'], str) or not isinstance(result['source'], str):
        raise PortError('SETTINGS_VALUE', 'Caminhos de configuração inválidos.')
    for field in ('hd_texture_pack', 'hd_texture_catalog'):
        if not isinstance(result[field], str) or len(result[field]) > 4096:
            raise PortError('SETTINGS_VALUE', 'Caminho de texturas HD inválido.')
    work = Workspace(result['workspace'], project)
    source = Path(result['source']).expanduser().resolve() if result['source'] else None
    if source and (source == Path(project).resolve() or work.root.is_relative_to(source)
                   or source.is_relative_to(work.root)):
        raise PortError('SOURCE_OVERLAP', 'Pasta/arquivo do jogo não pode conter o workspace nem ficar dentro dele.')
    if result['build_type'] not in ('Release', 'Debug', 'RelWithDebInfo'):
        raise PortError('SETTINGS_VALUE', 'Tipo de build inválido.')
    if type(result['jobs']) is not int or not 1 <= result['jobs'] <= 64:
        raise PortError('SETTINGS_VALUE', 'Número de tarefas deve ficar entre 1 e 64.')
    previous_graphics = result['graphics']
    if isinstance(previous_graphics, dict):
        previous_graphics = dict(previous_graphics)
        # Upgrade legacy Linux-only filters to the shared spatial backend.
        if previous_graphics.get('upscaler') in ('cubic', 'sharp'):
            previous_graphics['upscaler'] = 'fsr1'
        elif 'upscaler' not in previous_graphics and previous_graphics.get('preset') == 'custom':
            previous_graphics['upscaler'] = ('fsr1' if previous_graphics.get('texture_quality') in ('high', 'ultra') else 'bilinear')
    result['graphics'] = graphics.validate(previous_graphics)
    return result


def load(project):
    p = Workspace(Path(project) / '.aster', project).path('config/settings.json')
    if not p.exists():
        return defaults(project)
    try:
        if p.stat().st_size > 65536:
            raise PortError('SETTINGS_VALUE', 'Configuração excede o limite de tamanho.')
        return validate(json.loads(p.read_text(encoding='utf8')), project)
    except (ValueError, OSError) as e:
        raise PortError('SETTINGS_READ', str(e)) from e


def save(data, project):
    result = validate(data, project)
    return Workspace(Path(project) / '.aster', project).write_json('config/settings.json', result)
