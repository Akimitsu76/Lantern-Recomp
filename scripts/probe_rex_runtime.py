#!/usr/bin/env python3
"""Bounded local ReXGlue startup probe; never certifies a playable port."""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import re
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from native_port import graphics
from native_port.runtime_evidence import read_runtime_logs, summarize_runtime_log
from native_port.native_build import read_install, verify_install


SUPPORTED_XEX = "3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1"
CONTROL_KEYS = ('Return', 'space', 'BackSpace', 'Up', 'Down', 'Left', 'Right',
                'w', 'a', 's', 'd', 'q', 'e', 'l', 'p', '1', '3', 'f', 'k', 'Tab',
                'w+space', 'a+space', 's+space', 'd+space', 'q+l', 'e+l')


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stop_probe_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def capture_own_x11_window(pid: int, output: Path) -> dict:
    """Capture only a window whose _NET_WM_PID matches this probe's child."""
    try:
        result = subprocess.run(["xprop", "-root", "_NET_CLIENT_LIST"],
                                capture_output=True, text=True, timeout=2)
        if result.returncode:
            return {"error": result.stderr.strip() or "X11 property query failed"}
        window_ids = re.findall(r"0x[0-9a-fA-F]+", result.stdout)
        if not window_ids:
            # Bare X servers have no EWMH window manager/client list. Enumerate
            # root children, then still require this child's exact PID below.
            x11 = ctypes.CDLL("libX11.so.6")
            x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            x11.XOpenDisplay.restype = ctypes.c_void_p
            x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            x11.XDefaultRootWindow.restype = ctypes.c_ulong
            x11.XQueryTree.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                      ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
                                      ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)),
                                      ctypes.POINTER(ctypes.c_uint)]
            x11.XFree.argtypes = [ctypes.c_void_p]
            x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
            display = x11.XOpenDisplay(None)
            if not display:
                return {"error": "Cannot open X11 display for selected-window lookup"}
            children = ctypes.POINTER(ctypes.c_ulong)()
            try:
                root_return, parent_return = ctypes.c_ulong(), ctypes.c_ulong()
                count = ctypes.c_uint()
                if x11.XQueryTree(display, x11.XDefaultRootWindow(display),
                                  ctypes.byref(root_return), ctypes.byref(parent_return),
                                  ctypes.byref(children), ctypes.byref(count)):
                    window_ids = [hex(children[i]) for i in range(min(count.value, 256))]
            finally:
                if children:
                    x11.XFree(children)
                x11.XCloseDisplay(display)
        for window_id in window_ids:
            prop = subprocess.run(["xprop", "-id", window_id, "_NET_WM_PID"],
                                  capture_output=True, text=True, timeout=2)
            match = re.search(r"=\s*(\d+)\s*$", prop.stdout)
            if not match or int(match.group(1)) != pid:
                continue
            image = subprocess.run(["import", "-silent", "-window", window_id, str(output)],
                                   capture_output=True, text=True, timeout=3)
            if image.returncode == 0 and output.is_file():
                return {"pid": pid, "window_id": window_id, "path": str(output)}
            try:
                from rex_x11_capture import capture_verified_x11_window
                return capture_verified_x11_window(pid, window_id, output)
            except (OSError, ValueError, ImportError, subprocess.TimeoutExpired) as exc:
                fallback_error = str(exc)
            # Screenshot tools can fail on Xwayland while the window is still
            # valid for keyboard input. Keep the verified window identity.
            return {"pid": pid, "window_id": window_id, "path": str(output),
                    "error": "Selected-window capture failed", "returncode": image.returncode,
                    "fallback_error": fallback_error}
        return {"error": "No X11 client window matched the child PID"}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)}


def verified_spatial_install(root, binary, parser):
    """Bind spatial probes to the exact executable and all hashed staged files."""
    try:
        installation = read_install(root)
        if (not installation or installation.get('presentation_backend') != 'sdk-spatial-fsr1'
                or not installation.get('recipe', {}).get('sdk_spatial')):
            parser.error('--spatial-sdk requires a built spatial SDK installation.')
        if (root / installation['binary']).resolve() != binary.resolve():
            parser.error('--spatial-sdk executable differs from the installed manifest.')
        verify_install(root, installation)
    except Exception as exc:
        parser.error(str(exc))
    return installation


