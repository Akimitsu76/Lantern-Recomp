"""UI atlases must be verified separately and never enabled by inherited env."""
import argparse
from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import play_green_lantern as play
from native_port import graphics


class UILaunchTests(unittest.TestCase):
    def test_inherited_ui_pack_is_removed_without_touching_other_environment(self):
        original = {'ASTER_UI_TEXTURE_PACK_DIR': 'unverified', 'OTHER': 'keep'}
        result = play.ui_texture_environment(None, None, original, argparse.ArgumentParser())
        self.assertEqual(result, {'OTHER': 'keep'})
        self.assertIn('ASTER_UI_TEXTURE_PACK_DIR', original)

    def test_ui_pack_requires_exact_backend_capability(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            play.ui_texture_environment(Path('test-font'), {'recipe': {}}, {}, argparse.ArgumentParser())

    def test_only_validated_ui_path_reaches_the_child(self):
        installation = {'recipe': {'sdk_spatial': {'patches': {'0016-reviewed-ui-alpha-atlas.patch': 'verified'}}}}
        verified = Path('reviewed-font').resolve()
        with patch('native_port.texture_ui.validate_ui_pack', return_value=verified) as validate:
            result = play.ui_texture_environment(Path('input'), installation, {}, argparse.ArgumentParser())
        validate.assert_called_once_with(Path('input'), available_patches=installation['recipe']['sdk_spatial']['patches'])
        self.assertEqual(result['ASTER_UI_TEXTURE_PACK_DIR'], str(verified))

    def test_balanced_default_does_not_discard_an_explicit_sharpness(self):
        parser, args = play.parse_arguments(['--graphics-preset', 'high'])
        data = play.resolve_graphics(parser, args, '30')
        self.assertEqual(data['fsr_sharpness'], 30)
        self.assertEqual(graphics.validate({'preset': 'high', 'fsr_sharpness': 75})['fsr_sharpness'], 75)
        parser, args = play.parse_arguments(['--graphics-preset', 'high', '--fsr-sharpness', '90'])
        self.assertEqual(play.resolve_graphics(parser, args, '30')['fsr_sharpness'], 90)
