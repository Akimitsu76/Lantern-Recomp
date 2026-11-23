"""Headless entry points shared by the portable launcher and the CLI.

RecompLauncher starts the packaged executable with ``--prepare-game <copy>``
on its setup screen and ``--play <copy> [options]`` on Play. A player's copy
may be an extracted folder or an Xbox 360 ISO: ISOs are extracted once into
the launcher's own data root, never into the release. No window is opened by
this dispatcher and no game content is bundled with the launcher.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import runpy
import sys

from .errors import PortError
from . import xdvdfs_extract

PLAY_SCRIPT = 'scripts/play_green_lantern.py'
GAME_ID = 'green-lantern'
# Mirrors scripts/play_green_lantern.py; tests assert the two stay in step.
EXPECTED_XEX = '3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1'


def play_script(root):
    """Resolve the only script allowed to run through this entry point."""
    script = (Path(root) / PLAY_SCRIPT).resolve()
    if not script.is_file():
        raise SystemExit('Script de jogo ausente; extraia o pacote completo antes de jogar.')
    return script


def game_files_folder(root):
    """Persistent extraction folder, inside the launcher's own app data."""
    return Path(root) / '.aster' / 'game-files' / GAME_ID


def _is_verified(folder):
    xex = Path(folder) / 'default.xex'
    if not xex.is_file():
        return False
    try:
        return hashlib.sha256(xex.read_bytes()).hexdigest() == EXPECTED_XEX
    except OSError:
        return False


def prepare_game(root, source, *, emit=None):
    """Validate the player's copy; extract an ISO when needed. Return its folder."""
    emit = emit if emit is not None else (lambda line: None)
    try:
        source = Path(source).expanduser().resolve(strict=True)
    except OSError as exc:
        raise SystemExit(f'Cópia do jogo não encontrada: {exc}')
    if source.is_dir():
        if not _is_verified(source):
            raise SystemExit('A pasta selecionada não contém o default.xex usado por esta compilação.')
        emit('progress 1.0 Cópia verificada')
        return source
    if not source.is_file():
        raise SystemExit('Informe uma imagem .iso ou uma pasta com default.xex.')
    destination = game_files_folder(root)
    if not _is_verified(destination):
        try:
            xdvdfs_extract.extract(source, destination, emit=emit)
        except PortError as exc:
            raise SystemExit(f'Não foi possível extrair a imagem: {exc}')
        emit('progress 0.90 Verificando o default.xex extraído')
    if not _is_verified(destination):
        raise SystemExit('A imagem não contém o default.xex usado por esta compilação.')
    emit('progress 1.0 Jogo pronto')
    return destination


def resolve_game(root, source, *, emit=None):
    """Turn a player's copy into a folder the play script can open."""
    path = Path(source).expanduser()
    if not path.exists():
        # Let the play script report the missing path with its own clear message.
        return path
    if path.is_dir():
        return path
    return prepare_game(root, path, emit=emit)


def dispatch(root, argv):
    """Run ``argv`` as ``--play <copy> [play-script options]``."""
    if len(argv) < 3 or argv[1] != '--play' or not argv[2] or argv[2].startswith('-'):
        raise SystemExit('Uso: AsterNative --play <iso ou pasta com default.xex> [opções do jogo]')
    script = play_script(root)
    game = resolve_game(root, argv[2], emit=print)
    forwarded = [str(script), str(game), *argv[3:]]
    sys.argv = forwarded
    runpy.run_path(str(script), run_name='__main__')
    return 0


def prepare_dispatch(root, argv):
    """Run ``argv`` as ``--prepare-game <iso|pasta>`` for the launcher setup screen."""
    if len(argv) < 3 or argv[1] != '--prepare-game' or not argv[2] or argv[2].startswith('-'):
        raise SystemExit('Uso: AsterNative --prepare-game <imagem .iso ou pasta com default.xex>')
    folder = prepare_game(root, argv[2], emit=lambda line: print(line, flush=True))
    print(f'Jogo preparado em {folder}', flush=True)
    return 0
