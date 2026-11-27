"""Componentes visuais reutilizáveis do Portal dos Recomps.

Tudo é desenhado com primitivas do Tk/Canvas: sem PNGs, sem Pillow e sem
dependência de temas do sistema. Um jogo troca apenas o ``PortalTheme``; o
shell e estes componentes permanecem idênticos entre projetos.

Contrato importante para os launchers derivados: ``RoundedCard`` continua
sendo um ``tk.Frame``, então a hierarquia de widgets e os ``master.master``
usados por testes e layout permanecem os mesmos de um card retangular.
"""
from __future__ import annotations

import tkinter as tk

from .portal_theme import mix, shade
from .rounded_buttons import button_photo


def rounded_rect(canvas: tk.Canvas, x0: float, y0: float, x1: float, y1: float,
                 radius: float = 14, *, fill: str | None = None,
                 outline: str | None = None, width: int = 1) -> list[int]:
    """Desenha um retângulo de cantos arredondados em um Canvas.

    Tk não tem ``create_rounded_rectangle``; a forma é composta de dois
    retângulos, dois arcos e dois círculos. Funciona em Tk 8.6 e superior.
    """
    x0, x1 = sorted((float(x0), float(x1)))
    y0, y1 = sorted((float(y0), float(y1)))
    radius = max(1.0, min(float(radius), (x1 - x0) / 2, (y1 - y0) / 2))
    d = radius * 2
    items = [
        canvas.create_rectangle(x0 + radius, y0, x1 - radius, y1, fill=fill, outline=''),
        canvas.create_rectangle(x0, y0 + radius, x1, y1 - radius, fill=fill, outline=''),
    ]
    # arcs: quadrantes superior-esquerdo, superior-direito, inferior-direito, inferior-esquerdo
    items.append(canvas.create_arc(x0, y0, x0 + d, y0 + d, start=90, extent=90,
                                   fill=fill, outline=''))
    items.append(canvas.create_arc(x1 - d, y0, x1, y0 + d, start=0, extent=90,
                                   fill=fill, outline=''))
    items.append(canvas.create_arc(x1 - d, y1 - d, x1, y1, start=270, extent=90,
                                   fill=fill, outline=''))
    items.append(canvas.create_arc(x0, y1 - d, x0 + d, y1, start=180, extent=90,
                                   fill=fill, outline=''))
    if outline:
        items.extend([
            canvas.create_line(x0 + radius, y0, x1 - radius, y0, fill=outline, width=width),
            canvas.create_line(x0 + radius, y1, x1 - radius, y1, fill=outline, width=width),
            canvas.create_line(x0, y0 + radius, x0, y1 - radius, fill=outline, width=width),
            canvas.create_line(x1, y0 + radius, x1, y1 - radius, fill=outline, width=width),
            canvas.create_arc(x0, y0, x0 + d, y0 + d, start=90, extent=90,
                              style='arc', outline=outline, width=width),
            canvas.create_arc(x1 - d, y0, x1, y0 + d, start=0, extent=90,
                              style='arc', outline=outline, width=width),
            canvas.create_arc(x1 - d, y1 - d, x1, y1, start=270, extent=90,
                              style='arc', outline=outline, width=width),
            canvas.create_arc(x0, y1 - d, x0 + d, y1, start=180, extent=90,
                              style='arc', outline=outline, width=width),
        ])
    return items


