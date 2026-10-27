"""Portable texture-helper path tests. Supply ASTER_UNTILE_HELPER explicitly.

The fixture is synthetic BC1 block data; it contains no original game assets.
"""
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest


class UntileUnicodePathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configured = os.environ.get('ASTER_UNTILE_HELPER')
        if not configured:
            raise unittest.SkipTest('set ASTER_UNTILE_HELPER to the compiled untile helper')
        cls.binary = str(Path(configured).absolute())
        if not Path(cls.binary).is_file():
            raise RuntimeError('ASTER_UNTILE_HELPER does not name a file')

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='aster-untile-unicode-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name) / 'usuário_日本_🚀 com espaços'
        self.base.mkdir()
        self.source = self.base / 'textura_ação_纹理_😀.bin'
        self.output = self.base / 'saída_超解像_🌟.dds'
        self.raw = bytes(range(256)) * 32
        self.source.write_bytes(self.raw)

    def invoke(self, width='128'):
        return subprocess.run([self.binary, str(self.source), width, '128', '256',
                               '18', '0', '0', str(self.output)],
                              capture_output=True, text=True, timeout=15)

    def test_unicode_paths_preserve_original_bc1_pixels(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        dds = self.output.read_bytes()
        self.assertEqual(dds[:4], b'DDS ')
        self.assertEqual(struct.unpack_from('<II', dds, 12), (128, 128))
        self.assertEqual(dds[84:88], b'DXT1')
        self.assertEqual(dds[128:], self.raw)
        self.assertEqual(self.source.read_bytes(), self.raw)

    def test_existing_unicode_output_is_preserved(self):
        self.output.write_bytes(b'preserve existing Unicode output')
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_bytes(), b'preserve existing Unicode output')

    def test_truncated_unicode_source_creates_no_output(self):
        self.source.write_bytes(b'\0' * 8)
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_non_ascii_numerals_are_rejected(self):
        for width in ('١٢٨', '１２８'):
            with self.subTest(width=width):
                result = self.invoke(width=width)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
