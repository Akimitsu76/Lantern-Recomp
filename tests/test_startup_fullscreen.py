"""Execute the SDK focus branch, with window-owned once-only retry state."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from native_port.native_build import cpu_sdk_identity
from native_port.spatial_sdk import PATCHES, normalized_patch

ROOT = Path(__file__).resolve().parents[1]
NAME = '0028-startup-fullscreen-focus-retry.patch'
FIXTURE = ROOT / 'tests/fixtures/startup_fullscreen_focus_pinned.inc'
HARNESS = r'''
#include <cassert>
#include <cstdint>
using SDL_PropertiesID = uint32_t;
constexpr unsigned SDL_EVENT_WINDOW_FOCUS_GAINED=1, SDL_WINDOW_FULLSCREEN=1;
struct State { bool wanted, actual, retried, valid, success, destroyed; int calls=0, focus=0, warns=0; } state;
SDL_PropertiesID SDL_GetWindowProperties(void*) { return state.valid ? 1 : 0; }
bool SDL_GetBooleanProperty(SDL_PropertiesID,const char*,bool) { return state.retried; }
bool SDL_SetBooleanProperty(SDL_PropertiesID,const char*,bool v) { state.retried=v; return true; }
unsigned SDL_GetWindowFlags(void*) { return state.actual ? SDL_WINDOW_FULLSCREEN : 0; }
bool SDL_SetWindowFullscreen(void*,bool v) { assert(v); ++state.calls; state.actual=state.success; return state.success; }
const char* SDL_GetError() { return "test rejection"; }
#define REXLOG_WARN(...) (++state.warns)
struct Receiver { bool IsWindowDestroyed() { return state.destroyed; } };
struct Window {
 void* sdl_window_=this;
 bool IsFullscreen() { return state.wanted; }
 void OnFocusUpdate(bool focused,Receiver&) { assert(focused); ++state.focus; }
 void Focus() {
  Receiver destruction_receiver;
  switch(SDL_EVENT_WINDOW_FOCUS_GAINED) {
   BODY
  }
 }
};
int main() {
 for(bool wanted:{false,true}) for(bool actual:{false,true})
 for(bool retried:{false,true}) for(bool valid:{false,true})
 for(bool success:{false,true}) for(bool destroyed:{false,true}) {
  state={wanted,actual,retried,valid,success,destroyed}; Window w;
  bool expected=valid&&!retried&&wanted&&!actual;
  w.Focus(); assert(state.calls==int(expected));
  assert(state.focus==int(!(expected&&destroyed)));
  assert(state.warns==int(expected&&!success));
  assert(state.wanted==wanted); // Window setting is never rewritten.
  w.Focus(); assert(state.calls==int(expected)); // No repeat after failure/focus cycling.
 }
}
'''


class StartupFullscreenTests(unittest.TestCase):
    def test_actual_focus_branch_retries_once_only_when_requested_and_missing(self):
        compiler = shutil.which('c++') or shutil.which('clang++')
        if not compiler:
            self.skipTest('C++ compiler required for SDK window regression')
        changes = normalized_patch((ROOT / 'integrations/rexglue/patches' / NAME).read_text())
        lines = changes['src/ui/window_sdl.cpp'][2:]
        before = '\n'.join(line[1:] for line in lines if line.startswith((' ', '-')))
        after = '\n'.join(line[1:] for line in lines if line.startswith((' ', '+')))
        original = FIXTURE.read_text()
        self.assertIn('case SDL_EVENT_WINDOW_FOCUS_GAINED:', original)
        # The hunk includes adjacent cases; verify the pinned focus branch then
        # compile only its actual patched branch in the isolated event harness.
        self.assertIn(original[original.index('    case '):].rstrip(), before)
        start = after.index('    case SDL_EVENT_WINDOW_FOCUS_GAINED:')
        end = after.index('    case SDL_EVENT_WINDOW_FOCUS_LOST:', start)
        branch = after[start:end]
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / 'focus.cpp'
            executable = base / 'focus'
            source.write_text('#include <initializer_list>\n' + HARNESS.replace('BODY', branch))
            result = subprocess.run([compiler, '-std=c++17', str(source), '-o', str(executable)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_recipe_changes_without_public_window_layout_change(self):
        self.assertIn('integrations/rexglue/patches/' + NAME, PATCHES)
        before = {'patches': {'0004-embedded-spatial-sdk.patch': 'public-abi'}}
        after = {'patches': {**before['patches'], NAME: 'window-owned-property'}}
        self.assertEqual(cpu_sdk_identity(before), cpu_sdk_identity(after))
        changes = normalized_patch((ROOT / 'integrations/rexglue/patches' / NAME).read_text())
        self.assertEqual(set(changes), {'src/ui/window_sdl.cpp'})


if __name__ == '__main__':
    unittest.main()
