"""Exercise the actual cmd bridge, including spaces and failure propagation."""
from pathlib import Path
import os
import tempfile
import unittest
from native_port.native_build import capture_windows_environment, find_vcvars, vcvars_candidates
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
            self.assertEqual(result['VSCMD_SKIP_SENDTELEMETRY'], '1')
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

    def test_sdk_flags_accept_utf8_literals_and_cpp_exceptions(self):
        import subprocess
        from native_port.native_build import toolchain
        from native_port.spatial_sdk import spatial_sdk_recipe
        from native_port.workspace import Workspace
        project = Path(__file__).resolve().parents[1]
        _, _, compiler, environment = toolchain(project, Workspace(project / '.aster', project))
        with tempfile.TemporaryDirectory(prefix='Aster compiler contract ') as temporary:
            root = Path(temporary)
            source = root / 'utf8.cpp'
            source.write_text('#include <string_view>\n#include <stdexcept>\n'
                              'void contract() { std::string_view prefix(u8"native"); '
                              'try { throw std::runtime_error("test"); } catch (...) {} }\n', encoding='ascii')
            flags = spatial_sdk_recipe(project, 'win-amd64')['cxx_flags'].split()
            result = subprocess.run([compiler, '/nologo', '/std:c++latest', '/c',
                                     str(source), '/Fo' + str(root / 'utf8.obj'), *flags],
                                    env=environment, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn('unknown argument', result.stderr)
            self.assertTrue((root / 'utf8.obj').is_file())


class VcvarsDiscoveryTests(unittest.TestCase):
    """Discovery must work on Linux and prefer the native Program Files root."""

    def test_candidates_include_both_program_files_roots(self):
        candidates = vcvars_candidates('C:/Program Files', 'C:/Program Files (x86)')
        relative = Path('VC/Auxiliary/Build/vcvars64.bat')
        self.assertIn(Path('C:/Program Files/Microsoft Visual Studio Build Tools/2022/BuildTools') / relative,
                      candidates)
        self.assertIn(Path('C:/Program Files (x86)/Microsoft Visual Studio Build Tools/2022/BuildTools') / relative,
                      candidates)

    def test_program_files_build_tools_precedes_x86(self):
        candidates = vcvars_candidates('C:/Program Files', 'C:/Program Files (x86)')
        relative = Path('VC/Auxiliary/Build/vcvars64.bat')
        preferred = Path('C:/Program Files/Microsoft Visual Studio Build Tools/2022/BuildTools') / relative
        legacy = Path('C:/Program Files (x86)/Microsoft Visual Studio Build Tools/2022/BuildTools') / relative
        self.assertLess(candidates.index(preferred), candidates.index(legacy))

    def test_find_vcvars_uses_program_files_when_x86_is_empty(self):
        with tempfile.TemporaryDirectory(prefix='Aster vcvars discovery ') as temporary:
            root = Path(temporary)
            program_files = root / 'Program Files'
            program_files_x86 = root / 'Program Files (x86)'
            expected = (program_files / 'Microsoft Visual Studio/2022/Community'
                        / 'VC/Auxiliary/Build/vcvars64.bat')
            expected.parent.mkdir(parents=True)
            expected.write_text('@echo off\nexit /b 0\n', encoding='ascii')
            program_files_x86.mkdir()
            self.assertEqual(find_vcvars(program_files=program_files,
                                         program_files_x86=program_files_x86), expected)

    def test_missing_roots_return_none_without_raising(self):
        with tempfile.TemporaryDirectory(prefix='Aster missing vcvars ') as temporary:
            root = Path(temporary)
            self.assertIsNone(find_vcvars(program_files=root / 'Program Files',
                                          program_files_x86=root / 'Program Files (x86)'))
