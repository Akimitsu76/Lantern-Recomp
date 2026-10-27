"""Execute the SDK submission branch, including flush and blocking fallback.

Async workers must not be drained or awaited on the command processor thread.
The regression checks original behavior as well as the changed real SDK branch.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from native_port.native_build import cpu_sdk_identity
from native_port.spatial_sdk import PATCHES
ROOT=Path(__file__).resolve().parents[1]
NAME='0027-worker-only-async-submissions.patch'
FIXTURE=ROOT/'tests/fixtures/async_submission_pinned.inc'


def scheduling_change(name):
    chunks=re.split(r'^@@[^\n]*\n',(ROOT/'integrations/rexglue/patches'/name).read_text(),flags=re.M)[1:]
    chunk=chunks[0]
    old=''.join(s[1:] for s in chunk.splitlines(True) if s[:1] in (' ','-'))
    new=''.join(s[1:] for s in chunk.splitlines(True) if s[:1] in (' ','+'))
    return old,new

HARNESS=r'''
#include <cassert>
#include <mutex>
#include <vector>
#include <memory>
bool async_mode=false;
#define REXCVAR_GET(x) async_mode
struct Event {int resets=0;void Reset(){++resets;}};
int waits=0;
namespace rex::thread {void Wait(Event*,bool){++waits;}}
struct Condition {int notifications=0;void notify_one(){++notifications;}};
class VulkanPipelineCache {
 public:
 bool shader_storage_file_flush_needed_=true,pipeline_storage_file_flush_needed_=true;
 std::mutex storage_write_request_lock_,creation_request_lock_;
 bool storage_write_flush_shaders_=false,storage_write_flush_pipelines_=false;
 bool startup_loading_=false,creation_completion_set_event_=false;
 unsigned creation_threads_busy_=1;
 Condition storage_write_request_cond_,creation_request_cond_;
 std::vector<int>creation_threads_{1};
 std::unique_ptr<Event>creation_completion_event_=std::make_unique<Event>();
 int help=0,retired=0;
 void EndSubmission();
 void CreateQueuedPipelinesOnProcessorThread(){++help;}
 void ProcessDeferredPipelineDestructions(bool all){assert(!all);++retired;}
};
BODY
int main(){
 for(bool async: {false,true})for(bool startup:{false,true})
 for(bool threads:{false,true})for(unsigned busy:{0u,1u}){
  VulkanPipelineCache c;async_mode=async;c.startup_loading_=startup;
  if(!threads)c.creation_threads_.clear();c.creation_threads_busy_=busy;waits=0;
  c.EndSubmission();
  bool worker_only=threads&&(startup||(PATCHED&&async));
  bool drain=threads&&!worker_only;
  assert(c.help==int(drain));assert(waits==int(drain&&busy));
  assert(c.creation_request_cond_.notifications==int(worker_only||(drain&&busy)));
  assert(c.creation_completion_event_->resets==int(drain&&busy));
  assert(c.creation_completion_set_event_==bool(drain&&busy));
  assert(c.retired==1);
  // Cache writes/flushes keep happening in both modes, including no workers.
  assert(c.storage_write_flush_shaders_&&c.storage_write_flush_pipelines_);
  assert(!c.shader_storage_file_flush_needed_&&!c.pipeline_storage_file_flush_needed_);
  assert(c.storage_write_request_cond_.notifications==1);
  c.EndSubmission();assert(c.storage_write_request_cond_.notifications==1);
 }
}
'''

class AsyncSubmissionTests(unittest.TestCase):
    def test_actual_end_submission_keeps_async_on_workers_and_blocking_explicit(self):
        compiler=shutil.which('c++') or shutil.which('clang++')
        if not compiler:self.skipTest('C++ compiler required for SDK submission regression')
        original=FIXTURE.read_text();old,new=scheduling_change(NAME)
        self.assertEqual(original.count(old),1)
        changed=original.replace(old,new,1)
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            for patched,body in ((False,original),(True,changed)):
                path=base/f'test{int(patched)}.cpp';exe=base/f'test{int(patched)}'
                path.write_text(HARNESS.replace('BODY',body).replace('PATCHED',str(int(patched))))
                result=subprocess.run([compiler,'-std=c++17','-pthread',str(path),'-o',str(exe)],capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stderr)
                result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)

    def test_shared_and_linux_scheduling_are_identical_and_cpu_abi_is_preserved(self):
        self.assertEqual(scheduling_change(NAME),scheduling_change('0027-linux-worker-only-async-submissions.patch'))
        self.assertIn('integrations/rexglue/patches/'+NAME,PATCHES)
        previous={'patches':{'0004-embedded-spatial-sdk.patch':'ABI'}}
        changed={'patches':{**previous['patches'],NAME:'scheduling-only'}}
        self.assertEqual(cpu_sdk_identity(previous),cpu_sdk_identity(changed))

if __name__=='__main__':unittest.main()
