#!/usr/bin/env python3
"""Abre a compilação local com perfil Vulkan FSI e opções gráficas explícitas."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
try:
    import resource
except ImportError:
    resource = None
import shlex
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from native_port import controls, graphics, languages  # noqa: E402

EXPECTED_XEX = '3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1'
MAIN_BINARY = '.aster/build/rex-green/aster_green_lantern'
MAIN_REPORT = '.aster/reports/rexglue-runtime-probe.json'
MAIN_RUNTIME = '.aster/runtime/green-lantern'
EXPERIMENTAL_60_BINARY = '.aster/build/rex-fps-validation-v9/aster_green_lantern'
EXPERIMENTAL_60_REPORT = '.aster/reports/rexglue-runtime-probe-60fps.json'
EXPERIMENTAL_60_RUNTIME = MAIN_RUNTIME
EXPERIMENTAL_UNLIMITED_BINARY = '.aster/build/rex-fps-unlimited-v10/aster_green_lantern'
EXPERIMENTAL_UNLIMITED_REPORT = '.aster/reports/rexglue-runtime-probe-unlimited.json'
EXPERIMENTAL_UNLIMITED_RUNTIME = MAIN_RUNTIME


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


from native_port.locking import lock_session
from native_port.native_build import read_install, verify_install, XEX_SHA256, backend_update_reason, INTEGRATION_VERSION
from native_port.paths import external_env
from native_port.shader_prepare import prepare_game_shaders
from native_port.workspace import Workspace
from native_port.errors import PortError


def mode_paths(target):
    if target == '60':
        return EXPERIMENTAL_60_BINARY, EXPERIMENTAL_60_REPORT, EXPERIMENTAL_60_RUNTIME
    if target == 'unlimited':
        return EXPERIMENTAL_UNLIMITED_BINARY, EXPERIMENTAL_UNLIMITED_REPORT, EXPERIMENTAL_UNLIMITED_RUNTIME
    return MAIN_BINARY, MAIN_REPORT, MAIN_RUNTIME


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game_root', nargs='?', type=Path,
                        help='Pasta que contém default.xex; padrão: última pasta testada.')
    parser.add_argument('--dry-run', '--validar', action='store_true',
                        help='Confere arquivos e bibliotecas e mostra o comando, sem abrir o jogo.')
    parser.add_argument('--fps-target', choices=graphics.TARGETS,
                        help='Alvo de quadros: 30 (padrão), 60 ou ilimitado. Os dois últimos são experimentais.')
    parser.add_argument('--experimental-60fps', action='store_true',
                        help='Atalho antigo para --fps-target 60.')
    parser.add_argument('--graphics-preset', choices=graphics.PRESETS, default='default',
                        help='Preset gráfico. Padrão: default (mesmos valores do build principal).')
    parser.add_argument('--antialiasing', choices=graphics.ANTIALIASING,
                        help='Antisserrilhado antes da ampliação, Linux/Windows: none, fxaa ou fxaa_extreme.')
    parser.add_argument('--upscaler', choices=graphics.UPSCALERS, help='Filtro espacial de saída (Linux com backend atualizado).')
    parser.add_argument('--output-resolution', choices=graphics.OUTPUT_RESOLUTIONS, default='auto',
                        help='Tamanho da janela, incluindo 1920x1080; independente da escala interna.')
    parser.add_argument('--fullscreen', choices=('on', 'off'), default='off', help='Tela cheia ou janela (Linux/Windows).')
    parser.add_argument('--fsr-sharpness', type=int, default=graphics.DEFAULT_FSR_SHARPNESS, help='Nitidez FSR 1: 0 a 100; padrão equilibrado 30. Sem efeito em bilinear.')
    parser.add_argument('--render-scale', type=int, choices=(1, 2, 3),
                        help='Escala interna: 1x=720p, 2x=1440p, 3x=4K. Requer backend atualizado para 2x/3x.')
    parser.add_argument('--msaa', choices=('on', 'off'),
                        help='Compatibilidade: FSI mantém o MSAA do jogo; off não é suportado.')
    parser.add_argument('--anisotropic', type=int, choices=tuple(graphics.ANISOTROPIC_LABELS),
                        help='Filtragem anisotrópica (-1..5). Implica preset custom.')
    parser.add_argument('--hd-texture-pack', type=Path, help='Pacote local de cor opaca revisado, gerado pelo Real-ESRGAN.')
    parser.add_argument('--ui-texture-pack', type=Path, help='Atlas de fonte revisado com alpha e métricas originais; experimental.')
    parser.add_argument('--texture-quality', choices=graphics.TEXTURE_QUALITIES,
                        help='Limite de memória do cache de texturas. Implica preset custom.')
    parser.add_argument('--dither', choices=('on', 'off'),
                        help='Dithering de apresentação. Implica preset custom.')
    parser.add_argument('--shader-mode', choices=graphics.SHADER_MODES, default='async',
                        help='Shaders novos: async em segundo plano (padrão) ou blocking com espera.')
    parser.add_argument('--shader-preload', choices=('on', 'off'), default='on',
                        help='Preparar shaders/pipelines conhecidos antes de jogar. Cache persistente; não cobre cenas inéditas.')
    parser.add_argument('--vsync', choices=('on', 'off'),
                        help='VSync. Padrão ligado; desligado é experimental. O modo ilimitado exige off.')
    parser.add_argument('--present-mode', choices=('auto', 'mailbox', 'fifo', 'immediate'),
                        help='Apresentação. O modo ilimitado exige immediate.')
    parser.add_argument('--controls-json', help='Preferências tipadas de teclado/controle fornecidas pelo launcher.')
    parser.add_argument('--subtitle-language', choices=languages.TEXT_LANGUAGES,
                        help='Idioma original da interface e legendas, independente da voz.')
    parser.add_argument('--voice-language', choices=languages.VOICE_LANGUAGES,
                        help='Idioma da dublagem presente no dump, independente das legendas.')
    return parser, parser.parse_args(argv)


def resolve_target(parser, args):
    if args.experimental_60fps and args.fps_target and args.fps_target != '60':
        parser.error('--experimental-60fps não pode ser combinado com outro alvo de FPS.')
    return args.fps_target or ('60' if args.experimental_60fps else '30')


def resolve_graphics(parser, args, target):
    if target == 'unlimited':
        if args.vsync == 'on':
            parser.error('O modo ilimitado exige --vsync off.')
        if args.present_mode in ('fifo', 'mailbox'):
            parser.error('O modo ilimitado exige apresentação immediate.')
    if args.msaa == 'off':
        parser.error('O backend FSI preserva o MSAA do jogo; não oferece desligamento de MSAA.')
    vsync_on = args.vsync != 'off' 
    try:
        data = graphics.from_options(
            args.graphics_preset,
            render_scale=args.render_scale,
            msaa_2x=None if args.msaa is None else args.msaa == 'on',
            anisotropic=args.anisotropic,
            texture_quality=args.texture_quality,
            present_dither=None if args.dither is None else args.dither == 'on',
            fps_target=target,
            vsync=vsync_on,
            shader_mode=args.shader_mode,
            shader_preload=args.shader_preload == 'on',
            output_resolution=args.output_resolution,
            upscaler=args.upscaler,
            antialiasing=args.antialiasing,
            fullscreen=args.fullscreen == 'on',
            fsr_sharpness=args.fsr_sharpness,
        )
        return data
    except Exception as exc:  # PortError and malformed command-line combinations
        parser.error(str(exc))


def resolve_present_mode(args, target, vsync_on):
    if target == 'unlimited':
        return 'immediate'
    if args.present_mode:
        return args.present_mode
    return 'fifo' if vsync_on else 'immediate'


def mode_flags(target):
    if target == '60':
        return ['--aster_frame_diagnostics=true', '--aster_experimental_60fps=true']
    if target == 'unlimited':
        return ['--aster_frame_diagnostics=true', '--aster_experimental_unlimited_fps=true']
    return []


def check_mode_report(parser, report, target):
    command = report['command']
    if target == '60' and '--aster_experimental_60fps=true' not in command:
        parser.error('O relatório de referência não é do modo 60 fps experimental.')
    if target == 'unlimited':
        required = ('--aster_experimental_unlimited_fps=true', '--vsync=false',
                    '--vulkan_allow_present_mode_immediate=true')
        if not all(flag in command for flag in required):
            parser.error('O relatório de referência não é do modo ilimitado experimental '
                         'com VSync desligado e apresentação imediata.')
        if report.get('fps_target') != 'unlimited':
            parser.error('O relatório de referência não foi gerado com --fps-target unlimited.')
        try:
            average = (float(report.get('present_calls_observed') or 0) /
                       float(report.get('elapsed_seconds') or 0))
        except (TypeError, ValueError):
            average = 0
        if average <= 60:
            parser.error('O relatório ilimitado não registra apresentação acima de 60 por segundo; '
                         'o modo não foi comprovado.')
    if target == '30' and any(argument.startswith('--aster_experimental_') for argument in command):
        parser.error('O relatório principal não é uma referência de 30 fps.')


def load_report(parser, path):
    try:
        report = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        parser.error(f'Não foi possível ler o relatório de execução {path}: {exc}')
    if not isinstance(report, dict) or not isinstance(report.get('command'), list):
        parser.error('Formato inválido no relatório de execução.')
    if not all(isinstance(argument, str) for argument in report['command']):
        parser.error('Argumentos inválidos no relatório de execução.')
    return report


def validate_installation(parser, root, game, binary, report, target):
    if not game.is_dir():
        parser.error('Informe uma pasta contendo default.xex, em vez de um arquivo.')
    if not (game / 'default.xex').is_file():
        parser.error(f'A pasta selecionada não contém default.xex: {game}')
    if digest(game / 'default.xex') != EXPECTED_XEX:
        parser.error('O default.xex difere da imagem usada nesta compilação. Selecione a pasta do dump testado.')
    if not binary.is_file():
        parser.error(f'Build local ausente: {binary}. Compile o alvo correspondente antes de jogar.')
    if report.get('xex_sha256_after') != EXPECTED_XEX or digest(binary) != report.get('executable_sha256'):
        parser.error('A identidade da compilação mudou; execute novamente o probe limitado antes de abrir o jogo.')
    if report.get('gpu_plugin_sha256'):
        plugin_name = Path(report.get('gpu_plugin_path', '')).name
        plugin = binary.parent / plugin_name
        if not plugin_name or not plugin.is_file() or digest(plugin) != report['gpu_plugin_sha256']:
            parser.error('O plugin gráfico difere do que foi testado; valide o conjunto antes de abrir o jogo.')
    check_mode_report(parser, report, target)
    if report.get('unregistered_targets'):
        parser.error('O probe contém destinos não registrados; corrija o port e gere uma nova referência.')
    if report.get('rendering_errors'):
        parser.error('O probe contém falhas de shaders, pipelines ou dispositivo gráfico; corrija o backend e gere uma nova referência.')
    if ('--render_target_path_vulkan=fsi' not in report['command'] or report.get('fatal_messages')
            or not report.get('xex_loaded_observed') or not report.get('present_calls_observed')):
        parser.error('É necessário um probe FSI desta compilação, com XEX carregado, apresentação observada e sem erros fatais.')
    try:
        dependencies = subprocess.run(['ldd', str(binary)], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        parser.error(f'Não foi possível verificar as bibliotecas locais: {exc}')
    if 'not found' in dependencies.stdout + dependencies.stderr:
        parser.error('Faltam bibliotecas locais de execução:\n' + dependencies.stdout + dependencies.stderr)


def build_command(root, binary, game, run, log, args, target, graphics_data, present_mode):
    command = [str(binary), '--gpu_plugin=xenos', '--render_target_path_vulkan=fsi',
               '--store_shaders=true',
               f'--async_shader_compilation={str(graphics_data["shader_mode"] == "async").lower()}',
               f'--vsync={str(target != "unlimited").lower()}',
               '--allow_game_relative_writes=false',
               f'--game_data_root={game}', f'--user_data_root={run / "user"}',
               f'--cache_root={run / "cache"}', f'--log_file={log}', '--log_level=info']
    command.extend(graphics.cvar_arguments(graphics_data))
    command.extend(session_preferences_arguments(args))
    command.extend(mode_flags(target))
    if present_mode == 'fifo':
        command.extend(['--vulkan_allow_present_mode_immediate=false',
                        '--vulkan_allow_present_mode_mailbox=false',
                        '--vulkan_allow_present_mode_fifo_relaxed=false'])
    elif present_mode == 'mailbox':
        command.extend(['--vulkan_allow_present_mode_immediate=false',
                        '--vulkan_allow_present_mode_mailbox=true',
                        '--vulkan_allow_present_mode_fifo_relaxed=false'])
    elif present_mode == 'immediate':
        command.extend(['--vulkan_allow_present_mode_immediate=true',
                        '--vulkan_allow_present_mode_mailbox=false',
                        '--vulkan_allow_present_mode_fifo_relaxed=false'])
    return command


def session_preferences_arguments(args, game_root=None):
    """Typed CLI preferences become real runtime CVars, never shell fragments.

    Legacy direct CLI calls retain their existing keyboard behavior unless the
    new preferences were explicitly supplied. The launcher always supplies them.
    Availability is checked before a game process is launched, not at editing.
    """
    encoded = getattr(args, 'controls_json', None)
    arguments = []
    if encoded is None:
        arguments.append('--mnk_mode=true')
    else:
        if not isinstance(encoded, str) or len(encoded) > 16384:
            raise PortError('CONTROLS_VALUE', 'Configuração de controles excede o limite de tamanho.')
        try:
            data = json.loads(encoded)
        except (ValueError, TypeError) as exc:
            raise PortError('CONTROLS_VALUE', 'Configuração JSON de controles inválida.') from exc
        arguments.extend(controls.cvar_arguments(data))
    text = getattr(args, 'subtitle_language', None)
    voice = getattr(args, 'voice_language', None)
    if text is not None or voice is not None:
        data = {'subtitle_language': text or 'auto', 'voice_language': voice or 'auto'}
        arguments.extend(languages.cvar_arguments(data, game_root))
    return arguments


def presentation_arguments(data, installation, parser):
    """Use real embedded FSR1 only when the verified build records its SDK ABI."""
    sdk = (installation or {}).get('recipe', {}).get('sdk_spatial')
    preload = []
    if isinstance(sdk, dict) and graphics.SHADER_PRELOAD_PATCH in sdk.get('patches', {}):
        preload = ['--shader_preload='+str(data.get('shader_preload', True)).lower()]
    elif not data.get('shader_preload', True):
        parser.error('A opção de preparação de shaders exige atualizar o backend pelo launcher.')
    if data.get('render_scale', 1) > 1:
        sdk = (installation or {}).get('recipe', {}).get('sdk_spatial')
        if not isinstance(sdk, dict) or graphics.SCALED_PIXEL_CENTER_PATCH not in sdk.get('patches', {}):
            parser.error('Resolução interna 2x/3x exige o backend com a correção de profundidade. '
                         'Use Gerar port/Atualizar port no launcher ou selecione 1x.')
    if not installation or installation.get('presentation_backend') != 'sdk-spatial-fsr1':
        return []
    if not installation.get('recipe', {}).get('sdk_spatial'):
        parser.error('O manifesto não confirma o SDK espacial; gere novamente o port.')
    if data['upscaler'] not in ('bilinear', 'fsr1'):
        parser.error('Este runtime compartilhado Linux/Windows oferece bilinear e FSR 1. Selecione FSR 1 para ampliar a imagem.')
    if data['upscaler'] == 'fsr1':
        return [*preload, '--present_effect=fsr', '--present_fsr_max_upsampling_passes=2',
                f"--present_fsr_sharpness_reduction={2 * (1 - graphics.validate(data)['fsr_sharpness'] / 100):g}"]
    return [*preload, '--present_effect=bilinear']


def hd_texture_environment(directory, installation, env, parser):
    env = dict(env)
    env.pop('ASTER_HD_TEXTURE_PACK_DIR', None)
    if directory:
        patches = (installation or {}).get('recipe', {}).get('sdk_spatial', {}).get('patches', {})
        if '0006-reviewed-hd-texture-override.patch' not in patches:
            parser.error('Texturas HD exigem atualizar o backend nativo no launcher.')
        if (Path(directory) / 'library.json').exists() and '0012-campaign-texture-library.patch' not in patches:
            parser.error('Bibliotecas da campanha exigem atualizar o backend nativo no launcher.')
        if ((Path(directory) / 'pack.json').exists() or (Path(directory) / 'texture-pack.index').exists()) and '0009-multi-material-hd-pack.patch' not in patches:
            parser.error('Pacotes com vários materiais exigem atualizar o backend de texturas HD no launcher.')
        from native_port.texture_pack import validate_texture_pack_cached
        try:
            verified = validate_texture_pack_cached(directory,
                Path(__file__).resolve().parent.parent / '.aster/cache/texture-validation')
            manifests = list(verified.glob('*/manifest.json')) if (verified / 'pack.json').exists() or (verified / 'library.json').exists() else [verified / 'manifest.json']
            if '0011-hd-texture-scales.patch' not in patches and any(
                    json.loads(path.read_text(encoding='utf8')).get('recipe', {}).get('host_scale') == 4 for path in manifests):
                parser.error('Texturas Ultra 4x exigem atualizar o backend nativo no launcher.')
            env['ASTER_HD_TEXTURE_PACK_DIR'] = str(verified)
        except Exception as exc:
            parser.error(str(exc))
    return env


def ui_texture_environment(directory, installation, env, parser):
    """Keep UI coverage atlases separate from opaque materials and inherited env."""
    env = dict(env)
    env.pop('ASTER_UI_TEXTURE_PACK_DIR', None)
    if directory:
        patches = (installation or {}).get('recipe', {}).get('sdk_spatial', {}).get('patches', {})
        if '0016-reviewed-ui-alpha-atlas.patch' not in patches:
            parser.error('Fontes revisadas exigem atualizar o backend nativo no launcher.')
        from native_port.texture_ui import validate_ui_pack
        try:
            env['ASTER_UI_TEXTURE_PACK_DIR'] = str(validate_ui_pack(directory, available_patches=patches))
        except Exception as exc:
            parser.error(str(exc))
    return env


def presentation_environment(binary, data, env, parser, installation=None):
    env = dict(env)
    if installation and installation.get('presentation_backend') == 'sdk-spatial-fsr1':
        # Source-built presentation is inside the actual runtime on both OSes.
        # Do not preload the older Linux ABI compatibility module into it.
        presentation_arguments(data, installation, parser)
        env.pop('ASTER_PRESENT_FILTER', None)
        if os.name != 'nt':
            arena = binary.parent / 'libaster_arena_lifetime.so'
            if not arena.is_file():
                parser.error('O módulo de liberação de arenas está ausente; atualize o port antes de jogar.')
            env['LD_PRELOAD'] = str(arena.resolve())
        print(f"Filtro de saída: {data['upscaler']} (SDK espacial; FSR 1 EASU + RCAS quando selecionado)", flush=True)
        return env
    library = binary.parent / 'libaster_presenter_compat.so'
    if os.name != 'nt' and library.is_file():
        # Applied only to the game, never SDK tools or the Python launcher.
        env['LD_PRELOAD'] = str(library.resolve())
        env['ASTER_PRESENT_FILTER'] = data['upscaler']
        print(f"Filtro de saída: {data['upscaler']} (interno 720p; reconstrução espacial)", flush=True)
    elif data['upscaler'] != 'bilinear':
        parser.error('Este filtro exige o runtime espacial atualizado. Use Gerar port/Atualizar port no launcher.')
    return env


def main():
    parser, args = parse_arguments()
    target = resolve_target(parser, args)
    graphics_data = resolve_graphics(parser, args, target)
    root = Path(__file__).resolve().parent.parent
    binary_rel, report_rel, runtime_rel = mode_paths(target)
    installation = read_install(root)
    update_reason = backend_update_reason(installation)
    if update_reason:
        parser.error(update_reason)
    if graphics_data['upscaler'] == 'fsr1' and (not installation or installation.get('recipe', {}).get('integration', 0) < 6):
        parser.error('FSR 1 EASU exige atualizar o port: use Gerar port/Atualizar port no launcher.')
    if installation:
        report = {'command': [f'--game_data_root={installation["game_root"]}']}
    else:
        report_path = root / report_rel
        report = load_report(parser, report_path)

    game = args.game_root
    if game is None:
        try:
            game = Path(next(a.split('=', 1)[1] for a in report['command']
                             if a.startswith('--game_data_root=')))
        except StopIteration:
            parser.error('O relatório não informa a pasta do jogo; selecione o dump manualmente.')
    try:
        game = game.expanduser().resolve(strict=True)
    except OSError as exc:
        parser.error(f'Pasta do jogo não encontrada: {exc}')
    try:
        session_preferences_arguments(args, game)
    except PortError as exc:
        parser.error(str(exc))

    binary = root / binary_rel
    if installation:
        try:
            verify_install(root, installation)
            if digest(game / 'default.xex') != XEX_SHA256:
                parser.error('O dump não corresponde à revisão compilada.')
        except Exception as exc:
            parser.error(str(exc))
        binary = root / installation['binary']
        print('Port gerado localmente; inicialização e campanha ainda precisam ser verificadas.')
    else:
        validate_installation(parser, root, game, binary, report, target)

    run = root / runtime_rel
    prefix = '' if target == '30' else f'{target}-'
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + f'-{os.getpid()}'
    log = root / '.aster/reports' / f'green-lantern-play-{prefix}{stamp}.log'
    present_mode = resolve_present_mode(args, target, graphics_data['vsync'])
    command = build_command(root, binary, game, run, log, args, target, graphics_data, present_mode)
    command.extend(presentation_arguments(graphics_data, installation, parser))
    if installation and installation['renderer'] == 'd3d12-rov':
        command[command.index('--render_target_path_vulkan=fsi')] = '--render_target_path_d3d12=rov'
        command = [flag for flag in command if not flag.startswith('--vulkan_allow_present_mode_')]
        command.append('--d3d12_allow_variable_refresh_rate_and_tearing=' + str(not graphics_data['vsync']).lower())

    if target == '60':
        print('MODO 60 FPS EXPERIMENTAL: usa o port local e o save compartilhado deste usuário.', flush=True)
        print('O passo de simulação foi medido em par com 30 fps, mas combate, física, animações, áudio e campanha não estão certificados.', flush=True)
        print(f'Perfil compartilhado: {run / "user"}', flush=True)
    elif target == 'unlimited':
        print('MODO ILIMITADO EXPERIMENTAL: remove a espera de pacing, desliga VSync e usa apresentação imediata.', flush=True)
        print('Pode consumir muito mais GPU, apresentar tearing e não garante velocidade correta da simulação.', flush=True)
        print(f'Perfil compartilhado: {run / "user"}', flush=True)
        print('Se o jogo parecer acelerado ou instável, volte para 30 fps.', flush=True)
    print('Compilação experimental local; campanha completa e qualidade do áudio ainda sem validação.', flush=True)
    print(f'Gráficos: {graphics.summary(graphics_data)}', flush=True)
    if installation:
        print(f'Backend instalado: {installation["recipe"]["integration"]} | '
              f'{installation["renderer"]}', flush=True)
    print(f'Próxima sessão: alvo={target} | VSync={"on" if graphics_data["vsync"] else "off"} | '
          f'apresentação={present_mode} | shaders={graphics_data["shader_mode"]}', flush=True)
    if not graphics_data['vsync']:
        print('VSync desligado é experimental: pode aumentar uso da GPU e causar tearing.', flush=True)
    if args.controls_json is not None:
        print('Controles personalizados do launcher aplicados; consulte a aba Controles para ver as associações.', flush=True)
    else:
        print('Enter: Start | Espaço: A | Backspace: B | WASD: stick esquerdo | L: X', flush=True)
        print('Setas: stick direito | P: Y | Q/E: LT/RT | 1/3: LB/RB | F/K: LS/RS | Tab: Back | Shift+setas: direcional', flush=True)
    print(f'Jogo: {game}\nSaves: {run / "user"}\nLog desta sessão: {log}', flush=True)
    env = presentation_environment(binary, graphics_data, external_env(), parser, installation)
    env.pop('ASTER_EFFECTS_DIAGNOSTICS', None)
    env.pop('ASTER_EFFECTS_SOURCE_INDEX', None)
    env = hd_texture_environment(args.hd_texture_pack, installation, env, parser)
    env = ui_texture_environment(args.ui_texture_pack, installation, env, parser)
    if args.dry_run:
        print('Validação concluída. Comando de execução:\n' + shlex.join(command))
        return 0

    if installation and graphics_data['shader_preload']:
        try:
            prepare_game_shaders(game, run, root, Workspace(root / '.aster', root), installation,
                                 emit=lambda event: print(event.get('message', ''), flush=True))
        except (OSError, PortError) as exc:
            parser.error(str(exc))

    session_lock = None
    try:
        run.mkdir(parents=True, exist_ok=True)
        try:
            session_lock = lock_session(run / 'play.lock')
        except BlockingIOError:
            parser.error('Já existe uma sessão aberta por este launcher. Feche o jogo antes de iniciar outra.')
        for name in ['user', 'cache', 'config', 'xdg-cache', 'data']:
            (run / name).mkdir(parents=True, exist_ok=True)
        log.parent.mkdir(parents=True, exist_ok=True)
        for key, name in [('XDG_CONFIG_HOME', 'config'), ('XDG_CACHE_HOME', 'xdg-cache'), ('XDG_DATA_HOME', 'data')]:
            os.environ[key] = str(run / name)
        if resource is not None:
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.chdir(run)
        if os.name == 'nt':
            return subprocess.call(command, env=env)
        os.execve(command[0], command, env)
    except OSError as exc:
        parser.error(f'Não foi possível abrir o jogo: {exc}')
    finally:
        if session_lock is not None:
            os.close(session_lock)


if __name__ == '__main__':
    raise SystemExit(main())