def texture_capture_environment(env, attempt, start_at=None, limit=128):
    env = dict(env)
    env.pop('ASTER_UI_TEXTURE_PACK_DIR', None)
    env.pop('ASTER_EFFECTS_DIAGNOSTICS', None)
    env.pop('ASTER_EFFECTS_SOURCE_INDEX', None)
    for key in ('ASTER_TEXTURE_CAPTURE_DIR', 'ASTER_TEXTURE_CAPTURE_START_FILE',
                'ASTER_TEXTURE_CAPTURE_MAX_COUNT', 'ASTER_TEXTURE_CAPTURE_MAX_MIB'):
        env.pop(key, None)
    if start_at is not None:
        if not 1 <= limit <= 256:
            raise ValueError('Capture count must be between 1 and 256')
        env.update(ASTER_TEXTURE_CAPTURE_DIR=str(attempt / 'textures'),
                   ASTER_TEXTURE_CAPTURE_START_FILE=str(attempt / 'texture-capture.armed'),
                   ASTER_TEXTURE_CAPTURE_MAX_COUNT=str(limit), ASTER_TEXTURE_CAPTURE_MAX_MIB='256')
    return env


def diagnostic_backend_arguments(args):
    """Only explicit readback requests change the SDK's readback default."""
    arguments = [f'--render_target_path_vulkan={args.render_target_path}']
    if args.readback_resolve is not None:
        arguments.append(f'--vulkan_readback_resolve={str(args.readback_resolve == "on").lower()}')
    if args.resolve_half_pixel_fill is not None:
        arguments.append('--resolve_resolution_scale_fill_half_pixel_offset=' +
                         str(args.resolve_half_pixel_fill == 'on').lower())
    if args.scaled_texture_offsets is not None:
        arguments.append('--draw_resolution_scaled_texture_offsets=' +
                         str(args.scaled_texture_offsets == 'on').lower())
    axes = (args.render_scale_x, args.render_scale_y)
    if any(value is not None for value in axes):
        if any(value is None for value in axes):
            raise ValueError('Specify both --render-scale-x and --render-scale-y.')
        arguments.extend([f'--draw_resolution_scale_x={axes[0]}',
                          f'--draw_resolution_scale_y={axes[1]}'])
    return arguments


