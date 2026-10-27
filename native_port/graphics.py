"""Graphics and frame-target preferences shared by the launcher and the play script.

The values here are translated to real ReXGlue command-line CVars at launch
time. Nothing in this module writes to the game profile, save data or the
dump; the launcher stores its own preferences separately.
"""
from __future__ import annotations

import sys

from .errors import PortError

DEFAULT_FSR_SHARPNESS = 30
SCALED_PIXEL_CENTER_PATCH = '0024-scaled-pixel-parameter-centers.patch'
SHADER_PRELOAD_PATCH = '0025-known-shader-preload-selection.patch'

PRESETS = ('low', 'default', 'high', 'ultra', 'custom')
PRESET_LABELS = {
    'low': 'Baixa',
    'default': 'Média',
    'high': 'Alta',
    'ultra': 'Ultra',
    'custom': 'Personalizada',
}
PRESET_DESCRIPTIONS = {
    'low': 'Máximo desempenho: 720p interno, MSAA do jogo e cache de texturas reduzido.',
    'default': '720p interno, FXAA, MSAA do jogo e 4x anisotrópico.',
    'high': '1440p interno, FSR 1, FXAA, filtragem 8x e materiais HD 2x.',
    'ultra': '4K interno, FSR 1, FXAA, filtragem 16x e materiais HD 4x.',
    'custom': 'Ajuste imagem, filtragem, qualidade de texturas e desempenho.',
}
TARGETS = ('30', '60', 'unlimited')
TARGET_LABELS = {'30': '30 fps', '60': '60 fps', 'unlimited': 'Ilimitado'}
TARGET_DESCRIPTIONS = {
    '30': 'Padrão. Menor carga de CPU/GPU. Save compartilhado do usuário.',
    '60': 'Experimental. Usa o mesmo save do usuário, independente dos gráficos.',
    'unlimited': ('Experimental. Reduz a espera de pacing e usa apresentação imediata; '
                  'ganho real acima de 60 fps ainda não confirmado.'),
}
ANTIALIASING = ('none', 'fxaa', 'fxaa_extreme')
ANTIALIASING_LABELS = {'none': 'Desligado', 'fxaa': 'FXAA', 'fxaa_extreme': 'FXAA intenso'}
SHADER_MODES = ('async', 'blocking')
UPSCALERS = ('bilinear', 'cubic', 'sharp', 'fsr1')  # Legacy cubic/sharp accepted by CLI.
COMMON_UPSCALERS = ('bilinear', 'fsr1')
UPSCALER_LABELS = {'bilinear': 'Bilinear', 'cubic': 'Bicúbico', 'sharp': 'Bicúbico + nitidez', 'fsr1': 'FSR 1 espacial (experimental)'}
OUTPUT_RESOLUTIONS = ('auto', '1280x720', '1920x1080', '2560x1440', '3840x2160')
TEXTURE_QUALITIES = ('low', 'default', 'high', 'ultra')
TEXTURE_QUALITY_LABELS = {
    'low': 'Baixa', 'default': 'Média', 'high': 'Alta', 'ultra': 'Ultra',
}
TEXTURE_LIMITS = {
    # soft, hard, render-to-texture (MB)
    'low': (192, 384, 16),
    'default': (384, 768, 24),
    'high': (512, 1024, 32),
    'ultra': (768, 1536, 48),
}
ANISOTROPIC_LABELS = {
    -1: 'Automático (jogo)',
    0: 'Desligado',
    1: '1x',
    2: '2x',
    3: '4x (padrão)',
    4: '8x',
    5: '16x',
}
_PRESET_VALUES = {
    'low': {'render_scale': 1, 'msaa_2x': True, 'anisotropic': 1,
            'texture_quality': 'low', 'present_dither': False},
    'default': {'render_scale': 1, 'msaa_2x': True, 'anisotropic': 3,
                'texture_quality': 'default', 'present_dither': False},
    'high': {'render_scale': 2, 'msaa_2x': True, 'anisotropic': 4,
             'texture_quality': 'high', 'present_dither': False},
    'ultra': {'render_scale': 3, 'msaa_2x': True, 'anisotropic': 5,
              'texture_quality': 'ultra', 'present_dither': False},
    'custom': {'render_scale': 1, 'msaa_2x': True, 'anisotropic': 3,
               'texture_quality': 'default', 'present_dither': False},
}


