"""Botões ``tk.Button`` com cantos arredondados, sem assets externos.

O ttk ``element_create`` não consegue transparência real: o motor de tema
desenha um retângulo opaco por trás da imagem, então os cantos "transparentes"
aparecem na cor de fundo do estilo (quadrado). A solução confiável é um
``tk.Button`` cuja imagem PNG tem cantos arredondados e cujo ``bg`` é herdado
do container — aí os cantos mostram exatamente a cor de trás do botão.

Para não reescrever as dezenas de chamadas ``ttk.Button(..., style='X')`` do
launcher, :func:`flat_button` é um *drop-in*: aceita os mesmos argumentos
(inclusive ``style`` como nome de estilo ttk) e traduz o estilo para uma
paleta de cores derivada do ``PortalTheme`` ativo. A API pública do widget
continua sendo a de um ``tk.Button`` (``configure``, ``invoke``, ``cget``),
então os testes existentes seguem funcionando.

O Tk clássico não desenha a imagem quando o ``Button`` está ``disabled`` (só o
texto aparece), então o estado "desativado" é simulado: a cor de preenchimento
muda para o tom desativado e ``invoke`` deixa de chamar o comando, enquanto
``['state']``/``cget('state')`` continuam informando ``'disabled'``.
"""
from __future__ import annotations

import tkinter as tk

from .portal_theme import PortalTheme, mix, shade
from .rounded_buttons import button_photo

# Tema ativo, registrado pelo shell (``PortalShell``) e pela distro.
_ACTIVE = {'theme': None}


def set_theme(theme):
    """Define o tema usado para derivar as cores dos botões."""
    _ACTIVE['theme'] = theme.validate() if theme is not None else None


def active_theme():
    return _ACTIVE['theme'] or PortalTheme().validate()


def _parent_bg(parent):
    try:
        bg = parent.cget('bg')
        if bg:
            return str(bg)
    except tk.TclError:
        pass
    return active_theme().bg


def spec_for(style):
    """Traduz um nome de estilo ttk na paleta do botão arredondado."""
    t = active_theme()
    card_alt = t.surface_2
    accent, ink, muted = t.accent, t.ink, t.muted
    name = (style or 'TButton').strip()
    if name == 'Accent.TButton':
        return {'fill': accent, 'fg': mix(t.bg, accent, .16),
                'hover': shade(accent, .12),
                'disabled': mix(t.bg, accent, .42),
                'disabled_fg': mix(t.bg, accent, .18),
                'radius': 14, 'padx': 16, 'pady': 10}
    if name == 'Danger.TButton':
        return {'fill': mix(t.bg, t.danger, .24), 'fg': t.danger,
                'hover': mix(t.bg, t.danger, .38),
                'disabled': mix(t.bg, t.danger, .12),
                'disabled_fg': mix(t.bg, t.danger, .40),
                'radius': 12, 'padx': 10, 'pady': 7}
    if name == 'Secondary.TButton':
        return {'fill': card_alt, 'fg': ink, 'hover': shade(card_alt, .12),
                'disabled': mix(t.bg, card_alt, .55),
                'disabled_fg': mix(t.muted, t.bg, .42),
                'radius': 12, 'padx': 10, 'pady': 7}
    if name == 'Ghost.TButton':
        return {'fill': mix(t.bg, card_alt, .30), 'fg': muted,
                'hover': mix(t.bg, card_alt, .55),
                'disabled': mix(t.bg, card_alt, .18),
                'disabled_fg': mix(t.bg, card_alt, .45),
                'radius': 12, 'padx': 9, 'pady': 6}
    if name in ('Preset.TButton', 'PresetOn.TButton'):
        on = name == 'PresetOn.TButton'
        return {'fill': mix(t.bg, accent, .22) if on else card_alt,
                'fg': accent if on else ink, 'hover': mix(t.bg, accent, .34),
                'disabled': card_alt, 'disabled_fg': t.muted,
                'radius': 10, 'padx': 8, 'pady': 8}
    return {'fill': card_alt, 'fg': ink, 'hover': shade(card_alt, .10),
            'disabled': mix(t.bg, card_alt, .55),
            'disabled_fg': mix(t.muted, t.bg, .42),
            'radius': 12, 'padx': 10, 'pady': 7}


