import ctypes
import importlib.util
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from native_port import launcher_fonts as fonts


class LauncherFontTests(unittest.TestCase):
    def setUp(self):
        self.result_patch = patch.object(fonts, '_result', None)
        self.result_patch.start(); self.addCleanup(self.result_patch.stop)
        self.backend_patch = patch.object(fonts, '_backend', None)
        self.backend_patch.start(); self.addCleanup(self.backend_patch.stop)

    def test_all_bundled_faces_are_present_and_ttf(self):
        paths = fonts._font_paths()
        self.assertEqual(tuple(p.name for p in paths), fonts.FONT_FILES)
        self.assertTrue((paths[0].parent / 'LICENSE-DejaVu.txt').is_file())

    def test_parallel_calls_register_once(self):
        results = []
        paths = fonts._font_paths()
        with patch.object(fonts, '_font_paths', return_value=paths), \
             patch.object(fonts, '_register_linux', return_value=True) as register, \
             patch.object(fonts.os, 'name', 'posix'), patch.object(fonts.sys, 'platform', 'linux'):
            threads = [threading.Thread(target=lambda: results.append(fonts.load_fonts())) for _ in range(8)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self.assertEqual(results, [True] * 8)
            register.assert_called_once()

    def test_failure_remembers_safe_fallback_without_running_font_installers(self):
        with patch.object(fonts, '_font_paths', return_value=()), \
             patch.object(fonts, '_register_linux') as linux, \
             patch.object(fonts, '_register_windows') as windows:
            self.assertFalse(fonts.load_fonts()); self.assertFalse(fonts.load_fonts())
            linux.assert_not_called(); windows.assert_not_called()

    def test_missing_library_does_not_prevent_launcher_startup(self):
        paths = fonts._font_paths()
        with patch.object(fonts, '_font_paths', return_value=paths), \
             patch.object(fonts.os, 'name', 'posix'), patch.object(fonts.sys, 'platform', 'linux'), \
             patch.object(fonts, '_register_linux', side_effect=OSError('not installed')):
            self.assertFalse(fonts.load_fonts())

    def test_linux_only_adds_app_fonts_to_current_process_config(self):
        library = Mock(); library.FcConfigGetCurrent.return_value = 0x1234
        library.FcConfigAppFontAddFile.return_value = 1
        paths = fonts._font_paths()
        with patch.object(fonts.ctypes, 'CDLL', return_value=library), \
             patch.object(fonts.ctypes.util, 'find_library', return_value='libfontconfig.so.1'):
            self.assertTrue(fonts._register_linux(paths))
        self.assertEqual(library.FcConfigAppFontAddFile.call_count, 3)
        for call, path in zip(library.FcConfigAppFontAddFile.call_args_list, paths):
            self.assertEqual(call.args, (0x1234, os.fsencode(path)))
        library.FcConfigAppFontClear.assert_not_called()
        library.FcConfigBuildFonts.assert_not_called()

    def test_windows_registration_always_uses_fr_private(self):
        library = Mock(); library.AddFontResourceExW.return_value = 1
        paths = fonts._font_paths()
        with patch.object(fonts.ctypes, 'WinDLL', return_value=library, create=True):
            self.assertTrue(fonts._register_windows(paths))
        self.assertEqual(library.AddFontResourceExW.call_count, 3)
        for call, path in zip(library.AddFontResourceExW.call_args_list, paths):
            self.assertEqual(call.args, (str(path), 0x10, None))
        self.assertEqual(library.AddFontResourceExW.restype, ctypes.c_int)

    def test_frozen_module_layout_has_its_own_resource_copy(self):
        root = Path(__file__).resolve().parents[1]
        script = root / 'scripts/package_launcher.py'
        spec = importlib.util.spec_from_file_location('package_launcher_fonts_test', script)
        packaging = importlib.util.module_from_spec(spec); spec.loader.exec_module(packaging)
        arguments = packaging.launcher_resource_arguments(root)
        self.assertEqual(arguments, ['--add-data', str(root / 'native_port/resources') +
                                    os.pathsep + 'native_port/resources'])
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'app'
            with patch.object(packaging, 'PUBLIC_DIRS', ['native_port/resources/fonts']), \
                 patch.object(packaging, 'PUBLIC_SCRIPTS', []):
                copied = packaging.copy_public(root, destination)
            for name in (*fonts.FONT_FILES, 'LICENSE-DejaVu.txt'):
                relative = 'native_port/resources/fonts/' + name
                self.assertIn(str(Path(relative)), copied)
                self.assertEqual((destination / relative).read_bytes(), (root / relative).read_bytes())

    def test_invalid_bundled_face_uses_fallback_before_native_api(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary); resources = base / 'resources/fonts'; resources.mkdir(parents=True)
            for name in fonts.FONT_FILES: (resources / name).write_bytes(b'not true type')
            with patch.object(fonts, '__file__', str(base / 'launcher_fonts.py')), \
                 patch.object(fonts, '_register_linux') as register:
                self.assertFalse(fonts.load_fonts()); register.assert_not_called()


if __name__ == '__main__': unittest.main()
