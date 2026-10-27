import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from scripts.make_xenon_fixture import make
from native_port.analysis_state import verified_analysis
from native_port.errors import PortError
from native_port.pe import inspect_pe,normalize_memory_pe
from native_port.tasks import Cancellation,run_process
from native_port.workspace import Workspace
from native_port.xenon import analyze
from fixtures import xex

PROJECT=Path(__file__).resolve().parents[1]


class PETests(unittest.TestCase):
    def test_synthetic_memory_image(self):
        _,pe=make()
        normal,info=normalize_memory_pe(pe)
        self.assertEqual(info['entry_point'],0x82001000)
        self.assertEqual(info['architecture'],'PowerPC big-endian')
        self.assertEqual(normal[0x1000:0x1004],pe[0x1000:0x1004])

    def test_section_repacking_uses_rva_not_raw_pointer(self):
        _,raw=make();b=bytearray(raw)
        struct.pack_into('<I',b,0x98+224+20,0x200)
        out,info=normalize_memory_pe(bytes(b))
        self.assertEqual(out[0x200:0x204],raw[0x1000:0x1004])
        self.assertEqual(len(out),0x204)

    def test_larger_size_of_image_is_allowed_if_initialized_regions_present(self):
        _,raw=make();b=bytearray(raw)
        struct.pack_into('<I',b,0x98+56,0x3000)
        out,info=normalize_memory_pe(bytes(b))
        self.assertEqual(info['image_size'],0x3000)
        self.assertEqual(info['decoded_size'],0x2000)

    def test_bad_headers_truncation_and_overlap(self):
        _,raw=make()
        for data in (b'MZ',b'bad'*50,raw[:512]):
            with self.assertRaises(PortError): normalize_memory_pe(data)
        b=bytearray(raw);struct.pack_into('<I',b,0x98+224+20,0x100)
        with self.assertRaises(PortError):normalize_memory_pe(bytes(b))
        b=bytearray(raw);struct.pack_into('<H',b,0x84,0x8664)
        with self.assertRaises(PortError):inspect_pe(bytes(b))

    def test_explicit_decoding_authorization(self):
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory);p=project/'encrypted.xex';b=xex()
            struct.pack_into('>H',b,100,1);p.write_bytes(b)
            with self.assertRaises(PortError) as e:
                analyze(p,Workspace(project/'work',project))
            self.assertEqual(e.exception.code,'DECODE_AUTH_REQUIRED')

    def test_analysis_requires_exact_source_and_artifact_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory);work=Workspace(project/'work',project)
            data=work.path('analysis/example.pe');data.parent.mkdir(parents=True);data.write_bytes(b'example')
            report=dict(schema=1,state='decoded-and-validated',source_sha256='known',
                        normalized_path=str(data),normalized_sha256=hashlib.sha256(b'example').hexdigest(),
                        imports={'unique_apis':1},game_ready=True)
            work.write_json('reports/xenon-analysis.json',report)
            self.assertIsNone(verified_analysis(work,'wrong-source'))
            self.assertFalse(verified_analysis(work,'known')['game_ready'])
            data.write_bytes(b'tampered')
            self.assertIsNone(verified_analysis(work,'known'))

    def test_analysis_rejects_external_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory);work=Workspace(project/'work',project)
            p=project/'external.pe';p.write_bytes(b'example')
            work.write_json('reports/xenon-analysis.json',dict(schema=1,state='decoded-and-validated',
                source_sha256='known',normalized_path=str(p),normalized_sha256=hashlib.sha256(b'example').hexdigest()))
            self.assertIsNone(verified_analysis(work,'known'))

    @unittest.skipIf(os.name == 'nt', 'Optional local decoder fixture is built for Linux; portable parser tests still run.')
    def test_real_decoder_on_original_synthetic_fixture(self):
        decoder=PROJECT/'.aster/build/xenon/aster-xex-inspect'
        if not decoder.exists():self.skipTest('Local decoder not built')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);p=root/'fixture.xex';output=root/'decoded.pe'
            x,expected=make();p.write_bytes(x)
            r=run_process([str(decoder),str(p),str(output)],PROJECT,Cancellation())
            self.assertFalse(json.loads(r['stdout'])['executed_game'])
            self.assertEqual(output.read_bytes(),expected)
            self.assertEqual(p.read_bytes(),x)

    @unittest.skipIf(os.name == 'nt', 'Optional local native leaf experiment is a Linux ELF executable.')
    def test_native_leaf_artifact_semantics(self):
        binary=PROJECT/'.aster/analysis/green-lantern/leaf-native-probe'
        if not binary.exists():self.skipTest('Native leaf experiment not built')
        report=json.loads(run_process([str(binary)],PROJECT,Cancellation())['stdout'])
        self.assertEqual(report['native_cases_passed'],10000)
        self.assertFalse(report['game_ready'])
