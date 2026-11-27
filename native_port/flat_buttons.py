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
                'radius': 4, 'padx': 31, 'pady': 18}
    if name == 'Danger.TButton':
        return {'fill': mix(t.bg, t.danger, .24), 'fg': t.danger,
                'hover': mix(t.bg, t.danger, .38),
                'disabled': mix(t.bg, t.danger, .12),
                'disabled_fg': mix(t.bg, t.danger, .40),
                'radius': 4, 'padx': 23, 'pady': 14}
    if name == 'Secondary.TButton':
        return {'fill': card_alt, 'fg': ink, 'hover': shade(card_alt, .12),
                'disabled': mix(t.bg, card_alt, .55),
                'disabled_fg': mix(t.muted, t.bg, .42),
                'radius': 4, 'padx': 23, 'pady': 14}
    if name == 'Ghost.TButton':
        return {'fill': mix(t.bg, card_alt, .30), 'fg': muted,
                'hover': mix(t.bg, card_alt, .55),
                'disabled': mix(t.bg, card_alt, .18),
                'disabled_fg': mix(t.bg, card_alt, .45),
                'radius': 4, 'padx': 19, 'pady': 13}
    if name in ('Preset.TButton', 'PresetOn.TButton'):
        on = name == 'PresetOn.TButton'
        return {'fill': mix(t.bg, accent, .22) if on else card_alt,
                'fg': accent if on else ink, 'hover': mix(t.bg, accent, .34),
                'disabled': card_alt, 'disabled_fg': t.muted,
                'radius': 4, 'padx': 16, 'pady': 14}
    return {'fill': card_alt, 'fg': ink, 'hover': shade(card_alt, .10),
            'disabled': mix(t.bg, card_alt, .55),
            'disabled_fg': mix(t.muted, t.bg, .42),
            'radius': 4, 'padx': 23, 'pady': 14}


