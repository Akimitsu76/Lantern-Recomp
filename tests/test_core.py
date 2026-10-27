import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from fixtures import iso, xex
from games.green_lantern import GreenLantern
from native_port.artifacts import verify_host_elf
from native_port.diagnostics import diagnostics
from native_port.errors import PortError
from native_port.modules import require_api
from native_port.pipeline import prepare
from native_port.sources import inspect_source, digest_source
from native_port.tasks import Cancellation, run_process
from native_port.workspace import Workspace, cache_key


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.work = Workspace(self.project / 'work', self.project)

    def source(self, data, name='source.xex'):
        p = self.project / name
        p.write_bytes(data)
        return p

    def assert_code(self, code, action):
        with self.assertRaises(PortError) as e:
            action()
        self.assertEqual(e.exception.code, code)
        return e.exception

    def test_xex_metadata_big_endian(self):
        p = self.source(xex())
        info = inspect_source(p)
        self.assertEqual(info['title_id'], '575207E9')
        self.assertEqual(info['entry_point'], '0x82000000')
        self.assertEqual(info['encryption'], 0)
        self.assertFalse(info['complete_assets'])
        self.assertEqual(p.read_bytes(), xex())

    def test_xex_inline_type_one_is_not_file_pointer(self):
        b = xex()
        struct.pack_into('>II', b, 32, 0x10201, 0xFFFFFF00)
        self.assertEqual(inspect_source(self.source(b))['image_base'], '0xFFFFFF00')

    def test_iso_recognized_by_structure(self):
        p = self.source(iso(), 'source.iso')
        self.assertEqual(inspect_source(p)['format'], 'xdvdfs')

    def test_iso_partition_offset(self):
        p = self.source(bytearray(0xFB20) + iso(), 'source.iso')
        self.assertEqual(inspect_source(p)['partition_offset'], 0xFB20)

    def test_fake_extension(self):
        self.assert_code('BAD_XEX', lambda: inspect_source(self.source(b'a'*100)))
        self.assert_code('UNSUPPORTED_ISO', lambda: inspect_source(self.source(b'a'*100, 'source.iso')))

    def test_missing_path(self):
        self.assert_code('SOURCE_PATH', lambda: inspect_source(self.project / 'absent'))

    def test_directory(self):
        self.assert_code('MISSING_XEX', lambda: inspect_source(self.project))

    @unittest.skipIf(os.name == 'nt', 'POSIX mode bits do not remove Windows read access; Windows ACLs require a separate fixture.')
    def test_unreadable(self):
        p = self.source(xex())
        p.chmod(0)
        self.addCleanup(p.chmod, 0o600)
        self.assert_code('UNREADABLE', lambda: inspect_source(p))

    def test_access_denied_is_rejected_on_each_platform(self):
        p = self.source(xex())
        with patch('native_port.sources.os.access', return_value=False):
            self.assert_code('UNREADABLE', lambda: inspect_source(p))

    def test_truncated_inputs(self):
        self.assert_code('TRUNCATED', lambda: inspect_source(self.source(b'XEX2')))
        p = self.source(iso()[:33*2048], 'source.iso')
        self.assert_code('TRUNCATED', lambda: inspect_source(p))

    def test_invalid_xex_optional_bounds(self):
        b = xex()
        struct.pack_into('>I', b, 28, 0x7FFFFFFF)
        self.assert_code('BAD_XEX', lambda: inspect_source(self.source(b)))

    def test_invalid_xex_count(self):
        b = xex()
        struct.pack_into('>I', b, 20, 0xFFFFFFFF)
        self.assert_code('BAD_XEX', lambda: inspect_source(self.source(b)))

    def test_iso_trailing_magic(self):
        b = iso()
        b[33*2048-1] = 0
        self.assert_code('BAD_ISO', lambda: inspect_source(self.source(b, 'source.iso')))

    def test_module_identity_not_filename(self):
        module = GreenLantern()
        require_api(module)
        self.assertTrue(module.identify(inspect_source(self.source(xex())))['confirmed'])
        self.assertFalse(module.identify({'format': 'xdvdfs'})['confirmed'])
        self.assert_code('WRONG_GAME', lambda: module.identify({'title_id': '00000000'}))
        self.assert_code('NO_NATIVE_BACKEND', lambda: module.build({}))
        self.assert_code('NOT_READY', lambda: module.launch(None))
        module.api_version = 99
        self.assert_code('MODULE_API', lambda: require_api(module))

    def test_workspace_escape_and_symlink(self):
        for relative in ('../escape', '/tmp/escape', '.'):
            self.assert_code('WORKSPACE_ESCAPE', lambda: self.work.path(relative))
        self.work.root.mkdir()
        (self.work.root / 'link').symlink_to(self.project, target_is_directory=True)
        self.assert_code('WORKSPACE_ESCAPE', lambda: self.work.write_json('link/escape', {}))
        self.assert_code('WORKSPACE_ESCAPE', lambda: Workspace(self.project, self.project))

    def test_cache_clear_is_scoped_and_requires_confirmation(self):
        self.work.write_json('cache/v1/item/report.json', {})
        keep = self.work.write_json('reports/keep.json', {})
        self.assert_code('CONFIRM_CACHE', lambda: self.work.clear_cache())
        self.work.clear_cache(confirmed=True)
        self.assertTrue(keep.is_file())
        self.assertFalse(self.work.path('cache/v1').exists())

    def test_cache_clear_rejects_external_symlink(self):
        self.work.root.mkdir()
        (self.work.root / 'cache').symlink_to(self.project, target_is_directory=True)
        self.assert_code('WORKSPACE_ESCAPE', lambda: self.work.clear_cache(confirmed=True))

    def test_cache_key_all_dependencies(self):
        baseline = cache_key('sha', {'v': 1}, {'mode': 1}, {'cc': 1})
        for args in [('changed', {'v': 1}, {'mode': 1}, {'cc': 1}),
                     ('sha', {'v': 2}, {'mode': 1}, {'cc': 1}),
                     ('sha', {'v': 1}, {'mode': 2}, {'cc': 1}),
                     ('sha', {'v': 1}, {'mode': 1}, {'cc': 2})]:
            self.assertNotEqual(baseline, cache_key(*args))

    def test_digest_and_cancel(self):
        p = self.source(xex())
        self.assertEqual(digest_source(p, Cancellation()), hashlib.sha256(xex()).hexdigest())
        cancel = Cancellation()
        cancel.cancel()
        self.assert_code('CANCELLED', lambda: digest_source(p, cancel))

    @patch('native_port.pipeline.diagnostics', return_value={'tools': {}})
    def test_pipeline_stops_at_honest_boundary(self, _):
        p = self.source(xex())
        events = []
        report = prepare(p, self.work, GreenLantern(), emit=events.append)
        self.assertEqual(report['state'], 'blocked')
        self.assertFalse(report['ready'])
        self.assertIsNone(report['artifact'])
        self.assertIn('cmake', report['missing_dependencies'])
        self.assertEqual(events[-1]['state'], 'blocked')
        self.assertEqual(json.loads(self.work.path('reports/latest.json').read_text())['sha256'], report['sha256'])

    def test_pipeline_propagates_and_records_failure(self):
        self.assert_code('BAD_XEX', lambda: prepare(self.source(b'x'*100), self.work, GreenLantern()))
        saved = json.loads(self.work.path('reports/latest.json').read_text())
        self.assertEqual(saved['error']['code'], 'BAD_XEX')
        self.assertFalse(saved['ready'])

    def test_pipeline_cancel(self):
        cancel = Cancellation()
        cancel.cancel()
        self.assert_code('CANCELLED', lambda: prepare(self.source(xex()), self.work, GreenLantern(), cancel))
        self.assertEqual(json.loads(self.work.path('reports/latest.json').read_text())['state'], 'cancelled')

    def test_source_overlap(self):
        p = self.work.path('source.xex')
        p.parent.mkdir()
        p.write_bytes(xex())
        self.assert_code('SOURCE_OVERLAP', lambda: prepare(p, self.work, GreenLantern()))

    def test_process_failure_and_missing_executable(self):
        e = self.assert_code('PROCESS_FAILED', lambda: run_process(
            [sys.executable, '-c', 'import sys; print("diagnostic", file=sys.stderr); sys.exit(7)'],
            self.project, Cancellation()))
        self.assertEqual(e.details['returncode'], 7)
        self.assertIn('diagnostic', e.details['stderr'])
        self.assert_code('PROCESS_START', lambda: run_process(['/no/such/tool'], self.project, Cancellation()))

    def test_running_process_cancellation(self):
        cancel = Cancellation()
        timer = threading.Timer(0.15, cancel.cancel)
        timer.start()
        self.addCleanup(timer.join)
        start = time.monotonic()
        self.assert_code('CANCELLED', lambda: run_process(
            [sys.executable, '-c', 'import time; time.sleep(30)'], self.project, cancel))
        self.assertLess(time.monotonic()-start, 3)

    def test_process_reports_output_before_exit_and_remains_cancellable(self):
        cancel = Cancellation()
        seen = []
        def output(line):
            seen.append(line)
            cancel.cancel()
        start = time.monotonic()
        self.assert_code('CANCELLED', lambda: run_process(
            [sys.executable, '-c', 'import time; print("[1/12] compiling", flush=True); time.sleep(30)'],
            self.project, cancel, on_output=output))
        self.assertEqual(seen, ['[1/12] compiling'])
        self.assertLess(time.monotonic() - start, 3)

    def test_final_output_cancellation_is_not_reported_as_success(self):
        # A fast tool may already have exited when its last output is delivered.
        # Cancellation requested by that callback must still stop its caller.
        cancel = Cancellation()
        seen = []
        def output(line):
            seen.append(line)
            cancel.cancel()
        def exited_process(argv, **options):
            options['stdout'].write(b'completed target\n')
            options['stdout'].flush()
            process = Mock(returncode=0)
            process.poll.return_value = 0
            process.__enter__ = Mock(return_value=process)
            process.__exit__ = Mock(return_value=False)
            return process
        with patch('native_port.tasks.subprocess.Popen', side_effect=exited_process):
            self.assert_code('CANCELLED', lambda: run_process(
                ['synthetic-completed-tool'], self.project, cancel, on_output=output))
        self.assertEqual(seen, ['completed target'])

    def test_process_timeout(self):
        self.assert_code('TIMEOUT', lambda: run_process(
            [sys.executable, '-c', 'import time; time.sleep(30)'], self.project, Cancellation(), timeout=.1))

    @patch('native_port.diagnostics.local_tool', return_value=None)
    @patch('native_port.diagnostics.shutil.which', return_value=None)
    def test_missing_dependencies(self, _, __):
        report = diagnostics()
        self.assertTrue(all(not t['available'] for t in report['tools'].values()))

    def test_artifact_validation(self):
        p = self.source(b'not ELF', 'artifact')
        p.chmod(0o700)
        self.assert_code('BAD_ARTIFACT', lambda: verify_host_elf(p, self.project))
        self.assert_code('ARTIFACT_PATH', lambda: verify_host_elf(p, self.work.root))

    @unittest.skipIf(os.name == 'nt', 'Optional local artifact is a Linux ELF host probe, not a Windows executable.')
    def test_generated_host_artifact_hash(self):
        # Actual artifact test runs after scripts/host_probe.py; skip explicitly if unavailable.
        project = Path(__file__).resolve().parents[1]
        p = project / '.aster/output/aster-host-probe'
        if not p.exists():
            self.skipTest('Execute python3 scripts/host_probe.py para validar ELF real.')
        result = verify_host_elf(p, p.parent)
        self.assertFalse(result['game_ready'])
        self.assert_code('ARTIFACT_CHANGED', lambda: verify_host_elf(p, p.parent, 'wrong'))

    @patch('tempfile.mkstemp', side_effect=PermissionError('write denied'))
    def test_workspace_write_error_is_structured(self, _):
        self.assert_code('WORKSPACE_WRITE', lambda: self.work.write_json('reports/test.json', {}))

    def test_encrypted_basic_xex_still_inspectable(self):
        b = xex()
        struct.pack_into('>IHHII', b, 96, 16, 1, 1, 512, 256)
        info = inspect_source(self.source(b))
        self.assertEqual(info['code_access'], 'encrypted')
        self.assertEqual(info['basic_compression']['expanded_bytes'], 768)
        self.assertEqual(info['basic_compression']['stored_bytes'], 512)

    def test_truncated_basic_compression_data(self):
        b = xex()
        struct.pack_into('>IHHII', b, 96, 16, 1, 1, 1024, 0)
        self.assert_code('TRUNCATED', lambda: inspect_source(self.source(b)))

    @patch('native_port.pipeline.diagnostics', return_value={'tools': {}})
    def test_encrypted_pipeline_names_actual_blocker(self, _):
        b = xex()
        struct.pack_into('>IHH', b, 96, 8, 1, 0)
        result = prepare(self.source(b), self.work, GreenLantern())
        self.assertEqual(result['blocker'], 'XEX_ENCRYPTED')
        self.assertFalse(result['ready'])

    def test_import_library_metadata_and_invalid_bounds(self):
        from native_port.sources import inspect_imports
        blob = bytearray(12+8+44)
        struct.pack_into('>III', blob, 0, len(blob), 8, 1)
        blob[12:20] = b'test\x00\x00\x00\x00'
        struct.pack_into('>I', blob, 20, 44)
        struct.pack_into('>IIIHH', blob, 44, 1, 2, 1, 0, 1)
        result = inspect_imports(blob)
        self.assertEqual(result[0]['name'], 'test')
        self.assertEqual(result[0]['import_record_count'], 1)
        self.assertFalse(result[0]['resolved_ordinals'])
        struct.pack_into('>H', blob, 58, 65535)
        self.assert_code('BAD_XEX', lambda: inspect_imports(blob))


if __name__ == '__main__':
    unittest.main()
