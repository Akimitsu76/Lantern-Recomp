# Graphics presets and local AI textures (experimental)

The same graphics policy is implemented for Linux and Windows. The launcher
prepares supported original materials from the user's own extracted game dump;
no game textures or generated HD images are distributed with it.

**Coverage is partial:** the current source profile identifies **253 visually
reviewed opaque diffuse materials**, with source-file uses in all ten mission
containers and shared game resources. This describes the reviewed original
material set, not 253 AI outputs validated in gameplay. Other materials retain
their originals. It is not a complete HD remaster or campaign certification.

`games/green_lantern_textures.json` selects `runtime_library: true` and records
the exact supported XEX, source-container hashes, texture-block offsets and
layout identities. This public profile contains metadata only. The private
`selected-materials.json` investigation records the material uses underlying
the ten-mission coverage; it and the original images are not release assets.

## Normal launcher workflow

1. Select the extracted game folder containing `default.xex` and its assets.
2. Open **Gráficos** and choose a preset:

   | Preset | Supported reviewed textures | Filtering | Image presentation |
   | --- | --- | --- | --- |
   | Baixa | Originals | 1x anisotropic | Bilinear, post-process AA off |
   | Média | Originals | 4x anisotropic | Bilinear and FXAA |
   | Alta | AI-enhanced 2x | 8x anisotropic | FSR 1 and FXAA |
   | Ultra | AI-enhanced 4x | 16x anisotropic | FSR 1 and FXAA |

   Alta and Ultra also increase the texture-cache memory budget. The larger
   budget alone does not add detail: the reviewed replacement DDS resources
   have the actual larger dimensions shown above. Unreviewed materials do not.
3. Use **Preparar texturas deste preset** to prepare ahead of time, or proceed
   to generating/playing the port. Those workflows ensure the selected texture
   quality is prepared before launching gameplay. The normal workflow does not
   ask the user to find a catalog or select an HD folder manually.
4. Follow material progress in the **Texturas** section. Preparation is
   cancellable; verified completed materials remain reusable. A preparation or
   source-integrity error prevents launching with an unverified replacement.
   Baixa/Média skip HD tools and model preparation entirely.

The graphics page also exposes output resolution, including **1920x1080**,
fullscreen, VSync, FPS target, upscaler, FXAA, FSR sharpness, anisotropic filtering,
dithering and new-shader compilation mode. It scrolls at smaller window sizes.
Manually changing upscaling, AA, texture quality, anisotropic filtering or
dithering selects Personalizada. Display, FPS and FSR sharpness preferences
remain independent of that choice. Texture quality Alta or
Ultra in Personalizada uses the corresponding HD scale, independent of FPS.
Internal scene scale is selectable independently: 1x (720p), 2x (1440p) or
3x (2160p). Alta selects 2x and Ultra selects 3x; Personalizada can combine
1x with Ultra textures and 1920x1080 output. Patch 0024 corrects scaled depth
pixel centers, but only opening scenes have been visually checked at 2x/3x.
Exact 1080p internal rendering (1.5x) is not implemented. Output resolution and
FSR control presentation; higher internal scales have a substantial GPU cost.
MSAA, shadows and effects retain the game's behavior where independent working
controls have not been established.

Graphics settings do not create separate saves. All presets and FPS targets
use the system user's shared game profile. The 60 FPS and unlimited modes
remain experimental independently of texture preparation.

## What happens before play

For each reviewed entry, the pipeline verifies the supported XEX and original
container, decodes the bounded supported container layout, extracts the exact
reviewed texture blocks and checks decoded pixels and DDS hashes. Original
files remain unchanged. Original caches also undergo integrity checks.

The conservative offline TFO descriptor family was corroborated against 145
captured resource records. Its endian-1/tiled interpretation is an assumption
restricted to that observed constant header family, not an independently
decoded universal layout field. Exact original-block hashes and canonical
DDS/pixel identities guard extraction, and runtime untiled BC fingerprints
must still match before replacement. Unknown descriptor variants are excluded.
A diffuse filename suffix alone does not authorize enhancement: visual review
also excludes masks, effects, placeholders and other unsuitable materials.

Real-ESRGAN `realesrgan-x4plus` then enhances the original image locally. It is a
super-resolution model, not a generative image service. Public tools/models
are fetched from the official 20220424 release and pinned by archive,
executable and model SHA-256. They stay in the user's workspace cache. The
bounded extraction helpers compile against the same pinned verified SDK.
A Vulkan-capable device is required for AI preparation on either OS; Windows
gameplay uses D3D12. A working native compiler/toolchain is also needed for
source-built components.

One **4x inference master is shared by Alta and Ultra**. Its cache identity
includes the original pixels/input PNG, exact model/executable and inference
parameters; a strong SHA-256 receipt records output identity and dimensions.
Alta derives a 2x image with linear-light filtering. Ultra uses the actual 4x
master. Both encode the original BC1/BC3 format and a complete mip chain with
linear-light color filtering. Separate derived-product keys include host
scale, encoder version and mip recipe. Switching between presets reuses a
verified master instead of rerunning the model for that material.

