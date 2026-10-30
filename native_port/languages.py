"""Independent language selections for the reviewed Green Lantern edition.

Engine language values are not Xbox language IDs. The Europe SKU declares
Portuguese (engine 11) for text, while its shipped dialogue banks cover five
other languages. Nothing in this module creates or distributes game text.
"""
from pathlib import Path

from .errors import PortError

LABELS = {
    'auto': 'Padrão do jogo',
    'en': 'English',
    'pt-BR': 'Português',
    'fr': 'Français',
    'de': 'Deutsch',
    'it': 'Italiano',
    'es': 'Español',
}
ENGINE_IDS = {'en': 0, 'fr': 1, 'es': 3, 'de': 4, 'it': 5, 'pt-BR': 11}
TEXT_LANGUAGES = ('auto', 'pt-BR', 'en', 'fr', 'de', 'it', 'es')
VOICE_LANGUAGES = ('auto', 'en', 'fr', 'de', 'it', 'es')
EUROPE_SKU = b'X360_GL_EUROPE'


def defaults():
    return {'subtitle_language': 'pt-BR', 'voice_language': 'en'}


def validate(value):
    if not isinstance(value, dict):
        raise PortError('LANGUAGE_SETTINGS', 'Configuração de idiomas inválida.')
    unknown = set(value).difference(defaults())
    if unknown:
        raise PortError('LANGUAGE_SETTINGS', 'Opção de idioma desconhecida: ' + ', '.join(sorted(unknown)))
    result = {**defaults(), **value}
    if (not isinstance(result['subtitle_language'], str) or
            result['subtitle_language'] not in TEXT_LANGUAGES):
        raise PortError('LANGUAGE_TEXT', 'Idioma de interface e legendas inválido.')
    if (not isinstance(result['voice_language'], str) or
            result['voice_language'] not in VOICE_LANGUAGES):
        raise PortError('LANGUAGE_VOICE',
                        'Dublagem indisponível. Esta edição não contém áudio em português.')
    return result


def availability(game_root):
    """Inventory existing language resources without modifying the dump.

    File existence is not an integrity verification; the normal dump/build
    verifier remains responsible for identifying the supported executable.
    Text choices are declared by the reviewed Europe SKU, not inferred merely
    from shared fonts. Voice choices additionally require the dialogue bank.
    """
    root = Path(game_root)
    sku = root / 'gl/common/sku_x360.bin_be'
    try:
        edition = sku.read_bytes() if sku.stat().st_size <= 64 else b''
    except OSError:
        edition = b''
    known = edition == EUROPE_SKU and (root / 'gl/x360/levels/gui.lvl_760').is_file()
    text = tuple(code for code in TEXT_LANGUAGES if code == 'auto' or known)
    voice = tuple(code for code in VOICE_LANGUAGES if code == 'auto' or (
        root / f'gl/x360/sound/fmod/dialog_{code}.fsb').is_file())
    return {'reviewed_europe_sku': known, 'text': text, 'voice': voice,
            'portuguese_voice_available': False}


def require_available(value, game_root):
    result = validate(value)
    available = availability(game_root)
    if result['subtitle_language'] not in available['text']:
        raise PortError('LANGUAGE_MISSING',
                        'Idioma de texto não confirmado neste dump. Selecione Padrão do jogo ou confira a edição.')
    if result['voice_language'] not in available['voice']:
        raise PortError('LANGUAGE_MISSING',
                        'O banco de voz selecionado não está presente no dump. Os originais foram preservados.')
    return result


def cvar_arguments(value, game_root=None):
    value = validate(value) if game_root is None else require_available(value, game_root)
    result = []
    for key, flag in (('subtitle_language', 'aster_ui_language'),
                      ('voice_language', 'aster_spoken_language')):
        if value[key] != 'auto':
            result.append(f'--{flag}={ENGINE_IDS[value[key]]}')
    return result
