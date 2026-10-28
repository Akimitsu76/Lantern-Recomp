// Pinned ReXGlue f5337cdc; src/ui/window.cpp resize handler before patch0032.
// Copyright2021 Ben Vanik, BSD license; see docs/THIRD_PARTY_NOTICES.md.
bool Window::OnActualSizeUpdate(uint32_t new_physical_width, uint32_t new_physical_height,
                                WindowDestructionReceiver& destruction_receiver) {
  if (actual_physical_width_ == new_physical_width &&
      actual_physical_height_ == new_physical_height) {
    return false;
  }
  actual_physical_width_ = new_physical_width;
  actual_physical_height_ = new_physical_height;
  // The listeners may reference the presenter, update the presenter first.
  if (presenter_surface_) {
    presenter_->OnSurfaceResizeFromUIThread();
  }
  UISetupEvent e(this);
  SendEventToListeners([&e](auto listener) { listener->OnResize(e); }, destruction_receiver);
  if (destruction_receiver.IsWindowDestroyed()) {
    return true;
  }
  return true;
}
