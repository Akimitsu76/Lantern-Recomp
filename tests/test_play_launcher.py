import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shlex
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / 'scripts/play_green_lantern.py'
spec = importlib.util.spec_from_file_location('play_green_lantern', SOURCE)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class PlayLauncherTests(unittest.TestCase):
    def test_changed_graphics_plugin_cannot_pass_build_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            game = root / 'game'
            game.mkdir()
            (game / 'default.xex').write_bytes(b'synthetic xex')
            binary = root / launcher.MAIN_BINARY
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'synthetic executable')
            (binary.parent / 'librexgpu-xenosrd.so').write_bytes(b'synthetic plugin')
            report_path = root / '.aster/reports/rexglue-runtime-probe.json'
            report_path.parent.mkdir(parents=True)
            report_path.write_text(json.dumps({
                'command': [f'--game_data_root={game}', '--render_target_path_vulkan=fsi'],
                'xex_sha256_after': launcher.EXPECTED_XEX,
                'executable_sha256': 'a' * 64,
                'gpu_plugin_path': '/tested/librexgpu-xenosrd.so',
                'gpu_plugin_sha256': 'b' * 64,
            }))
            errors = io.StringIO()
            with patch.object(launcher, '__file__', str(root / 'scripts/play_green_lantern.py')), \
                    patch('sys.argv', ['play_green_lantern.py', '--validar']), \
                    patch.object(launcher, 'digest', side_effect=[launcher.EXPECTED_XEX, 'a' * 64, 'c' * 64]), \
                    patch.object(launcher.subprocess, 'run') as run, \
                    contextlib.redirect_stderr(errors), self.assertRaises(SystemExit):
                launcher.main()
            self.assertIn('plugin gráfico difere', errors.getvalue())
            run.assert_not_called()

    def test_shader_and_vsync_options_are_forwarded_without_starting_or_mutating_runtime(self):
        for options, asynchronous, vsync in [([], 'true', 'true'),
                (['--present-mode', 'auto'], 'true', 'true'),
                (['--shader-mode', 'blocking', '--vsync', 'off'], 'false', 'true')]:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as folder:
                root = Path(folder).resolve()
                game = root / 'dump'
                game.mkdir()
                (game / 'default.xex').write_bytes(b'synthetic xex')
                binary = root / '.aster/build/rex-green/aster_green_lantern'
                binary.parent.mkdir(parents=True)
                binary.write_bytes(b'synthetic executable')
                report = root / '.aster/reports/rexglue-runtime-probe.json'
                report.parent.mkdir(parents=True)
                identity = launcher.digest(game / 'default.xex')
                report.write_text(json.dumps({'command': [f'--game_data_root={game}', '--render_target_path_vulkan=fsi'],
                    'xex_sha256_after': identity, 'executable_sha256': launcher.digest(binary),
                    'xex_loaded_observed': True, 'present_calls_observed': 1, 'fatal_messages': []}))
                output = io.StringIO()
                with patch.object(launcher, '__file__', str(root / 'scripts/play_green_lantern.py')), \
                        patch.object(launcher, 'EXPECTED_XEX', identity), \
                        patch('sys.argv', ['play_green_lantern.py', '--dry-run', *options]), \
                        patch.object(launcher.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')), \
                        patch.object(launcher.os, 'execv') as execute, contextlib.redirect_stdout(output):
                    self.assertEqual(launcher.main(), 0)
                arguments = shlex.split(output.getvalue().splitlines()[-1])
                self.assertIn('--store_shaders=true', arguments)
                self.assertIn(f'--async_shader_compilation={asynchronous}', arguments)
                self.assertIn(f'--vsync={vsync}', arguments)
                if '--vsync' in options:
                    self.assertIn('--vulkan_allow_present_mode_immediate=true', arguments)
                elif vsync == 'true' and '--present-mode' not in options:
                    self.assertIn('--vulkan_allow_present_mode_immediate=false', arguments)
                    self.assertIn('--vulkan_allow_present_mode_mailbox=false', arguments)
                    self.assertIn('--vulkan_allow_present_mode_fifo_relaxed=false', arguments)
                else:
                    self.assertFalse(any(x.startswith('--vulkan_allow_present_mode_') for x in arguments))
                self.assertFalse((root / '.aster/runtime').exists())
                execute.assert_not_called()

    def test_experimental_60fps_uses_v9_build_and_shared_user_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            game = root / 'dump'
            game.mkdir()
            (game / 'default.xex').write_bytes(b'synthetic xex')
            binary = root / launcher.EXPERIMENTAL_60_BINARY
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'synthetic 60fps executable')
            plugin = binary.parent / 'librexgpu-xenosrd.so'
            plugin.write_bytes(b'synthetic plugin')
            report = root / launcher.EXPERIMENTAL_60_REPORT
            report.parent.mkdir(parents=True)
            identity = launcher.digest(game / 'default.xex')
            report.write_text(json.dumps({
                'command': [f'--game_data_root={game}', '--render_target_path_vulkan=fsi',
                            '--aster_experimental_60fps=true'],
                'xex_sha256_after': identity,
                'executable_sha256': launcher.digest(binary),
                'gpu_plugin_path': str(plugin),
                'gpu_plugin_sha256': launcher.digest(plugin),
                'xex_loaded_observed': True,
                'present_calls_observed': 1,
                'fatal_messages': [],
            }))
            output = io.StringIO()
            with patch.object(launcher, '__file__', str(root / 'scripts/play_green_lantern.py')), \
                    patch.object(launcher, 'EXPECTED_XEX', identity), \
                    patch('sys.argv', ['play_green_lantern.py', '--dry-run', '--experimental-60fps',
                                       str(game)]), \
                    patch.object(launcher.subprocess, 'run',
                                 return_value=subprocess.CompletedProcess([], 0, '', '')), \
                    patch.object(launcher.os, 'execv') as execute, contextlib.redirect_stdout(output):
                self.assertEqual(launcher.main(), 0)
            arguments = shlex.split(output.getvalue().splitlines()[-1])
            self.assertEqual(arguments[0], str(binary))
            self.assertIn('MODO 60 FPS EXPERIMENTAL', output.getvalue())
            self.assertIn('--aster_experimental_60fps=true', arguments)
            self.assertIn('--aster_frame_diagnostics=true', arguments)
            self.assertIn(f'--user_data_root={root / launcher.EXPERIMENTAL_60_RUNTIME / "user"}', arguments)
            self.assertIn('--render_target_path_vulkan=fsi', arguments)
            self.assertFalse((root / '.aster/runtime').exists())
            execute.assert_not_called()

    def test_fps_modes_share_user_save_and_shader_cache(self):
        roots = [launcher.mode_paths(target)[2] for target in ('30', '60', 'unlimited')]
        self.assertEqual(roots, [launcher.MAIN_RUNTIME] * 3)

    def test_experimental_60fps_rejects_a_non_60fps_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            game = root / 'dump'
            game.mkdir()
            (game / 'default.xex').write_bytes(b'synthetic xex')
            binary = root / launcher.EXPERIMENTAL_60_BINARY
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'synthetic 60fps executable')
            report = root / launcher.EXPERIMENTAL_60_REPORT
            report.parent.mkdir(parents=True)
            identity = launcher.digest(game / 'default.xex')
            report.write_text(json.dumps({
                'command': [f'--game_data_root={game}', '--render_target_path_vulkan=fsi'],
                'xex_sha256_after': identity,
                'executable_sha256': launcher.digest(binary),
                'xex_loaded_observed': True,
                'present_calls_observed': 1,
                'fatal_messages': [],
            }))
            errors = io.StringIO()
            with patch.object(launcher, '__file__', str(root / 'scripts/play_green_lantern.py')), \
                    patch.object(launcher, 'EXPECTED_XEX', identity), \
                    patch('sys.argv', ['play_green_lantern.py', '--validar', '--experimental-60fps',
                                       str(game)]), \
                    contextlib.redirect_stderr(errors), self.assertRaises(SystemExit):
                launcher.main()
            self.assertIn('não é do modo 60 fps', errors.getvalue())

    def _unlimited_install(self, folder, presents=41355, elapsed=90.0):
        root = Path(folder).resolve()
        game = root / 'dump'
        game.mkdir()
        (game / 'default.xex').write_bytes(b'synthetic xex')
        binary = root / launcher.EXPERIMENTAL_UNLIMITED_BINARY
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b'synthetic unlimited executable')
        report = root / launcher.EXPERIMENTAL_UNLIMITED_REPORT
        report.parent.mkdir(parents=True)
        identity = launcher.digest(game / 'default.xex')
        report.write_text(json.dumps({
            'command': [f'--game_data_root={game}', '--render_target_path_vulkan=fsi',
                        '--aster_experimental_unlimited_fps=true', '--vsync=false',
                        '--vulkan_allow_present_mode_immediate=true'],
            'xex_sha256_after': identity,
            'executable_sha256': launcher.digest(binary),
            'xex_loaded_observed': True,
            'present_calls_observed': presents,
            'elapsed_seconds': elapsed,
            'fps_target': 'unlimited',
            'fatal_messages': [],
        }))
        return root, game, binary

    def test_unlimited_uses_v10_and_high_present_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            root, game, binary = self._unlimited_install(folder)
            output = io.StringIO()
            with patch.object(launcher, '__file__', str(root / 'scripts/play_green_lantern.py')), \
                    patch.object(launcher, 'EXPECTED_XEX', launcher.digest(game / 'default.xex')), \
                    patch('sys.argv', ['play_green_lantern.py', '--dry-run', '--fps-target',
                                       'unlimited', str(game)]), \
                    patch.object(launcher.subprocess, 'run',
                                 return_value=subprocess.CompletedProcess([], 0, '', '')), \
                    patch.object(launcher.os, 'execv') as execute, contextlib.redirect_stdout(output):
                self.assertEqual(launcher.main(), 0)
            arguments = shlex.split(output.getvalue().splitlines()[-1])
            self.assertEqual(arguments[0], str(binary))
            self.assertIn('--aster_experimental_unlimited_fps=true', arguments)
            self.assertIn('--vsync=false', arguments)
            self.assertIn('--vulkan_allow_present_mode_immediate=true', arguments)
            self.assertIn(f'--user_data_root={root / launcher.EXPERIMENTAL_UNLIMITED_RUNTIME / "user"}', arguments)
            self.assertIn('MODO ILIMITADO EXPERIMENTAL', output.getvalue())
            self.assertFalse((root / '.aster/runtime').exists())
            execute.assert_not_called()

    def test_unlimited_rejects_slow_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            root, game, _ = self._unlimited_install(folder, presents=100, elapsed=10)
            errors = io.StringIO()
            with patch.object(launcher, '__file__', str(root / 'scripts/play_green_lantern.py')), \
                    patch.object(launcher, 'EXPECTED_XEX', launcher.digest(game / 'default.xex')), \
                    patch('sys.argv', ['play_green_lantern.py', '--validar', '--fps-target',
                                       'unlimited', str(game)]), \
                    contextlib.redirect_stderr(errors), self.assertRaises(SystemExit) as failure:
                launcher.main()
            self.assertEqual(failure.exception.code, 2)
            self.assertIn('acima de 60 por segundo', errors.getvalue())

    def test_unlimited_rejects_conflicting_vsync(self):
        for options in (['--fps-target', 'unlimited', '--vsync', 'on'],
                        ['--fps-target', 'unlimited', '--present-mode', 'fifo']):
            with self.subTest(options=options), contextlib.redirect_stderr(io.StringIO()), \
                    patch('sys.argv', ['play_green_lantern.py', *options]), \
                    self.assertRaises(SystemExit) as failure:
                launcher.main()
            self.assertEqual(failure.exception.code, 2)

    def test_high_preset_maps_to_real_cvars(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            game = root / 'dump'
            game.mkdir()
            (game / 'default.xex').write_bytes(b'synthetic xex')
            binary = root / launcher.MAIN_BINARY
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'synthetic executable')
            (binary.parent / 'libaster_presenter_compat.so').write_bytes(b'synthetic presenter')
            (binary.parent / 'libaster_arena_lifetime.so').write_bytes(b'synthetic arena cleanup')
            report = root / launcher.MAIN_REPORT
            report.parent.mkdir(parents=True)
            identity = launcher.digest(game / 'default.xex')
            report.write_text(json.dumps({
                'command': [f'--game_data_root={game}', '--render_target_path_vulkan=fsi'],
                'xex_sha256_after': identity, 'executable_sha256': launcher.digest(binary),
                'xex_loaded_observed': True, 'present_calls_observed': 1, 'fatal_messages': [],
            }))
            output = io.StringIO()
            with patch.object(launcher, '__file__', str(root / 'scripts/play_green_lantern.py')), \
                    patch.object(launcher, 'EXPECTED_XEX', identity), \
                    patch.object(launcher, 'XEX_SHA256', identity), \
                    patch.object(launcher, 'read_install', return_value={
                        'binary': str(binary.relative_to(root)), 'game_root': str(game),
                        'renderer': 'vulkan-fsi', 'presentation_backend': 'sdk-spatial-fsr1',
                        'recipe': {'integration': launcher.INTEGRATION_VERSION, 'sdk_spatial': {'revision': 'verified',
                                   'patches': {launcher.graphics.SCALED_PIXEL_CENTER_PATCH: 'verified',
                                              '0031-vulkan-fxaa-quality-parity.patch': 'verified',
                                              '0032-refresh-unchanged-surface-size.patch': 'verified',
                                              '0033-retire-present-queue.patch': 'verified',
                                              '0034-bounded-hd-source-cache.patch': 'verified',
                                              '0035-configurable-controls.patch': 'verified',
                                              '0037-native-save-slots.patch': 'verified'}}}}), \
                    patch.object(launcher, 'verify_install'), \
                    patch('sys.argv', ['play_green_lantern.py', '--dry-run', '--graphics-preset',
                                       'high', str(game)]), \
                    patch.object(launcher.subprocess, 'run',
                                 return_value=subprocess.CompletedProcess([], 0, '', '')), \
                    contextlib.redirect_stdout(output):
                self.assertEqual(launcher.main(), 0)
            arguments = shlex.split(output.getvalue().splitlines()[-1])
            self.assertIn('--resolution_scale=2', arguments)
            self.assertIn('--present_effect=fsr', arguments)
            self.assertIn('--present_fsr_sharpness_reduction=1.4', arguments)
            self.assertFalse(any(a.startswith('--native_2x_msaa=') for a in arguments))
            self.assertIn('--anisotropic_override=4', arguments)
            self.assertIn('--texture_cache_memory_limit_hard=1024', arguments)

    def test_legacy_build_cannot_silently_downgrade_requested_internal_scale(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            game = root / 'dump'
            game.mkdir()
            (game / 'default.xex').write_bytes(b'synthetic xex')
            binary = root / launcher.MAIN_BINARY
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'synthetic executable')
            report = root / launcher.MAIN_REPORT
            report.parent.mkdir(parents=True)
            identity = launcher.digest(game / 'default.xex')
            report.write_text(json.dumps({
                'command': [f'--game_data_root={game}', '--render_target_path_vulkan=fsi'],
                'xex_sha256_after': identity, 'executable_sha256': launcher.digest(binary),
                'xex_loaded_observed': True, 'present_calls_observed': 1, 'fatal_messages': [],
            }))
            output = io.StringIO()
            with patch.object(launcher, '__file__', str(root / 'scripts/play_green_lantern.py')), \
                    patch.object(launcher, 'EXPECTED_XEX', identity), \
                    patch('sys.argv', ['play_green_lantern.py', '--dry-run', '--render-scale', '2',
                                       '--msaa', 'on', '--anisotropic', '4',
                                       '--texture-quality', 'high', '--dither', 'on', str(game)]), \
                    patch.object(launcher.subprocess, 'run',
                                 return_value=subprocess.CompletedProcess([], 0, '', '')), \
                    contextlib.redirect_stdout(output):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                    launcher.main()
                self.assertEqual(failure.exception.code, 2)

    def test_antialiasing_cli_reaches_backend_flag(self):
        parser, args = launcher.parse_arguments(['--graphics-preset', 'high',
                                                '--antialiasing', 'fxaa_extreme', 'dummy'])
        data = launcher.resolve_graphics(parser, args, '30')
        self.assertEqual(data['antialiasing'], 'fxaa_extreme')
        self.assertEqual(data['preset'], 'custom')
        self.assertIn('--swap_post_effect=fxaa_extreme', launcher.graphics.cvar_arguments(data))

    def test_shader_and_vsync_reject_unknown_modes(self):
        for options in [['--shader-mode', 'magic'], ['--vsync', 'maybe'], ['--present-mode', 'magic']]:
            with self.subTest(options=options), contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as failure:
                launcher.parse_arguments(options)
            self.assertEqual(failure.exception.code, 2)

    def test_vsync_off_keeps_guest_clock_for_both_capped_targets(self):
        for target in ('30', '60'):
            parser, args = launcher.parse_arguments(['--fps-target', target, '--vsync', 'off'])
            data = launcher.resolve_graphics(parser, args, target)
            present = launcher.resolve_present_mode(args, target, data['vsync'])
            command = launcher.build_command(Path('.'), Path('host'), Path('dump'), Path('profile'),
                                             Path('log'), args, target, data, present)
            self.assertIn('--vsync=true', command)
            self.assertIn('--vulkan_allow_present_mode_immediate=true', command)
            self.assertFalse(data['vsync'])

    def test_missing_guest_function_blocks_validation_even_without_fatal_tag(self):
        from unittest.mock import Mock
        parser = launcher.argparse.ArgumentParser()
        game, binary = Mock(), Mock()
        game.is_dir.return_value = True
        game.__truediv__ = Mock(return_value=game)
        game.is_file.return_value = True
        binary.is_file.return_value = True
        report = {'command': ['--render_target_path_vulkan=fsi'],
                  'xex_sha256_after': launcher.EXPECTED_XEX, 'executable_sha256': 'binary',
                  'fatal_messages': [], 'unregistered_targets': ['0xDEADBEEF'],
                  'xex_loaded_observed': True, 'present_calls_observed': 1}
        errors = io.StringIO()
        with patch.object(launcher, 'digest', side_effect=[launcher.EXPECTED_XEX, 'binary']), \
                patch.object(launcher.subprocess, 'run') as dependencies, \
                contextlib.redirect_stderr(errors), self.assertRaises(SystemExit):
            launcher.validate_installation(parser, Path('.'), game, binary, report, '30')
        dependencies.assert_not_called()
        self.assertIn('destinos não registrados', errors.getvalue())

    def test_renderer_failure_blocks_reference_validation_after_successful_presents(self):
        from unittest.mock import Mock
        parser = launcher.argparse.ArgumentParser()
        game, binary = Mock(), Mock()
        game.is_dir.return_value = True
        game.__truediv__ = Mock(return_value=game)
        game.is_file.return_value = True
        binary.is_file.return_value = True
        report = {'command': ['--render_target_path_vulkan=fsi'],
                  'xex_sha256_after': launcher.EXPECTED_XEX, 'executable_sha256': 'binary',
                  'fatal_messages': [], 'unregistered_targets': [],
                  'rendering_errors': ['vkCreateGraphicsPipelines failed (result=-2)'],
                  'xex_loaded_observed': True, 'present_calls_observed': 1200}
        errors = io.StringIO()
        with patch.object(launcher, 'digest', side_effect=[launcher.EXPECTED_XEX, 'binary']), \
                patch.object(launcher.subprocess, 'run') as dependencies, \
                contextlib.redirect_stderr(errors), self.assertRaises(SystemExit):
            launcher.validate_installation(parser, Path('.'), game, binary, report, '30')
        dependencies.assert_not_called()
        self.assertIn('falhas de shaders', errors.getvalue())

    def test_msaa_off_is_rejected_instead_of_sending_ineffective_flag(self):
        parser, args = launcher.parse_arguments(['--msaa', 'off'])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            launcher.resolve_graphics(parser, args, '30')

    def test_session_lock_prevents_second_session_and_releases_on_close(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'play.lock'
            first = launcher.lock_session(path)
            try:
                self.assertTrue(os.get_inheritable(first))
                with self.assertRaises(BlockingIOError):
                    launcher.lock_session(path)
            finally:
                os.close(first)
            second = launcher.lock_session(path)
            os.close(second)

    def test_hash_reads_files_larger_than_one_block(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'image'
            data = b'local build' * 110000
            path.write_bytes(data)
            self.assertEqual(launcher.digest(path), hashlib.sha256(data).hexdigest())

    def test_malformed_report_produces_clear_error_without_traceback(self):
        for report in [[], {'command': None}, {'command': [7]}]:
            with self.subTest(report=report), tempfile.TemporaryDirectory() as folder:
                root = Path(folder).resolve()
                report_path = root / '.aster/reports/rexglue-runtime-probe.json'
                report_path.parent.mkdir(parents=True)
                report_path.write_text(json.dumps(report))
                errors = io.StringIO()
                with patch.object(launcher, '__file__', str(root / 'scripts/play_green_lantern.py')), \
                        patch('sys.argv', ['play_green_lantern.py', '--validar']), \
                        contextlib.redirect_stderr(errors), self.assertRaises(SystemExit) as failure:
                    launcher.main()
                self.assertEqual(failure.exception.code, 2)
                self.assertIn('relatório de execução', errors.getvalue())
                self.assertNotIn('Traceback', errors.getvalue())


if __name__ == '__main__':
    unittest.main()


class PresentationEnvironmentTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'LD_PRELOAD compatibility shim is Linux-only; shared spatial SDK tests cover both platforms.')
    def test_filter_is_applied_only_to_game_environment(self):
        import argparse
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); library=root/'libaster_presenter_compat.so'; library.write_bytes(b'fixture')
            original={'PATH':'/test'}
            env=launcher.presentation_environment(root/'aster_green_lantern',{'upscaler':'sharp'},original,argparse.ArgumentParser())
            self.assertEqual(original,{'PATH':'/test'})
            self.assertEqual(env['LD_PRELOAD'],str(library))
            self.assertEqual(env['ASTER_PRESENT_FILTER'],'sharp')
    def test_unavailable_filter_never_silently_claims_success(self):
        import argparse
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(SystemExit):
                launcher.presentation_environment(Path(folder)/'game',{'upscaler':'sharp'},{},argparse.ArgumentParser())


