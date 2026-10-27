# Original texture inspection (developer tool)

This is a bounded, opt-in extraction tool, **not texture replacement or an HD
preset**. It is shared by the Vulkan and D3D12 texture cache paths. It does not
modify guest memory, material data, or the rendering resource dimensions.

Apply `patches/0005-texture-inspection-capture.patch` to the pinned SDK through
the project's SDK/GPU build recipes. Set `ASTER_TEXTURE_CAPTURE_DIR` to a private
absolute output directory only for a deliberately started inspection session.
The variable is unset during ordinary play. The tool writes up to 16 texture
records / 64 MiB per process, with at most 64 unique attempts. Inspection performs
synchronous copies and file writes; do not use its runs as performance samples.

Eligibility is strictly DXT1 or DXT5, single-layer 2D, 64–2048 pixels per axis,
with a separate unpacked base level. Resolve-scaled, signed, array/cube and all
other formats are rejected. Before copying, `SharedMemory` requires every page
to be valid and rejects every page marked as GPU-written. A second immediate
comparison rejects visibly changing snapshots. This rejects known GPU targets
but **does not prove future immutability or distinguish diffuse, normal, UI and
other compressed textures**. Metadata marks classification unknown and requires
human review. The source container/material identity is still unknown.

Each JSON record describes dimensions, exact Xenos format/byte order, pitch,
base/mip pages and sizes, mip maximum and packed-mip state. Adjacent `.base.bin`
and optional `.mips.bin` files preserve the captured original bytes. The raw
XXH3 fingerprint deduplicates captures but includes padding and is not a stable
material identity. The offline tool additionally computes SHA-256 over canonical
decoded RGBA texels and dimensions, excluding guest addresses and padding.

Build the offline helper against the exact SDK:

```sh
cmake -S integrations/rexglue/texture-inspection -B /tmp/aster-texture-inspector \
  -DCMAKE_PREFIX_PATH=/path/to/rexglue-0.10.0
cmake --build /tmp/aster-texture-inspector
python3 scripts/inspect_texture_capture.py /private/capture/record.json \
  --helper /tmp/aster-texture-inspector/aster_untile_capture \
  --output /private/review/record --xex /own/dump/default.xex
```

Pillow is required only for offline DDS-to-PNG decoding. The helper uses SDK
`Untile`, `GetTiledOffset2D`, format tables and endian primitives, validates all
read offsets and outputs the original base mip as standard DXT1/DXT5 DDS.
`k16in32` swapping is handled explicitly: the pinned SDK's `CopySwapBlock` passes
byte length into a word-count routine for that endian case. The helper's local
workaround avoids that out-of-bounds access without altering SDK rendering.

A 16-case synthetic validation covered both formats, four byte orders and
linear/tiled layouts, with identical canonical decoded pixel hashes. This tests
conversion, not the semantics or authenticity of any game texture. Source-XEX
SHA-256 in `inspection.json` records the operator-selected file; it is not proof
of source-container membership.

Review `original.png`, alpha, seams, color/normal semantics and material usage
before any enhancement. Never generatively enhance normal/depth/shadow maps or
UI/text by default. AI enhancement, safe mip generation and conservative host-resource replacement
are implemented separately in `native_port/texture_enhance.py` and patch 0006.
See `docs/HD_TEXTURES.md` for the experimental single-material contract. Local game textures, enhanced
textures and captures must not be committed or included in launcher releases.

### Bounded XCTD/LZX research decoder

`xctd_decode.c` is a small, portable C helper using the public libmspack LZX
implementation. It does not run a game executable or use a proprietary decoder.
It is a research building block, not a complete game archive/texture extractor.
No original game files, extracted images, or decoded assets belong in a release.

Build it with the `mspack` include directory and `lzxd.c` from the pinned public
SDK source's `thirdparty/libmspack/libmspack/mspack` directory. For example:

