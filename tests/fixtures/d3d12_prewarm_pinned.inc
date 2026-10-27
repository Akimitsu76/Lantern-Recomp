// ReXGlue SDK f5337cdc947ff6d4c4196737e2c807a48f2a1fc2.
// Source: src/graphics/d3d12/pipeline_cache.cpp, initialization worker allocation
// and completion blocks. Copyright 2020 Ben Vanik; BSD license, see
// tests/fixtures/REXGLUE-LICENSE.txt and upstream LICENSE.
// No game code or assets. These are exact source excerpts, not a model of the fix.
// BEGIN ALLOCATION
    // Launch additional creation threads to use all cores to create
    // pipelines faster. Will also be using the main thread, so minus 1.
    size_t creation_thread_original_count = creation_threads_.size();
    size_t creation_thread_needed_count =
        std::max(std::min(pipeline_stored_descriptions.size(), logical_processor_count) - size_t(1),
                 creation_thread_original_count);
    while (creation_threads_.size() < creation_thread_original_count) {
      size_t creation_thread_index = creation_threads_.size();
      std::unique_ptr<rex::thread::Thread> creation_thread = rex::thread::Thread::Create(
          {}, [this, creation_thread_index]() { CreationThread(creation_thread_index); });
      assert_not_null(creation_thread);
      creation_thread->set_name("D3D12 Pipelines");
      creation_threads_.push_back(std::move(creation_thread));
    }

// END ALLOCATION
// BEGIN COMPLETION
    if (!creation_threads_.empty()) {
      CreateQueuedPipelinesOnProcessorThread();
      if (creation_threads_.size() > creation_thread_original_count) {
        {
          std::lock_guard<std::mutex> lock(creation_request_lock_);
          creation_threads_shutdown_from_ = creation_thread_original_count;
          // Assuming the queue is empty because of
          // CreateQueuedPipelinesOnProcessorThread.
        }
        creation_request_cond_.notify_all();
        while (creation_threads_.size() > creation_thread_original_count) {
          rex::thread::Wait(creation_threads_.back().get(), false);
          creation_threads_.pop_back();
        }
        bool await_creation_completion_event;
        {
          // Cleanup so additional threads can be created later again.
          std::lock_guard<std::mutex> lock(creation_request_lock_);
          creation_threads_shutdown_from_ = SIZE_MAX;
          // If the invocation is blocking, all the shader storage
          // initialization is expected to be done before proceeding, to avoid
          // latency in the command processor after the invocation.
          await_creation_completion_event = blocking && creation_threads_busy_ != 0;
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

    REXGPU_INFO(
        "Created {} graphics pipelines (not including reading the "
        "descriptions) from the storage in {} milliseconds",
        pipelines_created,
        (rex::chrono::Clock::QueryHostTickCount() - pipeline_creation_start_) * 1000 /
            rex::chrono::Clock::QueryHostTickFrequency());
// END COMPLETION
