"""Deterministic, alpha-aware UI preparation and experimental runtime packs.

Color-texture AI and its mip encoder intentionally do not handle UI alpha. These
helpers preserve normalized atlas coordinates and use bounded interpolation, not
new glyph generation. A reviewed source and explicit alpha interpretation are
required. Glyph rectangles must come from verified atlas metadata, not guesses.
The separate ASTERUI1/ASTERUI2 runtime channels have demonstrated the reviewed font upload.
It remains an explicit CLI experiment; presets do not enable it automatically.
Upload evidence does not by itself establish better in-game typography.
"""
from __future__ import annotations

import io
import struct

from .errors import PortError
from .tasks import Cancellation

RECIPE = 'aster-ui-straight-linear-premult-bilinear-v1'
RGBA_RECIPE = 'aster-ui-white-coverage-rgba8-bilinear-v2'
RGBA_PATCH = '0030-ui-uncompressed-coverage.patch'


def _geometry(size):
    if (len(size) != 2 or any(type(n) is not int or not 1 <= n <= 8192 for n in size)
            or size[0] * size[1] > 4 * 1024**2):
        raise PortError('UI_SIZE', 'Imagem de interface excede os limites de preparação.')


def resize_straight_alpha(image, size, *, alpha_semantics, cancel=None):
    """Filter straight-alpha sRGB in linear, premultiplied space without ringing.

    Hidden RGB at alpha zero cannot leak into visible pixels. Bilinear keeps
    alpha within the original extrema and avoids sharpening fragile glyph edges.
    Returned pixels are straight alpha, matching the declared source contract.
    """
    from PIL import Image
    if alpha_semantics != 'straight':
        raise PortError('UI_ALPHA', 'Confirme alpha direto; alpha desconhecido ou pré-multiplicado exige revisão própria.')
    _geometry(image.size); _geometry(size)
    cancel = cancel or Cancellation(); cancel.check()
    image = image.convert('RGBA')
    if image.size == tuple(size):
        return image.copy()
    lut = [v / 255 / 12.92 if v <= 10 else ((v / 255 + .055) / 1.055) ** 2.4 for v in range(256)]
    raw = image.tobytes(); alpha = Image.frombytes('L', image.size, raw[3::4])
    filtered_alpha = alpha.point([v / 255 for v in range(256)], mode='F').resize(size, Image.Resampling.BILINEAR)
    alpha_values = list(filtered_alpha.get_flattened_data())
    channels = []
    for component in range(3):
        cancel.check()
        premult = Image.new('F', image.size)
        premult.putdata([lut[raw[i + component]] * raw[i + 3] / 255 for i in range(0, len(raw), 4)])
        filtered = premult.resize(size, Image.Resampling.BILINEAR)
        result = bytearray()
        for index, (color, opacity) in enumerate(zip(filtered.get_flattened_data(), alpha_values)):
            if index % 65536 == 0: cancel.check()
            value = min(1., max(0., color / opacity)) if opacity > 1.e-8 else 0.
            encoded = 12.92 * value if value <= .0031308 else 1.055 * value ** (1 / 2.4) - .055
            result.append(max(0, min(255, round(encoded * 255))))
        channels.append(Image.frombytes('L', tuple(size), bytes(result)))
    channels.append(Image.frombytes('L', tuple(size), bytes(max(0, min(255, round(a * 255))) for a in alpha_values)))
    return Image.merge('RGBA', channels)


