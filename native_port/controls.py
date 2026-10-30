"""Portable, validated keyboard/gamepad preferences consumed by the runtime.

Gamepad names describe physical positions, shared by SDL's Xbox and PlayStation
layouts. Remapping applies only to physical devices; keyboard binds stay separate.
"""
from __future__ import annotations
import math
import string
from .errors import PortError

SCHEMA = 1
LAYOUTS = {'auto': 'Automático', 'xbox': 'Xbox', 'playstation': 'PlayStation'}
ACTIONS = (
    ('a', 'A / ×', 'Confirmar / pular'), ('b', 'B / ○', 'Voltar / esquivar'),
    ('x', 'X / □', 'Ataque'), ('y', 'Y / △', 'Ataque pesado'),
    ('left_shoulder', 'LB / L1', 'Ombro esquerdo'),
    ('right_shoulder', 'RB / R1', 'Ombro direito'),
    ('left_trigger', 'LT / L2', 'Gatilho esquerdo'),
    ('right_trigger', 'RT / R2', 'Gatilho direito'),
    ('back', 'Back / Share', 'Voltar / Select'),
    ('start', 'Start / Options', 'Pausa / iniciar'),
    ('lstick_press', 'LS / L3', 'Pressionar analógico esquerdo'),
    ('rstick_press', 'RS / R3', 'Pressionar analógico direito'),
    ('dpad_up', '↑', 'Direcional cima'), ('dpad_down', '↓', 'Direcional baixo'),
    ('dpad_left', '←', 'Direcional esquerda'), ('dpad_right', '→', 'Direcional direita'),
)
PAD_NAMES = tuple(row[0] for row in ACTIONS)
PAD_SOURCES = PAD_NAMES + ('none',)
PAD_LABELS = {row[0]: row[1] for row in ACTIONS} | {'none': 'Sem comando'}
KEYBOARD_DEFAULTS = {
    'a': 'Semicolon,Space', 'b': 'Quote,Backspace', 'x': 'L', 'y': 'P',
    'left_trigger': 'Q,I', 'right_trigger': 'E,O',
    'left_shoulder': '1', 'right_shoulder': '3',
    'lstick_up': 'W', 'lstick_down': 'S', 'lstick_left': 'A', 'lstick_right': 'D',
    'lstick_press': 'F', 'rstick_up': 'Up', 'rstick_down': 'Down',
    'rstick_left': 'Left', 'rstick_right': 'Right', 'rstick_press': 'K',
    'dpad_up': 'Shift+Up', 'dpad_down': 'Shift+Down',
    'dpad_left': 'Shift+Left', 'dpad_right': 'Shift+Right',
    'back': 'Z,Tab', 'start': 'X,Return', 'guide': '',
}
KEYBOARD_LABELS = {key: description for key, _, description in ACTIONS} | {
    'lstick_up': 'Mover para cima', 'lstick_down': 'Mover para baixo',
    'lstick_left': 'Mover à esquerda', 'lstick_right': 'Mover à direita',
    'rstick_up': 'Câmera para cima', 'rstick_down': 'Câmera para baixo',
    'rstick_left': 'Câmera à esquerda', 'rstick_right': 'Câmera à direita',
    'guide': 'Botão Guide',
}
KEY_NAMES = set(string.ascii_uppercase + string.digits) | {
    *(f'F{i}' for i in range(1, 25)), *(f'Numpad{i}' for i in range(10)),
    'Comma', 'Period', 'Slash', 'Backslash', 'Semicolon', 'Minus', 'Plus', 'Backtick',
    'LBracket', 'RBracket', 'Quote', 'Escape', 'Return', 'Space', 'Tab', 'Backspace',
    'Delete', 'Insert', 'Home', 'End', 'PageUp', 'PageDown', 'Left', 'Right', 'Up',
    'Down', 'NumpadEnter', 'NumpadPlus', 'NumpadMinus', 'NumpadStar', 'NumpadSlash',
    'PrintScreen', 'Pause', 'CapsLock', 'NumLock', 'ScrollLock', 'LMB', 'RMB', 'MMB',
}
MODIFIERS = ('Shift', 'Ctrl', 'Alt')
AXIS_FIELDS = ('swap_sticks', 'invert_lx', 'invert_ly', 'invert_rx', 'invert_ry')


def defaults():
    return {'schema': SCHEMA, 'layout': 'auto', 'keyboard_enabled': True,
            'mouse_look': False, 'mouse_sensitivity': 1.0,
            'keyboard': dict(KEYBOARD_DEFAULTS),
            'gamepad': {'bindings': dict(zip(PAD_NAMES, PAD_NAMES)),
                        **dict.fromkeys(AXIS_FIELDS, False), 'deadzone': 0}}