```sh
cc -std=c11 -D_POSIX_C_SOURCE=200809L -O2 -Wall -Wextra \
  -I "$MSPACK_SOURCE/mspack" xctd_decode.c "$MSPACK_SOURCE/mspack/lzxd.c" \
  -o aster_xctd_decode
```

The C source uses `wmain`, `_wfopen`, `_wopen`, and `_wremove` on Windows, so
paths retain their UTF-16 spelling independently of the active ANSI code page.
A Windows C11 build must compile the same two C sources and supply the same
include directory. MSVC/clang-cl must select the wide console CRT entry point;
MinGW additionally requires `-municode` at link time. A test PE cross-build of
the Windows branch passed the decoder tests under Windows Python/Wine, including
accented, CJK, non-BMP emoji, and space-containing paths. That test uses a small
private bootstrap and does not certify a production Windows SDK build or native
Windows gameplay. Respect libmspack's LGPL-2.1 license when redistributing a linked
binary; preserve the matching public source and notices.

The two-argument form deliberately accepts only the narrow header corroborated
against six small containers from the user's own dump:

```sh
aster_xctd_decode input.lvl_760 output.decoded
```

Its exact accepted profile is big-endian magic `0ff512ed`, version/reserved bytes
`01000000`, flags `00000062`, one 20-bit output-size field in the high bits of the
word at offset 16, zero low 12-bit table padding, and payload beginning at offset
20. It uses regular LZX, window bits 17, reset interval zero, and concatenates
nonempty BE16-length-prefixed chunks. Other header variants are rejected. The
four bytes at offset 8 are **not checksum-verified**; successful decompression
therefore does not establish container authenticity or checksum integrity.

The explicit research form reads only a caller-selected framed payload:

```sh
aster_xctd_decode input.bin output.decoded \
  --payload-offset 20 --uncompressed-size 153536 --window-bits 17
```

It does not infer a header, segment boundaries, padding, or expected output size.
Multi-segment observations require an external, independently validated segment
layout; they are not automatically accepted by this helper. Current private
experiments found absolute 131072-byte slots, packed 20/32-bit output-size tables,
and occasional zero padding at slot ends in three additional containers. These
observations do not yet constitute a general archive parser.

Input is capped at 64 MiB and output at 256 MiB. Empty/truncated frames, invalid
parameters, incomplete LZX blocks, and output-size mismatches are rejected.
Output is created exclusively only after decoding succeeds; existing files and
output symlinks are refused. Input files are never modified. The JSON success
record reports the profile, lengths, chunk count, decoder parameters, and the
unverified checksum limitation.

Run the synthetic tests against a built helper:

```sh
ASTER_XCTD_DECODER=/absolute/path/aster_xctd_decode \
  python3 test_xctd_decode.py
```

These tests contain original synthetic LZX blocks, not game data. They check
framing, narrow header dispatch, bounds, malformed data, existing-file/symlink
preservation, and exact output length. They do not validate generic XCTD header
variants, texture semantics, or Windows gameplay.


### Native Unicode paths in the untile helper

`untile_capture.cpp` likewise uses `wmain` and native `std::filesystem::path`
objects on Windows. Its numeric options still accept only ASCII decimal digits;
paths are never narrowed through the ANSI code page. Linux retains its regular
`main` entry and native path bytes. The same MinGW `-municode` link requirement
applies to this C++ executable.

The synthetic Unicode path checks verify the original BC1 bytes, DDS dimensions,
refusal to overwrite an existing Unicode output, malformed-source handling, and
rejection of non-ASCII numeric options:

```sh
ASTER_UNTILE_HELPER=/absolute/path/aster_untile_capture \
  python3 test_helper_unicode.py
```

The decoder's `test_xctd_decode.py` suite also checks Unicode input/output names.
On Windows, set the corresponding environment variables in PowerShell before
running the same Python test files. These fixtures are synthetic; no game data is
included. The untile helper's Windows SDK build and runtime validation remain
separate pending checks.
