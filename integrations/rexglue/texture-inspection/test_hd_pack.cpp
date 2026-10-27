// Synthetic DDS contract checks; one process per case due to immutable pack cache.
#include <rex/graphics/pipeline/texture/hd_override.h>
#include <cstdio>
int main(int argc, char** argv) {
  using namespace rex::graphics;
  if (argc != 3) return 2;
  const std::filesystem::path directory(argv[1]);
  const std::string mode(argv[2]);
  std::filesystem::create_directories(directory);
  std::vector<uint8_t> dds(128);
  auto word = [&](size_t offset, uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) dds[offset + i] = uint8_t(value >> (8 * i));
  };
  word(0, 0x20534444); word(4, 124); word(12, 128); word(16, 128);
  word(28, 8); word(76, 32); word(80, 4); word(84, 0x31545844);
  for (uint32_t size = 128; size; size >>= 1)
    dds.resize(dds.size() + size_t((size + 3) / 4) * ((size + 3) / 4) * 8);
  if (mode == "truncated") dds.pop_back();
  if (mode == "cube") word(112, 0x200);
  if (mode == "wrong-size") word(16, 256);
  if (mode == "wrong-format") word(84, 0x35545844);
  if (mode == "partial-mips") word(28, 7);
  const std::string hash = rex::hash_bytes(std::string_view(
      reinterpret_cast<const char*>(dds.data()), dds.size()));
  std::ofstream file(directory / "texture.dds", std::ios::binary);
  file.write(reinterpret_cast<const char*>(dds.data()), dds.size()); file.close();
  std::ofstream index(directory / "texture.index");
  index << "ASTERHD1 18 64 64 00000000000000000000000000000000 "
        << (mode == "bad-hash" ? std::string(32, '0') : hash) << ' '
        << (mode == "unreviewed" ? "unreviewed" : "reviewed-color-opaque") << '\n';
  index.close();
  // Set ASTER_HD_TEXTURE_PACK_DIR to argv[1] in the caller (portable Windows/Linux).
  auto pack = LoadHDTextureReplacement();
  if (bool(pack) != (mode == "valid")) {
    std::fprintf(stderr, "DDS pack contract failed: %s\n", mode.c_str()); return 1;
  }
  if (pack && (pack->width != 128 || pack->height != 128 || pack->mips.size() != 8 ||
      pack->mips.back().width != 1 || pack->mips.back().height != 1)) return 1;
  std::printf("DDS pack contract: %s passed\n", mode.c_str());
}
