"""Arte procedural do Portal dos Recomps. Nenhum asset do jogo é incluído.

O mesmo desenho serve para qualquer recomp: o ``PortalTheme`` define o glyph,
o motivo do portal, a paleta e os textos. O hero continua sendo um
``tk.Canvas`` com altura fixa, tag ``hero-status`` e ``set_status()``, para
permanecer compatível com o shell existente.
"""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import font as tkfont

from .portal_theme import PortalTheme, mix, shade
from .portal_widgets import rounded_rect


class LanternHero(tk.Canvas):
    """Banner temático com portal animado e hierarquia tipográfica limpa."""

    def __init__(self, parent, theme: PortalTheme | None = None, **kwargs):
        self.theme = (theme or PortalTheme()).validate()
        super().__init__(parent, background=self.theme.bg, highlightthickness=0,
                         height=310, **kwargs)
        self._image = None
        self.image_error = None
        self._pending = None
        self._reveal = None
        self._orbit = None
        self._orbit_items = []
        self._spin_items = []
        self._motes = []
        self._field_size = (1, 1)
        self._reveal_colors = []
        self._status = 'SEU DUMP. SEU PROGRESSO. SEU PC.'
        self._mission = {'dump': ('AGUARDANDO', 'off'),
                         'port': ('NÃO GERADO', 'off'),
                         'session': ('0MIN', 'off')}
        self._session_ticks = 0
        self._session_label_item = None
        self.bind('<Configure>', self._resize)
        self.bind('<Destroy>', self._destroy, add='+')

    def _destroy(self, event):
        if event.widget is not self:
            return
        for name in ('_pending', '_reveal', '_orbit'):
            pending = getattr(self, name)
            if pending:
                self.after_cancel(pending)
                setattr(self, name, None)

    def _resize(self, _):
        if self._pending:
            self.after_cancel(self._pending)
        self._pending = self.after(60, self._paint)

    def set_status(self, value):
        self._status = value
        self.itemconfigure('hero-status', text=value)

    def set_import_state(self, label: str):
        """Atualiza o texto de importação exibido ao lado do botão JOGAR."""
        if self._session_label_item is not None:
            self.itemconfigure(self._session_label_item, text=label)

    def set_session_seconds(self, seconds: int | None):
        """Atualiza o temporizador da sessão atual no hero."""
        if seconds is None:
            self._session_ticks = 0
        else:
            self._session_ticks = max(0, int(seconds))
        if self._session_label_item is None:
            width, height = self._field_size
            left = max(26, int(width * .028))
            top = max(18, int(height * .07))
            y = top + 96 + 48
            self._session_label_item = self.create_text(
                left, y, anchor='nw', tags='reveal',
                text='SESSION 00MIN', fill=self.theme.muted,
                font=self._font(9))
        minutes = self._session_ticks // 60
        self.itemconfigure(self._session_label_item,
                           text=f'SESSION {minutes:02d}MIN')

    def set_mission(self, key: str, label: str, state: str):
        """Atualiza um marcador de missão do hero."""
        if key in self._mission:
            self._mission[key] = (label, state)
        self._update_mission_markers()

    def _font(self, size: int, weight: str = 'bold') -> tuple:
        """Fonte do hero com fallback seguro para o ambiente X11 disponível."""
        available = set(tkfont.families())
        family = self.theme.font if self.theme.font in available else 'fixed'
        return (family, max(8, int(size)), weight)

    # ---------------------------------------------------------------- pintura
    def _paint(self):
        self._pending = None
        if not self.winfo_exists():
            return
        width, height = max(1, self.winfo_width()), max(1, self.winfo_height())
        self.delete('all')
        self._orbit_items, self._spin_items, self._motes = [], [], []
        self._reveal_colors = []
        self._field_size = (width, height)
        self.image_error = None
        self._paint_glow(width, height)
        self._paint_energy_field(width, height)
        geometry = self._paint_portal(width, height)
        self._paint_text(width, height, geometry)
        self._build_accent_column(width, height)
        self._build_terminal_lines(width, height)
        self._build_playback_frame(width, height)
        self._update_mission_markers()
        self._start_reveal()

    def _paint_glow(self, width, height):
        """Halo suave gerado com Pillow quando disponível; vetorial no fallback."""
        t = self.theme
        cx, cy, radius = int(width * .80), int(height * .48), int(height * .33)
        try:
            from PIL import Image, ImageDraw, ImageFilter, ImageTk
            base = Image.new('RGB', (width, height), t.bg)
            glow = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(glow)
            accent = t.accent.lstrip('#')
            rgb = tuple(int(accent[i:i + 2], 16) for i in (0, 2, 4))
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                         outline=rgb + (150,), width=11)
            draw.line((cx - radius * .8, cy + radius * .55, cx + radius * .8, cy + radius * .55),
                      fill=rgb + (100,), width=6)
            blurred = glow.filter(ImageFilter.GaussianBlur(26))
            base = Image.alpha_composite(base.convert('RGBA'), blurred).convert('RGB')
            self._image = ImageTk.PhotoImage(base, master=self)
            self.create_image(0, 0, image=self._image, anchor='nw')
        except (ImportError, OSError, tk.TclError) as error:
            self._image = None
            self.image_error = f'{type(error).__name__}: {error}'
            for factor, alpha in ((1.5, .07), (1.2, .10), (1.0, .14)):
                r = radius * factor
                color = mix(t.bg, t.accent, alpha)
                self.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=18)

    def _paint_energy_field(self, width, height):
        """Energia do anel no fundo: arcos, feixes e partículas em movimento."""
        t = self.theme
        cx, cy = width * .78, height * .48
        for index, (factor, alpha, start, extent) in enumerate((
                (1.05, .10, 18, 118), (1.28, .07, 168, 96),
                (1.52, .045, 78, 74), (1.86, .025, 240, 54))):
            radius = min(height * .46, width * .34) * factor
            item = self.create_arc(cx - radius, cy - radius, cx + radius, cy + radius,
                                   style='arc', start=start, extent=extent,
                                   outline=mix(t.bg, t.accent, alpha), width=1)
            self._spin_items.append((item, start + index * 11))
        for offset, alpha in ((-.26, .16), (.18, .10), (.34, .06)):
            self.create_line(0, height * (.5 + offset), width, height * (.5 + offset - .22),
                             fill=mix(t.bg, t.accent_2, alpha), width=1, smooth=True,
                             splinesteps=32)
        # Motes determinísticos: a animação não depende de random nem de assets.
        for index in range(18):
            radius = 1 + index % 3
            x = (index * 97 + 37) % max(2, width)
            y = (index * 61 + 23) % max(2, height)
            item = self.create_oval(x - radius, y - radius, x + radius, y + radius,
                                    fill=mix(t.bg, t.accent_2, .22 + (index % 4) * .12),
                                    outline='')
            self._motes.append([item, float(x), float(y), .28 + (index % 5) * .12,
                                radius, index * .7])

    def _paint_portal(self, width, height):
        t = self.theme
        cx, cy = width * .80, height * .48
        base = min(height * .34, width * .21)
        for factor, alpha in ((1.75, .06), (1.42, .10), (1.12, .18), (.86, .10)):
            r = base * factor
            self.create_oval(cx - r, cy - r, cx + r, cy + r,
                             outline=mix(t.bg, t.accent, alpha), width=1)
        # Arco principal: três arcos abertos, em vez de um círculo fechado.
        for start, extent, alpha, line in ((205, 130, .85, 3), (25, 130, .55, 2), (110, 34, .38, 1)):
            r = base * .74
            self.create_arc(cx - r, cy - r, cx + r, cy + r, style='arc',
                            start=start, extent=extent,
                            outline=mix(t.bg, t.accent, alpha), width=line)
        # Núcleo e partículas em órbita.
        self.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill=shade(t.accent, .45), outline='')
        self.create_oval(cx - 11, cy - 11, cx + 11, cy + 11,
                         outline=mix(t.bg, t.accent, .55), width=1)
        for index in range(7):
            dot = self.create_oval(cx - 2, cy - 2, cx + 2, cy + 2,
                                   fill=mix(t.bg, t.accent_2, .35 + (index % 3) * .2), outline='')
            self._orbit_items.append((dot, index * (360 / 7)))
        self._start_orbit(cx, cy, base)
        return cx, cy, base

    def _start_orbit(self, cx, cy, base):
        if self._orbit:
            self.after_cancel(self._orbit)
        phase = [0.0]

        def tick():
            if not self.winfo_exists() or not self._orbit_items:
                return
            phase[0] = (phase[0] + 0.9) % 360.0
            for item, base_start in self._spin_items:
                self.itemconfigure(item, start=base_start + phase[0] * .12)
            for item, offset in self._orbit_items:
                angle = math.radians(phase[0] + offset)
                radius = base * (.82 + .07 * math.sin(angle * 2))
                x = cx + math.cos(angle) * radius
                y = cy + math.sin(angle) * radius * .72
                self.coords(item, x - 2, y - 2, x + 2, y + 2)
            width, height = self._field_size
            for mote in self._motes:
                item, x, y, speed, radius, offset = mote
                y -= speed
                x += math.sin(math.radians(phase[0] * 1.7 + offset)) * .45
                if y < -4:
                    y = height + 4
                    x = (x + 83) % max(2, width)
                elif x < -4:
                    x = width + 4
                elif x > width + 4:
                    x = -4
                mote[1], mote[2] = x, y
                self.coords(item, x - radius, y - radius, x + radius, y + radius)
            self._orbit = self.after(70, tick)

        self._orbit = self.after(70, tick)

    def _paint_text(self, width, height, geometry):
        t = self.theme
        left = max(26, int(width * .028))
        top = max(18, int(height * .07))
        portal_x = geometry[0]
        small = ('DejaVu Sans', 9, 'bold')
        display = ('DejaVu Sans Condensed', max(34, min(62, int(height * .18))), 'bold')

        def record(item, color, attr='fill'):
            self._reveal_colors.append((item, color, attr))
            return item

        def decorate(items, color=None):
            for item in items:
                self.addtag_withtag('reveal', item)
                attr = 'fill' if self.itemcget(item, 'fill') not in ('', None) else 'outline'
                record(item, color or self.itemcget(item, attr), attr)

        eyebrow = record(self.create_text(left, top, anchor='nw', tags='reveal',
                                          text=f'XBOX 360 → PC  ·  {t.edition.upper()}',
                                          fill=t.muted, font=small), t.muted)

        title_x = left + 70
        record(self.create_text(title_x, top + 20, anchor='nw', tags='reveal',
                                text=t.game.upper(), fill=t.ink, font=display), t.ink)
        record(self.create_text(title_x + 2, top + 20 + display[1] * 1.05, anchor='nw',
                                tags='reveal', text=t.subtitle.upper(), fill=t.accent,
                                font=('DejaVu Sans', max(10, display[1] // 4), 'bold')), t.accent)

        # Uma curva suave substitui a régua reta: menos "caixa", mesma leitura.
        rule_y = top + 20 + display[1] * 1.05 + 34
        rule_color = mix(t.bg, t.accent, .28)
        rule = self.create_line(left, rule_y, left + (portal_x - left) * .46, rule_y + 7,
                                min(width - 40, left + 520), rule_y, tags='reveal',
                                fill=rule_color, width=1, smooth=True, splinesteps=24)
        record(rule, rule_color)
        record(self.create_text(left, rule_y + 14, anchor='nw', tags='reveal',
                                text=t.tagline, fill=t.muted, font=('DejaVu Sans', 10)), t.muted)

        badge_color = mix(t.bg, t.accent, .42)
        badge = rounded_rect(self, width - 118, height - 52, width - 28, height - 20, 16,
                             fill=mix(t.bg, t.accent_2, .12), outline=badge_color)
        decorate(badge, badge_color)
        record(self.create_text(width - 73, height - 36, anchor='center', tags='reveal',
                                text=t.edition.upper(), fill=t.accent_2, font=small), t.accent_2)

        record(self.create_text(left, height - 25, anchor='w', tags=('hero-status', 'reveal'),
                                text=self._status, fill=t.muted, font=('DejaVu Sans', 9)), t.muted)

    def _build_accent_column(self, width, height):
        """Coluna fina de acento à direita do hero, como painel de controle."""
        t = self.theme
        cx = width - 24
        for index, offset in enumerate((-44, -18, 8, 34, 60)):
            item = self.create_arc(cx - 12 + offset, height - 120 + index * 24,
                                   cx + 12 + offset, height - 104 + index * 24,
                                   style='arc', start=45, extent=270,
                                   outline=mix(t.bg, t.accent, .22 + index * .08), width=2)
            self.addtag_withtag('reveal', item)
            self._reveal_colors.append((item, mix(t.bg, t.accent, .22 + index * .08), 'outline'))

    def _build_terminal_lines(self, width, height):
        """Linhas de terminal acima do portal, simulando leitura do save."""
        t = self.theme
        left = max(26, int(width * .028))
        top = max(18, int(height * .07))
        y = top + 8
        for text in ('DISCO 0 :: XEX 575207E9',
                     'SHA-256 3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1',
                     'ABERTURA :: MODOS 30 / 60 / 120 / 240 QUADROS'):
            item = self.create_text(left, y, anchor='nw', tags='reveal',
                                    text=text, fill=mix(t.bg, t.accent, .25),
                                    font=self._font(8))
            self._reveal_colors.append((item, mix(t.bg, t.accent, .25), 'fill'))
            y += 13

    def _build_playback_frame(self, width, height):
        """Frame de reprodução ao redor do núcleo do portal."""
        t = self.theme
        cx, cy = width * .80, height * .48
        r = min(height * .34, width * .21) * .74
        frame = rounded_rect(self, cx - r - 10, cy - r - 10, cx + r + 10, cy + r + 10, 22,
                             fill=None,
                             outline=mix(t.bg, t.accent, .28))
        for item in frame:
            self.addtag_withtag('reveal', item)
            self._reveal_colors.append((item, mix(t.bg, t.accent, .28), 'outline'))

    def _update_mission_markers(self):
        """Constrói ou reconfigura os três marcadores de missão do hero."""
        t = self.theme
        left = max(26, int(width if False else 0))  # placeholder, corrigido abaixo
        width, height = self._field_size
        left = max(26, int(width * .028))
        top = max(18, int(height * .07))
        y = top + 96
        order = ('dump', 'port', 'session')
        glyphs = {'dump': '◆ ', 'port': '◉ ', 'session': '⟳ '}
        for key in order:
            label, state = self._mission[key]
            color = t.muted if state == 'off' else (t.accent if state == 'on' else t.warn)
            self.create_text(left, y, anchor='nw', tags='reveal',
                             text=f'{glyphs[key]}{label}', fill=color,
                             font=self._font(9))
            y += 16

    def _start_reveal(self):
        if self._reveal:
            self.after_cancel(self._reveal)
        bg = self.theme.bg
        steps, index = 12, [0]
        self.move('reveal', 0, 16)
        for item, _, attr in self._reveal_colors:
            try:
                self.itemconfigure(item, **{attr: bg})
            except tk.TclError:
                other = 'outline' if attr == 'fill' else 'fill'
                self.itemconfigure(item, **{other: bg})

        def step():
            index[0] += 1
            ratio = min(1.0, index[0] / steps)
            eased = 1 - (1 - ratio) ** 3
            self.move('reveal', 0, -16 / steps)
            for item, final, attr in self._reveal_colors:
                try:
                    self.itemconfigure(item, **{attr: mix(bg, final, eased)})
                except tk.TclError:
                    other = 'outline' if attr == 'fill' else 'fill'
                    self.itemconfigure(item, **{other: mix(bg, final, eased)})
            if ratio < 1.0:
                self._reveal = self.after(24, step)
            else:
                self._reveal = None

        self._reveal = self.after(24, step)
