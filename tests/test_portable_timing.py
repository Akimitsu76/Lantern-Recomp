"""Exercise the shipped hook against callback, wrap and guest-call contracts."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class PortableTimingTests(unittest.TestCase):
    def test_uncapped_preserves_guest_routine_and_only_adjusts_known_pacing_clock(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        if not compiler:
            self.skipTest('C++ compiler unavailable')
        source = Path(__file__).resolve().parents[1] / 'integrations/rexglue/portable_timing.cpp'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'rex').mkdir()
            (root / 'rex/cvar.h').write_text(
                '#define REXCVAR_DEFINE_BOOL(name,value,group,description) bool name=value;\n'
                '#define REXCVAR_GET(name) (name)\n')
            (root / 'aster_green_lantern_pch.h').write_text(r'''
#include <cstdint>
#include <cassert>
#include <unordered_map>
struct PPCContext { uint32_t guest_effect=0; uint64_t lr=0; };
inline std::unordered_map<uint32_t,uint32_t> words;
#define REX_LOAD_U32(address) words[address]
#define REX_LOAD_U8(address) uint8_t(words[address])
#define REX_STORE_U32(address,value) (words[address]=(value))
''')
            (root / 'hook.cpp').write_bytes(source.read_bytes())
            (root / 'test.cpp').write_text(r'''
#include "hook.cpp"
unsigned original_calls=0;
uint32_t comparison_seen=0;
extern "C" void __imp__sub_82402E38(PPCContext& ctx, uint8_t*) {
    ++original_calls;
    comparison_seen=words[0x8283E2F8u];
    ctx.guest_effect=0x12345678u; // Effects beyond a callback's return register.
}
void invoke() {
    PPCContext ctx;ctx.lr=0x11223344u;
    auto prior=original_calls;
    sub_82402E38(ctx,nullptr);
    assert(original_calls==prior+1);
    assert(ctx.guest_effect==0x12345678u && ctx.lr==0x11223344u);
}
int main() {
    words[0x82836A24u]=0x41F00000u;
    words[0x82839488u]=0x8247CE30u;
    words[0x8283E2F8u]=77;
    words[0x82BA0348u]=123;
    invoke();
    assert(words[0x82836A24u]==0x41F00000u && comparison_seen==77);
    aster_experimental_60fps=true;
    invoke();
    assert(words[0x82836A24u]==0x42700000u && comparison_seen==77);
    aster_experimental_60fps=false;aster_experimental_unlimited_fps=true;
    for(uint32_t current : {0u,1u,123u,0x7FFFFFFFu,0x80000000u,0xFFFFFFFFu}) {
        words[0x82BA0348u]=current;words[0x8283E2F8u]=77;
        invoke();
        assert(comparison_seen==uint32_t(current-1));
        assert(uint32_t(current-comparison_seen)==1);
        assert(words[0x82BA0348u]==current); // Never accelerate display time.
    }
    words[0x8283E2F8u]=77;words[0x8283E2CCu]=1;
    invoke();assert(comparison_seen==77);
    words[0x8283E2CCu]=0;words[0x82836A24u]=0x42F00000u;
    invoke();assert(comparison_seen==77);
    words[0x82836A24u]=0x42700000u;
    for(uint32_t callback : {0u,0x82402710u,0xDEADBEEFu}) {
        words[0x82839488u]=callback;invoke();assert(comparison_seen==77);
    }
}
''')
            binary = root / 'timing-test.exe'
            compiled = subprocess.run([compiler, '-std=c++17', '-I', str(root),
                                       str(root / 'test.cpp'), '-o', str(binary)],
                                      capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
