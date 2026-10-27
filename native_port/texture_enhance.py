"""Local, cached Real-ESRGAN preparation for explicitly reviewed color textures.

Models/tools are public downloads; originals and generated packs stay private.
This is not automatic material classification or proof that a pack was rendered.
"""
from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import tempfile
import time
import urllib.request

from .errors import PortError
from .tasks import Cancellation, run_process

VERSION = '20220424'
MODEL = 'realesrgan-x4plus'
MODEL_HASHES = {
    'models/realesrgan-x4plus.bin': '713ee713b0353afaa27976f0563a64a5043bd70b9bd8936c2e26e25ebcdbcddf',
    'models/realesrgan-x4plus.param': '35330ececcea33b6c397a72548e788d5d53becee4734c50b7fada36e89f10a86',
}
ASSETS = {
    'linux': ('ubuntu', 'e5aa6eb131234b87c0c51f82b89390f5e3e642b7b70f2b9bbe95b6a285a40c96',
              'realesrgan-ncnn-vulkan', '22c2296a39b40cc43ac92615c827ab6d4b60b7142e8cee59f718e3f8e2cdbda9'),
    'windows': ('windows', 'abc02804e17982a3be33675e4d471e91ea374e65b70167abc09e31acb412802d',
                'realesrgan-ncnn-vulkan.exe', '07e49f7cbb4ede01ae4dd4c399d3a7e5846e3d2085c3128eff881e55cb7b1a0c'),
}


def sha(path, cancel=None):
    with Path(path).open('rb') as stream:
        if cancel is None:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
        digest = hashlib.sha256()
        while True:
            cancel.check()
            block = stream.read(1024 * 1024)
            if not block:
                return digest.hexdigest()
            digest.update(block)