class FlatButton(tk.Button):
    """``tk.Button`` que desenha borda arredondada com PNG gerado em memória."""

    def __init__(self, parent, text='', command=None, *, style=None,
                 state='normal', takefocus=True, reserve_text=None, **kwargs):
        spec = dict(spec_for(style))
        self._radius = spec.pop('radius')
        padx, pady = spec.pop('padx'), spec.pop('pady')
        # O padding é aplicado *dentro* da imagem de fundo (a "cápsula"), não
        # como área transparente ao redor dela. Assim o texto fica com margem
        # e o fundo cobre toda a área do botão.
        self._pad_x = int(kwargs.pop('padx', padx))
        self._pad_y = int(kwargs.pop('pady', pady))
        kwargs.setdefault('padx', 0)
        kwargs.setdefault('pady', 0)
        self._bg = _parent_bg(parent)
        self._spec = spec
        self._command = command
        self._style_name = style or 'TButton'
        self._disabled = state == 'disabled'
        # ``reserve_text`` reserva a largura do rótulo mais longo do botão:
        # assim trocar o texto (ex.: 'JOGAR' → 'GERAR PORT NATIVO') não encolhe
        # nem expande o widget, evitando deslocamento de layout e piscagem.
        self._reserve_text = reserve_text
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
        self._render_job = self.after(1, self._render)

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
        return self._pad_x, self._pad_y

    def _measure(self):
        """Tamanho natural (texto + padding), medido sem tocar no botão visível.

        Medir o próprio botão exigiria ``configure(image='')`` — e isso remove
        a imagem aplicada e força o Tk a repintar o widget sem a borda
        arredondada. Esse ``configure`` + ``update_idletasks`` é a origem da
        piscagem vista a cada troca de texto. Um widget-filho **nunca
        mapeado** (sem ``pack``/``grid``/``place``) calcula o mesmo tamanho
        requisitado sem repintar nada na tela.
        """
        text = self._reserve_text or str(super().cget('text'))
        if not text:
            # Sem texto (só imagem): o tamanho atual já é o correto.
            return super().winfo_reqwidth(), super().winfo_reqheight()
        padx, pady = self._pad()
        probe = tk.Button(self, text=text, font=super().cget('font'),
                          padx=padx, pady=pady, relief='flat', bd=0,
                          highlightthickness=0, compound='center')
        try:
            probe.update_idletasks()
            return probe.winfo_reqwidth(), probe.winfo_reqheight()
        finally:
            probe.destroy()

    def _render(self):
        self._render_job = None
        if not self.winfo_exists():
            return
        if self._base_dirty or self._img_size is None:
            w, h = self._measure()
            if w < 2 or h < 2:
                return
            measured = (w + 1, h + 1)
            if measured != self._img_size:
                # Só descarta as fotos quando o tamanho realmente muda. Com
                # ``reserve_text`` todas as variações de texto medem o mesmo
                # tamanho, então as imagens já geradas são reutilizadas e nada
                # é repintado — nenhuma piscagem ao trocar o rótulo.
                self._img_size = measured
                self._photos.clear()
            self._base_dirty = False
        bw, bh = self._img_size
        # A imagem cobre todo o botão; o padding já está embutido na medição,
        # então o texto fica centralizado com margem dentro da cápsula.
        img_w, img_h = bw, bh
        key = (self._disabled, self._hover)
        photo = self._photos.get(key)
        if photo is None:
            fill = (self._spec['disabled'] if self._disabled else
                    self._spec['hover'] if self._hover else self._spec['fill'])
            photo = button_photo(self, fill, fill, width=img_w, height=img_h,
                                 radius=self._radius)
            self._photos[key] = photo
            self._all_photos.append(photo)
        current_image = super().cget('image')
        if current_image == '' or str(photo) != str(current_image):
            fg = (self._spec['disabled_fg'] if self._disabled
                  else self._spec['fg'])
            super().configure(image=photo, foreground=fg,
                              cursor='arrow' if self._disabled else 'hand2')

    def _schedule(self):
        """Repinta imediatamente, sem atraso.

        Adiar com ``after()`` deixava o botão exibindo a cor/estado anteriores
        por alguns quadros antes de trocar — a origem exata da piscagem (cor
        antiga → cor nova). Com as fotos em cache, repintar de forma síncrona
        custa uma consulta de dicionário; a geração da PNG só ocorre quando o
        tamanho, o estilo ou o estado realmente mudam.
        """
        self._render()

    def _set_hover(self, hovered):
        if self._hover != bool(hovered) and not self._disabled:
            self._hover = bool(hovered)
            self._render()

    # ------------------------------------------------------- configure patched
    def configure(self, *args, **kwargs):
        state = None
        options = args[0] if args and isinstance(args[0], dict) else None
        relayout = bool(kwargs.keys() & {'text', 'font', 'padx', 'pady'})
        if options is not None:
            relayout = relayout or bool(options.keys() & {'text', 'font', 'padx', 'pady'})
            state = options.pop('state', None)
            if 'command' in options:
                self._command = options.pop('command')
            if 'padx' in options:
                self._pad_x = int(options.pop('padx'))
            if 'pady' in options:
                self._pad_y = int(options.pop('pady'))
            args = (options, *args[1:]) if options else args[1:]
        if 'state' in kwargs:
            state = kwargs.pop('state')
        if 'command' in kwargs:
            self._command = kwargs.pop('command')
        if 'padx' in kwargs:
            self._pad_x = int(kwargs.pop('padx'))
        if 'pady' in kwargs:
            self._pad_y = int(kwargs.pop('pady'))
        if 'style' in kwargs:
            self._style_name = kwargs.pop('style')
            self._spec.update(spec_for(self._style_name))
            self._radius = self._spec.pop('radius')
            self._base_dirty = True
            self._photos.clear()
        if relayout:
            # A foto gerada NÃO contém texto — é somente o fundo arredondado.
            # Por isso trocar o rótulo não invalida as imagens: ``_render``
            # re-mede e só descarta as fotos se o tamanho realmente mudar.
            # Descartar aqui regeneraria PNGs a cada troca de texto, criando
            # lentidão e trocas de imagem desnecessárias.
            self._base_dirty = True
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