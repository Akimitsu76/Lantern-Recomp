"""Exercise the SDK's real prewarm completion block with a held worker.

The checked-in excerpts are pinned public SDK source. Both patch hunks are
applied to those exact excerpts, then original and patched C++ blocks run in the
same harness. This detects the old empty-queue/busy-worker early return without
requiring a GPU, game assets, or Windows SDK.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/d3d12_prewarm_pinned.inc'
PATCH = ROOT / 'integrations/rexglue/patches/0021-d3d12-blocking-shader-prewarm.patch'


def apply_excerpt_hunks(source, patch):
    """Require every complete old hunk exactly once; don't approximate the fix."""
    hunks = re.split(r'^@@[^\n]*\n', patch, flags=re.MULTILINE)[1:]
    if len(hunks) != 2:
        raise AssertionError('Expected the reviewed allocation and completion hunks')
    for hunk in hunks:
        lines = hunk.splitlines(keepends=True)
        old = ''.join(line[1:] for line in lines if line[:1] in (' ', '-'))
        new = ''.join(line[1:] for line in lines if line[:1] in (' ', '+'))
        if source.count(old) != 1:
            raise AssertionError('Pinned SDK excerpt no longer matches the complete patch hunk')
        source = source.replace(old, new, 1)
    return source


def excerpt(text, name):
    return text.split('// BEGIN ' + name + '\n', 1)[1].split('// END ' + name, 1)[0]


HARNESS = r'''
#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <future>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>
using namespace std::chrono_literals;
#define REXGPU_INFO(...) do {} while(0)
#define assert_not_null(value) do { if (!(value)) throw std::runtime_error("null"); } while(0)
namespace rex::thread {
struct Thread {
  template<class F> static std::unique_ptr<Thread> Create(int, F) {
    return std::make_unique<Thread>();
  }
  void set_name(const char*) {}
};
struct Event {
  std::mutex lock;
  std::condition_variable cv;
  bool signaled = false;
  void Reset() { std::lock_guard<std::mutex> guard(lock); signaled = false; }
  void Set() { {std::lock_guard<std::mutex> guard(lock); signaled = true;} cv.notify_all(); }
};
void Wait(Thread*, bool) {}  // Temporary-thread joins are counted via vector removal.
void Wait(Event* event, bool) {
  std::unique_lock<std::mutex> guard(event->lock);
  if (!event->cv.wait_for(guard, 2s, [&]{return event->signaled;}))
    throw std::runtime_error("prewarm completion event timed out");
}
}
struct Cache {
  std::vector<std::unique_ptr<rex::thread::Thread>> creation_threads_;
  std::mutex creation_request_lock_;
  std::condition_variable creation_request_cond_;
  size_t creation_threads_shutdown_from_ = SIZE_MAX;
  size_t creation_threads_busy_ = 0;
  std::unique_ptr<rex::thread::Event> creation_completion_event_ =
      std::make_unique<rex::thread::Event>();
  bool creation_completion_set_event_ = false;
  std::atomic<bool> queue_drained = false;
  explicit Cache(size_t original) {
    while (creation_threads_.size() < original)
      creation_threads_.push_back(std::make_unique<rex::thread::Thread>());
  }
  void CreationThread(size_t) {}
  void CreateQueuedPipelinesOnProcessorThread() { queue_drained.store(true); }
  size_t Allocate(size_t count, size_t logical_processor_count) {
    std::vector<int> pipeline_stored_descriptions(count);
    ALLOCATION_BLOCK
    return creation_threads_.size();
  }
  void Complete(bool blocking, size_t creation_thread_original_count) {
    COMPLETION_BLOCK
  }
  // A real controlled worker publishes completion with the SDK's lock/event
  // protocol. The task queue is empty while this worker owns the last job.
  void WorkerComplete() {
    std::lock_guard<std::mutex> guard(creation_request_lock_);
    --creation_threads_busy_;
    if (creation_completion_set_event_ && creation_threads_busy_ == 0) {
      creation_completion_set_event_ = false;
      creation_completion_event_->Set();
    }
  }
};
void require(bool condition, const char* message) {
  if (!condition) throw std::runtime_error(message);
}
void busy_case(bool patched, bool blocking, bool extras, bool failed_creation) {
  Cache cache(extras ? 3 : 1);
  cache.creation_threads_busy_ = 1;
  std::mutex worker_lock;
  std::condition_variable worker_cv;
  bool release_worker = false;
  bool failed = false;
  std::thread worker([&]{
    {std::unique_lock<std::mutex> guard(worker_lock);
     worker_cv.wait(guard, [&]{return release_worker;});}
    failed = failed_creation;  // Driver failure still completes the worker job.
    cache.WorkerComplete();
  });
  auto initialization = std::async(std::launch::async, [&]{cache.Complete(blocking, 1);});
  for (int i = 0; i < 1000 && !cache.queue_drained.load(); ++i) std::this_thread::sleep_for(1ms);
  bool drained = cache.queue_drained.load();
  bool returned_before_completion = initialization.wait_for(40ms) == std::future_status::ready;
  {std::lock_guard<std::mutex> guard(worker_lock); release_worker = true;}
  worker_cv.notify_all();
  worker.join();
  initialization.get();
  require(drained, "completion code never drained its queue");
  // Original incorrectly skips the wait unless there were temporary workers.
  bool should_wait = blocking && (patched || extras);
  require(returned_before_completion != should_wait, "blocking prewarm returned while worker was busy");
  require(cache.creation_threads_busy_ == 0, "worker not accounted for");
  require(cache.creation_threads_.size() == 1, "temporary workers were not removed");
  require(failed == failed_creation, "worker result lost");
}
int main() {
  bool patched = PATCHED_VARIANT;
  {Cache c(1); require(c.Allocate(6, 8) == (patched ? 5 : 1), "worker target count not used");}
  {Cache c(0); require(c.Allocate(1, 1) == 0, "single-core main-thread path changed");}
  {Cache c(1); require(c.Allocate(1, 8) == 1, "existing worker count reduced");}
  {Cache c(0); c.Complete(true, 0); require(!c.queue_drained.load(), "zero-worker path entered");}
  {Cache c(1); c.Complete(true, 1); require(c.queue_drained.load(), "idle queue not drained");}
  busy_case(patched, true, false, false);
  busy_case(patched, true, false, true);
  busy_case(patched, false, false, false);
  busy_case(patched, true, true, false);
  return 0;
}
'''


