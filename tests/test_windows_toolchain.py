"""Exercise the actual cmd bridge, including spaces and failure propagation."""
from pathlib import Path
import os
import tempfile
import unittest
from native_port.native_build import capture_windows_environment
from native_port.errors import PortError


@unittest.skipUnless(os.name == 'nt', 'Real cmd.exe requires Windows')
class WindowsToolchainTests(unittest.TestCase):
    def test_vcvars_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix='Aster toolchain with spaces ') as temporary:
            root = Path(temporary)
            script = root / 'Visual Studio Build Tools' / 'vcvars64.bat'
            script.parent.mkdir()
            script.write_text('@echo off\nset "VCToolsInstallDir=C:\\Build Tools\\VC\\Tools"\n'
                              'set "INCLUDE=C:\\Windows Kits\\Include"\nexit /b 0\n', encoding='ascii')
            env = {key.upper(): value for key, value in os.environ.items()}
            before = dict(env)
            result = capture_windows_environment(script, root, env)
            self.assertEqual(result['VCTOOLSINSTALLDIR'], r'C:\Build Tools\VC\Tools')
            self.assertEqual(result['INCLUDE'], r'C:\Windows Kits\Include')
            self.assertNotIn('ASTER_VCVARS_PATH', result)
            self.assertEqual(env, before)

    def test_failed_vcvars_is_not_accepted_as_a_working_compiler_environment(self):
        with tempfile.TemporaryDirectory(prefix='Aster failed toolchain ') as temporary:
            root = Path(temporary)
            script = root / 'failed vcvars.bat'
            script.write_text('@echo off\nexit /b 7\n', encoding='ascii')
            with self.assertRaises(PortError) as raised:
                capture_windows_environment(script, root, dict(os.environ))
            self.assertEqual(raised.exception.details['returncode'], 7)
