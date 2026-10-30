"""Compile the actual menu hooks against the pinned SDK, with synthetic IO."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


class NativeSlotContractTests(unittest.TestCase):
    def test_sdk_abi_menu_scope_and_read_rollback(self):
        prefix = os.environ.get('ASTER_TEST_SAVE_SDK_PREFIX')
        if not prefix:
            self.skipTest('Set ASTER_TEST_SAVE_SDK_PREFIX to the built public SDK')
        root = Path(__file__).resolve().parents[1]
        from native_port.native_build import toolchain
        from native_port.workspace import Workspace
        cmake, ninja, compiler, build_env = toolchain(root, Workspace(root / '.aster', root))
        with tempfile.TemporaryDirectory() as folder:
            build = Path(folder) / 'build'
            commands = [[cmake, '-S', str(root / 'integrations/rexglue/save-slots/contract'),
                         '-B', str(build), '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=RelWithDebInfo',
                         '-DCMAKE_CXX_COMPILER=' + compiler, '-DCMAKE_MAKE_PROGRAM=' + ninja,
                         '-DCMAKE_PREFIX_PATH=' + prefix], [cmake, '--build', str(build), '--parallel', '2']]
            for cmd in commands:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=build_env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            env = os.environ.copy()
            env['PATH'] = str(Path(prefix) / 'bin') + os.pathsep + env.get('PATH', '')
            result = subprocess.run([str(build / ('aster_save_slot_contract.exe' if os.name == 'nt'
                                                 else 'aster_save_slot_contract'))],
                                    capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('NATIVE_SAVE_SLOT_CONTRACT_OK', result.stdout)
