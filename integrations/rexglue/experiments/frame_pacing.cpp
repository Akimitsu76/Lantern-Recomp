// Local, opt-in hooks around original recompiled functions. No game code included.
#include "aster_green_lantern_pch.h"
#include <rex/cvar.h>
#include <chrono>
#include <cstdint>
#include <dlfcn.h>
#include <unordered_map>

REXCVAR_DEFINE_BOOL(aster_frame_diagnostics, false, "Aster/Experimental",
                   "Observe game frame and presentation calls without changing guest timing");

REXCVAR_DEFINE_BOOL(aster_experimental_60fps, false, "Aster/Experimental",
                   "Experimental engine target 60; requires simulation validation");

REXCVAR_DEFINE_BOOL(aster_experimental_unlimited_fps, false, "Aster/Experimental",
                   "Experimental uncapped presentation; skips the original vblank pacing wait");

REXCVAR_DEFINE_INT32(aster_unlimited_target, 120, "Aster/Experimental",
                     "Engine clock target when unlimited pacing is enabled");

extern "C" void __imp__sub_8215E758(PPCContext&, uint8_t*);
extern "C" void __imp__sub_825AEB90(PPCContext&, uint8_t*);
extern "C" void __imp__sub_825AE760(PPCContext&, uint8_t*);
extern "C" void __imp__sub_825A4070(PPCContext&, uint8_t*);

namespace {
using Clock = std::chrono::steady_clock;
struct Measurements {
  Clock::time_point since = Clock::now();
  uint64_t count = 0;
  double total_ms = 0;
  double max_ms = 0;
  void Add(const char* name, Clock::time_point start, uint32_t caller, uint32_t interval) {
    auto now = Clock::now();
    double duration = std::chrono::duration<double, std::milli>(now - start).count();
    total_ms += duration;
    if (duration > max_ms) max_ms = duration;
    ++count;
    double seconds = std::chrono::duration<double>(now - since).count();
    if (seconds >= 5.0) {
      REXLOG_INFO("ASTER_FRAME name={} wall_s={:.3f} calls={} rate={:.3f} body_ms={:.3f} max_ms={:.3f} caller={:08X} interval={:08X}",
                  name, seconds, count, count / seconds, total_ms, max_ms, caller, interval);
      since = now; count = 0; total_ms = 0; max_ms = 0;
    }
  }
};
}
extern "C" void sub_8215E758(PPCContext& ctx, uint8_t* base) {
  if (!REXCVAR_GET(aster_frame_diagnostics)) return __imp__sub_8215E758(ctx, base);
  thread_local Measurements stats;
  auto start = Clock::now();
  auto caller = uint32_t(ctx.lr);
  __imp__sub_8215E758(ctx, base);
  stats.Add("game_render", start, caller, 0);
}
extern "C" void sub_825AEB90(PPCContext& ctx, uint8_t* base) {
  if (!REXCVAR_GET(aster_frame_diagnostics)) return __imp__sub_825AEB90(ctx, base);
  thread_local Measurements stats;
  auto start = Clock::now();
  auto caller = uint32_t(ctx.lr);
  uint32_t interval = REX_LOAD_U32(ctx.r3.u32 + 13872);
  __imp__sub_825AEB90(ctx, base);
  stats.Add("present", start, caller, interval);
}
extern "C" void sub_825AE760(PPCContext& ctx, uint8_t* base) {
  if (!REXCVAR_GET(aster_frame_diagnostics)) return __imp__sub_825AE760(ctx, base);
  thread_local Measurements stats;
  auto start = Clock::now();
  auto caller = uint32_t(ctx.lr);
  uint32_t interval = REX_LOAD_U32(ctx.r3.u32 + 13872);
  __imp__sub_825AE760(ctx, base);
  stats.Add("pre_present", start, caller, interval);
}
extern "C" void sub_825A4070(PPCContext& ctx, uint8_t* base) {
  if (REXCVAR_GET(aster_frame_diagnostics)) {
    thread_local uint32_t last = UINT32_MAX;
    if (last != ctx.r4.u32) {
      last = ctx.r4.u32;
      REXLOG_INFO("ASTER_FRAME interval_set value={:08X} caller={:08X}", last, uint32_t(ctx.lr));
    }
  }
  __imp__sub_825A4070(ctx, base);
}

