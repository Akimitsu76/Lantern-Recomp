import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from native_port.errors import PortError
from native_port.native_build import XEX_SHA256, host_platform
from native_port.retention import trim_workspace
from native_port import settings

ACTIVE = 'a' * 20
OLD = 'b' * 20
KEEP_PACK = 'c' * 64
OLD_PACK = 'd' * 64


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install(project):
    build = project / '.aster/native' / ACTIVE / 'build'
    build.mkdir(parents=True)
    binary = build / 'aster_green_lantern'
    binary.write_bytes(b'compiled port')
    library = build / 'librexglue.so'
    library.write_bytes(b'runtime library')
    data = {'schema': 1, 'state': 'built', 'platform': host_platform(),
            'xex_sha256': XEX_SHA256, 'game_root': '/games/green-lantern',
            'renderer': 'vulkan-fsi', 'binary': str(binary.relative_to(project)),
            'files': {str(path.relative_to(project)): digest(path)
                      for path in (binary, library)}}
    path = project / '.aster/config/native-install.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data), encoding='utf8')
    return build


class RetentionTests(unittest.TestCase):
    def test_keeps_runtime_and_active_build_and_removes_update_caches(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            active = install(project)
            old = project / '.aster/native' / OLD
            (old / 'build').mkdir(parents=True)
            (old / 'build/aster_green_lantern').write_bytes(b'old')
            for name in ('tools/build/bin', 'textures/inference/cache', 'textures/decoded/cache',
                         'textures/prepared/cache'):
                path = project / '.aster' / name
                path.mkdir(parents=True)
                (path / 'blob.bin').write_bytes(b'x' * 2048)
            keep = project / '.aster/textures/libraries' / KEEP_PACK
            discard = project / '.aster/textures/libraries' / OLD_PACK
            for path in (keep, discard):
                path.mkdir(parents=True)
                (path / 'texture.dds').write_bytes(b'hd')
            for name in ('textures/originals/profile', 'shaders/decoded/bank',
                         'cache/texture-validation/receipt', '.aster/runtime/user/save'):
                path = project / name if name.startswith('.aster/') else project / '.aster' / name
                path.mkdir(parents=True)
                (path / 'keep.bin').write_bytes(b'save')

            report = trim_workspace(project, project / '.aster', keep_packs=[keep])

            self.assertEqual(report['state'], 'trimmed')
            self.assertGreater(report['freed'], 0)
            self.assertTrue((active / 'aster_green_lantern').is_file())
            self.assertFalse(old.exists())
            self.assertFalse((project / '.aster/tools').exists())
            for name in ('inference', 'decoded', 'prepared'):
                self.assertFalse((project / '.aster/textures' / name).exists())
            self.assertTrue(keep.is_dir())
            self.assertFalse(discard.exists())
            for name in ('textures/originals/profile', 'shaders/decoded/bank',
                         'cache/texture-validation/receipt', 'runtime/user/save'):
                self.assertTrue((project / '.aster' / name).exists())

    def test_refuses_to_delete_when_active_build_was_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            active = install(project)
            (project / '.aster/tools').mkdir(parents=True)
            (project / '.aster/tools/blob').write_bytes(b'x')
            old = project / '.aster/native' / OLD
            old.mkdir(parents=True)
            (active / 'aster_green_lantern').write_bytes(b'tampered')

            report = trim_workspace(project, project / '.aster')

            self.assertEqual(report['state'], 'skipped')
            self.assertTrue((project / '.aster/tools/blob').is_file())
            self.assertTrue(old.is_dir())

    def test_prunes_old_pack_but_keeps_pack_used_from_textures_packs(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            install(project)
            keep = project / '.aster/textures/packs' / KEEP_PACK
            discard = project / '.aster/textures/packs' / OLD_PACK
            for path in (keep, discard):
                path.mkdir(parents=True)
                (path / 'pack.json').write_bytes(b'{}')

            report = trim_workspace(project, project / '.aster', keep_packs=[keep])

            self.assertEqual(report['state'], 'trimmed')
            self.assertTrue(keep.is_dir())
            self.assertFalse(discard.exists())

    def test_clean_workspace_is_not_rehashed_or_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            install(project)
            report = trim_workspace(project, project / '.aster')
            self.assertEqual(report['state'], 'clean')
            self.assertEqual(report['removed'], [])

    def test_symlinked_cache_is_never_followed_or_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            install(project)
            outside = project / 'outside'
            outside.mkdir()
            (outside / 'important.txt').write_bytes(b'user data')
            (project / '.aster/tools').symlink_to(outside, target_is_directory=True)
            intermediate = project / '.aster/textures/decoded/blob'
            intermediate.parent.mkdir(parents=True)
            intermediate.write_bytes(b'cache')

            report = trim_workspace(project, project / '.aster')

            self.assertEqual(report['state'], 'trimmed')
            self.assertTrue((outside / 'important.txt').is_file())
            self.assertTrue((project / '.aster/tools').is_symlink())
            self.assertFalse(intermediate.parent.exists())

    def test_lightweight_setting_defaults_on_and_requires_bool(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.assertTrue(settings.defaults(project)['lightweight'])
            cfg = settings.defaults(project)
            cfg['lightweight'] = 'yes'
            with self.assertRaises(PortError):
                settings.validate(cfg, project)


if __name__ == '__main__':
    unittest.main()