def prepare_reviewed_ui(image, *, scale, classification, alpha_semantics,
                        reviewed=False, glyph_rectangles=None, cancel=None):
    """Prepare UI pixels without changing source UVs or original font metrics.

    Standalone UI images may use their whole rectangle. A glyph atlas needs a
    complete externally verified list of pixel rectangles, including its padding.
    Rectangles are processed independently, preventing cross-cell interpolation.
    Overlaps, out-of-bounds cells, and uncovered alpha>1 pixels fail. Original
    BC3 alpha=1 residue outside cells is retained with nearest sampling.
    """
    from PIL import Image
    if reviewed is not True or classification not in ('ui-image', 'glyph-atlas'):
        raise PortError('UI_REVIEW', 'Revise a finalidade e o alpha do recurso antes da preparação.')
    if type(scale) is not int or scale not in (2, 4):
        raise PortError('UI_SCALE', 'A interface revisada aceita escala 2x ou 4x.')
    _geometry(image.size); _geometry((image.width * scale, image.height * scale))
    if classification == 'ui-image':
        if glyph_rectangles is not None:
            raise PortError('UI_ATLAS', 'Metadados de glifos pertencem somente a atlas revisados.')
        return resize_straight_alpha(image, (image.width * scale, image.height * scale), alpha_semantics=alpha_semantics, cancel=cancel)
    if not isinstance(glyph_rectangles, (list, tuple)) or not 1 <= len(glyph_rectangles) <= 4096:
        raise PortError('UI_ATLAS', 'Atlas exige retângulos e margens originais verificados.')
    covered = Image.new('1', image.size)
    # Preserve sub-LSB BC3 residue outside cells without interpolating neighbors.
    output = image.convert('RGBA').resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
    rectangles = []
    for rect in glyph_rectangles:
        if (not isinstance(rect, (list, tuple)) or len(rect) != 4 or
                any(type(n) is not int for n in rect)):
            raise PortError('UI_ATLAS', 'Retângulo de glifo inválido.')
        x0, y0, x1, y1 = rect
        if not (0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height):
            raise PortError('UI_ATLAS', 'Retângulo de glifo fora da imagem.')
        if covered.crop(rect).getbbox():
            raise PortError('UI_ATLAS', 'Retângulos de glifos não podem se sobrepor.')
        covered.paste(1, tuple(rect)); rectangles.append(tuple(rect))
    from PIL import ImageChops
    outside = ImageChops.subtract(image.convert('RGBA').getchannel('A'), covered.convert('L'))
    # The original BC3 atlas has alpha=1 quantization residue outside glyphs.
    # Preserve that residue, but require every alpha>1 pixel inside a known cell.
    if outside.getextrema()[1] > 1:
        raise PortError('UI_ATLAS', 'Pixels visíveis não cobertos pelos metadados de glifos.')
    for rect in rectangles:
        tile = image.crop(rect)
        prepared = resize_straight_alpha(tile, (tile.width * scale, tile.height * scale), alpha_semantics=alpha_semantics, cancel=cancel)
        output.paste(prepared, (rect[0] * scale, rect[1] * scale))
    return output


