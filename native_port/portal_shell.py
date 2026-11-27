"""Base reutilizável do Portal dos Recomps ("kernel", no sentido Linux).

Esta camada não conhece Green Lantern, XEX, gráficos do jogo nem saves. Ela
fornece apenas o shell de desktop: tema, paleta, tipografia, logo, cabeçalho,
navegação animada, cartões arredondados, rodapé e animações. Cada recomp é uma
"distro": escolhe um ``PortalTheme`` e registra suas páginas.

Contrato preservado para as distros existentes e seus testes:

* nomes de estilos ttk (``Card.TFrame``, ``PresetOn.TButton``, ``H2.TLabel``…);
* atributos ``root``, ``tabs``, ``nav_buttons``, ``nav_lines``, ``status_bar``,
  ``footer_progress`` e as páginas nomeadas pelo próprio jogo;
* ordem das abas definida por quem chama ``build_shell(pages=...)``.

Uma distro deriva assim::

    class MeuLauncher(PortalShell):
        PAGES = (('play_tab', 'INÍCIO', '_build_play_tab'), ...)

        def __init__(self, root):
            theme = discover(PROJECT, override=ASTER_PORTAL_THEME)
            self.attach(root, theme, apply_to=globals())
            self.build_style()
            self.build_shell(PAGES, footer=self._build_footer)
            for _, _, builder in PAGES:
                getattr(self, builder)()
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from .portal_theme import PortalTheme, mix, shade
from .portal_widgets import ConstructNav, PortalMark, RoundedCard
from .flat_buttons import set_theme as set_button_theme

# Paleta ativa da base. ``apply_palette`` também exporta para o módulo da
# distro (via ``apply_to=globals()``), para que o código legado continue usando
# BG/CARD/ACCENT sem duplicar valores.
BG = PANEL = CARD = CARD_ALT = LINE = INK = MUTED = ACCENT = ''
ACCENT_DARK = WARN = WARN_BG = DANGER = FONT = ''


def palette_for(theme: PortalTheme) -> dict[str, str]:
    """Traduz um tema para os nomes de cor usados pelo shell Tk."""
    theme = theme.validate()
    return {
        'BG': theme.bg,
        'PANEL': theme.surface,
        'CARD': theme.surface,
        'CARD_ALT': theme.surface_2,
        'LINE': theme.line,
        'INK': theme.ink,
        'MUTED': theme.muted,
        'ACCENT': theme.accent,
        'ACCENT_DARK': mix(theme.bg, theme.accent, .22),
        'WARN': theme.warn,
        'WARN_BG': mix(theme.bg, theme.warn, .13),
        'DANGER': theme.danger,
        'FONT': theme.font,
    }


def apply_palette(theme: PortalTheme, *, apply_to: dict | None = None) -> dict[str, str]:
    """Aplica a paleta na base e, opcionalmente, no módulo da distro."""
    colors = palette_for(theme)
    globals().update(colors)
    if apply_to is not None:
        apply_to.update(colors)
    return colors


class PortalShell:
    """Shell de launcher independente de jogo."""

    DEFAULT_GEOMETRY = '1240x820'
    DEFAULT_MINSIZE = (1088, 720)

    # ------------------------------------------------------------- bootstrap
    def attach(self, root, theme: PortalTheme, *, title: str | None = None,
               geometry: str | None = None, apply_to: dict | None = None):
        """Vincula janela e tema. Chamar antes de ``build_style``."""
        self.root = root
        self.theme = (theme or PortalTheme()).validate()
        self.palette = apply_palette(self.theme, apply_to=apply_to)
        set_button_theme(self.theme)
        self.theme_error = None
        root.title(title or f'Portal dos Recomps | {self.theme.game}')
        root.geometry(geometry or self.DEFAULT_GEOMETRY)
        root.minsize(*self.DEFAULT_MINSIZE)
        root.configure(bg=BG)
        return self.palette

    # ----------------------------------------------------------------- style
    def build_style(self):
        """Estilos ttk com a identidade da distro, nomes inalterados."""
        style = ttk.Style(self.root)
        style.theme_use('clam')
        hover = shade(CARD_ALT, .10)
        soft = mix(BG, ACCENT, .12)
        inactive = mix(MUTED, BG, .42)
        style.configure('.', background=BG, foreground=INK, font=(FONT, 10))
        style.configure('TFrame', background=BG)
        style.configure('Card.TFrame', background=CARD)
        style.configure('Panel.TFrame', background=PANEL)
        style.configure('TLabel', background=BG, foreground=INK)
        style.configure('Card.TLabel', background=CARD, foreground=INK)
        style.configure('CardMuted.TLabel', background=CARD, foreground=MUTED)
        style.configure('Panel.TLabel', background=PANEL, foreground=MUTED)
        style.configure('Accent.TLabel', background=BG, foreground=ACCENT)
        style.configure('Warning.TLabel', background=CARD_ALT, foreground=WARN)
        style.configure('Title.TLabel', background=BG, foreground=INK, font=(FONT, 21, 'bold'))
        style.configure('H1.TLabel', background=CARD, foreground=INK, font=(FONT, 17, 'bold'))
        style.configure('H2.TLabel', background=CARD, foreground=INK, font=(FONT, 12, 'bold'))
        style.configure('Caps.TLabel', background=CARD, foreground=MUTED, font=(FONT, 8, 'bold'))
        style.configure('TButton', padding=(12, 8), background=CARD_ALT, foreground=INK,
                        borderwidth=0, focusthickness=0, relief='flat')
        style.map('TButton', background=[('active', hover), ('disabled', mix(BG, CARD_ALT, .55))],
                  foreground=[('disabled', inactive)])
        style.configure('Accent.TButton', padding=(24, 16), background=ACCENT,
                        foreground=mix(BG, ACCENT, .12), relief='flat',
                        font=('DejaVu Sans Condensed', 13, 'bold'))
        style.map('Accent.TButton', background=[('active', shade(ACCENT, .15)),
                                                ('disabled', mix(BG, ACCENT, .26))],
                  foreground=[('disabled', inactive)])
        style.configure('Secondary.TButton', padding=(14, 10), background=CARD_ALT,
                        foreground=INK, relief='flat')
        style.map('Secondary.TButton', background=[('active', hover),
                                                    ('disabled', mix(BG, CARD_ALT, .55))])
        style.configure('Ghost.TButton', padding=(10, 7), background=PANEL, foreground=MUTED,
                        relief='flat')
        style.map('Ghost.TButton', background=[('active', soft)])
        style.configure('Danger.TButton', padding=(12, 8), background=mix(BG, DANGER, .22),
                        foreground=DANGER, relief='flat')
        style.map('Danger.TButton', background=[('active', mix(BG, DANGER, .34)),
                                                ('disabled', mix(BG, DANGER, .11))],
                  foreground=[('disabled', inactive)])
        style.configure('Preset.TButton', padding=(10, 11), background=CARD_ALT, foreground=INK,
                        font=(FONT, 9), relief='flat')
        style.map('Preset.TButton', background=[('active', hover)])
        style.configure('PresetOn.TButton', padding=(10, 11), background=ACCENT_DARK,
                        foreground=ACCENT, font=(FONT, 9, 'bold'), relief='flat')
        style.map('PresetOn.TButton', background=[('active', mix(ACCENT_DARK, ACCENT, .16))])
        style.configure('TNotebook', background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
        style.configure('Modern.TNotebook', background=BG, borderwidth=0,
                        bordercolor=BG, lightcolor=BG, darkcolor=BG)
        style.layout('Modern.TNotebook.Tab', [])
        style.configure('TNotebook.Tab', padding=(20, 10), background=BG, foreground=MUTED,
                        font=(FONT, 10, 'bold'), borderwidth=0)
        style.map('TNotebook.Tab', background=[('selected', CARD), ('active', CARD_ALT)],
                  foreground=[('selected', ACCENT), ('active', INK)])
        style.configure('TEntry', fieldbackground=BG, foreground=INK, insertcolor=INK,
                        bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, padding=8)
        style.configure('TCombobox', fieldbackground=BG, foreground=INK, arrowcolor=MUTED,
                        bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, padding=6)
        style.map('TCombobox', fieldbackground=[('readonly', BG)], foreground=[('readonly', INK)])
        style.configure('TSpinbox', fieldbackground=BG, foreground=INK, arrowcolor=MUTED,
                        bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, padding=6)
        style.configure('TCheckbutton', background=CARD, foreground=INK, font=(FONT, 10))
        style.map('TCheckbutton', background=[('active', CARD)], foreground=[('disabled', MUTED)])
        style.configure('Treeview', background=BG, fieldbackground=BG, foreground=INK, rowheight=27,
                        borderwidth=0)
        style.configure('Treeview.Heading', background=PANEL, foreground=MUTED,
                        font=(FONT, 9, 'bold'))
        style.configure('Horizontal.TProgressbar', background=ACCENT, troughcolor=CARD_ALT,
                        bordercolor=CARD_ALT, lightcolor=ACCENT, darkcolor=ACCENT, thickness=6)
        # Observação: os botões do launcher são ``FlatButton`` (tk.Button com PNG
        # arredondado, ver ``flat_buttons``). O ttk ``element_create`` não gera
        # transparência real, então não substituímos o layout dos estilos ttk.

    # ------------------------------------------------------------- primitivas
    def card(self, parent, **pack_options):
        """Cartão arredondado que continua sendo um ``tk.Frame``."""
        card = RoundedCard(parent, fill=CARD, outline=LINE, radius=20)
        card.pack(**pack_options)
        return card

    def caps(self, parent, text, bg=None):
        """Rótulo de seção curto, em destaque e alinhado à esquerda."""
        return tk.Label(parent, text=text.upper(), bg=bg or CARD, fg=ACCENT,
                        font=(FONT, 9, 'bold'), anchor='w')

    # ------------------------------------------------------------------ shell
    def build_shell(self, pages, *, footer: Callable | None = None):
        """Monta logo, cabeçalho, navegação, abas e rodapé.

        ``pages`` é uma sequência de ``(nome_do_atributo, título, builder)``.
        As páginas são criadas aqui e preenchidas depois pela distro, para que
        ``nav_buttons`` e a ordem das abas existam antes de qualquer refresh.
        """
        shell = tk.Frame(self.root, bg=BG)
        shell.pack(fill='both', expand=True)

        # Sidebar fixa: identidade do jogo e constructos de navegação.
        sidebar = tk.Frame(shell, bg=PANEL, width=226)
        sidebar.pack(side='left', fill='y')
        sidebar.pack_propagate(False)

        brand = tk.Frame(sidebar, bg=PANEL, padx=16, pady=20)
        brand.pack(fill='x')
        self.logo = PortalMark(brand, theme=self.theme, size=46)
        self.logo.pack(anchor='w', pady=(0, 8))
        tk.Label(brand, text=self.theme.game.upper(), bg=PANEL, fg=INK,
                 font=('DejaVu Sans Condensed', 18, 'bold'), wraplength=192,
                 justify='left').pack(anchor='w')
        tk.Label(brand, text=self.theme.subtitle.upper(), bg=PANEL, fg=ACCENT,
                 font=(FONT, 8, 'bold'), wraplength=192,
                 justify='left').pack(anchor='w', pady=(2, 0))
        tk.Label(brand, text=self.theme.edition, bg=PANEL, fg=MUTED,
                 font=(FONT, 8)).pack(anchor='w', pady=(5, 0))

        side_bottom = tk.Frame(sidebar, bg=PANEL, padx=16, pady=12)
        side_bottom.pack(side='bottom', fill='x')
        tk.Label(side_bottom, text='XBOX 360 → PC', bg=PANEL, fg=MUTED,
                 font=(FONT, 7, 'bold')).pack(anchor='w')
        tk.Label(side_bottom, text=self.theme.edition.upper(), bg=PANEL, fg=ACCENT,
                 font=(FONT, 8, 'bold')).pack(anchor='w', pady=(2, 0))

        navigation = tk.Frame(sidebar, bg=PANEL, padx=8)
        navigation.pack(fill='both', expand=True, pady=(4, 0))
        self.nav_buttons, self.nav_lines, self.nav_constructs = {}, {}, {}

        main = tk.Frame(shell, bg=BG)
        main.pack(side='left', fill='both', expand=True)
        self.tabs = ttk.Notebook(main, style='Modern.TNotebook')
        self.tabs.pack(fill='both', expand=True)
        self.hd_tab = tk.Toplevel(self.root, bg=BG, padx=18, pady=14)
        self.hd_tab.title(f'{self.theme.game} · ferramentas avançadas')
        self.hd_tab.geometry('900x330')
        self.hd_tab.withdraw()
        self.hd_tab.protocol('WM_DELETE_WINDOW', self.hd_tab.withdraw)

        icons = {'INÍCIO': '⌂', 'GRÁFICOS': '◈', 'CONTROLES': '⌁', 'PREPARAR': '⚙',
                 'JOGO': '▣', 'DIAGNÓSTICO': '◎', 'ATUALIZAÇÕES': '↻'}
        for attr, title, _builder in pages:
            page = tk.Frame(self.tabs, bg=BG,
                            padx=20 if attr == 'play_tab' else 24,
                            pady=8 if attr == 'play_tab' else 16)
            setattr(self, attr, page)
            self.tabs.add(page, text=title)
            construct = ConstructNav(navigation, text=f'{icons.get(title, "·")}  {title}',
                                     theme=self.theme, height=44,
                                     command=lambda tab=page: self.tabs.select(tab))
            construct.pack(fill='x', pady=(0, 3))
            self.nav_constructs[str(page)] = construct
            self.nav_buttons[str(page)] = construct.button
            self.nav_lines[str(page)] = None

        def navigation_changed(_=None):
            selected = self.tabs.select()
            for page, construct in self.nav_constructs.items():
                construct.set_active(page == selected)

        self.tabs.bind('<<NotebookTabChanged>>', navigation_changed)
        self._navigation_changed = navigation_changed

        footer_frame = tk.Frame(main, bg=BG, padx=20, pady=12)
        footer_frame.pack(side='bottom', fill='x', before=self.tabs)
        # Grade: status à esquerda (elástico), ações reservadas à direita.
        footer_frame.columnconfigure(0, weight=1)
        footer_frame.rowconfigure(0, weight=1)
        actions = tk.Frame(footer_frame, bg=BG)
        actions.grid(row=0, column=1, sticky='e')
        status = tk.Frame(footer_frame, bg=BG)
        status.grid(row=0, column=0, sticky='nsew', padx=(0, 16))
        self.status_bar = tk.Label(status, textvariable=self.status_display, bg=BG, fg=MUTED,
                                   anchor='w', justify='left', font=(FONT, 10), wraplength=570)
        self.status_bar.pack(fill='x', expand=True)
        self.footer_progress = ttk.Progressbar(status, variable=self.task_progress,
                                               mode='determinate', maximum=100)
        self.footer_progress.pack(fill='x', pady=(9, 0))
        status.bind('<Configure>', lambda e: self.status_bar.configure(
            wraplength=max(150, e.width - 8)))

        if footer is not None:
            footer(footer_frame, actions, status)
        navigation_changed()
        return pages

    def cancel_animations(self):
        """Cancela timers decorativos antes de destruir a janela."""
        for construct in getattr(self, 'nav_constructs', {}).values():
            try:
                construct.cancel()
            except (AttributeError, tk.TclError):
                pass
        for name in ('nav_indicator',):
            widget = getattr(self, name, None)
            if widget is not None:
                try:
                    widget.cancel()
                except (AttributeError, tk.TclError):
                    pass
