import unittest

from native_port import graphics
from native_port.errors import PortError


class GraphicsPresetTests(unittest.TestCase):
    def test_presets_map_to_expected_rendering_values(self):
        expected = {
            'low': (1, True, 1, 'low', False),
            'default': (1, True, 3, 'default', False),
            'high': (2, True, 4, 'high', False),
            'ultra': (3, True, 5, 'ultra', False),
        }
        for name, values in expected.items():
            with self.subTest(preset=name):
                data = graphics.from_options(name, fps_target='30', vsync=True)
                actual = (data['render_scale'], data['msaa_2x'], data['anisotropic'],
                          data['texture_quality'], data['present_dither'])
                self.assertEqual(actual, values)
                self.assertEqual(data['preset'], name)

    def test_explicit_override_switches_to_custom_and_keeps_value(self):
        data = graphics.from_options('ultra', render_scale=1, msaa_2x=False,
                                     anisotropic=1, texture_quality='low',
                                     present_dither=True, fps_target='60', vsync=True)
        self.assertEqual(data['preset'], 'custom')
        self.assertEqual(data['render_scale'], 1)
        self.assertFalse(data['msaa_2x'])
        self.assertTrue(data['present_dither'])
        self.assertEqual(data['fps_target'], '60')

    def test_custom_preset_preserves_current_values(self):
        current = graphics.from_options('high', fps_target='60', vsync=True)
        data = graphics.apply_preset('custom', current)
        self.assertEqual(data['preset'], 'custom')
        self.assertEqual(data['render_scale'], current['render_scale'])
        self.assertEqual(data['texture_quality'], current['texture_quality'])

    def test_internal_resolution_and_texture_limits(self):
        self.assertEqual(graphics.internal_resolution(1), '1280x720')
        self.assertEqual(graphics.internal_resolution(3), '3840x2160')
        self.assertEqual(graphics.texture_limits('ultra'), (768, 1536, 48))

    def test_full_hd_output_is_independent_of_internal_scale(self):
        data = graphics.from_options('default', output_resolution='1920x1080')
        self.assertEqual(data['render_scale'], 1)
        self.assertEqual(data['output_resolution'], '1920x1080')
        self.assertIn('--window_width=1920', graphics.cvar_arguments(data))
        self.assertIn('--window_height=1080', graphics.cvar_arguments(data))
        self.assertEqual(graphics.apply_preset('high', data)['output_resolution'], '1920x1080')
        with self.assertRaises(PortError):
            graphics.from_options(output_resolution='1920x1080 --bad')

    def test_cvar_arguments_are_deterministic_real_flags(self):
        data = graphics.from_options('high', fps_target='30', vsync=True)
        arguments = graphics.cvar_arguments(data)
        self.assertEqual(arguments, [
            '--resolution_scale=2', '--anisotropic_override=4',
            '--texture_cache_memory_limit_soft=512',
            '--texture_cache_memory_limit_hard=1024',
            '--texture_cache_memory_limit_render_to_texture=32',
            '--present_dither=false', '--swap_post_effect=fxaa', '--fullscreen=false'])

    def test_unlimited_always_disables_vsync_without_touching_other_fields(self):
        data = graphics.from_options('low', fps_target='unlimited', vsync=True)
        self.assertFalse(data['vsync'])
        self.assertEqual(data['render_scale'], 1)
        self.assertEqual(data['fps_target'], 'unlimited')

    def test_invalid_values_are_rejected(self):
        for field, value in [('preset', 'cinema'), ('render_scale', 0), ('render_scale', 4),
                             ('render_scale', True), ('anisotropic', -2), ('anisotropic', 6),
                             ('fps_target', '120'), ('texture_quality', 'ultra2'),
                             ('shader_mode', 'instant'), ('vsync', 'off')]:
            with self.subTest(field=field), self.assertRaises(PortError):
                data = graphics.from_options('custom', fps_target='30', vsync=True)
                data[field] = value
                graphics.validate(data)


if __name__ == '__main__':
    unittest.main()


class SpatialFilterTests(unittest.TestCase):
    def test_presets_apply_filter_and_real_internal_resolution(self):
        for preset, expected in [('low','bilinear'),('default','bilinear'),('high','fsr1'),('ultra','fsr1')]:
            data=graphics.from_options(preset, output_resolution='1920x1080')
            self.assertEqual(data['upscaler'], expected)
            self.assertEqual(data['render_scale'], {'low': 1, 'default': 1, 'high': 2, 'ultra': 3}[preset])
            self.assertIn('--window_width=1920', graphics.cvar_arguments(data))
    def test_explicit_filter_is_preserved_and_validated(self):
        data=graphics.from_options('ultra',upscaler='cubic')
        self.assertEqual(data['preset'],'custom')
        self.assertEqual(data['upscaler'],'cubic')
        with self.assertRaises(PortError): graphics.from_options('custom',upscaler='fake')


