"""External receipts for previously verified, immutable texture artifacts.

Hits compare filesystem metadata, not file hashes. This detects ordinary edits,
replacement and directory membership changes; it is not authentication against a
writer able to forge both the files and this user's receipt. Full validators stay
available and are run whenever a snapshot differs. Nothing is stored in a dump,
texture library or save directory.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

from .errors import PortError
from .tasks import Cancellation

MAX_RECEIPT_BYTES = 32 * 1024**2
MAX_SNAPSHOT_ENTRIES = 100000
MAX_DEPTH = 32
RECEIPT_VERSION = 1


def _safe_stat(path):
    info = path.lstat()
    # Windows junctions and other reparse points must not evade the symlink
    # guard (Path.is_symlink alone does not cover junctions on all Python builds).
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise PortError('HD_VALIDATION_LINK', 'Links não são aceitos na verificação HD: ' + str(path))
    if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
        raise PortError('HD_VALIDATION_FILE', 'Entrada HD não é arquivo ou diretório regular: ' + str(path))
    return info


def safe_path(value, *, allow_missing=False):
    """Use lexical absolute paths so resolving cannot hide a linked ancestor."""
    path = Path(os.path.abspath(Path(value).expanduser()))
    for parent in reversed((path, *path.parents)):
        try: _safe_stat(parent)
        except FileNotFoundError:
            if allow_missing: break
            raise
    return path


def _make_directory(path):
    for part in reversed((path, *path.parents)):
        try:
            info = _safe_stat(part)
        except FileNotFoundError:
            try: part.mkdir()
            except FileExistsError: pass
            info = _safe_stat(part)
        if not stat.S_ISDIR(info.st_mode):
            raise PortError('HD_VALIDATION_PATH', 'O cache de verificação não é um diretório.')


def snapshot(roots, cancel=None):
    """Bounded, deterministic metadata inventory; never follow links."""
    cancel = cancel or Cancellation()
    result = []
    for root in sorted({str(Path(p).absolute()) for p in roots}):
        cancel.check()
        path = safe_path(root)
        pending = [(path, 0)]
        while pending:
            cancel.check()
            member, depth = pending.pop()
            if depth > MAX_DEPTH or len(result) >= MAX_SNAPSHOT_ENTRIES:
                raise PortError('HD_VALIDATION_LIMIT', 'Inventário HD excede os limites de verificação.')
            info = _safe_stat(member)
            result.append([str(member), 'd' if stat.S_ISDIR(info.st_mode) else 'f',
                           info.st_dev, info.st_ino, info.st_size,
                           info.st_mtime_ns, info.st_ctime_ns])
            if stat.S_ISDIR(info.st_mode):
                with os.scandir(member) as children:
                    names = []
                    for child in children:
                        if len(names) >= MAX_SNAPSHOT_ENTRIES - len(result):
                            raise PortError('HD_VALIDATION_LIMIT', 'Diretório HD excede os limites de verificação.')
                        names.append(child.name)
                pending.extend((member / name, depth + 1) for name in sorted(names, reverse=True))
    return result


class ValidationReceipt:
    def __init__(self, directory, identity, cancel=None):
        self.directory = Path(directory).absolute()
        self.identity = identity
        self.cancel = cancel or Cancellation()
        encoded = json.dumps(identity, sort_keys=True, separators=(',', ':')).encode('utf8')
        self.path = self.directory / (hashlib.sha256(encoded).hexdigest() + '.json')

    def read(self):
        self.cancel.check()
        try:
            path = safe_path(self.path)
            if path.stat().st_size > MAX_RECEIPT_BYTES:
                return None
            with path.open('rb') as source:
                payload = source.read(MAX_RECEIPT_BYTES + 1)
            if len(payload) > MAX_RECEIPT_BYTES:
                return None
            data = json.loads(payload)
            if (not isinstance(data, dict) or data.get('schema') != RECEIPT_VERSION or
                    data.get('identity') != self.identity or not isinstance(data.get('snapshot'), list)):
                return None
            return data
        except (OSError, ValueError, TypeError, PortError) as exc:
            if isinstance(exc, PortError) and exc.code == 'CANCELLED':
                raise
            return None

    def matches(self, data, roots):
        try:
            return data['snapshot'] == snapshot(roots, self.cancel)
        except (OSError, KeyError, ValueError, PortError) as exc:
            if isinstance(exc, PortError) and exc.code == 'CANCELLED':
                raise
            return False

    def publish(self, result, roots, validate):
        """Publish only after a complete validator between stable snapshots.

        A concurrent edit fails this invocation rather than blessing a mixed
        validation. Failure never deletes texture data or publishes a receipt.
        """
        # Reject before creating anything inside a texture artifact.
        if any(self.directory.is_relative_to(Path(root)) for root in roots):
            raise PortError('HD_VALIDATION_PATH', 'O recibo deve ficar fora dos arquivos HD verificados.')
        before = snapshot(roots, self.cancel)
        validate()
        after = snapshot(roots, self.cancel)
        if before != after:
            raise PortError('HD_VALIDATION_CHANGED', 'Arquivos HD mudaram durante a verificação; tente novamente.')
        data = {'schema': RECEIPT_VERSION, 'identity': self.identity,
                'snapshot': after, 'result': result}
        payload = (json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode('utf8')
        if len(payload) > MAX_RECEIPT_BYTES:
            return False  # Oversized inventories retain the full-validation path.
        _make_directory(self.directory)
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix='.validation-', dir=self.directory)
            with os.fdopen(fd, 'wb') as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            self.cancel.check()
            os.replace(temporary, self.path)
            temporary = None
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
        return True
