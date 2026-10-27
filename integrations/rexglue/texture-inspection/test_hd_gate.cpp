// Standalone contract test for the deliberately narrow HD replacement gate.
// Compile against the SDK with patch 0006, then run; no game files required.
#include <rex/graphics/pipeline/texture/hd_override.h>
#include <cstdio>
#include <cstdlib>

namespace {
void Require(bool condition, const char* description) {
  if (!condition) {
    std::fprintf(stderr, "HD eligibility contract failed: %s\n", description);
    std::exit(1);
  }
}
}

class SyntheticShader final : public rex::graphics::Shader {
 public:
  explicit SyntheticShader(rex::graphics::xenos::ShaderType type)
      : Shader(type, 0, nullptr, 0) { is_ucode_analyzed_ = true; }
  void Add(const rex::graphics::ParsedTextureFetchInstruction& instruction, uint32_t slot = 0) {
    TextureBinding binding{};
    binding.fetch_constant = slot;
    binding.fetch_instr = instruction;
    texture_bindings_.push_back(binding);
  }
};

int main() {
  using namespace rex::graphics;
  using rex::graphics::ucode::FetchOpcode;
  ParsedTextureFetchInstruction ordinary{};
  ordinary.opcode = FetchOpcode::kTextureFetch;
  ordinary.dimension = xenos::FetchOpDimension::k2D;
  Require(IsHDTextureFetchEligible(ordinary), "normalized implicit-LOD 2D sample");
  unsigned rejected = 0;
  for (auto opcode : {FetchOpcode::kGetTextureComputedLod,
                      FetchOpcode::kGetTextureWeights,
                      FetchOpcode::kGetTextureGradients,
                      FetchOpcode::kGetTextureBorderColorFrac,
                      FetchOpcode::kSetTextureLod}) {
    auto instruction = ordinary;
    instruction.opcode = opcode;
    Require(!IsHDTextureFetchEligible(instruction), "only ordinary texture fetch accepted");
    ++rejected;
  }
  for (auto dimension : {xenos::FetchOpDimension::k1D,
                         xenos::FetchOpDimension::k3DOrStacked,
                         xenos::FetchOpDimension::kCube}) {
    auto instruction = ordinary;
    instruction.dimension = dimension;
    Require(!IsHDTextureFetchEligible(instruction), "only 2D accepted");
    ++rejected;
  }
  {
    auto instruction = ordinary;
    instruction.attributes.unnormalized_coordinates = true;
    Require(!IsHDTextureFetchEligible(instruction), "unnormalized coordinates rejected");
    ++rejected;
  }
  {
    auto instruction = ordinary;
    instruction.attributes.use_computed_lod = false;
    Require(!IsHDTextureFetchEligible(instruction), "constant LOD rejected");
    ++rejected;
  }
  {
    auto instruction = ordinary;
    instruction.attributes.use_register_lod = true;
    Require(!IsHDTextureFetchEligible(instruction), "register LOD rejected");
    ++rejected;
  }
  {
    auto instruction = ordinary;
    instruction.attributes.use_register_gradients = true;
    Require(!IsHDTextureFetchEligible(instruction), "explicit gradients rejected");
    ++rejected;
  }
  for (float ParsedTextureFetchInstruction::Attributes::* field : {
           &ParsedTextureFetchInstruction::Attributes::lod_bias,
           &ParsedTextureFetchInstruction::Attributes::offset_x,
           &ParsedTextureFetchInstruction::Attributes::offset_y,
           &ParsedTextureFetchInstruction::Attributes::offset_z}) {
    auto instruction = ordinary;
    instruction.attributes.*field = .5f;
    Require(!IsHDTextureFetchEligible(instruction), "nonzero LOD bias or offset rejected");
    ++rejected;
  }
  Require(!IsHDTextureDrawEligible(nullptr, nullptr), "draw with no pixel shader rejected");
  SyntheticShader vertex(xenos::ShaderType::kVertex);
  SyntheticShader pixel(xenos::ShaderType::kPixel);
  Require(!IsHDTextureDrawEligible(&vertex, &pixel), "draw with no texture rejected");
  pixel.Add(ordinary);
  Require(IsHDTextureDrawEligible(&vertex, &pixel), "simple pixel-only normalized texture draw accepted");
  auto query = ordinary;
  query.opcode = FetchOpcode::kGetTextureComputedLod;
  pixel.Add(query);  // Same slot: every instruction must be checked.
  Require(!IsHDTextureDrawEligible(&vertex, &pixel), "query aliasing ordinary sample in same slot rejected");
  SyntheticShader ordinary_pixel(xenos::ShaderType::kPixel);
  ordinary_pixel.Add(ordinary);
  vertex.Add(ordinary);
  Require(!IsHDTextureDrawEligible(&vertex, &ordinary_pixel), "vertex texture access rejects whole draw");
  // Canonical BC blocks exclude linear pitch padding and guest endian layout.
  for (uint32_t format : {18u, 20u}) for (uint32_t endian = 0; endian != 4; ++endian) {
    const uint32_t block_bytes = format == 18 ? 8 : 16;
    const uint32_t width = 68, height = 72, columns = (width + 3) / 4, rows = (height + 3) / 4;
    const uint32_t pitch = 32 * block_bytes;
    std::vector<uint8_t> expected(size_t(columns) * rows * block_bytes);
    for (size_t i = 0; i < expected.size(); ++i) expected[i] = uint8_t(i * 13 + i / 7);
    for (bool tiled : {false, true}) {
      std::vector<uint8_t> guest(32768, 0xCD), canonical;
      for (uint32_t y = 0; y < rows; ++y) for (uint32_t column = 0; column < columns; ++column) {
        const size_t offset = tiled ? texture_util::GetTiledOffset2D(column, y, 32,
            block_bytes == 8 ? 3 : 4) : size_t(y) * pitch + column * block_bytes;
        const uint8_t* src = expected.data() + (size_t(y) * columns + column) * block_bytes;
        uint8_t* dst = guest.data() + offset;
        if (endian == 3) {
          for (uint32_t i = 0; i < block_bytes; i += 4) {
            dst[i] = src[i + 2]; dst[i + 1] = src[i + 3];
            dst[i + 2] = src[i]; dst[i + 3] = src[i + 1];
          }
        } else texture_conversion::CopySwapBlock(static_cast<xenos::Endian>(endian), dst, src, block_bytes);
      }
      Require(HDCanonicalBlocks(guest, width, height, pitch, format, endian, tiled, canonical),
              "canonicalization accepts valid padded/tiled input");
      Require(canonical == expected, "canonical blocks independent of endian, tiling and padding");
      Require(!HDCanonicalBlocks(std::span<const uint8_t>(guest.data(), 1), width,
          height, pitch, format, endian, tiled, canonical), "truncated blocks rejected");
    }
  }
  std::printf("HD eligibility: ordinary 2D accepted; %u unsafe cases rejected; BC1/BC3 canonical layout matrix passed\n", rejected);
}