class WindowsPresetTests(unittest.TestCase):
    def test_windows_and_linux_presets_share_fsr_and_aa(self):
        from unittest.mock import patch
        with patch.object(graphics.sys, 'platform', 'win32'):
            for name in ('high', 'ultra'):
                data = graphics.from_options(name, output_resolution='1920x1080')
                self.assertEqual(data['upscaler'], 'fsr1')
                self.assertEqual(graphics.apply_preset(name)['upscaler'], 'fsr1')
                self.assertEqual(graphics.validate({'preset': name})['upscaler'], 'fsr1')
                self.assertGreaterEqual(data['anisotropic'], 4)

    def test_explicit_unsupported_filter_remains_visible_to_runtime_validation(self):
        from unittest.mock import patch
        with patch.object(graphics.sys, 'platform', 'win32'):
            self.assertEqual(graphics.from_options('high', upscaler='sharp')['upscaler'], 'sharp')


class FsrEasuTests(unittest.TestCase):
    def test_easu_matches_high_preset_and_renders_at_1440p(self):
        data=graphics.from_options('high', upscaler='fsr1', output_resolution='1920x1080')
        self.assertEqual(data['preset'], 'high')
        self.assertEqual(data['upscaler'], 'fsr1')
        self.assertEqual(data['render_scale'], 2)
        self.assertEqual(graphics.apply_preset('custom', data)['upscaler'], 'fsr1')
        self.assertEqual(graphics.validate(data), data)


class AntialiasingTests(unittest.TestCase):
    def test_same_fxaa_policy_on_linux_and_windows(self):
        from unittest.mock import patch
        for platform in ('linux', 'win32'):
            with patch.object(graphics.sys, 'platform', platform):
                for preset in ('low', 'default', 'high', 'ultra'):
                    with self.subTest(platform=platform, preset=preset):
                        data = graphics.from_options(preset)
                        expected = 'none' if preset == 'low' else 'fxaa'
                        self.assertEqual(data['antialiasing'], expected)
                        self.assertIn('--swap_post_effect=' + expected, graphics.cvar_arguments(data))

    def test_antialiasing_is_independent_of_upscaler_and_persists_in_custom(self):
        data = graphics.from_options('high', antialiasing='fxaa_extreme', upscaler='fsr1')
        self.assertEqual(data['preset'], 'custom')
        self.assertEqual(graphics.apply_preset('custom', data)['antialiasing'], 'fxaa_extreme')
        self.assertIn('--swap_post_effect=fxaa_extreme', graphics.cvar_arguments(data))
        self.assertEqual(graphics.from_options('custom', antialiasing='none')['antialiasing'], 'none')
        with self.assertRaises(PortError):
            graphics.from_options('custom', antialiasing='taa')

    def test_old_custom_settings_receive_safe_fxaa_default(self):
        self.assertEqual(graphics.validate({'preset': 'custom'})['antialiasing'], 'fxaa')


class DisplayAndTexturePolicyTests(unittest.TestCase):
    def test_display_preferences_survive_preset_change(self):
        data = graphics.from_options('high', fullscreen=True, fsr_sharpness=90, output_resolution='1920x1080')
        changed = graphics.apply_preset('low', data)
        self.assertTrue(changed['fullscreen'])
        self.assertEqual(changed['fsr_sharpness'], 90)
        self.assertEqual(changed['output_resolution'], '1920x1080')
        self.assertIn('--fullscreen=true', graphics.cvar_arguments(changed))

    def test_invalid_display_fields_are_rejected(self):
        for field, value in [('fullscreen', 'on'), ('fsr_sharpness', -1), ('fsr_sharpness', 101), ('fsr_sharpness', True), ('fsr_sharpness', 2.5)]:
            with self.subTest(field=field, value=value), self.assertRaises(PortError):
                graphics.validate({'preset': 'custom', field: value})

    def test_texture_policy_is_bound_to_quality_presets(self):
        self.assertEqual(graphics.PRESET_LABELS['default'], 'Média')
        for preset in ('low', 'default', 'high', 'ultra'):
            self.assertEqual(graphics.from_options(preset)['texture_quality'], preset)