def add_graphics_diagnostics(parser):
    parser.add_argument('--fsr-sharpness', type=int, choices=range(101),
                        default=graphics.DEFAULT_FSR_SHARPNESS, metavar='0..100')
    parser.add_argument('--antialiasing', choices=graphics.ANTIALIASING)
    parser.add_argument('--render-target-path', choices=('fsi', 'fbo'), default='fsi',
                        help='Diagnostic render target backend for this isolated probe.')
    parser.add_argument('--readback-resolve', choices=('on', 'off'),
                        help='Diagnostic resolve readback override; omitted preserves the SDK default.')
    parser.add_argument('--render-scale-x', type=int, choices=(1, 2, 3),
                        help='Diagnostic asymmetric scaling; specify both axes and --render-scale 1.')
    parser.add_argument('--render-scale-y', type=int, choices=(1, 2, 3))
    parser.add_argument('--resolve-half-pixel-fill', choices=('on', 'off'),
                        help='Diagnostic scaled resolve edge-fill override; omitted keeps SDK default.')
    parser.add_argument('--scaled-texture-offsets', choices=('on', 'off'),
                        help='Diagnostic texture offset parity control; requires patch0017.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_root", type=Path)
    parser.add_argument('--finish-human-session', metavar='LABEL',
                        help='Request graceful exit of the identified human session after the player authorizes it.')
    parser.add_argument("--seconds", type=int, default=30, choices=range(1, 901), metavar="1..900")
    parser.add_argument("--label", help="Unique local attempt name (letters, digits, hyphens).")
    parser.add_argument("--capture-window", action="store_true",
                        help="Capture this process's X11 window only, using xprop/ImageMagick.")
    parser.add_argument('--keyboard', action='store_true', help='Enable SDK keyboard controller mapping.')
    parser.add_argument('--human-session', action='store_true',
                        help='Observe a human-controlled session until the player closes the game; no automatic inputs.')
    parser.add_argument('--executable-dir', type=Path, help='Isolated local build directory under .aster/build.')
    parser.add_argument('--runtime-root', type=Path, help='Isolated profile/cache directory under .aster/runtime.')
    parser.add_argument('--vsync', choices=('on', 'off'))
    parser.add_argument('--shader-mode', choices=('async', 'blocking'), default='async')
    parser.add_argument('--shader-preload', choices=('on', 'off'), default='on')
    parser.add_argument('--fps-target', choices=graphics.TARGETS,
                        help='30 (default), 60 or unlimited. The latter two require an isolated hook build.')
    parser.add_argument('--experimental-unlimited-fps', action='store_true',
                        help='Legacy alias for --fps-target unlimited.')
    parser.add_argument('--graphics-preset', choices=graphics.PRESETS,
                        help='Apply a real graphics preset to this isolated probe.')
    parser.add_argument('--upscaler', choices=graphics.UPSCALERS, default=None)
    add_graphics_diagnostics(parser)
    parser.add_argument('--output-resolution', choices=graphics.OUTPUT_RESOLUTIONS, default='auto')
    parser.add_argument('--fullscreen', action='store_true',
                        help='Use the verified game window in fullscreen; windowed sizes can be clamped by desktop decorations.')
    parser.add_argument('--render-scale', type=int, choices=(1, 2, 3))
    parser.add_argument('--msaa', choices=('on', 'off'))
    parser.add_argument('--anisotropic', type=int, choices=tuple(graphics.ANISOTROPIC_LABELS))
    parser.add_argument('--texture-quality', choices=graphics.TEXTURE_QUALITIES)
    parser.add_argument('--dither', choices=('on', 'off'))
    parser.add_argument('--output-report', type=Path,
                        help='Write the reference report here instead of rexglue-runtime-probe.json.')
    parser.add_argument('--gpu-metrics', action='store_true', help='Sample read-only NVIDIA GPU telemetry every five seconds.')
    parser.add_argument('--primary-submit', choices=('on', 'off'), default='on',
                        help='Diagnostic: submit at each primary PM4 buffer end or batch until other required boundaries.')
    parser.add_argument('--gpu-timing', action='store_true',
                        help='Enable opt-in GPU submission timestamps in a diagnostic plugin.')
    parser.add_argument('--frame-diagnostics', action='store_true',
                        help='Observe original guest frame/present functions in a hook-enabled experimental host.')
    parser.add_argument('--experimental-60fps', action='store_true',
                        help='Legacy alias for --fps-target 60; simulation not validated.')
    parser.add_argument('--present-mode', choices=('auto', 'fifo', 'mailbox', 'immediate'), default='auto',
                        help='Diagnostic host swapchain mode; does not change guest vblank/VSync by itself.')
    parser.add_argument('--live-input', action='store_true',
                        help='Accept local, recorded control requests for this bounded probe.')
    parser.add_argument('--audio-check-at', type=float,
                        help='Measure only this process playback streams at the given elapsed seconds.')
    parser.add_argument('--allow-invalid-fetch', action='store_true',
                        help='Test SDK compatibility mode for invalid-type GPU fetch descriptors.')
    parser.add_argument('--capture-textures-at', type=float, help='Arm bounded original texture capture at this elapsed second, before a level loads; diagnostic I/O, not a performance sample.')
    parser.add_argument('--capture-texture-limit', type=int, default=128, choices=range(1,257))
    parser.add_argument('--hd-texture-pack', type=Path, help='Validated local reviewed Real-ESRGAN pack for this probe only.')
    parser.add_argument('--ui-texture-pack', type=Path, help='Validated separate monochrome UI atlas for this probe only.')
    parser.add_argument('--scaled-resolve-diagnostics', action='store_true', help='Bounded metadata-only scale diagnostics; requires SDK patch0015.')
    parser.add_argument('--effects-diagnostics', action='store_true', help='Bounded exact-atlas sampling/transparency metadata; requires patch0018.')
    parser.add_argument('--effects-source-index', type=Path,
                        help='Optional local source index, armed after reviewing uploads from this session; requires patch0019.')
    parser.add_argument('--gpu-trace', action='store_true', help='Bounded texture inspection only; verbose GPU log, not a performance measurement.')
    parser.add_argument('--log-level', choices=('info', 'debug'), default='debug',
                        help='Use info for performance controls matching normal play; debug retains diagnostic detail. GPU trace overrides this.')
    parser.add_argument('--spatial-sdk', action='store_true',
                        help='Use the verified source SDK installation and embedded FSR1 presentation.')
    parser.add_argument('--presenter-compat', type=Path,
                        help='Load the pinned local presenter compatibility library for this child only.')
    parser.add_argument('--press', action='append', default=[], metavar='SECONDS:KEY[:HOLD]',
                        help='Send controller-mapped keys (Return, space, WASD, arrows) to this window only.')
    args = parser.parse_args()
    if args.effects_source_index and not args.effects_diagnostics:
        parser.error('--effects-source-index requires --effects-diagnostics.')
    if args.render_scale_x is not None or args.render_scale_y is not None:
        if args.render_scale != 1:
            parser.error('Axis diagnostics require --render-scale 1 to keep the uniform and per-axis controls unambiguous.')
        try:
            diagnostic_backend_arguments(args)
        except ValueError as exc:
            parser.error(str(exc))
    if args.capture_textures_at is not None and (not args.spatial_sdk or not 0 <= args.capture_textures_at < args.seconds):
        parser.error('Texture capture requires --spatial-sdk and arming time before the deadline.')
    if args.hd_texture_pack and not args.spatial_sdk:
        parser.error('--hd-texture-pack requires --spatial-sdk.')
    if (args.ui_texture_pack or args.scaled_resolve_diagnostics or args.effects_diagnostics or args.scaled_texture_offsets is not None) and not args.spatial_sdk:
        parser.error('UI atlases and scale diagnostics require --spatial-sdk.')
    if args.gpu_trace and args.seconds > 60:
        parser.error('Verbose GPU trace is limited to 60 seconds; use ordinary logs for gameplay probes.')
    if args.spatial_sdk and args.presenter_compat:
        parser.error('--spatial-sdk cannot load the older presenter compatibility ABI.')
    if args.experimental_60fps and args.experimental_unlimited_fps:
        parser.error('Choose either 60 fps or unlimited, not both.')
    if args.fps_target and (
            (args.experimental_60fps and args.fps_target != '60') or
            (args.experimental_unlimited_fps and args.fps_target != 'unlimited')):
        parser.error('FPS target conflicts with a legacy flag.')
    fps_target = args.fps_target or ('60' if args.experimental_60fps else
                                     'unlimited' if args.experimental_unlimited_fps else '30')
    if fps_target == 'unlimited':
        if args.vsync == 'on':
            parser.error('Unlimited requires --vsync off.')
        if args.present_mode in ('fifo', 'mailbox'):
            parser.error('Unlimited requires immediate presentation.')
        args.vsync, args.present_mode = 'off', 'immediate'
    elif args.vsync is None:
        args.vsync = 'on'
    if fps_target != 'unlimited' and args.vsync == 'off' and args.present_mode == 'auto':
        args.present_mode = 'immediate'
    if args.msaa == 'off':
        parser.error('FSI preserves guest MSAA; disabling it is unsupported.')
    args.frame_diagnostics = args.frame_diagnostics or fps_target != '30'
    if args.finish_human_session:
        root = Path(__file__).resolve().parent.parent
        label = args.finish_human_session
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', label):
            parser.error('Invalid session label.')
        attempt = root / '.aster/reports/rex-history' / label
        try:
            session = json.loads((attempt / 'session.json').read_text())
            if not session.get('human_session') or (attempt / 'report.json').exists():
                parser.error('Human session is not active.')
            pid = session['pid']
            proc = Path(f'/proc/{pid}')
            binary = root / '.aster/build/rex-green/aster_green_lantern'
            if proc.joinpath('exe').resolve(strict=True) != binary.resolve(strict=True):
                parser.error('Process executable does not match this game session.')
            if proc.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19] != session['proc_start_ticks']:
                parser.error('Process identity changed.')
            os.kill(pid, signal.SIGTERM)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.error(str(exc))
        print('Graceful exit requested for the identified game process.')
        return 0
    if args.human_session and (args.press or args.live_input or args.audio_check_at is not None):
        parser.error('--human-session does not accept automated input or audio recording.')
    actions = []
    for spec in args.press:
        try:
            parts = spec.split(':')
            assert len(parts) in (2, 3)
            at, key = parts[:2]
            hold = float(parts[2]) if len(parts) == 3 else 0.18
            at = float(at)
            assert 0 <= at < args.seconds and 0.01 <= hold <= 3 and at + hold < args.seconds and key in CONTROL_KEYS
        except (ValueError, AssertionError):
            parser.error('Invalid --press action.')
        actions.append((at, key, hold))
    if actions and not args.keyboard:
        parser.error('--press requires --keyboard.')
    if args.live_input and not args.keyboard:
        parser.error('--live-input requires --keyboard.')
    if args.audio_check_at is not None and not 0 <= args.audio_check_at < args.seconds - 35:
        parser.error('--audio-check-at must leave 35 seconds before the deadline.')
    actions.sort()
    root = Path(__file__).resolve().parent.parent
    if args.frame_diagnostics or fps_target != '30':
        if not args.executable_dir or not args.runtime_root:
            parser.error('Frame experiments require isolated executable and runtime directories.')
        if (args.executable_dir.resolve() == (root / '.aster/build/rex-green').resolve() or
                args.runtime_root.resolve() == (root / '.aster/runtime/green-lantern').resolve()):
            parser.error('Frame experiments cannot use the main executable or human profile.')
    game = args.game_root.resolve(strict=True)
    xex = game / "default.xex"
    before = sha256(xex)
    if before != SUPPORTED_XEX:
        parser.error("XEX hash differs from the image used for this build.")
    binary = root / ".aster/build/rex-green/aster_green_lantern"
    if args.executable_dir:
        directory = args.executable_dir.resolve(strict=True)
        if not any(directory.is_relative_to((root / allowed).resolve())
                   for allowed in ('.aster/build', '.aster/native')):
            parser.error('Experimental executable must be under .aster/build or .aster/native.')
        binary = directory / 'aster_green_lantern'
    if not binary.is_file():
        parser.error("Build the local ReXGlue host first.")
    installation = verified_spatial_install(root, binary, parser) if args.spatial_sdk else None
    if args.scaled_resolve_diagnostics:
        if '0015-scaled-resolve-diagnostics.patch' not in installation.get('recipe', {}).get('sdk_spatial', {}).get('patches', {}):
            parser.error('Rebuild the SDK with patch0015 before requesting scale diagnostics.')
    if args.effects_diagnostics:
        if '0018-effects-sampling-diagnostics.patch' not in installation.get('recipe', {}).get('sdk_spatial', {}).get('patches', {}):
            parser.error('Rebuild the SDK with patch0018 before requesting effects diagnostics.')
    for requested, patch_name in ((args.effects_source_index, '0019-armed-effects-source-index.patch'),
                                  (args.scaled_texture_offsets is not None, '0017-scaled-texture-offset-flag-parity.patch')):
        if requested and patch_name not in installation.get('recipe', {}).get('sdk_spatial', {}).get('patches', {}):
            parser.error('Rebuild the SDK with ' + patch_name + ' before requesting this diagnostic.')
    if args.capture_textures_at is not None and '0010-gameplay-texture-capture-arm.patch' not in installation.get('recipe', {}).get('sdk_spatial', {}).get('patches', {}):
        parser.error('Rebuild the native runtime with the bounded capture arming patch before using this option.')
    # Check staging before attempting to create a window.
    libraries = subprocess.run(["ldd", str(binary)], capture_output=True, text=True, check=True)
    if "not found" in libraries.stdout:
        parser.error("Missing shared libraries:\n" + libraries.stdout)
    run = root / ".aster/runtime/green-lantern"
    if args.runtime_root:
        run = args.runtime_root.resolve()
        if not run.is_relative_to((root / '.aster/runtime').resolve()):
            parser.error('Experimental runtime must be under .aster/runtime.')
    reports = root / ".aster/reports"
    reports.mkdir(parents=True, exist_ok=True)
    run.mkdir(parents=True, exist_ok=True)
    from play_green_lantern import lock_session
    try:
        session_lock = lock_session(run / 'play.lock')
    except BlockingIOError:
        parser.error('Já existe uma sessão do jogo ou um probe usando estes saves.')
    label = args.label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f"-{os.getpid()}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", label):
        parser.error("Invalid attempt label.")
    attempt = reports / "rex-history" / label
    try:
        attempt.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error("Attempt label already exists; evidence will not be overwritten.")
    env = texture_capture_environment(os.environ, attempt, args.capture_textures_at, args.capture_texture_limit)
    capture_armed = False
    if args.presenter_compat:
        compatibility = args.presenter_compat.resolve(strict=True)
        if not any(compatibility.is_relative_to((root / allowed).resolve()) for allowed in ('.aster/build', '.aster/native')) or compatibility.suffix != '.so':
            parser.error('Compatibility library must be a local .aster/build or .aster/native shared library.')
        env['LD_PRELOAD'] = str(compatibility)
        if args.upscaler:
            env['ASTER_PRESENT_FILTER'] = args.upscaler
    for key, name in (("XDG_CONFIG_HOME", "config"), ("XDG_CACHE_HOME", "xdg-cache"),
                      ("XDG_DATA_HOME", "data")):
        directory = run / name
        directory.mkdir(exist_ok=True)
        env[key] = str(directory)
    command = [str(binary), "--gpu_plugin=xenos", *diagnostic_backend_arguments(args),
               f"--game_data_root={game}",
               f"--user_data_root={run / 'user'}", f"--cache_root={run / 'cache'}",
               f"--log_file={attempt / 'runtime.log'}", "--log_level=trace" if args.gpu_trace else f"--log_level={args.log_level}",
               "--allow_game_relative_writes=false"]
    command.extend(['--store_shaders=true', f'--async_shader_compilation={str(args.shader_mode == "async").lower()}',
                    f'--vsync={str(args.vsync == "on").lower()}'])
    command.append(f'--vulkan_submit_on_primary_buffer_end={str(args.primary_submit == "on").lower()}')
    if args.gpu_timing:
        command.append('--vulkan_submission_timing=true')
    if args.scaled_resolve_diagnostics:
        command.append('--aster_scaled_resolve_diagnostics=true')
    if args.frame_diagnostics:
        command.append('--aster_frame_diagnostics=true')
    if fps_target == '60':
        command.append('--aster_experimental_60fps=true')
    elif fps_target == 'unlimited':
        command.append('--aster_experimental_unlimited_fps=true')
    graphics_data = None
    if (args.spatial_sdk or args.graphics_preset or args.upscaler or args.render_scale is not None or args.msaa is not None or
            args.anisotropic is not None or args.texture_quality is not None or args.dither is not None or
            args.antialiasing is not None or args.fsr_sharpness != graphics.DEFAULT_FSR_SHARPNESS):
        try:
            graphics_data = graphics.from_options(
                args.graphics_preset or 'default',
                render_scale=args.render_scale,
                msaa_2x=None if args.msaa is None else args.msaa == 'on',
                anisotropic=args.anisotropic,
                texture_quality=args.texture_quality,
                present_dither=None if args.dither is None else args.dither == 'on',
                fps_target=fps_target, vsync=args.vsync == 'on', shader_mode=args.shader_mode,
                shader_preload=args.shader_preload == 'on', fullscreen=args.fullscreen,
                upscaler=args.upscaler or env.get('ASTER_PRESENT_FILTER'), output_resolution=args.output_resolution,
                antialiasing=args.antialiasing, fsr_sharpness=args.fsr_sharpness)
        except Exception as exc:
            parser.error(str(exc))
        command.extend(graphics.cvar_arguments(graphics_data))
    if args.spatial_sdk:
        from play_green_lantern import presentation_arguments, presentation_environment
        command.extend(presentation_arguments(graphics_data, installation, parser))
        env = presentation_environment(binary, graphics_data, env, parser, installation)
        from play_green_lantern import hd_texture_environment, ui_texture_environment
        env = hd_texture_environment(args.hd_texture_pack, installation, env, parser)
        env = ui_texture_environment(args.ui_texture_pack, installation, env, parser)
        if args.effects_diagnostics:
            env['ASTER_EFFECTS_DIAGNOSTICS'] = '1'
            if args.effects_source_index:
                env['ASTER_EFFECTS_SOURCE_INDEX'] = str(args.effects_source_index.resolve())
    if args.present_mode != 'auto':
        command.extend([
            f'--vulkan_allow_present_mode_immediate={str(args.present_mode == "immediate").lower()}',
            f'--vulkan_allow_present_mode_mailbox={str(args.present_mode == "mailbox").lower()}',
            '--vulkan_allow_present_mode_fifo_relaxed=false'])
    if args.keyboard:
        command.append('--mnk_mode=true')
    if args.allow_invalid_fetch:
        command.append('--gpu_allow_invalid_fetch_constants=true')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    start = time.monotonic()
    timed_out = False
    interrupted = False
    operator_stop = False
    captures = []
    next_capture = 0.8
    next_status = 0.0
    capture_total = 0
    input_results = []
    control_offset = 0
    audio_check = None
    gpu_metrics = []
    next_gpu_sample = 0.0
    stdout = attempt / "stdout.log"
    with stdout.open("w") as log:
        process = subprocess.Popen(command, cwd=run, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            (attempt / 'session.json').write_text(json.dumps({
                'pid': process.pid, 'executable': str(binary),
                'proc_start_ticks': Path(f'/proc/{process.pid}/stat').read_text().rsplit(')', 1)[1].split()[19],
                'command': command, 'attempt': label,
                'live_input': args.live_input,
                'human_session': args.human_session,
            }, indent=2) + '\n')
            deadline = None if args.human_session else start + args.seconds
            print(f'Sessão {label} aberta. PID {process.pid}. ' +
                  ('Você controla o jogo; feche a janela para concluir a coleta.' if args.human_session else
                   f'Limite: {args.seconds} segundos.'), flush=True)
            while process.poll() is None:
                now = time.monotonic()
                if deadline is not None and now >= deadline:
                    raise subprocess.TimeoutExpired(command, args.seconds)
                if args.capture_textures_at is not None and not capture_armed and now - start >= args.capture_textures_at:
                    marker = attempt / 'texture-capture.armed'
                    with marker.open('x') as armed:
                        armed.write(str(round(now - start, 3)))
                    capture_armed = True
                if args.gpu_metrics and now - start >= next_gpu_sample:
                    try:
                        sample = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,power.draw,clocks.current.graphics,memory.used',
                                                 '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=3)
                        gpu_metrics.append({'elapsed_seconds': round(now - start, 2), 'returncode': sample.returncode,
                                            'csv': sample.stdout.strip(), 'error': sample.stderr.strip()})
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        gpu_metrics.append({'elapsed_seconds': round(now - start, 2), 'error': str(exc)})
                    next_gpu_sample = time.monotonic() - start + 5
                    now = time.monotonic()
                if args.human_session and now - start >= next_status:
                    status = {'attempt': label, 'pid': process.pid, 'state': 'running',
                              'elapsed_seconds': round(now - start, 2), 'human_session': True,
                              'automatic_input': False, 'capture_total': capture_total,
                              'last_capture': captures[-1] if captures else None}
                    temp_status = attempt / 'status.tmp'
                    temp_status.write_text(json.dumps(status, indent=2) + '\n')
                    temp_status.replace(attempt / 'status.json')
                    next_status = now - start + 5
                if args.audio_check_at is not None and audio_check is None and now - start >= args.audio_check_at:
                    try:
                        check = subprocess.run([sys.executable, str(root / 'scripts/probe_game_audio.py'), label],
                                               capture_output=True, text=True, timeout=35)
                        audio_check = {'returncode': check.returncode, 'stdout': check.stdout, 'stderr': check.stderr}
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        audio_check = {'error': str(exc)}
                    now = time.monotonic()
                queue = attempt / 'control.jsonl'
                if args.live_input and queue.exists():
                    with queue.open() as requests:
                        requests.seek(control_offset)
                        line = requests.readline(4096)
                        if line.endswith('\n'):
                            control_offset = requests.tell()
                        else:
                            line = ''
                    if line:
                        result = {'elapsed_seconds': round(now - start, 2)}
                        try:
                            request = json.loads(line)
                            result['request'] = request
                            if request.get('stop') is True:
                                operator_stop = True
                            else:
                                key = request.get('key')
                                hold = float(request.get('hold', 0.18))
                                if key is not None and (key not in CONTROL_KEYS or not 0.01 <= hold <= 3):
                                    raise ValueError('Invalid control key or hold.')
                                lookup = capture_own_x11_window(process.pid, attempt / f'live-{control_offset}.png')
                                result['capture'] = lookup
                                if key is not None:
                                    if 'window_id' not in lookup:
                                        raise ValueError('Probe window unavailable.')
                                    from rex_x11_input import send_window_key
                                    result['input'] = send_window_key(process.pid, lookup['window_id'], key, hold)
                        except (ValueError, TypeError, AttributeError) as exc:
                            result['error'] = str(exc)
                        with (attempt / 'live-results.jsonl').open('a') as results:
                            results.write(json.dumps(result) + '\n')
                        if operator_stop:
                            break
                while actions and now - start >= actions[0][0]:
                    at, key, hold = actions.pop(0)
                    lookup = capture_own_x11_window(process.pid, attempt / f'input-before-{len(input_results)}.png')
                    if 'window_id' in lookup and process.poll() is None:
                        from rex_x11_input import send_window_key
                        result = send_window_key(process.pid, lookup['window_id'], key, hold)
                    else:
                        result = {'key': key, 'error': 'Probe window unavailable'}
                    input_results.append({'scheduled_seconds': at, **result})
                    next_capture = min(next_capture, now - start + 0.5)
                if args.capture_window and now - start >= next_capture:
                    capture_total += 1
                    captures.append(capture_own_x11_window(
                        process.pid, attempt / f"window-{capture_total}.png"))
                    if args.human_session and len(captures) > 120:
                        previous = captures.pop(0)
                        if previous.get('path'):
                            Path(previous['path']).unlink(missing_ok=True)
                    next_capture = now - start + (15 if args.human_session else 2 if next_capture < 5 else 5)
                try:
                    process.wait(timeout=0.2 if deadline is None else min(0.2, max(0.01, deadline - time.monotonic())))
                except subprocess.TimeoutExpired:
                    continue
        except subprocess.TimeoutExpired:
            timed_out = True
        except KeyboardInterrupt:
            interrupted = True
        finally:
            stop_probe_process(process)
    after = sha256(xex)
    runtime_log = attempt / "runtime.log"
    log_text, log_files = read_runtime_logs(attempt)
    plugin_match = re.search(r"GPU plugin 'xenos' loaded \(([^)]+)\)", log_text)
    loaded_plugin = binary.parent / plugin_match.group(1) if plugin_match else None
    report = {**summarize_runtime_log(log_text), "command": command, "exit_code": process.returncode,
              "timeout": timed_out, "elapsed_seconds": round(time.monotonic() - start, 2),
              "xex_sha256_before": before, "xex_sha256_after": after,
              "executable_sha256": sha256(binary), "stdout_log": str(stdout),
              "runtime_log": str(runtime_log), "attempt": label,
              "window_captures": captures,
              "input_actions": input_results,
              "human_session": args.human_session,
              "capture_total": capture_total,
              "gpu_metrics_global": gpu_metrics,
              "gpu_plugin_path": str(loaded_plugin) if loaded_plugin else None,
              "gpu_plugin_sha256": sha256(loaded_plugin) if loaded_plugin and loaded_plugin.exists() else None,
              "runtime_root": str(run),
              "fps_target": fps_target,
              "diagnostic_draw_scale_axes": ([args.render_scale_x, args.render_scale_y]
                                             if args.render_scale_x is not None else None),
              "render_target_path": args.render_target_path,
              "readback_resolve": args.readback_resolve,
              "resolve_half_pixel_fill": args.resolve_half_pixel_fill,
              "fsr_sharpness": args.fsr_sharpness,
              "antialiasing": graphics_data['antialiasing'] if graphics_data else None,
              "graphics": graphics_data,
              "hd_pack_directory": env.get("ASTER_HD_TEXTURE_PACK_DIR"),
              "ui_pack_directory": env.get("ASTER_UI_TEXTURE_PACK_DIR"),
              "scaled_resolve_diagnostics": args.scaled_resolve_diagnostics,
              "effects_diagnostics": args.effects_diagnostics,
              "effects_source_index": str(args.effects_source_index.resolve()) if args.effects_source_index else None,
              "scaled_texture_offsets": args.scaled_texture_offsets,
              "hd_host_resources_created": log_text.count("Created reviewed HD host resource") if args.gpu_trace else None,
              "verbose_gpu_trace": args.gpu_trace,
              "texture_capture_at": args.capture_textures_at,
              "texture_capture_armed": capture_armed,
              "texture_capture_directory": env.get("ASTER_TEXTURE_CAPTURE_DIR"),
              "capture_diagnostic_not_performance": args.capture_textures_at is not None,
              "presentation_backend": installation.get("presentation_backend") if installation else None,
              "child_ld_preload": env.get("LD_PRELOAD"),
              "presenter_filter_environment": env.get("ASTER_PRESENT_FILTER", "bilinear"),
              "presenter_compat_path": str(compatibility) if args.presenter_compat else None,
              "presenter_compat_sha256": sha256(compatibility) if args.presenter_compat else None,
              "audio_check": audio_check,
              "live_results": str(attempt / 'live-results.jsonl') if args.live_input else None,
              "retained_log_files": log_files,
              "stop_reason": "operator_stop" if operator_stop else "interrupted" if interrupted else "probe_deadline" if timed_out else "process_exit"}
    encoded = json.dumps(report, indent=2) + "\n"
    (attempt / "report.json").write_text(encoded)
    if args.human_session:
        (attempt / 'status.json').write_text(json.dumps({
            'attempt': label, 'pid': process.pid, 'state': 'ended',
            'exit_code': process.returncode, 'report': str(attempt / 'report.json'),
            'human_session': True, 'elapsed_seconds': report['elapsed_seconds'],
        }, indent=2) + '\n')
        (reports / 'human-session-latest.json').write_text(encoded)
        print(encoded)
        os.close(session_lock)
        if after != before:
            raise RuntimeError('Original XEX changed during the session.')
        return 0 if process.returncode == 0 and not interrupted else 1
    default_report = reports / "rexglue-runtime-probe.json"
    if args.output_report:
        output_report = args.output_report.expanduser().resolve()
        output_report.parent.mkdir(parents=True, exist_ok=True)
        output_report.write_text(encoded)
    else:
        output_report = default_report
        output_report.write_text(encoded)
    if output_report == default_report:
        shutil.copyfile(stdout, reports / "rexglue-runtime-stdout.log")
        if runtime_log.exists():
            (reports / "rexglue-runtime.log").write_text(log_text, errors="replace")
    print(json.dumps(report, indent=2))
    print(stdout.read_text(errors="replace")[-9000:])
    if after != before:
        raise RuntimeError("Original XEX changed during the probe.")
    os.close(session_lock)
    return 0 if process.returncode == 0 and not timed_out and not interrupted else 1


if __name__ == "__main__":
    raise SystemExit(main())
