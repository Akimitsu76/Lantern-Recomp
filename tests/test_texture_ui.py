import io
import struct
import unittest

from native_port.errors import PortError
from native_port.texture_ui import encode_ui_mips, prepare_reviewed_ui, resize_straight_alpha
try:
    from PIL import Image
except ImportError:
    Image = None


@unittest.skipUnless(Image, 'Pillow required')
class TextureUITests(unittest.TestCase):
    def test_hidden_color_does_not_bleed(self):
        image = Image.new('RGBA', (2, 1)); image.putdata([(255, 0, 0, 0), (0, 255, 0, 255)])
        scaled = resize_straight_alpha(image, (8, 4), alpha_semantics='straight')
        for red, green, blue, alpha in scaled.get_flattened_data():
            self.assertEqual(red, 0); self.assertEqual(blue, 0)
            if alpha: self.assertGreaterEqual(green, 254)

    def test_constant_alpha_and_color_preserved(self):
        image = Image.new('RGBA', (4, 4), (23, 110, 197, 87))
        result = resize_straight_alpha(image, (16, 16), alpha_semantics='straight')
        self.assertEqual(set(result.get_flattened_data()), {(23, 110, 197, 87)})

    def test_unknown_alpha_rejected(self):
        for meaning in ('unknown', 'premultiplied'):
            with self.assertRaises(PortError):
                resize_straight_alpha(Image.new('RGBA', (4, 4)), (8, 8), alpha_semantics=meaning)

    def test_needs_review_and_valid_scale(self):
        for review, scale in ((False, 2), (True, 3), (True, True)):
            with self.assertRaises(PortError):
                prepare_reviewed_ui(Image.new('RGBA', (4, 4)), scale=scale, classification='ui-image', alpha_semantics='straight', reviewed=review)

    def test_glyph_metadata_mandatory(self):
        with self.assertRaises(PortError):
            prepare_reviewed_ui(Image.new('RGBA', (4, 4)), scale=2, classification='glyph-atlas', alpha_semantics='straight', reviewed=True)

    def test_glyph_cells_preserve_uv_and_separation(self):
        image = Image.new('RGBA', (8, 4)); image.paste((255, 0, 0, 255), (1, 1, 3, 3)); image.paste((0, 255, 0, 255), (5, 1, 7, 3))
        result = prepare_reviewed_ui(image, scale=2, classification='glyph-atlas', alpha_semantics='straight', reviewed=True, glyph_rectangles=[(0, 0, 4, 4), (4, 0, 8, 4)])
        self.assertEqual(result.size, (16, 8)); self.assertEqual(result.getpixel((7, 4))[3], 0); self.assertEqual(result.getpixel((8, 4))[3], 0)
        self.assertEqual(result.getpixel((3, 3)), (255, 0, 0, 255)); self.assertEqual(result.getpixel((11, 3)), (0, 255, 0, 255))

    def test_incomplete_overlap_and_bounds_rejected(self):
        image = Image.new('RGBA', (8, 4), 'white')
        for cells in ([(0, 0, 4, 4)], [(0, 0, 6, 4), (4, 0, 8, 4)], [(-1, 0, 8, 4)]):
            with self.assertRaises(PortError):
                prepare_reviewed_ui(image, scale=2, classification='glyph-atlas', alpha_semantics='straight', reviewed=True, glyph_rectangles=cells)

    def test_alpha_survives_every_mip(self):
        image = Image.new('RGBA', (16, 8), (255, 255, 255, 80))
        dds = encode_ui_mips(image, alpha_semantics='straight')
        self.assertEqual(struct.unpack_from('<I', dds, 28)[0], 5)
        width, height, offset = 16, 8, 128
        for _ in range(5):
            size = ((width + 3) // 4) * ((height + 3) // 4) * 16
            header = bytearray(dds[:128]); struct.pack_into('<II', header, 12, height, width)
            level = Image.open(io.BytesIO(bytes(header) + dds[offset:offset + size])).convert('RGBA')
            low, high = level.getchannel('A').getextrema()
            self.assertLess(high, 255); self.assertGreater(low, 0)
            offset += size; width = max(1, width // 2); height = max(1, height // 2)
        self.assertEqual(offset, len(dds))

    def test_limits_before_allocation(self):
        with self.assertRaises(PortError):
            resize_straight_alpha(Image.new('RGBA', (1, 1)), (8192, 8192), alpha_semantics='straight')


@unittest.skipUnless(Image, 'Pillow required')
class UIPackTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name); self.source = self.root / 'original.dds'
        Image.new('RGBA', (64, 64), (255, 255, 255, 80)).save(self.source, format='DDS', pixel_format='DXT5')
        self.glyphs = [{'codepoint': 65, 'page': 0, 'x': 0, 'y': 0, 'width': 64, 'height': 64, 'xoffset': 0, 'yoffset': 0, 'advance': 32}]

    def test_real_bc3_prepare_validate_and_reuse(self):
        from native_port.texture_ui import prepare_ui_pack, validate_ui_pack
        target = self.root / 'pack'
        self.assertEqual(prepare_ui_pack(self.source, self.glyphs, target, reviewed=True), target)
        self.assertEqual(validate_ui_pack(target), target)
        before = (target / 'texture.dds').stat().st_mtime_ns
        prepare_ui_pack(self.source, self.glyphs, target, reviewed=True)
        self.assertEqual((target / 'texture.dds').stat().st_mtime_ns, before)

    def test_mutation_preserved_and_rejected(self):
        from native_port.texture_ui import prepare_ui_pack, validate_ui_pack
        target = prepare_ui_pack(self.source, self.glyphs, self.root / 'pack', reviewed=True)
        (target / 'ui-glyphs.index').write_text('altered')
        with self.assertRaises(PortError): validate_ui_pack(target)
        with self.assertRaises(PortError): prepare_ui_pack(self.source, self.glyphs, target, reviewed=True)
        self.assertEqual((target / 'ui-glyphs.index').read_text(), 'altered')

    def test_nonwhite_and_unreviewed_rejected(self):
        from native_port.texture_ui import prepare_ui_pack
        with self.assertRaises(PortError): prepare_ui_pack(self.source, self.glyphs, self.root / 'pack')
        Image.new('RGBA', (64, 64), (0, 255, 0, 80)).save(self.source, format='DDS', pixel_format='DXT5')
        with self.assertRaises(PortError): prepare_ui_pack(self.source, self.glyphs, self.root / 'pack', reviewed=True)

    def test_glyph_contract_rejects_duplicate_and_overlap(self):
        from native_port.texture_ui import glyph_index_bytes
        with self.assertRaises(PortError): glyph_index_bytes(self.glyphs * 2, 64, 64)
        other = dict(self.glyphs[0], codepoint=66)
        with self.assertRaises(PortError): glyph_index_bytes(self.glyphs + [other], 64, 64)

    def test_white_hidden_rgb_survives_every_mip(self):
        from native_port.texture_ui import encode_ui_mips
        image = Image.new('RGBA', (16, 16), 'white'); image.putalpha(Image.new('L', (16, 16)))
        image.paste((255, 255, 255, 255), (4, 4, 12, 12))
        dds = encode_ui_mips(image, alpha_semantics='straight'); offset = 128; w = h = 16
        for _ in range(5):
            size = ((w + 3) // 4) * ((h + 3) // 4) * 16
            header = bytearray(dds[:128]); struct.pack_into('<II', header, 12, h, w)
            level = Image.open(io.BytesIO(bytes(header) + dds[offset:offset + size])).convert('RGBA')
            self.assertTrue(all(pixel[:3] == (255, 255, 255) for pixel in level.get_flattened_data()))
            offset += size; w = h = max(1, w // 2)

    def test_original_quantization_residue_preserved(self):
        image = Image.new('RGBA', (8, 8), (255, 255, 255, 0))
        image.putpixel((7, 7), (255, 255, 255, 1)); image.putpixel((1, 1), (255, 255, 255, 255))
        result = prepare_reviewed_ui(image, scale=2, classification='glyph-atlas', alpha_semantics='straight', reviewed=True, glyph_rectangles=[(0, 0, 4, 4)])
        self.assertEqual(result.getpixel((14, 14))[3], 1)

    def test_owned_dump_pipeline_hashes_metrics_before_pack(self):
        import hashlib, json, shutil
        from unittest.mock import patch
        from native_port.workspace import Workspace
        from native_port.texture_ui import prepare_game_ui, validate_ui_pack
        xex = self.root / 'default.xex'; xex.write_bytes(b'owned test executable')
        compressed = self.root / 'gui.lvl_760'; compressed.write_bytes(b'test compressed source')
        raw = bytes(16384); metrics = struct.pack('>HHHHBBbbB3x', 65, 0, 0, 0, 64, 64, 0, 0, 32)
        decoded_data = raw + metrics
        digest = lambda value: hashlib.sha256(value).hexdigest()
        profile = {'schema': 1, 'classification': 'reviewed-ui-straight', 'source_xex_sha256': digest(xex.read_bytes()),
                   'runtime_default_enabled': False, 'source_relative': 'gui.lvl_760',
                   'compressed_size': compressed.stat().st_size, 'compressed_sha256': digest(compressed.read_bytes()),
                   'decoded_size': len(decoded_data), 'decoded_sha256': digest(decoded_data),
                   'raw_offset': 0, 'raw_size': len(raw), 'raw_sha256': digest(raw),
                   'metrics_offset': len(raw), 'metrics_size': len(metrics), 'metrics_sha256': digest(metrics),
                   'original_dds_sha256': digest(self.source.read_bytes()), 'width': 64, 'height': 64,
                   'format': 20, 'endian': 1, 'tiled': True, 'row_pitch_bytes': 512, 'glyph_count': 1,
                   'metrics_stride': 16, 'metrics_schema': 'domyouji-be16-records-v1'}
        (self.root / 'games').mkdir(); (self.root / 'games/green_lantern_ui.json').write_text(json.dumps(profile))
        work = Workspace(self.root / 'work', self.root)
        decoded = work.path('textures/decoded/' + profile['decoded_sha256'] + '.bin')
        decoded.parent.mkdir(parents=True); decoded.write_bytes(decoded_data)
        def untile(argv, **kwargs):
            shutil.copyfile(self.source, argv[-1]); return {'returncode': 0}
        with patch('native_port.texture_pack.SOURCE_XEX_SHA256', profile['source_xex_sha256']), \
                patch('native_port.texture_tools.ensure_texture_tools', return_value={'untile': 'fake', 'decoder': 'fake'}), \
                patch('native_port.tasks.run_process', side_effect=untile):
            result = prepare_game_ui(xex, self.root, work)
            self.assertEqual(validate_ui_pack(result), result)
            compressed.write_bytes(b'changed source')
            with self.assertRaises(PortError): prepare_game_ui(xex, self.root, work)
