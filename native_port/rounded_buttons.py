"""Botões ttk com cantos arredondados, gerados sem assets externos.

O tema ``clam`` desenha botões retangulares. Para manter a API dos
``ttk.Button`` intacta (estados, ``invoke``, estilos nomeados), geramos PNGs
em memória e usamos ``element_create`` para substituir o elemento de fundo
pelo estilo arredondado. Nenhum widget precisa ser substituído.
"""
from __future__ import annotations

import base64
import math
import struct
import tkinter as tk
from tkinter import ttk
import zlib

from .portal_theme import mix, shade

# As fotos precisam viver enquanto a aplicação existir; senão o Tk libera a
# imagem e a borda do botão desaparece.
_IMAGES: list[tk.PhotoImage] = []


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (struct.pack('>I', len(data)) + kind + data
            + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))


def _png(width: int, height: int,
         rows: list[list[tuple[int, int, int, int]]]) -> bytes:
    raw = bytearray()
    for row in rows:
        raw.append(0)  # filtro PNG "none"
        for red, green, blue, alpha in row:
            raw += bytes((red, green, blue, alpha))
    header = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', header)
            + _chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + _chunk(b'IEND', b''))


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip('#')
    if len(value) == 8:
        value = value[:6]
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _coverage(px: float, py: float, width: int, height: int, radius: float) -> float:
    """Cobertura aproximada de um retângulo de cantos arredondados."""
    cx = min(max(px, radius), width - radius)
    cy = min(max(py, radius), height - radius)
    distance = math.hypot(px - cx, py - cy) - radius
    return max(0.0, min(1.0, .5 - distance))


def button_png(fill: str, outline: str, *, width: int = 48, height: int = 32,
               radius: int = 12) -> str:
    """Retorna uma PNG RGBA em base64 com borda arredondada e antialias."""
    fill_rgb, outline_rgb = _rgb(fill), _rgb(outline)
    radius = max(2, min(int(radius), width // 2, height // 2))
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            px, py = x + .5, y + .5
            outer = _coverage(px, py, width, height, radius)
            if outer <= 0:
                row.append((0, 0, 0, 0))
                continue
            inner = _coverage(px, py, width, height, max(.5, radius - 1.25))
            if inner <= 0:
                rgb = outline_rgb
            elif inner >= 1:
                rgb = fill_rgb
            else:
                rgb = tuple(out + (inside - out) * inner
                            for out, inside in zip(outline_rgb, fill_rgb))
            row.append(tuple(int(channel) for channel in rgb) + (int(255 * outer),))
        rows.append(row)
    return base64.b64encode(_png(width, height, rows)).decode('ascii')


def button_photo(master, fill: str, outline: str, *, width: int = 48,
                 height: int = 32, radius: int = 12) -> tk.PhotoImage:
    """Foto de borda arredondada para botões ``tk.Button`` (navegação)."""
    return tk.PhotoImage(master=master, format='png',
                         data=button_png(fill, outline, width=max(8, int(width)),
                                         height=max(8, int(height)),
                                         radius=max(2, int(radius))))


def _install_style(style: ttk.Style, name: str, fill: str, outline: str,
                   active: str, disabled: str):
    photos = [tk.PhotoImage(master=style.master, data=button_png(color, outline),
                            format='png')
              for color in (fill, active, disabled)]
    _IMAGES.extend(photos)
    element = f'{name.replace(".", "_")}_round'
    style.element_create(element, 'image', photos[0],
                         ('active', photos[1]), ('disabled', photos[2]),
                         border=(10, 10), sticky='nsew')
    # Sobrescreve o fundo retangular do clam com o elemento de imagem arredondada.
    style.layout(name, [
        (element, {'sticky': 'nsew', 'children': [
            ('Button.padding', {'sticky': 'nsew', 'children': [
                ('Button.label', {'sticky': 'nsew'}),
            ]}),
        ]}),
    ])


def install_rounded_buttons(style, theme):
    """Aplica borda arredondada a todos os estilos de botão usados no launcher."""
    global _IMAGES
    _IMAGES = []
    t = theme
    bg, surface, panel = t.bg, t.surface, t.surface
    card_alt, ink, accent = t.surface_2, t.ink, t.accent

    specs = (
        ('TButton', card_alt, mix(bg, accent, .26), shade(card_alt, .10),
         mix(bg, card_alt, .55)),
        ('Accent.TButton', accent, shade(accent, .24), shade(accent, .15),
         mix(bg, accent, .26)),
        ('Secondary.TButton', card_alt, mix(bg, accent, .34), shade(card_alt, .14),
         mix(bg, card_alt, .55)),
        ('Ghost.TButton', panel, mix(bg, accent, .18), mix(bg, accent, .12),
         mix(bg, panel, .45)),
        ('Danger.TButton', mix(bg, t.danger, .22), mix(bg, t.danger, .45),
         mix(bg, t.danger, .34), mix(bg, t.danger, .11)),
        ('Preset.TButton', card_alt, mix(bg, accent, .22), shade(card_alt, .10),
         mix(bg, card_alt, .55)),
        ('PresetOn.TButton', mix(bg, accent, .22), mix(bg, accent, .55),
         mix(bg, accent, .34), mix(bg, accent, .10)),
    )
    for name, fill, outline, active, disabled in specs:
        _install_style(style, name, fill, outline, active, disabled)
        # O ttk desenha o ``background`` do estilo como um retângulo por trás do
        # elemento de imagem, cobrindo os cantos transparentes. Limpar o
        # background faz com que apenas a imagem arredondada seja visível.
        style.configure(name, background='')
        style.map(name, background=[], foreground=[])
    return len(_IMAGES)