class RoundedCard(tk.Frame):
    """Um ``tk.Frame`` com fundo e borda arredondados desenhados atrás.

    Os filhos são packados normalmente no Frame; o Canvas de fundo é o primeiro
    filho, colocado com ``place``. Assim a API pública continua idêntica à de
    um Frame comum (``pack``, ``winfo_*``, ``master``).
    """

    def __init__(self, parent, *, fill: str, outline: str | None = None,
                 radius: int = 20, border: int = 1, pad: int = 1, **kwargs):
        parent_bg = parent.cget('bg') if 'bg' not in kwargs else kwargs['bg']
        kwargs.setdefault('bg', parent_bg)
        kwargs.setdefault('highlightthickness', 0)
        kwargs.setdefault('bd', 0)
        super().__init__(parent, **kwargs)
        self._fill = fill
        self._outline = outline
        self._radius = radius
        self._border = border
        self._pad = pad
        self._background_canvas = tk.Canvas(self, bg=parent_bg, highlightthickness=0)
        self._background_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._background_canvas.bind('<Configure>', self._redraw)
        self._hover = False

    def _redraw(self, event=None):
        canvas = self._background_canvas
        width = event.width if event is not None else canvas.winfo_width()
        height = event.height if event is not None else canvas.winfo_height()
        if width < 4 or height < 4:
            return
        canvas.delete('card')
        p = self._pad
        color = shade(self._fill, 0.05) if self._hover else self._fill
        outline = shade(self._outline, 0.22) if self._hover and self._outline else self._outline
        for item in rounded_rect(canvas, p, p, width - p, height - p, self._radius,
                                 fill=color, outline=outline, width=self._border):
            canvas.addtag_withtag('card', item)
        canvas.tag_lower('card')

    def set_hover(self, hovered: bool):
        if self._hover != bool(hovered):
            self._hover = bool(hovered)
            self._redraw()


def draw_portal_mark(canvas: tk.Canvas, cx: float, cy: float, size: float,
                     theme, *, glyph: bool = True, tags: str | tuple | None = None):
    """Desenha a marca do Portal dos Recomps diretamente em um Canvas.

    A mesma primitiva serve ao logo do cabeçalho e ao brasão do hero: um anel
    aberto, uma haste de passagem e um núcleo com o ``glyph`` da distro. Nada
    aqui conhece um jogo específico.

    Retorna ``(itens, arcos, cores)``. ``cores`` é uma lista de
    ``(item, cor, atributo)`` para animações de reveal que trocam cor.
    """
    t = theme
    r = size * .36
    items, arcs, colors = [], [], []

    def add(item, color=None, attr='fill', tag_as_arc=False):
        items.append(item)
        if tags is not None:
            canvas.addtag_withtag(tags, item)
        if color is not None:
            colors.append((item, color, attr))
        if tag_as_arc:
            arcs.append(item)
        return item

    # Halo circular: nenhum quadrado, mesmo em tamanhos pequenos.
    halo = mix(t.bg, t.accent, .07)
    add(canvas.create_oval(cx - r * 1.38, cy - r * 1.38, cx + r * 1.38, cy + r * 1.38,
                           fill=halo, outline=''), halo)
    for start, extent, alpha, width in ((205, 145, .92, max(2, int(size * .07))),
                                        (25, 145, .52, max(1, int(size * .04)))):
        color = mix(t.bg, t.accent, alpha)
        add(canvas.create_arc(cx - r, cy - r, cx + r, cy + r, style='arc',
                              start=start, extent=extent, outline=color, width=width),
            color, 'outline', True)
    stem = mix(t.bg, t.accent_2, .78)
    add(canvas.create_line(cx, cy + r * .68, cx, cy + r * 1.16,
                           fill=stem, width=max(1, int(size * .05))), stem)
    foot = mix(t.bg, t.accent_2, .62)
    add(canvas.create_line(cx - size * .10, cy + r * 1.16,
                           cx + size * .10, cy + r * 1.16,
                           fill=foot, width=max(1, int(size * .05))), foot)
    core = mix(t.bg, t.accent, .88)
    add(canvas.create_oval(cx - size * .085, cy - size * .085,
                           cx + size * .085, cy + size * .085,
                           fill=core, outline=''), core)
    if glyph and size >= 30:
        add(canvas.create_text(cx, cy, text=t.glyph, fill=t.bg,
                               font=('DejaVu Sans Condensed', max(7, int(size * .18)), 'bold')),
            t.bg)
    return items, arcs, colors


