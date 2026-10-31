from pathlib import Path
import sys
import tempfile
import unittest

from native_port.tasks import Cancellation, run_process
from native_port.errors import PortError


class ProcessDiagnosticTests(unittest.TestCase):
    def test_early_error_survives_warning_flood_in_full_log(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / 'compiler.log'
            command = [sys.executable, '-c',
                       "import sys; print('EARLY_COMPILER_ERROR',flush=True); "
                       "sys.stdout.write('warning details\\n'*100000); "
                       "sys.stdout.flush(); print('STDERR_DETAIL',file=sys.stderr); sys.exit(7)"]
            with self.assertRaises(PortError) as raised:
                run_process(command, root, Cancellation(), output_log=log, on_output=lambda _: None)
            self.assertEqual(raised.exception.details['returncode'], 7)
            self.assertLessEqual(len(raised.exception.details['stdout']), 65536)
            self.assertNotIn('EARLY_COMPILER_ERROR', raised.exception.details['stdout'])
            self.assertTrue(log.read_bytes().startswith(b'EARLY_COMPILER_ERROR'))
            self.assertIn(b'STDERR_DETAIL', log.read_bytes())
            self.assertGreater(log.stat().st_size, 1000000)
