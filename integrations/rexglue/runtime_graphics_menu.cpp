// Original host code. Curated graphics overlay backed by the runtime CVars.
//
// The SDK already ships an exhaustive CVar editor on F4. This overlay exists
// because a player should not have to know CVar names: it groups the settings
// that change the picture, offers the same presets as the launcher, and shows
// which ones apply immediately and which need a restart.
#include "aster_graphics_menu.h"

#include "aster_green_lantern_pch.h"

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ui/imgui_dialog.h>
#include <rex/ui/imgui_drawer.h>
#include <rex/ui/keybinds.h>

#include <imgui.h>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdlib>
#include <memory>
#include <string>
#include <string_view>

namespace aster::ui {
namespace {

constexpr const char* kBindName = "bind_aster_graphics";

bool HasFlag(std::string_view name) {
  return rex::cvar::GetFlagInfo(name) != nullptr;
}

bool Allowed(std::string_view name, std::string_view value) {
  const auto* info = rex::cvar::GetFlagInfo(name);
  if (!info) {
    return false;
  }
  if (!info->constraints.HasAllowedValues()) {
    return true;
  }
  const auto& allowed = info->constraints.allowed_values;
  return std::find(allowed.begin(), allowed.end(), value) != allowed.end();
}

std::string Current(std::string_view name) {
  return HasFlag(name) ? rex::cvar::GetFlagByName(name) : std::string();
}

void Apply(std::string_view name, std::string_view value) {
  if (HasFlag(name) && !rex::cvar::SetFlagByName(name, value)) {
    REXLOG_WARN("Aster graphics: {} rejected value {}", name, value);
  }
}

// Mirrors the label the SDK settings overlay uses, so both screens agree on
// whether a change is immediate or needs a restart.
const char* LifecycleBadge(std::string_view name) {
  const auto* info = rex::cvar::GetFlagInfo(name);
  if (!info) {
    return " [indisponível]";
  }
  switch (info->lifecycle) {
    case rex::cvar::Lifecycle::kHotReload:
      return " [ao vivo]";
    case rex::cvar::Lifecycle::kRequiresRestart:
      return " [reiniciar]";
    case rex::cvar::Lifecycle::kInitOnly:
      return " [inicialização]";
  }
  return "";
}

void Label(std::string_view text, std::string_view flag) {
  ImGui::TextUnformatted(std::string(text).c_str());
  ImGui::SameLine();
  ImGui::TextDisabled("%s", LifecycleBadge(flag));
}

struct Option {
  const char* label;
  const char* value;
};

// Draws one row only when the runtime actually declares the CVar. Names differ
// between SDK builds, so a missing flag hides the row instead of breaking the
// whole menu.
void ChoiceRow(const char* text, std::string_view flag, const Option* options, int count) {
  if (!HasFlag(flag)) {
    return;
  }
  Label(text, flag);
  const std::string value = Current(flag);
  int selected = 0;
  for (int index = 0; index < count; ++index) {
    if (value == options[index].value && Allowed(flag, options[index].value)) {
      selected = index;
      break;
    }
  }
  ImGui::SetNextItemWidth(260.0f);
  ImGui::PushID(std::string(flag).c_str());
  if (ImGui::BeginCombo("##choice", options[selected].label)) {
    for (int index = 0; index < count; ++index) {
      if (!Allowed(flag, options[index].value)) {
        continue;
      }
      const bool active = index == selected;
      if (ImGui::Selectable(options[index].label, active)) {
        Apply(flag, options[index].value);
      }
      if (active) {
        ImGui::SetItemDefaultFocus();
      }
    }
    ImGui::EndCombo();
  }
  ImGui::PopID();
}

void BoolRow(const char* text, std::string_view flag) {
  if (!HasFlag(flag)) {
    return;
  }
  Label(text, flag);
  bool enabled = Current(flag) == "true";
  ImGui::PushID(std::string(flag).c_str());
  if (ImGui::Checkbox("##bool", &enabled)) {
    Apply(flag, enabled ? "true" : "false");
  }
  ImGui::PopID();
}

void ApplyPreset(int preset) {
  struct Preset {
    const char* scale;
    const char* anisotropic;
    const char* effect;
    const char* post;
    const char* soft;
    const char* hard;
    const char* rtt;
  };
  // Kept in step with native_port/graphics.py so the launcher and the in-game
  // menu describe the same image quality.
  static constexpr Preset kPresets[] = {
      {"1", "1", "bilinear", "none", "192", "384", "16"},
      {"1", "3", "bilinear", "fxaa", "384", "768", "24"},
      {"2", "4", "fsr", "fxaa", "512", "1024", "32"},
      {"3", "5", "fsr", "fxaa_extreme", "768", "1536", "48"},
  };
  const Preset& selected = kPresets[std::clamp(preset, 0, 3)];
  Apply("resolution_scale", selected.scale);
  Apply("anisotropic_override", selected.anisotropic);
  Apply("present_effect", selected.effect);
  Apply("swap_post_effect", selected.post);
  Apply("present_dither", "false");
  Apply("texture_cache_memory_limit_soft", selected.soft);
  Apply("texture_cache_memory_limit_hard", selected.hard);
  Apply("texture_cache_memory_limit_render_to_texture", selected.rtt);
}

class AsterGraphicsDialog final : public rex::ui::ImGuiDialog {
 public:
  explicit AsterGraphicsDialog(rex::ui::ImGuiDrawer* drawer) : ImGuiDialog(drawer) {}

