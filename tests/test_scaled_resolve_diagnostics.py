"""CPU contract checks for the exact optional diagnostic block in SDK patch 0015.

This compiles the added block against small metadata stubs. It checks bounded
logging and opt-in behavior, not the SDK build or rendered correctness.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'integrations/rexglue/patches/0015-scaled-resolve-diagnostics.patch'


class ScaledResolveDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('c++') or shutil.which('g++') or shutil.which('clang++')
        if not compiler:
            raise unittest.SkipTest('C++ compiler unavailable for diagnostic CPU contract')
        added = '\n'.join(line[1:] for line in PATCH.read_text().splitlines()
                          if line.startswith('+') and not line.startswith('+++'))
        cls.added = added
        block = added.split('// ASTER_SCALED_RESOLVE_DIAGNOSTICS_BEGIN', 1)[1].split(
            '// ASTER_SCALED_RESOLVE_DIAGNOSTICS_END', 1)[0]
        cls.temp = tempfile.TemporaryDirectory(prefix='aster-resolve-contract-')
        cls.addClassCleanup(cls.temp.cleanup)
        source = Path(cls.temp.name) / 'contract.cpp'
        cls.binary = Path(cls.temp.name) / 'contract'
        source.write_text(r'''
#include <atomic>
#include <cstdint>
#include <string>
#include <thread>
#include <tuple>
#include <vector>
bool aster_scaled_resolve_diagnostics = false;
std::atomic<unsigned> logged{0}, queries{0};
thread_local std::string last_path;
#define REXCVAR_GET(name) (name)
template<typename... Args> void log_record(const char*, Args... args) {
  auto tuple = std::make_tuple(args...);
  last_path = std::get<sizeof...(Args)-1>(tuple);
  ++logged;
}
#define REXGPU_INFO(...) log_record(__VA_ARGS__)
struct Level { unsigned level_data_extent_bytes=4096, row_pitch_bytes=256; };
struct Layout { Level base; unsigned mips_total_extent_bytes=4096; };
struct Key {
  unsigned base_page=16, mip_page=17, format=6, dimension=1, tiled=1;
  unsigned mip_max_level=1, scaled_resolve=0;
  Layout GetGuestLayout() const { return {}; }
  unsigned GetWidth() const { return 64; }
  unsigned GetHeight() const { return 64; }
  unsigned GetDepthOrArraySize() const { return 1; }
};
struct Cache {
  bool scaled=true, overlap=true, supported=true;
  bool IsDrawResolutionScaled() const { return scaled; }
  bool QueryScaledResolveRangeForDiagnostics(unsigned, unsigned) const { ++queries; return overlap; }
  bool IsScaledResolveSupportedForFormat(Key) const { return supported; }
  unsigned draw_resolution_scale_x() const { return 2; }
  unsigned draw_resolution_scale_y() const { return 2; }
  void create(Key key) {
''' + block + r'''
  }
};
int main(int argc, char** argv) {
  if (argc != 2) return 1;
  const std::string mode(argv[1]);
  Cache cache;
  Key key;
  aster_scaled_resolve_diagnostics = mode != "off";
  if (mode == "unscaled") cache.scaled=false;
  if (mode == "unrelated") cache.overlap=false;
  if (mode == "linear") key.tiled=0;
  if (mode == "unsupported") cache.supported=false;
  if (mode == "scaled") { key.scaled_resolve=1; cache.overlap=false; }
  if (mode == "parallel") {
    std::vector<std::thread> threads;
    for (unsigned i=0; i<8; ++i) threads.emplace_back([&] {
      for (unsigned j=0; j<100; ++j) cache.create(key);
    });
    for (auto& t : threads) t.join();
    return logged == 128 ? 0 : 2;
  }
  for (unsigned i=0; i<200; ++i) cache.create(key);
  if (mode == "off" || mode == "unscaled")
    return logged == 0 && queries == 0 ? 0 : 3;
  if (mode == "unrelated") return logged == 0 ? 0 : 4;
  const char* expected = mode == "linear" ? "unscaled-linear" :
      mode == "unsupported" ? "unscaled-unsupported-loader" :
      mode == "scaled" ? "scaled" : "unscaled-key";
  return logged == 128 && last_path == expected ? 0 : 5;
}
''')
        result = subprocess.run([compiler, '-std=c++17', '-pthread', str(source), '-o', str(cls.binary)],
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError(result.stderr)

    def run_mode(self, mode):
        result = subprocess.run([str(self.binary), mode], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr or mode)

    def test_disabled_and_one_x_do_not_query_pages_or_log(self):
        for mode in ('off', 'unscaled'):
            with self.subTest(mode=mode):
                self.run_mode(mode)

    def test_unrelated_materials_do_not_consume_logging_budget(self):
        self.run_mode('unrelated')

    def test_linear_and_unsupported_fallbacks_are_distinguished(self):
        for mode in ('linear', 'unsupported', 'key', 'scaled'):
            with self.subTest(mode=mode):
                self.run_mode(mode)

    def test_logging_has_strict_process_wide_limit_under_concurrency(self):
        self.run_mode('parallel')

    def test_diagnostic_defaults_off_and_does_not_claim_mirror_validity(self):
        self.assertIn('REXCVAR_DEFINE_BOOL(aster_scaled_resolve_diagnostics, false,', self.added)
        self.assertIn('mirror1x=unknown', self.added)
        touched = [line[6:] for line in PATCH.read_text().splitlines() if line.startswith('+++ b/')]
        self.assertEqual(touched, ['include/rex/graphics/pipeline/texture/cache.h',
                                   'src/graphics/vulkan/texture_cache.cpp'])
        self.assertIn('return IsRangeScaledResolved(start_unscaled, length_unscaled);', self.added)
        # This CPU fixture stubs access; the separate real-header syntax contract
        # in patch-sequence-validation.json verifies protected/private access.
