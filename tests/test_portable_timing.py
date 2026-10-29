"""Exercise shipped timing hooks; these contracts do not certify gameplay."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class PortableTimingTests(unittest.TestCase):
    def run_cpp(self, program):
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
            (root / 'rex/logging.h').write_text('#define REXLOG_INFO(...) Log(__VA_ARGS__)\n')
            (root / 'aster_green_lantern_pch.h').write_text(r'''
#include <cstdint>
#include <cassert>
#include <cmath>
#include <cstring>
#include <string>
#include <sstream>
#include <unordered_map>
#include <vector>
struct Register { uint32_t u32=0; };
struct PPCContext { uint32_t guest_effect=0; uint64_t lr=0; Register r3{}; uint64_t marker=0; };
inline std::unordered_map<uint32_t,uint32_t> words;
inline unsigned reads=0;
inline std::vector<std::vector<std::string>> logs;
template<typename Value> std::string Text(Value value) { std::ostringstream out;out<<value;return out.str(); }
template<typename... Args> void Log(const char* format, Args... args) {
    logs.push_back({format,Text(args)...});
}
#define REX_LOAD_U32(address) (++reads,words[address])
#define REX_LOAD_U8(address) uint8_t((++reads,words[address]))
#define REX_STORE_U32(address,value) (words[address]=(value))
''')
            (root / 'hook.cpp').write_bytes(source.read_bytes())
            (root / 'test.cpp').write_text(r'''
#include "hook.cpp"
unsigned original_calls=0, sim_calls=0, render_calls=0, swap_calls=0;
uint32_t comparison_seen=0;
uint8_t* base_seen=nullptr;
void SetFloat(uint32_t offset,float value) {
    uint32_t bits;std::memcpy(&bits,&value,sizeof(bits));words[0x82836A08u+offset]=bits;
}
void Result(PPCContext& ctx,uint8_t* base,unsigned tag) {
    base_seen=base;ctx.guest_effect=tag;ctx.marker=0xfedcba9876543210ull;
    ctx.lr=0xaabbccdd;ctx.r3.u32=2;
}
extern "C" void __imp__sub_82402E38(PPCContext& ctx, uint8_t* base) {
    ++original_calls;base_seen=base;
    comparison_seen=words[0x8283E2F8u];
    ctx.guest_effect=0x12345678u;
}
extern "C" void __imp__sub_82403878(PPCContext& ctx, uint8_t* base) {
    ++sim_calls;Result(ctx,base,2);
    SetFloat(32,.016f);SetFloat(48,.96f);SetFloat(40,.48f);SetFloat(80,1.f);
}
extern "C" void __imp__sub_82141C18(PPCContext& ctx,uint8_t* base) { ++render_calls;Result(ctx,base,3); }
extern "C" void __imp__sub_825AEB90(PPCContext& ctx,uint8_t* base) { ++swap_calls;Result(ctx,base,4); }
''' + program)
            binary = root / 'timing-test.exe'
            compiled = subprocess.run([compiler, '-std=c++23', '-Wall', '-Wextra', '-I', str(root),
                                       str(root / 'test.cpp'), '-o', str(binary)],
                                      capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_uncapped_preserves_guest_routine_and_only_adjusts_known_pacing_clock(self):
        self.run_cpp(r'''

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

    def test_opt_in_aggregates_preserve_original_results_and_only_log_after_five_seconds(self):
        self.run_cpp(r'''
int main() {
    words[0x82836A24u]=0x42700000u;
    words[0x82839488u]=0x8247CE30u;
    words[0x82BA0348u]=99;
    uint8_t base[1]{};
    for(bool enabled : {false,true}) {
        aster_frame_diagnostics=enabled;
        auto old_words=words;
        const auto sim_before=sim_calls,render_before=render_calls,swap_before=swap_calls;
        for(auto [function,tag] : {std::pair{sub_82403878,2u},
                                 std::pair{sub_82141C18,3u},std::pair{sub_825AEB90,4u}}) {
            PPCContext ctx;ctx.lr=0x11223344u;
            const unsigned before_reads=reads;
            function(ctx,base);
            assert(ctx.lr==0xaabbccdd && ctx.r3.u32==2 && ctx.guest_effect==tag);
            assert(ctx.marker==0xfedcba9876543210ull && base_seen==base);
            if(!enabled) assert(reads==before_reads); // No diagnostic guest reads while disabled.
        }
        assert(sim_calls==sim_before+1 && render_calls==render_before+1 && swap_calls==swap_before+1);
        if(enabled) assert(words==old_words); // Observation adds no guest writes.
        assert(logs.empty()); // A frame never causes a frame-level log.
    }
    assert(simulation_diagnostics.window.calls==1 && simulation_diagnostics.substeps==2);
    assert(std::abs(simulation_diagnostics.elapsed_s-.016)<.000001);
    assert(std::abs(simulation_diagnostics.scaled_s-.016)<.000001);
    assert(render_diagnostics.window.calls==1 && swap_diagnostics.window.calls==1);
    aster_experimental_unlimited_fps=true;
    PPCContext pacing;sub_82402E38(pacing,base);
    assert(original_calls==1 && pacing.guest_effect==0x12345678u);
    assert(pacing_diagnostics.window.calls==1 && pacing_diagnostics.seeded==1);
    assert(words[0x82BA0348u]==99 && comparison_seen==98 && logs.empty());

    // Enabling observers must leave the complete guest memory/result contract
    // identical for known/unknown callbacks, disabled pacing and unknown modes.
    for(bool unlimited : {false,true}) for(uint32_t mode : {0x41f00000u,0x42700000u,0x42f00000u})
    for(uint32_t disabled : {0u,1u}) for(uint32_t callback : {0x8247ce30u,0xdeadbeefu}) {
        auto initial=words;
        initial[0x82836A24u]=mode;initial[0x8283E2CCu]=disabled;
        initial[0x82839488u]=callback;initial[0x8283E2F8u]=77;
        aster_experimental_unlimited_fps=unlimited;aster_experimental_60fps=false;
        words=initial;aster_frame_diagnostics=false;
        PPCContext without;without.lr=123;without.marker=456;
        sub_82402E38(without,base);
        auto expected=words;
        words=initial;aster_frame_diagnostics=true;
        PPCContext observed;observed.lr=123;observed.marker=456;
        sub_82402E38(observed,base);
        assert(words==expected);
        assert(observed.lr==without.lr && observed.r3.u32==without.r3.u32);
        assert(observed.marker==without.marker && observed.guest_effect==without.guest_effect);
        assert(logs.empty());
    }

    const auto t=DiagnosticClock::time_point{};
    const auto ms=std::chrono::milliseconds(2);
    PacingDiagnostics sample;
    sample.Add(t,t+ms,0xfffffffeu,0xffffffffu,true,true,0x42700000,0,0x8247CE30,1);
    sample.Add(t+ms,t+ms+ms,0xffffffffu,0u,false,true,0x42700000,0,0,2);
    assert(logs.empty() && sample.window.calls==2 && sample.seeded==1 && sample.fallbacks==1);
    assert(sample.first_tick==0xfffffffeu && sample.last_tick==0);
    const auto second=std::chrono::seconds(5);
    sample.Add(t+second,t+second+ms,0u,1u,true,true,0x42700000,0,0x8247CE30,3);
    assert(logs.size()==1 && sample.window.calls==0); // Aggregates reset independently.
    assert(logs.back()[0].find("ASTER_PACING_DIAGNOSTICS")==0);
    assert(logs.back()[2]=="3" && logs.back()[5]=="2" && logs.back()[6]=="1" && logs.back()[7]=="3");
    assert(std::abs(std::stod(logs.back()[3])-6.0)<.000001);

    SimulationDiagnostics sim;
    sim.Add(t,t+ms,.01,.005,2,.005,.5,60);
    sim.Add(t+second,t+second+ms,.02,.01,3,.01,.5,60);
    assert(logs.size()==2 && sim.window.calls==0);
    assert(logs.back()[0].find("ASTER_SIM")==0 && logs.back()[4]=="2" && logs.back()[5]=="5");
    assert(std::abs(std::stod(logs.back()[2])-.03)<.000001);
    assert(std::abs(std::stod(logs.back()[3])-.015)<.000001);
    RenderDiagnostics frame;
    frame.Add("guest_present_call",t,t+ms,7);
    frame.Add("guest_present_call",t+second,t+second+ms,8);
    assert(logs.size()==3 && frame.window.calls==0);
    assert(logs.back()[0].find("unique_frames_verified=false")!=std::string::npos);
    assert(logs.back()[1]=="guest_present_call" && logs.back()[3]=="2");
    assert(std::abs(std::stod(logs.back()[4])-4.)<.000001);
}
''')


if __name__ == '__main__':
    unittest.main()
