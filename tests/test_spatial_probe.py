"""The spatial probe must validate the actual runtime before using its SDK ABI."""
import argparse
from contextlib import redirect_stderr
import io
import importlib.util
from pathlib import Path
import sys
import subprocess
import unittest
from unittest.mock import patch

if sys.platform != 'linux':
    raise unittest.SkipTest('Local Linux research runtime probe requires resource limits, /proc and X11.')

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('spatial_probe', ROOT / 'scripts/probe_rex_runtime.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class SpatialProbeTests(unittest.TestCase):
    def setUp(self):
        self.stderr = redirect_stderr(io.StringIO())
        self.stderr.__enter__()
        self.addCleanup(self.stderr.__exit__, None, None, None)

    def installation(self):
        return {'binary': '.aster/native/test/aster_green_lantern',
                'presentation_backend': 'sdk-spatial-fsr1', 'recipe': {'sdk_spatial': {'schema': 2}}}

    def diagnostic_parser(self):
        parser = argparse.ArgumentParser()
        probe.add_graphics_diagnostics(parser)
        return parser

    def test_diagnostic_defaults_preserve_fsi_and_sdk_readback_default(self):
        options = self.diagnostic_parser().parse_args([])
        self.assertEqual(options.fsr_sharpness, probe.graphics.DEFAULT_FSR_SHARPNESS)
        self.assertIsNone(options.antialiasing)
        self.assertEqual(probe.diagnostic_backend_arguments(options), ['--render_target_path_vulkan=fsi'])

    def test_explicit_fbo_and_readback_overrides_are_exact_sdk_cvars(self):
        for toggle, expected in [('on', 'true'), ('off', 'false')]:
            with self.subTest(toggle=toggle):
                options = self.diagnostic_parser().parse_args([
                    '--render-target-path', 'fbo', '--readback-resolve', toggle,
                    '--fsr-sharpness', '0', '--antialiasing', 'none'])
                self.assertEqual(probe.diagnostic_backend_arguments(options), [
                    '--render_target_path_vulkan=fbo', f'--vulkan_readback_resolve={expected}'])
                settings = probe.graphics.from_options(
                    'high', render_scale=2, antialiasing=options.antialiasing,
                    fsr_sharpness=options.fsr_sharpness)
                self.assertEqual(settings['render_scale'], 2)
                self.assertEqual(settings['fsr_sharpness'], 0)
                self.assertEqual(settings['antialiasing'], 'none')
                self.assertIn('--resolution_scale=2', probe.graphics.cvar_arguments(settings))

    def test_axis_diagnostics_preserve_independent_axes_and_reject_partial_input(self):
        for x, y in ((2, 1), (1, 2)):
            options = self.diagnostic_parser().parse_args([
                '--render-scale-x', str(x), '--render-scale-y', str(y)])
            self.assertEqual(probe.diagnostic_backend_arguments(options), [
                '--render_target_path_vulkan=fsi',
                f'--draw_resolution_scale_x={x}', f'--draw_resolution_scale_y={y}'])
        for name in ('--render-scale-x', '--render-scale-y'):
            with self.assertRaises(ValueError):
                probe.diagnostic_backend_arguments(self.diagnostic_parser().parse_args([name, '2']))

    def test_half_pixel_fill_override_is_opt_in(self):
        for value in ('on', 'off'):
            options = self.diagnostic_parser().parse_args(['--resolve-half-pixel-fill', value])
            self.assertEqual(probe.diagnostic_backend_arguments(options)[-1],
                             '--resolve_resolution_scale_fill_half_pixel_offset=' + str(value == 'on').lower())

    def test_scaled_texture_offset_override_uses_shared_backend_flag(self):
        for value in ('on', 'off'):
            options = self.diagnostic_parser().parse_args(['--scaled-texture-offsets', value])
            self.assertEqual(probe.diagnostic_backend_arguments(options)[-1],
                             '--draw_resolution_scaled_texture_offsets=' + str(value == 'on').lower())

    def test_diagnostics_reject_unknown_modes_and_out_of_range_sharpness(self):
        for arguments in ([ '--fsr-sharpness', '-1'], ['--fsr-sharpness', '101'],
                          ['--render-target-path', 'host'], ['--readback-resolve', 'true'],
                          ['--antialiasing', 'invented']):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                self.diagnostic_parser().parse_args(arguments)

    def test_diagnostics_accept_all_supported_antialiasing_modes_and_strength_maximum(self):
        for mode in probe.graphics.ANTIALIASING:
            options = self.diagnostic_parser().parse_args([
                '--antialiasing', mode, '--fsr-sharpness', '100'])
            self.assertEqual(options.antialiasing, mode)
            self.assertEqual(options.fsr_sharpness, 100)

    def test_capture_is_opt_in_and_inherited_capture_is_cleared(self):
        inherited = {'PATH': 'tools', 'ASTER_TEXTURE_CAPTURE_DIR': '/unexpected',
                     'ASTER_TEXTURE_CAPTURE_START_FILE': '/old-marker',
                     'ASTER_EFFECTS_DIAGNOSTICS': '1', 'ASTER_EFFECTS_SOURCE_INDEX': '/unrelated-source'}
        clean = probe.texture_capture_environment(inherited, ROOT / 'attempt')
        self.assertEqual(clean, {'PATH': 'tools'})
        armed = probe.texture_capture_environment(inherited, ROOT / 'attempt', 65, 128)
        self.assertEqual(armed['ASTER_TEXTURE_CAPTURE_DIR'], str(ROOT / 'attempt/textures'))
        self.assertEqual(armed['ASTER_TEXTURE_CAPTURE_MAX_COUNT'], '128')
        self.assertEqual(inherited['ASTER_TEXTURE_CAPTURE_DIR'], '/unexpected')
        with self.assertRaises(ValueError):
            probe.texture_capture_environment({}, ROOT / 'attempt', 65, 257)

    def test_exact_executable_is_verified_before_spatial_use(self):
        installation = self.installation()
        with patch.object(probe, 'read_install', return_value=installation), patch.object(probe, 'verify_install') as verify:
            result = probe.verified_spatial_install(ROOT, ROOT / installation['binary'], argparse.ArgumentParser())
        self.assertIs(result, installation)
        verify.assert_called_once_with(ROOT, installation)

    def test_other_executable_cannot_borrow_verified_spatial_manifest(self):
        with patch.object(probe, 'read_install', return_value=self.installation()), patch.object(probe, 'verify_install') as verify:
            with self.assertRaises(SystemExit) as result:
                probe.verified_spatial_install(ROOT, ROOT / '.aster/build/other/game', argparse.ArgumentParser())
        self.assertEqual(result.exception.code, 2)
        verify.assert_not_called()

    def test_changed_staged_library_aborts_probe(self):
        installation = self.installation()
        with patch.object(probe, 'read_install', return_value=installation), patch.object(probe, 'verify_install', side_effect=ValueError('changed library')):
            with self.assertRaises(SystemExit) as result:
                probe.verified_spatial_install(ROOT, ROOT / installation['binary'], argparse.ArgumentParser())
        self.assertEqual(result.exception.code, 2)

    def test_legacy_or_missing_spatial_manifest_aborts_probe(self):
        for installation in (None, {'presentation_backend': 'linux-spatial-shim'},
                             {'presentation_backend': 'sdk-spatial-fsr1', 'recipe': {}}):
            with self.subTest(installation=installation), patch.object(probe, 'read_install', return_value=installation), patch.object(probe, 'verify_install') as verify:
                with self.assertRaises(SystemExit):
                    probe.verified_spatial_install(ROOT, ROOT / 'game', argparse.ArgumentParser())
                verify.assert_not_called()

    def test_legacy_shim_and_source_sdk_are_rejected_before_launch(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/probe_rex_runtime.py'),
                                 '/missing-game', '--spatial-sdk', '--presenter-compat', '/missing.so'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('older presenter compatibility ABI', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