class PortalMark(tk.Canvas):
    """Logo procedural reutilizável, na mesma identidade do hero."""

    def __init__(self, parent, *, theme, size: int = 48, glyph: bool = True, **kwargs):
        super().__init__(parent, width=size, height=size, bg=theme.bg,
                         highlightthickness=0, bd=0, **kwargs)
        self.theme = theme
        self.size = size
        self.glyph = glyph
        self.bind('<Configure>', lambda _: self._paint())

    def _paint(self):
        self.delete('mark')
        size = max(16, min(self.winfo_width(), self.winfo_height()))
        if size < 2:
            return
        draw_portal_mark(self, size / 2, size / 2, size, self.theme,
                         glyph=self.glyph, tags='mark')


class ConstructNav(tk.Canvas):
    """Item de menu desenhado como um constructo de anel.

    O ``tk.Button`` interno continua exposto em ``self.button`` para preservar
    ``nav_buttons``, atalhos e testes. O Canvas ao redor desenha cantos de
    energia e, ao clicar, constrói o contorno antes de trocar de página.
    """

    def __init__(self, parent, *, text: str, theme, command, height: int = 44, **kwargs):
        super().__init__(parent, height=height, bg=theme.surface,
                         highlightthickness=0, bd=0, **kwargs)
        self.theme = theme
        self._command = command
        self._active = False
        self._hover = False
        self._progress = 0.0
        self._anim = None
        self._button_images = {}
        self.button = tk.Button(
            self, text=text, bg=theme.surface, fg=theme.muted,
            activebackground=theme.surface,
            activeforeground=theme.ink, relief='flat', bd=0,
            highlightthickness=0, anchor='w', padx=14, pady=9, compound='center',
            font=(theme.font, 10, 'bold'), cursor='hand2', command=self._clicked)
        self._window = self.create_window(8, 5, anchor='nw', window=self.button)
        self.bind('<Configure>', self._layout)
        self.button.bind('<Enter>', lambda _: self._set_hover(True))
        self.button.bind('<Leave>', lambda _: self._set_hover(False))

    def _layout(self, _event=None):
        width = max(10, self.winfo_width() - 16)
        height = max(10, self.winfo_height() - 10)
        self.coords(self._window, 8, 5)
        self.itemconfigure(self._window, width=width, height=height)
        self._paint()

    def _set_hover(self, hovered):
        self._hover = bool(hovered)
        self._paint()

    def _paint(self):
        self.delete('construct')
        width, height = self.winfo_width(), self.winfo_height()
        if width < 8 or height < 8:
            return
        t = self.theme
        accent = t.accent
        if self._active:
            fill, foreground = mix(t.surface, accent, .20), t.ink
        elif self._hover:
            fill, foreground = mix(t.surface, accent, .10), t.accent_2
        else:
            fill, foreground = t.surface, t.muted
        # O fundo do tk.Button permanece igual ao do Canvas; a borda arredondada
        # vem da imagem, então não há cantos quadrados visíveis.
        self.button.configure(bg=t.surface, fg=foreground,
                              image=self._rounded_photo(width, height, fill))

        # Cantos de energia: a "construção" cresce a partir dos quatro cantos.
        strength = 1.0 if self._active else .55 if self._hover else .18
        growth = max(.0, min(1.0, self._progress))
        pad = 2
        length = min(width * .18, 14) * (0.35 + growth * .65)
        color = mix(t.surface, accent, strength if growth <= 0 else .9)
        for x, y, dx, dy in ((pad, pad, 1, 1), (width - pad, pad, -1, 1),
                             (pad, height - pad, 1, -1), (width - pad, height - pad, -1, -1)):
            item = self.create_line(x, y + dy * length, x, y, x + dx * length, y,
                                    fill=color, width=2, capstyle='round')
            self.addtag_withtag('construct', item)
        if self._active:
            bar = self.create_line(pad, height * .24, pad, height * .76,
                                   fill=accent, width=3, capstyle='round')
            self.addtag_withtag('construct', bar)
        if self._progress > 0:
            sweep = self.create_line(pad, height / 2,
                                     pad + (width - pad * 2) * self._progress, height / 2,
                                     fill=mix(t.surface, t.accent_2, .9), width=2)
            self.addtag_withtag('construct', sweep)
        self.tag_lower('construct')

    def _rounded_photo(self, width, height, fill):
        w, h = max(8, int(width) - 16), max(8, int(height) - 10)
        key = (w, h, fill)
        photo = self._button_images.get(key)
        if photo is None:
            photo = button_photo(self, fill, mix(self.theme.surface, self.theme.accent, .34),
                                 width=w, height=h, radius=min(4, h // 2))
            self._button_images[key] = photo
        return photo

    def _clicked(self):
        if self._anim:
            return
        steps, index = 10, [0]

        def step():
            index[0] += 1
            self._progress = min(1.0, index[0] / steps)
            self._paint()
            if index[0] < steps:
                self._anim = self.after(18, step)
            else:
                self._anim = None
                self._progress = 0.0
                self._paint()
                self._command()

        self._progress = .01
        self._paint()
        self._anim = self.after(18, step)

    def set_active(self, active: bool):
        self._active = bool(active)
        self._paint()

    def cancel(self):
        if self._anim:
            self.after_cancel(self._anim)
            self._anim = None


class NavIndicator(tk.Canvas):
    """Pílula arredondada que desliza entre os botões de navegação.

    A animação usa ``after`` com interpolação linear curta (120 ms). O indicador
    é decorativo: nunca vira pai dos botões, que continuam sendo ``tk.Button``
    normais e acessíveis pelos testes.
    """

    def __init__(self, parent, *, color: str, background: str, height: int = 34,
                 duration: int = 130, **kwargs):
        super().__init__(parent, height=height, bg=background, highlightthickness=0,
                         bd=0, **kwargs)
        self._color = color
        self._background = background
        self._duration = max(1, duration)
        self._target = None
        self._current = None
        self._anim = None
        self._item = None
        self.bind('<Configure>', lambda _: self._render())

    def move_to(self, widget: tk.Widget, _attempt: int = 0):
        """Alvo em coordenadas relativas ao próprio Canvas.

        Durante a construção a janela ainda não está mapeada; nesse caso
        tentamos de novo alguns frames depois, em vez de perder o indicador.
        """
        if widget.winfo_width() <= 1 or self.winfo_width() <= 1:
            if _attempt < 12:
                self.after(60, lambda: self.move_to(widget, _attempt + 1))
            return
        self.update_idletasks()
        x = widget.winfo_rootx() - self.winfo_rootx()
        y = widget.winfo_rooty() - self.winfo_rooty()
        width = widget.winfo_width()
        height = widget.winfo_height()
        target = (x, y, x + width, y + height)
        if self._current is None:
            self._current = target
            self._render()
            return
        self._target = target
        if self._anim:
            self.after_cancel(self._anim)
        start = self._current
        steps = max(2, self._duration // 16)

        def step(index=0):
            ratio = min(1.0, (index + 1) / steps)
            eased = ratio * ratio * (3 - 2 * ratio)  # smoothstep
            self._current = tuple(a + (b - a) * eased for a, b in zip(start, target))
            self._render()
            if ratio < 1.0:
                self._anim = self.after(16, lambda: step(index + 1))
            else:
                self._anim = None

        self._anim = self.after(16, step)

    def _render(self):
        if not self._current:
            return
        self.delete('indicator')
        x0, y0, x1, y1 = self._current
        pad = 2
        radius = min(8.0, (y1 - y0) / 2)
        for item in rounded_rect(self, x0 + pad, y0 + pad, x1 - pad, y1 - pad,
                                 radius, fill=self._color):
            self.addtag_withtag('indicator', item)
        self.tag_lower('indicator')

    def cancel(self):
        if self._anim:
            self.after_cancel(self._anim)
            self._anim = None
