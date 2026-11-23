"""Headless play entry point shared by the portable launcher and the CLI.

RecompLauncher starts the packaged executable with ``--play <game folder>``.
The game folder is passed straight to the existing play script: no config file
is edited, no window is opened by this dispatcher and no game content is
bundled with the launcher.
"""
from pathlib import Path
import runpy
import sys

PLAY_SCRIPT = 'scripts/play_green_lantern.py'


def play_script(root):
    """Resolve the only script allowed to run through this entry point."""
    script = (Path(root) / PLAY_SCRIPT).resolve()
    if not script.is_file():
        raise SystemExit('Script de jogo ausente; extraia o pacote completo antes de jogar.')
    return script


def dispatch(root, argv):
    """Run ``argv`` as ``--play <game folder> [play-script options]``.

    ``argv`` is the real ``sys.argv``: ``argv[0]`` is the executable and
    ``argv[1]`` must be ``--play``. The remaining arguments are forwarded
    unchanged to ``scripts/play_green_lantern.py``.
    """
    if len(argv) < 3 or argv[1] != '--play' or not argv[2] or argv[2].startswith('-'):
        raise SystemExit('Uso: AsterNative --play <pasta com default.xex> [opções do jogo]')
    script = play_script(root)
    forwarded = [str(script), *argv[2:]]
    sys.argv = forwarded
    runpy.run_path(str(script), run_name='__main__')
    return 0
