"""Only capture a selected PID-owned client; verify pixels on an isolated display."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from rex_x11_capture import capture_verified_x11_window


@unittest.skipUnless(sys.platform.startswith('linux') and os.environ.get('DISPLAY') and shutil.which('xprop'),
                     'Requires an isolated Linux X11 test display')
class X11CaptureTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from PIL import Image
        self.Image = Image
        self.window = tk.Tk()
        self.addCleanup(self.window.destroy)
        self.window.overrideredirect(True)
        self.window.geometry('120x80+0+0')
        self.window.configure(background='#123456')
        self.window.update()
        self.xid = hex(self.window.winfo_id())
        result = subprocess.run(['xprop', '-id', self.xid, '-f', '_NET_WM_PID', '32c',
                                 '-set', '_NET_WM_PID', str(os.getpid())], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.temp = tempfile.TemporaryDirectory(prefix='aster-x11-capture-')
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / 'selected.png'

    def test_client_image_dimensions_and_colour(self):
        result = capture_verified_x11_window(os.getpid(), self.xid, self.output)
        self.assertEqual(result['capture_method'], 'x11-client-image')
        with self.Image.open(self.output) as image:
            self.assertEqual(image.size, (120, 80))
            self.assertEqual(image.getpixel((60, 40)), (18, 52, 86))

    def test_mismatched_pid_never_writes_an_image(self):
        with self.assertRaises(ValueError):
            capture_verified_x11_window(os.getpid() + 1, self.xid, self.output)
        self.assertFalse(self.output.exists())

    def test_unmapped_window_fails_without_screen_fallback(self):
        self.window.withdraw()
        self.window.update()
        with self.assertRaises(ValueError):
            capture_verified_x11_window(os.getpid(), self.xid, self.output)
        self.assertFalse(self.output.exists())
