import unittest

from scripts.inspect_texture_capture import validate_metadata


class TextureInspectionValidationTests(unittest.TestCase):
    def setUp(self):
        self.raw = bytes(8192)
        self.meta = dict(schema=1, purpose='inspection-only', gpu_written_pages=False,
                         width=128, height=128, base_row_pitch_bytes=256, format=18,
                         endian=2, base_size=len(self.raw), tiled=True, packed_level=3)

    def test_accepts_bounded_original_compressed_base(self):
        validate_metadata(self.meta, self.raw)
        other = dict(self.meta, format=20, endian=3)
        validate_metadata(other, self.raw)

    def test_rejects_gpu_authored_or_unverified_snapshot(self):
        for value in (True, None, 0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_metadata(dict(self.meta, gpu_written_pages=value), self.raw)

    def test_rejects_non_compressed_and_invalid_layouts(self):
        for updates in ({'format': 6}, {'width': 8192}, {'height': 0},
                        {'endian': 4}, {'tiled': 1}, {'packed_level': 0},
                        {'base_size': 8191}, {'width': True}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                validate_metadata(dict(self.meta, **updates), self.raw)

    def test_rejects_unrelated_json_and_raw_length_mismatch(self):
        for updates in ({'schema': 2}, {'purpose': 'replacement'}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                validate_metadata(dict(self.meta, **updates), self.raw)
        with self.assertRaises(ValueError):
            validate_metadata(self.meta, self.raw[:-1])


if __name__ == '__main__':
    unittest.main()