def _atomic_json(path, data):
    fd, temporary = tempfile.mkstemp(prefix='.hd-record-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def ensure_engine(work, *, allow_download=False, cancel=None, emit=None):
    from .native_build import safe_extract
    from .paths import external_env
    import platform
    cancel = cancel or Cancellation()
    emit = emit or (lambda event: None)
    system = 'windows' if os.name == 'nt' else 'linux' if platform.system() == 'Linux' else ''
    if system not in ASSETS or platform.machine().lower() not in ('x86_64', 'amd64'):
        raise PortError('HD_PLATFORM', 'Super-resolução disponível para Linux e Windows x64.')
    label, checksum, executable, exe_sha = ASSETS[system]
    home = work.path(f'tools/realesrgan-{VERSION}/{label}')
    expected = {executable: exe_sha, **MODEL_HASHES}
    if system == 'windows':
        expected.update({'vcomp140.dll': '8f72ef2e483465444b2059fc6744d6cb22cd8d8a27f6fa56befd2a42dcd0f78b',
                         'vcomp140d.dll': '34980f5a28002967d4f2659b10a417b1b9a242e240195947c89195083d146c53'})
    if not all((home / name).is_file() and sha(home / name) == digest for name, digest in expected.items()):
        name = f'realesrgan-ncnn-vulkan-{VERSION}-{label}.zip'
        archive = work.path('tools/downloads/' + name)
        if not archive.is_file() or sha(archive) != checksum:
            if not allow_download:
                raise PortError('HD_TOOLS_MISSING', 'Habilite o download oficial do Real-ESRGAN para preparar texturas HD.')
            archive.parent.mkdir(parents=True, exist_ok=True)
            url = 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/' + name
            fd, temporary = tempfile.mkstemp(prefix='hd-download-', dir=archive.parent)
            try:
                with os.fdopen(fd, 'wb') as target, urllib.request.urlopen(url, timeout=60) as response:
                    total = int(response.headers.get('Content-Length', 0))
                    while block := response.read(1024 * 1024):
                        cancel.check(); target.write(block)
                        if target.tell() > 96 * 1024**2:
                            raise PortError('HD_DOWNLOAD', 'Pacote de IA excedeu o limite esperado.')
                        emit({'stage': 'hd', 'message': 'Baixando modelo de super-resolução',
                              'completed': target.tell(), 'total': total, 'unit': 'bytes'})
                if sha(temporary) != checksum:
                    raise PortError('HD_HASH', 'Hash inválido no pacote oficial de super-resolução.')
                os.replace(temporary, archive)
            finally:
                Path(temporary).unlink(missing_ok=True)
        # Trusted archive identity is checked before extracting any executable.
        home.mkdir(parents=True, exist_ok=True)
        safe_extract(archive, home)
    if not all((home / name).is_file() and sha(home / name) == digest for name, digest in expected.items()):
        raise PortError('HD_HASH', 'Executável ou modelo Real-ESRGAN alterado.')
    if system == 'linux':
        (home / executable).chmod(0o755)
    return home / executable, home / 'models', exe_sha, external_env()


def load_reviewed_source(inspection, reviewed_color_opaque, *, cancel=None):
    from PIL import Image
    if not reviewed_color_opaque:
        raise PortError('HD_REVIEW', 'Revise a imagem e confirme textura de cor opaca; não use normais, sombras, fontes ou interface.')
    cancel = cancel or Cancellation(); cancel.check()
    inspection = Path(inspection).expanduser().absolute()
    if (any(part.is_symlink() for part in (inspection, *inspection.parents)) or
            not inspection.is_file() or inspection.stat().st_size > 65536):
        raise PortError('HD_SOURCE', 'Inspeção original ausente, excessiva ou com links.')
    data = json.loads(inspection.read_text(encoding='utf8'))
    if data.get('status') != 'original-inspection-only' or data.get('runtime_replacement') is not False:
        raise PortError('HD_SOURCE', 'A origem deve ser uma captura original validada pelo inspetor.')
    source = inspection.parent / 'original.png'
    dds = inspection.parent / 'original.dds'
    for original_file in (source, dds):
        if original_file.is_symlink() or not original_file.is_file() or original_file.stat().st_size > 64 * 1024**2:
            raise PortError('HD_SOURCE', 'Original ausente, excessivo ou com link.')
    if sha(dds, cancel) != data.get('dds_sha256'):
        raise PortError('HD_SOURCE', 'Os blocos da textura original foram alterados.')
    with Image.open(source) as image:
        if any(n < 64 or n > 2048 or n & (n - 1) for n in image.size):
            raise PortError('HD_SIZE', 'Dimensões do original não suportadas.')
        rgba = image.convert('RGBA')
    cancel.check()
    width, height = rgba.size
    if not 64 <= width <= 2048 or not 64 <= height <= 2048 or width & (width - 1) or height & (height - 1):
        raise PortError('HD_SIZE', 'A amostra deve ter dimensões potência de dois entre 64 e 2048.')
    if rgba.getchannel('A').getextrema() != (255, 255):
        raise PortError('HD_ALPHA', 'Esta primeira integração aceita apenas texturas opacas revisadas.')
    canonical = hashlib.sha256(b'aster-texture-rgba8-v1\0' + struct.pack('<II', width, height) + rgba.tobytes()).hexdigest()
    if canonical != data.get('canonical_rgba8_sha256'):
        raise PortError('HD_SOURCE', 'Os pixels da textura original não correspondem à captura.')
    raw = dds.read_bytes()
    if len(raw) < 128 or raw[:4] != b'DDS ':
        raise PortError('HD_SOURCE', 'DDS original inválido.')
    fmt = {b'DXT1': 18, b'DXT5': 20}.get(raw[84:88])
    if fmt is None or fmt != data.get('capture_metadata', {}).get('format'):
        raise PortError('HD_SOURCE', 'Formato original não suportado ou divergente.')
    expected_bytes = ((width + 3) // 4) * ((height + 3) // 4) * (8 if fmt == 18 else 16)
    if (struct.unpack_from('<I', raw, 4)[0] != 124 or
            struct.unpack_from('<II', raw, 12) != (height, width) or
            len(raw) != 128 + expected_bytes):
        raise PortError('HD_SOURCE', 'Dimensões ou tamanho dos blocos originais divergentes.')
    # The PNG must decode exactly from the fingerprinted blocks, not a separate edited image.
    with Image.open(dds) as decoded:
        if decoded.convert('RGBA').tobytes() != rgba.tobytes():
            raise PortError('HD_SOURCE', 'PNG e blocos DDS não representam os mesmos pixels.')
    import xxhash
    return source, rgba.convert('RGB'), data, fmt, xxhash.xxh3_128_hexdigest(raw[128:])


def linear_resize(image, size, cancel=None):
    """Filter color mipmaps in linear light, returning sRGB bytes."""
    from PIL import Image
    lut = [(x / 255.0 / 12.92 if x <= 10 else ((x / 255.0 + 0.055) / 1.055) ** 2.4) for x in range(256)]
    channels = []
    for band in image.convert('RGB').split():
        if cancel: cancel.check()
        small = band.point(lut, mode='F').resize(size, Image.Resampling.LANCZOS)
        def encode(value):
            value = max(0.0, min(1.0, value))
            return max(0, min(255, round(255 * (12.92 * value if value <= .0031308 else 1.055 * value ** (1 / 2.4) - .055))))
        def pixels():
            for index, value in enumerate(small.get_flattened_data()):
                if cancel and index % 65536 == 0:
                    cancel.check()
                yield encode(value)
        channels.append(Image.frombytes('L', size, bytes(pixels())))
    return Image.merge('RGB', channels)


def encode_mip_dds(image, fmt, cancel=None, emit=None):
    cancel = cancel or Cancellation()
    emit = emit or (lambda event: None)
    if fmt not in (18, 20):
        raise PortError('HD_ENCODING', 'Formato DDS não suportado.')
    level = image.convert('RGBA'); chunks = []; header = None; mip_count = 0
    while True:
        cancel.check()
        buffer = io.BytesIO(); level.save(buffer, format='DDS', pixel_format='DXT1' if fmt == 18 else 'DXT5')
        encoded = buffer.getvalue()
        expected = ((level.width + 3) // 4) * ((level.height + 3) // 4) * (8 if fmt == 18 else 16)
        if encoded[:4] != b'DDS ' or len(encoded) != 128 + expected:
            raise PortError('HD_ENCODING', 'O encoder não gerou blocos DDS válidos.')
        if header is None: header = bytearray(encoded[:128])
        chunks.append(encoded[128:]); mip_count += 1
        emit({'stage': 'hd', 'message': f'Preparando mipmap {mip_count}', 'completed': mip_count,
              'total': max(image.size).bit_length(), 'unit': 'mipmaps'})
        if level.size == (1, 1): break
        size = (max(1, level.width // 2), max(1, level.height // 2))
        level = linear_resize(level, size, cancel).convert('RGBA')
    struct.pack_into('<I', header, 8, (struct.unpack_from('<I', header, 8)[0] | 0xA0000) & ~8)
    struct.pack_into('<I', header, 20, len(chunks[0]))
    struct.pack_into('<I', header, 28, mip_count)
    struct.pack_into('<I', header, 108, 0x401008)
    return bytes(header) + b''.join(chunks)


def _master_inference(source, original, identity, root, work, engine, models, env, cancel, emit):
    """Host scale never participates in this key: High and Ultra share one AI run."""
    from PIL import Image
    from .locking import lock_session
    cancel.check()
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    output = work.path('textures/inference/' + key)
    output.mkdir(parents=True, exist_ok=True)
    if any(path.is_symlink() for path in output.iterdir()):
        raise PortError('HD_CACHE_CHANGED', 'O cache de inferência contém links; artefatos preservados.')
    enhanced, inference = output / 'enhanced-x4.png', output / 'inference.json'
    dimensions = [original.width * 4, original.height * 4]
    # Advisory locks are released by the OS after process death. Keep the file
    # inode: unlinking it lets a second process lock a different inode while the
    # current owner is still working. Old O_EXCL markers are safe to reopen.
    try:
        descriptor = lock_session(output / '.inference.lock')
    except BlockingIOError as exc:
        raise PortError('HD_BUSY', 'Esta inferência está em preparação em outro processo: ' + str(output)) from exc
    try:
        # Unlike a game-session lock, this belongs only to the current worker.
        os.set_inheritable(descriptor, False)
        cancel.check()
        if inference.exists():
            try:
                if inference.stat().st_size > 65536:
                    raise ValueError('receipt too large')
                receipt = json.loads(inference.read_text(encoding='utf8'))
                if enhanced.stat().st_size > 256 * 1024**2:
                    raise ValueError('inference output too large')
                if (receipt.get('schema') != 1 or receipt.get('recipe') != identity or
                        receipt.get('dimensions') != dimensions or receipt.get('sha256') != sha(enhanced, cancel)):
                    raise ValueError('inference identity changed')
                with Image.open(enhanced) as image:
                    if list(image.size) != dimensions:
                        raise ValueError('inference geometry changed')
                    image.verify()
            except (OSError, ValueError, AttributeError) as exc:
                raise PortError('HD_CACHE_CHANGED', 'Inferência sem recibo válido; artefatos preservados: ' + str(output)) from exc
            emit({'stage': 'hd', 'message': 'Master IA 4x verificado · inferência reutilizada entre presets.'})
            return enhanced, inference
        if enhanced.exists():
            # A crash may publish the PNG before its receipt. It is not trusted as
            # a master: preserve the exact bytes and redo only this material.
            archive_descriptor, archived = tempfile.mkstemp(prefix='enhanced-unverified-', suffix='.png', dir=output)
            os.close(archive_descriptor)
            os.replace(enhanced, archived)
            emit({'stage': 'hd', 'message': 'Inferência sem recibo preservada; retomando somente este material.'})
        temporary_output = output / ('enhanced-pending-' + str(time.time_ns()) + '.png')
        emit({'stage': 'hd', 'message': 'Real-ESRGAN: preparando detalhes da textura original', 'state': 'running'})
        result = run_process([str(engine), '-i', str(source), '-o', str(temporary_output), '-m', str(models),
                              '-n', MODEL, '-s', '4', '-t', '128', '-j', '1:1:1', '-g', '0', '-f', 'png'],
                             Path(root), cancel, env=env, timeout=3600,
                             on_output=lambda line: emit({'stage': 'hd', 'message': line[:160]}))
        (output / 'inference.log').write_text(result['stdout'] + result['stderr'], encoding='utf8')
        with Image.open(temporary_output) as generated:
            if list(generated.size) != dimensions:
                raise PortError('HD_SIZE', 'A inferência não produziu a resolução esperada.')
            generated.verify()
        cancel.check()
        digest = sha(temporary_output, cancel)
        os.replace(temporary_output, enhanced)
        _atomic_json(inference, {'schema': 1, 'recipe': identity, 'sha256': digest, 'dimensions': dimensions})
        return enhanced, inference
    finally:
        os.close(descriptor)


def prepare_texture(inspection, root, work, *, reviewed_color_opaque=False,
                    allow_download=False, cancel=None, emit=None, host_scale=2):
    """Produce a reviewed 2x/4x pack with one cached AI master shared by both."""
    from PIL import Image, __version__ as pillow_version
    import shutil
    import xxhash
    if type(host_scale) is not int or host_scale not in (2, 4):
        raise PortError('HD_SCALE', 'A resolução HD deve ser 2x (Alta) ou 4x (Ultra).')
    cancel = cancel or Cancellation(); emit = emit or (lambda event: None)
    cancel.check()
    source, original, source_data, fmt, bc_id = load_reviewed_source(inspection, reviewed_color_opaque, cancel=cancel)
    engine, models, engine_hash, env = ensure_engine(work, allow_download=allow_download, cancel=cancel, emit=emit)
    inference_recipe = {'schema': 1, 'original': source_data['canonical_rgba8_sha256'],
                        'source_png_sha256': sha(source, cancel), 'model': MODEL, 'model_hashes': MODEL_HASHES,
                        'engine_sha256': engine_hash, 'inference_scale': 4, 'tile': 128, 'threads': '1:1:1'}
    recipe = {'schema': 2, 'original': source_data['canonical_rgba8_sha256'], 'original_bc': bc_id,
              'model': MODEL, 'model_hashes': MODEL_HASHES, 'engine_sha256': engine_hash,
              'inference_scale': 4, 'host_scale': host_scale, 'tile': 128, 'threads': '1:1:1',
              'inference_recipe': inference_recipe,
              'color_space': 'srgb-declared-by-review', 'mip_filter': 'linear-light-lanczos-v1',
              'encoder': 'Pillow-' + pillow_version}
    key = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()[:24]
    output = work.path('textures/prepared/' + key); manifest = output / 'manifest.json'
    if manifest.is_file():
        try:
            current = json.loads(manifest.read_text(encoding='utf8'))
            if current.get('recipe') != recipe:
                raise ValueError('recipe changed')
            validate_prepared_pack(output, cancel=cancel)
        except (OSError, ValueError, AttributeError, PortError) as exc:
            if isinstance(exc, PortError) and exc.code == 'CANCELLED':
                raise
            raise PortError('HD_CACHE_CHANGED', 'O cache HD foi alterado; preservado para inspeção: ' + str(output)) from exc
        emit({'stage': 'hd', 'message': 'Textura HD já preparada e verificada; reutilizando cache.', 'state': 'completed'})
        return output
    output.mkdir(parents=True, exist_ok=True)
    if any(path.is_symlink() for path in output.iterdir()):
        raise PortError('HD_CACHE_CHANGED', 'O cache HD contém links; preservado para inspeção.')
    master, receipt = _master_inference(source, original, inference_recipe, root, work,
                                         engine, models, env, cancel, emit)
    # Each prepared pack is independently portable and hash-verifiable. The
    # shared master remains separate from these preset-specific products.
    enhanced, inference = output / 'enhanced-x4.png', output / 'inference.json'
    shutil.copyfile(master, enhanced)
    shutil.copyfile(receipt, inference)
    if sha(enhanced, cancel) != json.loads(inference.read_text(encoding='utf8'))['sha256']:
        raise PortError('HD_CACHE_CHANGED', 'Master IA alterado durante a cópia; cache preservado.')
    with Image.open(enhanced) as result_image:
        if result_image.size != (original.width * 4, original.height * 4):
            raise PortError('HD_SIZE', 'O modelo não gerou a resolução solicitada.')
        result_image.load()
        master_image = result_image.convert('RGB')
        preview = linear_resize(master_image, (original.width * 2, original.height * 2), cancel)
        host = preview if host_scale == 2 else master_image
    preview.save(output / 'enhanced-x2.png')
    dds = encode_mip_dds(host, fmt, cancel, emit); (output / 'texture.dds').write_bytes(dds)
    index = f'ASTERHD1 {fmt} {original.width} {original.height} {bc_id} {xxhash.xxh3_128_hexdigest(dds)} reviewed-color-opaque\n'
    (output / 'texture.index').write_text(index, encoding='ascii')
    record = {'recipe': recipe, 'review': 'operator-reviewed-color-opaque', 'source_xex_sha256': source_data.get('game_xex_sha256'),
              'source_inspection': str(Path(inspection).resolve()), 'runtime_rendered': False,
              'dimensions': list(host.size), 'mip_count': max(host.size).bit_length(),
              'files': {n: sha(output / n, cancel) for n in ['texture.dds', 'texture.index', 'enhanced-x2.png', 'enhanced-x4.png', 'inference.json']}}
    _atomic_json(manifest, record)
    validate_prepared_pack(output, cancel=cancel)
    emit({'stage': 'hd', 'message': f'Textura HD preparada ({host_scale}x); carregamento no renderer ainda exige validação.', 'state': 'completed'})
    return output


def validate_prepared_pack(directory, cancel=None):
    """Check a locally prepared pack before handing its directory to the GPU."""
    import xxhash
    cancel = cancel or Cancellation()
    cancel.check()
    path = Path(directory).expanduser().resolve(strict=True)
    try:
        manifest = path / 'manifest.json'
        if manifest.is_symlink() or manifest.stat().st_size > 65536:
            raise ValueError('manifest too large')
        data = json.loads(manifest.read_text(encoding='utf8'))
        required = {'texture.dds', 'texture.index', 'enhanced-x2.png', 'enhanced-x4.png', 'inference.json'}
        files = data['files']
        if (set(files) != required or data['review'] != 'operator-reviewed-color-opaque' or
                type(data['recipe']['host_scale']) is not int or data['recipe']['host_scale'] not in (2, 4) or data['recipe'].get('schema', 1) not in (1, 2) or data['recipe']['model_hashes'] != MODEL_HASHES):
            raise ValueError('unsupported pack recipe')
        for name, digest in files.items():
            file = path / name
            limit = 65536 if name == 'inference.json' else 512 if name == 'texture.index' else 128 * 1024**2 if name == 'texture.dds' else 256 * 1024**2
            if file.is_symlink() or not file.is_file() or file.stat().st_size > limit or sha(file, cancel) != digest:
                raise ValueError('pack contents changed or exceeds size limit')
        parts = (path / 'texture.index').read_text(encoding='ascii').split()
        cancel.check()
        raw = (path / 'texture.dds').read_bytes()
        if (len(parts) != 7 or parts[0] != 'ASTERHD1' or parts[6] != 'reviewed-color-opaque' or
                parts[4] != data['recipe']['original_bc'] or parts[5] != xxhash.xxh3_128_hexdigest(raw)):
            raise ValueError('index mismatch')
        fmt, width, height = map(int, parts[1:4])
        if (fmt not in (18, 20) or not 64 <= width <= 2048 or not 64 <= height <= 2048 or
                width & (width - 1) or height & (height - 1)):
            raise ValueError('unsupported source geometry')
        scale = data['recipe']['host_scale']
        if data['recipe'].get('schema', 1) == 1 and scale != 2:
            raise ValueError('legacy recipe cannot use 4x')
        if (len(raw) < 128 or len(raw) > 128 * 1024**2 or raw[:4] != b'DDS ' or
                struct.unpack_from('<I', raw, 4)[0] != 124 or
                struct.unpack_from('<II', raw, 12) != (height * scale, width * scale) or
                struct.unpack_from('<II', raw, 76) != (32, 4) or
                struct.unpack_from('<I', raw, 112)[0] != 0 or
                raw[84:88] != (b'DXT1' if fmt == 18 else b'DXT5')):
            raise ValueError('invalid DDS header')
        mips = max(width * scale, height * scale).bit_length()
        size = sum(((max(1, width * scale >> i) + 3) // 4) *
                   ((max(1, height * scale >> i) + 3) // 4) * (8 if fmt == 18 else 16) for i in range(mips))
        if struct.unpack_from('<I', raw, 28)[0] != mips or len(raw) != 128 + size:
            raise ValueError('incomplete mip chain')
        if data.get('dimensions') != [width * scale, height * scale] or data.get('mip_count') != mips:
            raise ValueError('manifest geometry mismatch')
        receipt = json.loads((path / 'inference.json').read_text(encoding='utf8'))
        expected_inference = data['recipe'].get('inference_recipe', data['recipe'])
        if receipt.get('recipe') != expected_inference or receipt.get('sha256') != sha(path / 'enhanced-x4.png', cancel):
            raise ValueError('inference receipt mismatch')
        from PIL import Image
        for name, factor in [('enhanced-x2.png', 2), ('enhanced-x4.png', 4)]:
            with Image.open(path / name) as image:
                if image.size != (width * factor, height * factor):
                    raise ValueError('preview geometry mismatch')
                image.verify()
        if data['recipe'].get('schema') == 2:
            if (receipt.get('schema') != 1 or receipt.get('dimensions') != [width * 4, height * 4] or
                    expected_inference.get('original') != data['recipe']['original'] or
                    expected_inference.get('model_hashes') != MODEL_HASHES or
                    expected_inference.get('engine_sha256') != data['recipe']['engine_sha256']):
                raise ValueError('master inference identity mismatch')
        return path
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise PortError('HD_PACK', 'Pacote HD local inválido ou alterado: ' + str(exc)) from exc
