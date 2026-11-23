"""Bounded, read-only XDVDFS extraction for the RecompLauncher setup step.

The launcher checks the player's disc image and then calls ``--prepare-game``.
Only regular files and directories are created, always under the launcher's
own data root: game content is never written into the release and updates can
never overwrite it. Names, nesting, file sizes and totals are capped, and
symlinks or parent/absolute paths are refused.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import struct

from .errors import PortError
from .sources import SECTOR, inspect_iso, read_at, source_path
from .tasks import Cancellation

MAX_DEPTH = 32
MAX_FILES = 100000
MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024
MAX_TABLE_BYTES = 64 * 1024 * 1024
MAX_NAME_BYTES = 255
MAX_PATH_BYTES = 1024
# Windows forbids these in file names; refusing them here keeps one extracted
# tree usable on every system the launcher supports.
BAD_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


class _Budget:
    def __init__(self, cancel=None, emit=None):
        self.cancel = cancel or Cancellation()
        self.emit = emit if emit is not None else (lambda line: None)
        self.files = 0
        self.bytes = 0


def _name(raw):
    """Decode one XDVDFS name (Windows-1252) and validate it as a path part."""
    if not raw or len(raw) > MAX_NAME_BYTES:
        raise PortError('BAD_XDVDFS_NAME', 'Nome de arquivo XDVDFS inválido.')
    text = raw.decode('cp1252', errors='replace')
    if text in ('.', '..') or BAD_NAME.search(text) or text != text.strip(' .\t'):
        raise PortError('BAD_XDVDFS_NAME', 'Nome de arquivo XDVDFS não aceito.',
                        name=repr(text))
    return text


def _dirents(f, base, sector, size, total, budget, visited, depth):
    """Return ``(name, sector, size, is_directory)`` for every entry of a table."""
    if depth > MAX_DEPTH:
        raise PortError('XDVDFS_LIMIT', 'Diretório XDVDFS excede o limite de profundidade.')
    key = (sector, size)
    if key in visited:
        raise PortError('BAD_XDVDFS', 'Loop detectado na árvore de diretórios XDVDFS.')
    visited.add(key)
    if not size or size > MAX_TABLE_BYTES:
        raise PortError('XDVDFS_LIMIT', 'Tabela de diretório XDVDFS inválida ou grande demais.',
                        size=size)
    start = base + sector * SECTOR
    if start < base or start + size > total:
        raise PortError('TRUNCATED', 'Tabela de diretório XDVDFS fora da imagem.',
                        offset=start, size=size)

    pending, seen, entries = [0], set(), []
    while pending:
        budget.cancel.check()
        offset = pending.pop()
        if offset in seen:
            continue
        seen.add(offset)
        if offset % 4 or offset + 14 > size:
            raise PortError('BAD_XDVDFS', 'Entrada XDVDFS desalinhada ou fora da tabela.',
                            offset=offset)
        header = read_at(f, start + offset, 14, total)
        if header == b'\xff' * 14 or header == b'\x00' * 14:
            continue
        left, right = struct.unpack_from('<HH', header, 0)
        file_sector, file_size = struct.unpack_from('<II', header, 4)
        attributes, name_length = header[12], header[13]
        if not name_length or name_length > MAX_NAME_BYTES or offset + 14 + name_length > size:
            raise PortError('BAD_XDVDFS', 'Nome de entrada XDVDFS fora da tabela.',
                            offset=offset, size=name_length)
        name = _name(read_at(f, start + offset + 14, name_length, total))
        for pointer in (left, right):
            if pointer in (0, 0xffff):
                continue
            child = pointer * 4
            if child + 14 > size:
                raise PortError('BAD_XDVDFS', 'Ponteiro XDVDFS fora da tabela.', pointer=pointer)
            pending.append(child)
        entries.append((name, file_sector, file_size, bool(attributes & 0x10)))
    if len(entries) + budget.files > MAX_FILES:
        raise PortError('XDVDFS_LIMIT', 'Imagem contém arquivos demais.')
    return entries


def _extract_directory(f, base, sector, size, total, destination, prefix,
                       budget, visited, depth):
    for name, file_sector, file_size, is_directory in _dirents(
            f, base, sector, size, total, budget, visited, depth):
        budget.cancel.check()
        rel = f'{prefix}/{name}' if prefix else name
        if len(rel.encode('utf8')) > MAX_PATH_BYTES:
            raise PortError('XDVDFS_LIMIT', 'Caminho XDVDFS longo demais.', path=rel)
        target = destination.joinpath(*rel.split('/'))
        if not target.resolve().is_relative_to(destination.resolve()) or target.is_symlink():
            raise PortError('BAD_XDVDFS_NAME', 'Entrada XDVDFS tenta sair da pasta de extração.',
                            path=rel)
        if is_directory:
            target.mkdir(parents=True, exist_ok=True)
            _extract_directory(f, base, file_sector, file_size, total, destination, rel,
                               budget, visited, depth + 1)
            continue
        if budget.files >= MAX_FILES or file_size > MAX_FILE_BYTES:
            raise PortError('XDVDFS_LIMIT', 'Arquivo ou quantidade de arquivos excede o limite.',
                            path=rel, size=file_size)
        if budget.bytes + file_size > MAX_TOTAL_BYTES:
            raise PortError('XDVDFS_LIMIT', 'Extração excede o limite total de dados.',
                            path=rel, size=file_size)
        start = base + file_sector * SECTOR
        if start < base or start + file_size > total:
            raise PortError('TRUNCATED', 'Arquivo XDVDFS fora da imagem.',
                            offset=start, size=file_size)
        target.parent.mkdir(parents=True, exist_ok=True)
        f.seek(start)
        remaining = file_size
        with target.open('wb') as out:
            while remaining:
                wanted = min(1024 * 1024, remaining)
                chunk = f.read(wanted)
                if len(chunk) != wanted:
                    raise PortError('TRUNCATED', 'Arquivo XDVDFS incompleto.', path=rel)
                out.write(chunk)
                budget.bytes += len(chunk)
                remaining -= len(chunk)
                budget.cancel.check()
        budget.files += 1


def extract(source, destination, *, cancel=None, emit=None):
    """Extract a whole XDVDFS image into ``destination``; return a small report."""
    path = source_path(source)
    budget = _Budget(cancel, emit)
    with path.open('rb') as f:
        before = os.fstat(f.fileno())
        info = inspect_iso(f, before.st_size)
        base = info['partition_offset']
        root_sector = (info['root_offset'] - base) // SECTOR
        destination = Path(destination).resolve()
        if destination.exists() and not destination.is_dir():
            raise PortError('DESTINATION', 'A pasta de extração não é um diretório.',
                            path=str(destination))
        destination.mkdir(parents=True, exist_ok=True)
        budget.emit('progress 0.10 Lendo o sistema de arquivos do disco')
        _extract_directory(f, base, root_sector, info['root_size'], before.st_size,
                           destination, '', budget, visited=set(), depth=0)
        budget.emit(f'progress 0.85 Extraindo arquivos ({budget.files})')
        after = os.fstat(f.fileno())
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise PortError('SOURCE_CHANGED', 'A imagem mudou durante a extração.')
    return {'source': str(path), 'destination': str(destination),
            'files': budget.files, 'bytes': budget.bytes}
