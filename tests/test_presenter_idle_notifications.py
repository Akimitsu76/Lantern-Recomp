"""Compile the actual new SDK method bodies and exercise idle/wakeup races.

No graphics API or game assets are needed. Extracting reviewed method bodies
from the patch prevents a Python behavioral model from passing independently
of the C++ implementation being proposed.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'integrations/rexglue/patches/0022-idle-notification-presentation.patch'


def new_patch_sections(patch):
    sections = {}
    current = None
    for line in patch.splitlines(keepends=True):
        if line.startswith('+++ b/'):
            current = line[6:].strip()
            sections[current] = []
        elif current and line[:1] in (' ', '+'):
            sections[current].append(line[1:])
    return {name: ''.join(lines) for name, lines in sections.items()}


def block(source, signature):
    start = source.index(signature)
    body = source.index('{', start)
    depth = 1
    end = body + 1
    while depth:
        if source[end] == '{':
            depth += 1
        elif source[end] == '}':
            depth -= 1
        end += 1
    return source[start:end]


HARNESS = r'''
#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <deque>
#include <functional>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>
struct WindowedAppContext {
  virtual ~WindowedAppContext() = default;
  std::mutex lock;
  std::deque<std::function<void()>> callbacks;
  bool running = true;
  std::function<void()> before_enqueue;
  bool CallInUIThreadDeferred(std::function<void()> fn) {
    if (before_enqueue) before_enqueue();
    std::lock_guard<std::mutex> guard(lock);
    if (!running) return false;
    callbacks.push_back(std::move(fn)); return true;
  }
  void Pump() {
    for (;;) {
      std::function<void()> fn;
      {std::lock_guard<std::mutex> guard(lock);
       if (callbacks.empty()) return;
       fn = std::move(callbacks.front()); callbacks.pop_front();}
      fn();
    }
  }
};
struct SDLWindowedAppContext final : WindowedAppContext {};
struct Window {
  SDLWindowedAppContext context;
  WindowedAppContext* alternate_context = nullptr;
  std::thread::id ui = std::this_thread::get_id();
  bool alive = true;
  bool pending_paint = false;
  size_t paint_requests = 0;
  WindowedAppContext& app_context() { return alternate_context ? *alternate_context : context; }
  void RequestPaint() {
    if (!alive || std::this_thread::get_id() != ui)
      throw std::runtime_error("paint accessed dead window or ran off UI thread");
    if (!pending_paint) {pending_paint = true; ++paint_requests;}
  }
};
class ImGuiDialog {
 public:
  virtual ~ImGuiDialog() = default;
  DEFAULT_REPAINT_QUERY
};
class ImGuiDrawer {
 public:
  struct PaintRequestState;
  Window* window_;
  std::shared_ptr<PaintRequestState> paint_request_state_;
  std::vector<ImGuiDialog*> dialogs_;
  explicit ImGuiDrawer(Window* window);
  ~ImGuiDrawer();
  std::function<void()> MakeThreadSafePaintRequest() const;
  bool NeedsContinuousPaint() const;
};
PAINT_STATE
ImGuiDrawer::~ImGuiDrawer() {INVALIDATE_REQUESTS}
ImGuiDrawer::ImGuiDrawer(Window* window)
    : window_(window), paint_request_state_(std::make_shared<PaintRequestState>(window)) {}
MAKE_PAINT_REQUEST
DRAWER_REPAINT_QUERY
namespace rex::system { struct AchievementEvent { int value = 0; }; }
class AchievementToastDialog : public ImGuiDialog {
 public:
  const std::function<void()> request_paint_;
  mutable std::mutex mutex_;
  struct PendingToast {
    rex::system::AchievementEvent event;
    std::chrono::steady_clock::time_point arrived;
  };
  std::deque<PendingToast> queue_;
  explicit AchievementToastDialog(ImGuiDrawer* drawer)
      : request_paint_(drawer->MakeThreadSafePaintRequest()) {}
  void Push(const rex::system::AchievementEvent& event);
  bool NeedsContinuousPaint() const override;
  void Expire() {std::lock_guard<std::mutex> guard(mutex_); queue_.clear();}
};
TOAST_PUSH
TOAST_REPAINT_QUERY
void require(bool condition, const char* message) {
  if (!condition) throw std::runtime_error(message);
}
void PaintOnce(Window& window, ImGuiDrawer& drawer) {
  require(window.pending_paint, "no paint was scheduled");
  window.pending_paint = false;
  // The SDK invokes this query after rendering/removing expired toasts.
  if (drawer.NeedsContinuousPaint()) window.RequestPaint();
}
int main() {
  Window window;
  ImGuiDrawer drawer(&window);
  AchievementToastDialog toast(&drawer);
  drawer.dialogs_.push_back(&toast);
  window.RequestPaint();
  PaintOnce(window, drawer);
  require(!window.pending_paint, "empty toast started an idle repaint loop");
  require(window.paint_requests == 1, "idle painting did not settle");

  // A guest worker wakes an idle title, without any new game frame/input event.
  std::thread push([&]{for (int i=0; i<5; ++i) toast.Push({i});});
  push.join();
  require(!window.pending_paint, "guest worker touched the window directly");
  window.context.Pump();
  require(window.pending_paint, "Push did not wake an idle presenter");
  require(window.paint_requests == 2, "queued wakeups were not coalesced by the window");
  require(toast.queue_.size() == 5, "multiple queued achievements were lost");
  for (int i=0; i<1000; ++i) PaintOnce(window, drawer);
  require(window.pending_paint, "active toast animation was throttled or stopped");
  toast.Expire();
  PaintOnce(window, drawer);
  require(!window.pending_paint, "expired toast kept painting");

  // New Push immediately after expiry still carries a separate wakeup.
  toast.Push({9});
  window.context.Pump();
  require(window.pending_paint && drawer.NeedsContinuousPaint(), "expiry lost a new event");
  toast.Expire();
  PaintOnce(window, drawer);
  require(!window.pending_paint, "second idle transition did not settle");

  // Default dialogs/menus keep their original continuous animation behavior.
  ImGuiDialog animated_menu;
  drawer.dialogs_.push_back(&animated_menu);
  window.RequestPaint();
  for (int i=0; i<1000; ++i) PaintOnce(window, drawer);
  require(window.pending_paint, "animated menu unexpectedly stopped");
  drawer.dialogs_.pop_back();
  PaintOnce(window, drawer);
  require(!window.pending_paint, "closing the active menu did not settle");

  // Deliveries queued before teardown and retained callbacks after it are safe.
  Window dying_window;
  auto dying_drawer = std::make_unique<ImGuiDrawer>(&dying_window);
  auto request = dying_drawer->MakeThreadSafePaintRequest();
  auto held_state = dying_drawer->paint_request_state_; // Simulate an in-flight caller.
  request();
  dying_drawer.reset();
  dying_window.alive = false;
  dying_window.context.Pump();
  request();
  dying_window.context.Pump();
  require(!dying_window.pending_paint, "stale request accessed a destroyed drawer/window");
  held_state.reset();
  request();
  dying_window.context.Pump();

  // Teardown synchronizes a producer already inside the enqueue call. The
  // real opted-in SDL enqueue does not await UI processing; this artificial
  // latch proves invalidation cannot return before that producer leaves it.
  Window racing_window;
  auto racing_drawer = std::make_unique<ImGuiDrawer>(&racing_window);
  auto racing_request = racing_drawer->MakeThreadSafePaintRequest();
  auto retained_state = racing_drawer->paint_request_state_;
  std::mutex enqueue_mutex;
  std::condition_variable enqueue_cv;
  bool release_enqueue = false;
  std::atomic<bool> enqueue_entered{false}, invalidated{false};
  racing_window.context.before_enqueue = [&]{
    std::unique_lock<std::mutex> lock(enqueue_mutex);
    enqueue_entered.store(true);
    enqueue_cv.wait(lock, [&]{return release_enqueue;});
  };
  std::thread producer([&]{racing_request();});
  for (int i=0; i<1000 && !enqueue_entered.load(); ++i)
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  bool producer_inside = enqueue_entered.load();
  std::thread invalidate([&]{racing_drawer.reset(); invalidated.store(true);});
  std::this_thread::sleep_for(std::chrono::milliseconds(20));
  bool waited_for_enqueue = !invalidated.load();
  {std::lock_guard<std::mutex> lock(enqueue_mutex); release_enqueue = true;}
  enqueue_cv.notify_all();
  producer.join(); invalidate.join();
  racing_window.alive = false;
  racing_window.context.before_enqueue = []{throw std::runtime_error("post-invalidation context access");};
  racing_request();
  racing_window.context.Pump();
  require(producer_inside && waited_for_enqueue, "teardown escaped an in-flight enqueue");
  require(!racing_window.pending_paint, "racing callback painted after teardown");

  // A generic context can have a blocking wakeup pipe: preserve its old
  // continuous behavior rather than introducing an unsafe gated enqueue.
  Window generic_window;
  WindowedAppContext generic_context;
  generic_window.alternate_context = &generic_context;
  ImGuiDrawer generic_drawer(&generic_window);
  require(!generic_drawer.MakeThreadSafePaintRequest(), "generic context unexpectedly opted in");
  AchievementToastDialog generic_toast(&generic_drawer);
  require(generic_toast.NeedsContinuousPaint(), "generic legacy redraw path was disabled");
  generic_toast.Push({7});
  require(generic_toast.queue_.size() == 1, "generic fallback lost its notification");

  // An app context that stopped accepting callbacks drops wakeups cleanly.
  Window stopped_window;
  ImGuiDrawer stopped_drawer(&stopped_window);
  stopped_window.context.running = false;
  stopped_drawer.MakeThreadSafePaintRequest()();
  stopped_window.context.Pump();
  require(!stopped_window.pending_paint, "shutdown context still accepted paints");
  return 0;
}
'''


class PresenterIdleNotificationTests(unittest.TestCase):
    def test_idle_toasts_stop_repainting_and_threadsafe_push_wakes_them(self):
        compiler = shutil.which('c++') or shutil.which('g++') or shutil.which('clang++')
        if not compiler:
            self.skipTest('A C++ compiler is required to run the actual proposed SDK methods')
        files = new_patch_sections(PATCH.read_text(encoding='utf8'))
        drawer = files['src/ui/imgui_drawer.cpp']
        toast = files['src/ui/overlay/achievement_toast.cpp']
        dialog = files['include/rex/ui/imgui_dialog.h']
        # The only change in Draw's scheduling condition must use the semantic
        # query. Actual query, Push, dispatcher and invalidation run below.
        self.assertIn('  if (NeedsContinuousPaint()) {', drawer)
        destructor = drawer.split('ImGuiDrawer::~ImGuiDrawer() {', 1)[1].split('  SetPresenter(nullptr);', 1)[0]
        substitutions = {
            'DEFAULT_REPAINT_QUERY': block(dialog, 'virtual bool NeedsContinuousPaint() const'),
            'PAINT_STATE': block(drawer, 'struct ImGuiDrawer::PaintRequestState') + ';',
            'INVALIDATE_REQUESTS': destructor,
            'MAKE_PAINT_REQUEST': block(drawer, 'std::function<void()> ImGuiDrawer::MakeThreadSafePaintRequest() const'),
            'DRAWER_REPAINT_QUERY': block(drawer, 'bool ImGuiDrawer::NeedsContinuousPaint() const'),
            'TOAST_PUSH': block(toast, 'void AchievementToastDialog::Push('),
            'TOAST_REPAINT_QUERY': block(toast, 'bool AchievementToastDialog::NeedsContinuousPaint() const'),
        }
        cpp = HARNESS
        for key, value in substitutions.items():
            cpp = cpp.replace(key, value)
        with tempfile.TemporaryDirectory(prefix='aster-idle-paint-test-') as temporary:
            temporary = Path(temporary)
            source, binary = temporary / 'test.cpp', temporary / 'test'
            source.write_text(cpp, encoding='utf8')
            built = subprocess.run([compiler, '-std=c++17', '-pthread', str(source), '-o', str(binary)],
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
