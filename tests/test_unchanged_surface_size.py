"""Reproduce a fullscreen surface connected before the final native window size."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from native_port.spatial_sdk import PATCHES, normalized_patch
from native_port.native_build import cpu_sdk_identity

ROOT = Path(__file__).resolve().parents[1]
NAME = '0032-refresh-unchanged-surface-size.patch'


class SurfaceResizeTests(unittest.TestCase):
    def test_real_window_handler_refreshes_stale_surface_without_duplicate_resize(self):
        compiler = shutil.which('clang++') or shutil.which('c++')
        if not compiler: self.skipTest('C++ compiler unavailable')
        patch = (ROOT / 'integrations/rexglue/patches' / NAME).read_text()
        self.assertEqual(set(normalized_patch(patch)), {'src/ui/window.cpp'})
        baseline = (ROOT / 'tests/fixtures/unchanged_surface_size_pinned.inc').read_text()
        candidate = baseline
        for hunk in re.split(r'^@@[^\n]*\n', patch, flags=re.M)[1:]:
            rows = [r for r in hunk.splitlines() if r.startswith((' ', '+', '-'))]
            old = '\n'.join(r[1:] for r in rows if not r.startswith('+')) + '\n'
            new = '\n'.join(r[1:] for r in rows if not r.startswith('-')) + '\n'
            self.assertEqual(candidate.count(old), 1)
            candidate = candidate.replace(old, new, 1)
        stub = r'''
#include <cstdint>
struct WindowDestructionReceiver {
 bool destroyed=false;
 bool IsWindowDestroyed() const { return destroyed; }
};
struct UISetupEvent { template<class T> UISetupEvent(T*) {} };
struct Surface { uint32_t width=1920,height=1080; };
struct Presenter {
 Surface* surface;
 uint32_t connected_width=1920,connected_height=1030,calls=0;
 WindowDestructionReceiver* destroy_on_refresh=nullptr;
 void OnSurfaceResizeFromUIThread() {
  ++calls;connected_width=surface->width;connected_height=surface->height;
  if(destroy_on_refresh)destroy_on_refresh->destroyed=true;
 }
};
struct Common {
 uint32_t actual_physical_width_=1920,actual_physical_height_=1080,resize_events=0;
 bool presenter_surface_=true;
 Presenter* presenter_=nullptr;
 struct Listener { Common* self;void OnResize(UISetupEvent&){++self->resize_events;} };
 template<class F> void SendEventToListeners(F f,WindowDestructionReceiver&){Listener l{this};f(&l);}
};
struct Window:Common { bool OnActualSizeUpdate(uint32_t,uint32_t,WindowDestructionReceiver&); };
struct WindowBefore:Common { bool OnActualSizeUpdate(uint32_t,uint32_t,WindowDestructionReceiver&); };
'''
        main = r'''
int main() {
 Surface surface;Presenter presenter{&surface};WindowDestructionReceiver life;
 WindowBefore before;before.presenter_=&presenter;
 if(before.OnActualSizeUpdate(1920,1080,life)||presenter.calls||presenter.connected_height!=1030)return 1;
 Window current;current.presenter_=&presenter;
 if(current.OnActualSizeUpdate(1920,1080,life)||presenter.calls!=1||presenter.connected_height!=1080||current.resize_events)return 2;
 surface.width=1280;surface.height=720;
 if(!current.OnActualSizeUpdate(1280,720,life)||presenter.calls!=2||presenter.connected_height!=720||current.resize_events!=1)return 3;
 current.presenter_surface_=false;
 if(current.OnActualSizeUpdate(1280,720,life)||presenter.calls!=2||current.resize_events!=1)return 4;
 current.presenter_surface_=true;presenter.destroy_on_refresh=&life;
 if(!current.OnActualSizeUpdate(1280,720,life)||!life.destroyed||current.resize_events!=1)return 5;
 return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='aster-surface-') as temp:
            temp = Path(temp); source = temp / 'check.cpp'; binary = temp / 'check.exe'
            source.write_text(stub + baseline.replace('Window::', 'WindowBefore::') + candidate + main)
            result = subprocess.run([compiler, '-std=c++17', str(source), '-o', str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('integrations/rexglue/patches/' + NAME, PATCHES)
        base = {'patches': {'0004-embedded-spatial-sdk.patch': 'abi'}}
        self.assertEqual(cpu_sdk_identity(base), cpu_sdk_identity({'patches': {**base['patches'], NAME: 'implementation-only'}}))
