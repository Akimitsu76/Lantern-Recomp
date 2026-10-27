// Synthetic materials only. Run each case in a fresh process (immutable loader).
#include <rex/graphics/pipeline/texture/hd_override.h>
#include <cstdio>
using namespace rex::graphics;
void WriteMaterial(const std::filesystem::path& directory, const std::string& fingerprint,
                   bool bc3 = false) {
  std::filesystem::create_directories(directory);
  std::vector<uint8_t> dds(128);
  auto word = [&](size_t offset, uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) dds[offset + i] = uint8_t(value >> (8 * i));
  };
  word(0, 0x20534444); word(4, 124); word(12, 128); word(16, 128);
  word(28, 8); word(76, 32); word(80, 4);
  word(84, bc3 ? 0x35545844 : 0x31545844);
  for (uint32_t size = 128; size; size >>= 1)
    dds.resize(dds.size() + size_t((size + 3) / 4) * ((size + 3) / 4) * (bc3 ? 16 : 8));
  const auto hash = rex::hash_bytes(std::string_view(
      reinterpret_cast<const char*>(dds.data()), dds.size()));
  std::ofstream file(directory / "texture.dds", std::ios::binary);
  file.write(reinterpret_cast<const char*>(dds.data()), dds.size()); file.close();
  std::ofstream index(directory / "texture.index");
  index << "ASTERHD1 " << (bc3 ? 20 : 18) << " 64 64 " << fingerprint << ' ' << hash
        << " reviewed-color-opaque\n";
}
int main(int argc, char** argv) {
  if (argc != 3) return 2;
  const std::filesystem::path root(argv[1]);
  const std::string mode(argv[2]), first(32, 'a'), second(32, 'b');
  WriteMaterial(root / "one", first);
  WriteMaterial(root / "two", second, true);
  std::string index = "ASTERHDPACK1 2\n" + first + " one\n" + second + " two\n";
  if (mode == "valid256") {
    index = "ASTERHDPACK1 256\n";
    for (unsigned i = 0; i < 256; ++i) {
      char value[33]; std::snprintf(value, sizeof(value), "%032x", i);
      const auto relative = "material_" + std::to_string(i);
      WriteMaterial(root / relative, value, bool(i & 1));
      index += std::string(value) + ' ' + relative + '\n';
    }
    std::ofstream(root / "texture-pack.index") << index;
    const auto pack = LoadHDTexturePack();
    if (!pack || pack->entries.size() != 256) return 1;
    std::puts("Multi-material pack contract: maximum 256 entries passed"); return 0;
  }
  if (mode == "budget") {
    size_t remaining = 128;
    if (HDReadReplacement(root / "one", remaining) || remaining != 128) return 1;
    std::puts("Multi-material budget rejects before payload allocation"); return 0;
  }
  if (mode == "duplicate") index = "ASTERHDPACK1 2\n" + first + " one\n" + first + " two\n";
  if (mode == "mismatch") index = "ASTERHDPACK1 2\n" + first + " one\n" + second + " one\n";
  if (mode == "traversal") index = "ASTERHDPACK1 1\n" + first + " ../one\n";
  if (mode == "absolute") index = "ASTERHDPACK1 1\n" + first + " /one\n";
  if (mode == "backslash") index = "ASTERHDPACK1 1\n" + first + " one\\two\n";
  if (mode == "empty-component") index = "ASTERHDPACK1 1\n" + first + " one//two\n";
  if (mode == "extra") index += second + " two\n";
  if (mode == "count") index = "ASTERHDPACK1 257\n";
  if (mode == "zero") index = "ASTERHDPACK1 0\n";
  if (mode == "negative") index = "ASTERHDPACK1 -1\n";
  if (mode == "oversize-index") index.assign(65537, 'a');
  if (mode == "child-index") { std::ofstream f(root / "two" / "texture.index"); f << std::string(513, 'x'); }
  if (mode == "bad-dds") { std::ofstream f(root / "two" / "texture.dds"); f << "bad"; }
  if (mode == "symlink-directory") {
    std::filesystem::rename(root / "two", root / "actual-two");
    std::filesystem::create_directory_symlink(root / "actual-two", root / "two");
  }
  if (mode == "symlink-dds") {
    std::filesystem::rename(root / "two" / "texture.dds", root / "actual.dds");
    std::filesystem::create_symlink(root / "actual.dds", root / "two" / "texture.dds");
  }
  if (mode == "symlink-root") {
    const auto actual = root.parent_path() / (root.filename().string() + "-actual");
    std::filesystem::rename(root, actual);
    std::filesystem::create_directory_symlink(actual, root);
  }
  if (mode == "symlink-index") {
    std::filesystem::rename(root / "two" / "texture.index", root / "actual.index");
    std::filesystem::create_symlink(root / "actual.index", root / "two" / "texture.index");
  }
  std::ofstream(root / "texture-pack.index") << index;
  const auto pack = LoadHDTexturePack();
  if (bool(pack) != (mode == "valid")) {
    std::fprintf(stderr, "Multi-material contract failed: %s\n", mode.c_str()); return 1;
  }
  if (pack && (pack->entries.size() != 2 || !pack->entries.contains(first) ||
      !pack->entries.contains(second) || !pack->HasGeometry(18, 64, 64) ||
      !pack->HasGeometry(20, 64, 64) || pack->HasGeometry(18, 128, 64) ||
      pack->entries.at(second)->mips.size() != 8 || LoadHDTextureReplacement())) return 1;
  std::printf("Multi-material pack contract: %s passed\n", mode.c_str());
}
