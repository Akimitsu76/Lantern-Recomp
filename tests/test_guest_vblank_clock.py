"""Run original and patched SDK scheduler blocks against a deterministic clock."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/vblank_clock_pinned.inc'
PATCH = ROOT / 'integrations/rexglue/patches/0023-guest-vblank-video-mode-clock.patch'

HARNESS = r'''
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <stdexcept>
static uint64_t tick = 0, count = 0;
static bool vsync_worker_running_ = false, vsync = true, toggle = false;
namespace chrono {
struct Clock {
 static uint64_t guest_tick_frequency() { return 1000000; }
 static uint64_t QueryGuestTickCount() { return tick; }
};
}
namespace rex::thread {
void Sleep(std::chrono::milliseconds) {
 tick += 1000;
 if (toggle && tick >= 500000) vsync = false;
 if (tick > 1000000) vsync_worker_running_ = false;
}
}
#define REXCVAR_GET(name) (name)
static void MarkVblank() { ++count; }
static uint64_t run(double rate, bool sync, bool change) {
 tick=0;count=0;vsync=sync;toggle=change;vsync_worker_running_=true;
 struct { float refresh_rate; } video_mode{float(rate)};
 SCHEDULER_BLOCK
 return count;
}
int main() {
 const bool patched = PATCHED_VARIANT;
 for (double rate : {30.0, 50.0, 59.94, 60.0, 120.0}) {
  const auto expected = uint64_t(1000000) / std::max(uint64_t(1), uint64_t(1000000 / double(float(rate))));
  if(run(rate,true,false)!=expected) throw std::runtime_error("video mode rate changed");
  if(run(rate,false,false)!=(patched?expected:1000)) throw std::runtime_error("uncapped presentation changed guest interrupts");
  if(patched && run(rate,true,true)!=expected) throw std::runtime_error("runtime VSync toggle changed guest clock");
 }
 if(run(0,true,false)!=1) throw std::runtime_error("invalid mode guard lost");
}
'''


class GuestVblankClockTests(unittest.TestCase):
    def test_host_vsync_does_not_accelerate_guest_interrupt_clock(self):
        original = FIXTURE.read_text(encoding='utf8')
        hunks = re.split(r'^@@[^\n]*\n', PATCH.read_text(encoding='utf8'), flags=re.MULTILINE)[1:]
        self.assertEqual(len(hunks), 1)
        lines = hunks[0].splitlines(keepends=True)
        old = ''.join(line[1:] for line in lines if line[:1] in (' ', '-'))
        new = ''.join(line[1:] for line in lines if line[:1] in (' ', '+'))
        self.assertEqual(original.count(old), 1, 'Pinned SDK scheduler changed')
        patched = original.replace(old, new, 1)
        compiler = shutil.which('c++') or shutil.which('g++') or shutil.which('clang++')
        if not compiler:
            self.skipTest('Actual SDK-block regression requires a C++ compiler')
        with tempfile.TemporaryDirectory(prefix='aster-vblank-test-') as temporary:
            folder = Path(temporary)
            for label, text in [('original', original), ('patched', patched)]:
                with self.subTest(variant=label):
                    block = text.split('// BEGIN SCHEDULER\n', 1)[1].split('// END SCHEDULER', 1)[0]
                    source = HARNESS.replace('SCHEDULER_BLOCK', block).replace('PATCHED_VARIANT', str(label == 'patched').lower())
                    cpp, binary = folder / (label + '.cpp'), folder / label
                    cpp.write_text(source, encoding='utf8')
                    build = subprocess.run([compiler, '-std=c++17', str(cpp), '-o', str(binary)], capture_output=True, text=True, timeout=30)
                    self.assertEqual(build.returncode, 0, build.stderr)
                    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
