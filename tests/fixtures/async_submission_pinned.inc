/**
 ******************************************************************************
 * Xenia : Xbox 360 Emulator Research Project                                 *
 ******************************************************************************
 * Copyright 2022 Ben Vanik. All rights reserved.                             *
 * Released under the BSD license - see LICENSE in the root for more details. *
 ******************************************************************************
 *
 * @modified    Tom Clay, 2026 - Adapted for ReXGlue runtime
 */

void VulkanPipelineCache::EndSubmission() {
  if (shader_storage_file_flush_needed_ || pipeline_storage_file_flush_needed_) {
    {
      std::lock_guard<std::mutex> lock(storage_write_request_lock_);
      if (shader_storage_file_flush_needed_) {
        storage_write_flush_shaders_ = true;
      }
      if (pipeline_storage_file_flush_needed_) {
        storage_write_flush_pipelines_ = true;
      }
    }
    storage_write_request_cond_.notify_one();
    shader_storage_file_flush_needed_ = false;
    pipeline_storage_file_flush_needed_ = false;
  }

  if (!creation_threads_.empty()) {
    bool startup_loading = false;
    {
      std::lock_guard<std::mutex> lock(creation_request_lock_);
      startup_loading = startup_loading_;
    }
    if (startup_loading) {
      creation_request_cond_.notify_one();
    } else {
      // Help worker threads on the processor thread to reduce warm-up latency.
      CreateQueuedPipelinesOnProcessorThread();
      bool await_creation_completion_event;
      {
        std::lock_guard<std::mutex> lock(creation_request_lock_);
        // The queue is empty because of CreateQueuedPipelinesOnProcessorThread,
        // only check in-flight creation by worker threads.
        await_creation_completion_event = creation_threads_busy_ != 0;
        if (await_creation_completion_event) {
          creation_completion_event_->Reset();
          creation_completion_set_event_ = true;
        }
      }
      if (await_creation_completion_event) {
        creation_request_cond_.notify_one();
        rex::thread::Wait(creation_completion_event_.get(), false);
      }
    }
  }

  ProcessDeferredPipelineDestructions(false);
}

