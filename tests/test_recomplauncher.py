"""Contract tests for RecompLauncher level 1 and level 2 support."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from native_port.play_entry import dispatch  # noqa: E402
from scripts import package_launcher  # noqa: E402
from scripts import play_green_lantern  # noqa: E402


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / 'recomplauncher.json').read_text(encoding='utf8'))

    def test_level_one_setup_and_start(self):
        self.assertEqual(self.manifest['format'], 1)
        self.assertEqual(self.manifest['repo'], 'Akimitsu76/Lantern-Recomp')
        game = next(item for item in self.manifest['inputs'] if item['id'] == 'game')
        self.assertIn({'type': 'folder'}, game['formats'])
        self.assertEqual(game['check']['file'], 'default.xex')
        self.assertEqual(game['check']['ids'], ['575207E9'])
        self.assertEqual(self.manifest['start']['args'][:2], ['--play', '{game}'])
        programs = self.manifest['start']['program']
        self.assertTrue(any(name.endswith('.exe') for name in programs))
        self.assertTrue(any(name.endswith('.AppImage') for name in programs))

    def test_level_two_config_and_settings(self):
        config = self.manifest['config'][0]
        self.assertEqual(config['format'], 'json')
        self.assertTrue(config['game_path'])
        settings = self.manifest['settings']
        self.assertGreaterEqual(len(settings), 5)
        for setting in settings:
            self.assertEqual(setting['in'], 'args')
            self.assertGreaterEqual(len(setting['choices']), 2)
            for choice in setting['choices']:
                self.assertIsInstance(choice['args'], list)

    def test_every_setting_choice_is_a_valid_play_command(self):
        for setting in self.manifest['settings']:
            for choice in setting['choices']:
                with self.subTest(setting=setting['id'], choice=choice['label']):
                    parser, parsed = play_green_lantern.parse_arguments(
                        ['dump-folder', *choice['args']])
                    target = play_green_lantern.resolve_target(parser, parsed)
                    play_green_lantern.resolve_graphics(parser, parsed, target)

    def test_combined_options_do_not_conflict(self):
        chosen = [
            ['--graphics-preset', 'low'],
            ['--render-scale', '3'],
            ['--upscaler', 'fsr1'],
            ['--antialiasing', 'fxaa_extreme'],
            ['--fps-target', 'unlimited', '--vsync', 'off', '--present-mode', 'immediate'],
        ]
        arguments = ['dump-folder', *(arg for group in chosen for arg in group)]
        parser, parsed = play_green_lantern.parse_arguments(arguments)
        target = play_green_lantern.resolve_target(parser, parsed)
        graphics = play_green_lantern.resolve_graphics(parser, parsed, target)
        self.assertEqual(graphics['render_scale'], 3)
        self.assertEqual(graphics['fps_target'], 'unlimited')
        self.assertFalse(graphics['vsync'])


class PlayEntryTests(unittest.TestCase):
    def test_forwards_game_folder_and_options_to_play_script(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root / 'scripts/play_green_lantern.py'
            script.parent.mkdir()
            script.write_text('', encoding='utf8')
            captured = {}

            def fake_run(path, run_name=None):
                captured['argv'] = list(sys.argv)
                captured['run_name'] = run_name

            argv = ['AsterNative-windows-x64.exe', '--play', 'C:/Jogos/Green Lantern',
                    '--fps-target', '60']
            with patch('native_port.play_entry.runpy.run_path', side_effect=fake_run):
                with patch.object(sys, 'argv', argv):
                    self.assertEqual(dispatch(root, argv), 0)
            self.assertEqual(captured['argv'], [str(script), 'C:/Jogos/Green Lantern',
                                                '--fps-target', '60'])
            self.assertEqual(captured['run_name'], '__main__')

    def test_requires_a_game_folder(self):
        with self.assertRaises(SystemExit):
            dispatch(ROOT, ['AsterNative', '--play'])
        with self.assertRaises(SystemExit):
            dispatch(ROOT, ['AsterNative', '--play', '--fps-target', '60'])

    def test_requires_the_packaged_play_script(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(SystemExit):
                dispatch(Path(temporary), ['AsterNative', '--play', 'dump'])


class PackageTests(unittest.TestCase):
    def test_zip_has_manifest_at_the_top(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'native_port').mkdir()
            (root / 'native_port/__init__.py').write_text("__version__ = '9.9.9'\n", encoding='utf8')
            (root / 'recomplauncher.json').write_text('{}', encoding='utf8')
            output = root / 'dist'
            output.mkdir()
            artifact = output / 'AsterNative-windows-x64.exe'
            artifact.write_bytes(b'fake single file')
            system = 'Windows-x64' if os.name == 'nt' else 'Linux-x64'
            archive = package_launcher.recomplauncher_zip(root, artifact, output)
            self.assertEqual(archive.name, f'LanternRecomp-v9.9.9-{system}.zip')
            with zipfile.ZipFile(archive) as z:
                self.assertEqual(set(z.namelist()), {'AsterNative-windows-x64.exe',
                                                     'recomplauncher.json'})
                self.assertEqual(z.read('recomplauncher.json'), b'{}')


if __name__ == '__main__':
    unittest.main()