def defaults():
    return {
        **_PRESET_VALUES['default'],
        'preset': 'default',
        'fps_target': '30',
        'vsync': True,
        'shader_mode': 'async',
        'shader_preload': True,
        'output_resolution': 'auto',
        'fullscreen': False,
        'fsr_sharpness': DEFAULT_FSR_SHARPNESS,
    }


for _name, _filter in [('low', 'bilinear'), ('default', 'bilinear'), ('high', 'fsr1'), ('ultra', 'fsr1'), ('custom', 'bilinear')]:
    _PRESET_VALUES[_name]['upscaler'] = _filter
    _PRESET_VALUES[_name]['antialiasing'] = 'none' if _name == 'low' else 'fxaa'


def preset_values(name):
    if name not in PRESETS:
        raise PortError('GRAPHICS_VALUE', f'Preset gráfico inválido: {name}.')
    values = dict(_PRESET_VALUES[name])
    return values


def apply_preset(name, current=None):
    """Return a normalized graphics block with a preset's rendering values."""
    current = current or defaults()
    values = defaults()
    values.update({key: value for key, value in current.items() if key in values})
    values['preset'] = name
    if name != 'custom':
        values.update(preset_values(name))
    return validate(values)


def from_options(preset='default', *, render_scale=None, msaa_2x=None,
                 anisotropic=None, texture_quality=None, present_dither=None,
                 fps_target='30', vsync=True, shader_mode='async', shader_preload=True, output_resolution='auto', upscaler=None, antialiasing=None, fullscreen=False, fsr_sharpness=DEFAULT_FSR_SHARPNESS):
    """Build a graphics block from CLI/UI values.

    Any explicit rendering override switches the block to ``custom`` so a
    preset can never silently discard the value requested by the user.
    """
    if preset not in PRESETS:
        raise PortError('GRAPHICS_VALUE', f'Preset gráfico inválido: {preset}.')
    values = defaults()
    values.update(preset_values(preset))
    values['preset'] = preset
    overrides = {
        'render_scale': render_scale,
        'msaa_2x': msaa_2x,
        'anisotropic': anisotropic,
        'texture_quality': texture_quality,
        'present_dither': present_dither,
        'antialiasing': antialiasing,
    }
    applied = False
    for field, value in overrides.items():
        if value is not None:
            values[field] = value
            applied = True
    if applied and preset != 'custom':
        values['preset'] = 'custom'
    values.update(fps_target=fps_target, vsync=vsync, shader_mode=shader_mode, shader_preload=shader_preload, output_resolution=output_resolution, fullscreen=fullscreen, fsr_sharpness=fsr_sharpness)
    if upscaler is not None:
        if values['upscaler'] != upscaler:
            values['preset'] = 'custom'
        values['upscaler'] = upscaler
    return validate(values)


