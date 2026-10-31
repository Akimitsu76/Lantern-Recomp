// Aster Native: per-user Green Lantern save storage. No game data is embedded.
// This header is also shipped verbatim by SDK patch 0037.
#pragma once

#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <system_error>
#include <thread>
#include <utility>
#ifdef _WIN32
#include <windows.h>
#endif

namespace rex::system::xam::green_lantern {

inline constexpr uint32_t kTitleId = 0x575207E9;
inline constexpr uint32_t kSavedGameType = 1;
inline constexpr uint32_t kSlotCount = 6;

struct SaveSlot {
  uint32_t id = 0;
  bool existing = false;
  // Seconds since the Unix epoch; zero means no readable timestamp.
  int64_t modified = 0;
};

enum class SelectResult { kSuccess, kCancelled, kInvalidSlot, kOpenContent, kIoError };

// This store changes only the selected directory. Selecting never creates,
// deletes, copies, truncates or edits a save/header. The caller serializes
// selection with the content manager's normal open/create/close operations.
class SaveSlotStore {
 public:
  explicit SaveSlotStore(std::filesystem::path root) : root_(std::move(root)) {}

  static bool Eligible(uint32_t title_id, uint32_t content_type) {
    return title_id == kTitleId && content_type == kSavedGameType;
  }
  static bool ValidSlot(uint32_t id) { return id >= 1 && id <= kSlotCount; }

  static std::string Hex(uint64_t value, unsigned width) {
    std::ostringstream text;
    text << std::uppercase << std::hex << std::setfill('0') << std::setw(width) << value;
    return text.str();
  }

  std::filesystem::path TitleRoot(uint64_t xuid, uint32_t title = kTitleId) const {
    return root_ / Hex(xuid, 16) / Hex(title, 8);
  }
  std::filesystem::path SelectionPath(uint64_t xuid) const {
    return TitleRoot(xuid) / "NativeSlots" / "active.txt";
  }
  std::filesystem::path SlotBase(uint64_t xuid, uint32_t id) const {
    if (!ValidSlot(id)) throw std::invalid_argument("Invalid Green Lantern save slot");
    const auto title = TitleRoot(xuid);
    if (id == 1) return title;  // Exact legacy path, including legacy headers.
    return title / "NativeSlots" / (std::string("0") + char('0' + id));
  }
  std::filesystem::path SlotPackage(uint64_t xuid, uint32_t id) const {
    return SlotBase(xuid, id) / "00000001" / "GL_10";
  }
  std::filesystem::path SlotHeader(uint64_t xuid, uint32_t id) const {
    return SlotBase(xuid, id) / "Headers" / "00000001" / "GL_10.header";
  }

  uint32_t Active(uint64_t xuid) const {
    // Reading an absent/corrupt preference must never create or repair files.
    if (!SelectionDirectorySafe(xuid)) return 1;
    const auto path = SelectionPath(xuid);
    std::error_code ec;
    if (!std::filesystem::is_regular_file(std::filesystem::symlink_status(path, ec)) || ec)
      return 1;
    std::ifstream input(path, std::ios::binary);
    char bytes[4]{};
    input.read(bytes, sizeof(bytes));
    const auto count = input.gcount();
    if (!input.eof() || count < 1 || bytes[0] < '1' || bytes[0] > '6') return 1;
    if (count != 1 && !(count == 2 && bytes[1] == '\n') &&
        !(count == 3 && bytes[1] == '\r' && bytes[2] == '\n')) return 1;
    return uint32_t(bytes[0] - '0');
  }

  std::filesystem::path PackageRoot(uint64_t xuid, uint32_t title, uint32_t type) const {
    const auto base = Eligible(title, type) ? SlotBase(xuid, Active(xuid)) : TitleRoot(xuid, title);
    return base / Hex(type, 8);
  }
  std::filesystem::path HeaderRoot(uint64_t xuid, uint32_t title, uint32_t type) const {
    const auto base = Eligible(title, type) ? SlotBase(xuid, Active(xuid)) : TitleRoot(xuid, title);
    return base / "Headers" / Hex(type, 8);
  }

