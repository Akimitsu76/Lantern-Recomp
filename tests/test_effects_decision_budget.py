"""The diagnostic rejection ledger stays bounded under concurrent callers."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from native_port.native_cache import apply_patch_exact

ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / 'integrations/rexglue/patches'
HEADER = 'include/rex/graphics/pipeline/texture/effects_diagnostics.h'


class EffectsDecisionBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('c++') or shutil.which('clang++')
        if not compiler:
            raise unittest.SkipTest('C++ compiler unavailable')
        cls.temp = tempfile.TemporaryDirectory(prefix='aster-effects-decisions-')
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        text = (PATCHES / '0018-effects-sampling-diagnostics.patch').read_text()
        first = text.split('+++ b/' + HEADER + '\n', 1)[1].split('--- a/', 1)[0]
        header = folder / HEADER
        header.parent.mkdir(parents=True)
        header.write_text('\n'.join(row[1:] for row in first.splitlines() if row.startswith('+')) + '\n')
        for name in ('0019-armed-effects-source-index.patch', '0020-effects-decision-diagnostics.patch'):
            apply_patch_exact(folder, (PATCHES / name).read_text().split('--- a/src/', 1)[0])
        (folder / 'contract.cpp').write_text(r'''
#include "include/rex/graphics/pipeline/texture/effects_diagnostics.h"
#include <thread>
using namespace rex::graphics::effects_diagnostics;
int main() {
  std::atomic<unsigned> records{0};
  std::vector<std::thread> threads;
  for (unsigned t = 0; t < 8; ++t) threads.emplace_back([&] {
    for (unsigned n = 0; n < 10000; ++n)
      if (DecisionOnce(n % 32)) ++records;
  });
  for (auto& t : threads) t.join();
  if (DecisionOnce(UINT32_MAX) || DecisionOnce(16)) return 1;
  // Metadata logging cannot consume, reset or increase the source snapshot cap.
  if (Budget().Full() || !Budget().Reserve("first-source-state")) return 2;
  return records == (Enabled() ? 16u : 0u) ? 0 : 3;
}
''')
        cls.binary = folder / 'contract'
        result = subprocess.run([compiler, '-std=c++17', '-pthread', str(folder / 'contract.cpp'),
                                 '-o', str(cls.binary)], capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError(result.stderr)

    def test_opt_in_concurrent_limit_and_independent_snapshot_budget(self):
        for value in (None, '', '0', 'true', '1', '11'):
            env = dict(os.environ)
            env.pop('ASTER_EFFECTS_DIAGNOSTICS', None)
            if value is not None:
                env['ASTER_EFFECTS_DIAGNOSTICS'] = value
            with self.subTest(value=value):
                result = subprocess.run([str(self.binary)], env=env, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
