// Native main-menu save selection for the supported Green Lantern executable.
// Shared by Linux/Vulkan and Windows/D3D12. No game assets are embedded.
#include "aster_green_lantern_pch.h"
#include <rex/runtime.h>
#include <rex/logging.h>
#include <rex/input/input_system.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xam/content_manager.h>
#include <rex/system/xam/user_profile.h>
#include <rex/thread.h>
#include <rex/ui/imgui_dialog.h>
#include <rex/ui/windowed_app_context.h>
#include <imgui.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstring>
#include <ctime>
#include <memory>
#include <optional>
#include <string>

extern "C" void __imp__sub_823809C0(PPCContext&, uint8_t*);
extern "C" void __imp__sub_8252E010(PPCContext&, uint8_t*);
extern "C" void __imp__sub_823764F8(PPCContext&, uint8_t*);
extern "C" void __imp__sub_823817C0(PPCContext&, uint8_t*);
extern "C" void __imp__sub_823D7310(PPCContext&, uint8_t*);
extern "C" void __imp__sub_822AE450(PPCContext&, uint8_t*);
extern "C" void sub_822AE280(PPCContext&, uint8_t*);
extern "C" void sub_822AE460(PPCContext&, uint8_t*);
extern "C" void sub_823D7310(PPCContext&, uint8_t*);