class D3D12ShaderPrewarmTests(unittest.TestCase):
    def test_blocking_prewarm_waits_for_busy_worker_even_with_empty_queue(self):
        compiler = shutil.which('c++') or shutil.which('g++') or shutil.which('clang++')
        if not compiler:
            self.skipTest('A C++ compiler is needed for the actual SDK-block concurrency regression')
        original = FIXTURE.read_text(encoding='utf8')
        patched = apply_excerpt_hunks(original, PATCH.read_text(encoding='utf8'))
        with tempfile.TemporaryDirectory(prefix='aster-prewarm-test-') as temporary:
            temporary = Path(temporary)
            for label, source in [('original', original), ('patched', patched)]:
                with self.subTest(variant=label):
                    cpp = HARNESS.replace('ALLOCATION_BLOCK', excerpt(source, 'ALLOCATION'))
                    cpp = cpp.replace('COMPLETION_BLOCK', excerpt(source, 'COMPLETION'))
                    cpp = cpp.replace('PATCHED_VARIANT', 'true' if label == 'patched' else 'false')
                    cpp_path, binary = temporary / (label + '.cpp'), temporary / label
                    cpp_path.write_text(cpp, encoding='utf8')
                    built = subprocess.run([compiler, '-std=c++17', '-pthread', str(cpp_path), '-o', str(binary)],
                                           capture_output=True, text=True, timeout=30)
                    self.assertEqual(built.returncode, 0, built.stderr)
                    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