def validate(data):
    if not isinstance(data, dict):
        raise PortError('GRAPHICS_VALUE', 'Configuração gráfica inválida.')
    result = defaults()
    for field in result:
        if field in data:
            result[field] = data[field]
    if result['preset'] not in PRESETS:
        raise PortError('GRAPHICS_VALUE', 'Preset gráfico inválido.')
    if result['preset'] != 'custom':
        result.update(preset_values(result['preset']))
    if result['fps_target'] not in TARGETS:
        raise PortError('GRAPHICS_VALUE', 'Alvo de FPS deve ser 30, 60 ou ilimitado.')
    if not isinstance(result['fullscreen'], bool):
        raise PortError('GRAPHICS_VALUE', 'Modo de tela inválido.')
    if type(result['fsr_sharpness']) is not int or not 0 <= result['fsr_sharpness'] <= 100:
        raise PortError('GRAPHICS_VALUE', 'Nitidez FSR deve ficar entre 0 e 100.')
    if not isinstance(result['vsync'], bool):
        raise PortError('GRAPHICS_VALUE', 'VSync inválido.')
    if result['shader_mode'] not in SHADER_MODES:
        raise PortError('GRAPHICS_VALUE', 'Modo de shaders inválido.')
    if type(result['shader_preload']) is not bool:
        raise PortError('GRAPHICS_VALUE', 'Pré-compilação de shaders deve estar ligada ou desligada.')
    if result['antialiasing'] not in ANTIALIASING:
        raise PortError('GRAPHICS_VALUE', 'Antisserrilhado inválido.')
    if result['upscaler'] not in UPSCALERS:
        raise PortError('GRAPHICS_VALUE', 'Filtro de ampliação inválido.')
    if result['output_resolution'] not in OUTPUT_RESOLUTIONS:
        raise PortError('GRAPHICS_VALUE', 'Resolução de saída inválida.')
    render_scale = result['render_scale']
    if type(render_scale) is not int or not 1 <= render_scale <= 3:
        raise PortError('GRAPHICS_VALUE', 'Resolução interna deve ficar entre 1x e 3x.')
    if not isinstance(result['msaa_2x'], bool):
        raise PortError('GRAPHICS_VALUE', 'MSAA inválido.')
    if type(result['anisotropic']) is not int or not -1 <= result['anisotropic'] <= 5:
        raise PortError('GRAPHICS_VALUE', 'Filtragem anisotrópica inválida.')
    if result['texture_quality'] not in TEXTURE_QUALITIES:
        raise PortError('GRAPHICS_VALUE', 'Qualidade de texturas inválida.')
    if not isinstance(result['present_dither'], bool):
        raise PortError('GRAPHICS_VALUE', 'Dithering inválido.')
    if result['fps_target'] == 'unlimited':
        # VSync is not an option in this mode; keeping the saved preference
        # would imply a smoothness that the mode cannot provide.
        result['vsync'] = False
    return result


def effective_target(data):
    """Return the target used by the play script, including legacy aliases."""
    return validate(data)['fps_target']


def internal_resolution(render_scale):
    width, height = 1280 * int(render_scale), 720 * int(render_scale)
    return f'{width}x{height}'


def texture_limits(quality):
    if quality not in TEXTURE_LIMITS:
        raise PortError('GRAPHICS_VALUE', 'Qualidade de texturas inválida.')
    return TEXTURE_LIMITS[quality]


def cvar_arguments(data):
    """Map a validated graphics block to deterministic ReXGlue CVar flags."""
    data = validate(data)
    soft, hard, rtt = texture_limits(data['texture_quality'])
    arguments = [
        f"--resolution_scale={data['render_scale']}",
        f"--anisotropic_override={data['anisotropic']}",
        f"--texture_cache_memory_limit_soft={soft}",
        f"--texture_cache_memory_limit_hard={hard}",
        f"--texture_cache_memory_limit_render_to_texture={rtt}",
        f"--present_dither={str(data['present_dither']).lower()}",
        f"--swap_post_effect={data['antialiasing']}",
        f"--fullscreen={str(data['fullscreen']).lower()}",
    ]
    if data['output_resolution'] != 'auto':
        width, height = data['output_resolution'].split('x')
        arguments.extend([f'--window_width={width}', f'--window_height={height}'])
    return arguments


def summary(data):
    data = validate(data)
    return (f"{PRESET_LABELS[data['preset']]} · {internal_resolution(data['render_scale'])} · "
            f"{UPSCALER_LABELS[data['upscaler']]} · MSAA do jogo · "
            f"Aniso {ANISOTROPIC_LABELS[data['anisotropic']]} · "
            f"Texturas {TEXTURE_QUALITY_LABELS[data['texture_quality']]} · "
            f"{TARGET_LABELS[data['fps_target']]}")