  std::array<SaveSlot, kSlotCount> List(uint64_t xuid) const {
    std::array<SaveSlot, kSlotCount> slots{};
    const bool selection_directory_safe = SelectionDirectorySafe(xuid);
    for (uint32_t id = 1; id <= kSlotCount; ++id) {
      auto& slot = slots[id - 1];
      slot.id = id;
      if (id != 1 && !selection_directory_safe) continue;
      const auto package = SlotPackage(xuid, id);
      const auto header = SlotHeader(xuid, id);
      // Incomplete containers count as occupied as well. Do not invite an
      // unconfirmed overwrite merely because a save/header is damaged.
      std::error_code ec;
      slot.existing = std::filesystem::exists(package, ec);
      ec.clear();
      slot.existing = slot.existing || std::filesystem::exists(header, ec);
      for (const auto& candidate : {package, package / "GL_10", header}) {
        ec.clear();
        const auto stamp = std::filesystem::last_write_time(candidate, ec);
        if (ec) continue;
        // MSVC's file_clock exposes to_utc instead of to_sys; clock_cast
        // accounts for its epoch and leap seconds. libstdc++ uses to_sys.
#ifdef _MSC_VER
        const auto system_stamp = std::chrono::clock_cast<std::chrono::system_clock>(stamp);
#else
        const auto system_stamp = std::filesystem::file_time_type::clock::to_sys(stamp);
#endif
        const auto seconds = std::chrono::duration_cast<std::chrono::seconds>(
            system_stamp.time_since_epoch()).count();
        if (seconds > slot.modified) slot.modified = seconds;
      }
    }
    return slots;
  }

  bool OwnsPackage(uint64_t xuid, const std::filesystem::path& package) const {
    auto name = package.filename().string();
    for (char& ch : name) if (ch >= 'a' && ch <= 'z') ch = char(ch - 'a' + 'A');
    if (name != "GL_10") return false;
    const auto parent = package.parent_path().lexically_normal();
    for (uint32_t id = 1; id <= kSlotCount; ++id)
      if (parent == SlotPackage(xuid, id).parent_path().lexically_normal()) return true;
    return false;
  }

  // An occupied New Game slot is backed up before the original game can
  // overwrite it. A failed backup must abort the menu action.
  std::optional<std::filesystem::path> Backup(uint64_t xuid, uint32_t id) const {
    if (!ValidSlot(id) || !SlotDirectorySafe(xuid, id)) return {};
    const auto parent = TitleRoot(xuid) / "NativeSlots" / "Backups";
    std::error_code ec;
    if (!OrdinaryDirectoryOrAbsent(parent)) return {};
    std::filesystem::create_directories(parent, ec);
    if (ec) return {};
    const auto stamp = std::chrono::system_clock::now().time_since_epoch().count();
    const auto target = parent / ("slot-" + std::to_string(id) + "-" + std::to_string(stamp));
    if (!std::filesystem::create_directory(target, ec) || ec) return {};
    bool ok = true;
    for (const auto& source : {SlotPackage(xuid, id), SlotHeader(xuid, id)}) {
      const auto status = std::filesystem::symlink_status(source, ec);
      if (status.type() == std::filesystem::file_type::not_found ||
          ec == std::errc::no_such_file_or_directory) { ec.clear(); continue; }
      if (ec || std::filesystem::is_symlink(status)) { ok = false; break; }
      if (std::filesystem::is_directory(status)) {
        for (const auto& entry : std::filesystem::recursive_directory_iterator(source, ec)) {
          if (ec || std::filesystem::is_symlink(entry.symlink_status(ec))) { ok = false; break; }
        }
      }
      if (!ok || ec) { ok = false; break; }
      std::filesystem::copy(source, target / source.filename(),
                            std::filesystem::copy_options::recursive, ec);
      if (ec) { ok = false; break; }
    }
    if (!ok) return {}; // Preserve any partial backup for diagnosis.
    std::ofstream marker(target / "complete", std::ios::binary);
    marker << "Aster save slot backup\n";
    marker.close();
    if (!marker) return {};
    return target;
  }

