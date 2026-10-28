"""Entry point for Linux/Windows portable executables (no game content)."""
import argparse
import ctypes
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import runpy
import ssl
import subprocess
import sys
import tempfile
import threading
import tkinter
from tkinter import ttk, filedialog, messagebox
import tomllib
import urllib.request
import zipfile


def main():
    root = (Path(sys.executable).resolve().parent / 'app' if getattr(sys, 'frozen', False)
            else Path(__file__).resolve().parents[2])
    if os.name == 'nt':
        # Windowed PyInstaller sets Python streams to None. Reconnect inherited
        # pipes for workers/CLI, otherwise discard output without console windows.
        import msvcrt
        for name, identifier in [('stdout', -11), ('stderr', -12)]:
            if getattr(sys, name) is None:
                ctypes.windll.kernel32.GetStdHandle.restype = ctypes.c_void_p
                handle = ctypes.windll.kernel32.GetStdHandle(identifier)
                try:
                    if not handle or handle == ctypes.c_void_p(-1).value:
                        raise OSError('no inherited stream')
                    fd = msvcrt.open_osfhandle(handle, os.O_WRONLY)
                    stream = os.fdopen(fd, 'w', encoding='utf8', closefd=False)
                except OSError:
                    stream = open(os.devnull, 'w')
                setattr(sys, name, stream)
    # The copied helper must not install its older payload over the current app.
    if len(sys.argv) == 3 and sys.argv[1] == '--aster-apply-update':
        from native_port.launcher_update import apply_update
        return apply_update(sys.argv[2])
    if getattr(sys, 'frozen', False):
        payload = Path(sys._MEIPASS) / 'aster-payload.zip'
        if payload.is_file():
            from native_port.portable import install_payload, user_data_root
            root = install_payload(payload, user_data_root() / 'app')
            os.environ['ASTER_LAUNCHER_ROOT'] = str(root)
    if not (root / 'games/green_lantern_rex_hints.toml').is_file():
        raise SystemExit('Extraia o pacote completo antes de abrir o launcher; a pasta app está ausente.')
    sys.path.insert(0, str(root))
    if len(sys.argv) > 1 and sys.argv[1] == '--aster-script':
        script = Path(sys.argv[2]).resolve()
        if script != root / 'scripts/play_green_lantern.py':
            raise SystemExit('Worker não permitido.')
        sys.argv = [str(script), *sys.argv[3:]]
        runpy.run_path(str(script), run_name='__main__')
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == '--smoke-test':
        from native_port.launcher import Launcher
        from native_port import __version__
        from native_port.launcher_fonts import load_fonts, BODY_FAMILY
        from tkinter import font
        fonts_registered = load_fonts()
        window = tkinter.Tk()
        # Do not call close(): smoke tests must not save launcher preferences.
        app = Launcher(window)
        window.update()
        # Let the debounced artwork paint too: constructing widgets alone misses
        # frozen-runtime font and Pillow/Tk failures.
        window.after(180, window.quit)
        window.mainloop()
        small = font.Font(root=window, family=BODY_FAMILY, size=10)
        large = font.Font(root=window, family=BODY_FAMILY, size=30)
        small_width = small.measure('Green Lantern')
        large_width = large.measure('Green Lantern')
        scalable_fonts = large_width > small_width * 2
        result = {'platform': platform.system(), 'python': platform.python_version(),
                  'version': __version__, 'updates_tab': str(app.tabs.tab(app.update_tab, 'text')),
                  'tk': tkinter.TkVersion, 'gui_created': True, 'project': str(root),
                  'build_button': str(app.compile_button['text']),
                  'fonts_registered': fonts_registered,
                  'font_family': large.actual('family'),
                  'font_widths': [small_width, large_width],
                  'scalable_fonts': scalable_fonts,
                  'hero_image_ready': app.hero._image is not None,
                  'hero_image_error': app.hero.image_error,
                  'game_launched': False}
        app.closed = True
        window.after_cancel(app.after_id)
        app.footer_progress.stop()
        app.progress.stop()
        window.destroy()
        print(json.dumps(result))
        return 0 if scalable_fonts and result['hero_image_ready'] else 1
    if len(sys.argv) == 1:
        sys.argv.append('gui')
    from native_port.__main__ import main as application
    return application()


if __name__ == '__main__':
    raise SystemExit(main())
