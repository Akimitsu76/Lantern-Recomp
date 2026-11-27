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
        # Constructo Hall Jordan: itens e fase do tick contínuo.
        self._hall_items = {'rings': [], 'spirals': [], 'distortion': []}
        self._hall_distortion_meta = []
        self._hall_tick = None
        self._hall_phase = [0.0]
        self._hall_geometry = None
        self._field_size = (1, 1)
        self._reveal_colors = []
        self._status = 'SELECIONE SEU DUMP PARA COMEÇAR'
        self._mission = {'dump': ('AGUARDANDO', 'off'),
                         'port': ('NÃO GERADO', 'off'),
                         'session': ('0 MIN', 'off')}
        self._session_ticks = 0
        # Linhas de informação do disco, alimentadas pelo launcher.
        self._info_lines = {
            'disc': 'DISCO :: --',
            'sha': 'SHA-256 :: --',
            'abertura': 'ABERTURA :: 30 / 60 / 240 QUADROS',
        }
        # IDs do bloco de informações alinhado abaixo do título. Uma única
        # construção por paint;set_* apenas reconfigura o texto existente.
        self._info_items = {}
        self.bind('<Configure>', self._resize)
        self.bind('<Destroy>', self._destroy, add='+')

    def _destroy(self, event):
        if event.widget is not self:
            return
        for name in ('_pending', '_reveal', '_orbit', '_hall_tick',
                     '_juramento_anim', '_juramento_text_anim'):
            pending = getattr(self, name, None)
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
        """Atualiza a linha de importação do bloco, quando ela existir."""
        item = self._info_items.get('import')
        if item is not None:
            self.itemconfigure(item, text=label)

    def set_session_seconds(self, seconds: int | None):
        """Atualiza a linha de sessão do bloco alinhado abaixo do título."""
        self._session_ticks = 0 if seconds is None else max(0, int(seconds))
        minutes = self._session_ticks // 60
        self._mission['session'] = (f'{minutes} MIN', 'off' if seconds is None else 'on')
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
        self._info_items = {}
        self._field_size = (width, height)
        self.image_error = None
        self._paint_glow(width, height)
        self._paint_grid(width, height)
        self._paint_energy_field(width, height)
        geometry = self._paint_portal(width, height)
        # Constructo Hall Jordan: anéis concêntricos, espirais e distorção,
        # desenhados sobre o portal base e animados por um tick próprio.
        self._paint_hall_jordan(geometry)
        self._paint_text(width, height, geometry)
        self._build_accent_column(width, height)
        self._build_playback_frame(width, height)
        self._start_reveal()

    def _paint_grid(self, width, height):
        """Grade tecnológica discreta no fundo, como um HUD de radar.

        Linhas verticais e horizontais finas, mais densas à direita (perto do
        portal), dando profundidade sem competir com o conteúdo textual.
        """
        t = self.theme
        # Linhas verticais: espaçamento regular, acento só perto do portal.
        step = 46
        for x in range(step, width, step):
            near_port = abs(x - width * .62) < width * .30
            alpha = .055 if near_port else .028
            self.create_line(x, 0, x, height, fill=mix(t.bg, t.accent, alpha), width=1)
        # Linhas horizontais: mais sutis, ancoradas no centro do portal.
        cy = height * .46
        for y in range(int(height * .12), height, 34):
            distance = abs(y - cy) / max(1, height)
            alpha = .05 * (1.0 - distance) + .018
            self.create_line(0, y, width, y, fill=mix(t.bg, t.accent, alpha), width=1)

    def _paint_glow(self, width, height):
        """Fundo da capa: gradiente, manchas de luz e halo do construtor."""
        t = self.theme
        cx, cy, radius = int(width * .62), int(height * .46), int(height * .42)
        try:
            from PIL import Image, ImageDraw, ImageFilter, ImageTk
            base = Image.new('RGB', (width, height), t.bg)
            grad = Image.new('RGB', (1, max(2, height)))
            top = tuple(int(t.bg_deep[i:i + 2], 16) for i in (1, 3, 5))
            bottom = tuple(int(t.bg[i:i + 2], 16) for i in (1, 3, 5))
            for y in range(max(2, height)):
                ratio = y / max(2, height)
                grad.putpixel((0, y), tuple(round(a + (b - a) * ratio)
                                            for a, b in zip(top, bottom)))
            base = grad.resize((width, max(2, height)))

            glow = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(glow)
            accent = t.accent.lstrip('#')
            rgb = tuple(int(accent[i:i + 2], 16) for i in (0, 2, 4))
            # Manchas de luz difusas: dão profundidade sem nenhum asset.
            for bx, by, br, alpha in ((width * .18, height * .22, height * .30, 26),
                                      (width * .30, height * .78, height * .26, 18),
                                      (width * .62, height * .46, radius, 34)):
                draw.ellipse((bx - br, by - br, bx + br, by + br), fill=rgb + (alpha,))
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                         outline=rgb + (150,), width=11)
            draw.line((cx - radius * .8, cy + radius * .55, cx + radius * .8, cy + radius * .55),
                      fill=rgb + (100,), width=6)
            blurred = glow.filter(ImageFilter.GaussianBlur(40))
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
        cx, cy = width * .62, height * .46
        for index, (factor, alpha, start, extent) in enumerate((
                (1.05, .13, 18, 118), (1.28, .09, 168, 96),
                (1.52, .06, 78, 74), (1.86, .035, 240, 54), (2.2, .022, 300, 40))):
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
        for index in range(30):
            radius = 1 + index % 3
            x = (index * 79 + 41) % max(2, width)
            y = (index * 53 + 19) % max(2, height)
            item = self.create_oval(x - radius, y - radius, x + radius, y + radius,
                                    fill=mix(t.bg, t.accent_2, .22 + (index % 4) * .12),
                                    outline='')
            self._motes.append([item, float(x), float(y), .28 + (index % 5) * .12,
                                radius, index * .7])

    def _paint_portal(self, width, height):
        t = self.theme
        cx, cy = width * .62, height * .46
        base = min(height * .40, width * .26)
        for factor, alpha in ((1.75, .06), (1.42, .10), (1.12, .18), (.86, .10)):
            r = base * factor
            self.create_oval(cx - r, cy - r, cx + r, cy + r,
                             outline=mix(t.bg, t.accent, alpha), width=1)
        # Raios radiais ligando o núcleo aos anéis, como feixes de luz.
        for index in range(24):
            angle = math.radians(index * 15)
            r0, r1 = base * .9, base * (1.55 if index % 4 else 2.1)
            self.create_line(cx + math.cos(angle) * r0, cy + math.sin(angle) * r0 * .72,
                             cx + math.cos(angle) * r1, cy + math.sin(angle) * r1 * .72,
                             fill=mix(t.bg, t.accent, .05 + (index % 3) * .04), width=1)
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

    # ------------------------------------------------- constructo Hall Jordan
    def _cancel_hall_tick(self):
        """Cancela o tick anterior antes de reconstruir o constructo."""
        pending = getattr(self, '_hall_tick', None)
        if pending:
            try:
                self.after_cancel(pending)
            except tk.TclError:
                pass
        self._hall_tick = None

    def _paint_hall_jordan(self, geometry):
        """Desenha o constructo Hall Jordan sobre o portal base e anima-o.

        Ordem de renderização: anéis concêntricos → partículas em espirais →
        retângulos de distorção espacial. Cada repintura reinicia a fase.
        """
        cx, cy, base = geometry
        self._cancel_hall_tick()
        self._hall_phase = [0.0]
        self._hall_geometry = (cx, cy, base)
        self._hall_distortion_meta = []

        rings, spirals, distortion = self._create_hall_jordan_construct(cx, cy)
        self._hall_items = {
            'rings': rings,
            'spirals': spirals,
            'distortion': distortion,
        }
        self._start_hall_tick()

    def _create_hall_jordan_construct(self, cx, cy):
        """Cria anéis, espirais e distorção usando os métodos do constructo."""
        rings = self._ano_concentricos_hall_jordan(cx, cy)
        spirals = self._construir_espirais(cx, cy)
        distortion = []
        for ring_id in range(3):
            distortion.extend(self._construir_anel_distorcao(cx, cy, ring_id))
        return rings, spirals, distortion

    def _start_hall_tick(self):
        """Tick contínuo: gira os arcos, orbita as espirais e pulsa a distorção."""
        def tick():
            if not self.winfo_exists():
                self._hall_tick = None
                return
            phase = self._hall_phase[0]
            self._hall_phase[0] = (phase + 1.6) % 360.0
            cx, cy, _base = self._hall_geometry

            # Anéis concêntricos: cada arco gira em velocidade própria.
            for index, item in enumerate(self._hall_items['rings']):
                start = (index * 7 + self._hall_phase[0] * (.3 + (index % 4) * .08)) % 360
                try:
                    self.itemconfigure(item, start=start)
                except tk.TclError:
                    continue

            # Espirais: partículas orbitam com raio levemente pulsante.
            for index, item in enumerate(self._hall_items['spirals']):
                row, i = divmod(index, 16)
                angle = (-90 + row * 35 + i * (360 / 16) * (1.8 + row * .2)
                         + self._hall_phase[0] * (1 + row * .25))
                r = 26 * math.sqrt(1 + .45 * i)
                r *= 1 + .04 * math.sin(math.radians(self._hall_phase[0] * 2 + i))
                x = cx + math.cos(math.radians(angle)) * r
                y = cy + math.sin(math.radians(angle)) * r * .65
                size = max(3, 7 - int(i * .18) - row)
                try:
                    self.coords(item, x - size // 2, y - size // 2,
                                x + size // 2, y + size // 2)
                except tk.TclError:
                    continue

            # Distorção espacial: retângulos giram e pulsam com a fase.
            for item, angle, radius, ring_id in self._hall_distortion_meta:
                a = angle + self._hall_phase[0] * (.4 + ring_id * .15)
                wobble = 1 + .08 * math.sin(math.radians(a * 2 + ring_id * 30))
                x = cx + math.cos(math.radians(a)) * radius * wobble
                y = cy + math.sin(math.radians(a)) * radius * wobble * .65
                try:
                    self.coords(item, x - 3, y - 2, x + 3, y + 2)
                except tk.TclError:
                    continue

            self._hall_tick = self.after(70, tick)

        self._hall_tick = self.after(70, tick)

    def _paint_text(self, width, height, geometry):
        """Capa do jogo: identidade no topo, painel de status e constructo."""
        t = self.theme
        left, top = 30, 22
        title_size = max(26, min(54, int(height * .13)))
        small = ('DejaVu Sans', 9, 'bold')
        tiny = ('DejaVu Sans', 8)
        mono = ('DejaVu Sans Mono', 8)
        display = ('DejaVu Sans Condensed', title_size, 'bold')

        def record(item, color, attr='fill'):
            self._reveal_colors.append((item, color, attr))
            return item

        def decorate(items, color=None):
            for item in items:
                self.addtag_withtag('reveal', item)
                attr = 'fill' if self.itemcget(item, 'fill') not in ('', None) else 'outline'
                record(item, color or self.itemcget(item, attr), attr)

        # Identidade da capa, ancorada no topo esquerdo.
        record(self.create_text(left, top, anchor='nw', tags='reveal',
                                text=f'XBOX 360 → PC  ·  {t.edition.upper()}',
                                fill=t.muted, font=small), t.muted)
        record(self.create_text(left, top + 18, anchor='nw', tags='reveal',
                                text=t.game.upper(), fill=t.ink, font=display), t.ink)
        record(self.create_text(left, top + 26 + title_size, anchor='nw', tags='reveal',
                                text=t.subtitle.upper(), fill=t.accent,
                                font=('DejaVu Sans', max(12, title_size // 4), 'bold')), t.accent)

        # Bloco de informações alinhado com o título (mesma coluna esquerda).
        # Começa logo abaixo do subtítulo com espaçamento hierárquico consistente.
        y = top + 40 + title_size + 24
        record(self.create_text(left, y, anchor='nw', tags='reveal',
                                text=self._info_lines['abertura'],
                                fill=t.accent_2, font=mono), t.accent_2)
        y += 18
        for key in ('disc', 'sha'):
            item = self.create_text(left, y, anchor='nw', tags='reveal',
                                    text=self._info_lines[key], fill=t.muted, font=mono)
            self._info_items[key] = item
            record(item, t.muted)
            y += 17
        y += 10
        glyphs = {'dump': '◆', 'port': '◉', 'session': '⟳'}
        for key in ('dump', 'port', 'session'):
            label, st = self._mission[key]
            color = t.muted if st == 'off' else (t.accent if st == 'on' else t.warn)
            item = self.create_text(left, y, anchor='nw', tags='reveal',
                                    text=f'{glyphs[key]}  {label}', fill=color, font=tiny)
            self._info_items[key] = item
            record(item, color)
            y += 17
        y += 12
        record(self.create_text(left, y, anchor='nw', tags='reveal',
                                text=t.tagline.upper(), fill=t.ink,
                                font=('DejaVu Sans', 11, 'bold')), t.ink)
        y += 24
        record(self.create_text(left, y, anchor='nw', tags=('hero-status', 'reveal'),
                                text=self._status, fill=t.muted, font=tiny), t.muted)

        # Selo da edição no canto inferior direito.
        badge_color = mix(t.bg, t.accent, .60)
        badge = rounded_rect(self, width - 118, height - 52, width - 28, height - 20, 16,
                             fill=mix(t.bg, t.accent_2, .20), outline=badge_color)
        decorate(badge, badge_color)
        record(self.create_text(width - 73, height - 36, anchor='center', tags='reveal',
                                text=t.edition.upper(), fill=t.accent_2, font=small), t.accent_2)

    def set_info(self, key: str, value: str):
        """Atualiza uma linha do painel (``disc``, ``sha``, ``abertura``)."""
        if key not in self._info_lines:
            return
        self._info_lines[key] = value
        item = self._info_items.get(key)
        if item is not None:
            try:
                self.itemconfigure(item, text=value)
            except tk.TclError:
                pass

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

    def _build_playback_frame(self, width, height):
        """Frame de reprodução ao redor do núcleo do portal."""
        t = self.theme
        cx, cy = width * .62, height * .46
        r = min(height * .34, width * .21) * .74
        frame = rounded_rect(self, cx - r - 10, cy - r - 10, cx + r + 10, cy + r + 10, 22,
                             fill=None,
                             outline=mix(t.bg, t.accent, .28))
        for item in frame:
            self.addtag_withtag('reveal', item)
            self._reveal_colors.append((item, mix(t.bg, t.accent, .28), 'outline'))

    def set_mission(self, key: str, label: str, state: str):
        """Atualiza um marcador de missão e reconfigura o bloco de informações."""
        if key in self._mission:
            self._mission[key] = (label, state)
        self._update_mission_markers()
        # Quando o dump é reconhecido, dispara a animação do juramento.
        if key == 'dump' and state == 'on':
            self.after(600, self.animate_juramento)

    def _update_mission_markers(self):
        """Reconfigura as três linhas dinâmicas sem criar novos itens."""
        glyphs = {'dump': '◆', 'port': '◉', 'session': '⟳'}
        for key in ('dump', 'port', 'session'):
            item = self._info_items.get(key)
            if item is None:
                continue
            label, st = self._mission[key]
            color = self.theme.muted if st == 'off' else (
                self.theme.accent if st == 'on' else self.theme.warn)
            try:
                self.itemconfigure(item, text=f'{glyphs[key]}  {label}', fill=color)
            except tk.TclError:
                pass

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

    # ------------------------------------------------------------- juramento
    def animate_juramento(self):
        """Converge partículas para o constructo Hall Jordan e mostra o juramento."""
        if getattr(self, '_juramento_done', False):
            return
        self._juramento_done = True
        t = self.theme
        width, height = self._field_size
        cx, cy, _base = self._hall_geometry or (width * .62, height * .46, None)

        # Encerra a órbita comum; o constructo continua sob o tick Hall Jordan.
        if self._orbit:
            self.after_cancel(self._orbit)
            self._orbit = None
        for item, _ in self._orbit_items:
            try:
                self.delete(item)
            except tk.TclError:
                pass
        self._orbit_items = []

        # O constructo já foi desenhado pelo _paint e segue sob o tick Hall Jordan.

        # Partículas convergem em espiral e se fundem no núcleo.
        motes = []
        for index in range(24):
            dot = self.create_oval(cx - 2, cy - 2, cx + 2, cy + 2,
                                   fill=t.accent_2, outline='', tags='juramento')
            motes.append(dot)
            self._reveal_colors.append((dot, t.accent_2, 'fill'))

        phase = [0.0]

        def spin():
            if not self.winfo_exists():
                self._juramento_anim = None
                return
            phase[0] += .5
            progress = min(1.0, phase[0] / 12.0)
            radius = 150 * (1.0 - progress) + 8
            for i, dot in enumerate(motes):
                angle = math.radians(i * (360 / len(motes)) + phase[0] * 14)
                x = cx + math.cos(angle) * radius
                y = cy + math.sin(angle) * radius * .72
                try:
                    self.coords(dot, x - 2, y - 2, x + 2, y + 2)
                except tk.TclError:
                    self._juramento_anim = None
                    return
            if progress < 1.0:
                self._juramento_anim = self.after(35, spin)
            else:
                self._juramento_anim = None
                for dot in motes:
                    try:
                        self.delete(dot)
                    except tk.TclError:
                        pass
                self._juramento_lines = 0
                self._juramento_texto = [
                    'NO DIA MAIS CLARO,',
                    'NA NOITE MAIS DENSA,',
                    'O MAL SUCUMBIRÁ PERANTE A MINHA PRESENÇA,',
                    'TODO AQUELE QUE VENERA O MAL IRÁ DE PENAR,',
                    'QUANDO O LANTERNA VERDE ENFRENTAR',
                ]
                self._escrever_juramento(cx, cy + 60)

        self._juramento_anim = self.after(35, spin)

    def _construir_espirais(self, cx, cy):
        """Partículas de energia em 3 fileiras seguindo espirais logarítmicas."""
        t = self.theme
        spirals = []

        # 3 fileiras de espirais
        for row in range(3):
            items = []
            num_particles = 16
            base_angle = -90 + row * 35
            base_radius = 26

            # Partículas distribuidas seguindo espiral
            for i in range(num_particles):
                angle = base_angle + i * (360 / num_particles) * (1.8 + row * 0.2)  # espiral logarítmica

                r = base_radius * math.sqrt(1 + 0.45 * i)  # aumenta levemente com a espiral

                x_offset = math.cos(math.radians(angle)) * r
                y_offset = math.sin(math.radians(angle)) * r * 0.65

                # Tamanho diminui conforme anda para fora
                size = max(3, 7 - int(i * 0.18) - row)

                dot = self.create_oval(cx + x_offset - size//2, cy + y_offset - size//2,
                                      cx + x_offset + size//2, cy + y_offset + size//2,
                                      fill=t.accent if row < 2 else t.accent_2,
                                      outline='',
                                      tags='juramento')

                if dot:
                    items.append(dot)
            spirals.extend(items)

        return spirals

    def _construir_anel_distorcao(self, cx, cy, ring_id):
        """Retângulos de distorção espacial em onda senoidal (Hall Jordan)."""
        t = self.theme
        phase = getattr(self, '_hall_phase', [0.0])

        rings_data = [
            {'count': 5, 'amplitude': 40, 'frequency': 0.8, 'offset_angle': -17},
            {'count': 8, 'amplitude': 62, 'frequency': 1.6, 'offset_angle': -39},
            {'count': 11, 'amplitude': 85, 'frequency': 2.4, 'offset_angle': -70},
        ][ring_id] if ring_id < 3 else {
            'count': 3, 'amplitude': 68, 'frequency': 1.3, 'offset_angle': -6}

        items = []
        num_items = rings_data['count']
        amplitude = rings_data['amplitude']
        freq = rings_data['frequency']
        start_offset = rings_data['offset_angle']

        for i in range(num_items):
            angle = (-170 + i * 45) + (hash(str(i)) % 20 - 10)
            r_distortion = (28 + math.sin(math.radians(angle + start_offset) * freq)
                            * amplitude / num_items)
            x_offset = math.cos(math.radians(angle)) * r_distortion
            y_offset = math.sin(math.radians(angle)) * r_distortion * .65

            # Pulsação determinística ligada à fase do tick.
            pulse = (hash(str(i) + str(int(phase[0]))) % 4 - 1) / 4
            rect = self.create_rectangle(
                cx + x_offset - 3, cy + y_offset - 2,
                cx + x_offset + 3, cy + y_offset + 2,
                fill=mix(t.bg, t.accent if ring_id % 2 == 0 else t.accent_2, .85 + pulse),
                outline='', tags='juramento')

            if rect:
                items.append(rect)
                self._hall_distortion_meta.append(
                    (rect, angle, r_distortion, ring_id))

        return items

    def _ano_concentricos_hall_jordan(self, cx, cy):
        """Desenha anéis de ondas concêntricos variando do interior para exterior (Hall Jordan visual)."""
        t = self.theme

        ring_items = []
        colors = [
            mix(t.bg, t.accent, .75),      # interior - acento intenso
            mix(t.bg, t.warn, .68),
            mix(t.bg, t.accent_2, .60),    # meio - verde suave
            mix(t.bg, t.accent, .53),
            mix(t.bg, t.warn, .56),
            mix(t.bg, t.accent_2, .49),
            mix(t.bg, t.ok, .58),       # externo - verde vibrante
        ]

        # 7 camadas concêntricas com efeito de onda irregular
        for i, base_outline in enumerate(colors):
            base_radius = 16 + i * 10

            # Aro principal quase completo
            offset = (hash(str(i)) % 5 - 2)  # variação aleatória

            arc_items = []
            for j in range(4):  # 3 aros incompletos para efeito de onda
                angle_start = i * 15 + offset + j * 8
                angle_end = angle_start + 260 + (hash(str(i) + str(j)) % 30)

                arc = self.create_arc(cx - base_radius, cy - base_radius,
                                      cx + base_radius, cy + base_radius,
                                      start=angle_start, extent=angle_end,
                                      outline=base_outline, width=2 if j < 2 else 1.5,
                                      style=tk.ARC,
                                      tags='juramento')
                if arc:
                    arc_items.append(arc)

            ring_items.extend(arc_items)

        return ring_items

    def _escrever_juramento(self, x, y):
        """Exibe o juramento linha por linha, como um constructo de luz."""
        t = self.theme
        if self._juramento_lines >= len(self._juramento_texto):
            return
        texto = self._juramento_texto[self._juramento_lines]
        item = self.create_text(x, y + self._juramento_lines * 24,
                                anchor='center', text=texto, fill=t.accent_2,
                                font=('DejaVu Sans', 11, 'bold'), tags='juramento')
        self._reveal_colors.append((item, t.accent_2, 'fill'))
        self._juramento_lines += 1
        self._juramento_text_anim = self.after(700,
                                               lambda: self._escrever_juramento(x, y))

    def cancel(self):
        """Cancela animações decorativas antes de destruir."""
        self._cancel_hall_tick()
        for name in ('_juramento_anim', '_juramento_text_anim', '_reveal', '_orbit'):
            pending = getattr(self, name, None)
            if pending:
                try:
                    self.after_cancel(pending)
                except tk.TclError:
                    pass
                setattr(self, name, None)