def encode_ui_mips(image, *, alpha_semantics, cancel=None):
    """BC3 full mip chain retaining alpha at every level (unlike color encoder).

    BC3 is lossy. Prepared runtime packs are experimental; matching gameplay
    comparisons are required before automatic preset selection. Base-only source
    fonts expose only host mip0, preserving the original sampling contract.
    """
    cancel = cancel or Cancellation(); _geometry(image.size)
    if alpha_semantics != 'straight':
        raise PortError('UI_ALPHA', 'Alpha direto deve ser confirmado antes da codificação.')
    level = image.convert('RGBA'); chunks = []; header = None
    # White-coverage font atlases retain white hidden RGB too. BC3 color
    # compression must not interpolate black transparent texels into glyphs.
    white_coverage = all(pixel[:3] == (255, 255, 255) for pixel in level.get_flattened_data())
    while True:
        cancel.check(); buffer = io.BytesIO()
        level.save(buffer, format='DDS', pixel_format='DXT5')
        encoded = buffer.getvalue()
        expected = ((level.width + 3) // 4) * ((level.height + 3) // 4) * 16
        if encoded[:4] != b'DDS ' or len(encoded) != 128 + expected or encoded[84:88] != b'DXT5':
            raise PortError('UI_ENCODING', 'Encoder BC3 inválido.')
        if header is None: header = bytearray(encoded[:128])
        chunks.append(encoded[128:])
        if level.size == (1, 1): break
        level = resize_straight_alpha(level, (max(1, level.width // 2), max(1, level.height // 2)), alpha_semantics=alpha_semantics, cancel=cancel)
        if white_coverage:
            coverage = level.getchannel('A'); level.paste((255, 255, 255, 255), (0, 0, level.width, level.height)); level.putalpha(coverage)
    struct.pack_into('<I', header, 8, (struct.unpack_from('<I', header, 8)[0] | 0xA0000) & ~8)
    struct.pack_into('<I', header, 20, len(chunks[0]))
    struct.pack_into('<I', header, 28, len(chunks))
    struct.pack_into('<I', header, 108, 0x401008)
    return bytes(header) + b''.join(chunks)


def encode_ui_rgba_mips(image, *, cancel=None):
    """Lossless white coverage DDS: exact 8-bit alpha, no BC3 re-quantization.

    This changes storage only. Original glyph shapes/UVs/metrics remain intact;
    it does not claim to recreate typography lost in the original bitmap.
    """
    from PIL import Image
    cancel = cancel or Cancellation(); _geometry(image.size)
    level = image.convert('RGBA'); chunks = []
    if any(pixel[:3] != (255, 255, 255) for pixel in level.get_flattened_data()):
        raise PortError('UI_ENCODING', 'RGBA de cobertura exige RGB branco.')
    header = bytearray(128)
    header[:4] = b'DDS '
    # DDSD_CAPS|HEIGHT|WIDTH|PITCH|PIXELFORMAT|MIPMAPCOUNT.
    struct.pack_into('<7I', header, 4, 124, 0x2100f, level.height, level.width, level.width * 4, 0, 0)
    struct.pack_into('<8I', header, 76, 32, 0x41, 0, 32, 0xff, 0xff00, 0xff0000, 0xff000000)
    struct.pack_into('<I', header, 108, 0x401008)
    while True:
        cancel.check(); chunks.append(level.tobytes())
        if level.size == (1, 1): break
        alpha = level.getchannel('A').resize((max(1, level.width // 2), max(1, level.height // 2)), Image.Resampling.BILINEAR)
        level = Image.new('RGBA', alpha.size, 'white'); level.putalpha(alpha)
    struct.pack_into('<I', header, 28, len(chunks))
    return bytes(header) + b''.join(chunks)


def glyph_index_bytes(glyphs, width, height):
    """Serialize checked original metrics. Source coordinates never get scaled."""
    if not isinstance(glyphs, list) or not 1 <= len(glyphs) <= 4096:
        raise PortError('UI_ATLAS', 'Quantidade de glifos inválida.')
    seen = set(); occupied = []
    lines = [f'ASTERUIGLYPHS1 {len(glyphs)}']
    for glyph in glyphs:
        keys = ('codepoint', 'page', 'x', 'y', 'width', 'height', 'xoffset', 'yoffset', 'advance')
        if not isinstance(glyph, dict) or any(type(glyph.get(k)) is not int for k in keys):
            raise PortError('UI_ATLAS', 'Métricas originais inválidas.')
        cp, page, x, y, w, h, xo, yo, advance = [glyph[k] for k in keys]
        if (not 0 <= cp <= 0x10ffff or cp in seen or page != 0 or
                not 0 <= x <= width or not 0 <= y <= height or
                not 0 <= w <= width - x or not 0 <= h <= height - y or
                (w == 0) != (h == 0) or not -128 <= xo <= 127 or
                not -128 <= yo <= 127 or not 0 <= advance <= 255):
            raise PortError('UI_ATLAS', 'Métrica fora dos limites originais.')
        if w and h:
            if any(x < ox + ow and ox < x + w and y < oy + oh and oy < y + h for ox, oy, ow, oh in occupied):
                raise PortError('UI_ATLAS', 'Retângulos de glifos sobrepostos.')
            occupied.append((x, y, w, h))
        seen.add(cp)
        lines.append(' '.join(str(glyph[k]) for k in keys))
    return ('\n'.join(lines) + '\n').encode('ascii')


def prepare_ui_pack(original_dds, glyphs, destination, *, scale=2, reviewed=False, cancel=None, coverage_format='bc3'):
    """Write a separately opted-in UI pack from an exact, reviewed BC3 source.

    Does not install a runtime environment variable. The caller must pin source
    XEX/container/DDS identities and review the actual upload and glyph output.
    No font metrics in the game's memory or source resources are modified.
    """
    from pathlib import Path
    import hashlib
    import json
    import xxhash
    from PIL import Image
    cancel = cancel or Cancellation(); cancel.check()
    if coverage_format not in ('bc3', 'rgba8'):
        raise PortError('UI_ENCODING', 'Formato de cobertura UI desconhecido.')
    source = Path(original_dds).absolute(); destination = Path(destination).absolute()
    if (any(p.is_symlink() for p in (source, *source.parents)) or not source.is_file() or
            source.stat().st_size > 4 * 1024**2):
        raise PortError('UI_SOURCE', 'DDS original inválido, excessivo ou com links.')
    raw = source.read_bytes()
    if (len(raw) < 128 or raw[:4] != b'DDS ' or raw[84:88] != b'DXT5' or
            struct.unpack_from('<I', raw, 4)[0] != 124):
        raise PortError('UI_SOURCE', 'A interface revisada deve ser BC3 padrão.')
    height, width = struct.unpack_from('<II', raw, 12)
    if (any(n < 64 or n > 1024 or n & (n - 1) for n in (width, height)) or
            len(raw) != 128 + ((width + 3) // 4) * ((height + 3) // 4) * 16):
        raise PortError('UI_SOURCE', 'Geometria ou blocos originais divergentes.')
    with Image.open(io.BytesIO(raw)) as image: original = image.convert('RGBA')
    # This first bridge is specific to the verified monochrome font. Color UI,
    # effects, and premultiplied imagery require their own reviewed contract.
    if any(pixel[:3] != (255, 255, 255) for pixel in original.get_flattened_data()):
        raise PortError('UI_SOURCE', 'Primeira integração aceita somente fonte branca com cobertura alpha.')
    metrics = glyph_index_bytes(glyphs, width, height)
    rects = [(g['x'], g['y'], g['x'] + g['width'], g['y'] + g['height']) for g in glyphs if g['width'] and g['height']]
    enhanced = prepare_reviewed_ui(original, scale=scale, classification='glyph-atlas', alpha_semantics='straight', reviewed=reviewed, glyph_rectangles=rects, cancel=cancel)
    coverage = enhanced.getchannel('A')
    enhanced.paste((255, 255, 255, 255), (0, 0, enhanced.width, enhanced.height)); enhanced.putalpha(coverage)
    dds = (encode_ui_rgba_mips(enhanced, cancel=cancel) if coverage_format == 'rgba8' else
           encode_ui_mips(enhanced, alpha_semantics='straight', cancel=cancel))
    recipe = RGBA_RECIPE if coverage_format == 'rgba8' else RECIPE
    magic = 'ASTERUI2' if coverage_format == 'rgba8' else 'ASTERUI1'
    fingerprint = xxhash.xxh3_128_hexdigest(raw[128:])
    index = f'{magic} 20 {width} {height} {fingerprint} {xxhash.xxh3_128_hexdigest(dds)} reviewed-ui-straight {xxhash.xxh3_128_hexdigest(metrics)}\n'.encode('ascii')
    files = {'texture.dds': dds, 'texture.index': index, 'ui-glyphs.index': metrics}
    receipt = {'schema': 1, 'recipe': recipe, 'classification': 'reviewed-ui-straight', 'scale': scale,
               'source_dds_sha256': hashlib.sha256(raw).hexdigest(), 'source_canonical_bc_xxh3_128': fingerprint,
               'glyph_count': len(glyphs), 'metrics_modified': False, 'runtime_rendered': False,
               'files': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    files['ui-pack.json'] = (json.dumps(receipt, indent=2) + '\n').encode('utf8')
    if destination.exists():
        if (destination.is_symlink() or not destination.is_dir() or set(p.name for p in destination.iterdir()) != set(files) or
                any((destination / name).is_symlink() or not (destination / name).is_file() or
                    (destination / name).stat().st_size != len(data) or (destination / name).read_bytes() != data for name, data in files.items())):
            raise PortError('UI_CACHE_CHANGED', 'Pacote UI em cache alterado; arquivos preservados.')
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    if any(p.is_symlink() for p in destination.parents):
        raise PortError('UI_SOURCE', 'Links não são aceitos na saída UI.')
    import tempfile, os, shutil
    temporary = Path(tempfile.mkdtemp(prefix='ui-pending-', dir=destination.parent))
    try:
        for name, data in files.items(): cancel.check(); (temporary / name).write_bytes(data)
        os.rename(temporary, destination)
    finally:
        if temporary.exists(): shutil.rmtree(temporary)
    return destination


def parse_font_metrics(metrics, width, height):
    """Read the exact hash-verified records from the user's own font resource.

    No original character map, rectangle coordinates or advances are shipped in
    a public profile. The schema was corroborated against the captured atlas.
    """
    if not isinstance(metrics, bytes) or not 16 <= len(metrics) <= 4096 * 16 or len(metrics) % 16:
        raise PortError('UI_SOURCE', 'Tamanho da tabela original de glifos inválido.')
    keys = ('codepoint', 'page', 'x', 'y', 'width', 'height', 'xoffset', 'yoffset', 'advance')
    glyphs = []
    for offset in range(0, len(metrics), 16):
        if metrics[offset + 13:offset + 16] != bytes(3):
            raise PortError('UI_SOURCE', 'Variante desconhecida de registro de glifo.')
        values = struct.unpack_from('>HHHHBBbbB', metrics, offset)
        glyphs.append(dict(zip(keys, values)))
    glyph_index_bytes(glyphs, width, height)
    return glyphs


def prepare_game_ui(source, root, work, *, scale=2, cancel=None, emit=None, allow_download=False, coverage_format='bc3'):
    """Reconstruct the reviewed font from an owned dump before isolated tests.

    Shared Linux/Windows path, exact source/decoded/block/metrics/DDS hashes. This
    bridge returns a prepared pack; runtime opt-in is intentionally separate while
    matching captures establish whether the image actually improves. Never invokes AI or GPU.
    """
    import hashlib
    import json
    from pathlib import Path
    from .sources import source_path
    from .texture_enhance import sha
    from .texture_pack import SOURCE_XEX_SHA256, _relative
    from .texture_pipeline import _check_file
    from .texture_tools import ensure_texture_tools
    from .xctd import decode_container
    from .tasks import run_process
    cancel = cancel or Cancellation(); emit = emit or (lambda event: None)
    root = Path(root).absolute(); profile_path = root / 'games/green_lantern_ui.json'
    if profile_path.is_symlink() or profile_path.stat().st_size > 256 * 1024:
        raise PortError('UI_PROFILE', 'Perfil de fonte inválido.')
    profile = json.loads(profile_path.read_text(encoding='utf8'))
    if (profile.get('schema') != 1 or profile.get('classification') != 'reviewed-ui-straight' or
            profile.get('source_xex_sha256') != SOURCE_XEX_SHA256 or
            profile.get('runtime_default_enabled') is not False):
        raise PortError('UI_PROFILE', 'Fonte sem revisão correspondente ao XEX.')
    candidate = Path(source).expanduser()
    if candidate.is_dir():
        matches = [p for p in candidate.iterdir() if p.name.lower() == 'default.xex']
        if len(matches) != 1: raise PortError('UI_SOURCE', 'Pasta exige um único default.xex.')
        candidate = matches[0]
    xex = source_path(candidate)
    if sha(xex, cancel) != SOURCE_XEX_SHA256:
        raise PortError('UI_SOURCE', 'XEX diferente da revisão da fonte.')
    for key in ('compressed_sha256', 'decoded_sha256', 'raw_sha256', 'original_dds_sha256', 'metrics_sha256'):
        value = profile.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise PortError('UI_PROFILE', 'Hash de fonte inválido.')
    bounds = {'compressed_size': (1, 512 * 1024**2), 'decoded_size': (1, 1024**3),
              'raw_offset': (0, 1024**3), 'raw_size': (1, 4 * 1024**2),
              'metrics_offset': (0, 1024**3), 'metrics_size': (16, 4096 * 16)}
    if any(type(profile.get(k)) is not int or not low <= profile[k] <= high for k, (low, high) in bounds.items()):
        raise PortError('UI_PROFILE', 'Limites de fonte inválidos.')
    for offset, count in (('raw_offset', 'raw_size'), ('metrics_offset', 'metrics_size')):
        if profile[offset] + profile[count] > profile['decoded_size']:
            raise PortError('UI_PROFILE', 'Fonte fora do contêiner.')
    if (profile.get('format') != 20 or profile.get('endian') != 1 or profile.get('tiled') is not True or
            any(type(profile.get(k)) is not int or not 64 <= profile[k] <= 1024 or profile[k] & (profile[k] - 1) for k in ('width', 'height')) or
            profile.get('row_pitch_bytes') != ((profile['width'] + 127) // 128) * 512 or
            profile['raw_size'] != ((profile['width'] + 127) // 128) * ((profile['height'] + 127) // 128) * 16384):
        raise PortError('UI_PROFILE', 'Layout de fonte desconhecido.')
    if (profile.get('metrics_schema') != 'domyouji-be16-records-v1' or profile.get('metrics_stride') != 16 or
            type(profile.get('glyph_count')) is not int or not 1 <= profile['glyph_count'] <= 4096 or
            profile['metrics_size'] != profile['glyph_count'] * 16):
        raise PortError('UI_PROFILE', 'Esquema de métricas originais inválido.')
    compressed = _relative(xex.parent, profile.get('source_relative'))
    _check_file(compressed, profile['compressed_size'], profile['compressed_sha256'], cancel)
    tools = ensure_texture_tools(root, work, cancel=cancel, emit=emit, allow_download=allow_download)
    decoded = work.path('textures/decoded/' + profile['decoded_sha256'] + '.bin')
    if decoded.exists(): _check_file(decoded, profile['decoded_size'], profile['decoded_sha256'], cancel)
    else:
        decoded.parent.mkdir(parents=True, exist_ok=True)
        decode_container(compressed, decoded, tools['decoder'], cancel=cancel, emit=emit,
                         expected_source_sha256=profile['compressed_sha256'], expected_output_sha256=profile['decoded_sha256'])
    with decoded.open('rb') as stream:
        stream.seek(profile['raw_offset']); raw = stream.read(profile['raw_size'])
        stream.seek(profile['metrics_offset']); metrics = stream.read(profile['metrics_size'])
    if hashlib.sha256(raw).hexdigest() != profile['raw_sha256'] or hashlib.sha256(metrics).hexdigest() != profile['metrics_sha256']:
        raise PortError('UI_SOURCE', 'Blocos ou métricas originais divergentes.')
    glyphs = parse_font_metrics(metrics, profile['width'], profile['height'])
    home = work.path('textures/ui-original/' + sha(profile_path, cancel))
    home.mkdir(parents=True, exist_ok=True)
    if any(p.is_symlink() for p in (home, *home.parents)):
        raise PortError('UI_SOURCE', 'Cache UI contém links.')
    raw_file, dds_file = home / 'source.base.bin', home / 'original.dds'
    if raw_file.exists() and raw_file.read_bytes() != raw:
        raise PortError('UI_CACHE_CHANGED', 'Blocos UI em cache alterados; preservados.')
    if raw_file.is_symlink() or dds_file.is_symlink(): raise PortError('UI_SOURCE', 'Cache UI contém links.')
    if not raw_file.exists():
        with raw_file.open('xb') as stream: stream.write(raw)
    if not dds_file.exists():
        result = run_process([str(tools['untile']), str(raw_file), str(profile['width']), str(profile['height']),
                              str(profile['row_pitch_bytes']), '20', '1', '1', str(dds_file)], cwd=root, cancel=cancel)
        if result['returncode']: raise PortError('UI_SOURCE', 'Falha ao converter atlas original.')
    if sha(dds_file, cancel) != profile['original_dds_sha256']:
        raise PortError('UI_CACHE_CHANGED', 'Atlas DDS original em cache alterado; preservado.')
    recipe = RGBA_RECIPE if coverage_format == 'rgba8' else RECIPE
    key = hashlib.sha256((sha(profile_path, cancel) + recipe + str(scale)).encode()).hexdigest()
    emit({'stage': 'ui', 'message': 'Preparando fonte original com cobertura alpha e métricas preservadas.'})
    return prepare_ui_pack(dds_file, glyphs, work.path('textures/ui-packs/' + key),
                           scale=scale, reviewed=True, cancel=cancel, coverage_format=coverage_format)


def validate_ui_pack(path, *, available_patches=None):
    """Bounded receipt/index/metrics/BC3-chain validation before runtime opt-in."""
    import hashlib, json
    import xxhash
    from pathlib import Path
    folder = Path(path).expanduser().absolute()
    expected_files = {'texture.dds', 'texture.index', 'ui-glyphs.index', 'ui-pack.json'}
    if (any(p.is_symlink() for p in (folder, *folder.parents)) or not folder.is_dir() or
            set(p.name for p in folder.iterdir()) != expected_files):
        raise PortError('UI_PACK', 'Pacote UI ausente ou com arquivos inesperados/links.')
    bounds = {'texture.dds': 32 * 1024**2, 'texture.index': 512, 'ui-glyphs.index': 256 * 1024, 'ui-pack.json': 65536}
    files = {}
    for name, limit in bounds.items():
        candidate = folder / name
        if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size > limit:
            raise PortError('UI_PACK', 'Arquivo UI inválido ou excessivo.')
        files[name] = candidate.read_bytes()
    try:
        record = json.loads(files['ui-pack.json'])
        if (record.get('schema') != 1 or record.get('recipe') not in (RECIPE, RGBA_RECIPE) or
                record.get('classification') != 'reviewed-ui-straight' or
                record.get('metrics_modified') is not False or record.get('runtime_rendered') is not False or
                set(record.get('files', {})) != expected_files - {'ui-pack.json'}):
            raise ValueError('receipt contract')
        for name, digest in record['files'].items():
            if hashlib.sha256(files[name]).hexdigest() != digest: raise ValueError('file hash')
        tokens = files['texture.index'].decode('ascii').split()
        if len(tokens) != 8 or tokens[0] != ('ASTERUI2' if record['recipe'] == RGBA_RECIPE else 'ASTERUI1') or tokens[1] != '20' or tokens[6] != 'reviewed-ui-straight':
            raise ValueError('UI index')
        width, height = map(int, tokens[2:4])
        if any(n < 64 or n > 1024 or n & (n - 1) for n in (width, height)): raise ValueError('geometry')
        if (tokens[4] != record.get('source_canonical_bc_xxh3_128') or len(tokens[4]) != 32 or
                any(c not in '0123456789abcdef' for c in tokens[4]) or
                xxhash.xxh3_128_hexdigest(files['texture.dds']) != tokens[5] or
                xxhash.xxh3_128_hexdigest(files['ui-glyphs.index']) != tokens[7]): raise ValueError('native hashes')
        lines = files['ui-glyphs.index'].decode('ascii').splitlines()
        head = lines[0].split()
        if len(head) != 2 or head[0] != 'ASTERUIGLYPHS1': raise ValueError('glyph header')
        count = int(head[1])
        if count != record.get('glyph_count') or len(lines) != count + 1: raise ValueError('glyph count')
        keys = ('codepoint', 'page', 'x', 'y', 'width', 'height', 'xoffset', 'yoffset', 'advance')
        glyphs = []
        for line in lines[1:]:
            values = [int(v) for v in line.split()]
            if len(values) != 9: raise ValueError('glyph row')
            glyphs.append(dict(zip(keys, values)))
        if glyph_index_bytes(glyphs, width, height) != files['ui-glyphs.index']: raise ValueError('canonical metrics')
        raw = files['texture.dds']
        rgba = record['recipe'] == RGBA_RECIPE
        if rgba and available_patches is not None and RGBA_PATCH not in available_patches:
            raise ValueError('Backend lacks RGBA coverage capability')
        if (len(raw) < 128 or raw[:4] != b'DDS ' or struct.unpack_from('<I', raw, 4)[0] != 124 or
                struct.unpack_from('<I', raw, 112)[0] != 0):
            raise ValueError('DDS')
        if rgba:
            if struct.unpack_from('<8I', raw, 76) != (32, 0x41, 0, 32, 0xff, 0xff00, 0xff0000, 0xff000000):
                raise ValueError('RGBA coverage layout')
        elif struct.unpack_from('<3I', raw, 76) != (32, 4, 0x35545844):
            raise ValueError('BC3 coverage layout')
        host_h, host_w = struct.unpack_from('<II', raw, 12)
        scale = record.get('scale')
        if type(scale) is not int or scale not in (2, 4) or (host_w, host_h) != (width * scale, height * scale):
            raise ValueError('DDS geometry')
        count = 0; expected = 128; w, h = host_w, host_h
        while True:
            expected += w * h * 4 if rgba else ((w + 3) // 4) * ((h + 3) // 4) * 16
            count += 1
            if (w, h) == (1, 1): break
            w, h = max(1, w // 2), max(1, h // 2)
        if len(raw) != expected or struct.unpack_from('<I', raw, 28)[0] != count: raise ValueError('DDS mip chain')
        if any(raw[i + component] != 255 for i in range(128, len(raw), 4 if rgba else 16)
               for component in (range(3) if rgba else range(8, 12))):
            raise ValueError('white coverage contract')
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as atlas:
            low, high = atlas.convert('RGBA').getchannel('A').getextrema()
        if low == 255 or high == 0: raise ValueError('missing glyph alpha coverage')
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, IndexError, PortError) as exc:
        raise PortError('UI_PACK', 'Recibo ou índice UI inválido.') from exc
    return folder
