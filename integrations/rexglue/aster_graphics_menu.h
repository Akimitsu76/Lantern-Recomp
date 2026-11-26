// Aster in-game graphics menu.
//
// The host wires this into the generated ReXApp subclass so players can change
// the presentation settings without leaving the game. Every control is backed
// by the runtime's own CVars, so the launcher and the in-game menu can never
// disagree about what a setting means.
#pragma once

namespace rex::ui {
class ImGuiDrawer;
}

namespace aster::ui {

// Registers the F1 graphics overlay and the bind that toggles it. Safe to call
// once per process; repeated calls are ignored.
void InstallGraphicsMenu(rex::ui::ImGuiDrawer* drawer);

// Removes the bind and closes the overlay. Called from OnShutdown so no global
// callback outlives the drawer it captures.
void UninstallGraphicsMenu();

}  // namespace aster::ui
