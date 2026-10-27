# Spatial SDK: Linux and Windows

The original ReXGlue 0.10.0 source already contains D3D12 and Vulkan spatial FSR1
EASU/RCAS shader bytecode. The official prebuilt runtime disables that presentation
flow. Merely passing a launcher flag does not activate it.

Aster's source build enables the embedded spatial implementation, including its
intermediate EASU surface and final RCAS pass, without downloading the temporal
FidelityFX runtime. FSR2/FSR3 selection is excluded: the game does not supply the
motion/depth inputs needed to claim correct temporal reconstruction.

The source revision is `f5337cdc947ff6d4c4196737e2c807a48f2a1fc2`. Recursive
submodules must match that revision's gitlinks; patch `0004-embedded-spatial-sdk.patch`
is checked against exact source context. Installation is isolated and content
addressed. The installed `aster-spatial-sdk.json` records hashes of every file.
The native build records `presentation_backend: sdk-spatial-fsr1` only after the
SDK has compiled, installed and passed artifact verification.

## Compile the public runtime without a game

From a source checkout, run:

```sh
python scripts/build_spatial_sdk.py --allow-download --jobs 4
```

On Windows this requires Git, CMake 3.25+, Ninja, Clang 18+ with C++23, Visual
Studio C++ x64 Build Tools and the Windows SDK. A launcher executable does not
contain those development tools. Its normal Windows generation flow builds this
SDK before generating the user's game. It never patches an existing runtime DLL.

On Linux the command requires the SDK's normal Vulkan/Wayland/X11 development
dependencies. Both platforms now use this source SDK by default. The old Linux
presenter shim is only available through the developer regression override
`ASTER_USE_LEGACY_SDK=1`. CPU hosts and GPU plugins are never mixed across SDK
ABI identities. Patch 0006 adds conservative local reviewed HD texture support;
patch 0007 keeps isolated SDK installation out of the global user CMake registry.
Patches 0008/0009 cache material decisions and support legacy batches of up to
256 materials / 256 MiB DDS. Patch 0011 accepts matching 2x/4x host resources on
both backends. Patch 0012 adds immutable `ASTERHDLIB1` campaign libraries,
parsing a bounded metadata index at startup and reading a DDS only after an
eligible original-material fingerprint matches. Patch 0013 reads
`ASTER_HD_TEXTURE_PACK_DIR` through Windows' wide-character environment API;
non-ASCII library-root paths do not depend on the process ANSI code page.
Public Unicode extraction helpers link against this same SDK, and the workflow
builds them without assets.

The normal launcher shares this policy on Linux and Windows: Baixa/Média keep
original textures without preparing AI tools; Alta prepares reviewed materials
at 2x and Ultra at 4x before play. A verified 4x inference master is reused
between presets, with separate derived DDS/mip products. The metadata-only
source profile selects `runtime_library: true` for 253 reviewed opaque diffuse
materials with recorded uses across all ten mission containers. This source
coverage does not certify completed AI generation, all enhanced image quality,
or gameplay throughout the campaign. Alpha, normal, specular, effect and
unknown variants retain their originals.

Campaign libraries accept up to 16,384 materials, a 4 MiB index and 64 GiB of
DDS files; Python validates at most 256 GiB of total member files. Those are
storage ceilings, not resident allocations. Weak CPU references retain payloads
only while active owners need them, and GPU texture-cache accounting remains
in force. First matching DDS reads are synchronous and can still pause play;
preparing AI outside gameplay does not remove this lazy-load limitation.

Offline layout inference is restricted to the constant TFO family corroborated
against 145 captured resource records. Endian-1/tiled interpretation is not a
universal decoded field. Pinned source/block hashes, canonical DDS/pixel hashes,
visual material review and runtime original-BC fingerprints independently guard
this bounded replacement route. See [HD_TEXTURES.md](HD_TEXTURES.md) for the
complete contract and validation limits.

The Windows validation workflow `native-graphics-windows.yml` is prepared but
not included in this revision. If enabled, it compiles only public runtime
sources and preserves compilation evidence. It requires no XEX or game assets. A
successful run would confirm compilation, **not Windows gameplay**. No claim of
Windows visual or performance validation follows from a Wine launcher smoke test
or the pending workflow.

FSR1 improves spatial reconstruction from the original image; it does not create
HD textures and is not temporal antialiasing. The separately configured FXAA
pass handles spatial edge smoothing. Native Windows visual comparisons and
performance testing remain necessary before calling this path fully validated.

## Hardware baseline and incremental builds

Both pinned `windows-base` and `linux-base` presets use `-march=x86-64-v2`.
Aster passes that same baseline to C and C++ compilation, including clang-cl;
it never tunes to the build machine with `-march=native`. The resulting runtime
requires an x86-64-v2 CPU (including SSE4.2/POPCNT), matching the upstream presets.

Build identity records the revision, patch hashes, explicit compiler baseline,
configurations and semantic builder revision. Cosmetic Python edits do not
invalidate artifacts. Verified source trees and their pinned submodules are
shared between build recipes. Failed build directories remain available.

To resume an existing isolated CMake tree without moving absolute build paths:

```sh
python scripts/build_spatial_sdk.py --allow-download --jobs 4 --resume-base /absolute/project/.aster/tools/spatial-sdk/OLD_KEY
```

Resume checks the exact Git revision, dependency gitlinks and final source bytes
reconstructed by applying the public patches to the immutable Git revision.
CMake is then configured with the current flags and Ninja rebuilds every affected
object. A new artifact manifest is written only after successful compilation and
installation; an old hash is never relabeled as a new build.

Patch0014 uses the canonical regular libmspack source/header directory. Its bytes
match the former cabextract symlink targets, so Windows SDK generation no longer
requires symlink checkout privileges for those LZX files. Native Windows build
and gameplay validation remain required.
