"""Owned-source guards and preset behavior of automatic HD preparation."""
import copy
import hashlib
import json
import shutil
import struct
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from native_port import texture_pipeline as pipeline
from native_port.errors import PortError
from native_port.workspace import Workspace
from native_port.tasks import Cancellation


def digest(data):
    return hashlib.sha256(data).hexdigest()


class TexturePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = Workspace(self.root / 'work', self.root)
        self.dump = self.root / 'dump'
        self.dump.mkdir()
        self.xex = self.dump / 'default.xex'
        self.xex.write_bytes(b'XEX2 synthetic source')
        self.xex_hash = digest(self.xex.read_bytes())
        self.original_source = self.dump / 'gl/x360/levels/world.lvl_760'
        self.original_source.parent.mkdir(parents=True)
        self.original_source.write_bytes(b'compressed synthetic original')
        self.decoded = b'prefix' + b'reviewed texture blocks' + b'suffix'
        self.entry = {
            'source_relative': 'gl/x360/levels/world.lvl_760',
            'compressed_sha256': digest(self.original_source.read_bytes()),
            'compressed_size': self.original_source.stat().st_size,
            'decoded_sha256': digest(self.decoded), 'decoded_size': len(self.decoded),
            'raw_offset': 6, 'raw_size': len(b'reviewed texture blocks'),
            'raw_sha256': digest(b'reviewed texture blocks'),
            'canonical_rgba8_sha256': 'a' * 64,
            'original_dds_sha256': 'b' * 64,
            'classification': 'color-opaque', 'reviewed': True,
            'capture_metadata': {'schema': 1, 'purpose': 'inspection-only',
                'gpu_written_pages': False, 'tiled': True, 'width': 64, 'height': 64,
                'format': 18, 'endian': 1, 'base_size': len(b'reviewed texture blocks'),
                'base_row_pitch_bytes': 128, 'mip_max_level': 6, 'packed_level': 1},
        }
        self.profile = {'schema': 1, 'source_xex_sha256': self.xex_hash,
                        'entries': [self.entry], 'coverage': 'one reviewed fixture'}
        self.profile_path = self.root / pipeline.PROFILE
        self.profile_path.parent.mkdir(parents=True)
        self.write_profile()
        self.xex_patch = patch.object(pipeline, 'SOURCE_XEX_SHA256', self.xex_hash)
        self.xex_patch.start()
        self.addCleanup(self.xex_patch.stop)

    def write_profile(self):
        self.profile_path.write_text(json.dumps(self.profile), encoding='utf8')

    def prepare(self, quality, **kwargs):
        return pipeline.ensure_graphics_textures(self.xex, {'texture_quality': quality},
                                                self.root, self.work, **kwargs)

    def test_low_and_default_do_not_inspect_sources_or_create_cache(self):
        for quality in ('low', 'default'):
            with self.subTest(quality=quality), \
                 patch.object(pipeline, 'load_source_profile', side_effect=AssertionError('profile I/O')), \
                 patch('native_port.sources.source_path', side_effect=AssertionError('source I/O')), \
                 patch('native_port.texture_tools.ensure_texture_tools', side_effect=AssertionError('tools')):
                result = pipeline.ensure_graphics_textures('/missing/source',
                    {'texture_quality': quality}, '/missing/project', self.work)
                self.assertEqual(result, {'pack': None, 'material_count': 0,
                                         'state': 'original', 'host_scale': 1})
                self.assertFalse(self.work.root.exists())

    def test_changed_xex_fails_before_tool_download_or_ai(self):
        self.xex.write_bytes(b'changed source')
        with patch('native_port.texture_tools.ensure_texture_tools') as tools, \
             patch.object(pipeline, 'prepare_texture_pack') as ai:
            with self.assertRaises(PortError) as raised:
                self.prepare('high', allow_download=True)
            self.assertEqual(raised.exception.code, 'HD_XEX')
            tools.assert_not_called()
            ai.assert_not_called()

    def test_changed_container_fails_before_tool_download_or_ai(self):
        self.original_source.write_bytes(b'altered synthetic container')
        with patch('native_port.texture_tools.ensure_texture_tools') as tools, \
             patch.object(pipeline, 'prepare_texture_pack') as ai:
            with self.assertRaises(PortError) as raised:
                self.prepare('high', allow_download=True)
            self.assertEqual(raised.exception.code, 'HD_SOURCE_CHANGED')
            tools.assert_not_called()
            ai.assert_not_called()

    def test_profile_rejects_escaping_paths_unreviewed_materials_and_bounds(self):
        mutations = [
            ('posix traversal', {'source_relative': '../outside'}),
            ('absolute path', {'source_relative': '/tmp/outside'}),
            ('windows traversal', {'source_relative': r'..\outside'}),
            ('windows drive', {'source_relative': 'C:/outside'}),
            ('unreviewed', {'reviewed': False}),
            ('normal map', {'classification': 'normal'}),
            ('end beyond decoded', {'raw_offset': len(self.decoded)}),
            ('negative offset', {'raw_offset': -1}),
            ('boolean size', {'raw_size': True}),
            ('oversize decoded', {'decoded_size': 1024**3 + 1}),
            ('invalid hash', {'raw_sha256': 'wrong'}),
        ]
        for name, changes in mutations:
            with self.subTest(name=name):
                self.profile['entries'] = [dict(self.entry, **changes)]
                self.write_profile()
                with self.assertRaises(PortError):
                    pipeline.load_source_profile(self.root)

    def test_profile_rejects_unknown_or_unsafe_capture_layouts(self):
        baseline = copy.deepcopy(self.entry['capture_metadata'])
        mutations = [
            ('missing metadata', None),
            ('gpu authored', dict(baseline, gpu_written_pages=True)),
            ('wrong purpose', dict(baseline, purpose='runtime-target')),
            ('boolean dimension', dict(baseline, width=True)),
            ('non power of two', dict(baseline, width=96)),
            ('unsupported format', dict(baseline, format=6)),
            ('unknown endian', dict(baseline, endian=4)),
            ('base size mismatch', dict(baseline, base_size=99)),
            ('no guest mips', dict(baseline, mip_max_level=0)),
            ('packed base', dict(baseline, packed_level=0)),
            ('unbounded row pitch', dict(baseline, base_row_pitch_bytes=1024**2+1)),
        ]
        for name, metadata in mutations:
            with self.subTest(name=name):
                self.profile['entries'][0]['capture_metadata'] = metadata
                self.write_profile()
                with self.assertRaises(PortError) as raised:
                    pipeline.load_source_profile(self.root)
                self.assertEqual(raised.exception.code, 'HD_PROFILE')

    def test_profile_rejects_symlink_source_component(self):
        outside = self.root / 'external'
        outside.mkdir()
        (self.root / 'linked').symlink_to(outside, target_is_directory=True)
        self.profile['entries'][0]['source_relative'] = 'linked/world.lvl_760'
        self.write_profile()
        with self.assertRaises(PortError):
            pipeline.load_source_profile(self.root)

    def test_cached_originals_skip_tools_but_still_validate_owned_container(self):
        with patch.object(pipeline, '_original_matches', return_value=True), \
             patch('native_port.texture_tools.ensure_texture_tools') as tools, \
             patch('native_port.xctd.decode_container') as decode, \
             patch.object(pipeline, 'prepare_texture_pack', return_value=self.root / 'pack') as ai:
            result = self.prepare('high')
            self.assertEqual(result['material_count'], 1)
            tools.assert_not_called()
            decode.assert_not_called()
            self.assertEqual(ai.call_count, 1)
            self.original_source.write_bytes(b'corrupt original container')
            with self.assertRaises(PortError) as raised:
                self.prepare('high')
            self.assertEqual(raised.exception.code, 'HD_SOURCE_CHANGED')
            self.assertEqual(ai.call_count, 1)
            tools.assert_not_called()

    def test_cached_decoded_container_tamper_stops_before_ai(self):
        decoded = self.work.path('textures/decoded/' + self.entry['decoded_sha256'] + '.bin')
        decoded.parent.mkdir(parents=True)
        decoded.write_bytes(self.decoded[:-1] + b'!')
        with patch.object(pipeline, '_original_matches', return_value=False), \
             patch('native_port.texture_tools.ensure_texture_tools', return_value={'decoder': 'decode', 'untile': 'untile'}), \
             patch.object(pipeline, 'run_process') as helper, \
             patch.object(pipeline, 'prepare_texture_pack') as ai:
            with self.assertRaises(PortError) as raised:
                self.prepare('high')
            self.assertEqual(raised.exception.code, 'HD_SOURCE_CHANGED')
            helper.assert_not_called()
            ai.assert_not_called()
            self.assertEqual(decoded.read_bytes(), self.decoded[:-1] + b'!')

    def test_wrong_profile_raw_slice_stops_before_helper_and_ai(self):
        decoded = self.work.path('textures/decoded/' + self.entry['decoded_sha256'] + '.bin')
        decoded.parent.mkdir(parents=True)
        decoded.write_bytes(self.decoded)
        self.profile['entries'][0]['raw_sha256'] = 'c' * 64
        self.write_profile()
        with patch.object(pipeline, '_original_matches', return_value=False), \
             patch('native_port.texture_tools.ensure_texture_tools', return_value={'decoder': 'decode', 'untile': 'untile'}), \
             patch.object(pipeline, 'run_process') as helper, \
             patch.object(pipeline, 'prepare_texture_pack') as ai:
            with self.assertRaises(PortError) as raised:
                self.prepare('high')
            self.assertEqual(raised.exception.code, 'HD_SOURCE_CHANGED')
            helper.assert_not_called()
            ai.assert_not_called()
            self.assertFalse(list(decoded.parent.parent.rglob('.original-*')))

    def test_high_and_ultra_forward_real_two_and_four_times_scale(self):
        for quality, scale in (('high', 2), ('ultra', 4)):
            with self.subTest(quality=quality), \
                 patch.object(pipeline, '_original_matches', return_value=True), \
                 patch('native_port.texture_tools.ensure_texture_tools') as tools, \
                 patch.object(pipeline, 'prepare_texture_pack', return_value=self.root / 'pack') as ai:
                result = self.prepare(quality)
                self.assertEqual(ai.call_args.kwargs['host_scale'], scale)
                self.assertEqual(result['host_scale'], scale)
                self.assertEqual(result['coverage'], 'one reviewed fixture')
                catalog = json.loads(Path(ai.call_args.args[0]).read_text())
                self.assertEqual(catalog['entries'][0]['canonical_rgba8_sha256'], self.entry['canonical_rgba8_sha256'])
                self.assertTrue(catalog['entries'][0]['reviewed'])
                tools.assert_not_called()

    def test_runtime_library_flag_selects_library_for_both_scales(self):
        self.profile['runtime_library'] = True
        self.write_profile()
        for quality, scale in [('high', 2), ('ultra', 4)]:
            with self.subTest(quality=quality), \
                 patch.object(pipeline, '_original_matches', return_value=True), \
                 patch.object(pipeline, 'prepare_texture_pack') as pack, \
                 patch('native_port.texture_library.prepare_texture_library', return_value=self.root/'library') as library, \
                 patch('native_port.texture_tools.ensure_texture_tools') as tools:
                token = Cancellation()
                result = self.prepare(quality, cancel=token)
                self.assertEqual(result['pack'], str(self.root/'library'))
                self.assertEqual(result['material_count'], 1)
                self.assertEqual(library.call_args.kwargs['host_scale'], scale)
                self.assertIs(library.call_args.kwargs['cancel'], token)
                self.assertEqual(library.call_count, 1)
                pack.assert_not_called()
                tools.assert_not_called()

    def test_explicit_false_runtime_library_retains_pack_producer(self):
        self.profile['runtime_library'] = False
        self.write_profile()
        with patch.object(pipeline, '_original_matches', return_value=True), \
             patch.object(pipeline, 'prepare_texture_pack', return_value=self.root/'pack') as pack, \
             patch('native_port.texture_library.prepare_texture_library') as library:
            result=self.prepare('high')
            self.assertEqual(result['pack'],str(self.root/'pack'))
            pack.assert_called_once()
            library.assert_not_called()

    def test_profile_rejects_non_boolean_runtime_library_flag(self):
        for value in [None, 0, 1, 'true', [], {}]:
            with self.subTest(value=value):
                self.profile['runtime_library']=value
                self.write_profile()
                with self.assertRaises(PortError) as error: pipeline.load_source_profile(self.root)
                self.assertEqual(error.exception.code,'HD_PROFILE')

    def cached_original_fixture(self):
        from PIL import Image
        folder=self.root/'cached-original';folder.mkdir()
        Image.new('RGB',(64,64),(80,120,180)).save(folder/'original.dds',format='DDS',pixel_format='DXT1')
        with Image.open(folder/'original.dds') as image:
            rgba=image.convert('RGBA');rgba.save(folder/'original.png')
        canonical=hashlib.sha256(b'aster-texture-rgba8-v1\0'+struct.pack('<II',64,64)+rgba.tobytes()).hexdigest()
        dds=digest((folder/'original.dds').read_bytes())
        data={'status':'original-inspection-only','runtime_replacement':False,
              'canonical_rgba8_sha256':canonical,'dds_sha256':dds,
              'game_xex_sha256':self.xex_hash,'capture_metadata':{'format':18}}
        (folder/'inspection.json').write_text(json.dumps(data))
        return folder,dict(self.entry,canonical_rgba8_sha256=canonical,original_dds_sha256=dds)

    def test_cancellation_during_cached_original_hash_propagates(self):
        from native_port import texture_enhance
        folder,entry=self.cached_original_fixture()
        token=Cancellation();original_sha=texture_enhance.sha
        def interrupt_hash(path,cancel=None):
            if Path(path).name=='original.dds': token.cancel()
            return original_sha(path,cancel)
        before={p.name:p.read_bytes()for p in folder.iterdir()}
        with patch.object(texture_enhance,'sha',side_effect=interrupt_hash):
            with self.assertRaises(PortError) as error: pipeline._original_matches(folder,entry,token)
        self.assertEqual(error.exception.code,'CANCELLED')
        self.assertEqual({p.name:p.read_bytes()for p in folder.iterdir()},before)

    def test_cached_original_child_symlinks_are_rejected_without_changing_targets(self):
        folder,entry=self.cached_original_fixture()
        self.assertTrue(pipeline._original_matches(folder,entry,Cancellation()))
        for name in ['original.dds','original.png','inspection.json']:
            with self.subTest(name=name):
                # A complete external tree makes even inspection.json links
                # valid if followed; rejection must come from the link guard.
                outside_folder=self.root/('external-'+name)
                shutil.copytree(folder,outside_folder)
                child=folder/name;outside=outside_folder/name
                original=child.read_bytes();child.unlink()
                try:
                    child.symlink_to(outside)
                except OSError:
                    child.write_bytes(original)
                    self.skipTest('Host does not support symlink creation')
                try:
                    with self.assertRaises(PortError) as error: pipeline._original_matches(folder,entry,Cancellation())
                    self.assertEqual(error.exception.code,'HD_CACHE_CHANGED')
                    self.assertEqual(outside.read_bytes(),original)
                    self.assertTrue(child.is_symlink())
                finally:
                    child.unlink();child.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