AI work occurs outside gameplay. New shaders use the selected runtime shader
compilation policy; texture super-resolution is not a gameplay shader task.
Changed verified caches are preserved and reported as errors rather than
silently overwritten. Interrupted unverified inference output is not accepted
as a finished master. Increasing texture resolution consumes additional
storage, preparation time and GPU memory; a frame-rate improvement is not
implied.

## Renderer contract and limits

Public patches `0006-reviewed-hd-texture-override.patch`,
`0008-hd-selection-cache.patch`, `0009-multi-material-hd-pack.patch`,
`0011-hd-texture-scales.patch` and `0012-campaign-texture-library.patch`
implement matching Vulkan/D3D12 host-resource paths. Patch
`0013-windows-hd-library-path.patch` reads the Windows pack-root environment
variable through the wide-character API, preserving non-ASCII user paths.

Original guest keys, layout and memory remain unchanged. A canonical
untiled, endian-corrected BC base-level fingerprint selects a reviewed
material. GPU-written pages, unsafe layouts and incompatible shader fetches
keep the original resource.

Eligible fetches are normalized ordinary implicit-LOD pixel samples with full
mip chains. LOD bias/minimum overrides, signed samples and vertex texture
fetches retain their originals.
Replacement resources are separately cached, invalidated by source writes and
retired after GPU submission completes. Actual larger allocations count toward
cache limits. The selection cache remembers native fallbacks, avoiding repeated
source fingerprinting for unchanged ineligible bindings.

Two immutable container formats remain supported:

| Format | Materials | Index | Aggregate DDS files | Python validation of all member files |
| --- | --- | --- | --- | --- |
| Legacy batch | Up to 256 | Existing batch index | Up to 256 MiB | Up to 2 GiB |
| Campaign library, `ASTERHDLIB1` | Up to 16,384 | Up to 4 MiB | Up to 64 GiB | Up to 256 GiB |

These are validation/storage ceilings, not preparation-size promises or
resident-memory allocations. Individual DDS resources remain limited to
128 MiB, source dimensions to 64–2048 per axis and host dimensions to 8192;
both axes must have the same supported 2x or 4x scale. Validation checks
identities, geometry, full mip chains, receipts, indexes and exact contents;
extra files and symlink escapes are refused.

At game startup the campaign renderer reads the small `texture-library.index`
metadata index rather than loading every DDS. It opens a material's DDS only
when its original BC fingerprint matches an eligible fetch. CPU payloads use
weak references, allowing memory to be released after active resources stop
owning them; actual GPU allocations remain subject to texture-cache limits.
This does **not** guarantee stall-free first use: the first matching DDS read
and validation are synchronous, and an evicted material can require another
read. AI preparation finishes before gameplay, but lazy disk reads are a
separate remaining source of possible pauses.

`texture.index`, `texture.dds`, batch/library indexes and library membership
are immutable during a game process. Changing presets or a library takes
effect on the next session. Linux and Windows use the same library contract,
per-material inference cache and Alta/Ultra scale policy.

The `reviewed-color-opaque` marker records a review decision, not automatic
material classification. Normal, shadow, depth, font, UI and unknown-purpose
maps are excluded from this color-model path. Alpha/transparency, specular,
effect and unknown descriptor variants also retain their original textures.
A successful file load does not prove a material appeared in a rendered frame; visual and runtime match
validation remain separate steps.

## Advanced tools and validation status

Manual catalog preparation and pack selection remain under
**Diagnóstico → Ferramentas de texturas** for investigation. There is no
separate Texturas HD tab in the normal navigation. Source-checkout commands
for a reviewed single texture and a reviewed catalog also remain available:

```sh
python -m native_port texture-prepare /private/decoded/inspection.json \
  --reviewed-color-opaque --download-model
python -m native_port texture-pack-prepare /private/catalog.json --download-model
```

These developer commands currently use the default 2x output. They do not
classify or review materials. Original/AI images, captures, saves, decoded
containers and generated packs stay private under `.aster`; never commit them,
upload them to CI, or include them in release payloads.

Automated tests cover preset selection, real launch arguments, preparation
before validation/spawn, cancellation/error behavior, cache integrity and
2x/4x DDS geometry with inference reuse. Synthetic model mocks test orchestration;
they are not evidence of AI image quality or a GPU rendering benchmark.
Linux helper compilation and shader/runtime tests do not establish native
Windows D3D12 or Windows AI inference correctness. The source graphics workflow
must be published and pass on Windows; Wine launcher tests are not equivalent.
On Linux, all253 materials were prepared in2x and4x, accepted by the native
DDS loader and checked for geometry, hashes and full mip chains. Eight overview
sheets compared all253 source/output atlases without gross layout/color loss;
this does not certify every texel, UV seam or rendered material. Initial Oa
gameplay with the campaign library passed bounded Alta/Ultra probes. Full-campaign
gameplay, native Windows D3D12 and60FPS visual certification remain pending.

## Upstream

- [Real-ESRGAN, BSD 3-Clause](https://github.com/xinntao/Real-ESRGAN)
- [NCNN Vulkan executable, MIT](https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan)
- [Official packages](https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.2.5.0)
