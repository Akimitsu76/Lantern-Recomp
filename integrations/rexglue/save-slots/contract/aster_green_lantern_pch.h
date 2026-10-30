#pragma once
// Synthetic ABI fixture. No game code, headers, asset or memory image.
#include <rex/ppc.h>
#include <bit>
#include <cstring>
inline uint32_t ContractWord(const uint8_t* p) {
  uint32_t v; std::memcpy(&v, p, 4);
  if constexpr (std::endian::native == std::endian::little) return std::byteswap(v);
  return v;
}
#define REX_LOAD_U32(address) ContractWord(base + uint32_t(address))
