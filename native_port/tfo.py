"""Conservative research candidates from the corroborated Xbox 360 TFO profile.

Fields were compared with complete captured base bytes for 145 resources. Width,
height, BC format and mip count have direct corroborated fields; row pitch and
base extent are calculations matching that observed profile. Endian and tiled
mode have no independently identified header encoding. This scanner intentionally
returns neither field and never approves a texture for replacement.
"""
from __future__ import annotations

import hashlib
import mmap
from pathlib import Path
import stat
import struct

from .errors import PortError
from .tasks import Cancellation

HEADER_BYTES = 148
MAX_DECODED_BYTES = 1024**3
MAX_NAME_BYTES = 512
MAX_NAME_MARKERS = 200000
MAX_DESCRIPTORS = 16384
_SCAN_CHUNK = 1024**2
_MARKER = b'.tfo\0'
_ALLOWED_FAMILIES = {'materials', 'objects', 'actors', 'textures'}
_EXCLUDED_SEGMENTS = {'interface', 'ui', 'hud', 'menu', 'menus', 'effects', 'fx', 'vfx', 'particles'}
_VARIABLE_RANGES = ((8, 12), (16, 18), (28, 32), (64, 72))
_TEMPLATE = bytearray(HEADER_BYTES)
for _offset, _value in ((4, 1), (20, 4), (24, 2), (36, 1), (40, 2),
                        (44, 4), (52, 0x00030000), (60, 30)):
    struct.pack_into('>I', _TEMPLATE, _offset, _value)
struct.pack_into('>HH', _TEMPLATE, 12, 1, 1)
_TEMPLATE = bytes(_TEMPLATE)
LAYOUT_SIGNATURE = 'tfo-v1-bc-' + hashlib.sha256(_TEMPLATE).hexdigest()


def _error(message):
    return PortError('TFO', message)


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _decode_header(header, name):
    """Accept one exact observed constant layout, not a generic TFO variant."""
    if len(header) != HEADER_BYTES:
        return None
    masked = bytearray(header)
    for start, end in _VARIABLE_RANGES:
        masked[start:end] = bytes(end - start)
    # Includes the observed color/spec layout code00030000. The normal-map
    # candidate code00020300 and every unknown constant variant are rejected.
    if masked != _TEMPLATE:
        return None
    if (not name.startswith('\\gl\\') or '/' in name or ':' in name or
            any(part in ('', '.', '..') for part in name[1:].split('\\'))):
        return None
    parts = name[1:].lower().split('\\')
    if (len(parts) < 3 or parts[0] != 'gl' or parts[1] not in _ALLOWED_FAMILIES or
            any(part in _EXCLUDED_SEGMENTS for part in parts[1:-1]) or
            not parts[-1].endswith('_d.tfo')):
        return None
    width, height = struct.unpack_from('>HH', header, 8)
    width_copy, height_copy = struct.unpack_from('>II', header, 64)
    mip_count = struct.unpack_from('>H', header, 16)[0]
    engine_format = struct.unpack_from('>I', header, 28)[0]
    if (width != width_copy or height != height_copy or
            not 64 <= width <= 2048 or not 64 <= height <= 2048 or
            width & (width - 1) or height & (height - 1) or
            mip_count <= 1 or mip_count != max(width, height).bit_length() or
            engine_format not in (1, 5)):
        return None
    format_value = 18 if engine_format == 1 else 20
    block_bytes = 8 if format_value == 18 else 16
    pitch = ((width + 127) // 128) * 32 * block_bytes
    base_bytes = ((width + 127) // 128) * ((height + 127) // 128) * 32 * 32 * block_bytes
    return {'name': name, 'width': width, 'height': height, 'format': format_value,
            'mip_count': mip_count, 'derived_row_pitch_bytes': pitch,
            'raw_size': base_bytes, 'layout_signature': LAYOUT_SIGNATURE,
            'candidate_kind': 'diffuse-suffix-d', 'reviewed': False,
            'approved_for_runtime': False,
            'layout_inference': 'Base extent/pitch follow the captured BC profile; no independent endian or tiled field decoded.'}


def iter_texture_descriptors(decoded_path, cancel=None):
    """Yield bounded, unapproved diffuse candidates; never extract or modify data.

    Only lowercase ``.tfo`` markers from the observed serializer are scanned.
    Names are printable ASCII absolute resource paths, not filesystem paths.
    The immediately preceding148 bytes must match the exact corroborated constant
    layout and duplicate dimensions. Base bytes are bounded by the decoded file.
    No following padding, mip offsets, payload ownership or nested-resource index
    membership is inferred. Caller must pin the original/decoded file hashes and
    independently review material purpose and opacity before using candidates.
    """
    cancel = cancel or Cancellation()
    cancel.check()
    path = Path(decoded_path).expanduser().absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise _error('Links não são aceitos na pesquisa de texturas TFO.')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not 0 <= info.st_size <= MAX_DECODED_BYTES:
        raise _error('Contêiner TFO deve ser um arquivo regular de até 1 GiB.')
    original = _identity(info)
    if info.st_size < HEADER_BYTES + len(_MARKER):
        return
    with path.open('rb') as stream:
        if _identity(path.stat()) != original:
            raise _error('O contêiner mudou antes da pesquisa TFO.')
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
            cursor = 0
            markers = 0
            emitted = 0
            while cursor < info.st_size:
                cancel.check()
                end = min(info.st_size, cursor + _SCAN_CHUNK)
                scan_end = min(info.st_size, end + len(_MARKER) - 1)
                found = data.find(_MARKER, cursor, scan_end)
                while found >= 0 and found < end:
                    cancel.check()
                    markers += 1
                    if markers > MAX_NAME_MARKERS:
                        raise _error('Marcadores TFO excedem o limite de pesquisa por contêiner.')
                    name_end = found + len(_MARKER) - 1
                    # Last preceding NUL is safe here because the corroborated
                    # header ends with76 zero bytes; do not use nearest strings.
                    previous_nul = data.rfind(b'\0', max(0, name_end - MAX_NAME_BYTES - 1), found)
                    name_start = previous_nul + 1
                    header_offset = name_start - HEADER_BYTES
                    if previous_nul >= 0 and header_offset >= 0 and name_end - name_start <= MAX_NAME_BYTES:
                        raw_name = data[name_start:name_end]
                        if raw_name and all(32 <= byte < 127 for byte in raw_name):
                            header = data[header_offset:name_start]
                            parsed = _decode_header(header, raw_name.decode('ascii'))
                            if parsed is not None:
                                raw_offset = name_end + 1
                                if parsed['raw_size'] <= info.st_size - raw_offset:
                                    emitted += 1
                                    if emitted > MAX_DESCRIPTORS:
                                        raise _error('Descritores TFO excedem o limite por contêiner.')
                                    yield {**parsed, 'offset': header_offset, 'raw_offset': raw_offset,
                                           'header_sha256': hashlib.sha256(header).hexdigest(),
                                           'header_hex': header.hex()}
                                    cancel.check()
                                    if _identity(path.stat()) != original:
                                        raise _error('O contêiner mudou durante a pesquisa TFO.')
                    found = data.find(_MARKER, found + len(_MARKER), scan_end)
                cursor = end
                if _identity(path.stat()) != original:
                    raise _error('O contêiner mudou durante a pesquisa TFO.')
        if _identity(path.stat()) != original:
            raise _error('O contêiner mudou durante a pesquisa TFO.')
