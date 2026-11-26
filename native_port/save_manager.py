"""Importação e exportação do save do usuário em um pacote ``.zip``.

O save real continua em ``.aster/runtime/green-lantern/user``. Exportar apenas
lê essa pasta. Importar sempre cria um backup da pasta atual antes de extrair
o pacote escolhido, e rejeita caminhos que tentem sair do diretório de destino.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import tempfile
import zipfile

from .errors import PortError

PROFILE = Path('.aster/runtime/green-lantern/user')
MAX_PACKAGE_BYTES = 512 * 1024 * 1024


def profile_dir(root: Path | str) -> Path:
    return Path(root).expanduser() / PROFILE


def default_export_name(now: datetime | None = None) -> str:
    moment = now or datetime.now()
    return f'green-lantern-save-{moment.strftime("%Y%m%d-%H%M")}.zip'


def export_save(root: Path | str, destination: Path | str) -> dict:
    source = profile_dir(root)
    if not source.is_dir():
        raise PortError('SAVE_MISSING', 'Ainda não há save deste usuário para exportar.')
    destination = Path(destination).expanduser()
    if destination.is_dir():
        destination = destination / default_export_name()
    if destination.suffix.lower() != '.zip':
        destination = destination.with_suffix('.zip')
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = 0
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as package:
        for path in sorted(source.rglob('*')):
            if path.is_file():
                package.write(path, path.relative_to(source).as_posix())
                files += 1
    if not files:
        destination.unlink(missing_ok=True)
        raise PortError('SAVE_EMPTY', 'A pasta de save existe, mas não contém arquivos.')
    return {'path': str(destination), 'files': files}


def _validated_members(package: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = package.infolist()
    total = sum(member.file_size for member in members)
    if total > MAX_PACKAGE_BYTES:
        raise PortError('SAVE_PACKAGE', 'Pacote de save excede 512 MiB.')
    for member in members:
        name = member.filename.replace('\\', '/')
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or not name.strip('/'):
            raise PortError('SAVE_PACKAGE', f'Caminho inseguro no pacote: {member.filename}')
    return members


def import_save(root: Path | str, source: Path | str) -> dict:
    source = Path(source).expanduser()
    if not source.is_file():
        raise PortError('SAVE_PACKAGE', 'Pacote de save não encontrado.')
    try:
        package = zipfile.ZipFile(source)
    except (OSError, zipfile.BadZipFile) as exc:
        raise PortError('SAVE_PACKAGE', f'Pacote de save inválido: {exc}') from exc
    with package:
        members = _validated_members(package)
        if not members:
            raise PortError('SAVE_PACKAGE', 'O pacote de save está vazio.')
        destination = profile_dir(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        backup = None
        if destination.exists():
            backup = destination.with_name(
                destination.name + '.before-import-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
            shutil.move(str(destination), str(backup))
        staging = Path(tempfile.mkdtemp(prefix='save-import-', dir=str(destination.parent)))
        try:
            package.extractall(staging)
            staging.replace(destination)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            if backup is not None and backup.exists() and not destination.exists():
                shutil.move(str(backup), str(destination))
            raise
    return {'path': str(destination), 'files': len(members),
            'backup': str(backup) if backup else None}
