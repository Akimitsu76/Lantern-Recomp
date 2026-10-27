import importlib.util
from pathlib import Path
import unittest
import subprocess
import sys

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/build_rex_experiment.py'
spec = importlib.util.spec_from_file_location('build_rex_experiment', SOURCE)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ExperimentBuildTests(unittest.TestCase):
    def test_link_extraction_never_executes_post_build_staging(self):
        command = ': && /usr/bin/clang++ "object with spaces.o" -o game && cd build && cmake -E copy original-plugin.so main-plugin.so'
        self.assertEqual(builder.compiler_segment(command),
                         ['/usr/bin/clang++', 'object with spaces.o', '-o', 'game'])

    def test_codegen_or_ambiguous_compilers_are_rejected(self):
        for command in ['cd source && rexglue codegen manifest.toml',
                        '/usr/bin/clang++ a.cpp && /usr/bin/clang++ b.cpp']:
            with self.subTest(command=command), self.assertRaises(ValueError):
                builder.compiler_segment(command)

    @unittest.skipUnless(sys.platform == 'linux', 'CLI under test is the Linux research probe requiring resource and /proc.')
    def test_frame_experiments_reject_default_or_human_profile_before_launch(self):
        root = SOURCE.parents[1]
        for options in [[], ['--executable-dir', str(root / '.aster/build/rex-green'),
                            '--runtime-root', str(root / '.aster/runtime/test')],
                        ['--executable-dir', str(root / '.aster/build/test'),
                         '--runtime-root', str(root / '.aster/runtime/green-lantern')]]:
            for target in (['--experimental-60fps'], ['--fps-target', 'unlimited']):
                with self.subTest(options=options, target=target):
                    result = subprocess.run([sys.executable, str(root / 'scripts/probe_rex_runtime.py'),
                                             '/missing-game', *target, *options],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn('Frame experiments', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)

    @unittest.skipUnless(sys.platform == 'linux', 'CLI under test is the Linux research probe requiring resource and /proc.')
    def test_probe_rejects_conflicting_or_unsafe_fps_options(self):
        root = SOURCE.parents[1]
        for options in (['--fps-target', 'unlimited', '--vsync', 'on'],
                        ['--fps-target', 'unlimited', '--present-mode', 'fifo'],
                        ['--experimental-60fps', '--fps-target', 'unlimited'],
                        ['--experimental-60fps', '--experimental-unlimited-fps']):
            with self.subTest(options=options):
                result = subprocess.run([sys.executable, str(root / 'scripts/probe_rex_runtime.py'),
                                         '/missing-game', *options],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn('Traceback', result.stderr)

    def test_probe_report_falls_back_to_main_only_when_not_redirected(self):
        source = (SOURCE.parents[1] / 'scripts/probe_rex_runtime.py').read_text()
        self.assertIn('output_report == default_report', source)
        self.assertIn('shutil.copyfile(stdout, reports / "rexglue-runtime-stdout.log")', source)
