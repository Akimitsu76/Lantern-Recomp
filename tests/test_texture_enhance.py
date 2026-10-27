import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from native_port.errors import PortError
from native_port.texture_enhance import encode_mip_dds, linear_resize, load_reviewed_source, prepare_texture, sha, validate_prepared_pack
from native_port.workspace import Workspace


class TextureEnhanceTests(unittest.TestCase):
    def source(self, root):
        folder = root / 'capture'; folder.mkdir()
        image = Image.new('RGBA', (64, 64), (80, 100, 150, 255))
        image.save(folder / 'original.dds', pixel_format='DXT1')
        with Image.open(folder / 'original.dds') as decoded:
            rgba = decoded.convert('RGBA')
        rgba.save(folder / 'original.png')
        canonical = hashlib.sha256(b'aster-texture-rgba8-v1\0' + struct.pack('<II', *rgba.size) + rgba.tobytes()).hexdigest()
        data = {'status': 'original-inspection-only', 'runtime_replacement': False,
                'dds_sha256': sha(folder / 'original.dds'), 'canonical_rgba8_sha256': canonical,
                'capture_metadata': {'format': 18}}
        inspection = folder / 'inspection.json'; inspection.write_text(json.dumps(data))
        return inspection

    def test_source_needs_review_and_matching_original_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inspection = self.source(root)
            with self.assertRaises(PortError): load_reviewed_source(inspection, False)
            self.assertEqual(load_reviewed_source(inspection, True)[1].size, (64, 64))
            Image.new('RGB', (64, 64), 'red').save(inspection.parent / 'original.png')
            # Even changing the inspection PNG digest cannot disconnect it from the source blocks.
            data = json.loads(inspection.read_text())
            pixels = Image.open(inspection.parent / 'original.png').convert('RGBA')
            data['canonical_rgba8_sha256'] = hashlib.sha256(b'aster-texture-rgba8-v1\0' + struct.pack('<II', 64, 64) + pixels.tobytes()).hexdigest()
            inspection.write_text(json.dumps(data))
            with self.assertRaisesRegex(PortError, 'mesmos pixels'): load_reviewed_source(inspection, True)

    def test_dds_full_chain_has_correct_block_sizes_and_decodes(self):
        for fmt, fourcc, block in ((18, b'DXT1', 8), (20, b'DXT5', 16)):
            dds = encode_mip_dds(Image.new('RGB', (128, 64), (80, 120, 170)), fmt)
            self.assertEqual(dds[84:88], fourcc)
            self.assertEqual(struct.unpack_from('<I', dds, 28)[0], 8)
            self.assertEqual(struct.unpack_from('<I', dds, 20)[0], 32 * 16 * block)
            sizes = [(max(1, 128 >> i), max(1, 64 >> i)) for i in range(8)]
            self.assertEqual(len(dds), 128 + sum(((w+3)//4)*((h+3)//4)*block for w,h in sizes))
            with Image.open(io.BytesIO(dds)) as image:
                self.assertEqual(image.size, (128, 64)); image.load()

    def test_color_mips_filter_in_linear_light(self):
        image = Image.new('RGB', (2, 1)); image.putdata([(0,0,0), (255,255,255)])
        pixel = linear_resize(image, (1,1)).getpixel((0,0))
        self.assertTrue(180 < pixel[0] < 195, pixel)

    def test_preparation_reuses_verified_result_without_running_ai_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inspection = self.source(root); work = Workspace(root / '.aster', root)
            def inference(argv, *args, **kwargs):
                Image.new('RGB', (256, 256), (80,100,150)).save(Path(argv[argv.index('-o')+1]))
                return {'stdout': 'synthetic test inference', 'stderr': '', 'returncode': 0}
            with patch('native_port.texture_enhance.ensure_engine', return_value=(Path('engine'), Path('models'), 'test-engine', {})), \
                 patch('native_port.texture_enhance.run_process', side_effect=inference) as process:
                output = prepare_texture(inspection, root, work, reviewed_color_opaque=True)
                self.assertEqual(prepare_texture(inspection, root, work, reviewed_color_opaque=True), output)
                self.assertEqual(process.call_count, 1)
                self.assertEqual(validate_prepared_pack(output), output)
                self.assertEqual(json.loads((output/'manifest.json').read_text())['dimensions'], [128,128])
                (output/'texture.dds').write_bytes(b'changed')
                with self.assertRaises(PortError): prepare_texture(inspection, root, work, reviewed_color_opaque=True)
                with self.assertRaises(PortError): validate_prepared_pack(output)
                self.assertEqual(process.call_count, 1)


class TextureScaleTests(unittest.TestCase):
    source = TextureEnhanceTests.source
    def mocked_inference(self, argv, *args, **kwargs):
        with Image.open(argv[argv.index('-i') + 1]) as image:
            image.convert('RGB').resize((image.width * 4, image.height * 4)).save(argv[argv.index('-o') + 1])
        return {'stdout': 'synthetic inference', 'stderr': '', 'returncode': 0}

    def test_high_and_ultra_share_master_but_publish_different_dds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inspection = self.source(root); work = Workspace(root / '.aster', root)
            with patch('native_port.texture_enhance.ensure_engine', return_value=(Path('engine'), Path('models'), 'test-engine', {})), \
                    patch('native_port.texture_enhance.run_process', side_effect=self.mocked_inference) as process:
                high = prepare_texture(inspection, root, work, reviewed_color_opaque=True, host_scale=2)
                ultra = prepare_texture(inspection, root, work, reviewed_color_opaque=True, host_scale=4)
                self.assertNotEqual(high, ultra)
                self.assertEqual(process.call_count, 1)
                for folder, scale in [(high, 2), (ultra, 4)]:
                    self.assertEqual(validate_prepared_pack(folder), folder)
                    data = json.loads((folder / 'manifest.json').read_text())
                    self.assertEqual(data['dimensions'], [64 * scale, 64 * scale])
                    with Image.open(folder / 'texture.dds') as image:
                        self.assertEqual(image.size, (64 * scale, 64 * scale))
                    self.assertEqual(prepare_texture(inspection, root, work, reviewed_color_opaque=True, host_scale=scale), folder)
                self.assertEqual((high / 'inference.json').read_bytes(), (ultra / 'inference.json').read_bytes())
                self.assertEqual(process.call_count, 1)

    def test_master_tamper_does_not_trigger_unrequested_gpu_rebuild(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inspection = self.source(root); work = Workspace(root / '.aster', root)
            with patch('native_port.texture_enhance.ensure_engine', return_value=(Path('engine'), Path('models'), 'test-engine', {})), \
                    patch('native_port.texture_enhance.run_process', side_effect=self.mocked_inference) as process:
                high = prepare_texture(inspection, root, work, reviewed_color_opaque=True, host_scale=2)
                master = next(work.path('textures/inference').glob('*/enhanced-x4.png'))
                master.write_bytes(b'changed')
                with self.assertRaises(PortError) as caught:
                    prepare_texture(inspection, root, work, reviewed_color_opaque=True, host_scale=4)
                self.assertEqual(caught.exception.code, 'HD_CACHE_CHANGED')
                self.assertEqual(process.call_count, 1)
                self.assertEqual(validate_prepared_pack(high), high)

    def test_invalid_scales_are_rejected_before_source_or_model_access(self):
        for scale in (1, 3, 8, True, '4'):
            with self.subTest(scale=scale), self.assertRaises(PortError) as caught:
                prepare_texture('missing', 'missing', None, host_scale=scale)
            self.assertEqual(caught.exception.code, 'HD_SCALE')

    def test_receipt_and_host_geometry_must_match_even_with_rehashed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inspection = self.source(root); work = Workspace(root / '.aster', root)
            with patch('native_port.texture_enhance.ensure_engine', return_value=(Path('engine'), Path('models'), 'test-engine', {})), \
                    patch('native_port.texture_enhance.run_process', side_effect=self.mocked_inference):
                output = prepare_texture(inspection, root, work, reviewed_color_opaque=True, host_scale=4)
            metadata = json.loads((output / 'manifest.json').read_text())
            metadata['dimensions'] = [128, 128]
            (output / 'manifest.json').write_text(json.dumps(metadata))
            with self.assertRaises(PortError): validate_prepared_pack(output)
            metadata['dimensions'] = [256, 256]
            receipt = json.loads((output / 'inference.json').read_text())
            receipt['recipe']['original'] = 'wrong-original'
            (output / 'inference.json').write_text(json.dumps(receipt))
            metadata['files']['inference.json'] = sha(output / 'inference.json')
            (output / 'manifest.json').write_text(json.dumps(metadata))
            with self.assertRaises(PortError): validate_prepared_pack(output)
