"""A launcher update must not quietly keep the old eroding Vulkan FXAA backend."""
import unittest
import contextlib
import importlib.util
import io
from pathlib import Path
from unittest.mock import patch
from native_port.launcher import Launcher
from native_port.native_build import INTEGRATION_VERSION, backend_update_reason


def current_manifest(renderer):
    return {'recipe': {'integration': INTEGRATION_VERSION, 'sdk_spatial': {'patches': {
        '0031-vulkan-fxaa-quality-parity.patch': 'verified',
        '0032-refresh-unchanged-surface-size.patch': 'verified',
        '0033-retire-present-queue.patch': 'verified',
        '0034-bounded-hd-source-cache.patch': 'verified'}}},
        'renderer': renderer, 'presentation_backend': 'sdk-spatial-fsr1'}


class QualityUpdateTests(unittest.TestCase):
    def test_integration20_requires_regeneration_in_the_updated_launcher(self):
        # No Tk root/process/driver is required to exercise the launch gate.
        launcher = object.__new__(Launcher)
        manifest = {'recipe': {'integration': 20}, 'presentation_backend': 'sdk-spatial-fsr1'}
        with patch('native_port.launcher.read_install', return_value=manifest):
            self.assertTrue(launcher._backend_update_needed())
        manifest = current_manifest('vulkan-fsi')
        with patch('native_port.launcher.read_install', return_value=manifest):
            self.assertFalse(launcher._backend_update_needed())

    def test_missing_fix_requires_update_on_both_platforms(self):
        for renderer in ('vulkan-fsi', 'd3d12-rov'):
            with self.subTest(renderer=renderer):
                manifest = current_manifest(renderer)
                self.assertFalse(backend_update_reason(manifest))
                del manifest['recipe']['sdk_spatial']['patches']['0032-refresh-unchanged-surface-size.patch']
                self.assertIn('correções', backend_update_reason(manifest))

    def test_backend21_cannot_silently_keep_the_old_swapchain_retirement(self):
        for renderer in ('vulkan-fsi', 'd3d12-rov'):
            manifest = current_manifest(renderer)
            manifest['recipe']['integration'] = 21
            self.assertIn('Backend 21 instalado', backend_update_reason(manifest))
        manifest = current_manifest('vulkan-fsi')
        del manifest['recipe']['sdk_spatial']['patches']['0033-retire-present-queue.patch']
        self.assertIn('correções', backend_update_reason(manifest))

    def test_missing_hd_source_retention_requires_new_shared_backend(self):
        for renderer in ('vulkan-fsi', 'd3d12-rov'):
            manifest = current_manifest(renderer)
            del manifest['recipe']['sdk_spatial']['patches']['0034-bounded-hd-source-cache.patch']
            self.assertIn('correções', backend_update_reason(manifest))

    def test_vulkan_quality_filter_required_but_d3d12_uses_existing_quality_shader(self):
        manifest = current_manifest('vulkan-fsi')
        del manifest['recipe']['sdk_spatial']['patches']['0031-vulkan-fxaa-quality-parity.patch']
        self.assertTrue(backend_update_reason(manifest))
        manifest['renderer'] = 'd3d12-rov'
        self.assertFalse(backend_update_reason(manifest))

    def test_direct_play_rejects_stale_backend_before_process_or_save_access(self):
        source = Path(__file__).resolve().parents[1] / 'scripts/play_green_lantern.py'
        spec = importlib.util.spec_from_file_location('play_quality_gate', source)
        play = importlib.util.module_from_spec(spec); spec.loader.exec_module(play)
        for renderer in ('vulkan-fsi', 'd3d12-rov'):
            manifest = current_manifest(renderer); manifest['recipe']['integration'] = 20
            errors = io.StringIO()
            with self.subTest(renderer=renderer), patch('sys.argv', ['play_green_lantern.py', '--dry-run']), \
                    patch.object(play, 'read_install', return_value=manifest), \
                    patch.object(play.subprocess, 'run') as run, \
                    patch.object(play, 'lock_session') as lock, contextlib.redirect_stderr(errors), \
                    self.assertRaises(SystemExit):
                play.main()
            self.assertIn('Backend 20 instalado', errors.getvalue())
            run.assert_not_called(); lock.assert_not_called()
