from pathlib import Path
import tempfile
import unittest
import zipfile

from native_port import save_manager
from native_port.errors import PortError


class SaveManagerTests(unittest.TestCase):
    def _profile(self, root):
        profile = save_manager.profile_dir(root)
        (profile / 'slot-1').mkdir(parents=True)
        (profile / 'slot-1' / 'profile.bin').write_bytes(b'GLSAVE')
        (profile / 'settings.bin').write_bytes(b'CONFIG')
        return profile

    def test_export_round_trip_and_backup_on_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = self._profile(root)
            package = root / 'export.zip'
            result = save_manager.export_save(root, package)
            self.assertEqual(result['files'], 2)
            with zipfile.ZipFile(package) as archive:
                self.assertEqual(sorted(archive.namelist()), ['settings.bin', 'slot-1/profile.bin'])

            (profile / 'slot-1' / 'profile.bin').write_bytes(b'CHANGED')
            imported = save_manager.import_save(root, package)
            self.assertEqual((profile / 'slot-1' / 'profile.bin').read_bytes(), b'GLSAVE')
            self.assertTrue(imported['backup'])
            backup = Path(imported['backup'])
            self.assertEqual((backup / 'slot-1' / 'profile.bin').read_bytes(), b'CHANGED')

    def test_export_missing_profile_and_empty_profile_are_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(PortError):
                save_manager.export_save(root, root / 'missing.zip')
            save_manager.profile_dir(root).mkdir(parents=True)
            with self.assertRaises(PortError):
                save_manager.export_save(root, root / 'empty.zip')

    def test_import_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'evil.zip'
            with zipfile.ZipFile(package, 'w') as archive:
                archive.writestr('../outside.bin', b'bad')
            with self.assertRaises(PortError):
                save_manager.import_save(root, package)
            self.assertFalse((root.parent / 'outside.bin').exists())

    def test_default_export_name_is_a_zip(self):
        self.assertTrue(save_manager.default_export_name().endswith('.zip'))


if __name__ == '__main__':
    unittest.main()