  SelectResult Select(uint64_t xuid, std::optional<uint32_t> id, bool content_open = false) const {
    if (!id) return SelectResult::kCancelled;
    if (!ValidSlot(*id)) return SelectResult::kInvalidSlot;
    if (content_open) return SelectResult::kOpenContent;
    if (!SlotDirectorySafe(xuid, *id)) return SelectResult::kIoError;
    const auto target = SelectionPath(xuid);
    std::error_code ec;
    const auto target_status = std::filesystem::symlink_status(target, ec);
    if (!ec && target_status.type() != std::filesystem::file_type::not_found &&
        !std::filesystem::is_regular_file(target_status)) return SelectResult::kIoError;
    ec.clear();
    std::filesystem::create_directories(target.parent_path(), ec);
    if (ec || !SelectionDirectorySafe(xuid)) return SelectResult::kIoError;

    // Atomically claim a new staging directory, rather than truncating a
    // predictable temporary file. Publish with rename, never remove+rename.
    static std::atomic<uint64_t> sequence{0};
    std::filesystem::path staging;
    for (unsigned attempt = 0; attempt < 64; ++attempt) {
      const auto tick = uint64_t(std::chrono::steady_clock::now().time_since_epoch().count());
      auto candidate = target.parent_path() /
          (".active-write-" + Hex(tick, 16) + "-" + Hex(sequence.fetch_add(1), 16));
      ec.clear();
      if (std::filesystem::create_directory(candidate, ec)) {
        staging = std::move(candidate);
        break;
      }
      if (ec && ec != std::errc::file_exists) return SelectResult::kIoError;
    }
    if (staging.empty()) return SelectResult::kIoError;
    struct Cleanup {
      std::filesystem::path folder;
      ~Cleanup() {
        std::error_code ignored;
        std::filesystem::remove(folder / "value", ignored);
        std::filesystem::remove(folder, ignored);
      }
    } cleanup{staging};
    const auto temporary = staging / "value";
    std::ofstream output(temporary, std::ios::binary | std::ios::out | std::ios::trunc);
    if (!output) return SelectResult::kIoError;
    output.put(char('0' + *id));
    output.put('\n');
    output.flush();
    output.close();
    if (!output) return SelectResult::kIoError;
    for (unsigned attempt = 0; attempt < 8; ++attempt) {
      ec.clear();
#ifdef _WIN32
      if (::MoveFileExW(temporary.c_str(), target.c_str(),
                        MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
        return SelectResult::kSuccess;
      ec = std::error_code(int(::GetLastError()), std::system_category());
#else
      std::filesystem::rename(temporary, target, ec);
#endif
      if (!ec) return SelectResult::kSuccess;
      if (ec != std::errc::permission_denied && ec != std::errc::device_or_resource_busy) break;
      std::this_thread::yield();
    }
    return SelectResult::kIoError;
  }

 private:
  static bool OrdinaryDirectoryOrAbsent(const std::filesystem::path& path) {
    std::error_code ec;
    const auto status = std::filesystem::symlink_status(path, ec);
    return status.type() == std::filesystem::file_type::not_found ||
           ec == std::errc::no_such_file_or_directory ||
           (!ec && std::filesystem::is_directory(status));
  }
  bool SlotDirectorySafe(uint64_t xuid, uint32_t id) const {
    if (!SelectionDirectorySafe(xuid)) return false;
    const auto base = SlotBase(xuid, id);
    for (const auto& path : {base, base / "00000001", base / "00000001" / "GL_10",
                             base / "Headers", base / "Headers" / "00000001"})
      if (!OrdinaryDirectoryOrAbsent(path)) return false;
    return true;
  }
  bool SelectionDirectorySafe(uint64_t xuid) const {
    auto path = root_;
    // The caller supplied user-data root is trusted. All newly introduced
    // components beneath it must be ordinary directories, not redirections.
    for (const auto& name : {Hex(xuid, 16), Hex(kTitleId, 8), std::string("NativeSlots")}) {
      path /= name;
      std::error_code ec;
      const auto status = std::filesystem::symlink_status(path, ec);
      if (status.type() == std::filesystem::file_type::not_found || ec == std::errc::no_such_file_or_directory)
        continue;
      if (ec || !std::filesystem::is_directory(status)) return false;
    }
    return true;
  }

  std::filesystem::path root_;
};

}  // namespace rex::system::xam::green_lantern