 protected:
  void OnDraw(ImGuiIO& io) override {
    (void)io;
    if (!open_) {
      return;
    }
    ImGui::SetNextWindowSize(ImVec2(620.0f, 660.0f), ImGuiCond_FirstUseEver);
    ImGui::SetNextWindowPos(ImVec2(80.0f, 60.0f), ImGuiCond_FirstUseEver);
    const bool expanded = ImGui::Begin("Gráficos (Aster) — F1 fecha", &open_,
                                       ImGuiWindowFlags_NoCollapse);
    if (!expanded) {
      ImGui::End();
      return;
    }

    ImGui::TextWrapped(
        "Ajustes aplicados ao motor em execução. As marcações indicam o que muda na hora e o "
        "que só vale na próxima inicialização.");
    ImGui::Separator();

    ImGui::TextUnformatted("Presets");
    const char* presets[] = {"Baixa", "Média", "Alta", "Ultra"};
    for (int index = 0; index < 4; ++index) {
      if (index) {
        ImGui::SameLine();
      }
      if (ImGui::Button(presets[index])) {
        ApplyPreset(index);
      }
    }

    ImGui::Separator();
    ImGui::TextUnformatted("Desempenho");
    if (HasFlag("aster_experimental_unlimited_fps")) {
      bool unlimited = Current("aster_experimental_unlimited_fps") == "true";
      bool sixty = Current("aster_experimental_60fps") == "true";
      Label("Limite de quadros", "aster_experimental_unlimited_fps");
      if (ImGui::RadioButton("30 fps (original)", !sixty && !unlimited)) {
        Apply("aster_experimental_60fps", "false");
        Apply("aster_experimental_unlimited_fps", "false");
      }
      ImGui::SameLine();
      if (ImGui::RadioButton("60 fps", sixty)) {
        Apply("aster_experimental_60fps", "true");
        Apply("aster_experimental_unlimited_fps", "false");
      }
      ImGui::SameLine();
      if (ImGui::RadioButton("Ilimitado", unlimited)) {
        Apply("aster_experimental_60fps", "false");
        Apply("aster_experimental_unlimited_fps", "true");
      }
    }
    BoolRow("VSync", "vsync");
    BoolRow("Diagnóstico de quadros", "aster_frame_diagnostics");

    ImGui::Separator();
    ImGui::TextUnformatted("Imagem");
    static constexpr Option kEffects[] = {{"Bilinear", "bilinear"},
                                          {"CAS", "cas"},
                                          {"FSR 1 (espacial)", "fsr"},
                                          {"FSR 2", "fsr2"},
                                          {"FSR 3", "fsr3"}};
    ChoiceRow("Ampliação", "present_effect", kEffects, 5);
    static constexpr Option kQuality[] = {{"Automática", "auto"},
                                          {"Nativa (AA)", "nativeaa"},
                                          {"Qualidade", "quality"},
                                          {"Equilibrada", "balanced"},
                                          {"Desempenho", "performance"},
                                          {"Ultra desempenho", "ultra_performance"}};
    ChoiceRow("Qualidade temporal (FSR 2/3)", "present_fsr_quality_mode", kQuality, 6);
    static constexpr Option kPost[] = {{"Desligado", "none"},
                                       {"FXAA", "fxaa"},
                                       {"FXAA intenso", "fxaa_extreme"}};
    ChoiceRow("Antisserrilhado", "swap_post_effect", kPost, 3);
    BoolRow("Dithering de saída", "present_dither");

    if (HasFlag("present_fsr_sharpness_reduction")) {
      // The runtime stores RCAS reduction in stops; players think in the
      // launcher's 0-100 sharpness. Keep the same conversion as the launcher.
      const double reduction = std::atof(Current("present_fsr_sharpness_reduction").c_str());
      int sharpness = static_cast<int>(std::lround((1.0 - reduction * 0.5) * 100.0));
      sharpness = std::clamp(sharpness, 0, 100);
      Label("Nitidez FSR/CAS", "present_fsr_sharpness_reduction");
      ImGui::SetNextItemWidth(260.0f);
      if (ImGui::SliderInt("##sharpness", &sharpness, 0, 100)) {
        const double stops = 2.0 * (1.0 - sharpness / 100.0);
        Apply("present_fsr_sharpness_reduction", std::to_string(stops));
      }
      static constexpr int kPresets[] = {0, 15, 30, 50, 70};
      static constexpr const char* kPresetLabels[] = {"Sem nitidez", "Suave", "Equilibrado",
                                                      "Nítido", "Muito nítido"};
      for (int index = 0; index < 5; ++index) {
        if (index) {
          ImGui::SameLine();
        }
        if (ImGui::SmallButton(kPresetLabels[index])) {
          const double stops = 2.0 * (1.0 - kPresets[index] / 100.0);
          Apply("present_fsr_sharpness_reduction", std::to_string(stops));
        }
      }
    }
    if (HasFlag("present_effect") && !Allowed("present_effect", "fsr2")) {
      ImGui::TextDisabled(
          "FSR 2/3 e DLSS exigem FidelityFX/Streamline e vetores de movimento; esta "
          "compilação usa FSR 1 espacial e CAS.");
    }

    ImGui::Separator();
    ImGui::TextUnformatted("Resolução e filtragem");
    static constexpr Option kScale[] = {{"1x (1280x720)", "1"},
                                        {"2x (2560x1440)", "2"},
                                        {"3x (3840x2160)", "3"}};
    ChoiceRow("Resolução interna", "resolution_scale", kScale, 3);
    static constexpr Option kAniso[] = {{"Automático", "-1"}, {"Desligado", "0"}, {"1x", "1"},
                                        {"2x", "2"},        {"4x", "3"},       {"8x", "4"},
                                        {"16x", "5"}};
    ChoiceRow("Filtragem anisotrópica", "anisotropic_override", kAniso, 7);

    ImGui::Separator();
    ImGui::TextWrapped(
        "O launcher grava estas opções e as reaplica ao iniciar. F4 abre o editor completo de "
        "CVars; F3 mostra tempos de quadro.");
    ImGui::End();
  }

 private:
  bool open_ = true;
};

std::unique_ptr<AsterGraphicsDialog> g_dialog;
rex::ui::ImGuiDrawer* g_drawer = nullptr;
std::atomic<bool> g_installed{false};

void Toggle() {
  if (g_dialog) {
    // Destroying the dialog unregisters it; no Close() so the toggle can
    // create a fresh window on the next press.
    g_dialog.reset();
  } else if (g_drawer) {
    g_dialog = std::make_unique<AsterGraphicsDialog>(g_drawer);
  }
}

}  // namespace

void InstallGraphicsMenu(rex::ui::ImGuiDrawer* drawer) {
  if (!drawer || g_installed.exchange(true)) {
    return;
  }
  g_drawer = drawer;
  rex::ui::RegisterBind(kBindName, "F1", "Abrir gráficos (Aster)", [] { Toggle(); });
  REXLOG_INFO("Aster graphics menu ready on F1");
}

void UninstallGraphicsMenu() {
  if (!g_installed.exchange(false)) {
    return;
  }
  g_dialog.reset();
  g_drawer = nullptr;
  rex::ui::UnregisterBind(kBindName);
}

}  // namespace aster::ui