extern "C" void __imp__sub_82141C18(PPCContext&, uint8_t*);
extern "C" void sub_82141C18(PPCContext& ctx, uint8_t* base) {
  if (!REXCVAR_GET(aster_frame_diagnostics)) return __imp__sub_82141C18(ctx, base);
  thread_local Measurements stats;
  auto start = Clock::now();
  auto caller = uint32_t(ctx.lr);
  __imp__sub_82141C18(ctx, base);
  stats.Add("whole_render_frame", start, caller, 0);
}
extern "C" void __imp__sub_82586F30(PPCContext&, uint8_t*);
extern "C" void sub_82586F30(PPCContext& ctx, uint8_t* base) {
  if (!REXCVAR_GET(aster_frame_diagnostics)) return __imp__sub_82586F30(ctx, base);
  thread_local std::unordered_map<uint32_t, Measurements> by_caller;
  auto start = Clock::now();
  auto caller = uint32_t(ctx.lr);
  auto pointer = ctx.r3.u32;
  __imp__sub_82586F30(ctx, base);
  if (by_caller.size() < 64 || by_caller.contains(caller))
    by_caller[caller].Add("clock_read", start, caller, pointer);
}
namespace {
thread_local uint32_t wait_outer = 0;
using GuestFunction = void (*)(PPCContext&, uint8_t*);
GuestFunction OriginalImport(const char* name) {
  auto function = reinterpret_cast<GuestFunction>(dlsym(RTLD_NEXT, name));
  if (!function) {
    REXLOG_ERROR("ASTER_FRAME original import unavailable: {}", name);
    std::abort();
  }
  return function;
}
void ObserveWait(GuestFunction original, const char* name, PPCContext& ctx, uint8_t* base,
                 uint32_t timeout_pointer) {
  if (!REXCVAR_GET(aster_frame_diagnostics)) return original(ctx, base);
  thread_local std::unordered_map<uint64_t, Measurements> by_caller;
  auto start = Clock::now();
  auto caller = uint32_t(ctx.lr);
  int64_t timeout = timeout_pointer ? int64_t(REX_LOAD_U64(timeout_pointer)) : 0;
  original(ctx, base);
  auto key = (uint64_t(caller) << 8) | uint64_t(name[0]);
  if (!by_caller.contains(key) && by_caller.size() < 128) {
    REXLOG_INFO("ASTER_WAIT api={} caller={:08X} outer={:08X}", name, caller, wait_outer);
  }
  if (by_caller.size() < 128 || by_caller.contains(key)) {
    // Diagnostic interval field: absolute magnitude in 100 ns units, clamped.
    uint64_t magnitude = timeout < 0 ? uint64_t(-(timeout + 1)) + 1 : uint64_t(timeout);
    by_caller[key].Add(name, start, caller, uint32_t(std::min(magnitude, uint64_t(UINT32_MAX))));
  }
}
}
extern "C" void __imp__KeWaitForSingleObject(PPCContext& ctx, uint8_t* base) {
  static auto original = OriginalImport("__imp__KeWaitForSingleObject");
  ObserveWait(original, "kernel_wait", ctx, base, ctx.r7.u32);
}
extern "C" void __imp__NtWaitForSingleObjectEx(PPCContext& ctx, uint8_t* base) {
  static auto original = OriginalImport("__imp__NtWaitForSingleObjectEx");
  ObserveWait(original, "nt_wait", ctx, base, ctx.r6.u32);
}
extern "C" void __imp__KeDelayExecutionThread(PPCContext& ctx, uint8_t* base) {
  static auto original = OriginalImport("__imp__KeDelayExecutionThread");
  ObserveWait(original, "delay", ctx, base, ctx.r5.u32);
}

