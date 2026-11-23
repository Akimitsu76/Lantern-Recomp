"""Contract tests for RecompLauncher support (levels 1, 2 and 3)."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from native_port import play_entry, xdvdfs_extract  # noqa: E402
from native_port.sources import MAGIC, SECTOR  # noqa: E402
from scripts import package_launcher  # noqa: E402
from scripts import play_green_lantern  # noqa: E402


def dirent(name, sector, size, *, directory=False, left=0, right=0):
    """One 4-byte-aligned XDVDFS directory entry."""
    raw = name.encode('cp1252')
    record = struct.pack('<HHIIBB', left, right, sector, size,
                         0x10 if directory else 0, len(raw)) + raw
    return record + b'\xff' * (-len(record) % 4)


def table(records):
    buffer = bytearray(b'\xff' * SECTOR)
    for offset, record in records.items():
        buffer[offset:offset + len(record)] = record
    return bytes(buffer)


def make_iso(path, *, xex_name='default.xex', xex=b'XEX2' + b'x' * 96,
             readme=b'hello from the disc'):
    """Write a minimal but structurally valid single-partition XDVDFS image."""
    image = bytearray(SECTOR * 42)
    descriptor = bytearray(SECTOR)
    descriptor[0:20] = MAGIC
    struct.pack_into('<II', descriptor, 20, 34, SECTOR)
    descriptor[-20:] = MAGIC
    image[32 * SECTOR:33 * SECTOR] = descriptor
    first = dirent(xex_name, 36, len(xex))
    second = dirent('Media', 38, SECTOR, directory=True)
    first = dirent(xex_name, 36, len(xex), right=len(first) // 4)
    image[34 * SECTOR:35 * SECTOR] = table({0: first, len(first): second})
    image[38 * SECTOR:39 * SECTOR] = table({0: dirent('readme.txt', 40, len(readme))})
    image[36 * SECTOR:36 * SECTOR + len(xex)] = xex
    image[40 * SECTOR:40 * SECTOR + len(readme)] = readme
    Path(path).write_bytes(image)
    return xex


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / 'recomplauncher.json').read_text(encoding='utf8'))
        cls.game = next(item for item in cls.manifest['inputs'] if item['id'] == 'game')

    def test_level_one_setup_and_start(self):
        self.assertEqual(self.manifest['format'], 1)
        self.assertEqual(self.manifest['repo'], 'Akimitsu76/Lantern-Recomp')
        self.assertEqual(self.game['role'], 'game')
        self.assertIn({'type': 'file', 'extensions': ['iso']}, self.game['formats'])
        self.assertIn({'type': 'folder'}, self.game['formats'])
        self.assertEqual(self.game['check']['ids'], ['575207E9'])
        self.assertEqual(self.manifest['start']['args'][:2], ['--play', '{input:game}'])
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

    def test_level_three_prepare_and_dumps(self):
        prepare = self.manifest['prepare']
        self.assertEqual(prepare['args'], ['--prepare-game', '{input:game}'])
        self.assertTrue(prepare['label'])
        self.assertEqual(len(prepare['done']), 2)
        self.assertTrue(all(path.endswith('green-lantern/default.xex')
                            for path in prepare['done']))
        self.assertTrue(any(name.endswith('.exe') for name in prepare['program']))
        self.assertTrue(any(name.endswith('.AppImage') for name in prepare['program']))
        dumps = {item['name']: item for item in self.game['dumps']}
        self.assertEqual(dumps['Europe'],
                         {'name': 'Europe', 'size': 7838695424, 'crc32': 'b722866e'})
        self.assertEqual(dumps['USA'],
                         {'name': 'USA', 'size': 7838695424, 'crc32': '1cb483fd'})

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

    def test_expected_xex_matches_play_script(self):
        self.assertEqual(play_entry.EXPECTED_XEX, play_green_lantern.EXPECTED_XEX)


class XdvdfsExtractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.xex = make_iso(self.root / 'greenlantern.iso')

    def tearDown(self):
        self.temp.cleanup()

    def test_extracts_files_and_subdirectories(self):
        destination = self.root / 'extracted'
        lines = []
        report = xdvdfs_extract.extract(self.root / 'greenlantern.iso', destination,
                                        emit=lines.append)
        self.assertEqual((destination / 'default.xex').read_bytes(), self.xex)
        self.assertEqual((destination / 'Media' / 'readme.txt').read_bytes(), b'hello from the disc')
        self.assertEqual(report['files'], 2)
        self.assertTrue(any(line.startswith('progress 0.10 ') for line in lines))

    def test_refuses_parent_path_in_entry_name(self):
        iso = self.root / 'evil.iso'
        make_iso(iso, xex_name='../evil')
        with self.assertRaises(xdvdfs_extract.PortError) as caught:
            xdvdfs_extract.extract(iso, self.root / 'evil-out')
        self.assertEqual(caught.exception.code, 'BAD_XDVDFS_NAME')

    def test_enforces_file_size_limit(self):
        with patch.object(xdvdfs_extract, 'MAX_FILE_BYTES', 8):
            with self.assertRaises(xdvdfs_extract.PortError) as caught:
                xdvdfs_extract.extract(self.root / 'greenlantern.iso', self.root / 'capped')
        self.assertEqual(caught.exception.code, 'XDVDFS_LIMIT')

    def test_enforces_directory_limit(self):
        with patch.object(xdvdfs_extract, 'MAX_DEPTH', 0):
            with self.assertRaises(xdvdfs_extract.PortError) as caught:
                xdvdfs_extract.extract(self.root / 'greenlantern.iso', self.root / 'shallow')
        self.assertEqual(caught.exception.code, 'XDVDFS_LIMIT')


class PrepareDispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.xex = make_iso(self.root / 'greenlantern.iso')
        self.expected = hashlib.sha256(self.xex).hexdigest()
        self.hashes = patch.object(play_entry, 'EXPECTED_XEX', self.expected)
        self.hashes.start()
        self.addCleanup(self.hashes.stop)

    def tearDown(self):
        self.temp.cleanup()

    def test_prepare_game_extracts_iso_once(self):
        with patch.object(xdvdfs_extract, 'extract',
                          wraps=xdvdfs_extract.extract) as extract:
            lines = []
            folder = play_entry.prepare_game(self.root, self.root / 'greenlantern.iso',
                                             emit=lines.append)
            self.assertEqual(folder, play_entry.game_files_folder(self.root))
            self.assertTrue((folder / 'default.xex').is_file())
            self.assertEqual(lines[-1], 'progress 1.0 Jogo pronto')
            play_entry.prepare_game(self.root, self.root / 'greenlantern.iso', emit=lines.append)
            self.assertEqual(extract.call_count, 1)

    def test_prepare_game_accepts_a_verified_folder(self):
        folder = self.root / 'dump'
        folder.mkdir()
        (folder / 'default.xex').write_bytes(self.xex)
        self.assertEqual(play_entry.prepare_game(self.root, folder), folder)

    def test_prepare_game_refuses_a_wrong_default_xex(self):
        folder = self.root / 'wrong'
        folder.mkdir()
        (folder / 'default.xex').write_bytes(b'not the reviewed build')
        with self.assertRaises(SystemExit):
            play_entry.prepare_game(self.root, folder)

    def test_play_resolves_an_iso_before_forwarding(self):
        script = self.root / 'scripts/play_green_lantern.py'
        script.parent.mkdir()
        script.write_text('', encoding='utf8')
        captured = {}

        def fake_run(path, run_name=None):
            captured['argv'] = list(sys.argv)

        argv = ['AsterNative', '--play', str(self.root / 'greenlantern.iso'), '--fps-target', '60']
        with patch('native_port.play_entry.runpy.run_path', side_effect=fake_run):
            with patch.object(sys, 'argv', argv):
                self.assertEqual(play_entry.dispatch(self.root, argv), 0)
        self.assertEqual(captured['argv'],
                         [str(script), str(play_entry.game_files_folder(self.root)),
                          '--fps-target', '60'])

    def test_prepare_dispatch_prints_progress_and_returns_zero(self):
        argv = ['AsterNative', '--prepare-game', str(self.root / 'greenlantern.iso')]
        with patch.object(sys, 'argv', argv):
            self.assertEqual(play_entry.prepare_dispatch(self.root, argv), 0)
        with self.assertRaises(SystemExit):
            play_entry.prepare_dispatch(self.root, ['AsterNative', '--prepare-game'])


class DispatchTests(unittest.TestCase):
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
                    self.assertEqual(play_entry.dispatch(root, argv), 0)
            self.assertEqual(captured['argv'], [str(script), 'C:/Jogos/Green Lantern',
                                                '--fps-target', '60'])
            self.assertEqual(captured['run_name'], '__main__')

    def test_requires_a_game_copy(self):
        with self.assertRaises(SystemExit):
            play_entry.dispatch(ROOT, ['AsterNative', '--play'])
        with self.assertRaises(SystemExit):
            play_entry.dispatch(ROOT, ['AsterNative', '--play', '--fps-target', '60'])

    def test_requires_the_packaged_play_script(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(SystemExit):
                play_entry.dispatch(Path(temporary), ['AsterNative', '--play', 'dump'])


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
