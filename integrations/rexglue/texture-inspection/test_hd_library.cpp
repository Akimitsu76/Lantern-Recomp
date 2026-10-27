// Synthetic campaign-library contract. No game assets or GPU execution.
#ifdef NDEBUG
#undef NDEBUG  // Contract assertions remain active in a Release test executable.
#endif
#include <rex/graphics/pipeline/texture/hd_override.h>
#include <cassert>
#include <iomanip>
#include <iostream>

using namespace rex::graphics;
static const std::string kFingerprint(32, 'a');
static std::string Fingerprint(unsigned value) {
  std::ostringstream out; out << std::hex << std::setfill('0') << std::setw(32) << value; return out.str();
}
static std::vector<uint8_t> MakeDDS(unsigned scale = 2) {
  std::vector<uint8_t> dds(HDExpectedDDSSize(18, 64, 64, scale));
  auto word = [&](size_t offset, uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) dds[offset + i] = uint8_t(value >> (8 * i));
  };
  word(0, 0x20534444); word(4, 124); word(12, 64 * scale); word(16, 64 * scale);
  word(28, scale == 2 ? 8 : 9); word(76, 32); word(80, 4); word(84, 0x31545844);
  return dds;
}
static std::string Hash(const std::vector<uint8_t>& dds) {
  return rex::hash_bytes(std::string_view(reinterpret_cast<const char*>(dds.data()), dds.size()));
}
static void Write(const std::filesystem::path& folder, const std::vector<uint8_t>& dds,
                  const std::string& fingerprint = kFingerprint) {
  std::filesystem::create_directories(folder);
  std::ofstream file(folder / "texture.dds", std::ios::binary);
  file.write(reinterpret_cast<const char*>(dds.data()), dds.size()); file.close();
  std::ofstream index(folder / "texture.index");
  index << "ASTERHD1 18 64 64 " << fingerprint << ' ' << Hash(dds) << " reviewed-color-opaque\n";
}
static std::string Row(const std::vector<uint8_t>& dds, const std::string& relative = "material",
                       const std::string& fingerprint = kFingerprint) {
  return fingerprint + ' ' + relative + " 18 64 64 " + Hash(dds) + ' ' + std::to_string(dds.size()) + '\n';
}
int main(int argc, char** argv) {
  if (argc != 2) return 2;
  const std::filesystem::path root = std::filesystem::absolute(argv[1]);
  std::filesystem::create_directories(root);
  const auto dds = MakeDDS();
  // Parsing metadata succeeds without any material directory or DDS on disk.
  auto pack = HDReadCampaignLibrary(root, "ASTERHDLIB1 1\n" + Row(dds));
  assert(pack && pack->entries.empty() && pack->library_entries.size() == 1);
  assert(pack->HasGeometry(18, 64, 64) && !pack->HasGeometry(20, 64, 64));
  assert(pack->library_entries.at(kFingerprint).resident.expired());
  assert(!pack->Find(kFingerprint, 20, 64, 64));  // Wrong geometry does not poison a later match.
  Write(root / "material", dds);
  auto loaded = pack->Find(kFingerprint, 18, 64, 64);
  assert(loaded && loaded->width == 128 && loaded->mips.size() == 8);
  assert(loaded->mips.back().width == 1 && loaded->mips.back().height == 1);
  std::weak_ptr<const HDTextureReplacement> weak = loaded;
  std::filesystem::remove(root / "material/texture.dds");
  assert(pack->Find(kFingerprint, 18, 64, 64) == loaded);  // Active resource causes no disk retry.
  loaded.reset();
  assert(weak.expired());  // Metadata does not pin CPU texture bytes for the campaign.
  assert(!pack->Find(kFingerprint, 18, 64, 64));
  Write(root / "material", dds);
  assert(!pack->Find(kFingerprint, 18, 64, 64));  // Failure is permanently cached until restart.
  auto restarted = HDReadCampaignLibrary(root, "ASTERHDLIB1 1\n" + Row(dds));
  assert(restarted->Find(kFingerprint, 18, 64, 64));

  // Successfully evicted resources may reload, and scale 4 has an actual 4x DDS.
  auto four = MakeDDS(4); Write(root / "four", four);
  auto scaled = HDReadCampaignLibrary(root, "ASTERHDLIB1 1\n" + Row(four, "four"));
  auto scale4 = scaled->Find(kFingerprint, 18, 64, 64);
  assert(scale4 && scale4->width == 256 && scale4->mips.size() == 9);
  scale4.reset();
  assert(scaled->library_entries.at(kFingerprint).resident.expired());
  assert(scaled->Find(kFingerprint, 18, 64, 64));

  // A rewritten child index cannot override the library's pinned DDS hash.
  auto changed = dds; changed.back() = 9; Write(root / "tamper", changed);
  auto tampered = HDReadCampaignLibrary(root, "ASTERHDLIB1 1\n" + Row(dds, "tamper"));
  assert(tampered && !tampered->Find(kFingerprint, 18, 64, 64));
  auto bad_source = HDReadCampaignLibrary(root, "ASTERHDLIB1 1\n" + Row(dds, "missing"));
  assert(bad_source && !bad_source->Find(kFingerprint, 18, 64, 64));
  Write(root / "missing", dds);
  assert(!bad_source->Find(kFingerprint, 18, 64, 64));

  const std::vector<std::string> bad = {
      "ASTERHDLIB1 0\n", "ASTERHDLIB1 16385\n", "ASTERHDLIB1 1 trailing\n" + Row(dds),
      "ASTERHDLIB1 2\n" + Row(dds), "ASTERHDLIB1 1\n" + Row(dds) + "\n",
      "ASTERHDLIB1 2\n" + Row(dds) + Row(dds, "other"),
      "ASTERHDLIB1 2\n" + Row(dds) + Row(dds, "material", std::string(32, 'b')),
      "ASTERHDLIB1 1\n" + Row(dds, "../escape"), "ASTERHDLIB1 1\n" + Row(dds, "/absolute"),
      "ASTERHDLIB1 1\n" + Row(dds, "C:drive"), "ASTERHDLIB1 1\n" + Row(dds, "a\\b"),
      "ASTERHDLIB1 1\n" + Row(dds, "a//b"), "ASTERHDLIB1 1\n" + Row(dds, "./a"),
      "ASTERHDLIB1 1\n" + kFingerprint + " material 6 64 64 " + Hash(dds) + " 128\n",
      "ASTERHDLIB1 1\n" + kFingerprint + " material 18 65 64 " + Hash(dds) + ' ' + std::to_string(dds.size()) + '\n',
      "ASTERHDLIB1 1\n" + kFingerprint + " material 18 64 64 " + Hash(dds) + " 128\n"};
  for (const auto& text : bad) assert(!HDReadCampaignLibrary(root, text));
  assert(!HDReadCampaignLibrary(root, std::string((4u << 20) + 1, 'x')));

  // The full metadata limit is accepted without loading 16,384 DDS resources.
  std::string large = "ASTERHDLIB1 16384\n";
  for (unsigned i = 0; i < 16384; ++i) large += Row(dds, "m" + std::to_string(i), Fingerprint(i));
  auto full = HDReadCampaignLibrary(root, large);
  assert(full && full->library_entries.size() == 16384 && full->entries.empty());
  for (const auto& entry : full->library_entries) assert(entry.second.resident.expired());
  // Declared DDS storage over 64 GiB fails without opening material files.
  std::string over_budget = "ASTERHDLIB1 1024\n";
  const auto big_size = HDExpectedDDSSize(20, 2048, 2048, 4);
  for (unsigned i = 0; i < 1024; ++i) {
    over_budget += Fingerprint(i) + " m" + std::to_string(i) + " 20 2048 2048 " +
        std::string(32, '0') + ' ' + std::to_string(big_size) + '\n';
  }
  assert(!HDReadCampaignLibrary(root, over_budget));
#ifndef _WIN32
  // Path validation happens before the lazy open, including ancestor links.
  std::filesystem::create_directory_symlink(root / "material", root / "link");
  auto linked = HDReadCampaignLibrary(root, "ASTERHDLIB1 1\n" + Row(dds, "link"));
  assert(linked && !linked->Find(kFingerprint, 18, 64, 64));
#endif
  std::ofstream(root / "texture-library.index") << "ASTERHDLIB1 1\n" + Row(dds);
  // Caller sets ASTER_HD_TEXTURE_PACK_DIR to root for the immutable process loader.
  const auto runtime_pack = LoadHDTexturePack();
  assert(runtime_pack && runtime_pack->library_entries.size() == 1 && runtime_pack->entries.empty());
  assert(runtime_pack->Find(kFingerprint, 18, 64, 64));
  assert(!LoadHDTextureReplacement());
  std::cout << "Campaign library: metadata/lazy IO/weak lifetime/2x4x/tamper/path/bounds passed\n";
}
