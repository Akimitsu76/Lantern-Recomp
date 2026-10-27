"""Install bundled public resources in persistent user storage for single files."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
import zipfile

from .locking import lock_session


def user_data_root():
    override = os.environ.get('ASTER_DATA_HOME')
    if override:
        return Path(override).expanduser().resolve()
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'AsterNative'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'aster-native'


def install_payload(archive, destination):
    """Update only packaged resources, preserving builds, preferences and saves."""
    archive, destination = Path(archive), Path(destination)
    fingerprint = hashlib.sha256(archive.read_bytes()).hexdigest()
    destination.mkdir(parents=True, exist_ok=True)
    descriptor = lock_session(destination / '.resources.lock')
    try:
        marker = destination / '.resources.json'
        if marker.is_file():
            try:
                previous = json.loads(marker.read_text(encoding='utf8'))
                if (previous.get('sha256') == fingerprint and
                        (destination / 'games/green_lantern_rex_hints.toml').is_file() and
                        (destination / 'scripts/play_green_lantern.py').is_file()):
                    return destination
            except (OSError, ValueError, AttributeError):
                pass
        with zipfile.ZipFile(archive) as package:
            members = package.infolist()
            if sum(item.file_size for item in members) > 512 * 1024**2:
                raise ValueError('Payload excede o tamanho permitido.')
            for item in members:
                path = PurePosixPath(item.filename.replace('\\', '/'))
                if (path.is_absolute() or '..' in path.parts or ':' in str(path)
                        or '.aster' in path.parts or stat.S_ISLNK(item.external_attr >> 16)
                        or not (destination / str(path)).resolve().is_relative_to(destination.resolve())):
                    raise ValueError('Caminho inseguro no payload: ' + item.filename)
            for item in members:
                if item.is_dir():
                    continue
                target = destination / item.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                content = package.read(item)
                if not target.is_file() or target.read_bytes() != content:
                    fd, temporary = tempfile.mkstemp(dir=target.parent, prefix='.resource-')
                    try:
                        with os.fdopen(fd, 'wb') as output:
                            output.write(content)
                        os.replace(temporary, target)
                    finally:
                        Path(temporary).unlink(missing_ok=True)
                if item.external_attr >> 16 & stat.S_IXUSR:
                    target.chmod(0o755)
        fd, temporary = tempfile.mkstemp(dir=destination, prefix='.resource-')
        try:
            with os.fdopen(fd, 'w') as output:
                json.dump({'sha256': fingerprint}, output)
            os.replace(temporary, marker)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return destination
    finally:
        os.close(descriptor)