namespace {
using Slot = rex::system::xam::green_lantern::SaveSlot;
using Slots = std::array<Slot, 6>;
constexpr uint32_t kReadCookie = 0xA57E5107;
std::atomic<int> read_result{-1};
std::atomic<bool> read_pending{false};
std::chrono::steady_clock::time_point ignore_confirmation_until{};
struct NewGameSelection {
  bool pending = false, empty = false, left_main_menu = false;
  uint32_t owner = 0, previous = 1;
} new_game_selection;

struct Choice { std::optional<uint32_t> slot; bool replace = false; };

std::string Date(int64_t seconds) {
  if (!seconds) return "Progresso salvo";
  std::time_t stamp = std::time_t(seconds);
  std::tm value{};
#ifdef _WIN32
  localtime_s(&value, &stamp);
#else
  localtime_r(&stamp, &value);
#endif
  char text[40]; std::strftime(text, sizeof(text), "%d/%m/%Y  %H:%M", &value);
  return text;
}

class SlotDialog final : public rex::ui::ImGuiDialog {
 public:
  SlotDialog(rex::ui::ImGuiDrawer* drawer, rex::input::InputSystem* input,
             Slots slots, uint32_t active, bool new_game, Choice& result)
      : ImGuiDialog(drawer), input_(input), slots_(slots), selected_(int(active) - 1),
        new_game_(new_game), result_(result) {}
 private:
  void Finish() {
    if (!new_game_ && !slots_[selected_].existing) return;
    if (new_game_ && slots_[selected_].existing && !replacing_) {
      replacing_ = true; confirm_replace_ = false; armed_ = false; return;
    }
    if (replacing_ && !confirm_replace_) {
      replacing_ = false; armed_ = false; return;
    }
    result_.slot = slots_[selected_].id;
    result_.replace = replacing_;
    closing_ = true;
  }
  void OnDraw(ImGuiIO& io) override {
    using namespace rex::input;
    X_INPUT_STATE state{};
    uint16_t buttons = 0;
    int direction = 0;
    if (input_ && input_->GetState(0, &state) == 0) {
      buttons = state.gamepad.buttons;
      const int y = state.gamepad.thumb_ly;
      if ((buttons & X_INPUT_GAMEPAD_DPAD_UP) || y > 18000) direction = -1;
      if ((buttons & X_INPUT_GAMEPAD_DPAD_DOWN) || y < -18000) direction = 1;
    }
    const bool accept = (buttons & X_INPUT_GAMEPAD_A) ||
        ImGui::IsKeyDown(ImGuiKey_Enter) || ImGui::IsKeyDown(ImGuiKey_Space);
    const bool back = (buttons & X_INPUT_GAMEPAD_B) ||
        ImGui::IsKeyDown(ImGuiKey_Escape) || ImGui::IsKeyDown(ImGuiKey_Backspace);
    const bool first = !opened_;
    if (first) { ImGui::OpenPopup("Campanhas salvas###aster_slots"); opened_ = true; }
    const float scale = std::clamp(io.DisplaySize.y / 900.0f, 0.85f, 1.7f);
    ImGui::SetNextWindowPos(ImVec2(io.DisplaySize.x * .5f, io.DisplaySize.y * .5f),
                            ImGuiCond_Always, ImVec2(.5f, .5f));
    ImGui::SetNextWindowSize(ImVec2(620 * scale, 0), ImGuiCond_Always);
    if (ImGui::BeginPopupModal("Campanhas salvas###aster_slots", nullptr,
                               ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoMove)) {
      ImGui::SetWindowFontScale(1.15f * scale);
      ImGui::TextUnformatted(new_game_ ? "NOVA CAMPANHA" : "CONTINUAR CAMPANHA");
      ImGui::TextWrapped(new_game_ ? "Escolha onde guardar o novo progresso."
                                  : "Escolha o progresso que deseja carregar.");
      ImGui::Separator();
      if (replacing_) {
        ImGui::TextWrapped("O Slot %u ja possui uma campanha. Uma copia de seguranca sera criada antes de substituir o progresso.", slots_[selected_].id);
        if (ImGui::Selectable("Voltar", !confirm_replace_)) { replacing_ = false; armed_ = false; }
        if (ImGui::Selectable("Criar backup e usar este slot", confirm_replace_)) {
          confirm_replace_ = true; Finish();
        }
      } else {
        for (int i = 0; i < 6; ++i) {
          const auto& slot = slots_[i];
          const auto label = "Slot " + std::to_string(slot.id) + "    " +
              (slot.existing ? Date(slot.modified) : "Vazio");
          ImGui::BeginDisabled(!new_game_ && !slot.existing);
          if (ImGui::Selectable(label.c_str(), selected_ == i, 0, ImVec2(0, 36 * scale))) {
            selected_ = i; Finish();
          }
          ImGui::EndDisabled();
        }
      }
      ImGui::Separator();
      ImGui::TextWrapped("Setas / direcional: escolher   Enter / A: confirmar   Esc / B: voltar");
      if (ImGui::Button("Voltar", ImVec2(130 * scale, 0))) {
        if (replacing_) replacing_ = false;
        else closing_ = true;
      }
      if (!armed_) {
        if (!accept && !back && !direction) armed_ = true;
      } else {
        const bool move_up = ImGui::IsKeyPressed(ImGuiKey_UpArrow) ||
            ImGui::IsKeyPressed(ImGuiKey_W) || (direction == -1 && previous_direction_ != -1);
        const bool move_down = ImGui::IsKeyPressed(ImGuiKey_DownArrow) ||
            ImGui::IsKeyPressed(ImGuiKey_S) || (direction == 1 && previous_direction_ != 1);
        if (move_up || move_down) {
          if (replacing_) confirm_replace_ = !confirm_replace_;
          else {
            const int step = move_up ? -1 : 1;
            for (int attempt = 0; attempt < 6; ++attempt) {
              selected_ = (selected_ + step + 6) % 6;
              if (new_game_ || slots_[selected_].existing) break;
            }
          }
        }
        if (back && !previous_back_) {
          if (replacing_) { replacing_ = false; armed_ = false; }
          else closing_ = true;
        } else if (accept && !previous_accept_) Finish();
      }
      // Do not hand a held confirmation/back button to the original menu.
      if (closing_ && !accept && !back && !direction && !ImGui::IsMouseDown(0)) {
        ImGui::CloseCurrentPopup(); Close();
      }
      ImGui::EndPopup();
    } else Close();
    previous_accept_ = accept; previous_back_ = back; previous_direction_ = direction;
  }
  rex::input::InputSystem* input_;
  Slots slots_;
  int selected_;
  bool new_game_, opened_ = false, armed_ = false, replacing_ = false, closing_ = false;
  bool confirm_replace_ = false, previous_accept_ = true, previous_back_ = false;
  int previous_direction_ = 0;
  Choice& result_;
};

void Message(rex::Runtime* runtime, const char* text) {
  rex::thread::Fence fence;
  auto app = runtime->app_context();
  const bool shown = app && app->CallInUIThreadSynchronous([&] {
    rex::ui::ImGuiDialog::ShowMessageBox(runtime->imgui_drawer(), "Campanhas salvas", text)->Then(&fence);
  });
  if (shown) fence.Wait();
}

// The original Continue applies a RAM copy. Re-read GL_10 through the game's
// own asynchronous IO before allowing it to use the newly selected container.
// Pump the original IO update only; never simulate gameplay or rewrite progress.
bool Reload(PPCContext& original, uint8_t* base, uint32_t manager) {
  if (REX_LOAD_U32(manager) != 0x82006B50 || REX_LOAD_U32(manager + 0xe4) != 6) return false;
  std::array<uint8_t, 0x448> old_buffer{};
  std::memcpy(old_buffer.data(), base + manager + 0x530, old_buffer.size());
  PPCContext call = original;
  read_result.store(-1); read_pending.store(true);
  call.r3.u64 = manager; call.r4.u64 = 0x8252E010;
  call.r5.u64 = kReadCookie; call.r6.u64 = 0;
  sub_822AE280(call, base);
  if (call.r3.u32 == 0 && read_result.load() == -1) read_result.store(0);
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(20);
  bool delayed = false;
  while (read_result.load() == -1) {
    // Never abandon a read whose destination is still guest memory: a late IO
    // completion could otherwise overwrite the restored slot's cached data.
    if (!delayed && std::chrono::steady_clock::now() > deadline) {
      delayed = true;
      REXLOG_WARN("ASTER_SAVE_SLOT slow storage read; waiting for original IO completion");
    }
    call = original; call.r3.u64 = manager;
    sub_823D7310(call, base);
    rex::thread::Sleep(std::chrono::milliseconds(2));
  }
  const int result = read_result.load();
  read_pending.store(false);
  REXLOG_INFO("ASTER_SAVE_SLOT reload result={} manager={:08X}", result, manager);
  if (result != 1) {
    std::memcpy(base + manager + 0x530, old_buffer.data(), old_buffer.size());
    return false;
  }
  call = original; call.r3.u64 = manager;
  sub_822AE460(call, base); // Original loaded-settings/cached-profile application.
  return true;
}
} // namespace

