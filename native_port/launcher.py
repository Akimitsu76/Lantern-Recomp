"""Tk desktop launcher for the local Green Lantern port.

The launcher only stores its own preferences. Game saves, cache and runtime
data share one per-user profile under .aster/runtime; graphics choices are
translated to command-line CVars and never written into the game profile.
"""
from __future__ import annotations

import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from games.green_lantern import GreenLantern
from . import graphics, settings
from .native_build import build_native, read_install, INTEGRATION_VERSION
from .paths import project_root, python_command, external_env
from .diagnostics import diagnostics
from .errors import PortError
from .pipeline import prepare
from .sources import inspect_source
from .tasks import Cancellation
from .workspace import Workspace

PROJECT = project_root(__file__)
BG = '#0b0e12'
PANEL = '#10151c'
CARD = '#151c25'
CARD_ALT = '#1c2632'
LINE = '#293443'
INK = '#f0f4f8'
MUTED = '#94a3b7'
ACCENT = '#b4ed74'
ACCENT_DARK = '#263b25'
WARN = '#ffcc66'
WARN_BG = '#2b2519'
DANGER = '#ff9b8f'
FONT = 'DejaVu Sans'
MONO = 'DejaVu Sans Mono'

MODE_FILES = {
    '30': ('.aster/build/rex-green/aster_green_lantern',
           '.aster/reports/rexglue-runtime-probe.json'),
    '60': ('.aster/build/rex-fps-validation-v9/aster_green_lantern',
           '.aster/reports/rexglue-runtime-probe-60fps.json'),
    'unlimited': ('.aster/build/rex-fps-unlimited-v10/aster_green_lantern',
                  '.aster/reports/rexglue-runtime-probe-unlimited.json'),
}
PROFILE_FILES = {
    '30': '.aster/runtime/green-lantern',
    '60': '.aster/runtime/green-lantern',
    'unlimited': '.aster/runtime/green-lantern',
}
TARGET_TITLES = {
    '30': 'Jogar 30 fps',
    '60': 'Jogar 60 fps experimental',
    'unlimited': 'Jogar ilimitado experimental',
}
ANISO_LABELS = dict(graphics.ANISOTROPIC_LABELS)
ANISO_BY_LABEL = {label: value for value, label in ANISO_LABELS.items()}
TEXTURE_BY_LABEL = {label: value for value, label in graphics.TEXTURE_QUALITY_LABELS.items()}
BUILD_STAGES = (
    ('dump', 'Conferir o dump', 'Identidade e integridade dos arquivos'),
    ('tools', 'Preparar ferramentas', 'SDK e ambiente de compilação'),
    ('cache', 'Preparar gráficos', 'Cache e bibliotecas da plataforma'),
    ('codegen', 'Gerar código nativo', 'Traduzir o executável para este PC'),
    ('compile', 'Compilar o port', 'Construir o executável e seus componentes'),
    ('verify', 'Verificar instalação', 'Conferir os arquivos gerados'),
)


