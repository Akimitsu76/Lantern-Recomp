// Original host hooks only; the user's code is generated locally by ReXGlue.
#include "aster_green_lantern_pch.h"
#include <rex/cvar.h>

REXCVAR_DEFINE_BOOL(aster_experimental_60fps, false, "Aster/Experimental",
                   "Select the game's existing 60 Hz pacing path");
REXCVAR_DEFINE_BOOL(aster_experimental_unlimited_fps, false, "Aster/Experimental",
                   "Experimental: bypass guest pacing; gameplay not certified");
REXCVAR_DEFINE_BOOL(aster_frame_diagnostics, false, "Aster/Experimental",
                   "Reserved for compatibility with local probes");

extern "C" void __imp__sub_82402E38(PPCContext&, uint8_t*);
extern "C" void sub_82402E38(PPCContext& ctx, uint8_t* base) {
    bool unlimited = REXCVAR_GET(aster_experimental_unlimited_fps);
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
    }
    // Unknown callbacks, modes and disabled pacing keep the guest routine.
    __imp__sub_82402E38(ctx, base);
}
