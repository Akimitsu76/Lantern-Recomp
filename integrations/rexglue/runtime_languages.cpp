// Original host hooks. The original game validates each independent selection
// against the language arrays declared by its own SKU before applying it.
//
// X360_GL_EUROPE exposes text slots {0,1,3,4,5,11} and voice slots
// {0,1,3,4,5}. The values are engine language IDs, not Xbox locale IDs:
//   0 English, 1 French, 3 Spanish, 4 German, 5 Italian, 11 Portuguese (text).
// The European dump has no Portuguese dialogue bank, so voice 11 is rejected
// and the original falls back to the first slot. The launcher therefore sends
// Portuguese text with an English voice by default.
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
std::atomic<bool> text_done{false}, voice_done{false};
std::atomic<bool> text_rejected{false}, voice_rejected{false};
std::atomic<bool> text_unsupported{false}, voice_unsupported{false};
}  // namespace

extern "C" void __imp__sub_82376988(PPCContext&, uint8_t*);
extern "C" void sub_82376988(PPCContext& ctx, uint8_t* base) {
    const auto selected = REXCVAR_GET(aster_ui_language);
    const auto caller = uint32_t(ctx.lr);
    if (selected >= 0 && !SupportedText(selected) &&
        !text_unsupported.exchange(true, std::memory_order_relaxed)) {
        REXLOG_WARN("ASTER_LANGUAGE request=text id={} is not a Europe SKU text slot "
                    "(0,1,3,4,5,11); the original keeps its own choice", selected);
    }
    const bool override = SupportedText(selected) && TextSelectionCaller(caller);
    if (override) ctx.r3.s64 = selected;
    __imp__sub_82376988(ctx, base);
    if (!override) {
        return;
    }
    const int32_t actual = ctx.r3.s32;
    if (actual == selected) {
        if (!text_done.exchange(true, std::memory_order_relaxed)) {
            REXLOG_INFO("ASTER_LANGUAGE selection=text requested={} actual={} "
                        "sku_validated=true caller={:08X}", selected, actual, caller);
        }
    } else if (!text_rejected.exchange(true, std::memory_order_relaxed)) {
        REXLOG_WARN("ASTER_LANGUAGE selection=text requested={} actual={} caller={:08X}: "
                    "the original rejected the slot and kept its fallback", selected,
                    actual, caller);
    }
}

extern "C" void __imp__sub_823769D8(PPCContext&, uint8_t*);
extern "C" void sub_823769D8(PPCContext& ctx, uint8_t* base) {
    const auto selected = REXCVAR_GET(aster_spoken_language);
    const auto caller = uint32_t(ctx.lr);
    if (selected >= 0 && !SupportedVoice(selected) &&
        !voice_unsupported.exchange(true, std::memory_order_relaxed)) {
        REXLOG_WARN("ASTER_LANGUAGE request=voice id={} has no dialogue bank in this dump "
                    "(0,1,3,4,5); the original falls back", selected);
    }
    const bool override = SupportedVoice(selected) && VoiceSelectionCaller(caller);
    if (override) ctx.r3.s64 = selected;
    __imp__sub_823769D8(ctx, base);
    if (!override) {
        return;
    }
    const int32_t actual = ctx.r3.s32;
    if (actual == selected) {
        if (!voice_done.exchange(true, std::memory_order_relaxed)) {
            REXLOG_INFO("ASTER_LANGUAGE selection=voice requested={} actual={} "
                        "sku_validated=true caller={:08X}", selected, actual, caller);
        }
    } else if (!voice_rejected.exchange(true, std::memory_order_relaxed)) {
        REXLOG_WARN("ASTER_LANGUAGE selection=voice requested={} actual={} caller={:08X}: "
                    "the original rejected the slot and kept its fallback", selected,
                    actual, caller);
    }
}