class Launcher:
    def __init__(self, root):
        self.root = root
        root.title('Aster Native | Green Lantern')
        root.geometry('1160x800')
        root.minsize(1088, 720)
        root.configure(bg=BG)
        self.queue, self.events = queue.Queue(), []
        self.busy, self.cancel = False, Cancellation()
        self.last_result, self.last_environment = None, None
        self.selected_folder = None
        self.closed = False
        self.experimental_process = None
        self.experimental_lock = threading.Lock()
        self.settings_warning = None
        self._syncing = False
        self._vsync_preference = True
        try:
            cfg = settings.load(PROJECT)
        except PortError as exc:
            cfg, self.settings_warning = settings.defaults(PROJECT), exc.as_dict()
        self.cfg = cfg
        self.source = tk.StringVar(value=cfg['source'])
        self.workspace = tk.StringVar(value=cfg['workspace'])
        self.build_type = tk.StringVar(value=cfg['build_type'])
        self.jobs = tk.IntVar(value=cfg['jobs'])
        self.hd_texture_pack = tk.StringVar(value=cfg['hd_texture_pack'])
        self.hd_texture_catalog = tk.StringVar(value=cfg['hd_texture_catalog'])
        self.hd_status = tk.StringVar(value='Texturas originais · nenhum pacote selecionado')
        self.hd_material_count = None
        self.hd_running = False
        self.graphics_preset = tk.StringVar(value=cfg['graphics']['preset'])
        self.fps_target = tk.StringVar(value=cfg['graphics']['fps_target'])
        self.vsync = tk.BooleanVar(value=cfg['graphics']['vsync'])
        self.shader_mode = tk.StringVar(value=cfg['graphics']['shader_mode'])
        self.shader_preload = tk.BooleanVar(value=cfg['graphics']['shader_preload'])
        self.antialiasing = tk.StringVar(value=graphics.ANTIALIASING_LABELS[cfg['graphics']['antialiasing']])
        self.upscaler = tk.StringVar(value=graphics.UPSCALER_LABELS[cfg['graphics']['upscaler']])
        self.output_resolution = tk.StringVar(value=cfg['graphics']['output_resolution'])
        self.fullscreen = tk.BooleanVar(value=cfg['graphics']['fullscreen'])
        self.fsr_sharpness = tk.IntVar(value=cfg['graphics']['fsr_sharpness'])
        self.custom_render_scale = tk.IntVar(value=cfg['graphics']['render_scale'])
        self.custom_msaa = tk.BooleanVar(value=cfg['graphics']['msaa_2x'])
        self.custom_aniso = tk.StringVar(value=ANISO_LABELS.get(cfg['graphics']['anisotropic'],
                                                               ANISO_LABELS[3]))
        self.custom_texture = tk.StringVar(
            value=graphics.TEXTURE_QUALITY_LABELS.get(cfg['graphics']['texture_quality'], 'Padrão'))
        self.custom_dither = tk.BooleanVar(value=cfg['graphics']['present_dither'])
        self._vsync_preference = bool(cfg['graphics']['vsync'])
        self.status = tk.StringVar(value='Pronto para selecionar o dump e revisar as opções gráficas.')
        self.environment_status = tk.StringVar(value='Ambiente / diagnóstico não executado')
        self.source_status = tk.StringVar(value='Jogo / entrada ainda não validada')
        self.output_status = tk.StringVar(value='Artefato / compilação integral ainda não validada')
        self.engine_status = tk.StringVar(value='Build local: verificando…')
        self.graphics_summary = tk.StringVar(value='')
        self.warning_text = tk.StringVar(value='')
        self.quick_target = tk.StringVar(value='')
        self.quick_graphics = tk.StringVar(value='')
        self.quick_profile = tk.StringVar(value='')
        self.report_path = tk.StringVar(value='Relatórios ficam dentro do diretório de trabalho.')
        self.preset_buttons, self.target_buttons = {}, {}
        self.stage_states = {key: 'pending' for key, *_ in BUILD_STAGES}
        self.active_stage = None
        self.build_heading = tk.StringVar(value='Seu dump. Uma versão para o seu PC.')
        self.build_detail = tk.StringVar(value='Selecione a pasta do jogo na Biblioteca para começar.')
        self.build_count = tk.StringVar(value='0 de 6 etapas concluídas')
        self.build_measure = tk.StringVar(value='Aguardando início')
        self.build_elapsed = tk.StringVar(value='00:00')
        self.build_running = False
        self.task_started = time.monotonic()
        self._build_style()
        self._build_shell()
        self._set_graphics_vars(cfg['graphics'])
        self._refresh_graphics_ui()
        self._refresh_engine_status()
        self._refresh_play_state()
        self.status.set(self._idle_status())
        self.workspace.trace_add('write', lambda *_: self.refresh_paths())
        self.source.trace_add('write', lambda *_: self._refresh_play_state())
        for variable in (self.custom_render_scale, self.custom_msaa,
                         self.custom_aniso, self.custom_texture, self.custom_dither):
            variable.trace_add('write', lambda *_: self._on_custom_changed())
        self.fsr_sharpness.trace_add('write', lambda *_: self._refresh_graphics_ui() if not self._syncing else None)
        self.fps_target.trace_add('write', lambda *_: self._on_target_changed())
        self.vsync.trace_add('write', lambda *_: self._on_vsync_changed())
        self.refresh_paths()
        if self.settings_warning:
            self.log({'task': 'Carregar configuração', 'error': self.settings_warning})
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.after_id = root.after(50, self.poll)

    # ------------------------------------------------------------------ style
    def _build_style(self):
        style = ttk.Style(self.root)
        style.theme_use('clam')
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
                        borderwidth=0, focusthickness=0)
        style.map('TButton', background=[('active', '#29434d'), ('disabled', '#1b282e')],
                  foreground=[('disabled', '#6c8185')])
        style.configure('Accent.TButton', padding=(24, 16), background=ACCENT,
                        foreground='#06231a', font=(FONT, 12, 'bold'))
        style.map('Accent.TButton', background=[('active', '#8af0c7'), ('disabled', '#29473e')],
                  foreground=[('disabled', '#6c8b81')])
        style.configure('Secondary.TButton', padding=(14, 10), background=CARD_ALT, foreground=INK)
        style.map('Secondary.TButton', background=[('active', '#29434d'), ('disabled', '#1b282e')])
        style.configure('Ghost.TButton', padding=(10, 7), background=PANEL, foreground=MUTED)
        style.map('Ghost.TButton', background=[('active', '#1d3039')])
        style.configure('Danger.TButton', padding=(12, 8), background='#3a2224', foreground=DANGER)
        style.map('Danger.TButton',
                  background=[('active', '#4a2a2d'), ('disabled', '#26191b')],
                  foreground=[('disabled', '#725257')])
        style.configure('Preset.TButton', padding=(10, 11), background=CARD_ALT, foreground=INK,
                        font=(FONT, 9))
        style.map('Preset.TButton', background=[('active', '#29434d')])
        style.configure('PresetOn.TButton', padding=(10, 11), background=ACCENT_DARK,
                        foreground=ACCENT, font=(FONT, 9, 'bold'))
        style.map('PresetOn.TButton', background=[('active', '#1b5143')])
        style.configure('TNotebook', background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
        style.configure('Modern.TNotebook', background=BG, borderwidth=0,
                        bordercolor=BG, lightcolor=BG, darkcolor=BG)
        style.layout('Modern.TNotebook.Tab', [])
        style.configure('TNotebook.Tab', padding=(22, 12), background=BG, foreground=MUTED,
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
                        bordercolor=CARD_ALT, lightcolor=ACCENT, darkcolor=ACCENT, thickness=8)

    def _card(self, parent, **pack_options):
        card = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        card.pack(**pack_options)
        return card

    def _caps(self, parent, text, bg=CARD):
        return tk.Label(parent, text=text.upper(), bg=bg, fg=MUTED,
                        font=(FONT, 8, 'bold'), anchor='w')

    # ------------------------------------------------------------------- shell
    def _build_shell(self):
        shell = tk.Frame(self.root, bg=BG, padx=22, pady=12)
        shell.pack(fill='both', expand=True)
        header = tk.Frame(shell, bg=BG)
        header.pack(fill='x', pady=(0, 8))
        brand = tk.Frame(header, bg=BG)
        brand.pack(side='left', fill='x', expand=True)
        tk.Label(brand, text='ASTER', bg=BG, fg=ACCENT,
                 font=(FONT, 22, 'bold')).pack(side='left')
        tk.Label(brand, text='  NATIVE   /   SUA BIBLIOTECA', bg=BG, fg=MUTED,
                 font=(FONT, 9, 'bold')).pack(side='left', padx=(10, 0), pady=(8, 0))
        badge = tk.Label(header, text='VERSÃO EXPERIMENTAL', bg=ACCENT_DARK,
                         fg=ACCENT, font=(FONT, 8, 'bold'), padx=12, pady=7)
        badge.pack(side='right')
        tk.Frame(shell, bg=LINE, height=1).pack(fill='x', pady=(0, 6))
        navigation = tk.Frame(shell, bg=BG)
        navigation.pack(fill='x', pady=(0, 10))
        self.tabs = ttk.Notebook(shell, style='Modern.TNotebook')
        self.tabs.pack(fill='both', expand=True)
        self.play_tab = tk.Frame(self.tabs, bg=BG, padx=12, pady=14)
        self.build_tab = tk.Frame(self.tabs, bg=BG, padx=12, pady=14)
        self.graphics_tab = tk.Frame(self.tabs, bg=BG, padx=12, pady=14)
        self.hd_tab = tk.Toplevel(self.root, bg=BG, padx=18, pady=14)
        self.hd_tab.title('Aster · Ferramentas de texturas')
        self.hd_tab.geometry('900x330')
        self.hd_tab.withdraw()
        self.hd_tab.protocol('WM_DELETE_WINDOW', self.hd_tab.withdraw)
        self.game_tab = tk.Frame(self.tabs, bg=BG, padx=12, pady=14)
        self.diag_tab = tk.Frame(self.tabs, bg=BG, padx=12, pady=14)
        self.tabs.add(self.play_tab, text='Biblioteca')
        self.tabs.add(self.build_tab, text='Gerar port')
        self.tabs.add(self.graphics_tab, text='Gráficos')
        self.tabs.add(self.game_tab, text='Jogo e arquivos')
        self.tabs.add(self.diag_tab, text='Diagnóstico')
        self.nav_buttons = {}
        for page, title in [(self.play_tab, 'Biblioteca'), (self.build_tab, 'Gerar port'),
                            (self.graphics_tab, 'Gráficos'),
                            (self.game_tab, 'Jogo e arquivos'),
                            (self.diag_tab, 'Diagnóstico')]:
            button = tk.Button(navigation, text=title, bg=BG, fg=MUTED, activebackground=CARD,
                               activeforeground=INK, relief='flat', bd=0, highlightthickness=0, padx=22, pady=11,
                               font=(FONT, 10, 'bold'), cursor='hand2',
                               command=lambda tab=page: self.tabs.select(tab))
            button.pack(side='left', padx=(0, 4))
            self.nav_buttons[str(page)] = button
        def navigation_changed(_=None):
            selected = self.tabs.select()
            for page, button in self.nav_buttons.items():
                button.configure(bg=CARD if selected == page else BG,
                                 fg=ACCENT if selected == page else MUTED)
        self.tabs.bind('<<NotebookTabChanged>>', navigation_changed)
        navigation_changed()
        self._build_play_tab()
        self._build_generation_tab()
        self._build_graphics_tab()
        self._build_game_tab()
        self._build_diag_tab()
        footer = tk.Frame(shell, bg=BG)
        footer.pack(side='bottom', fill='x', pady=(4, 0), before=self.tabs)
        self.status_bar = tk.Label(footer, textvariable=self.status, bg=PANEL, fg=MUTED,
                                   anchor='w', justify='left', padx=12, pady=8,
                                   font=(FONT, 9), wraplength=800)
        self.status_bar.pack(side='left', fill='x', expand=True)
        tk.Label(footer, text='SEUS ARQUIVOS · SEU PC', bg=BG, fg=MUTED,
                 font=(FONT, 8), padx=8).pack(side='right')
        self.widgets = [self.folder_button, self.select_button, self.inspect_button,
                        self.prepare_button, self.cancel_button, self.compile_button,
                        self.stop_experimental_button, self.open_profile_button, self.play_button,
                        self.source_entry, self.work_entry, self.jobs_spin, self.save_button,
                        self.doctor_button, self.clear_button, self.export_button,
                        self.copy_button, self.restore_graphics_button, self.build_start_button,
                        self.hd_select_button, self.hd_original_button, self.hd_catalog_button, self.hd_prepare_button, self.hd_auto_button, self.fullscreen_check, self.sharpness_spin, self.sharpness_balanced_button, self.shader_preload_check]
        self._readonly_widgets = [self.build_combo, self.shader_combo, self.output_combo, self.upscaler_combo, self.antialiasing_combo]

    # -------------------------------------------------------------- play tab
    def _build_play_tab(self):
        hero = self._card(self.play_tab, fill='x')
        art = tk.Canvas(hero, width=104, height=132, bg=CARD, highlightthickness=0)
        art.pack(side='left', padx=(16, 0), pady=12)
        for radius, color in [(43, LINE), (32, '#3d5936'), (21, ACCENT)]:
            art.create_oval(52-radius, 66-radius, 52+radius, 66+radius, outline=color, width=2)
        art.create_line(52, 10, 52, 38, fill=ACCENT, width=3)
        art.create_line(52, 94, 52, 122, fill=ACCENT, width=3)
        hero_left = tk.Frame(hero, bg=CARD)
        hero_left.pack(side='left', fill='both', expand=True, padx=20, pady=17)
        self._caps(hero_left, 'Xbox 360 · Port nativo experimental').pack(anchor='w')
        tk.Label(hero_left, text='GREEN LANTERN', bg=CARD, fg=INK,
                 font=(FONT, 25, 'bold')).pack(anchor='w', pady=(5, 0))
        tk.Label(hero_left, text='RISE OF THE MANHUNTERS', bg=CARD, fg=MUTED,
                 font=(FONT, 10, 'bold')).pack(anchor='w', pady=(0, 8))
        tk.Label(hero_left, text='Transforme seu dump em uma versão local para PC.\n'
                  'Depois, escolha como jogar.',
                 bg=CARD, fg=MUTED, font=(FONT, 10), wraplength=430,
                 justify='left').pack(anchor='w')
        hero_right = tk.Frame(hero, bg=CARD)
        hero_right.pack(side='right', padx=20, pady=16)
        self.play_button = ttk.Button(hero_right, text='JOGAR AGORA', style='Accent.TButton',
                                      command=self.play)
        self.play_button.pack(fill='x')
        tk.Label(hero_right, textvariable=self.quick_target, bg=CARD, fg=ACCENT,
                 font=(FONT, 9, 'bold')).pack(anchor='e', pady=(7, 0))
        self.launch_button = self.play_button
        self.experimental_button = self.play_button

        chips = tk.Frame(self.play_tab, bg=BG)
        chips.pack(fill='x', pady=(10, 0))
        for index, (caption, variable) in enumerate((
                ('ALVO DE QUADROS', self.quick_target),
                ('PRESET GRÁFICO', self.quick_graphics),
                ('PERFIL DE SESSÃO', self.quick_profile))):
            chips.columnconfigure(index, weight=1, uniform='chip')
            card = tk.Frame(chips, bg=CARD, highlightthickness=1, highlightbackground=LINE)
            card.grid(row=0, column=index, sticky='nsew', padx=(0 if index == 0 else 5, 0))
            tk.Label(card, text=caption, bg=CARD, fg=MUTED, font=(FONT, 8, 'bold'),
                     anchor='w').pack(fill='x', padx=12, pady=(9, 0))
            tk.Label(card, textvariable=variable, bg=CARD, fg=INK, font=(FONT, 10, 'bold'),
                     anchor='w', wraplength=300, justify='left').pack(fill='x', padx=12, pady=(2, 9))

        self.warning_frame = tk.Frame(self.play_tab, bg=WARN_BG,
                                      highlightthickness=1, highlightbackground='#5c4b24')
        self.warning_label = tk.Label(self.warning_frame, textvariable=self.warning_text,
                                      bg=WARN_BG, fg=WARN, font=(FONT, 9), anchor='w',
                                      justify='left', wraplength=1020, padx=12, pady=8)
        self.warning_label.pack(fill='x')

        source_card = self.source_card = self._card(self.play_tab, fill='x', pady=(10, 0))
        heading = tk.Frame(source_card, bg=CARD)
        heading.pack(fill='x', padx=16, pady=(13, 0))
        self._caps(heading, 'Pasta do jogo').pack(side='left')
        tk.Label(heading, textvariable=self.engine_status, bg=CARD, fg=MUTED,
                 font=(FONT, 8)).pack(side='right')
        row = tk.Frame(source_card, bg=CARD)
        row.pack(fill='x', padx=16, pady=(6, 0))
        self.source_entry = ttk.Entry(row, textvariable=self.source)
        self.source_entry.pack(side='left', fill='x', expand=True)
        self.folder_button = ttk.Button(row, text='Selecionar pasta…', style='Secondary.TButton',
                                        command=self.select_folder)
        self.folder_button.pack(side='left', padx=(8, 0))
        self.select_button = ttk.Button(row, text='ISO / XEX…', style='Ghost.TButton',
                                        command=self.select)
        self.select_button.pack(side='left', padx=(5, 0))
        actions = tk.Frame(source_card, bg=CARD)
        actions.pack(fill='x', padx=16, pady=(8, 13))
        self.inspect_button = ttk.Button(actions, text='Inspecionar dump', style='Secondary.TButton',
                                         command=self.inspect)
        self.inspect_button.pack(side='left')
        self.prepare_button = ttk.Button(actions, text='Preparar evidências', style='Ghost.TButton',
                                         command=self.prepare)
        self.prepare_button.pack(side='left', padx=(6, 0))
        self.stop_experimental_button = ttk.Button(actions, text='Encerrar sessão',
                                                   style='Danger.TButton', state='disabled',
                                                   command=self.stop_experimental)
        self.stop_experimental_button.pack(side='right')
        self.open_profile_button = ttk.Button(actions, text='Abrir perfil', style='Ghost.TButton',
                                              command=self.open_profile)
        self.open_profile_button.pack(side='right', padx=(0, 6))
        self.cancel_button = ttk.Button(actions, text='Cancelar tarefa', style='Ghost.TButton',
                                        state='disabled', command=self.stop_experimental)
        self.cancel_button.pack(side='right', padx=(0, 6))
        track = tk.Frame(source_card, bg=CARD)
        track.pack(fill='x', padx=16, pady=(0, 10))
        tk.Label(track, textvariable=self.build_count, bg=CARD, fg=MUTED, font=(FONT, 9)).pack(side='left')
        ttk.Button(track, text='Ver geração  →', style='Ghost.TButton',
                   command=lambda: self.tabs.select(self.build_tab)).pack(side='right')

        notes = tk.Frame(self.play_tab, bg=BG)
        notes.pack(fill='x', pady=(10, 0))
        notes_data = (
            ('Seu progresso, em qualquer modo',
             '30, 60 e ilimitado compartilham o save deste usuário. Trocar FPS ou qualidade '
             'não cria outra campanha.'),
            ('Validação antes de abrir',
             'O launcher confere dump, build, plugin e referência FSI com --validar antes de abrir '
             'a sessão.'),
            ('Experimental é opt-in',
             '30 fps é o padrão. 60 e ilimitado pedem confirmação. O save continua o mesmo.'),
        )
        for index, (title, body) in enumerate(notes_data):
            notes.columnconfigure(index, weight=1, uniform='note')
            card = tk.Frame(notes, bg=CARD_ALT, highlightthickness=1,
                            highlightbackground='#30464f')
            card.grid(row=0, column=index, sticky='nsew', padx=(0 if index == 0 else 7, 0))
            tk.Label(card, text=title, bg=CARD_ALT, fg=ACCENT, font=(FONT, 9, 'bold'),
                     anchor='w').pack(fill='x', padx=12, pady=(9, 1))
            tk.Label(card, text=body, bg=CARD_ALT, fg=MUTED, font=(FONT, 8), anchor='w',
                     justify='left', wraplength=280).pack(fill='x', padx=10, pady=(0, 9))

    def _build_generation_tab(self):
        tk.Label(self.build_tab, text='Do seu dump ao PC', bg=BG, fg=INK,
                 font=(FONT, 22, 'bold')).pack(anchor='w')
        tk.Label(self.build_tab, text='Acompanhe cada etapa. Você pode sair desta aba sem interromper a geração.',
                 bg=BG, fg=MUTED, font=(FONT, 10)).pack(anchor='w', pady=(4, 10))
        columns = tk.Frame(self.build_tab, bg=BG)
        columns.pack(fill='both', expand=True)
        left = tk.Frame(columns, bg=BG)
        left.pack(side='left', fill='both', expand=True)
        side = tk.Frame(columns, bg=PANEL, width=245, padx=20, pady=20)
        side.pack(side='right', fill='y', padx=(16, 0))
        side.pack_propagate(False)
        self._caps(side, 'Durante a geração', PANEL).pack(anchor='w')
        tk.Label(side, text='Tudo acontece\nno seu PC.', bg=PANEL, fg=INK,
                 font=(FONT, 17, 'bold'), justify='left').pack(anchor='w', pady=(12, 16))
        for title, body in [('Seu dump é preservado', 'Os arquivos originais são apenas lidos.'),
                            ('Continue depois', 'Se cancelar, o que já foi compilado fica disponível para retomar.'),
                            ('Progresso da etapa', 'Downloads mostram MB transferidos. Compilações mostram tarefas concluídas.')]:
            tk.Label(side, text=title, bg=PANEL, fg=ACCENT, font=(FONT, 9, 'bold')).pack(anchor='w', pady=(12, 4))
            tk.Label(side, text=body, bg=PANEL, fg=MUTED, font=(FONT, 9), wraplength=205,
                     justify='left').pack(anchor='w')
        card = self._card(left, fill='x')
        head = tk.Frame(card, bg=CARD)
        head.pack(fill='x', padx=18, pady=(12, 6))
        tk.Label(head, textvariable=self.build_count, bg=CARD, fg=ACCENT,
                 font=(FONT, 9, 'bold')).pack(side='left')
        tk.Label(head, textvariable=self.build_elapsed, bg=CARD, fg=MUTED,
                 font=(MONO, 10)).pack(side='right')
        tk.Label(card, textvariable=self.build_heading, bg=CARD, fg=INK,
                 font=(FONT, 15, 'bold'), anchor='w', wraplength=650).pack(fill='x', padx=18)
        tk.Label(card, textvariable=self.build_detail, bg=CARD, fg=MUTED,
                 font=(FONT, 9), wraplength=650, anchor='w', justify='left').pack(fill='x', padx=18, pady=(8, 12))
        self.progress = ttk.Progressbar(card, mode='determinate', value=0)
        self.progress.pack(fill='x', padx=18)
        tk.Label(card, textvariable=self.build_measure, bg=CARD, fg=MUTED,
                 font=(FONT, 9), anchor='w').pack(fill='x', padx=18, pady=(8, 16))
        steps = self._card(left, fill='x', pady=(12, 0))
        self.stage_widgets = {}
        for index, (key, title, detail) in enumerate(BUILD_STAGES):
            row = tk.Frame(steps, bg=CARD)
            row.pack(fill='x', padx=16, pady=3)
            number = tk.Label(row, text=f'{index+1:02}', bg=CARD_ALT, fg=MUTED,
                              font=(MONO, 10, 'bold'), padx=8, pady=4)
            number.pack(side='left', padx=(0, 12))
            label = tk.Label(row, text=title, bg=CARD, fg=MUTED, font=(FONT, 10), anchor='w')
            label.pack(side='left')
            state = tk.Label(row, text='Aguardando', bg=CARD, fg=MUTED, font=(FONT, 9))
            state.pack(side='right')
            self.stage_widgets[key] = (number, label, state)
        actions = tk.Frame(left, bg=BG)
        actions.pack(side='bottom', fill='x', pady=(10, 0), before=card)
        self.build_start_button = ttk.Button(actions, text='Gerar port', style='Secondary.TButton', command=self.generate_native)
        self.build_start_button.pack(side='left')
        self.build_cancel_button = ttk.Button(actions, text='Cancelar geração', style='Ghost.TButton', state='disabled', command=self.stop_experimental)
        self.build_cancel_button.pack(side='left', padx=8)
        ttk.Button(actions, text='Ver logs', style='Ghost.TButton', command=lambda: self.tabs.select(self.diag_tab)).pack(side='right')

    def _paint_build_steps(self):
        for key, widgets in self.stage_widgets.items():
            state = self.stage_states[key]
            color = ACCENT if state in ('running', 'completed') else DANGER if state == 'failed' else WARN if state == 'cancelled' else MUTED
            number, label, badge = widgets
            number.configure(fg=color, bg=ACCENT_DARK if state == 'running' else CARD_ALT)
            label.configure(fg=INK if state in ('running', 'completed') else MUTED)
            badge.configure(fg=color, text={'pending': 'Aguardando', 'running': 'Em andamento',
                            'completed': 'Concluída', 'failed': 'Falhou', 'cancelled': 'Cancelada'}[state])
        self.build_count.set(f"{sum(state == 'completed' for state in self.stage_states.values())} de 6 etapas concluídas")

    def _build_event(self, event):
        if event.get('task') == 'Port já compilado':
            self.build_reused = True
        key = event.get('stage')
        if key not in self.stage_states or not self.build_running:
            return
        state = event.get('state', 'running')
        self.stage_states[key] = state
        if state == 'running':
            if self.active_stage != key:
                self.active_stage = key
                self.progress.stop()
                self.progress.configure(mode='indeterminate', value=0)
                self.progress.start(18)
                self.build_measure.set('Em andamento · duração ainda não estimada')
            self.build_heading.set(next(title for stage, title, _ in BUILD_STAGES if stage == key))
            self.build_detail.set(event.get('message') or next(detail for stage, _, detail in BUILD_STAGES if stage == key))
            completed, total = event.get('completed', 0), event.get('total', 0)
            if total > 0:
                self.progress.stop()
                self.progress.configure(mode='determinate', value=min(100, completed / total * 100))
            if event.get('unit') == 'bytes':
                amount = f'{completed / 1048576:.1f} MB'
                if total > 0:
                    amount += f' de {total / 1048576:.1f} MB'
                self.build_measure.set('Download · ' + amount)
            elif event.get('unit') == 'targets' and total > 0:
                self.build_measure.set(f'Compilação · {completed} de {total} tarefas ({min(100, completed*100//total)}% desta etapa)')
        elif state == 'completed':
            self.progress.stop()
            self.progress.configure(mode='determinate', value=100)
            self.build_measure.set('Etapa concluída')
        self._paint_build_steps()

    # ---------------------------------------------------------- graphics tab
    def _build_graphics_tab(self):
        top = tk.Frame(self.graphics_tab, bg=BG)
        top.pack(fill='x')
        tk.Label(top, text='Gráficos', bg=BG, fg=INK, font=(FONT, 17, 'bold')).pack(side='left')
        self.restore_graphics_button = ttk.Button(top, text='Restaurar padrão', style='Ghost.TButton', command=self.restore_graphics)
        self.restore_graphics_button.pack(side='right')
        tk.Label(self.graphics_tab, text='Escolha um preset ou ajuste cada opção. As alterações valem para a próxima sessão.',
                 bg=BG, fg=MUTED, font=(FONT, 9)).pack(anchor='w', pady=(4, 10))
        preset_frame = tk.Frame(self.graphics_tab, bg=BG)
        preset_frame.pack(fill='x')
        preset_text = {'low': 'BAIXA\nOriginais · leve', 'default': 'MÉDIA\nOriginais · equilíbrio',
                       'high': 'ALTA\n1440p · HD 2x', 'ultra': 'ULTRA\n4K · HD 4x',
                       'custom': 'PERSONALIZADA\najuste fino'}
        for index, name in enumerate(graphics.PRESETS):
            preset_frame.columnconfigure(index, weight=1, uniform='preset')
            button = ttk.Button(preset_frame, text=preset_text[name], style='Preset.TButton', command=lambda n=name: self.choose_preset(n))
            button.grid(row=0, column=index, sticky='nsew', padx=(0 if index == 0 else 5, 0))
            self.preset_buttons[name] = button
        target_frame = tk.Frame(self.graphics_tab, bg=BG)
        target_frame.pack(fill='x', pady=(10, 0))
        for index, target in enumerate(graphics.TARGETS):
            target_frame.columnconfigure(index, weight=1, uniform='target')
            button = ttk.Button(target_frame, text=graphics.TARGET_LABELS[target] + (' · experimental' if target != '30' else ' · padrão'),
                                style='Preset.TButton', command=lambda t=target: self.choose_target(t))
            button.grid(row=0, column=index, sticky='nsew', padx=(0 if index == 0 else 5, 0))
            self.target_buttons[target] = button
        self.target_note = tk.Label(self.graphics_tab, text='', bg=BG, fg=MUTED, font=(FONT, 8), wraplength=1000, justify='left')
        self.target_note.pack(anchor='w', pady=(5, 6))

        viewport = tk.Frame(self.graphics_tab, bg=BG)
        viewport.pack(fill='both', expand=True)
        self.graphics_canvas = tk.Canvas(viewport, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(viewport, orient='vertical', command=self.graphics_canvas.yview)
        scrollbar.pack(side='right', fill='y')
        self.graphics_canvas.pack(side='left', fill='both', expand=True)
        self.graphics_canvas.configure(yscrollcommand=scrollbar.set)
        body = tk.Frame(self.graphics_canvas, bg=BG)
        body.columnconfigure(0, weight=1, uniform='graphics')
        body.columnconfigure(1, weight=1, uniform='graphics')
        body_window = self.graphics_canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda _: self.graphics_canvas.configure(scrollregion=self.graphics_canvas.bbox('all')))
        self.graphics_canvas.bind('<Configure>', lambda e: self.graphics_canvas.itemconfigure(body_window, width=e.width))
        def scroll(event):
            delta = -1 if getattr(event, 'num', None) == 4 else 1 if getattr(event, 'num', None) == 5 else -int(event.delta / 120) or (-1 if event.delta > 0 else 1)
            self.graphics_canvas.yview_scroll(delta * 3, 'units')
            return 'break'
        def section(title, row, col):
            card = tk.Frame(body, bg=CARD, padx=14, pady=12)
            card.grid(row=row, column=col, sticky='nsew', padx=(0 if col == 0 else 8, 0), pady=(0, 8))
            self._caps(card, title).pack(anchor='w', pady=(0, 5))
            return card
        def combo(parent, title, variable, values, attr, custom=False):
            line = tk.Frame(parent, bg=CARD)
            line.pack(fill='x', pady=4)
            tk.Label(line, text=title, bg=CARD, fg=MUTED, font=(FONT, 9), width=19, anchor='w').pack(side='left')
            widget = ttk.Combobox(line, textvariable=variable, values=values, state='readonly', width=25)
            widget.pack(side='right', fill='x', expand=True)
            if custom:
                widget.bind('<<ComboboxSelected>>', lambda _: self._on_custom_changed())
            setattr(self, attr, widget)
            return widget
        def note(parent, text):
            tk.Label(parent, text=text, bg=CARD, fg=MUTED, font=(FONT, 8), wraplength=430, justify='left').pack(anchor='w', pady=(5, 0))

        display = section('TELA', 0, 0)
        combo(display, 'Resolução de saída', self.output_resolution, ['Automática', *graphics.OUTPUT_RESOLUTIONS[1:]], 'output_combo')
        self.fullscreen_check = ttk.Checkbutton(display, text='Tela cheia', variable=self.fullscreen)
        self.fullscreen_check.pack(anchor='w', pady=4)
        self.vsync_check = ttk.Checkbutton(display, text='Sincronização vertical (VSync)', variable=self.vsync)
        self.vsync_check.pack(anchor='w', pady=4)
        note(display, '1920x1080 é Full HD. A resolução de saída e a resolução interna são independentes. Alta renderiza em 1440p; Ultra em 4K, inclusive quando a saída é Full HD.')

        image = section('IMAGEM', 0, 1)
        combo(image, 'Escala interna (1–3x)', self.custom_render_scale, [1, 2, 3], 'render_scale_spin', True)
        combo(image, 'Ampliação', self.upscaler, [graphics.UPSCALER_LABELS[k] for k in graphics.COMMON_UPSCALERS], 'upscaler_combo', True)
        combo(image, 'Antisserrilhado', self.antialiasing, list(graphics.ANTIALIASING_LABELS.values()), 'antialiasing_combo', True)
        sharp_row = tk.Frame(image, bg=CARD)
        sharp_row.pack(fill='x', pady=4)
        tk.Label(sharp_row, text='Nitidez FSR (0–100)', bg=CARD, fg=MUTED, font=(FONT, 9), width=19, anchor='w').pack(side='left')
        self.sharpness_spin = ttk.Spinbox(sharp_row, from_=0, to=100, textvariable=self.fsr_sharpness, width=7)
        self.sharpness_spin.pack(side='left')
        self.sharpness_balanced_button = ttk.Button(sharp_row, text='Equilibrada', style='Ghost.TButton',
                                                   command=lambda: self.fsr_sharpness.set(graphics.DEFAULT_FSR_SHARPNESS))
        self.sharpness_balanced_button.pack(side='left', padx=(7, 0))
        note(image, 'FSR 1 amplia a imagem; FXAA reduz serrilhados. Nitidez recomendada: 30; valores altos podem realçar granulação e contornos. MSAA preserva o comportamento original do jogo.')

        textures = section('TEXTURAS', 1, 0)
        combo(textures, 'Qualidade', self.custom_texture, list(graphics.TEXTURE_QUALITY_LABELS.values()), 'texture_combo', True)
        combo(textures, 'Filtro anisotrópico', self.custom_aniso, list(ANISO_LABELS.values()), 'aniso_combo', True)
        tk.Label(textures, textvariable=self.hd_status, bg=CARD, fg=ACCENT, font=(FONT, 9), wraplength=430, justify='left').pack(anchor='w', pady=(7, 4))
        hd_actions = tk.Frame(textures, bg=CARD)
        hd_actions.pack(fill='x')
        self.hd_auto_button = ttk.Button(hd_actions, text='Preparar texturas deste preset', style='Ghost.TButton', command=self.prepare_graphics_textures)
        self.hd_auto_button.pack(side='left')
        self.hd_cancel_button = ttk.Button(hd_actions, text='Cancelar', style='Ghost.TButton', command=lambda: self.cancel.cancel(), state='disabled')
        self.hd_cancel_button.pack(side='left', padx=5)
        self.hd_progress = ttk.Progressbar(textures, mode='determinate', value=0)
        self.hd_progress.pack(fill='x', pady=(7, 0))
        note(textures, 'Baixa/Média usam originais. Alta prepara materiais revisados em 2x; Ultra em 4x. A preparação ocorre antes de jogar e reutiliza a mesma inferência de IA. A cobertura HD é parcial; os demais materiais mantêm os originais.')

        performance = section('DESEMPENHO', 1, 1)
        self.shader_preload_check = ttk.Checkbutton(performance, text='Pré-compilar shaders conhecidos antes de jogar', variable=self.shader_preload)
        self.shader_preload_check.pack(anchor='w', pady=4)
        combo(performance, 'Shaders novos', self.shader_mode, graphics.SHADER_MODES, 'shader_combo')
        self.dither_check = ttk.Checkbutton(performance, text='Dithering de apresentação', variable=self.custom_dither)
        self.dither_check.pack(anchor='w', pady=4)
        note(performance, 'O cache de shaders fica guardado entre aberturas. A preparação cobre o que já foi encontrado; cenas inéditas e mudanças de driver ou gráficos podem exigir novas variantes. async compila pipelines novos em segundo plano; blocking aguarda. O primeiro uso ainda pode causar pausas.')
        note(performance, 'Escala interna: 1x = 720p; 2x = 1440p; 3x = 4K. Escalas maiores aumentam a carga da GPU e exigem atualizar o port. Validação da campanha completa ainda está em andamento.')
        # MSAA follows guest state and is not offered as a misleading toggle.
        self.msaa_check = ttk.Checkbutton(performance, variable=self.custom_msaa)
        self.custom_grid = performance
        self.graphics_summary_label = tk.Label(body, textvariable=self.graphics_summary, bg=BG, fg=ACCENT,
                                                font=(FONT, 9), wraplength=950, justify='left')
        self.graphics_summary_label.grid(row=2, column=0, columnspan=2, sticky='w', pady=5)
        def bind_scroll(widget):
            # Comboboxes and spinboxes retain native wheel selection; other
            # descendants scroll this page without global bindings.
            if not isinstance(widget, (ttk.Combobox, ttk.Spinbox)):
                for event in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                    widget.bind(event, scroll)
            for child in widget.winfo_children():
                bind_scroll(child)
        bind_scroll(body)
        self.graphics_canvas.bind('<MouseWheel>', scroll)
        self._build_texture_tools()

    def _build_texture_tools(self):
        parent = self.hd_tab
        tk.Label(parent, text='Ferramentas de texturas · avançado', bg=BG, fg=INK, font=(FONT, 17, 'bold')).pack(anchor='w', pady=10)
        tk.Label(parent, text='Inspeção e seleção manual para diagnóstico. O fluxo normal usa os presets na página Gráficos.',
                 bg=BG, fg=MUTED, wraplength=820, justify='left').pack(anchor='w')
        row = tk.Frame(parent, bg=BG)
        row.pack(fill='x', pady=12)
        self.hd_select_button = ttk.Button(row, text='Selecionar pacote HD…', style='Ghost.TButton', command=self.select_hd_pack)
        self.hd_select_button.pack(side='left')
        self.hd_original_button = ttk.Button(row, text='Limpar seleção manual', style='Ghost.TButton', command=self.use_original_textures)
        self.hd_original_button.pack(side='left', padx=6)
        prepare_row = tk.Frame(parent, bg=BG)
        prepare_row.pack(fill='x', pady=5)
        self.hd_catalog_button = ttk.Button(prepare_row, text='Selecionar catálogo revisado…', style='Ghost.TButton', command=self.select_hd_catalog)
        self.hd_catalog_button.pack(side='left')
        self.hd_prepare_button = ttk.Button(prepare_row, text='Preparar catálogo com IA', style='Ghost.TButton', command=self.prepare_hd_pack)
        self.hd_prepare_button.pack(side='left', padx=6)
        tk.Label(parent, textvariable=self.hd_texture_catalog, bg=BG, fg=MUTED, wraplength=820, justify='left').pack(anchor='w', pady=8)
        tk.Label(parent, textvariable=self.hd_status, bg=BG, fg=ACCENT, wraplength=820, justify='left').pack(anchor='w')
        ttk.Button(parent, text='Voltar aos gráficos', command=lambda: (parent.withdraw(), self.tabs.select(self.graphics_tab))).pack(anchor='w', pady=12)

    def show_texture_tools(self):
        self.hd_tab.deiconify()
        self.hd_tab.lift()

    def prepare_graphics_textures(self):
        if self.busy:
            return
        data = self._graphics_data()
        if data['texture_quality'] not in ('high', 'ultra'):
            self.status.set('Baixa e Média usam texturas originais; selecione Alta ou Ultra para preparar HD.')
            return
        if not self._source_ready():
            self.status.set('Selecione a pasta do dump antes de preparar texturas.')
            return
        source = Path(self.source.get()).expanduser().resolve()
        work = Workspace(self.workspace.get(), PROJECT)
        self.hd_running = True
        self.hd_progress.configure(mode='indeterminate', value=0)
        self.hd_progress.start(15)
        def action():
            from .texture_pipeline import ensure_graphics_textures
            return ensure_graphics_textures(source, data, PROJECT, work, cancel=self.cancel,
                                            emit=lambda event: self.queue.put(('hd-event', '', event)), allow_download=True)
        self.start(action, 'Preparar texturas HD')
        self.tabs.select(self.graphics_tab)


    # --------------------------------------------------------------- game tab
    def _build_game_tab(self):
        tk.Label(self.game_tab, text='Jogo e arquivos', bg=BG, fg=INK,
                 font=(FONT, 17, 'bold')).pack(anchor='w')
        tk.Label(self.game_tab, text='O dump precisa conter default.xex. A pasta de trabalho e os '
                  'perfis ficam em .aster, separados dos arquivos originais.',
                 bg=BG, fg=MUTED, font=(FONT, 9), wraplength=1050,
                 justify='left').pack(anchor='w', pady=(4, 10))
        workspace_card = self._card(self.game_tab, fill='x')
        left = tk.Frame(workspace_card, bg=CARD)
        left.pack(fill='x', padx=16, pady=13)
        self._caps(left, 'Diretório de trabalho').pack(anchor='w')
        work_row = tk.Frame(left, bg=CARD)
        work_row.pack(fill='x', pady=(6, 0))
        self.work_entry = ttk.Entry(work_row, textvariable=self.workspace)
        self.work_entry.pack(side='left', fill='x', expand=True)
        self.work_button = ttk.Button(work_row, text='Escolher…', style='Ghost.TButton',
                                      command=self.select_workspace)
        self.work_button.pack(side='left', padx=(8, 0))
        self.paths_label = tk.Label(left, text='', bg=CARD, fg=MUTED, font=(FONT, 8),
                                    wraplength=1000, justify='left')
        self.paths_label.pack(anchor='w', pady=(6, 0))
        config_row = tk.Frame(left, bg=CARD)
        config_row.pack(fill='x', pady=(9, 0))
        tk.Label(config_row, text='Build', bg=CARD, fg=MUTED, font=(FONT, 9)).pack(side='left')
        self.build_combo = ttk.Combobox(config_row, textvariable=self.build_type, state='readonly',
                                        width=15, values=('Release', 'Debug', 'RelWithDebInfo'))
        self.build_combo.pack(side='left', padx=(8, 18))
        tk.Label(config_row, text='Tarefas paralelas', bg=CARD, fg=MUTED,
                 font=(FONT, 9)).pack(side='left')
        self.jobs_spin = ttk.Spinbox(config_row, from_=1, to=64, textvariable=self.jobs, width=5)
        self.jobs_spin.pack(side='left', padx=(8, 18))
        self.save_button = ttk.Button(config_row, text='Salvar preferências', style='Secondary.TButton',
                                      command=self.save_settings)
        self.save_button.pack(side='left')
        tk.Label(left, text='Gerar port valida a revisão do dump, gera C++ e compila localmente. '
                  'Requer CMake, Ninja e Clang/C++23 (Build Tools + Windows SDK no Windows).', bg=CARD, fg=MUTED,
                 font=(FONT, 8)).pack(anchor='w', pady=(6, 0))
        actions = tk.Frame(self.game_tab, bg=BG)
        actions.pack(fill='x', pady=(10, 0))
        self.compile_button = ttk.Button(actions, text='Gerar port nativo', style='Secondary.TButton',
                                         command=self.generate_native, state='disabled')
        self.compile_button.pack(side='left')
        self.doctor_button = ttk.Button(actions, text='Verificar ambiente', style='Secondary.TButton',
                                        command=self.doctor)
        self.doctor_button.pack(side='left', padx=(6, 0))
        self.clear_button = ttk.Button(actions, text='Limpar cache…', style='Ghost.TButton',
                                       command=self.clear_cache)
        self.clear_button.pack(side='left', padx=(6, 0))
        self.summary = tk.Text(self.game_tab, height=4, bg=BG, fg=INK, relief='flat',
                               wrap='word', padx=12, pady=12, font=(FONT, 9),
                               highlightthickness=1, highlightbackground=LINE)
        self.summary.pack(fill='both', expand=True, pady=(10, 0))
        self.set_summary('Nenhuma entrada validada.\n\nSelecione a pasta que contém default.xex e os '
                         'assets extraídos do jogo. O inventário é local e não modifica o dump.\n\n'
                         'Para jogar, o host local e a referência FSI precisam existir; o launcher '
                         'executa --validar antes de abrir a sessão. O modo 30 fps usa o perfil '
                         'principal. Todos os modos compartilham o save deste usuário.')
        self.requirements = tk.Frame(self.game_tab, bg=CARD_ALT, highlightthickness=1,
                                     highlightbackground='#3a4f57')
        self.requirements.pack(fill='x', pady=(10, 0))
        tk.Label(self.requirements, text='Para outro computador com o mesmo dump', bg=CARD_ALT,
                 fg=ACCENT, font=(FONT, 9, 'bold'), anchor='w').pack(fill='x', padx=12, pady=(8, 1))
        tk.Label(self.requirements, text='1. Confirme o SHA-256 do default.xex.  2. Compile o host '
                 'local e o plugin xenos.  3. Gere/valide o probe FSI.  4. Selecione o dump aqui: '
                 'nada do jogo é escrito fora do perfil isolado.', bg=CARD_ALT, fg=MUTED,
                 font=(FONT, 8), anchor='w', justify='left', wraplength=1030).pack(fill='x', padx=12,
                                                                                  pady=(0, 8))

    # -------------------------------------------------------------- diag tab
    def _build_diag_tab(self):
        top = tk.Frame(self.diag_tab, bg=BG)
        top.pack(fill='x')
        tk.Label(top, text='Diagnóstico', bg=BG, fg=INK,
                 font=(FONT, 17, 'bold')).pack(side='left')
        self.environment_status_label = tk.Label(top, textvariable=self.environment_status,
                                                 bg=BG, fg=MUTED, font=(FONT, 9))
        self.environment_status_label.pack(side='right', pady=(5, 0))
        env_card = self._card(self.diag_tab, fill='x', pady=(8, 0))
        self.environment = tk.Text(env_card, bg=BG, fg=INK, relief='flat', height=2, wrap='word',
                                   padx=10, pady=8, font=(MONO, 9), highlightthickness=0)
        self.environment.pack(fill='x', padx=10, pady=8)
        self.environment.insert('end', 'Execute “Verificar ambiente” para consultar ferramentas e versões locais.')
        self.environment.configure(state='disabled')
        task_card = self._card(self.diag_tab, fill='x', pady=(10, 0))
        self.task_tree = ttk.Treeview(task_card, columns=('state', 'duration'),
                                      show='tree headings', height=5)
        self.task_tree.heading('#0', text='Tarefa')
        self.task_tree.heading('state', text='Estado')
        self.task_tree.heading('duration', text='Duração')
        self.task_tree.column('#0', width=500)
        self.task_tree.column('state', width=130)
        self.task_tree.column('duration', width=100)
        self.task_tree.pack(fill='x', padx=10, pady=10)
        self.logs = tk.Text(self.diag_tab, bg=BG, fg=INK, insertbackground=INK, relief='flat',
                            wrap='word', font=(MONO, 8), height=8,
                            highlightthickness=1, highlightbackground=LINE)
        self.logs.pack(fill='both', expand=True, pady=(10, 0))
        self.logs.configure(state='disabled')
        actions = tk.Frame(self.diag_tab, bg=BG)
        actions.pack(fill='x', pady=(10, 0))
        self.export_button = ttk.Button(actions, text='Salvar diagnóstico e logs', style='Secondary.TButton',
                                        command=self.export_report)
        self.export_button.pack(side='left')
        ttk.Button(actions, text='Ferramentas de texturas…', style='Ghost.TButton', command=self.show_texture_tools).pack(side='left', padx=6)
        self.copy_button = ttk.Button(actions, text='Copiar logs', style='Ghost.TButton',
                                      command=self.copy_logs)
        self.copy_button.pack(side='left', padx=(6, 0))
        tk.Label(self.diag_tab, textvariable=self.report_path, bg=BG, fg=MUTED,
                 font=(FONT, 8), wraplength=1000, justify='left').pack(anchor='w', pady=(7, 0))

    # ---------------------------------------------------------- graphics sync
    def _set_graphics_vars(self, data):
        self._syncing = True
        try:
            self.graphics_preset.set(data['preset'])
            self.fps_target.set(data['fps_target'])
            self.vsync.set(data['vsync'])
            self.shader_mode.set(data['shader_mode'])
            self.shader_preload.set(data['shader_preload'])
            self.upscaler.set(graphics.UPSCALER_LABELS[data['upscaler']])
            self.antialiasing.set(graphics.ANTIALIASING_LABELS[data['antialiasing']])
            self.output_resolution.set('Automática' if data['output_resolution'] == 'auto' else data['output_resolution'])
            self.fullscreen.set(data['fullscreen'])
            self.fsr_sharpness.set(data['fsr_sharpness'])
            self.custom_render_scale.set(data['render_scale'])
            self.custom_msaa.set(data['msaa_2x'])
            self.custom_aniso.set(ANISO_LABELS.get(data['anisotropic'], ANISO_LABELS[3]))
            self.custom_texture.set(graphics.TEXTURE_QUALITY_LABELS.get(
                data['texture_quality'], graphics.TEXTURE_QUALITY_LABELS['default']))
            self.custom_dither.set(data['present_dither'])
            if data['fps_target'] != 'unlimited':
                self._vsync_preference = bool(data['vsync'])
        finally:
            self._syncing = False

    def _graphics_data(self):
        target = self.fps_target.get()
        preset = self.graphics_preset.get()
        common = dict(fps_target=target, vsync=self.vsync.get(), fullscreen=self.fullscreen.get(), fsr_sharpness=self.fsr_sharpness.get(),
                      shader_mode=self.shader_mode.get(),
                      shader_preload=self.shader_preload.get(),
                      output_resolution='auto' if self.output_resolution.get() == 'Automática' else self.output_resolution.get())
        if preset == 'custom':
            return graphics.from_options(
                'custom',
                upscaler={label: key for key, label in graphics.UPSCALER_LABELS.items()}.get(self.upscaler.get(), 'bilinear'),
                antialiasing={label: key for key, label in graphics.ANTIALIASING_LABELS.items()}.get(self.antialiasing.get(), 'fxaa'),
                render_scale=self.custom_render_scale.get(),
                msaa_2x=self.custom_msaa.get(),
                anisotropic=ANISO_BY_LABEL.get(self.custom_aniso.get(), 3),
                texture_quality=TEXTURE_BY_LABEL.get(self.custom_texture.get(), 'default'),
                present_dither=self.custom_dither.get(),
                **common)
        return graphics.from_options(preset, **common)

    def _refresh_graphics_ui(self):
        try:
            data = self._graphics_data()
            text = graphics.summary(data)
        except (PortError, tk.TclError) as exc:
            data, text = None, str(exc)
        self.graphics_summary.set(text)
        target = self.fps_target.get()
        preset = self.graphics_preset.get()
        if data:
            self.quick_target.set(graphics.TARGET_LABELS[target] +
                                  (' · experimental' if target != '30' else ' · padrão'))
            self.quick_graphics.set(
                f"{graphics.PRESET_LABELS[preset]} · {graphics.internal_resolution(data['render_scale'])}")
            self.quick_profile.set({
                '30': 'Usuário do sistema · save compartilhado',
                '60': 'Usuário do sistema · save compartilhado',
                'unlimited': 'Usuário do sistema · save compartilhado',
            }[target])
        for name, button in self.preset_buttons.items():
            button.configure(style='PresetOn.TButton' if name == preset else 'Preset.TButton')
        for target_name, button in self.target_buttons.items():
            button.configure(style='PresetOn.TButton' if target_name == target else 'Preset.TButton')
        self.warning_frame.pack_forget()
        if target == '60':
            self.warning_text.set('MODO 60 FPS EXPERIMENTAL · usa o save compartilhado do usuário. '
                                  'O timestep foi medido, mas combate, física, animações, áudio e '
                                  'campanha completa ainda não estão certificados.')
            self.warning_frame.pack(fill='x', pady=(10, 0), before=self.source_card)
        elif target == 'unlimited':
            self.warning_text.set('MODO ILIMITADO EXPERIMENTAL · remove a espera de pacing, desliga '
                                  'VSync e usa apresentação imediata. Pode causar tearing, alto uso de '
                                  'GPU e velocidade incorreta; use apenas para testar.')
            self.warning_frame.pack(fill='x', pady=(10, 0), before=self.source_card)
        note = graphics.TARGET_DESCRIPTIONS[target]
        if target == 'unlimited':
            note += ' VSync fica desligado. O save pertence ao usuário.'
        self.target_note.configure(text=note, fg=WARN if target != '30' else MUTED)
        self._refresh_custom_state()
        self._refresh_engine_status()
        self._refresh_hd_status()

    def _refresh_custom_state(self):
        state = 'disabled' if self.busy else 'normal'
        for widget in (self.render_scale_spin, self.msaa_check, self.aniso_combo,
                       self.texture_combo, self.dither_check):
            widget.configure(state=state)
        self.msaa_check.configure(state='disabled')
        self.render_scale_spin.configure(state='disabled' if self.busy else 'readonly')
        if not self.busy:
            self.aniso_combo.configure(state='readonly')
            self.texture_combo.configure(state='readonly')
        if self.fps_target.get() == 'unlimited' or self.busy:
            self.vsync_check.configure(state='disabled')
        else:
            self.vsync_check.configure(state='normal')
        self.sharpness_spin.configure(state='normal' if not self.busy and self.upscaler.get() == graphics.UPSCALER_LABELS['fsr1'] else 'disabled')
        self.sharpness_balanced_button.configure(state=str(self.sharpness_spin['state']))
        if self.busy:
            self.shader_combo.configure(state='disabled')
        else:
            self.shader_combo.configure(state='readonly')

    def _on_custom_changed(self):
        if self._syncing or self.busy:
            return
        if self.graphics_preset.get() != 'custom':
            self._syncing = True
            try:
                self.graphics_preset.set('custom')
            finally:
                self._syncing = False
        self._refresh_graphics_ui()

    def _on_target_changed(self):
        if self._syncing:
            return
        target = self.fps_target.get()
        if target == 'unlimited':
            if self.vsync.get():
                self._syncing = True
                try:
                    self._vsync_preference = True
                    self.vsync.set(False)
                finally:
                    self._syncing = False
        else:
            if not self.vsync.get() and self._vsync_preference:
                self._syncing = True
                try:
                    self.vsync.set(True)
                finally:
                    self._syncing = False
        self._refresh_graphics_ui()

    def _on_vsync_changed(self):
        if self._syncing:
            return
        if self.fps_target.get() != 'unlimited':
            self._vsync_preference = bool(self.vsync.get())
        self._refresh_graphics_ui()

    def choose_preset(self, name):
        if self.busy:
            return
        try:
            data = graphics.apply_preset(name, self._graphics_data())
        except PortError as exc:
            self.status.set(str(exc))
            return
        self._set_graphics_vars(data)
        self._refresh_graphics_ui()
        self.status.set(f'Preset {graphics.PRESET_LABELS[name]} selecionado para a próxima sessão.')

    def choose_target(self, target):
        if self.busy:
            return
        old = self.fps_target.get()
        self.fps_target.set(target)
        if target == 'unlimited':
            self.vsync.set(False)
        self._refresh_graphics_ui()
        if old != target:
            self.status.set(f'Alvo alterado para {graphics.TARGET_LABELS[target]}. '
                            'As opções só valem para a próxima sessão.')

    def restore_graphics(self):
        if self.busy:
            return
        self._set_graphics_vars(graphics.defaults())
        self._refresh_graphics_ui()
        self.status.set('Opções gráficas restauradas para o padrão de 30 fps.')

    # ------------------------------------------------------------- state/UI
    def _source_ready(self):
        try:
            folder = Path(self.source.get()).expanduser()
        except (OSError, ValueError):
            return False
        return bool(self.source.get()) and folder.is_dir() and (folder / 'default.xex').is_file()

    def _engine_paths(self, target=None):
        target = target or self.fps_target.get()
        try:
            installation = read_install(PROJECT)
        except PortError:
            installation = None
        if installation:
            return PROJECT / installation['binary'], PROJECT / '.aster/config/native-install.json'
        binary, report = MODE_FILES[target]
        return PROJECT / binary, PROJECT / report

    def _backend_update_needed(self):
        try:
            installation = read_install(PROJECT)
        except PortError:
            return False
        return bool(installation and (installation.get('recipe', {}).get('integration', 0) < INTEGRATION_VERSION
                    or installation.get('presentation_backend') != 'sdk-spatial-fsr1'))

    def _engine_ready(self, target=None):
        if self._backend_update_needed():
            return False
        binary, report = self._engine_paths(target)
        return binary.is_file() and report.is_file()

    def _refresh_engine_status(self):
        target = self.fps_target.get()
        binary, report = self._engine_paths(target)
        if self._backend_update_needed():
            self.engine_status.set('Atualize o backend em Gerar port para ativar shaders e filtros novos')
        elif binary.is_file() and report.is_file():
            self.engine_status.set('Build e referência locais encontrados')
        elif binary.is_file():
            self.engine_status.set('Build encontrado; falta o probe FSI de referência')
        else:
            self.engine_status.set('Build local ausente para esta opção')
        self._refresh_play_state()

    def _refresh_play_state(self):
        if self.busy:
            return
        ready = self._source_ready() and self._engine_ready()
        self.play_button.configure(state='normal' if self._source_ready() else 'disabled',
                                   text='JOGAR AGORA' if ready else 'ATUALIZAR PORT' if self._backend_update_needed() else 'GERAR PORT NATIVO')
        self.compile_button.configure(state='normal' if self._source_ready() else 'disabled')
        self.build_start_button.configure(state='normal' if self._source_ready() else 'disabled')

    def _idle_status(self):
        if not self.source.get():
            return 'Selecione a pasta do jogo para começar.'
        if not self._source_ready():
            return 'A pasta selecionada precisa conter default.xex.'
        if not self._engine_ready():
            target = graphics.TARGET_LABELS[self.fps_target.get()]
            return f'Build ou referência FSI ausente para {target}; consulte Jogo e arquivos.'
        target = graphics.TARGET_LABELS[self.fps_target.get()]
        preset = graphics.PRESET_LABELS[self.graphics_preset.get()]
        return f'Pronto para abrir {target} com preset {preset}.'

    def _set_busy_controls(self, enabled):
        for widget in self.widgets:
            try:
                widget.configure(state='normal' if enabled else 'disabled')
            except tk.TclError:
                pass
        for button in list(self.preset_buttons.values()) + list(self.target_buttons.values()):
            button.configure(state='normal' if enabled else 'disabled')
        for widget in self._readonly_widgets:
            widget.configure(state='readonly' if enabled else 'disabled')
        self.compile_button.configure(state='normal' if enabled and self._source_ready() else 'disabled')
        self.cancel_button.configure(state='disabled' if enabled else 'normal')
        self.hd_cancel_button.configure(state='normal' if self.hd_running and not enabled else 'disabled')
        self.build_cancel_button.configure(state='normal' if not enabled and self.build_running else 'disabled')
        self.stop_experimental_button.configure(
            state='normal' if (not enabled and self.experimental_process is not None) else 'disabled')
        self._refresh_custom_state()

    # --------------------------------------------------------------- actions
    def select_hd_pack(self):
        if self.busy:
            return
        directory = filedialog.askdirectory(title='Pacote HD local preparado pelo Real-ESRGAN')
        if not directory:
            return
        self.hd_running = True
        self.hd_progress.configure(mode='indeterminate', value=0)
        self.hd_progress.start(15)
        def action():
            from .texture_pack import validate_texture_pack
            self.cancel.check()
            verified = validate_texture_pack(directory, cancel=self.cancel)
            self.cancel.check()
            return {'pack': str(verified), 'material_count': self._hd_count(verified), 'state': 'verified'}
        self.start(action, 'Selecionar pacote HD')
        self.hd_status.set('Conferindo integridade do pacote local…')

    @staticmethod
    def _hd_count(verified):
        if isinstance(verified, (str, Path)):
            manifest = Path(verified) / ('library.json' if (Path(verified) / 'library.json').exists() else 'pack.json')
            try:
                if manifest.is_file() and manifest.stat().st_size <= 4 * 1024 * 1024:
                    verified = json.loads(manifest.read_text(encoding='utf8'))
                elif (Path(verified) / 'texture.index').is_file():
                    return 1
            except (OSError, ValueError):
                return None
        if isinstance(verified, dict):
            for key in ('material_count', 'count'):
                count = verified.get(key)
                if type(count) is int and count >= 0:
                    return count
            for key in ('textures', 'materials', 'entries'):
                if isinstance(verified.get(key), list):
                    return len(verified[key])
        return None

    def _refresh_hd_status(self):
        if self.hd_running:
            return
        try:
            active = self._graphics_data()['texture_quality'] in ('high', 'ultra')
        except (PortError, tk.TclError):
            return
        self.hd_auto_button.configure(state='normal' if active and not self.busy else 'disabled')
        if not self.hd_texture_pack.get():
            scale = '4x' if self._graphics_data()['texture_quality'] == 'ultra' else '2x'
            self.hd_status.set(f'HD {scale} · preparação automática antes de jogar' if active else 'Texturas originais neste preset')
            return
        count = self.hd_material_count
        prepared = f'{count} materiais preparados' if count is not None else 'Pacote local selecionado'
        self.hd_status.set(prepared + (' · habilitado neste preset' if active else ' · ative Alta/Ultra para usar'))

    def use_original_textures(self):
        if self.busy:
            return
        self.hd_texture_pack.set('')
        self.hd_material_count = None
        self._refresh_hd_status()
        self.save_settings(quiet=True)

    def select_hd_catalog(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(title='Catálogo local de materiais revisados',
                                          filetypes=[('Catálogo JSON', '*.json')])
        if path:
            self.hd_texture_catalog.set(path)
            self.save_settings(quiet=True)
            self.status.set('Catálogo selecionado · revisão e integridade serão conferidas antes da IA')

    def prepare_hd_pack(self):
        if self.busy:
            return
        if not self.hd_texture_catalog.get():
            self.select_hd_catalog()
        if not self.hd_texture_catalog.get():
            return
        if not messagebox.askyesno('Preparar materiais HD',
                'Preparar somente os materiais de cor opaca revisados deste catálogo?\n\n'
                'O Real-ESRGAN e seu modelo oficial serão baixados se necessário (cerca de 50 MB). '
                'A preparação usa a GPU fora da partida e reutiliza resultados já verificados. '
                'Isso não constitui um pacote HD completo do jogo.'):
            return
        catalog = Path(self.hd_texture_catalog.get())
        try:
            cfg = self.config()
            settings.save(cfg, PROJECT)
            work = Workspace(cfg['workspace'], PROJECT)
        except (PortError, OSError) as exc:
            self.status.set(str(exc))
            return
        self.hd_running = True
        self.hd_progress.configure(mode='indeterminate', value=0)
        self.hd_progress.start(15)
        def action():
            from .texture_pack import prepare_texture_pack, validate_texture_pack
            output = prepare_texture_pack(catalog, PROJECT, work, cancel=self.cancel,
                                          emit=lambda e: self.queue.put(('hd-event', '', e)),
                                          allow_download=True)
            return {'pack': str(output), 'material_count': self._hd_count(validate_texture_pack(output, cancel=self.cancel)),
                    'state': 'prepared', 'runtime_rendered': False}
        self.start(action, 'Preparar texturas HD')

    def _hd_event(self, event):
        message = event.get('message') or event.get('task') or 'Preparando materiais HD…'
        self.status.set(message)
        self.hd_status.set(message)
        completed, total = event.get('completed'), event.get('total')
        if isinstance(completed, (int, float)) and isinstance(total, (int, float)) and total > 0:
            self.hd_progress.stop()
            self.hd_progress.configure(mode='determinate', value=max(0, min(100, completed / total * 100)))

    def refresh_paths(self):
        try:
            work = Workspace(self.workspace.get(), PROJECT)
            self.paths_label.configure(text=f'Saída: {work.path("output")}\n'
                                            f'Cache: {work.path("cache/v1")}')
        except PortError as exc:
            self.paths_label.configure(text=str(exc))

    def config(self):
        try:
            return settings.validate({'schema': 2, 'workspace': self.workspace.get(),
                                      'source': self.source.get(), 'build_type': self.build_type.get(),
                                      'jobs': self.jobs.get(), 'hd_texture_pack': self.hd_texture_pack.get(),
                                      'hd_texture_catalog': self.hd_texture_catalog.get(), 'graphics': self._graphics_data()}, PROJECT)
        except tk.TclError as exc:
            raise PortError('SETTINGS_VALUE', 'Número de tarefas inválido.') from exc

    def save_settings(self, quiet=False):
        try:
            p = settings.save(self.config(), PROJECT)
            if not quiet:
                self.log({'task': 'Salvar preferências', 'state': 'completed', 'path': str(p)})
                self.status.set('Preferências salvas localmente • o save do jogo não foi alterado')
            return True
        except (PortError, OSError) as exc:
            self.status.set(str(exc))
            if not quiet:
                messagebox.showerror('Configuração inválida', str(exc))
            return False

    def close(self):
        if self.closed:
            return
        self.save_settings(quiet=True)
        with self.experimental_lock:
            self.closed = True
        self.cancel.cancel()
        self.stop_experimental()
        self.progress.stop()
        try:
            self.root.after_cancel(self.after_id)
        except tk.TclError:
            pass
        self.root.destroy()

    def stop_experimental(self):
        """Stop only the child started by this launcher; never search global PIDs."""
        self.cancel.cancel()
        with self.experimental_lock:
            process = self.experimental_process
        if process is None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            return

        def stop():
            try:
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            except ProcessLookupError:
                pass

        threading.Thread(target=stop, daemon=False).start()

    def _confirm_target(self, target):
        if target == '30':
            return True
        if target == '60':
            title = '60 fps experimental'
            text = ('O modo 60 fps é experimental.\n\n'
                    'O passo de simulação foi medido em par com 30 fps, mas combate, física, '
                    'animações, áudio e campanha completa não estão certificados.\n\n'
                    'Usa o mesmo save deste usuário em todos os alvos de FPS.\n\n'
                    'Deseja abrir mesmo assim?')
        else:
            title = 'FPS ilimitado experimental'
            text = ('O modo ilimitado é experimental e remove a espera de pacing do motor.\n\n'
                    'Ele desliga o VSync, usa apresentação imediata e pode causar tearing, alto '
                    'consumo de GPU e velocidade de simulação incorreta.\n\n'
                    'O ganho real acima de 60 fps e a estabilidade da campanha ainda não foram validados. '
                    'Prefira 30 ou 60 fps para uso normal.\n\n'
                    'Usa o mesmo save deste usuário em todos os alvos de FPS.\n\n'
                    'Deseja abrir mesmo assim?')
        return messagebox.askyesno(title, text)

    def play_command(self, folder=None):
        folder = Path(folder or self.source.get()).expanduser().resolve()
        data = self._graphics_data()
        command = python_command(PROJECT / 'scripts/play_green_lantern.py') + [
                   '--shader-mode', data['shader_mode'],
                   '--vsync', 'on' if data['vsync'] else 'off',
                   '--fps-target', data['fps_target'],
                   '--output-resolution', data['output_resolution'],
                   '--graphics-preset', data['preset'], '--upscaler', data['upscaler'],
                   '--fullscreen', 'on' if data['fullscreen'] else 'off',
                   '--fsr-sharpness', str(data['fsr_sharpness']),
                   '--shader-preload', 'on' if data['shader_preload'] else 'off']
        if data['preset'] == 'custom':
            command += ['--antialiasing', data['antialiasing'],
                        '--render-scale', str(data['render_scale']),
                                                '--anisotropic', str(data['anisotropic']),
                        '--texture-quality', data['texture_quality'],
                        '--dither', 'on' if data['present_dither'] else 'off']
        if data['fps_target'] == 'unlimited':
            command += ['--present-mode', 'immediate']
        if self.hd_texture_pack.get() and data['texture_quality'] in ('high', 'ultra'):
            command += ['--hd-texture-pack', self.hd_texture_pack.get()]
        command.append(str(folder))
        return command

    def play(self):
        if self.busy or self.closed:
            return
        target = self.fps_target.get()
        if not self._source_ready():
            messagebox.showwarning('Pasta do jogo', 'Selecione uma pasta que contenha default.xex.')
            self.status.set('Selecione uma pasta válida com default.xex.')
            return
        if not self._engine_ready(target):
            self.generate_native()
            return
        if not self._confirm_target(target):
            self.status.set(f'{graphics.TARGET_LABELS[target]} cancelado • 30 fps continua sendo o padrão')
            return
        if not self.save_settings(quiet=True):
            return
        kind = TARGET_TITLES[target]
        # All Tk variable reads happen here, on the main thread. The worker
        # must only deal with plain values so Tcl is never touched off-thread.
        folder = Path(self.source.get()).expanduser()
        try:
            graphics_data = self._graphics_data()
        except (PortError, tk.TclError) as exc:
            self.status.set(str(exc))
            return
        command = self.play_command(folder)
        texture_work = Workspace(self.workspace.get(), PROJECT)
        def action():
            from .texture_pipeline import ensure_graphics_textures
            prepared = ensure_graphics_textures(folder, graphics_data, PROJECT, texture_work,
                cancel=self.cancel, emit=lambda e: self.queue.put(('hd-event', '', e)), allow_download=True)
            self.queue.put(('hd-selection', '', prepared))
            # Rebuild only the HD argument from worker-owned plain values.
            if '--hd-texture-pack' in command:
                pos = command.index('--hd-texture-pack'); del command[pos:pos + 2]
            if prepared['pack']:
                command[-1:-1] = ['--hd-texture-pack', prepared['pack']]
            checked = subprocess.run(command + ['--dry-run'], capture_output=True, text=True,
                                     timeout=30, cwd=PROJECT, env=external_env())
            self.cancel.check()
            if checked.returncode:
                raise PortError('EXPERIMENTAL_VALIDATION', (checked.stderr or checked.stdout).strip()
                                or 'A validação da instalação falhou.')
            output = PROJECT / '.aster/reports' / f'launcher-play-{time.time_ns()}.log'
            output.parent.mkdir(parents=True, exist_ok=True)
            process = None
            try:
                with output.open('w') as console:
                    console.write(checked.stdout)
                    console.flush()
                    with self.experimental_lock:
                        self.cancel.check()
                        if self.closed:
                            raise PortError('CANCELLED', 'Launcher fechado antes de iniciar o jogo.')
                        process = subprocess.Popen(command, cwd=PROJECT, stdout=console,
                                                   stderr=subprocess.STDOUT, env=external_env())
                        self.experimental_process = process
                    self.queue.put(('event', '', {
                        'task': kind, 'state': 'running',
                        'message': f'{graphics.TARGET_LABELS[target]} aberto. '
                                   f'Preset {graphics.PRESET_LABELS[graphics_data["preset"]]}. '
                                   'Feche a janela do jogo ou use Encerrar sessão.',
                        'log': str(output), 'pid': process.pid}))
                    code = process.wait()
                self.cancel.check()
                if code:
                    raise PortError('EXPERIMENTAL_EXIT', f'A sessão terminou com código {code}. Consulte {output}')
                return {'ready': False, 'experimental': target != '30', 'fps_target': target,
                        'graphics_preset': graphics_data['preset'],
                        'graphics': graphics_data, 'exit_code': code, 'log': str(output)}
            finally:
                with self.experimental_lock:
                    if self.experimental_process is process:
                        self.experimental_process = None
        self.start(action, kind)
        self.stop_experimental_button.configure(state='normal')

    def play_experimental(self):
        self.play()

    def play_experimental_60fps(self):
        self.choose_target('60')
        self.play()

    # -------------------------------------------------------------- utilities
    def set_summary(self, text):
        self.summary.configure(state='normal')
        self.summary.delete('1.0', 'end')
        self.summary.insert('end', text)
        self.summary.configure(state='disabled')

    def log(self, event):
        self.events.append(event)
        self.events = self.events[-1000:]
        self.logs.configure(state='normal')
        self.logs.insert('end', json.dumps(event, ensure_ascii=False) + '\n')
        if int(self.logs.index('end-1c').split('.')[0]) > 1500:
            self.logs.delete('1.0', '500.0')
        self.logs.see('end')
        self.logs.configure(state='disabled')
        if event.get('task') and event.get('state'):
            name = event['task']
            values = (event['state'], f"{event['seconds']:.3f}s" if 'seconds' in event else '—')
            if self.task_tree.exists(name):
                self.task_tree.item(name, values=values)
            else:
                self.task_tree.insert('', 'end', iid=name, text=name, values=values)

    def select(self):
        p = filedialog.askopenfilename(title='Selecionar ISO ou XEX',
                                      filetypes=[('Dumps Xbox 360', '*.iso *.ISO *.xex *.XEX'),
                                                 ('Todos', '*')])
        if p:
            self.source.set(p)
            self.save_settings(quiet=True)
            self.inspect()

    def select_folder(self):
        p = filedialog.askdirectory(title='Pasta com default.xex e assets do jogo', mustexist=True)
        if p:
            self.source.set(p)
            self.save_settings(quiet=True)
            self.inspect()

    def select_workspace(self):
        p = filedialog.askdirectory(title='Selecionar diretório de trabalho dentro do projeto',
                                    initialdir=str(PROJECT), mustexist=True)
        if p:
            self.workspace.set(p)

    def open_profile(self):
        path = PROJECT / PROFILE_FILES[self.fps_target.get()] / 'user'
        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == 'win32':
                import os
                os.startfile(path)
            else:
                subprocess.Popen(['xdg-open', str(path)], env=external_env())
        except OSError as exc:
            self.status.set(f'Não foi possível abrir o perfil: {exc}')

    def start(self, action, kind):
        if self.busy:
            return False
        self.busy = True
        self.build_running = kind == 'Gerar port'
        if self.build_running:
            self.stage_states = {key: 'pending' for key, *_ in BUILD_STAGES}
            self.active_stage = None
            self.build_reused = False
            self.build_heading.set('Preparando sua versão para PC')
            self.build_detail.set('Conferindo o dump e o ambiente local…')
            self.build_measure.set('Aguardando a primeira etapa')
            self.build_elapsed.set('00:00')
            self._paint_build_steps()
        self.cancel = Cancellation()
        self._set_busy_controls(False)
        self.progress.configure(mode='indeterminate')
        self.progress.start(15)
        self.task_started = time.monotonic()
        self.status.set('Tarefa em andamento…')
        self.log({'task': kind, 'state': 'running'})

        def worker():
            try:
                result = action()
                self.queue.put(('done', kind, result))
            except PortError as exc:
                self.queue.put(('error', kind, exc.as_dict()))
            except Exception as exc:
                self.queue.put(('error', kind, {'code': 'UNEXPECTED', 'message': str(exc)}))

        threading.Thread(target=worker, daemon=True).start()
        return True

    def inspect(self):
        value = self.source.get()
        self.start(lambda: inspect_source(value, self.cancel), 'Inspecionar')

    def prepare(self):
        try:
            cfg = self.config()
            settings.save(cfg, PROJECT)
        except (PortError, OSError) as exc:
            self.status.set(str(exc))
            self.log({'task': 'Preparar', 'error': str(exc)})
            return
        self.start(lambda: prepare(cfg['source'], Workspace(cfg['workspace'], PROJECT), GreenLantern(),
                                   self.cancel, emit=lambda e: self.queue.put(('event', '', e)),
                                   config={'build_type': cfg['build_type'], 'jobs': cfg['jobs']}),
                   'Preparar')

    def generate_native(self):
        if self.busy or self.closed:
            return
        try:
            cfg = self.config()
        except PortError as exc:
            self.status.set(str(exc))
            return
        if not self._source_ready():
            messagebox.showwarning('Dump extraído', 'Selecione a pasta com default.xex e os assets.')
            return
        consent = messagebox.askyesno('Gerar port local',
            'O XEX será verificado e recompilado neste PC. Os arquivos originais não serão alterados.\n\n'
            'Se faltarem fontes do SDK ReXGlue 0.10.0 e dependências, baixá-las nas revisões fixadas? '
            'A primeira geração compila o SDK gráfico completo no Linux e no Windows e pode demorar.\n\n'
            'Preparar também as dependências ausentes pelo gerenciador oficial do sistema? '
            'A instalação de ferramentas e bibliotecas pode pedir autorização de administrador '
            'e ocupar vários GB na primeira geração. O launcher verificará os requisitos novamente ao concluir.')
        if not consent:
            return
        source, jobs = cfg['source'], cfg['jobs']
        graphics_data = self._graphics_data()
        texture_work = Workspace(cfg['workspace'], PROJECT)
        def generate():
            result = build_native(source, Workspace(PROJECT / '.aster', PROJECT), self.cancel,
                                  emit=lambda e: self.queue.put(('event', '', e)), jobs=jobs, allow_download=True,
                                  install_dependencies=True)
            from .texture_pipeline import ensure_graphics_textures
            textures = ensure_graphics_textures(source, graphics_data, PROJECT, texture_work,
                cancel=self.cancel, emit=lambda e: self.queue.put(('hd-event', '', e)), allow_download=True)
            self.queue.put(('hd-selection', '', textures))
            return result
        self.start(generate, 'Gerar port')
        self.tabs.select(self.build_tab)

    def doctor(self):
        self.start(lambda: diagnostics(self.cancel), 'Diagnóstico')

    def clear_cache(self):
        if messagebox.askyesno('Limpar cache', 'Apagar somente cache/v1 dentro do diretório de trabalho?\n'
                               'As origens, os relatórios e as saídas serão preservados.'):
            try:
                Workspace(self.workspace.get(), PROJECT).clear_cache(confirmed=True)
                self.log({'task': 'Limpar cache', 'state': 'completed'})
            except (PortError, OSError) as exc:
                messagebox.showerror('Falha', str(exc))

    def export_report(self):
        try:
            work = Workspace(self.workspace.get(), PROJECT)
            p = work.write_json(f'reports/launcher-{time.time_ns()}.json',
                                {'schema': 2, 'ready': False, 'source': self.source.get(),
                                 'graphics': self._graphics_data(), 'last_result': self.last_result,
                                 'environment': self.last_environment, 'events': self.events})
            self.report_path.set(str(p))
            self.status.set('Diagnóstico salvo localmente')
        except (PortError, OSError) as exc:
            self.status.set(str(exc))

    def copy_logs(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.logs.get('1.0', 'end'))
        self.status.set('Logs copiados para a área de transferência')

    def show_source(self, value):
        info = value.get('source', value)
        title = info.get('title_id')
        identity = ('Title ID corresponde ao módulo Green Lantern; revisão ainda não confirmada.'
                    if title == GreenLantern.title_id else
                    'Title ID de outro jogo.' if title else 'Jogo ainda não identificado por Title ID.')
        lines = [f"Formato: {info.get('format', 'desconhecido')}  |  Title ID: {title or 'não disponível'}",
                 identity, f"Executável/entrada: {info.get('path', '')}"]
        if info.get('format') == 'xex2':
            lines += [f"Acesso ao código: {info.get('code_access', 'não determinado')}",
                      f"Criptografia: {info.get('encryption')} | Compressão: {info.get('compression')}"]
        if info.get('game_directory'):
            lines += [f"Pasta: {info['game_directory']}",
                      f"Inventário: {info['file_count']} arquivos / {info['total_bytes']:,} bytes",
                      f"Outros arquivos (possíveis assets): {info['asset_file_count']}. Completude não verificada.",
                      '', 'Arquivos (amostra):']
            lines += [f"  {r['path']}  ({r['size']:,} bytes)" for r in info['inventory'][:12]]
        else:
            lines += ['XEX isolado não garante assets; selecione a pasta extraída para inventariá-los.']
        if value.get('sha256'):
            lines += ['', f"SHA-256: {value['sha256']}",
                      f"Dependências ausentes: {', '.join(value['missing_dependencies']) or 'nenhuma das sondadas'}",
                      f"Preparação salva. Bloqueio: {value.get('blocker', 'NO_NATIVE_BACKEND')}."]
        if value.get('analysis'):
            analysis = value['analysis']
            lines += ['', 'PE decodificado e validado para este hash de origem.',
                      f"Imports identificados: {analysis['imports']['unique_apis']} APIs."]
            if analysis.get('native_leaf_probe'):
                lines += ['Experimento nativo de uma função: 10.000 casos aprovados. Não é execução do jogo.']
            lines += ['Runtime e backend integral do jogo ainda pendentes.']
        self.set_summary('\n'.join(lines))
        self.source_status.set(f"Jogo / {'Title ID reconhecido' if title == GreenLantern.title_id else 'identidade não confirmada'}")
        self.tabs.select(self.game_tab)

    def poll(self):
        while True:
            try:
                state, kind, value = self.queue.get_nowait()
            except queue.Empty:
                break
            if state == 'hd-selection':
                self.hd_texture_pack.set(value.get('pack') or '')
                self.hd_material_count = value.get('material_count', 0)
                self._refresh_hd_status()
                self.save_settings(quiet=True)
                continue
            if state == 'hd-event':
                self.log(value)
                self._hd_event(value)
                continue
            if state == 'event':
                self.log(value)
                self._build_event(value)
                self.status.set(value.get('message') or value.get('task') or self.build_heading.get())
                continue
            self.busy = False
            if kind in ('Preparar texturas HD', 'Selecionar pacote HD'):
                self.hd_running = False
                self.hd_progress.stop()
                self.hd_progress.configure(mode='determinate', value=100 if state == 'done' else 0)
            self.progress.stop()
            if kind == 'Gerar port':
                self.build_running = False
                if state == 'error':
                    cancelled = value.get('code') == 'CANCELLED'
                    if self.active_stage:
                        self.stage_states[self.active_stage] = 'cancelled' if cancelled else 'failed'
                    self.build_heading.set('Geração cancelada' if cancelled else 'Não foi possível concluir')
                    self.build_detail.set(value['message'])
                    self.build_measure.set('Você pode retomar a geração. Os arquivos já compilados foram mantidos.')
                    self.progress.configure(mode='determinate')
                else:
                    self.stage_states = {key: 'completed' for key, *_ in BUILD_STAGES}
                    self.build_heading.set('Seu port está pronto')
                    self.build_detail.set('Volte à Biblioteca e clique em Jogar agora para testar a inicialização.')
                    self.build_measure.set('Build reutilizado · nenhuma recompilação' if self.build_reused else 'Geração concluída · arquivos verificados')
                    self.progress.configure(mode='determinate', value=100)
                self._paint_build_steps()
            else:
                self.progress.configure(mode='determinate', value=0)
            self._set_busy_controls(True)
            self._refresh_engine_status()
            self.last_result = value
            self.log({'task': kind,
                      'state': ('cancelled' if value.get('code') == 'CANCELLED' else 'failed')
                      if state == 'error' else 'blocked' if value.get('state') == 'blocked' else 'completed',
                      'seconds': time.monotonic() - self.task_started,
                      **({'error': value} if state == 'error' else {})})
            if state == 'error':
                if kind in ('Preparar texturas HD', 'Selecionar pacote HD'):
                    self._refresh_hd_status()
                self.status.set(f"{value['code']} • {value['message']}")
                self.set_summary(json.dumps(value, indent=2, ensure_ascii=False))
                if kind == 'Inspecionar':
                    self.source_status.set('Jogo / entrada inválida ou não suportada')
            elif kind in ('Preparar texturas HD', 'Selecionar pacote HD'):
                self.hd_texture_pack.set(value['pack'] or '')
                self.hd_material_count = value.get('material_count')
                self._refresh_hd_status()
                self.save_settings(quiet=True)
                self.status.set('Materiais HD preparados e selecionados · uso habilitado em Alta/Ultra'
                                if kind == 'Preparar texturas HD' else
                                'Pacote HD verificado e selecionado · uso habilitado em Alta/Ultra')
            elif kind == 'Diagnóstico':
                self.last_environment = value
                missing = [n for n in GreenLantern().dependencies()
                           if not value['tools'].get(n, {}).get('available')]
                self.environment_status.set(
                    f"Ambiente / {'faltam: ' + ', '.join(missing) if missing else 'ferramentas básicas disponíveis'}")
                self.environment.configure(state='normal')
                self.environment.delete('1.0', 'end')
                self.environment.insert('end', '\n'.join(
                    f"{name}: {tool.get('version') or ('não encontrado' if not tool['available'] else 'versão não confirmada')}"
                    for name, tool in value['tools'].items()))
                ghidra = value.get('ghidra', {})
                self.environment.insert('end', f"\nGhidra local: {ghidra.get('version') or 'não encontrado'}\n"
                                               'REA MCP: acesso não consultado pelo launcher independente')
                self.environment.configure(state='disabled')
                self.status.set('Diagnóstico concluído • port nativo em validação')
            elif kind == 'Gerar port':
                self.status.set('Port gerado localmente • pronto para testar a inicialização')
                self.set_summary(value.get('message', '') + '\n' + str(value.get('binary', '')))
                self._refresh_engine_status()
                self.tabs.select(self.build_tab)
            elif kind.startswith('Jogar'):
                target = value.get('fps_target', self.fps_target.get())
                if target == '60':
                    self.status.set('Sessão 60 fps encerrada • timestep medido; validação humana pendente')
                elif target == 'unlimited':
                    self.status.set('Sessão ilimitada encerrada • modo experimental; valide a sensação no jogo')
                else:
                    self.status.set('Sessão 30 fps encerrada • campanha completa ainda não validada')
                self.report_path.set(value['log'])
            else:
                self.show_source(value)
                self.status.set('Inspeção concluída • port nativo em validação' if kind == 'Inspecionar'
                                else f"Relatório salvo • compilação bloqueada: {value.get('blocker', 'NO_NATIVE_BACKEND')}")
                if kind == 'Preparar':
                    self.tabs.select(self.game_tab)
        self._refresh_play_state()
        if self.build_running:
            elapsed = int(time.monotonic() - self.task_started)
            self.build_elapsed.set(f'{elapsed//60:02}:{elapsed%60:02}')
        self.after_id = self.root.after(50, self.poll)


def main():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise PortError('DISPLAY_UNAVAILABLE', 'Não foi possível abrir o display gráfico.',
                        reason=str(exc)) from exc
    Launcher(root)
    root.mainloop()
