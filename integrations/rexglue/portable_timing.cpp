// Original host hooks only; the user's code is generated locally by ReXGlue.
#include "aster_green_lantern_pch.h"
#include <rex/cvar.h>
#include <rex/logging.h>
#include <chrono>
#include <cstring>

REXCVAR_DEFINE_BOOL(aster_experimental_60fps, false, "Aster/Experimental",
                   "Select the game's existing 60 Hz pacing path");
REXCVAR_DEFINE_BOOL(aster_experimental_unlimited_fps, false, "Aster/Experimental",
                   "Experimental: bypass guest pacing; gameplay not certified");
REXCVAR_DEFINE_BOOL(aster_frame_diagnostics, false, "Aster/Experimental",
                   "Observe pacing, simulation and render calls in five-second aggregates");

namespace {
using DiagnosticClock = std::chrono::steady_clock;
// Observation only: these counters never supply guest clocks or frame deltas.
// Opt in at launch. Windows are per guest thread and per function, not aligned
// monitor samples. Body costs may overlap (render can include a present call).
// Simulation fields follow the verified original layout, not a gameplay verdict.
struct DiagnosticWindow {
    DiagnosticClock::time_point since{};
    uint64_t calls = 0;
    double body_ms = 0, max_ms = 0;
    void Add(DiagnosticClock::time_point start, DiagnosticClock::time_point end) {
        if (!calls) since = start;
        const double milliseconds = std::chrono::duration<double, std::milli>(end - start).count();
        ++calls;
        body_ms += milliseconds;
        if (milliseconds > max_ms) max_ms = milliseconds;
    }
    double Seconds(DiagnosticClock::time_point now) const {
        return std::chrono::duration<double>(now - since).count();
    }
    bool Due(DiagnosticClock::time_point now) const { return calls && Seconds(now) >= 5.0; }
};
struct PacingDiagnostics {
    DiagnosticWindow window;
    uint64_t seeded = 0, fallbacks = 0;
    uint32_t first_tick = 0, last_tick = 0;
    void Add(DiagnosticClock::time_point start, DiagnosticClock::time_point end,
             uint32_t before, uint32_t after, bool did_seed, bool unlimited,
             uint32_t target, uint32_t disabled, uint32_t callback, uint32_t caller) {
        if (!window.calls) first_tick = before;
        window.Add(start, end);
        last_tick = after;
        seeded += did_seed;
        fallbacks += unlimited && !did_seed;
        if (!window.Due(end)) return;
        REXLOG_INFO("ASTER_PACING_DIAGNOSTICS wall_s={:.6f} calls={} body_ms={:.6f} max_ms={:.6f} seeded={} fallbacks={} real_tick_delta={} last_target_bits={:08X} last_disabled={} last_callback={:08X} last_caller={:08X}",
                    window.Seconds(end), window.calls, window.body_ms, window.max_ms,
                    seeded, fallbacks, uint32_t(last_tick - first_tick), target, disabled, callback, caller);
        *this = {};
    }
};
struct SimulationDiagnostics {
    DiagnosticWindow window;
    double elapsed_s = 0, scaled_s = 0;
    uint64_t substeps = 0;
    void Add(DiagnosticClock::time_point start, DiagnosticClock::time_point end,
             double elapsed, double scaled, uint32_t steps, double last_delta,
             double timescale, double target) {
        window.Add(start, end);
        elapsed_s += elapsed;
        scaled_s += scaled;
        substeps += steps;
        if (!window.Due(end)) return;
        REXLOG_INFO("ASTER_SIM wall_s={:.6f} elapsed_s={:.6f} scaled_s={:.6f} calls={} substeps={} last_dt={:.6f} last_scaled_dt={:.6f} timescale={:.6f} target={:.0f} body_ms={:.6f} max_ms={:.6f}",
                    window.Seconds(end), elapsed_s, scaled_s, window.calls, substeps,
                    elapsed, last_delta, timescale, target, window.body_ms, window.max_ms);
        *this = {};
    }
};
struct RenderDiagnostics {
    DiagnosticWindow window;
    void Add(const char* name, DiagnosticClock::time_point start,
             DiagnosticClock::time_point end, uint32_t caller) {
        window.Add(start, end);
        if (!window.Due(end)) return;
        // A returned render/swap call does not prove a unique displayed frame.
        REXLOG_INFO("ASTER_RENDER_DIAGNOSTICS name={} wall_s={:.6f} calls={} body_ms={:.6f} max_ms={:.6f} caller={:08X} unique_frames_verified=false",
                    name, window.Seconds(end), window.calls, window.body_ms, window.max_ms, caller);
        *this = {};
    }
};
thread_local PacingDiagnostics pacing_diagnostics;
thread_local SimulationDiagnostics simulation_diagnostics;
thread_local RenderDiagnostics render_diagnostics, swap_diagnostics;
double StateFloat(uint8_t* base, uint32_t offset) {
    const uint32_t bits = REX_LOAD_U32(0x82836A08u + offset);
    float value;
    std::memcpy(&value, &bits, sizeof(value));
    return double(value);
}
}  // namespace

