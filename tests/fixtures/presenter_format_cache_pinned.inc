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

          if (swapchain_effect_pipeline.swapchain_pipeline != VK_NULL_HANDLE &&
              swapchain_effect_pipeline.swapchain_format !=
                  paint_context_.swapchain_render_pass_format) {
            paint_context_.submission_tracker.AwaitSubmissionCompletion(
                paint_context_.guest_output_image_paint_last_submission);
            util::DestroyAndNullHandle(dfn.vkDestroyPipeline, device,
                                       swapchain_effect_pipeline.swapchain_pipeline);
          }
          if (swapchain_effect_pipeline.swapchain_pipeline == VK_NULL_HANDLE) {
            assert_true(CanGuestOutputPaintEffectBeFinal(swapchain_effect));
            assert_true(guest_output_paint_fs_[size_t(swapchain_effect)] != VK_NULL_HANDLE);
            swapchain_effect_pipeline.swapchain_pipeline = CreateGuestOutputPaintPipeline(
                swapchain_effect, paint_context_.swapchain_render_pass);
            if (swapchain_effect_pipeline.swapchain_pipeline == VK_NULL_HANDLE) {
              guest_output_flow.effect_count = 0;
            }
          }
        }
