"""Exercise the real SDK presenter branch with a simulated Vulkan lifetime.

Repeated frames must not await/destroy/recreate a compatible output pipeline.
Failures must retry, and format transitions must retain their GPU wait.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from native_port.native_cache import apply_patch_exact
from native_port.native_build import cpu_sdk_identity
from native_port.spatial_sdk import PATCHES

ROOT=Path(__file__).resolve().parents[1]
NAME='0026-presenter-pipeline-format-cache.patch'
FIXTURE=ROOT/'tests/fixtures/presenter_format_cache_pinned.inc'
HARNESS=r'''
#include <cassert>
#include <cstddef>
#define VK_NULL_HANDLE 0
#define assert_true assert
int creates=0,destroys=0,waits=0;bool fail=false;
struct Tracker {void AwaitSubmissionCompletion(int n){assert(n==11);++waits;}};
struct State {Tracker submission_tracker;int swapchain_render_pass_format=44;
 int swapchain_render_pass=1,guest_output_image_paint_last_submission=11;} paint_context_;
struct Pipeline {int swapchain_pipeline=0,swapchain_format=0;} effects[2];
struct {int vkDestroyPipeline=0;} dfn;
int device=1,guest_output_paint_fs_[2]={1,1};
bool CanGuestOutputPaintEffectBeFinal(int){return true;}
int CreateGuestOutputPaintPipeline(int,int){++creates;return fail?0:creates;}
namespace util {void DestroyAndNullHandle(int,int,int& p){assert(p);++destroys;p=0;}}
int draw(int swapchain_effect=0){
 auto& swapchain_effect_pipeline=effects[swapchain_effect];
 struct{int effect_count=1;}guest_output_flow;
 if(guest_output_flow.effect_count){
 BLOCK
 return guest_output_flow.effect_count;
}
int main(){
 for(int i=0;i<8;++i)assert(draw()==1);
 assert(creates==(FIXED?1:8));assert(waits==(FIXED?0:7));
 if(!FIXED)return 0;
 assert(draw(1)==1);assert(creates==2);assert(waits==0);
 // A resize with the same render-pass format keeps the compatible pipeline.
 paint_context_.swapchain_render_pass=2;assert(draw()==1);assert(creates==2);
 // A format change must still await the previous submission before destroying.
 paint_context_.swapchain_render_pass_format=50;
 assert(draw()==1);assert(creates==3&&waits==1&&destroys==1);
 assert(effects[0].swapchain_format==50);
 // Failure must not mark a pipeline as ready; a later frame retries.
 paint_context_.swapchain_render_pass_format=64;fail=true;
 assert(draw()==0);assert(creates==4&&waits==2&&destroys==2);
 assert(effects[0].swapchain_pipeline==0&&effects[0].swapchain_format==50);
 fail=false;assert(draw()==1);assert(creates==5&&waits==2);
 for(int i=0;i<8;++i)assert(draw()==1);
 assert(creates==5&&effects[0].swapchain_format==64);
}
'''

class PresenterFormatCacheTests(unittest.TestCase):
    def test_actual_presenter_branch_reuses_retries_and_retires_pipelines(self):
        compiler=shutil.which('c++') or shutil.which('clang++')
        if not compiler:self.skipTest('C++ compiler required for actual presenter branch regression')
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);source=base/'src/ui/vulkan/vulkan_presenter.cpp';source.parent.mkdir(parents=True)
            original=FIXTURE.read_text();source.write_text(original)
            patch=(ROOT/'integrations/rexglue/patches'/NAME).read_text()
            # Fixture contains the full branch, without 1,839 unrelated lines.
            first='                swapchain_effect, paint_context_.swapchain_render_pass);\n'
            line=original[:original.index(first)].count('\n')+1
            patch=patch.replace('@@ -1840,6 +1840,9 @@',f'@@ -{line},6 +{line},9 @@')
            apply_patch_exact(base,patch)
            for fixed,body in ((False,original),(True,source.read_text())):
                cpp=base/f'test{int(fixed)}.cpp';exe=base/f'test{int(fixed)}'
                cpp.write_text(HARNESS.replace('BLOCK',body).replace('FIXED',str(int(fixed))))
                result=subprocess.run([compiler,'-std=c++17',str(cpp),'-o',str(exe)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                result=subprocess.run([str(exe)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)

    def test_runtime_recipe_includes_fix_without_invalidating_cpu_objects(self):
        self.assertIn('integrations/rexglue/patches/'+NAME,PATCHES)
        original={'patches':{'0004-embedded-spatial-sdk.patch':'ABI','0025-known-shader-preload-selection.patch':'GPU'}}
        changed={'patches':{**original['patches'],NAME:'presenter-implementation'}}
        self.assertEqual(cpu_sdk_identity(original),cpu_sdk_identity(changed))
        future={'patches':{**changed['patches'],'0027-unknown.patch':'unknown'}}
        self.assertNotEqual(cpu_sdk_identity(original),cpu_sdk_identity(future))

if __name__=='__main__':unittest.main()