extern "C" void sub_823817C0(PPCContext& ctx, uint8_t* base) {
  const auto owner = ctx.r3.u32;
  __imp__sub_823817C0(ctx, base);
  if (new_game_selection.pending && owner == new_game_selection.owner) {
    const auto page = REX_LOAD_U32(owner + 32);
    if (page && REX_LOAD_U32(page + 8) != 1) new_game_selection.left_main_menu = true;
    if (page && REX_LOAD_U32(page + 8) == 1 && new_game_selection.left_main_menu) {
      auto kernel = REX_KERNEL_STATE();
      const auto result = kernel->content_manager()->SelectGreenLanternSaveSlot(
          kernel->user_profile()->xuid(), new_game_selection.previous);
      REXLOG_INFO("ASTER_SAVE_SLOT new_game_cancelled restore={} result={:08X}", new_game_selection.previous, result);
      new_game_selection = {};
    }
  }
}

extern "C" void sub_823D7310(PPCContext& ctx, uint8_t* base) {
  // The original save job commits the New Game destination. Until then,
  // backing out of difficulty/player selection restores the previous slot.
  if (new_game_selection.pending && REX_LOAD_U32(ctx.r3.u32 + 0xe4) == 2)
    new_game_selection = {};
  __imp__sub_823D7310(ctx, base);
}

extern "C" void sub_822AE450(PPCContext& ctx, uint8_t* base) {
  if (new_game_selection.pending && new_game_selection.empty) {
    ctx.r3.u64 = 0; // No overwrite warning for the newly selected empty slot.
    return;
  }
  __imp__sub_822AE450(ctx, base);
}

// This original startup routine creates the save manager, before its first
// enumeration/read. Keep Continue available if a New Game was cancelled while
// its empty destination was selected during the previous run.
extern "C" void sub_823764F8(PPCContext& ctx, uint8_t* base) {
  static bool initialized = false;
  if (!initialized) {
    initialized = true;
    auto kernel = REX_KERNEL_STATE();
    auto content = kernel->content_manager();
    const auto xuid = kernel->user_profile()->xuid();
    const auto slots = content->GetGreenLanternSaveSlots(xuid);
    const auto active = content->ActiveGreenLanternSaveSlot(xuid);
    if (!slots[active - 1].existing) {
      for (const auto& slot : slots) if (slot.existing) {
        const auto result = content->SelectGreenLanternSaveSlot(xuid, slot.id);
        REXLOG_INFO("ASTER_SAVE_SLOT startup from={} to={} result={:08X}", active, slot.id, result);
        break;
      }
    }
  }
  __imp__sub_823764F8(ctx, base);
}