extern "C" void __imp__sub_82402E38(PPCContext&, uint8_t*);
extern "C" void sub_82402E38(PPCContext& ctx, uint8_t* base) {
    const bool diagnostics = REXCVAR_GET(aster_frame_diagnostics);
    bool unlimited = REXCVAR_GET(aster_experimental_unlimited_fps);
    bool seeded = false;
    constexpr uint32_t target = 0x82836A24u;
    if (unlimited || REXCVAR_GET(aster_experimental_60fps)) {
        if (REX_LOAD_U32(target) == 0x41F00000u)
            REX_STORE_U32(target, 0x42700000u);
    }
    if (unlimited && REX_LOAD_U32(target) == 0x42700000u &&
        REX_LOAD_U8(0x8283E2CCu) == 0 &&
        REX_LOAD_U32(0x82839488u) == 0x8247CE30u) {
        // The verified callback reads the display counter at 0x82BA0348.
        // Seed only the pacing comparison so the original routine need not
        // wait for its next tick. Keep its actual callback, register effects,
        // stack frame and counter commit: replacing those broke menu input.
        // Unsigned subtraction also preserves the comparison across wrap.
        REX_STORE_U32(0x8283E2F8u, REX_LOAD_U32(0x82BA0348u) - uint32_t(1));
        seeded = true;
    }
    // Unknown callbacks, modes and disabled pacing keep the guest routine.
    if (!diagnostics) return __imp__sub_82402E38(ctx, base);
    const uint32_t caller = uint32_t(ctx.lr);
    const uint32_t before = REX_LOAD_U32(0x82BA0348u);
    const uint32_t mode = REX_LOAD_U32(target);
    const uint32_t disabled = REX_LOAD_U8(0x8283E2CCu);
    const uint32_t callback = REX_LOAD_U32(0x82839488u);
    const auto start = DiagnosticClock::now();
    __imp__sub_82402E38(ctx, base);
    const auto end = DiagnosticClock::now();
    pacing_diagnostics.Add(start, end, before, REX_LOAD_U32(0x82BA0348u),
                           seeded, unlimited, mode, disabled, callback, caller);
}

extern "C" void __imp__sub_82403878(PPCContext&, uint8_t*);
extern "C" void sub_82403878(PPCContext& ctx, uint8_t* base) {
    if (!REXCVAR_GET(aster_frame_diagnostics)) return __imp__sub_82403878(ctx, base);
    const auto start = DiagnosticClock::now();
    __imp__sub_82403878(ctx, base);
    const auto end = DiagnosticClock::now();
    simulation_diagnostics.Add(start, end, StateFloat(base, 32), StateFloat(base, 48) / 60.0,
                               ctx.r3.u32, StateFloat(base, 40) / 60.0,
                               StateFloat(base, 80), StateFloat(base, 28));
}

extern "C" void __imp__sub_82141C18(PPCContext&, uint8_t*);
extern "C" void sub_82141C18(PPCContext& ctx, uint8_t* base) {
    if (!REXCVAR_GET(aster_frame_diagnostics)) return __imp__sub_82141C18(ctx, base);
    const uint32_t caller = uint32_t(ctx.lr);
    const auto start = DiagnosticClock::now();
    __imp__sub_82141C18(ctx, base);
    const auto end = DiagnosticClock::now();
    render_diagnostics.Add("whole_render_frame", start, end, caller);
}

extern "C" void __imp__sub_825AEB90(PPCContext&, uint8_t*);
extern "C" void sub_825AEB90(PPCContext& ctx, uint8_t* base) {
    if (!REXCVAR_GET(aster_frame_diagnostics)) return __imp__sub_825AEB90(ctx, base);
    const uint32_t caller = uint32_t(ctx.lr);
    const auto start = DiagnosticClock::now();
    __imp__sub_825AEB90(ctx, base);
    const auto end = DiagnosticClock::now();
    swap_diagnostics.Add("guest_present_call", start, end, caller);
}