class SharedSpatialBackendTests(unittest.TestCase):
    def test_verified_sdk_uses_real_fsr_flow_without_legacy_preload_on_both_platforms(self):
        import argparse
        parser = argparse.ArgumentParser()
        installation = {'presentation_backend': 'sdk-spatial-fsr1',
                        'recipe': {'sdk_spatial': {'revision': 'verified'}}}
        for platform_name in ('posix', 'nt'):
            with self.subTest(platform=platform_name), tempfile.TemporaryDirectory() as folder:
                binary = Path(folder) / 'game'
                # A stale compatibility module must not be loaded into the new ABI.
                (binary.parent / 'libaster_presenter_compat.so').write_bytes(b'old ABI')
                arena = binary.parent / 'libaster_arena_lifetime.so'
                arena.write_bytes(b'ABI-independent arena cleanup')
                with patch.object(launcher.os, 'name', platform_name):
                    flags = launcher.presentation_arguments({'upscaler': 'fsr1'}, installation, parser)
                    env = launcher.presentation_environment(binary, {'upscaler': 'fsr1'}, {}, parser, installation)
                self.assertIn('--present_effect=fsr', flags)
                self.assertIn('--present_fsr_sharpness_reduction=1.4', flags)
                if platform_name == 'posix':
                    self.assertEqual(env['LD_PRELOAD'], str(arena.resolve()))
                else:
                    self.assertNotIn('LD_PRELOAD', env)
                self.assertNotIn('ASTER_PRESENT_FILTER', env)

    def test_sdk_without_abi_recipe_cannot_claim_fsr_capability(self):
        import argparse
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            launcher.presentation_arguments({'upscaler': 'fsr1'},
                {'presentation_backend': 'sdk-spatial-fsr1', 'recipe': {}}, argparse.ArgumentParser())


