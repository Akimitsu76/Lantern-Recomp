import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

if sys.platform != 'linux':
    raise unittest.SkipTest('Linux research input probe requires fcntl and verified X11 window controls.')

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import rex_x11_input as x11_input
spec = importlib.util.spec_from_file_location('rex_probe_input', SCRIPTS / 'rex_probe_input.py')
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


class ProbeControlTests(unittest.TestCase):
    def test_timing_lookup_still_verifies_pid_without_reading_or_encoding_an_image(self):
        import probe_rex_runtime as probe
        with patch.object(probe.subprocess, 'run', side_effect=[
                subprocess.CompletedProcess([], 0, '_NET_CLIENT_LIST(WINDOW): 0x12, 0x34', ''),
                subprocess.CompletedProcess([], 0, '_NET_WM_PID(CARDINAL) = 77', ''),
                subprocess.CompletedProcess([], 0, '_NET_WM_PID(CARDINAL) = 123', '')]) as run:
            self.assertEqual(probe.capture_own_x11_window(123, None), {'pid': 123, 'window_id': '0x34'})
            self.assertEqual(run.call_count, 3)
            self.assertTrue(all(call.args[0][0] == 'xprop' for call in run.call_args_list))

    def test_completed_probe_rejects_input_without_creating_queue(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            attempt = root / '.aster/reports/rex-history/finished'
            attempt.mkdir(parents=True)
            (attempt / 'report.json').write_text('{}')
            with patch.object(control, '__file__', str(root / 'scripts/rex_probe_input.py')), \
                    patch.object(sys, 'argv', ['rex_probe_input.py', 'finished', '--key', 'w']), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                control.main()
            self.assertFalse((attempt / 'control.jsonl').exists())

    def test_input_requires_explicit_live_input_session(self):
        for session in ({'live_input': False}, []):
            with self.subTest(session=session), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                attempt = root / '.aster/reports/rex-history/disabled'
                attempt.mkdir(parents=True)
                (attempt / 'session.json').write_text(json.dumps(session))
                with patch.object(control, '__file__', str(root / 'scripts/rex_probe_input.py')), \
                        patch.object(sys, 'argv', ['rex_probe_input.py', 'disabled', '--key', 'w']), \
                        contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    control.main()
                self.assertFalse((attempt / 'control.jsonl').exists())

    def test_path_traversal_cannot_queue_outside_attempt_directory(self):
        with patch.object(sys, 'argv', ['rex_probe_input.py', '../outside', '--key', 'w']), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            control.main()


class ProbeCompositorFocusTests(unittest.TestCase):
    def test_focus_requires_unique_matching_title_and_class(self):
        properties = '_NET_WM_NAME(UTF8_STRING) = "Probe game"\nWM_CLASS(STRING) = "probe", "Probe"\n'
        match = {'id': 42, 'title': 'Probe game', 'app_id': 'probe'}
        for rows in ([], [dict(match, title='Other')], [dict(match, app_id='other')], [match, match]):
            with self.subTest(rows=rows), patch.dict(x11_input.os.environ, {'NIRI_SOCKET': 'test'}), \
                    patch.object(x11_input.subprocess, 'run', side_effect=[
                        subprocess.CompletedProcess([], 0, properties, ''),
                        subprocess.CompletedProcess([], 0, json.dumps(rows), '')]) as run:
                self.assertIn('error', x11_input.focus_verified_niri_window('0x12'))
                self.assertEqual(run.call_count, 2)
        with patch.dict(x11_input.os.environ, {'NIRI_SOCKET': 'test'}), \
                patch.object(x11_input.subprocess, 'run', side_effect=[
                    subprocess.CompletedProcess([], 0, properties, ''),
                    subprocess.CompletedProcess([], 0, json.dumps([match]), ''),
                    subprocess.CompletedProcess([], 0, '', '')]) as run:
            self.assertEqual(x11_input.focus_verified_niri_window('0x12'), {'window_id': 42, 'returncode': 0})
            self.assertEqual(run.call_args.args[0], ['niri', 'msg', 'action', 'focus-window', '--id', '42'])

    def test_wrong_pid_prevents_compositor_focus_and_input(self):
        with patch.object(x11_input.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0,
                '_NET_WM_PID(CARDINAL) = 999', '')), \
                patch.object(x11_input, 'focus_verified_niri_window') as focus, \
                patch.object(x11_input.C, 'CDLL') as library:
            self.assertIn('error', x11_input.send_window_key(123, '0x12', 'Return'))
            focus.assert_not_called()
            library.assert_not_called()
