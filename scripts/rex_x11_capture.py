"""Bounded client-image fallback for one PID-verified X11 window."""
import ctypes as C
from pathlib import Path
import re
import subprocess
import threading

_LOCK = threading.Lock()


class _XImage(C.Structure):
    _fields_ = [(name, C.c_int) for name in ('width', 'height', 'xoffset', 'format')]
    _fields_ += [('data', C.c_void_p)]
    _fields_ += [(name, C.c_int) for name in ('byte_order', 'bitmap_unit', 'bitmap_bit_order',
                                             'bitmap_pad', 'depth', 'bytes_per_line', 'bits_per_pixel')]
    _fields_ += [(name, C.c_ulong) for name in ('red_mask', 'green_mask', 'blue_mask')]
    _fields_ += [('obdata', C.c_void_p)]


def _verify_pid(pid, window_id):
    result = subprocess.run(['xprop', '-id', window_id, '_NET_WM_PID'], capture_output=True,
                            text=True, timeout=2)
    match = re.search(r'=\s*(\d+)\s*$', result.stdout)
    if result.returncode or not match or int(match[1]) != pid:
        raise ValueError('Selected window does not belong to the requested PID.')
    return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]


def capture_verified_x11_window(pid, window_id, output):
    """Read only the selected client drawable; never select root or change focus.

    The image excludes compositor decorations. Unsupported pixel layouts and
    windows that close during capture fail explicitly; there is no screen fallback.
    """
    from PIL import Image
    if type(pid) is not int or pid <= 0 or re.fullmatch(r'0x[0-9a-fA-F]+', window_id) is None:
        raise ValueError('Expected a process PID and explicit X11 window ID.')
    before = _verify_pid(pid, window_id)
    x = C.CDLL('libX11.so.6')
    x.XOpenDisplay.argtypes, x.XOpenDisplay.restype = [C.c_char_p], C.c_void_p
    x.XCloseDisplay.argtypes = [C.c_void_p]
    x.XGetGeometry.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong),
                              C.POINTER(C.c_int), C.POINTER(C.c_int),
                              C.POINTER(C.c_uint), C.POINTER(C.c_uint),
                              C.POINTER(C.c_uint), C.POINTER(C.c_uint)]
    x.XGetImage.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_int,
                           C.c_uint, C.c_uint, C.c_ulong, C.c_int]
    x.XGetImage.restype = C.POINTER(_XImage)
    x.XDestroyImage.argtypes = [C.POINTER(_XImage)]
    x.XSync.argtypes = [C.c_void_p, C.c_int]
    x.XSetErrorHandler.argtypes, x.XSetErrorHandler.restype = [C.c_void_p], C.c_void_p
    # Xlib's error handler is process-wide. Serialize our temporary handler and
    # restore it after synchronizing this private display connection.
    with _LOCK:
        display = x.XOpenDisplay(None)
        if not display:
            raise ValueError('Cannot open X11 display for selected-window capture.')
        errors = []
        callback = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p)(lambda *_: errors.append(True) or 0)
        previous = x.XSetErrorHandler(C.cast(callback, C.c_void_p))
        image = None
        try:
            root, left, top = C.c_ulong(), C.c_int(), C.c_int()
            width, height, border, depth = (C.c_uint() for _ in range(4))
            if not x.XGetGeometry(display, int(window_id, 16), C.byref(root), C.byref(left), C.byref(top),
                                  C.byref(width), C.byref(height), C.byref(border), C.byref(depth)):
                raise ValueError('Selected window geometry is unavailable.')
            w, h = width.value, height.value
            if not 1 <= w <= 8192 or not 1 <= h <= 8192 or w * h * 4 > 64 << 20:
                raise ValueError('Selected window exceeds the capture size limit.')
            image = x.XGetImage(display, int(window_id, 16), 0, 0, w, h, C.c_ulong(-1).value, 2)
            x.XSync(display, 0)
            if errors or not image:
                raise ValueError('Selected client image is unavailable; no screen capture attempted.')
            info = image.contents
            if ((info.width, info.height) != (w, h) or not info.data or
                    info.bits_per_pixel not in (24, 32) or info.byte_order not in (0, 1) or
                    (info.red_mask, info.green_mask, info.blue_mask) != (0xff0000, 0xff00, 0xff) or
                    not w * (info.bits_per_pixel // 8) <= info.bytes_per_line <= 8192 * 4 or
                    info.bytes_per_line * h > 64 << 20):
                raise ValueError('Unsupported selected-window pixel layout.')
            mode = {24: ('BGR', 'RGB'), 32: ('BGRX', 'XRGB')}[info.bits_per_pixel][info.byte_order]
            pixels = C.string_at(info.data, info.bytes_per_line * h)
            result = Image.frombytes('RGB', (w, h), pixels, 'raw', mode, info.bytes_per_line, 1)
        finally:
            if image:
                x.XDestroyImage(image)
            x.XSync(display, 0)
            x.XSetErrorHandler(previous)
            x.XCloseDisplay(display)
    if _verify_pid(pid, window_id) != before:
        raise ValueError('Selected window process changed during capture.')
    output = Path(output)
    result.save(output, format='PNG')
    return {'pid': pid, 'window_id': window_id, 'path': str(output),
            'capture_method': 'x11-client-image', 'width': w, 'height': h}
