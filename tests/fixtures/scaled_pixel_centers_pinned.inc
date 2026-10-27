// ReXGlue SDK f5337cdc947ff6d4c4196737e2c807a48f2a1fc2.
// Exact source contexts from src/graphics/pipeline/shader/{spirv,dxbc}_translator.cpp.
// Copyright 2020 Ben Vanik and contributors; BSD, see REXGLUE-LICENSE.txt.
// No game code or assets.
// BEGIN HUNK0
        builder_->createLoad(
            builder_->createAccessChain(spv::StorageClassInput, input_fragment_coordinates_,
                                        id_vector_temp_),
            spv::NoPrecision));
    if (draw_resolution_scale_x_ > 1) {
      param_gen_x = builder_->createNoContractionBinOp(
          spv::OpFMul, type_float_, param_gen_x,
          builder_->makeFloatConstant(1.0f / float(draw_resolution_scale_x_)));
    }
    param_gen_x = builder_->createUnaryBuiltinCall(type_float_, ext_inst_glsl_std_450_,
                                                   GLSLstd450FAbs, param_gen_x);
    if (!modification.pixel.param_gen_point) {
      assert_true(input_front_facing_ != spv::NoResult);
      param_gen_x = builder_->createTriOp(
          spv::OpSelect, type_float_,
          builder_->createBinOp(
// END HUNK0
// BEGIN HUNK1
        builder_->createLoad(
            builder_->createAccessChain(spv::StorageClassInput, input_fragment_coordinates_,
                                        id_vector_temp_),
            spv::NoPrecision));
    if (draw_resolution_scale_y_ > 1) {
      param_gen_y = builder_->createNoContractionBinOp(
          spv::OpFMul, type_float_, param_gen_y,
          builder_->makeFloatConstant(1.0f / float(draw_resolution_scale_y_)));
    }
    param_gen_y = builder_->createUnaryBuiltinCall(type_float_, ext_inst_glsl_std_450_,
                                                   GLSLstd450FAbs, param_gen_y);
    if (modification.pixel.param_gen_point) {
      param_gen_y = builder_->createUnaryOp(
          spv::OpBitcast, type_float_,
          builder_->createBinOp(spv::OpBitwiseXor, type_uint_,
                                builder_->createUnaryOp(spv::OpBitcast, type_uint_, param_gen_y),
// END HUNK1
// BEGIN HUNK2
    // faceness), so in case the host GPU for some reason has quads used for
    // derivative calculation at odd locations, the left and top edges will have
    // correct derivative magnitude and LODs.
    in_position_used_ |= 0b0011;
    a_.OpRoundNI(dxbc::Dest::R(param_gen_temp, 0b0011), dxbc::Src::V1D(in_reg_ps_position_));
    uint32_t resolution_scaled_axes =
        uint32_t(draw_resolution_scale_x_ > 1) | (uint32_t(draw_resolution_scale_y_ > 1) << 1);
    if (resolution_scaled_axes) {
      // Revert resolution scale - after truncating, so if the pixel position
      // is passed to tfetch (assuming the game doesn't round it by itself),
      // it will be sampled with higher resolution too.
      a_.OpMul(dxbc::Dest::R(param_gen_temp, resolution_scaled_axes), dxbc::Src::R(param_gen_temp),
               dxbc::Src::LF(1.0f / draw_resolution_scale_x_, 1.0f / draw_resolution_scale_y_, 1.0f,
                             1.0f));
    }
    if (shader_modification.pixel.param_gen_point) {
      // A point - always front-facing (the upper bit of X is 0), not a line
      // (the upper bit of Z is 0).
      // Take the absolute value of the position and apply the point flag.
      a_.OpMov(dxbc::Dest::R(param_gen_temp, 0b0001),
               dxbc::Src::R(param_gen_temp, dxbc::Src::kXXXX).Abs());
      a_.OpMov(dxbc::Dest::R(param_gen_temp, 0b0010),
// END HUNK2
