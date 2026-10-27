import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from native_port.portable import install_payload, user_data_root


class PortablePayloadTests(unittest.TestCase):
    def test_update_and_reopening_preserve_user_data_and_executable_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / 'data/app'
            archive = base / 'payload.zip'
            def package(value):
                with zipfile.ZipFile(archive, 'w') as z:
                    z.writestr('games/green_lantern_rex_hints.toml', value)
                    z.writestr('scripts/play_green_lantern.py', 'public worker')
                    tool = zipfile.ZipInfo('tools/ninja/ninja')
                    tool.external_attr = 0o100755 << 16
                    z.writestr(tool, b'public tool')
            package('version one')
            install_payload(archive, root)
            save = root / '.aster/runtime/user/save'
            save.parent.mkdir(parents=True)
            save.write_bytes(b'human progress')
            config = root / '.aster/config/settings.json'
            config.parent.mkdir(parents=True)
            config.write_bytes(b'user preferences')
            tool = root / 'tools/ninja/ninja'
            stamp = tool.stat().st_mtime_ns
            install_payload(archive, root)
            self.assertEqual(tool.stat().st_mtime_ns, stamp)
            package('version two')
            install_payload(archive, root)
            self.assertEqual((root / 'games/green_lantern_rex_hints.toml').read_text(), 'version two')
            self.assertEqual(save.read_bytes(), b'human progress')
            self.assertEqual(config.read_bytes(), b'user preferences')
            if os.name != 'nt':
                self.assertTrue(os.access(tool, os.X_OK))

    def test_rejects_paths_into_workspace_and_outside_payload(self):
        for name in ['../escape', '.aster/config/settings.json', 'C:/escape', '/escape']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive = root / 'payload.zip'
                with zipfile.ZipFile(archive, 'w') as z:
                    z.writestr('games/green_lantern_rex_hints.toml', 'safe')
                    z.writestr(name, 'unsafe')
                with self.assertRaises(ValueError):
                    install_payload(archive, root / 'out')
                self.assertFalse((root / 'out/games').exists())

    def test_single_file_project_and_child_use_persistent_root(self):
        from native_port.paths import project_root, python_command
        with patch.dict(os.environ, {'ASTER_DATA_HOME': '/tmp/aster-test-data',
                                     'ASTER_LAUNCHER_ROOT': '/tmp/aster-test-data/app',
                                     'APPIMAGE': '/tmp/Launcher.AppImage'}), patch('sys.frozen', True, create=True):
            self.assertEqual(user_data_root(), Path('/tmp/aster-test-data').resolve())
            self.assertEqual(project_root(__file__), Path('/tmp/aster-test-data/app').resolve())
            self.assertEqual(python_command('/tmp/script.py', '--help')[0], '/tmp/Launcher.AppImage')
            self.assertEqual(python_command('/tmp/script.py')[1], '--appimage-extract-and-run')
