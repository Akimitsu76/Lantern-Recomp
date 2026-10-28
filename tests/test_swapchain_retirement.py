"""Exercise the patched retirement method against an outstanding present."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from native_port.native_build import cpu_sdk_identity
from native_port.spatial_sdk import PATCHES, normalized_patch

ROOT = Path(__file__).resolve().parents[1]
NAME = '0033-retire-present-queue.patch'


class SwapchainRetirementTests(unittest.TestCase):
    def test_render_completion_alone_cannot_retire_an_outstanding_present(self):
        compiler = shutil.which('clang++') or shutil.which('c++')
        if not compiler:
            self.skipTest('C++ compiler unavailable')
        patch = (ROOT / 'integrations/rexglue/patches' / NAME).read_text()
        self.assertEqual(set(normalized_patch(patch)), {'src/ui/vulkan/vulkan_presenter.cpp'})
        before = (ROOT / 'tests/fixtures/swapchain_retirement_pinned.inc').read_text()
        after = before
        for hunk in re.split(r'^@@[^\n]*\n', patch, flags=re.M)[1:]:
            rows = [r for r in hunk.splitlines() if r.startswith((' ', '+', '-'))]
            old = '\n'.join(r[1:] for r in rows if not r.startswith('+')) + '\n'
            new = '\n'.join(r[1:] for r in rows if not r.startswith('-')) + '\n'
            self.assertEqual(after.count(old), 1)
            after = after.replace(old, new, 1)
        stub = r'''
#include <cstdint>
#include <vector>
#define REXGPU_ERROR(...) (++errors)
#define assert_not_null(p) do{if(!(p))throw 9;}while(false)
using VkSwapchainKHR=void*;using VkDevice=int;using VkResult=int;
using PFN_vkQueueWaitIdle=int(*)(int);
constexpr auto VK_NULL_HANDLE=nullptr;constexpr int VK_SUCCESS=0;
int errors=0,step=0,waits=0,destroys=0;bool pending=true,locked=false;
struct VulkanDevice {
 struct Queue { struct Acquisition {
  Acquisition(){locked=true;}~Acquisition(){locked=false;}
  int queue()const{return 7;}
 };};
 struct Functions {
  static int vkQueueWaitIdle(int q) {
   if(q!=7||step!=1||!locked)throw 1;
   pending=false;step=2;++waits;return 0;
  }
  PFN_vkQueueWaitIdle vkGetDeviceProcAddr(int,const char*)const{return &vkQueueWaitIdle;}
  void vkDestroyFramebuffer(int,int,void*)const {if(pending)throw 2;++destroys;}
  void vkDestroyImageView(int,int,void*)const {if(pending)throw 3;++destroys;}
 };
 Queue::Acquisition AcquireQueue(uint32_t family,int index)const {
  if(family!=3||index!=0)throw 4;return {};
 }
 const Functions& functions()const {static Functions f;return f;}
 const VulkanDevice* vulkan_instance()const{return this;}
 int device()const{return 1;}
};
struct State {
 VulkanDevice* vulkan_device;
 struct Tracker {void AwaitAllSubmissionsCompletion(){step=1;}}submission_tracker;
 struct SwapchainFramebuffer {int framebuffer=1,image_view=2;};
 std::vector<SwapchainFramebuffer>swapchain_framebuffers{{}};
 std::vector<int>swapchain_images{1};
 struct {uint32_t width=1920,height=1080;}swapchain_extent;
 uint32_t present_queue_family=3;
 VkSwapchainKHR swapchain=reinterpret_cast<void*>(1);
};
struct VulkanPresenter {struct PaintContext:State {
 VkSwapchainKHR PrepareForSwapchainRetirement();
};};
struct Before {struct PaintContext:State {
 VkSwapchainKHR PrepareForSwapchainRetirement();
};};
'''
        main = r'''
int main(){
 VulkanDevice device;Before::PaintContext old;old.vulkan_device=&device;
 try{old.PrepareForSwapchainRetirement();return 1;}catch(int reason){if(reason!=2)return 2;}
 VulkanPresenter::PaintContext current;current.vulkan_device=&device;
 if(current.PrepareForSwapchainRetirement()!=reinterpret_cast<void*>(1))return 3;
 if(waits!=1||destroys!=2||locked||pending||current.swapchain||
    !current.swapchain_images.empty()||current.swapchain_extent.height)return 4;
 // An already-retired swapchain must not drain the queue again.
 current.PrepareForSwapchainRetirement();if(waits!=1||errors)return 5;
 return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='aster-retirement-') as directory:
            directory = Path(directory)
            source, binary = directory / 'check.cpp', directory / 'check.exe'
            source.write_text(stub + before.replace('VulkanPresenter::', 'Before::') + after + main)
            result = subprocess.run([compiler, '-std=c++17', str(source), '-o', str(binary)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('integrations/rexglue/patches/' + NAME, PATCHES)
        base = {'patches': {'0004-embedded-spatial-sdk.patch': 'abi'}}
        self.assertEqual(cpu_sdk_identity(base),
                         cpu_sdk_identity({'patches': {**base['patches'], NAME: 'implementation'}}))
