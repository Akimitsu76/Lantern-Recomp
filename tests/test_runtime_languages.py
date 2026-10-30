"""Exercise the shipped host hooks, including original SKU fallback semantics."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class RuntimeLanguageTests(unittest.TestCase):
    def test_independent_channels_call_original_and_preserve_capability_queries(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        if not compiler:
            self.skipTest('C++ compiler unavailable')
        source = Path(__file__).resolve().parents[1] / 'integrations/rexglue/runtime_languages.cpp'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'rex').mkdir()
            (root / 'rex/cvar.h').write_text(
                '#define REXCVAR_DEFINE_INT32(name,value,group,description) int32_t name=value;\n'
                '#define REXCVAR_GET(name) (name)\n')
            (root / 'rex/logging.h').write_text('#define REXLOG_INFO(...) (++logs)\n')
            (root / 'aster_green_lantern_pch.h').write_text(r'''
#include <cstdint>
#include <cassert>
#include <initializer_list>
union Register { uint64_t u64; int64_t s64; uint32_t u32; int32_t s32; Register():u64(0){} };
struct PPCContext { Register r3{},r4{}; uint64_t lr=0, marker=0; };
inline unsigned logs=0;
''')
            (root / 'hook.cpp').write_bytes(source.read_bytes())
            (root / 'test.cpp').write_text(r'''
#include "hook.cpp"
unsigned text_calls=0,voice_calls=0;
int text_seen=-99,voice_seen=-99;
bool portuguese_in_sku=true;
uint8_t* base_seen=nullptr;
extern "C" void __imp__sub_82376988(PPCContext& ctx,uint8_t* base) {
    ++text_calls;text_seen=ctx.r3.s32;base_seen=base;ctx.marker=0x1122334455667788ull;
    if(ctx.r3.s32==11 && !portuguese_in_sku) ctx.r3.s64=0;
}
extern "C" void __imp__sub_823769D8(PPCContext& ctx,uint8_t* base) {
    ++voice_calls;voice_seen=ctx.r3.s32;base_seen=base;ctx.marker=0x8877665544332211ull;
    // Original game's unsupported-language fallback, never supplied by hook.
    if(ctx.r3.s32==11) ctx.r3.s64=0;
}
int main() {
 uint8_t base[1]{};PPCContext c;c.lr=0x82378d10;c.r3.s64=4;c.r4.u64=123;
 sub_82376988(c,base);
 assert(text_calls==1 && text_seen==4 && c.r3.s32==4 && logs==0);
 assert(c.r4.u64==123 && c.lr==0x82378d10 && c.marker==0x1122334455667788ull && base_seen==base);
 aster_ui_language=11;aster_spoken_language=1;
 for(uint32_t caller:{0x82378d10u,0x824c0b9cu,0x824c05b4u}) {
   c.lr=caller;c.r3.s64=0;sub_82376988(c,base);assert(text_seen==11 && c.r3.s32==11);
 }
 for(uint32_t caller:{0x82378c58u,0x82378d20u,0x824c0ba8u}) {
   c.lr=caller;c.r3.s64=11;sub_823769D8(c,base);assert(voice_seen==1 && c.r3.s32==1);
 }
 assert(logs==2);
 // Validation callbacks and unknown callers retain their original arguments.
 for(uint32_t caller:{0x824b9bd0u,0x824b9bd8u,0xdeadbeefu}) {
   c.lr=caller;c.r3.s64=5;sub_82376988(c,base);assert(text_seen==5 && c.r3.s32==5);
   c.r3.s64=4;sub_823769D8(c,base);assert(voice_seen==4 && c.r3.s32==4);
 }
 // A mismatching SKU can still refuse Portuguese through the original function.
 portuguese_in_sku=false;c.lr=0x82378d10;c.r3.s64=4;sub_82376988(c,base);
 assert(text_seen==11 && c.r3.s32==0);
 // Unsupported values cannot be forced into either original selector.
 for(int value:{-1,2,8,9,999}) {
   aster_ui_language=value;c.lr=0x82378d10;c.r3.s64=4;sub_82376988(c,base);assert(text_seen==4);
   aster_spoken_language=value;c.lr=0x82378d20;c.r3.s64=5;sub_823769D8(c,base);assert(voice_seen==5);
 }
 aster_spoken_language=11;c.lr=0x82378d20;c.r3.s64=4;sub_823769D8(c,base);assert(voice_seen==4);
 assert(logs==2);
}
''')
            binary = root / 'language-test.exe'
            compiled = subprocess.run([compiler, '-std=c++23', '-Wall', '-Wextra', '-I', str(root),
                                       str(root / 'test.cpp'), '-o', str(binary)],
                                      capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
