"""Bounded decoding of corroborated v1 XCTD BE16-framed LZX containers.

Only window17/128KiB compressed slots and packed20/32 output-size tables are
supported. The upper flag byte and container checksum remain uninterpreted.
Production callers must pin source SHA256; exploratory callers must explicitly
opt into research mode. Decoded bytes are not automatically textures.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from .errors import PortError
from .tasks import Cancellation, run_process

MAX_INPUT_BYTES = 512 * 1024**2
MAX_OUTPUT_BYTES = 1024**3
MAX_SEGMENTS = 4096
MAX_SEGMENT_OUTPUT_BYTES = 256 * 1024**2
SLOT_BYTES = 128 * 1024
_HEX64 = re.compile(r'[0-9a-f]{64}\Z')
_PREFIX = bytes.fromhex('0ff512ed01000000')


def _error(message):
    return PortError('XCTD', message)


def _no_links(path):
    path = Path(path).expanduser().absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise _error('Links não são aceitos nos caminhos XCTD.')
    return path


def _identity(path):
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise _error('A origem XCTD deve ser um arquivo regular.')
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _digest(path, cancel):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        while True:
            cancel.check()
            block = stream.read(1024**2)
            if not block:
                return value.hexdigest()
            value.update(block)


def _expected_hash(value, label):
    if value is not None and (not isinstance(value, str) or not _HEX64.fullmatch(value)):
        raise _error('SHA256 esperado inválido: ' + label)


def _read_plan(stream, input_size):
    header = stream.read(16)
    if len(header) != 16 or header[:8] != _PREFIX:
        raise _error('Header XCTD não suportado; exige versão 1 big endian.')
    flags = int.from_bytes(header[12:16], 'big')
    # These fields are independently corroborated against real containers. The
    # high byte remains opaque; it is reported, never treated as an integrity bit.
    if flags & 0x3f != 0x22:
        raise _error('Janela ou tamanho dos blocos XCTD não suportado.')
    selector = (flags >> 22) & 3
    if selector not in (0, 1):
        raise _error('Tabela de tamanhos XCTD não suportada.')
    bits = (20, 32)[selector]
    count = (flags & 0x003fffff) >> 6
    if not 1 <= count <= MAX_SEGMENTS or (input_size + SLOT_BYTES - 1) // SLOT_BYTES != count:
        raise _error('Quantidade de segmentos XCTD inválida para o tamanho da origem.')
    table_bytes = ((count * bits + 31) // 32) * 4
    if 16 + table_bytes >= min(SLOT_BYTES, input_size):
        raise _error('Tabela XCTD fora do primeiro bloco.')
    table_raw = stream.read(table_bytes)
    if len(table_raw) != table_bytes:
        raise _error('Tabela XCTD truncada.')
    table = int.from_bytes(table_raw, 'big')
    padding_bits = table_bytes * 8 - count * bits
    if padding_bits and table & ((1 << padding_bits) - 1):
        raise _error('Padding da tabela XCTD deve ser zero.')
    sizes = [(table >> (table_bytes * 8 - (i + 1) * bits)) & ((1 << bits) - 1)
             for i in range(count)]
    if any(not 1 <= value <= MAX_SEGMENT_OUTPUT_BYTES for value in sizes):
        raise _error('Tamanho de saída por segmento XCTD inválido ou excessivo.')
    if sum(sizes) > MAX_OUTPUT_BYTES:
        raise _error('Saída XCTD excede o limite de 1 GiB.')
    return {'flags': flags, 'count': count, 'bits': bits, 'sizes': sizes,
            'first_payload': 16 + table_bytes, 'output_bytes': sum(sizes),
            'checksum_field_hex': header[8:12].hex()}


def _framed_payload(block):
    cursor = 0
    chunks = 0
    while cursor < len(block):
        remaining = len(block) - cursor
        if remaining < 2:
            if any(block[cursor:]):
                raise _error('Último tamanho BE16 de segmento XCTD está truncado.')
            break
        length = int.from_bytes(block[cursor:cursor + 2], 'big')
        if not length:
            if any(block[cursor:]):
                raise _error('Dados não nulos após o terminador do segmento XCTD.')
            break
        if length > remaining - 2:
            raise _error('Chunk LZX excede o limite do segmento XCTD.')
        cursor += 2 + length
        chunks += 1
    if not chunks:
        raise _error('Segmento XCTD sem chunks LZX.')
    return block[:cursor], len(block) - cursor, chunks


def decode_container(source, output, helper, cancel=None, emit=None,
                     expected_source_sha256=None, expected_output_sha256=None, *,
                     allow_unverified_source=False):
    """Decode supported observed slots to an exclusively published output file.

    The helper must be the trusted compiled ``xctd_decode.c`` executable. No shell
    is involved. Uninterpreted upper flags are permitted only for a source whose
    SHA256 is pinned by the caller, or with explicit research opt-in. A trusted
    SHA pins bytes, not the meaning of unknown flags or an unverified checksum.
    Cancellation removes only the private temporary directory created by this
    invocation. Existing output paths, including symlinks, are never replaced.
    Atomic publication uses a same-filesystem hard link; unsupported filesystems
    fail safely rather than falling back to an overwriting rename.
    """
    cancel = cancel or Cancellation()
    emit = emit or (lambda event: None)
    cancel.check()
    _expected_hash(expected_source_sha256, 'origem')
    _expected_hash(expected_output_sha256, 'saída')
    if expected_source_sha256 is None and allow_unverified_source is not True:
        raise _error('A decodificação exige SHA256 original fixado ou opção explícita de pesquisa.')
    source, output, helper = map(_no_links, (source, output, helper))
    if not output.parent.is_dir() or os.path.lexists(output):
        raise _error('A pasta de saída deve existir e o arquivo de saída deve ser novo.')
    if not helper.is_file():
        raise _error('Decodificador LZX confiável não encontrado.')
    identity = _identity(source)
    if not 20 < identity[2] <= MAX_INPUT_BYTES:
        raise _error('A origem XCTD deve ter até 512 MiB e conter payload.')
    emit({'stage': 'xctd-source', 'message': 'Verificando o contêiner original.',
          'completed': 0, 'total': identity[2]})
    source_hash = _digest(source, cancel)
    if expected_source_sha256 is not None and source_hash != expected_source_sha256:
        raise _error('SHA256 do contêiner original não corresponde ao esperado.')
    if _identity(source) != identity:
        raise _error('O contêiner original mudou durante a verificação.')
    with source.open('rb') as stream:
        plan = _read_plan(stream, identity[2])
        digest = hashlib.sha256()
        completed = 0
        segments = []
        with tempfile.TemporaryDirectory(prefix='.aster-xctd-', dir=output.parent) as temporary:
            temporary = Path(temporary)
            aggregate = temporary / 'aggregate.decoded'
            with aggregate.open('xb') as destination:
                for index, size in enumerate(plan['sizes']):
                    cancel.check()
                    start = plan['first_payload'] if index == 0 else index * SLOT_BYTES
                    end = min(identity[2], (index + 1) * SLOT_BYTES)
                    if not 0 <= start < end <= identity[2]:
                        raise _error('Intervalo de segmento XCTD fora da origem.')
                    stream.seek(start)
                    block = stream.read(end - start)
                    if len(block) != end - start:
                        raise _error('A origem XCTD foi truncada durante a leitura.')
                    payload, zero_padding, chunks = _framed_payload(block)
                    framed, decoded = temporary / 'segment.framed', temporary / 'segment.decoded'
                    framed.write_bytes(payload)
                    result = run_process([str(helper), str(framed), str(decoded),
                                          '--payload-offset', '0', '--uncompressed-size',
                                          str(size), '--window-bits', '17'],
                                         temporary, cancel, timeout=120)
                    cancel.check()
                    try:
                        event = json.loads(result['stdout'])
                    except (ValueError, TypeError) as error:
                        raise _error('Resultado inválido do decodificador LZX.') from error
                    if (not isinstance(event, dict) or event.get('profile') != 'explicit-be16-framed-lzx' or
                            event.get('output_bytes') != size or event.get('chunks') != chunks or
                            event.get('input_bytes') != len(payload) or
                            event.get('window_bits') != 17 or event.get('reset_interval') != 0 or
                            decoded.is_symlink() or not decoded.is_file() or decoded.stat().st_size != size):
                        raise _error('Saída LZX não corresponde ao plano validado.')
                    with decoded.open('rb') as part:
                        remaining = size
                        while remaining:
                            cancel.check()
                            data = part.read(min(1024**2, remaining))
                            if not data:
                                raise _error('Saída LZX truncada durante a leitura.')
                            destination.write(data)
                            digest.update(data)
                            remaining -= len(data)
                        if part.read(1):
                            raise _error('Saída LZX aumentou durante a leitura.')
                    decoded.unlink()
                    completed += size
                    segments.append({'index': index, 'source_start': start, 'source_end': end,
                                     'output_bytes': size, 'chunks': chunks,
                                     'zero_padding_bytes': zero_padding})
                    emit({'stage': 'xctd-decode', 'message': f'Decodificando segmento {index + 1}/{plan["count"]}.',
                          'completed': completed, 'total': plan['output_bytes'],
                          'segment': index + 1, 'segments': plan['count']})
                destination.flush()
                os.fsync(destination.fileno())
            output_hash = digest.hexdigest()
            if completed != plan['output_bytes']:
                raise _error('Quantidade total de bytes XCTD decodificados incorreta.')
            if expected_output_sha256 is not None and output_hash != expected_output_sha256:
                raise _error('SHA256 do conteúdo decodificado não corresponde ao esperado.')
            cancel.check()
            if _no_links(source) != source or _identity(source) != identity or _digest(source, cancel) != source_hash:
                raise _error('O contêiner original mudou durante a decodificação.')
            cancel.check()
            try:
                os.link(aggregate, output, follow_symlinks=False)
            except OSError as error:
                raise _error('Não foi possível publicar atomicamente a saída sem substituir arquivos: ' + str(error)) from error
    return {'schema': 1, 'profile': 'observed-xctd-v1-window17-slots128k',
            'source': str(source), 'output': str(output), 'source_sha256': source_hash,
            'output_sha256': output_hash, 'input_bytes': identity[2],
            'output_bytes': completed, 'segment_count': plan['count'],
            'size_table_bits': plan['bits'], 'flags_hex': f'{plan["flags"]:08x}',
            'uninterpreted_upper_flags_hex': f'{plan["flags"] & 0xff000000:08x}',
            'container_checksum_field_hex': plan['checksum_field_hex'],
            'container_checksum_verified': False, 'source_unchanged': True,
            'source_sha256_pinned': expected_source_sha256 is not None,
            'research_opt_in': allow_unverified_source is True, 'segments': segments}
