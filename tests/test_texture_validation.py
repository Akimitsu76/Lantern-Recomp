"""Startup receipts must skip expensive work only while verified inputs persist."""
import hashlib
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from native_port.errors import PortError
from native_port.tasks import Cancellation
from native_port.texture_validation import ValidationReceipt, snapshot
from native_port.texture_pack import validate_texture_pack, validate_texture_pack_cached
from native_port import texture_pipeline as pipeline
from native_port.workspace import Workspace
from tests import test_texture_pack as pack_fixtures


class ValidationReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tree = self.root / 'tree'; self.tree.mkdir()
        self.file = self.tree / 'data'; self.file.write_bytes(b'first')
        self.receipt = ValidationReceipt(self.root / 'receipts', {'fixture': 1})

    def test_only_successful_stable_validation_is_published(self):
        with self.assertRaises(ValueError):
            self.receipt.publish('verified', [self.tree], lambda: (_ for _ in ()).throw(ValueError('invalid')))
        self.assertIsNone(self.receipt.read())
        def change(): self.file.write_bytes(b'changed during verification')
        with self.assertRaises(PortError) as error:
            self.receipt.publish('verified', [self.tree], change)
        self.assertEqual(error.exception.code, 'HD_VALIDATION_CHANGED')
        self.assertIsNone(self.receipt.read())
        self.receipt.publish('verified', [self.tree], lambda: None)
        self.assertTrue(self.receipt.matches(self.receipt.read(), [self.tree]))

    def test_edits_replacement_addition_removal_and_touch_invalidate(self):
        for change in ['edit', 'replace', 'add', 'remove', 'touch']:
            with self.subTest(change=change):
                self.receipt.publish('verified', [self.tree], lambda: None)
                if change == 'edit': self.file.write_bytes(b'other')
                elif change == 'replace':
                    other = self.tree / 'replacement'; other.write_bytes(self.file.read_bytes()); os.replace(other, self.file)
                elif change == 'add': (self.tree / 'extra').write_bytes(b'extra')
                elif change == 'remove': (self.tree / 'extra').unlink()
                else:
                    s = self.file.stat(); os.utime(self.file, ns=(s.st_atime_ns, s.st_mtime_ns + 1000000))
                self.assertFalse(self.receipt.matches(self.receipt.read(), [self.tree]))

    def test_links_and_linked_ancestors_cannot_reuse_receipt(self):
        self.receipt.publish('verified', [self.tree], lambda: None)
        outside = self.root / 'outside'; outside.write_bytes(self.file.read_bytes())
        self.file.unlink()
        try: self.file.symlink_to(outside)
        except OSError: self.skipTest('Host cannot create symlinks')
        self.assertFalse(self.receipt.matches(self.receipt.read(), [self.tree]))
        with self.assertRaises(PortError): snapshot([self.tree])
        self.file.unlink(); self.file.write_bytes(b'first')
        renamed = self.root / 'renamed'; self.tree.rename(renamed); self.tree.symlink_to(renamed, target_is_directory=True)
        with self.assertRaises(PortError): snapshot([self.file])

    def test_receipt_is_bounded_external_and_not_followed_if_linked(self):
        with patch('native_port.texture_validation.MAX_RECEIPT_BYTES', 1):
            self.assertFalse(self.receipt.publish('verified', [self.tree], lambda: None))
        inside = ValidationReceipt(self.tree / 'receipts', {'fixture': 1})
        with self.assertRaises(PortError): inside.publish('verified', [self.tree], lambda: None)
        self.receipt.publish('verified', [self.tree], lambda: None)
        original = self.receipt.path.read_bytes(); self.receipt.path.unlink()
        outside = self.root / 'outside.json'; outside.write_bytes(original)
        try: self.receipt.path.symlink_to(outside)
        except OSError: self.skipTest('Host cannot create symlinks')
        self.assertIsNone(self.receipt.read())

    def test_cancellation_never_publishes(self):
        cancel = Cancellation(); receipt = ValidationReceipt(self.root / 'receipts', {}, cancel)
        with self.assertRaises(PortError) as error:
            receipt.publish('result', [self.tree], cancel.cancel)
        self.assertEqual(error.exception.code, 'CANCELLED')
        self.assertFalse(receipt.path.exists())

    def test_windows_reparse_points_are_rejected_even_when_not_symlinks(self):
        from native_port.texture_validation import _safe_stat
        info = SimpleNamespace(st_mode=self.file.stat().st_mode, st_file_attributes=0x400)
        with patch.object(type(self.file), 'lstat', return_value=info):
            with self.assertRaises(PortError) as error: _safe_stat(self.file)
        self.assertEqual(error.exception.code, 'HD_VALIDATION_LINK')


class TextureStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.work = Workspace(self.root / '.aster', self.root)
        fixture = pack_fixtures.TexturePackTests()
        self.catalog = fixture.catalog(self.root, 1)
        engine, inference = fixture.patches()
        from native_port.texture_pack import prepare_texture_pack
        with engine, inference: self.pack = prepare_texture_pack(self.catalog, self.root, self.work)

    def test_pack_dry_run_then_play_reuses_full_validation(self):
        cache = self.work.path('cache/texture-validation')
        with patch('native_port.texture_pack.validate_texture_pack', wraps=validate_texture_pack) as full:
            self.assertEqual(validate_texture_pack_cached(self.pack, cache), self.pack)
            self.assertEqual(full.call_count, 1)
        with patch('native_port.texture_pack.validate_texture_pack', side_effect=AssertionError('full validator')), \
             patch('PIL.Image.open', side_effect=AssertionError('image decode')):
            self.assertEqual(validate_texture_pack_cached(self.pack, cache), self.pack)
        with patch('native_port.texture_pack.validate_texture_pack', wraps=validate_texture_pack) as full:
            validate_texture_pack_cached(self.pack, cache, full=True)
            self.assertEqual(full.call_count, 1)

    def test_pack_edit_falls_back_and_invalid_result_is_not_cached(self):
        cache = self.work.path('cache/texture-validation')
        validate_texture_pack_cached(self.pack, cache)
        member = next(self.pack.glob('*/texture.dds')); member.write_bytes(b'corrupt')
        with patch('native_port.texture_pack.validate_texture_pack', wraps=validate_texture_pack) as full:
            for _ in range(2):
                with self.assertRaises(PortError): validate_texture_pack_cached(self.pack, cache)
            self.assertEqual(full.call_count, 2)

    def test_pack_directory_addition_and_link_are_not_accepted_as_hits(self):
        cache = self.work.path('cache/texture-validation')
        validate_texture_pack_cached(self.pack, cache)
        extra = self.pack / 'unexpected'; extra.write_bytes(b'extra')
        with self.assertRaises(PortError): validate_texture_pack_cached(self.pack, cache)
        extra.unlink()
        validate_texture_pack_cached(self.pack, cache)
        member = next(self.pack.glob('*/texture.index')); original = member.read_bytes()
        outside = self.root / 'outside.index'; outside.write_bytes(original); member.unlink()
        try: member.symlink_to(outside)
        except OSError: self.skipTest('Host cannot create symlinks')
        with self.assertRaises(PortError): validate_texture_pack_cached(self.pack, cache)
        self.assertEqual(outside.read_bytes(), original)

    def test_wrong_source_identity_cannot_reuse_pack_receipt(self):
        cache = self.work.path('cache/texture-validation')
        validate_texture_pack_cached(self.pack, cache)
        with self.assertRaises(PortError):
            validate_texture_pack_cached(self.pack, cache, expected_xex_sha256='0' * 64)

    def test_corrupt_receipt_returns_to_complete_validation(self):
        cache = self.work.path('cache/texture-validation')
        validate_texture_pack_cached(self.pack, cache)
        for path in cache.glob('*.json'): path.write_text('{invalid')
        with patch('native_port.texture_pack.validate_texture_pack', wraps=validate_texture_pack) as full:
            validate_texture_pack_cached(self.pack, cache)
            self.assertEqual(full.call_count, 1)

    def test_complete_pipeline_hit_skips_originals_producer_ai_and_full_validation(self):
        xex = self.root / 'dump/default.xex'; xex.parent.mkdir(); xex.write_bytes(b'synthetic owned dump')
        source = xex.parent / 'source.pak'; source.write_bytes(b'container')
        inspection = json.loads((self.root / 'source0/inspection.json').read_text())
        canonical = inspection['canonical_rgba8_sha256']
        entry = {'source_relative': source.name, 'compressed_size': source.stat().st_size,
                 'compressed_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                 'canonical_rgba8_sha256': canonical, 'original_dds_sha256': inspection['dds_sha256']}
        profile = {'entries': [entry], 'coverage': 'fixture'}
        profile_path = self.root / pipeline.PROFILE; profile_path.parent.mkdir(parents=True); profile_path.write_text('{}')
        profile_hash = hashlib.sha256(profile_path.read_bytes()).hexdigest()
        original_home = self.work.path('textures/originals/' + profile_hash)
        original_home.mkdir(parents=True)
        shutil.copytree(self.root / 'source0', original_home / canonical)
        digest = hashlib.sha256(xex.read_bytes()).hexdigest()
        with patch.object(pipeline, 'SOURCE_XEX_SHA256', digest), \
             patch.object(pipeline, 'load_source_profile', return_value=(profile, profile_hash)), \
             patch.object(pipeline, '_original_matches', return_value=True), \
             patch.object(pipeline, 'prepare_texture_pack', return_value=self.pack) as producer, \
             patch('native_port.texture_pack.validate_texture_pack', wraps=lambda *a, **kw: self.pack) as full:
            first = pipeline.ensure_graphics_textures(xex, {'texture_quality': 'high'}, self.root, self.work)
            self.assertEqual(producer.call_count, 1); self.assertEqual(full.call_count, 1)
        with patch.object(pipeline, 'SOURCE_XEX_SHA256', digest), \
             patch.object(pipeline, 'load_source_profile', return_value=(profile, profile_hash)), \
             patch.object(pipeline, '_original_matches', side_effect=AssertionError('decode originals')), \
             patch.object(pipeline, 'prepare_texture_pack', side_effect=AssertionError('producer')), \
             patch('native_port.texture_pack.validate_texture_pack', side_effect=AssertionError('full validator')), \
             patch('PIL.Image.open', side_effect=AssertionError('PIL')):
            self.assertEqual(pipeline.ensure_graphics_textures(xex, {'texture_quality': 'high'}, self.root, self.work), first)
        # The 2x receipt cannot authorize 4x output or an explicit full check.
        with patch.object(pipeline, 'SOURCE_XEX_SHA256', digest), \
             patch.object(pipeline, 'load_source_profile', return_value=(profile, profile_hash)), \
             patch.object(pipeline, '_original_matches', return_value=True), \
             patch.object(pipeline, 'prepare_texture_pack', return_value=self.pack) as producer, \
             patch('native_port.texture_pack.validate_texture_pack', wraps=lambda *a, **kw: self.pack):
            pipeline.ensure_graphics_textures(xex, {'texture_quality': 'ultra'}, self.root, self.work)
            self.assertEqual(producer.call_args.kwargs['host_scale'], 4)
            pipeline.ensure_graphics_textures(xex, {'texture_quality': 'high'}, self.root, self.work,
                                             full_validation=True)
            self.assertEqual(producer.call_count, 2)
        # Changing only a reviewed source invalidates the combined startup receipt.
        source.write_bytes(b'changed')
        with patch.object(pipeline, 'SOURCE_XEX_SHA256', digest), \
             patch.object(pipeline, 'load_source_profile', return_value=(profile, profile_hash)), \
             patch.object(pipeline, 'prepare_texture_pack', side_effect=AssertionError('producer')):
            with self.assertRaises(PortError) as error:
                pipeline.ensure_graphics_textures(xex, {'texture_quality': 'high'}, self.root, self.work)
            self.assertEqual(error.exception.code, 'HD_SOURCE_CHANGED')


if __name__ == '__main__': unittest.main()
