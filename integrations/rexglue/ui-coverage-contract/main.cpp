// Synthetic coverage atlases only; this contract needs no game dump or GPU.
#include <rex/graphics/pipeline/texture/hd_override.h>
#include <cstdio>
int main(int argc, char** argv) {
  if (argc != 3) return 2;
  using namespace rex::graphics;
  const auto folder = std::filesystem::u8path(argv[1]);
  const std::string expected(argv[2]);
  size_t remaining = 32u << 20;
  if (HDReadReplacement(folder, remaining)) return 3;  // Never an opaque material.
  auto image = HDReadReplacement(folder, remaining, nullptr, 0, true);
  if (expected == "reject") return image ? 4 : 0;
  if (!image || (expected != "rgba8" && expected != "bc3")) return 5;
  if (HDIsRGBA8Coverage(*image) != (expected == "rgba8")) return 6;
  if (image->width != 128 || image->height != 128 || image->mips.size() != 8 ||
      HDVisibleMipCount(0, uint32_t(image->mips.size())) != 1 ||
      image->bytes.size() + 128 + remaining != (32u << 20)) return 7;
  if (expected == "rgba8") {
    if (image->mips.front().row_bytes != 512 || image->mips.front().rows != 128 ||
        image->mips.back().row_bytes != 4 || image->mips.back().rows != 1) return 8;
  }
  std::puts("coverage storage, mip footprints and opaque isolation verified");
  return 0;
}
