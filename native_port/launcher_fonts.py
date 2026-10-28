"""Register bundled launcher fonts privately, before creating the Tk window.

No font files are copied into a user/system font directory, no registry keys
are written and no font-change broadcast is sent. Missing assets/platform APIs
are a cosmetic fallback, never a reason to prevent opening the launcher.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
from pathlib import Path
import sys
import threading

FONT_FILES = ('DejaVuSans.ttf', 'DejaVuSans-Bold.ttf', 'DejaVuSansCondensed-Bold.ttf')
BODY_FAMILY = 'DejaVu Sans'
DISPLAY_FAMILY = 'DejaVu Sans Condensed'
_lock = threading.Lock()
_result = None
_backend = None  # Keep the library loaded for the lifetime of private fonts.


def _font_paths():
    directory = Path(__file__).resolve().parent / 'resources/fonts'
    if directory.is_symlink() or directory.parent.is_symlink():
        return ()
    paths = []
    for name in FONT_FILES:
        path = directory / name
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 5 * 1024**2:
            return ()
        # TrueType sfnt header; malformed/unsupported files retain system fonts.
        with path.open('rb') as source:
            if source.read(4) != b'\0\x01\0\0':
                return ()
        paths.append(path)
    return tuple(paths)


def _register_linux(paths):
    global _backend
    library = ctypes.CDLL(ctypes.util.find_library('fontconfig') or 'libfontconfig.so.1')
    current = library.FcConfigGetCurrent
    current.argtypes = []
    current.restype = ctypes.c_void_p
    add = library.FcConfigAppFontAddFile
    add.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    add.restype = ctypes.c_int
    config = current()
    if not config:
        return False
    _backend = library
    # App fonts are part of this process's FcConfig, not a font installation.
    # Never clear the config: other in-process components may own app fonts.
    return all(add(config, os.fsencode(path)) != 0 for path in paths)


def _register_windows(paths):
    global _backend
    library = ctypes.WinDLL('gdi32', use_last_error=True)
    add = library.AddFontResourceExW
    add.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p]
    add.restype = ctypes.c_int
    _backend = library
    # FR_PRIVATE keeps enumeration usable by Tk within this process. FR_NOT_ENUM
    # would prevent even the calling process from enumerating these families.
    return all(add(str(path), 0x10, None) > 0 for path in paths)


def load_fonts():
    """Return True if all bundled faces registered; otherwise use system fallback.

    Call before Tk() or before requesting named fonts. Repeated calls, including
    from different threads, do not register again. A failed attempt is also
    remembered; restart after repairing missing/corrupt bundled assets. Partial
    success remains private to this process and never removes another owner's
    registered fonts. Process termination releases all registrations.
    """
    global _result
    with _lock:
        if _result is not None:
            return _result
        try:
            paths = _font_paths()
            if len(paths) != len(FONT_FILES):
                _result = False
            elif os.name == 'nt':
                _result = _register_windows(paths)
            elif sys.platform.startswith('linux'):
                _result = _register_linux(paths)
            else:
                _result = False
        except (OSError, ValueError, AttributeError, TypeError):
            _result = False
        return _result
