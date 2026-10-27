"""Synthetic framed-LZX decoder checks; no game data or inferred XCTD headers.

Set ASTER_XCTD_DECODER to the compiled helper executable and run this file.
"""
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest


def uncompressed_lzx(data):
    """One regular LZX uncompressed block (1..32768 bytes), no Intel filter."""
    assert 1 <= len(data) <= 32768
    bits = '0' + '011' + format(len(data) >> 8, '016b') + format(len(data) & 255, '08b')
    bits = bits.ljust((len(bits) + 15) // 16 * 16, '0')
    stream = b''.join(struct.pack('<H', int(bits[i:i + 16], 2))
                      for i in range(0, len(bits), 16))
    stream += struct.pack('<III', 1, 1, 1) + data
    return stream + (b'\0' if len(data) % 2 else b'')


def frame(stream, chunk_size=65535):
    return b''.join(struct.pack('>H', len(stream[i:i + chunk_size]))
                    + stream[i:i + chunk_size]
                    for i in range(0, len(stream), chunk_size))


class FramedLzxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configured = os.environ.get('ASTER_XCTD_DECODER')
        if not configured:
            raise unittest.SkipTest('set ASTER_XCTD_DECODER to the compiled helper')
        cls.binary = str(Path(configured).absolute())
        if not Path(cls.binary).is_file():
            raise RuntimeError('ASTER_XCTD_DECODER does not name a file')

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='aster-framed-lzx-')
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.source = self.base / 'source.lzx'
        self.output = self.base / 'decoded.bin'

    def run_helper(self, content, size=36, offset=0, window=17, output=None):
        self.source.write_bytes(content)
        return subprocess.run([self.binary, str(self.source), str(output or self.output),
                               '--payload-offset', str(offset), '--uncompressed-size',
                               str(size), '--window-bits', str(window)],
                              capture_output=True, text=True, timeout=10)

    def test_valid_odd_even_and_multi_chunk(self):
        for n, chunk_size, offset in [(1, 65535, 0), (36, 9, 20), (32767, 7000, 0),
                                      (32768, 8191, 20)]:
            with self.subTest(size=n, chunk_size=chunk_size, offset=offset):
                data = bytes((i * 17 + 3) & 255 for i in range(n))
                content = bytes(range(offset)) + frame(uncompressed_lzx(data), chunk_size)
                result = self.run_helper(content, size=n, offset=offset)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.output.read_bytes(), data)
                record = json.loads(result.stdout)
                self.assertEqual(record['profile'], 'explicit-be16-framed-lzx')
                self.assertEqual(record['output_bytes'], n)
                self.assertEqual(record['payload_offset'], offset)
                self.output.unlink()

    def test_malformed_framing_creates_no_output(self):
        for content in (b'', b'\x00', b'\x00\x00', b'\x00\x04abc',
                        b'\x00\x01x\x00', b'\xff\xffabc'):
            with self.subTest(content=content):
                result = self.run_helper(content)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.output.exists())

    def test_invalid_lzx_creates_no_output(self):
        for payload in (b'\xff', b'\0\0\0\0', bytes(range(64))):
            with self.subTest(payload=payload):
                result = self.run_helper(frame(payload))
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.output.exists())

    def test_bounds_and_numeric_syntax(self):
        good = frame(uncompressed_lzx(b'x' * 36))
        cases = [dict(size=0), dict(size=268435457), dict(size='-1'), dict(size='36junk'),
                 dict(size='+36'), dict(size=' 36'), dict(size='٣٦'), dict(size='３６'), dict(offset=-1), dict(offset=len(good)),
                 dict(offset=67108865), dict(window=14), dict(window=22)]
        for options in cases:
            with self.subTest(options=options):
                result = self.run_helper(good, **options)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.output.exists())

    def test_output_size_mismatch_does_not_publish(self):
        for size in (35, 37):
            with self.subTest(size=size):
                result = self.run_helper(frame(uncompressed_lzx(b'x' * 36)), size=size)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.output.exists())

    def test_existing_output_preserved(self):
        self.output.write_bytes(b'preserve existing data')
        result = self.run_helper(frame(uncompressed_lzx(b'x' * 36)))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_bytes(), b'preserve existing data')

    @unittest.skipIf(os.name == 'nt', 'Windows symlink privilege is not assumed')
    def test_output_symlink_preserved(self):
        target = self.base / 'valuable.bin'
        target.write_bytes(b'preserve existing data')
        self.output.symlink_to(target)
        result = self.run_helper(frame(uncompressed_lzx(b'x' * 36)))
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.output.is_symlink())
        self.assertEqual(target.read_bytes(), b'preserve existing data')

    def test_input_cannot_be_output(self):
        content = frame(uncompressed_lzx(b'x' * 36))
        result = self.run_helper(content, output=self.source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.source.read_bytes(), content)

    def test_unicode_input_output_paths(self):
        folder = self.base / 'usuário_日本_🚀 com espaços'
        folder.mkdir()
        self.source = folder / 'origem_ação_纹理_😀.lzx'
        self.output = folder / 'saída_超解像_🌟.bin'
        data = b'Unicode path roundtrip.'
        result = self.run_helper(frame(uncompressed_lzx(data)), size=len(data))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_bytes(), data)
        # Refusing an existing Unicode path must preserve it byte for byte.
        result = self.run_helper(frame(uncompressed_lzx(data)), size=len(data))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_bytes(), data)

    def test_auto_header_roundtrip(self):
        data = b'Corroborated narrow header test.'
        content = bytes.fromhex('0ff512ed010000001234567800000062')
        content += struct.pack('>I', len(data) << 12) + frame(uncompressed_lzx(data))
        self.source.write_bytes(content)
        result = subprocess.run([self.binary, str(self.source), str(self.output)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_bytes(), data)
        record = json.loads(result.stdout)
        self.assertEqual(record['profile'], 'xctd-v1-single-segment-flags-0x62')
        self.assertFalse(record['container_checksum_verified'])

    def test_auto_header_rejects_unknown_or_truncated_layout(self):
        data = b'Corroborated narrow header test.'
        good = bytes.fromhex('0ff512ed010000001234567800000062')
        good += struct.pack('>I', len(data) << 12) + frame(uncompressed_lzx(data))
        bad = [good[:19], good[:20], b'WRONGMAG' + good[8:]]
        for offset, value in [(4, 2), (6, 1), (12, 0x40), (15, 0xa2), (19, 1)]:
            changed = bytearray(good); changed[offset] = value; bad.append(bytes(changed))
        changed = bytearray(good); changed[16:20] = b'\0' * 4; bad.append(bytes(changed))
        for content in bad:
            with self.subTest(header=content[:20]):
                self.source.write_bytes(content)
                result = subprocess.run([self.binary, str(self.source), str(self.output)],
                                        capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.output.exists())

    def test_input_size_limit_rejected_without_output(self):
        with self.source.open('wb') as source:
            source.seek(64 * 1024 * 1024)
            source.write(b'\0')
        result = subprocess.run([self.binary, str(self.source), str(self.output)],
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_invalid_argument_count(self):
        result = subprocess.run([self.binary, str(self.source), str(self.output), "--bad"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn('Other layouts require explicit research parameters', result.stderr)
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