extern "C" void __imp__KeWaitForMultipleObjects(PPCContext& ctx, uint8_t* base) {
  static auto original = OriginalImport("__imp__KeWaitForMultipleObjects");
  ObserveWait(original, "kernel_multi", ctx, base, ctx.r9.u32);
}
extern "C" void __imp__NtWaitForMultipleObjectsEx(PPCContext& ctx, uint8_t* base) {
  static auto original = OriginalImport("__imp__NtWaitForMultipleObjectsEx");
  ObserveWait(original, "nt_multi", ctx, base, ctx.r8.u32);
}

// Capture known wrapper callers without probing guest stack memory.
extern "C" void __imp__sub_82300650(PPCContext&, uint8_t*);
extern "C" void sub_82300650(PPCContext& ctx, uint8_t* base) {
  auto saved = wait_outer;
  wait_outer = uint32_t(ctx.lr);
  __imp__sub_82300650(ctx, base);
  wait_outer = saved;
}
extern "C" void __imp__sub_82375558(PPCContext&, uint8_t*);
extern "C" void sub_82375558(PPCContext& ctx, uint8_t* base) {
  if (!REXCVAR_GET(aster_frame_diagnostics)) return __imp__sub_82375558(ctx, base);
  thread_local std::unordered_map<uint32_t, Measurements> callers;
  auto caller = uint32_t(ctx.lr);
  auto start = Clock::now();
  __imp__sub_82375558(ctx, base);
  if (callers.size() < 64 || callers.contains(caller))
    callers[caller].Add("engine_wait", start, caller, 0);
}
extern "C" void __imp__sub_82403EF8(PPCContext&, uint8_t*);
extern "C" void sub_82403EF8(PPCContext& ctx, uint8_t* base) {
  if (!REXCVAR_GET(aster_frame_diagnostics)) return __imp__sub_82403EF8(ctx, base);
  thread_local std::unordered_map<uint32_t, Measurements> callers;
  auto caller = uint32_t(ctx.lr);
  auto start = Clock::now();
  __imp__sub_82403EF8(ctx, base);
  if (callers.size() < 64 || callers.contains(caller))
    callers[caller].Add("engine_clock", start, caller, 0);
}

extern "C" void __imp__sub_82402E38(PPCContext&, uint8_t*);
extern "C" void sub_82402E38(PPCContext& ctx, uint8_t* base) {
  const bool diagnostics = REXCVAR_GET(aster_frame_diagnostics);
  const bool target_60 = REXCVAR_GET(aster_experimental_60fps);
  const bool unlimited = REXCVAR_GET(aster_experimental_unlimited_fps);
  if (!diagnostics && !target_60 && !unlimited) return __imp__sub_82402E38(ctx, base);
  thread_local Measurements stats;
  thread_local uint32_t last = UINT32_MAX;
  constexpr uint32_t state = 0x82836A08;
  auto fps_bits = REX_LOAD_U32(state + 28);
  if (unlimited && (fps_bits == 0x41F00000u || fps_bits == 0x42700000u)) {
    // The old experiment kept simulation timekeeping at 60, so gameplay never
    // exceeded 60 even though presentation ran free. Raise the engine clock.
    const uint32_t wanted = REXCVAR_GET(aster_unlimited_target) == 240
                                ? 0x43700000u : 0x42F00000u;  // 240.0f / 120.0f
    REX_STORE_U32(state + 28, wanted);
    fps_bits = wanted;
  } else if (target_60 && fps_bits == 0x41F00000u) {
    REX_STORE_U32(state + 28, 0x42700000u);
    fps_bits = 0x42700000u;
  }
  if (last != fps_bits) {
    last = fps_bits;
    PPCRegister value{}; value.u32 = fps_bits;
    REXLOG_INFO("ASTER_PACING target={:.3f} counter_callback={:08X} disabled={} caller={:08X} unlimited={}",
                double(value.f32), REX_LOAD_U32(state + 10880),
                unsigned(REX_LOAD_U8(0x82840000u - 7476)), uint32_t(ctx.lr), unlimited);
  }
  if (unlimited) {
    // The original function only waits for a guest vblank and advances its
    // own pacing counter. Returning here leaves simulation timekeeping (which
    // reads the real clock) intact while presentation is handled by the host
    // swapchain (VSync off + immediate mode).
    if (diagnostics) {
      auto start = Clock::now();
      stats.Add("engine_pacing_bypass", start, uint32_t(ctx.lr), fps_bits);
    }
    return;
  }
  auto start = Clock::now();
  auto caller = uint32_t(ctx.lr);
  __imp__sub_82402E38(ctx, base);
  stats.Add("engine_pacing", start, caller, fps_bits);
}