extern "C" void sub_8252E010(PPCContext& ctx, uint8_t* base) {
  if (ctx.r4.u32 == kReadCookie) {
    if (read_pending.load()) read_result.store(ctx.r3.s32);
    return;
  }
  __imp__sub_8252E010(ctx, base);
}

extern "C" void sub_823809C0(PPCContext& ctx, uint8_t* base) {
  if (uint32_t(ctx.lr) != 0x82381E9C || !ctx.r3.u32 || !ctx.r4.u32)
    return __imp__sub_823809C0(ctx, base);
  const uint32_t owner = ctx.r3.u32, item = ctx.r4.u32;
  const uint32_t page = REX_LOAD_U32(owner + 32), child = REX_LOAD_U32(item + 152);
  if (!page || !child || REX_LOAD_U32(page + 8) != 1)
    return __imp__sub_823809C0(ctx, base);
  const uint32_t action = REX_LOAD_U32(child + 8);
  if ((action != 1 && action != 2) || (REX_LOAD_U32(child + 16) & 4))
    return __imp__sub_823809C0(ctx, base);
  if (std::chrono::steady_clock::now() < ignore_confirmation_until) return;
  auto kernel = REX_KERNEL_STATE();
  auto runtime = kernel->emulator();
  if (!runtime->imgui_drawer() || !runtime->app_context()) return;
  auto content = kernel->content_manager();
  const uint64_t xuid = kernel->user_profile()->xuid();
  const auto slots = content->GetGreenLanternSaveSlots(xuid);
  const uint32_t before = content->ActiveGreenLanternSaveSlot(xuid);
  Choice choice;
  REXLOG_INFO("ASTER_SAVE_SLOT open action={} active={}", action, before);
  rex::thread::Fence fence;
  const bool shown = runtime->app_context()->CallInUIThreadSynchronous([&] {
    (new SlotDialog(runtime->imgui_drawer(),
         dynamic_cast<rex::input::InputSystem*>(runtime->input_system()),
         slots, before, action == 1, choice))->Then(&fence);
  });
  if (!shown) return;
  fence.Wait();
  ignore_confirmation_until = std::chrono::steady_clock::now() + std::chrono::milliseconds(350);
  if (!choice.slot) { REXLOG_INFO("ASTER_SAVE_SLOT cancelled action={}", action); return; }
  const auto selected = *choice.slot;
  if (action == 2 && !slots[selected - 1].existing) return;
  if (choice.replace && content->BackupGreenLanternSaveSlot(xuid, selected) != 0) {
    Message(runtime, "Nao foi possivel criar o backup. A campanha foi preservada."); return;
  }
  const auto result = content->SelectGreenLanternSaveSlot(xuid, selected);
  REXLOG_INFO("ASTER_SAVE_SLOT select action={} from={} to={} result={:08X}", action, before, selected, result);
  if (result != 0) { Message(runtime, "O save ainda esta em uso ou nao pode ser aberto. Tente novamente."); return; }
  if (action == 2) {
    new_game_selection = {};
    const auto globals = REX_LOAD_U32(0x8283691C);
    const auto manager = globals ? REX_LOAD_U32(globals + 0x5b4) : 0;
    if (!manager || !Reload(ctx, base, manager)) {
      content->SelectGreenLanternSaveSlot(xuid, before);
      Message(runtime, "Nao foi possivel carregar este slot. Nenhum progresso foi substituido."); return;
    }
  }
  if (action == 1)
    new_game_selection = {true, !slots[selected - 1].existing, false, owner, before};
  // The original menu still owns difficulty, campaign startup and autosaving.
  ignore_confirmation_until = std::chrono::steady_clock::now() + std::chrono::milliseconds(350);
  return __imp__sub_823809C0(ctx, base);
}
