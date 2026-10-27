// Original Aster inspection helper. Uses the pinned SDK's licensed conversion
// primitives; no game data is embedded. Writes only the original base mip.
#include <rex/graphics/pipeline/texture/conversion.h>
#include <rex/graphics/pipeline/texture/util.h>
#include <array>
#include <charconv>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

static uint32_t number(const char* text) {
  uint32_t result = 0;
  const char* end = text;
  while (*end) ++end;
  const auto parsed = std::from_chars(text, end, result);
  if (parsed.ec != std::errc{} || parsed.ptr != end)
    throw std::runtime_error("invalid integer");
  return result;
}
#ifdef _WIN32
using argument_char = wchar_t;
#define ASTER_PROGRAM_ENTRY wmain
static uint32_t number(const wchar_t* text) {
  std::string ascii;
  for (; *text; ++text) {
    if (*text < L'0' || *text > L'9') throw std::runtime_error("invalid integer");
    ascii.push_back(static_cast<char>(*text));
  }
  return number(ascii.c_str());
}
#else
using argument_char = char;
#define ASTER_PROGRAM_ENTRY main
#endif
static void swap_block(rex::graphics::xenos::Endian endian, void* output,
                       const void* input, size_t size) {
  if (endian == rex::graphics::xenos::Endian::k16in32) {
    // Pinned SDK CopySwapBlock passes byte length as a word count for this case.
    // Handle it explicitly to avoid reading/writing beyond the captured block.
    auto* dst = static_cast<uint8_t*>(output);
    const auto* src = static_cast<const uint8_t*>(input);
    if (size & 3) throw std::runtime_error("unaligned 16-in-32 block");
    for (size_t i = 0; i < size; i += 4) {
      dst[i] = src[i + 2]; dst[i + 1] = src[i + 3];
      dst[i + 2] = src[i]; dst[i + 3] = src[i + 1];
    }
  } else {
    rex::graphics::texture_conversion::CopySwapBlock(endian, output, input, size);
  }
}
static void word(std::ostream& out, uint32_t value) {
  const std::array<char, 4> bytes{char(value), char(value >> 8),
                                char(value >> 16), char(value >> 24)};
  out.write(bytes.data(), bytes.size());
}
int ASTER_PROGRAM_ENTRY(int argc, argument_char** argv) {
  try {
    if (argc != 9) throw std::runtime_error(
        "usage: untile_capture raw width height row_pitch_bytes format endian tiled output.dds");
    const uint32_t width = number(argv[2]), height = number(argv[3]);
    const uint32_t row_pitch = number(argv[4]), format = number(argv[5]);
    const uint32_t endian = number(argv[6]), tiled = number(argv[7]);
    if (!width || !height || width > 2048 || height > 2048 ||
        (format != 18 && format != 20) || endian > 3 || tiled > 1)
      throw std::runtime_error("unsupported inspection layout");
    const uint32_t block_bytes = format == 18 ? 8 : 16;
    const uint32_t blocks_x = (width + 3) / 4, blocks_y = (height + 3) / 4;
    if (row_pitch % block_bytes || row_pitch < blocks_x * block_bytes ||
        row_pitch > (1u << 20)) throw std::runtime_error("invalid row pitch");
    // Native filesystem::path is UTF-16 on Windows; no ANSI conversion.
    const std::filesystem::path input_path(argv[1]), output_path(argv[8]);
    std::ifstream input(input_path, std::ios::binary | std::ios::ate);
    const auto length = input.tellg();
    if (!input || length <= 0 || length > (16 << 20))
      throw std::runtime_error("invalid capture file size");
    std::vector<uint8_t> raw(static_cast<size_t>(length));
    input.seekg(0);
    input.read(reinterpret_cast<char*>(raw.data()), raw.size());
    if (!input) throw std::runtime_error("capture read failed");
    std::vector<uint8_t> linear(size_t(blocks_x) * blocks_y * block_bytes);
    using namespace rex::graphics;
    const auto byte_order = static_cast<xenos::Endian>(endian);
    if (tiled) {
      const uint32_t pitch_blocks = row_pitch / block_bytes;
      if (pitch_blocks & 31) throw std::runtime_error("unaligned tiled pitch");
      // Validate every accessed SDK offset before letting Untile read the file.
      const uint32_t block_log2 = block_bytes == 8 ? 3 : 4;
      for (uint32_t y = 0; y < blocks_y; ++y) {
        for (uint32_t x = 0; x < blocks_x; ++x) {
          const int32_t offset = texture_util::GetTiledOffset2D(x, y, pitch_blocks, block_log2);
          if (offset < 0 || size_t(offset) + block_bytes > raw.size())
            throw std::runtime_error("capture truncated for tiled layout");
        }
      }
      texture_conversion::UntileInfo layout{};
      layout.width = blocks_x;
      layout.height = blocks_y;
      layout.input_pitch = pitch_blocks;
      layout.output_pitch = blocks_x;
      layout.input_format_info = FormatInfo::Get(format);
      layout.output_format_info = layout.input_format_info;
      layout.copy_callback = [byte_order](void* dst, const void* src, size_t size) {
        swap_block(byte_order, dst, src, size);
      };
      texture_conversion::Untile(linear.data(), raw.data(), &layout);
    } else {
      if (size_t(blocks_y - 1) * row_pitch + blocks_x * block_bytes > raw.size())
        throw std::runtime_error("capture truncated for linear layout");
      for (uint32_t y = 0; y < blocks_y; ++y)
        swap_block(byte_order,
            linear.data() + size_t(y) * blocks_x * block_bytes,
            raw.data() + size_t(y) * row_pitch, blocks_x * block_bytes);
    }
    std::ifstream existing(output_path, std::ios::binary);
    if (existing.good()) throw std::runtime_error("output already exists");
    std::ofstream output(output_path, std::ios::binary);
    // DDS_HEADER: FourCC compressed base level, no fabricated mipmaps.
    output.write("DDS ", 4);
    word(output, 124); word(output, 0x00081007); word(output, height); word(output, width);
    word(output, linear.size()); word(output, 0); word(output, 0);
    for (int i = 0; i < 11; ++i) word(output, 0);
    word(output, 32); word(output, 4);
    word(output, format == 18 ? 0x31545844 : 0x35545844);  // DXT1 / DXT5
    for (int i = 0; i < 5; ++i) word(output, 0);
    word(output, 0x1000);
    for (int i = 0; i < 4; ++i) word(output, 0);
    output.write(reinterpret_cast<const char*>(linear.data()), linear.size());
    output.close();
    if (!output) throw std::runtime_error("DDS write failed");
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