extern "C" void __imp__sub_82403F68(PPCContext&, uint8_t*);
extern "C" void sub_82403F68(PPCContext& ctx, uint8_t* base) {
  __imp__sub_82403F68(ctx, base);
  if (!REXCVAR_GET(aster_frame_diagnostics)) return;
  thread_local auto since = Clock::now();
  thread_local double elapsed = 0;
  thread_local uint64_t count = 0;
  elapsed += ctx.f1.f64;
  ++count;
  auto now = Clock::now();
  double seconds = std::chrono::duration<double>(now - since).count();
  if (seconds >= 5.0) {
    REXLOG_INFO("ASTER_DELTA wall_s={:.3f} engine_seconds={:.6f} calls={} last_delta={:.6f}",
                seconds, elapsed, count, ctx.f1.f64);
    since = now; elapsed = 0; count = 0;
  }
}

// Observe the engine's original millisecond-based simulation step.
extern "C" void __imp__sub_82403878(PPCContext&, uint8_t*);
extern "C" void sub_82403878(PPCContext& ctx, uint8_t* base) {
  if (!REXCVAR_GET(aster_frame_diagnostics)) return __imp__sub_82403878(ctx, base);
  thread_local auto since = Clock::now();
  thread_local double elapsed = 0, scaled = 0, steps = 0;
  thread_local uint64_t count = 0;
  __imp__sub_82403878(ctx, base);
  auto read_float = [base](uint32_t offset) {
    PPCRegister value{}; value.u32 = REX_LOAD_U32(0x82836A08u + offset);
    return double(value.f32);
  };
  elapsed += read_float(32);
  scaled += read_float(48) / 60.0;
  steps += ctx.r3.u32;
  ++count;
  auto now = Clock::now();
  double seconds = std::chrono::duration<double>(now - since).count();
  if (seconds >= 5.0) {
    REXLOG_INFO("ASTER_SIM wall_s={:.6f} elapsed_s={:.6f} scaled_s={:.6f} calls={} substeps={:.0f} last_dt={:.6f} last_scaled_dt={:.6f} timescale={:.6f} target={:.0f}",
                seconds, elapsed, scaled, count, steps, read_float(32), read_float(40) / 60.0,
                read_float(80), read_float(28));
    since = now; elapsed = 0; scaled = 0; steps = 0; count = 0;
  }
}

extern "C" void __imp__sub_82516240(PPCContext&, uint8_t*);
extern "C" void sub_82516240(PPCContext& ctx, uint8_t* base) {
  if (REXCVAR_GET(aster_frame_diagnostics) && uint32_t(ctx.lr) == 0x8237B300u) {
    thread_local auto since = Clock::now();
    thread_local double elapsed = 0;
    thread_local uint64_t count = 0;
    elapsed += ctx.f1.f64;
    ++count;
    auto now = Clock::now();
    double seconds = std::chrono::duration<double>(now - since).count();
    if (seconds >= 5.0) {
      REXLOG_INFO("ASTER_STEP wall_s={:.6f} elapsed_s={:.6f} calls={} last_dt={:.6f} object={:08X} pause_flag={}",
                  seconds, elapsed, count, ctx.f1.f64, ctx.r3.u32, REX_LOAD_U32(0x82836A08u + 12));
      since = now; elapsed = 0; count = 0;
    }
  }
  __imp__sub_82516240(ctx, base);
}