class SharedDisplayControlsTests(unittest.TestCase):
    def test_scaled_internal_rendering_requires_the_depth_fix_on_both_platforms(self):
        import argparse
        patch_name = launcher.graphics.SCALED_PIXEL_CENTER_PATCH
        for platform_name in ('linux', 'win32'):
            for scale in (2, 3):
                data = launcher.graphics.from_options('custom', render_scale=scale)
                old = {'presentation_backend': 'sdk-spatial-fsr1', 'recipe': {'sdk_spatial': {'patches': {}}}}
                with patch.object(launcher.sys, 'platform', platform_name), \
                        contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    launcher.presentation_arguments(data, old, argparse.ArgumentParser())
                new = {'presentation_backend': 'sdk-spatial-fsr1',
                       'recipe': {'sdk_spatial': {'patches': {patch_name: 'verified'}}}}
                with patch.object(launcher.sys, 'platform', platform_name):
                    self.assertEqual(launcher.presentation_arguments(data, new, argparse.ArgumentParser()),
                                     ['--present_effect=bilinear'])
                    self.assertIn('--resolution_scale='+str(scale), launcher.graphics.cvar_arguments(data))

    def test_fullscreen_and_fsr_sharpness_use_real_shared_runtime_flags(self):
        import argparse
        installation = {'presentation_backend': 'sdk-spatial-fsr1', 'recipe': {'sdk_spatial': {
            'patches': {launcher.graphics.SCALED_PIXEL_CENTER_PATCH: 'verified',
                                              '0031-vulkan-fxaa-quality-parity.patch': 'verified',
                                              '0032-refresh-unchanged-surface-size.patch': 'verified',
                                              '0033-retire-present-queue.patch': 'verified'}}}}
        for strength, reduction in [(0, '2'), (75, '0.5'), (100, '0')]:
            parser, args = launcher.parse_arguments(['--graphics-preset', 'high', '--fullscreen', 'on', '--fsr-sharpness', str(strength)])
            data = launcher.resolve_graphics(parser, args, '30')
            self.assertTrue(data['fullscreen'])
            self.assertIn('--fullscreen=true', launcher.graphics.cvar_arguments(data))
            self.assertIn('--present_fsr_sharpness_reduction=' + reduction, launcher.presentation_arguments(data, installation, parser))
