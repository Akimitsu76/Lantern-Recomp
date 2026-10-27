import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fixtures import xex
from games.green_lantern import GreenLantern
from native_port import graphics, settings
from native_port.errors import PortError
from native_port.pipeline import prepare
from native_port.sources import inspect_source
from native_port.tasks import Cancellation
from native_port.workspace import Workspace


class FolderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.dump = self.project / 'dump'
        self.dump.mkdir()

    def test_default_preferred_and_inventory(self):
        (self.dump / 'default.xex').write_bytes(xex())
        (self.dump / 'other.xex').write_bytes(b'invalid-secondary-is-not-loaded')
        (self.dump / 'data').mkdir()
        (self.dump / 'data/asset.dat').write_bytes(b'synthetic')
        info = inspect_source(self.dump)
        self.assertTrue(info['path'].endswith('default.xex'))
        self.assertEqual(info['file_count'], 3)
        self.assertEqual(info['asset_file_count'], 1)
        self.assertIsNone(info['complete_assets'])
        self.assertEqual(info['input_kind'], 'game-folder')
        baseline = info['directory_manifest_sha256']
        (self.dump / 'data/asset.dat').write_bytes(b'changed')
        self.assertNotEqual(inspect_source(self.dump)['directory_manifest_sha256'], baseline)

    def test_single_nested_candidate(self):
        (self.dump / 'sub').mkdir()
        (self.dump / 'sub/game.XEX').write_bytes(xex())
        self.assertEqual(inspect_source(self.dump)['title_id'], '575207E9')

    def test_missing_ambiguous_and_symlink(self):
        with self.assertRaises(PortError) as e:
            inspect_source(self.dump)
        self.assertEqual(e.exception.code, 'MISSING_XEX')
        for name in ('a.xex', 'b.xex'):
            (self.dump / name).write_bytes(xex())
        with self.assertRaises(PortError) as e:
            inspect_source(self.dump)
        self.assertEqual(e.exception.code, 'AMBIGUOUS_XEX')
        (self.dump / 'outside').symlink_to(self.project, target_is_directory=True)
        with self.assertRaises(PortError) as e:
            inspect_source(self.dump)
        self.assertEqual(e.exception.code, 'SOURCE_SYMLINK')

    def test_folder_cancel(self):
        token = Cancellation()
        token.cancel()
        with self.assertRaises(PortError) as e:
            inspect_source(self.dump, token)
        self.assertEqual(e.exception.code, 'CANCELLED')

    @patch('native_port.pipeline.diagnostics', return_value={'tools': {}})
    def test_folder_pipeline_hashes_selected_executable(self, _):
        (self.dump / 'default.xex').write_bytes(xex())
        (self.dump / 'asset').write_bytes(b'data')
        work = Workspace(self.project / 'work', self.project)
        report = prepare(self.dump, work, GreenLantern())
        self.assertEqual(report['state'], 'blocked')
        self.assertEqual(report['source']['input_kind'], 'game-folder')
        self.assertFalse(report['ready'])
        self.assertEqual(report['source']['file_count'], 2)

    def test_settings_roundtrip_and_validation(self):
        data = settings.defaults(self.project)
        data.update(source=str(self.dump), build_type='Debug', jobs=4)
        settings.save(data, self.project)
        self.assertEqual(settings.load(self.project), data)
        for field, value in [('jobs', -1), ('jobs', 'sh'), ('workspace', '/tmp'), ('build_type', 'command')]:
            with self.assertRaises(PortError):
                settings.validate(dict(data, **{field: value}), self.project)
        with self.assertRaises(PortError):
            settings.validate(dict(data, source=str(self.project)), self.project)

    def test_schema_one_migrates_and_gains_graphics_defaults(self):
        (self.project / '.aster/config').mkdir(parents=True)
        legacy = {'schema': 1, 'workspace': str(self.project / '.aster'),
                  'source': str(self.dump), 'build_type': 'Release', 'jobs': 2}
        (self.project / '.aster/config/settings.json').write_text(json.dumps(legacy))
        loaded = settings.load(self.project)
        self.assertEqual(loaded['schema'], 2)
        self.assertEqual(loaded['source'], str(self.dump))
        self.assertEqual(loaded['graphics'], graphics.defaults())
        self.assertEqual(loaded['graphics']['fps_target'], '30')
        self.assertTrue(loaded['graphics']['vsync'])

    def test_graphics_validation_rejects_unknown_or_unsafe_values(self):
        good = settings.defaults(self.project)
        custom = graphics.from_options('custom', fps_target='30', vsync=True)
        for field, value in [('preset', 'cinema'), ('render_scale', 4), ('render_scale', True),
                             ('anisotropic', 9), ('texture_quality', 'max'), ('vsync', 'yes'),
                             ('shader_mode', 'magic'), ('fps_target', '120')]:
            with self.subTest(field=field), self.assertRaises(PortError):
                settings.validate(dict(good, graphics=dict(custom, **{field: value})),
                                  self.project)
        unlimited = settings.validate(
            dict(good, graphics=dict(custom, fps_target='unlimited', vsync=True)),
            self.project)
        self.assertEqual(unlimited['graphics']['fps_target'], 'unlimited')
        self.assertFalse(unlimited['graphics']['vsync'])

    def test_settings_save_never_creates_runtime_or_game_state(self):
        data = settings.defaults(self.project)
        data['graphics'] = graphics.from_options('high', fps_target='60', vsync=True)
        settings.save(data, self.project)
        written = self.project / '.aster/config/settings.json'
        self.assertTrue(written.is_file())
        self.assertFalse((self.project / '.aster/runtime').exists())
        self.assertFalse((self.dump / 'user').exists())
        self.assertEqual(settings.load(self.project)['graphics']['preset'], 'high')

    def test_settings_malformed(self):
        work = Workspace(self.project / '.aster', self.project)
        p = work.write_json('config/settings.json', {})
        with self.assertRaises(PortError) as e:
            settings.load(self.project)
        self.assertEqual(e.exception.code, 'SETTINGS_SCHEMA')
        p.write_text('{')
        with self.assertRaises(PortError) as e:
            settings.load(self.project)
        self.assertEqual(e.exception.code, 'SETTINGS_READ')


class SpatialSettingsMigrationTests(unittest.TestCase):
    def test_legacy_ultra_custom_gains_filter_but_explicit_choice_survives(self):
        from native_port import settings,graphics
        with tempfile.TemporaryDirectory() as folder:
            data=settings.defaults(folder)
            data['graphics']=graphics.from_options('custom',texture_quality='ultra')
            data['graphics'].pop('upscaler')
            with patch('native_port.settings.sys.platform','linux'):
                migrated=settings.validate(data,folder)
                self.assertEqual(migrated['graphics']['upscaler'],'fsr1')
                data['graphics']['upscaler']='bilinear'
                self.assertEqual(settings.validate(data,folder)['graphics']['upscaler'],'bilinear')
