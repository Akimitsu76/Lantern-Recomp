"""Production inference resume semantics; synthetic images and isolated caches only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from native_port.errors import PortError
from native_port.locking import lock_session
from native_port.tasks import Cancellation
from native_port.texture_enhance import _master_inference, sha
from native_port.workspace import Workspace


class TextureInferenceResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.work = Workspace(self.root / '.aster', self.root)
        self.source = self.root / 'original.png'
        self.original = Image.new('RGB', (64, 64), (30, 70, 120))
        self.original.save(self.source)
        self.identity = {'schema': 1, 'original': 'synthetic-source', 'model': 'synthetic-model', 'inference_scale': 4}
        key = hashlib.sha256(json.dumps(self.identity, sort_keys=True).encode()).hexdigest()[:24]
        self.output = self.work.path('textures/inference/' + key)
        self.output.mkdir(parents=True)
        self.lock = self.output / '.inference.lock'

    def inference(self, argv, *args, **kwargs):
        Image.new('RGB', (256, 256), (40, 80, 130)).save(argv[argv.index('-o') + 1])
        return {'stdout': 'synthetic inference', 'stderr': ''}

    def prepare(self, cancel=None):
        return _master_inference(self.source, self.original, self.identity, self.root, self.work,
                                 Path('synthetic-engine'), Path('synthetic-models'), {},
                                 cancel or Cancellation(), lambda event: None)

    def assert_released(self):
        descriptor = lock_session(self.lock)
        os.close(descriptor)

    def test_stale_exclusive_marker_is_reopened_without_unlinking_inode(self):
        self.lock.write_bytes(b'old-exclusive-marker')
        inode = self.lock.stat().st_ino
        with patch('native_port.texture_enhance.run_process', side_effect=self.inference) as process:
            enhanced, receipt = self.prepare()
        self.assertTrue(enhanced.is_file())
        self.assertEqual(json.loads(receipt.read_text())['sha256'], sha(enhanced))
        self.assertEqual(process.call_count, 1)
        self.assertEqual(self.lock.stat().st_ino, inode)
        self.assertEqual(self.lock.read_bytes(), b'old-exclusive-marker')
        self.assert_released()

    def test_active_os_lock_reports_busy_before_reading_receipt_or_launching(self):
        # A reader must also honor an active writer's OS lock, even if receipt
        # publication is halfway through and the JSON is temporarily unusable.
        (self.output / 'inference.json').write_text('not-complete')
        owner = lock_session(self.lock)
        try:
            with patch('native_port.texture_enhance.run_process') as process:
                with self.assertRaises(PortError) as caught:
                    self.prepare()
            self.assertEqual(caught.exception.code, 'HD_BUSY')
            process.assert_not_called()
            self.assertEqual((self.output / 'inference.json').read_text(), 'not-complete')
        finally:
            os.close(owner)
        self.assert_released()

    def test_cancellation_releases_lock_and_next_attempt_resumes(self):
        cancel = Cancellation()
        def interrupted(argv, *args, **kwargs):
            Path(argv[argv.index('-o') + 1]).write_bytes(b'incomplete-previous-run')
            cancel.cancel()
            cancel.check()
        with patch('native_port.texture_enhance.run_process', side_effect=interrupted):
            with self.assertRaises(PortError) as caught:
                self.prepare(cancel)
        self.assertEqual(caught.exception.code, 'CANCELLED')
        self.assert_released()
        partial = list(self.output.glob('enhanced-pending-*.png'))
        self.assertEqual(len(partial), 1)
        with patch('native_port.texture_enhance.run_process', side_effect=self.inference) as process:
            enhanced, _ = self.prepare()
        self.assertTrue(enhanced.is_file())
        self.assertEqual(process.call_count, 1)
        self.assertEqual(partial[0].read_bytes(), b'incomplete-previous-run')
        self.assert_released()

    def test_reopening_completed_master_verifies_and_reuses_without_inference(self):
        with patch('native_port.texture_enhance.run_process', side_effect=self.inference) as process:
            initial = self.prepare()
            inode = self.lock.stat().st_ino
            reopened = self.prepare()
            self.assertEqual(process.call_count, 1)
        self.assertEqual(initial, reopened)
        self.assertEqual(self.lock.stat().st_ino, inode)
        self.assert_released()

    def test_half_published_png_is_archived_and_not_accepted_without_receipt(self):
        enhanced = self.output / 'enhanced-x4.png'
        Image.new('RGB', (256, 256), 'red').save(enhanced)
        unverified_digest = sha(enhanced)
        with patch('native_port.texture_enhance.run_process', side_effect=self.inference) as process:
            prepared, receipt = self.prepare()
        archived = list(self.output.glob('enhanced-unverified-*.png'))
        self.assertEqual(len(archived), 1)
        self.assertEqual(sha(archived[0]), unverified_digest)
        self.assertNotEqual(sha(prepared), unverified_digest)
        self.assertEqual(json.loads(receipt.read_text())['sha256'], sha(prepared))
        self.assertEqual(process.call_count, 1)
        self.assert_released()

    def test_receipted_digest_tamper_stays_error_and_preserves_artifacts(self):
        with patch('native_port.texture_enhance.run_process', side_effect=self.inference):
            enhanced, receipt = self.prepare()
        receipt_bytes = receipt.read_bytes()
        enhanced.write_bytes(b'tampered-master')
        with patch('native_port.texture_enhance.run_process') as process:
            with self.assertRaises(PortError) as caught:
                self.prepare()
        self.assertEqual(caught.exception.code, 'HD_CACHE_CHANGED')
        process.assert_not_called()
        self.assertEqual(receipt.read_bytes(), receipt_bytes)
        self.assertEqual(enhanced.read_bytes(), b'tampered-master')
        self.assertEqual(list(self.output.glob('enhanced-unverified-*.png')), [])
        self.assert_released()

    def test_os_releases_owner_lock_after_process_termination(self):
        code = ('import sys,time; from native_port.locking import lock_session; '
                'fd=lock_session(sys.argv[1]); print("locked",flush=True); time.sleep(60)')
        project = Path(__file__).resolve().parents[1]
        process = subprocess.Popen([sys.executable, '-c', code, str(self.lock)], cwd=project,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'locked')
            with patch('native_port.texture_enhance.run_process') as inference:
                with self.assertRaises(PortError) as caught:
                    self.prepare()
            self.assertEqual(caught.exception.code, 'HD_BUSY')
            inference.assert_not_called()
            process.kill()
            process.wait(timeout=5)
            with patch('native_port.texture_enhance.run_process', side_effect=self.inference) as inference:
                self.prepare()
            self.assertEqual(inference.call_count, 1)
            self.assert_released()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()
