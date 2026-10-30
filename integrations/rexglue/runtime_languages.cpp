// Original host hooks. The original game validates each independent selection
// against the language arrays declared by its own SKU before applying it.
#include "aster_green_lantern_pch.h"
#include <rex/cvar.h>
#include <rex/logging.h>
#include <atomic>

REXCVAR_DEFINE_INT32(aster_ui_language, -1, "Aster/Languages",
                    "Original engine text language (-1 preserves the game default)");
REXCVAR_DEFINE_INT32(aster_spoken_language, -1, "Aster/Languages",
                    "Original engine voice language (-1 preserves the game default)");

namespace {
bool SupportedText(int32_t value) {
    return value == 0 || value == 1 || value == 3 || value == 4 || value == 5 || value == 11;
}
bool SupportedVoice(int32_t value) {
    return value == 0 || value == 1 || value == 3 || value == 4 || value == 5;
}
bool TextSelectionCaller(uint32_t caller) {
    // Original startup, platform-language apply, and explicit UI-language apply.
    // Do not alter the SKU capability-query callback (824B9BD0).
    return caller == 0x82378D10u || caller == 0x824C0B9Cu || caller == 0x824C05B4u;
}
bool VoiceSelectionCaller(uint32_t caller) {
    return caller == 0x82378C58u || caller == 0x82378D20u || caller == 0x824C0BA8u;
}
std::atomic<bool> text_reported{false}, voice_reported{false};
}  // namespace

extern "C" void __imp__sub_82376988(PPCContext&, uint8_t*);
extern "C" void sub_82376988(PPCContext& ctx, uint8_t* base) {
    const auto selected = REXCVAR_GET(aster_ui_language);
    const auto caller = uint32_t(ctx.lr);
    const bool override = SupportedText(selected) && TextSelectionCaller(caller);
    if (override) ctx.r3.s64 = selected;
    __imp__sub_82376988(ctx, base);
    if (override && !text_reported.exchange(true, std::memory_order_relaxed)) {
        REXLOG_INFO("ASTER_LANGUAGE selection=text requested={} actual={} sku_validated=true caller={:08X}",
                    selected, ctx.r3.s32, caller);
    }
}

extern "C" void __imp__sub_823769D8(PPCContext&, uint8_t*);
extern "C" void sub_823769D8(PPCContext& ctx, uint8_t* base) {
    const auto selected = REXCVAR_GET(aster_spoken_language);
    const auto caller = uint32_t(ctx.lr);
    const bool override = SupportedVoice(selected) && VoiceSelectionCaller(caller);
    if (override) ctx.r3.s64 = selected;
    __imp__sub_823769D8(ctx, base);
    if (override && !voice_reported.exchange(true, std::memory_order_relaxed)) {
        REXLOG_INFO("ASTER_LANGUAGE selection=voice requested={} actual={} sku_validated=true caller={:08X}",
                    selected, ctx.r3.s32, caller);
    }
}
