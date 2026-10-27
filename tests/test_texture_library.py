import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from native_port.errors import PortError
from native_port.tasks import Cancellation
from native_port.texture_enhance import sha
from native_port.texture_pack import SOURCE_XEX_SHA256, load_material_catalog, validate_texture_pack
from native_port.texture_library import prepare_texture_library, validate_texture_library
from native_port.workspace import Workspace


class TextureLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.work = Workspace(self.root / '.aster', self.root)
        entries = []
        for i in range(2):
            folder = self.root / f'original{i}'; folder.mkdir()
            Image.new('RGBA', (64, 64), (30 + i * 50, 100, 170, 255)).save(folder / 'original.dds', pixel_format='DXT1')
            with Image.open(folder / 'original.dds') as source: rgba = source.convert('RGBA')
            rgba.save(folder / 'original.png')
            canonical = hashlib.sha256(b'aster-texture-rgba8-v1\0' + struct.pack('<II', 64, 64) + rgba.tobytes()).hexdigest()
            dds = sha(folder / 'original.dds')
            (folder / 'inspection.json').write_text(json.dumps({'status': 'original-inspection-only',
                'runtime_replacement': False, 'game_xex_sha256': SOURCE_XEX_SHA256,
                'canonical_rgba8_sha256': canonical, 'dds_sha256': dds, 'capture_metadata': {'format': 18}}))
            entries.append({'inspection': f'original{i}/inspection.json', 'classification': 'color-opaque',
                            'reviewed': True, 'canonical_rgba8_sha256': canonical, 'dds_sha256': dds})
        self.catalog = self.root / 'catalog.json'
        self.catalog.write_text(json.dumps({'schema': 1, 'source_xex_sha256': SOURCE_XEX_SHA256, 'entries': entries}))
        def inference(argv, *args, **kwargs):
            with Image.open(argv[argv.index('-i') + 1]) as source:
                source.resize((256, 256)).save(argv[argv.index('-o') + 1])
            return {'stdout': '', 'stderr': ''}
        self.engine = patch('native_port.texture_enhance.ensure_engine', return_value=(Path('engine'), Path('models'), '1' * 64, {}))
        self.process = patch('native_port.texture_enhance.run_process', side_effect=inference)
        self.engine.start(); self.addCleanup(self.engine.stop)
        self.inference = self.process.start(); self.addCleanup(self.process.stop)

    def prepare(self, **kwargs):
        return prepare_texture_library(self.catalog, self.root, self.work, **kwargs)

    def test_full_library_index_and_two_scales_share_inference(self):
        high = self.prepare(); ultra = self.prepare(host_scale=4)
        self.assertNotEqual(high, ultra); self.assertEqual(self.inference.call_count, 2)
        for path, scale in ((high, 2), (ultra, 4)):
            self.assertEqual(validate_texture_library(path), path)
            self.assertEqual(validate_texture_pack(path), path)
            lines = (path / 'texture-library.index').read_text().splitlines()
            self.assertEqual(lines[0], 'ASTERHDLIB1 2')
            for line in lines[1:]:
                bc, relative, fmt, w, h, digest, length = line.split()
                self.assertEqual(bc, relative); self.assertEqual((fmt, w, h), ('18', '64', '64'))
                self.assertEqual(int(length), (path / relative / 'texture.dds').stat().st_size)
                meta = json.loads((path / relative / 'manifest.json').read_text())
                self.assertEqual(meta['dimensions'], [64 * scale, 64 * scale])
        self.assertEqual(self.prepare(), high); self.assertEqual(self.inference.call_count, 2)

    def test_tampered_member_blocks_cached_library_without_new_inference(self):
        path = self.prepare(); data = json.loads((path / 'library.json').read_text())
        file = path / data['materials'][0]['bc'] / 'texture.dds'; file.write_bytes(b'changed')
        with self.assertRaises(PortError): validate_texture_library(path)
        self.assertEqual(self.inference.call_count, 2)

    def test_index_must_match_material_identity_and_geometry(self):
        path = self.prepare(); index = path / 'texture-library.index'; original = index.read_text()
        for change in (original.replace('ASTERHDLIB1 2', 'ASTERHDLIB1 3'), original.replace(' 64 64 ', ' 128 64 '), original + 'extra\n'):
            index.write_text(change)
            with self.assertRaises(PortError): validate_texture_library(path)
        index.write_text(original)
        self.assertEqual(validate_texture_library(path), path)

    def test_extra_files_and_symlink_escape_are_rejected(self):
        path = self.prepare(); extra = path / 'extra'; extra.write_text('extra')
        with self.assertRaises(PortError): validate_texture_library(path)
        extra.unlink(); data = json.loads((path / 'library.json').read_text())
        bc = data['materials'][0]['bc']; file = path / bc / 'texture.index'
        original = file.read_bytes(); file.unlink()
        outside = self.root / 'outside'; outside.write_bytes(original)
        try: file.symlink_to(outside)
        except OSError: self.skipTest('Host does not support symlink creation')
        with self.assertRaises(PortError): validate_texture_library(path)

    def test_cancel_after_material_resumes_completed_inference(self):
        cancel = Cancellation()
        def emit(event):
            if event.get('message', '').startswith('Textura HD preparada'): cancel.cancel()
        with self.assertRaises(PortError) as raised: self.prepare(cancel=cancel, emit=emit)
        self.assertEqual(raised.exception.code, 'CANCELLED'); self.assertEqual(self.inference.call_count, 1)
        path = self.prepare(); self.assertEqual(self.inference.call_count, 2)
        self.assertEqual(validate_texture_library(path), path)

    def test_large_catalog_requires_explicit_library_limit(self):
        entries = [{'inspection': f'source{i}/inspection.json', 'classification': 'unknown',
                    'canonical_rgba8_sha256': f'{i:064x}', 'dds_sha256': f'{i+1000:064x}'} for i in range(300)]
        self.catalog.write_text(json.dumps({'schema': 1, 'source_xex_sha256': SOURCE_XEX_SHA256, 'entries': entries}))
        with self.assertRaises(PortError): load_material_catalog(self.catalog)
        self.assertEqual(load_material_catalog(self.catalog, maximum=16384)['counts']['total'], 300)
        self.inference.assert_not_called()