class FlatButton(tk.Button):
    """``tk.Button`` que desenha borda arredondada com PNG gerado em memória."""

    def __init__(self, parent, text='', command=None, *, style=None,
                 state='normal', takefocus=True, **kwargs):
        spec = dict(spec_for(style))
        self._radius = spec.pop('radius')
        padx, pady = spec.pop('padx'), spec.pop('pady')
        kwargs.setdefault('padx', padx)
        kwargs.setdefault('pady', pady)
        self._bg = _parent_bg(parent)
        self._spec = spec
        self._command = command
        self._style_name = style or 'TButton'
        self._disabled = state == 'disabled'
        super().__init__(parent, text=text, bg=self._bg, fg=spec['fg'],
                         relief='flat', bd=0, highlightthickness=0,
                         activebackground=self._bg,
                         activeforeground=spec['fg'],
                         disabledforeground=spec['disabled_fg'],
                         compound='center', cursor='hand2',
                         takefocus=takefocus, command=self._invoke, **kwargs)
        self._hover = False
        self._photos = {}
        self._all_photos = []
        self._img_size = None
        self._base_dirty = True
        self._render_job = None
        self.bind('<Enter>', lambda _e: self._set_hover(True), add='+')
        self.bind('<Leave>', lambda _e: self._set_hover(False), add='+')
        self.after(1, self._render)

    # ------------------------------------------------------------- estado "real"
    def _invoke(self):
        if not self._disabled and self._command:
            return self._command()

    def invoke(self):
        return self._invoke()

    def cget(self, key):
        if key == 'state':
            return 'disabled' if self._disabled else 'normal'
        if key == 'style':
            return self._style_name
        return super().cget(key)

    def __getitem__(self, key):
        if key == 'state':
            return 'disabled' if self._disabled else 'normal'
        if key == 'style':
            return self._style_name
        return super().__getitem__(key)

    def _set_state(self, value):
        self._disabled = value == 'disabled'
        self._schedule()

    # ---------------------------------------------------------------- pintura
    def _pad(self):
        try:
            return int(super().cget('padx') or 0), int(super().cget('pady') or 0)
        except (tk.TclError, ValueError):
            return 0, 0

    def _measure(self):
        """Tamanho natural (texto + padding), medido sem nenhuma imagem."""
        super().configure(image='')
        try:
            self.update_idletasks()
            return self.winfo_reqwidth(), self.winfo_reqheight()
        finally:
            pass

    def _render(self):
        self._render_job = None
        if not self.winfo_exists():
            return
        if self._base_dirty or self._img_size is None:
            w, h = self._measure()
            if w < 2 or h < 2:
                return
            self._img_size = (w + 1, h + 1)
            self._base_dirty = False
            self._photos.clear()
        padx, pady = self._pad()
        bw, bh = self._img_size
        img_w, img_h = max(2, bw - 2 * padx), max(2, bh - 2 * pady)
        key = (self._disabled, self._hover)
        photo = self._photos.get(key)
        if photo is None:
            fill = (self._spec['disabled'] if self._disabled else
                    self._spec['hover'] if self._hover else self._spec['fill'])
            photo = button_photo(self, fill, fill, width=img_w, height=img_h,
                                 radius=self._radius)
            self._photos[key] = photo
            self._all_photos.append(photo)
        if str(photo) != str(super().cget('image') or ''):
            fg = (self._spec['disabled_fg'] if self._disabled
                  else self._spec['fg'])
            # O tamanho da imagem é fixo (texto + padding), então aplicar não
            # realtera o "requested": não há laço de <Configure>.
            super().configure(image=photo, foreground=fg,
                              cursor='arrow' if self._disabled else 'hand2')

    def _schedule(self):
        if self._render_job:
            try:
                self.after_cancel(self._render_job)
            except tk.TclError:
                pass
        # Aumentar de 2ms para 50ms reduz flickering em transições rápidas
        self._render_job = self.after(50, self._render)

    def _set_hover(self, hovered):
        if self._hover != bool(hovered) and not self._disabled:
            self._hover = bool(hovered)
            self._render()

    # ------------------------------------------------------- configure patched
    def configure(self, *args, **kwargs):
        state = None
        if args and isinstance(args[0], dict):
            state = args[0].pop('state', None)
            if 'command' in args[0]:
                self._command = args[0].pop('command')
            args = (args[0], *args[1:]) if args[0] else args[1:]
        if 'state' in kwargs:
            state = kwargs.pop('state')
        if 'command' in kwargs:
            self._command = kwargs.pop('command')
        if 'style' in kwargs:
            self._style_name = kwargs.pop('style')
            self._spec.update(spec_for(self._style_name))
            self._radius = self._spec.pop('radius')
            self._base_dirty = True
            self._photos.clear()
        relayout = kwargs.keys() & {'text', 'font', 'padx', 'pady'}
        if args and isinstance(args[0], dict):
            relayout = bool(args[0].keys() & {'text', 'font', 'padx', 'pady'})
        if relayout:
            self._base_dirty = True
            self._photos.clear()
        if state is not None:
            self._set_state(state)
        super().configure(*args, **kwargs)
        self._schedule()
        return None

    def destroy(self):
        job = self._render_job
        if job:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        super().destroy()


def flat_button(parent, text='', command=None, *, style=None, state='normal',
                **kwargs):
    """Compatível com ``ttk.Button``; devolve um :class:`FlatButton`."""
    return FlatButton(parent, text=text, command=command, style=style,
                      state=state, **kwargs)