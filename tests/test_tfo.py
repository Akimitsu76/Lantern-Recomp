"""Original synthetic TFO records: candidate bounds/exclusions, never game assets."""
import hashlib
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from native_port.errors import PortError
from native_port.tasks import Cancellation
from native_port.tfo import HEADER_BYTES, LAYOUT_SIGNATURE, iter_texture_descriptors


def record(name='\\gl\\materials\\test\\stone_d.tfo', *, width=128, height=128,
           engine_format=1, mip_count=None):
    header = bytearray(bytes.fromhex(
        '00000000 00000001 00800080 00010001 00080000 00000004 '
        '00000002 00000001 00000000 00000001 00000002 00000004 '
        '00000000 00030000 00000000 0000001e 00000080 00000080') + bytes(76))
    assert len(header) == 148
    struct.pack_into('>HH', header, 8, width, height)
    struct.pack_into('>II', header, 64, width, height)
    struct.pack_into('>H', header, 16, mip_count or max(width, height).bit_length())
    struct.pack_into('>I', header, 28, engine_format)
    block = 8 if engine_format == 1 else 16
    raw_size = ((width + 127) // 128) * ((height + 127) // 128) * 32 * 32 * block
    return bytes(header) + name.encode('ascii') + b'\0' + b'\x5a' * raw_size


class TfoDescriptorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='aster-tfo-test-')
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'original decoded.bin'

    def parse(self, data):
        self.path.write_bytes(data)
        return list(iter_texture_descriptors(self.path))

    def test_valid_bc1_is_unreviewed_and_exactly_bounded(self):
        source = record()
        result = self.parse(source)
        self.assertEqual(len(result), 1)
        value = result[0]
        self.assertEqual(value['offset'], 0)
        self.assertEqual(value['raw_offset'], len(source) - 8192)
        self.assertEqual(value['raw_size'], 8192)
        self.assertEqual((value['width'], value['height'], value['format'], value['mip_count']), (128, 128, 18, 8))
        self.assertEqual(value['derived_row_pitch_bytes'], 256)
        self.assertEqual(value['header_sha256'], hashlib.sha256(source[:HEADER_BYTES]).hexdigest())
        self.assertEqual(value['header_hex'], source[:HEADER_BYTES].hex())
        self.assertEqual(value['layout_signature'], LAYOUT_SIGNATURE)
        self.assertFalse(value['reviewed'])
        self.assertFalse(value['approved_for_runtime'])
        self.assertNotIn('tiled', value)
        self.assertNotIn('endian', value)
        self.assertEqual(self.path.read_bytes(), source)

    def test_bc3_rectangle_and_small_aligned_base(self):
        for width, height, fmt, expected_size, expected_pitch in [
                (128, 256, 5, 32768, 512), (64, 64, 1, 8192, 256),
                (2048, 1024, 1, 1048576, 4096)]:
            with self.subTest(width=width, height=height):
                result = self.parse(record(width=width, height=height, engine_format=fmt))[0]
                self.assertEqual(result['raw_size'], expected_size)
                self.assertEqual(result['derived_row_pitch_bytes'], expected_pitch)
                self.assertEqual(result['format'], 18 if fmt == 1 else 20)

    def test_unicode_decoded_file_path(self):
        folder=Path(self.directory.name)/'usuário_日本_🚀 com espaços'
        folder.mkdir()
        self.path=folder/'texturas_ação_纹理.decoded'
        self.assertEqual(len(self.parse(record())),1)

    def test_multiple_records_and_uninterpreted_following_bytes(self):
        first, second = record(), record('\\gl\\objects\\props\\rock_d.tfo', engine_format=5)
        between = b'unknown bytes after base; not claimed as mip storage'
        result = self.parse(b'prefix' + first + between + second + b'trailing data')
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['offset'], 6)
        self.assertEqual(result[1]['offset'], 6 + len(first) + len(between))
        self.assertFalse(any('mip_offset' in k or 'payload_size' in k for k in result[0]))

    def test_dimensions_must_agree_and_be_supported_powers(self):
        original = record()
        bad = []
        mismatch = bytearray(original); struct.pack_into('>I', mismatch, 64, 256); bad.append(mismatch)
        for width, height in [(63,128),(96,128),(4096,128),(128,0)]:
            changed=bytearray(original)
            struct.pack_into('>HH',changed,8,width,height)
            struct.pack_into('>II',changed,64,width,height)
            bad.append(changed)
        for data in bad:
            with self.subTest(header=data[:72].hex()): self.assertEqual(self.parse(data), [])

    def test_partial_and_base_only_mips_are_excluded(self):
        for count in (1, 7, 9):
            with self.subTest(count=count):
                self.assertEqual(self.parse(record(mip_count=count)), [])

    def test_normal_header_unknown_flags_and_formats_are_excluded(self):
        original = record()
        for offset, value in [(52,0x00020300),(52,0x40000),(20,5),(24,3),(36,0),(60,31),(28,3)]:
            changed=bytearray(original);struct.pack_into('>I',changed,offset,value)
            with self.subTest(offset=offset,value=value): self.assertEqual(self.parse(changed), [])
        changed=bytearray(original);changed[100]=1
        self.assertEqual(self.parse(changed), [])

    def test_normal_specular_ui_unknown_and_traversal_names_are_excluded(self):
        for name in ['\\gl\\materials\\test\\stone_n.tfo','\\gl\\materials\\test\\stone_s.tfo',
                     '\\gl\\materials\\test\\stone.tfo','\\gl\\textures\\interface\\stone_d.tfo',
                     '\\gl\\textures\\ui\\stone_d.tfo','\\gl\\textures\\fx\\flare_d.tfo',
                     '\\gl\\unknown\\stone_d.tfo','\\other\\materials\\stone_d.tfo',
                     '\\gl\\materials\\..\\stone_d.tfo','\\gl\\materials/stone_d.tfo']:
            with self.subTest(name=name): self.assertEqual(self.parse(record(name)), [])

    def test_truncated_header_name_or_base_is_excluded(self):
        data=record()
        for content in (data[1:],data[:-1],data[:147],b'\\gl\\materials\\stone_d.tfo\0'):
            with self.subTest(length=len(content)): self.assertEqual(self.parse(content), [])
        oversized='\\gl\\materials\\'+'a'*512+'_d.tfo'
        self.assertEqual(self.parse(record(oversized)), [])

    def test_marker_at_scan_boundary_is_not_lost_or_duplicated(self):
        data=record()
        marker=data.index(b'.tfo\0')
        for remainder in range(5):
            with self.subTest(remainder=remainder), patch('native_port.tfo._SCAN_CHUNK', 256):
                padding=b'x'*((255-marker-remainder)%256)
                result=self.parse(padding+data)
                self.assertEqual(len(result),1)
                self.assertEqual(result[0]['offset'],len(padding))

    def test_cancellation_during_iteration_preserves_file(self):
        data=record()+record('\\gl\\materials\\test\\second_d.tfo')
        self.path.write_bytes(data);cancel=Cancellation()
        iterator=iter_texture_descriptors(self.path,cancel)
        next(iterator);cancel.cancel()
        with self.assertRaises(PortError) as error: next(iterator)
        self.assertEqual(error.exception.code,'CANCELLED')
        self.assertEqual(self.path.read_bytes(),data)

    def test_file_and_search_limits(self):
        self.path.write_bytes(record())
        with patch('native_port.tfo.MAX_DECODED_BYTES', 100):
            with self.assertRaises(PortError): list(iter_texture_descriptors(self.path))
        self.path.write_bytes(b'x'*148+b'.tfo\0'*3)
        with patch('native_port.tfo.MAX_NAME_MARKERS',1):
            with self.assertRaises(PortError): list(iter_texture_descriptors(self.path))
        self.path.write_bytes(record()+record())
        with patch('native_port.tfo.MAX_DESCRIPTORS',1):
            with self.assertRaises(PortError): list(iter_texture_descriptors(self.path))

    def test_source_changes_during_iteration_are_detected(self):
        data=record()+record('\\gl\\materials\\test\\second_d.tfo')
        self.path.write_bytes(data)
        iterator=iter_texture_descriptors(self.path)
        next(iterator)
        # Windows forbids truncating an open mapped file. A timestamp change
        # exercises the same identity guard portably, without resizing mappings.
        before=self.path.stat()
        os.utime(self.path, ns=(before.st_atime_ns,before.st_mtime_ns+1000000000))
        with self.assertRaises(PortError): next(iterator)

    @unittest.skipIf(__import__('os').name=='nt','Windows symlink privilege not assumed')
    def test_symlink_container_is_rejected(self):
        actual=self.path.with_suffix('.actual');actual.write_bytes(record())
        self.path.symlink_to(actual)
        with self.assertRaises(PortError): list(iter_texture_descriptors(self.path))


if __name__ == '__main__':
    unittest.main()