def normalize_keybind(value):
    if not isinstance(value, str) or len(value) > 128:
        raise PortError('CONTROLS_KEY', 'Combinação de teclas inválida.')
    if not value.strip():
        return ''
    alternatives = []
    for alternative in value.split(','):
        pieces = [part.strip() for part in alternative.split('+')]
        if not pieces or not all(pieces):
            raise PortError('CONTROLS_KEY', 'Use teclas como Space, L ou Shift+Up; separe alternativas com vírgula.')
        key = pieces[-1]
        if len(key) == 1 and key in string.ascii_letters:
            key = key.upper()
        modifiers = ["Ctrl" if p == 'Control' else p for p in pieces[:-1]]
        if (key not in KEY_NAMES or len(set(modifiers)) != len(modifiers)
                or any(p not in MODIFIERS for p in modifiers)):
            raise PortError('CONTROLS_KEY', f'Tecla ou modificador não reconhecido: {alternative}.')
        normalized = '+'.join([p for p in MODIFIERS if p in modifiers] + [key])
        if normalized not in alternatives:
            alternatives.append(normalized)
    if len(alternatives) > 4:
        raise PortError('CONTROLS_KEY', 'Cada comando aceita até quatro alternativas de teclado.')
    return ','.join(alternatives)


def validate(value):
    if not isinstance(value, dict) or value.get('schema') != SCHEMA:
        raise PortError('CONTROLS_SCHEMA', 'Configuração de controles incompatível.')
    result = defaults()
    if set(value) - set(result):
        raise PortError('CONTROLS_VALUE', 'Campo de controles desconhecido.')
    result.update(value)
    if not isinstance(result['layout'], str) or result['layout'] not in LAYOUTS:
        raise PortError('CONTROLS_VALUE', 'Layout de controle inválido.')
    for field in ('keyboard_enabled', 'mouse_look'):
        if type(result[field]) is not bool:
            raise PortError('CONTROLS_VALUE', 'Opção de teclado/mouse inválida.')
    sensitivity = result['mouse_sensitivity']
    if type(sensitivity) not in (int, float) or not .01 <= sensitivity <= 10 or not math.isfinite(sensitivity):
        raise PortError('CONTROLS_VALUE', 'Sensibilidade deve ficar entre 0,01 e 10.')
    keyboard = result['keyboard']
    if not isinstance(keyboard, dict) or set(keyboard) != set(KEYBOARD_DEFAULTS):
        raise PortError('CONTROLS_VALUE', 'Mapa de teclado incompleto ou desconhecido.')
    result['keyboard'] = {key: normalize_keybind(keyboard[key]) for key in KEYBOARD_DEFAULTS}
    if result['keyboard_enabled'] and any(not result['keyboard'][key] for key in ('a', 'b', 'back', 'start')):
        raise PortError('CONTROLS_NAVIGATION', 'Mantenha teclas para confirmar, voltar, Select e Start.')
    gamepad = result['gamepad']
    expected = {'bindings', *AXIS_FIELDS, 'deadzone'}
    if not isinstance(gamepad, dict) or set(gamepad) != expected:
        raise PortError('CONTROLS_VALUE', 'Configuração de controle incompleta ou desconhecida.')
    bindings = gamepad['bindings']
    if (not isinstance(bindings, dict) or set(bindings) != set(PAD_NAMES)
            or any(not isinstance(x, str) or x not in PAD_SOURCES for x in bindings.values())):
        raise PortError('CONTROLS_VALUE', 'Botão físico inválido.')
    bound = [x for x in bindings.values() if x != 'none']
    if len(set(bound)) != len(bound):
        raise PortError('CONTROLS_DUPLICATE', 'Um botão físico não pode executar dois comandos. Troque os dois campos ao inverter botões.')
    if any(bindings[key] == 'none' for key in ('a', 'b', 'back', 'start')):
        raise PortError('CONTROLS_NAVIGATION', 'Mantenha botões para confirmar, voltar, Select e Start.')
    if any(type(gamepad[key]) is not bool for key in AXIS_FIELDS):
        raise PortError('CONTROLS_VALUE', 'Opção de analógico inválida.')
    if type(gamepad['deadzone']) is not int or not 0 <= gamepad['deadzone'] <= 30:
        raise PortError('CONTROLS_VALUE', 'Zona morta adicional deve ficar entre 0 e 30%.')
    result['gamepad'] = dict(gamepad, bindings=dict(bindings))
    return result


def cvar_arguments(value):
    config = validate(value)
    pad = config['gamepad']
    boolean = lambda value: str(value).lower()
    arguments = [f'--mnk_mode={boolean(config["keyboard_enabled"])}',
                 f'--mnk_mouse={boolean(config["mouse_look"])}',
                 f'--mnk_sensitivity={config["mouse_sensitivity"]:g}']
    arguments += [f'--keybind_{key}={bind}' for key, bind in config['keyboard'].items()]
    arguments += ['--aster_pad_map=' + ','.join(str(PAD_SOURCES.index(pad['bindings'][key])) for key in PAD_NAMES),
                  '--aster_pad_axes=' + ','.join('1' if pad[key] else '0' for key in AXIS_FIELDS),
                  f'--aster_pad_deadzone={pad["deadzone"]}',
                  f'--aster_controller_layout={config["layout"]}']
    return arguments
