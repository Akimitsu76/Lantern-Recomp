"""Bounded XCTD planning/publication tests with original synthetic LZX blocks."""
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from native_port.errors import PortError
from native_port.tasks import Cancellation
from native_port.xctd import SLOT_BYTES, decode_container


def _lzx(data):
    bits = '0' + '011' + format(len(data) >> 8, '016b') + format(len(data) & 255, '08b')
    bits = bits.ljust((len(bits) + 15) // 16 * 16, '0')
    raw = b''.join(struct.pack('<H', int(bits[i:i + 16], 2))
                   for i in range(0, len(bits), 16))
    return raw + struct.pack('<III', 1, 1, 1) + data + (b'\0' if len(data) % 2 else b'')


def _framed(raw):
    # Small framing chunks exercise concatenation independently of LZX blocks.
    return b''.join(struct.pack('>H', len(raw[i:i + 17])) + raw[i:i + 17]
                    for i in range(0, len(raw), 17))


def _container(parts, bits=20, upper=0x70000000):
    flags = upper | (len(parts) << 6) | 0x22 | (0x00400000 if bits == 32 else 0)
    width = ((len(parts) * bits + 31) // 32) * 4
    table = 0
    for part in parts:
        table = (table << bits) | len(part)
    table <<= width * 8 - len(parts) * bits
    result = bytearray(bytes.fromhex('0ff512ed0100000012345678') + struct.pack('>I', flags)
                       + table.to_bytes(width, 'big'))
    for index, part in enumerate(parts):
        if index:
            result.extend(b'\0' * (index * SLOT_BYTES - len(result)))
        result.extend(_framed(_lzx(part)))
    return bytes(result)


class XctdTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='aster-xctd-tests-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source, self.output = self.root / 'source.lvl', self.root / 'result.decoded'
        self.helper = self.root / 'trusted-helper'
        self.helper.write_bytes(b'synthetic helper placeholder')
        self.parts = [b'Original synthetic color block.\n', b'Second synthetic block!\n']
        self.source.write_bytes(_container(self.parts))
        self.lookup = {_framed(_lzx(data)): data for data in self.parts}

    def _run_fixture_decoder(self, argv, cwd, cancel, timeout):
        """Stand-in for the independently tested native decoder, not archive parsing."""
        self.assertEqual(argv[-6:], ['--payload-offset', '0', '--uncompressed-size',
                                    argv[-3], '--window-bits', '17'])
        cancel.check()
        raw = Path(argv[1]).read_bytes()
        data = self.lookup[raw]
        self.assertEqual(int(argv[-3]), len(data))
        Path(argv[2]).write_bytes(data)
        return {'stdout': json.dumps({'profile': 'explicit-be16-framed-lzx',
                                     'input_bytes': len(raw), 'output_bytes': len(data),
                                     'chunks': sum(1 for i in range(0, len(_lzx(data)), 17)),
                                     'window_bits': 17, 'reset_interval': 0})}

    def decode(self, **kwargs):
        return decode_container(self.source, self.output, self.helper,
                                expected_source_sha256=hashlib.sha256(self.source.read_bytes()).hexdigest(),
                                **kwargs)

    def assert_no_partial(self):
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob('.aster-xctd-*')))

    def test_valid_multi_20_and_32_bit_tables(self):
        for bits in (20, 32):
            with self.subTest(bits=bits):
                original = _container(self.parts, bits=bits)
                self.source.write_bytes(original)
                events = []
                with patch('native_port.xctd.run_process', side_effect=self._run_fixture_decoder) as external:
                    report = self.decode(emit=events.append,
                                         expected_output_sha256=hashlib.sha256(b''.join(self.parts)).hexdigest())
                self.assertEqual(external.call_count, 2)
                self.assertEqual(self.output.read_bytes(), b''.join(self.parts))
                self.assertEqual(self.source.read_bytes(), original)
                self.assertEqual(report['size_table_bits'], bits)
                self.assertEqual(report['segment_count'], 2)
                self.assertFalse(report['container_checksum_verified'])
                self.assertTrue(report['source_sha256_pinned'])
                self.assertEqual(events[-1]['completed'], sum(map(len, self.parts)))
                self.assertEqual(events[-1]['total'], sum(map(len, self.parts)))
                self.assertGreater(report['segments'][0]['zero_padding_bytes'], 0)
                self.output.unlink()

    def test_requires_source_hash_or_explicit_research(self):
        with self.assertRaises(PortError):
            decode_container(self.source, self.output, self.helper)
        with patch('native_port.xctd.run_process', side_effect=self._run_fixture_decoder):
            result = decode_container(self.source, self.output, self.helper, allow_unverified_source=True)
        self.assertTrue(result['research_opt_in'])
        self.assertFalse(result['source_sha256_pinned'])

    def test_wrong_source_hash_prevents_subprocess(self):
        with patch('native_port.xctd.run_process') as external:
            with self.assertRaises(PortError):
                decode_container(self.source, self.output, self.helper, expected_source_sha256='0' * 64)
            external.assert_not_called()
        self.assert_no_partial()

    def test_wrong_output_hash_never_publishes(self):
        with patch('native_port.xctd.run_process', side_effect=self._run_fixture_decoder):
            with self.assertRaises(PortError):
                self.decode(expected_output_sha256='0' * 64)
        self.assert_no_partial()

    def test_header_and_table_validation(self):
        original = _container(self.parts)
        cases = []
        for offset, value in [(0, 0), (4, 2), (7, 1), (15, 0x21), (13, 0x80)]:
            changed = bytearray(original); changed[offset] = value; cases.append(changed)
        # Claim a single segment for a physically two-slot file.
        changed = bytearray(original); changed[12:16] = struct.pack('>I', 0x62); cases.append(changed)
        # Two20-bit sizes leave24low table padding bits.
        changed = bytearray(original); changed[23] = 1; cases.append(changed)
        # Output zero for first segment.
        changed = bytearray(original); changed[16:19] = b'\0\0\0'; cases.append(changed)
        for content in cases:
            with self.subTest(header=content[:24]):
                self.source.write_bytes(content)
                with patch('native_port.xctd.run_process') as external:
                    with self.assertRaises(PortError): self.decode()
                    external.assert_not_called()
                self.assert_no_partial()

    def test_nonzero_slot_padding_rejected(self):
        changed = bytearray(self.source.read_bytes()); changed[SLOT_BYTES - 1] = 1
        self.source.write_bytes(changed)
        with patch('native_port.xctd.run_process') as external:
            with self.assertRaises(PortError): self.decode()
            external.assert_not_called()
        self.assert_no_partial()

    def test_truncated_frame_in_final_slot_rejected(self):
        changed = bytearray(self.source.read_bytes()); changed[SLOT_BYTES:SLOT_BYTES + 2] = b'\xff\xff'
        self.source.write_bytes(changed)
        with patch('native_port.xctd.run_process', side_effect=self._run_fixture_decoder):
            with self.assertRaises(PortError): self.decode()
        self.assert_no_partial()

    def test_bounded_input_output_and_segments(self):
        for limit, value in [('MAX_INPUT_BYTES', 20), ('MAX_OUTPUT_BYTES', 1),
                             ('MAX_SEGMENTS', 1), ('MAX_SEGMENT_OUTPUT_BYTES', 1)]:
            with self.subTest(limit=limit), patch('native_port.xctd.' + limit, value):
                with self.assertRaises(PortError): self.decode()
                self.assert_no_partial()

    def test_cancellation_cleans_only_owned_temp(self):
        cancel = Cancellation()
        valuable = self.root / '.aster-xctd-existing-user-dir'; valuable.mkdir()
        (valuable / 'keep').write_text('preserve')
        def progress(event):
            if event['stage'] == 'xctd-decode': cancel.cancel()
        with patch('native_port.xctd.run_process', side_effect=self._run_fixture_decoder):
            with self.assertRaises(PortError) as error: self.decode(cancel=cancel, emit=progress)
        self.assertEqual(error.exception.code, 'CANCELLED')
        self.assertFalse(self.output.exists())
        self.assertEqual((valuable / 'keep').read_text(), 'preserve')
        self.assertEqual(list(self.root.glob('.aster-xctd-*')), [valuable])

    def test_existing_output_and_publication_race_preserved(self):
        self.output.write_bytes(b'preserve')
        with self.assertRaises(PortError): self.decode()
        self.assertEqual(self.output.read_bytes(), b'preserve')
        self.output.unlink()
        def race(event):
            if event.get('segment') == 2: self.output.write_bytes(b'external writer')
        with patch('native_port.xctd.run_process', side_effect=self._run_fixture_decoder):
            with self.assertRaises(PortError): self.decode(emit=race)
        self.assertEqual(self.output.read_bytes(), b'external writer')

    @unittest.skipIf(os.name == 'nt', 'Windows symlink privilege not assumed')
    def test_symlink_output_refused(self):
        target = self.root / 'valuable'; target.write_bytes(b'preserve')
        self.output.symlink_to(target)
        with self.assertRaises(PortError): self.decode()
        self.assertEqual(target.read_bytes(), b'preserve')
        self.assertTrue(self.output.is_symlink())

    def test_source_mutation_during_decode_never_publishes(self):
        def mutate(event):
            if event.get('segment') == 2:
                self.source.write_bytes(self.source.read_bytes() + b'\0')
        with patch('native_port.xctd.run_process', side_effect=self._run_fixture_decoder):
            with self.assertRaises(PortError): self.decode(emit=mutate)
        self.assert_no_partial()

    def test_malformed_helper_record_never_publishes(self):
        for stdout in ('[]', 'garbage', '{}'):
            with self.subTest(stdout=stdout):
                with patch('native_port.xctd.run_process', return_value={'stdout': stdout}):
                    with self.assertRaises(PortError): self.decode()
                self.assert_no_partial()

    @unittest.skipUnless(os.environ.get('ASTER_XCTD_DECODER'), 'set ASTER_XCTD_DECODER for native integration')
    def test_native_helper_multi_container_integration(self):
        self.helper = Path(os.environ['ASTER_XCTD_DECODER']).absolute()
        result = self.decode(expected_output_sha256=hashlib.sha256(b''.join(self.parts)).hexdigest())
        self.assertEqual(self.output.read_bytes(), b''.join(self.parts))
        self.assertEqual(result['segment_count'], 2)


if __name__ == '__main__':
    unittest.main()
