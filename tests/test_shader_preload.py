import argparse
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

from native_port import graphics, settings
from native_port.errors import PortError

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('play_shader_preload', ROOT/'scripts/play_green_lantern.py')
play=importlib.util.module_from_spec(spec);spec.loader.exec_module(play)


class ShaderPreloadTests(unittest.TestCase):
    def test_startup_preparation_and_new_shader_mode_are_independent_and_persistent(self):
        with tempfile.TemporaryDirectory() as folder:
            data=settings.defaults(folder)
            data['graphics']=graphics.from_options('custom',render_scale=1,texture_quality='ultra',
                shader_preload=False,shader_mode='async',output_resolution='1920x1080')
            settings.save(data,folder)
            saved=settings.load(folder)['graphics']
            self.assertFalse(saved['shader_preload'])
            self.assertEqual(saved['shader_mode'],'async')
            self.assertEqual(saved['texture_quality'],'ultra')
            self.assertEqual(saved['output_resolution'],'1920x1080')
            self.assertFalse(graphics.apply_preset('high',saved)['shader_preload'])

    def test_preparation_maps_to_the_real_backend_flag_only_with_its_capability(self):
        manifest={'presentation_backend':'sdk-spatial-fsr1','recipe':{'sdk_spatial':{'patches':{graphics.SHADER_PRELOAD_PATCH:'verified'}}}}
        for enabled in (False,True):
            data=graphics.from_options('custom',shader_preload=enabled)
            self.assertEqual(play.presentation_arguments(data,manifest,argparse.ArgumentParser()),
                ['--shader_preload='+str(enabled).lower(),'--present_effect=bilinear'])
        legacy={'presentation_backend':'sdk-spatial-fsr1','recipe':{'sdk_spatial':{'patches':{}}}}
        self.assertEqual(play.presentation_arguments(graphics.defaults(),legacy,argparse.ArgumentParser()),
                         ['--present_effect=bilinear'])
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            play.presentation_arguments(graphics.from_options('custom',shader_preload=False),legacy,argparse.ArgumentParser())

    def test_cli_has_separate_switches_and_bad_boolean_preferences_are_rejected(self):
        parser,args=play.parse_arguments(['--shader-preload','off','--shader-mode','async'])
        data=play.resolve_graphics(parser,args,'30')
        self.assertFalse(data['shader_preload'])
        self.assertEqual(data['shader_mode'],'async')
        for bad in ('false',0,None):
            with self.assertRaises(PortError):
                graphics.from_options('custom',shader_preload=bad)

    def test_shared_and_linux_patches_make_the_same_source_changes(self):
        # Line numbers differ because Linux adds the driver-cache/deferred code.
        # The actual added/removed statements must remain identical on Windows.
        def changes(name):
            return [line for line in (ROOT/'integrations/rexglue/patches'/name).read_text().splitlines()
                    if line.startswith(('+','-')) and not line.startswith(('+++','---'))]
        self.assertEqual(changes('0025-known-shader-preload-selection.patch'),
                         changes('0025-linux-known-shader-preload-selection.patch'))


if __name__=='__main__':
    unittest.main()
