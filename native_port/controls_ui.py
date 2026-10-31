"""Controls preferences, with real offline Xbox and DualSense product images."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from . import controls
from .controller_artwork import ControllerCard

BG = '#090c0b'
CARD = '#111a16'
INK = '#f0f4f8'
MUTED = '#98a99f'
ACCENT = '#b4ed74'


class ControlsPanel(ttk.Frame):
    def __init__(self, parent, config=None):
        super().__init__(parent)
        config = controls.validate(config if config is not None else controls.defaults())
        self.layout = tk.StringVar(self, value=controls.LAYOUTS[config['layout']])
        self.keyboard_enabled = tk.BooleanVar(self, value=config['keyboard_enabled'])
        self.mouse_look = tk.BooleanVar(self, value=config['mouse_look'])
        self.mouse_sensitivity = tk.StringVar(self, value=str(config['mouse_sensitivity']))
        self.keyboard = {key: tk.StringVar(self, value=value) for key, value in config['keyboard'].items()}
        self.gamepad = {key: tk.StringVar(self, value=controls.PAD_LABELS[value])
                        for key, value in config['gamepad']['bindings'].items()}
        self.axes = {key: tk.BooleanVar(self, value=config['gamepad'][key]) for key in controls.AXIS_FIELDS}
        self.deadzone = tk.IntVar(self, value=config['gamepad']['deadzone'])
        self._styles()
        header = ttk.Frame(self)
        header.pack(fill='x', pady=(0, 14))
        ttk.Label(header, text='Controles', font=('DejaVu Sans', 20, 'bold')).pack(side='left')
        ttk.Button(header, text='Restaurar padrão', command=lambda: self.set_settings(controls.defaults())).pack(side='right')
        options = ttk.Frame(self)
        options.pack(fill='x', pady=(0, 14))
        ttk.Label(options, text='Layout dos botões', font=('DejaVu Sans', 10, 'bold')).pack(side='left')
        ttk.Combobox(options, state='readonly', width=17, values=list(controls.LAYOUTS.values()),
                     textvariable=self.layout).pack(side='left', padx=(16, 14))
        ttk.Label(options, text='Escolha a referência visual dos comandos.', foreground=MUTED).pack(side='left')
        wrapper = ttk.Frame(self)
        wrapper.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(wrapper, bg=BG, highlightthickness=0, height=310)
        scrollbar = ttk.Scrollbar(wrapper, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y', padx=(8, 0))
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = ttk.Frame(self.canvas)
        window = self.canvas.create_window(0, 0, window=self.body, anchor='nw')
        self.body.bind('<Configure>', lambda _: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda event: self.canvas.itemconfigure(window, width=event.width))
        self.body.columnconfigure((0, 1), weight=1, uniform='control-columns')
        self.previews = {}
        for column, family in enumerate(('xbox', 'playstation')):
            card = ControllerCard(self.body, family, self.layout)
            card.grid(row=0, column=column, sticky='ew', padx=(0, 8) if column == 0 else (8, 0), pady=(0, 18))
            self.previews[family] = card
        keyboard = self._column(self.body, 0, 'Teclado e mouse', 'Personalize as teclas e os movimentos da câmera.')
        gamepad = self._column(self.body, 1, 'Controle', 'Ação do jogo → botão físico do controle.')
        self._keyboard_fields(keyboard)
        self._gamepad_fields(gamepad)
        self._bind_scroll(self)
        ttk.Label(self, text='Salve para aplicar na próxima abertura do jogo. Seus saves permanecem os mesmos.',
                  foreground=MUTED, wraplength=950).pack(anchor='w', pady=(12, 0))

    def _styles(self):
        style = ttk.Style(self)
        style.configure('Controls.Card.TFrame', background=CARD)
        style.configure('Controls.Card.TLabel', background=CARD, foreground=INK)
        style.configure('Controls.Muted.TLabel', background=CARD, foreground=MUTED)
        style.configure('Controls.Group.TLabel', background=CARD, foreground=ACCENT, font=('DejaVu Sans', 9, 'bold'))
        style.configure('Controls.TCheckbutton', background=CARD, foreground=INK, padding=(0, 4))
        style.map('Controls.TCheckbutton', background=[('active', CARD)])
        style.configure('Controls.TEntry', padding=(10, 8), fieldbackground='#0b120e', foreground=INK,
                        bordercolor='#304237', lightcolor='#304237', darkcolor='#304237')
        style.configure('Controls.TCombobox', padding=(8, 7), fieldbackground='#0b120e', foreground=INK,
                        bordercolor='#304237', lightcolor='#304237', darkcolor='#304237', arrowcolor=MUTED)
        style.map('Controls.TCombobox', fieldbackground=[('readonly', '#0b120e')],
                  selectbackground=[('readonly', '#0b120e')], selectforeground=[('readonly', INK)])

    @staticmethod
    def _column(parent, column, title, subtitle):
        outer = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground='#283a30')
        outer.grid(row=1, column=column, sticky='new', padx=(0, 8) if column == 0 else (8, 0))
        inner = ttk.Frame(outer, style='Controls.Card.TFrame', padding=18)
        inner.pack(fill='both', expand=True)
        inner.columnconfigure(1, weight=1)
        ttk.Label(inner, text=title, style='Controls.Card.TLabel', font=('DejaVu Sans', 13, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w')
        ttk.Label(inner, text=subtitle, style='Controls.Muted.TLabel', wraplength=400).grid(row=1, column=0, columnspan=2, sticky='w', pady=(6, 14))
        return inner

    @staticmethod
    def _group(parent, row, title):
        ttk.Label(parent, text=title.upper(), style='Controls.Group.TLabel').grid(
            row=row, column=0, columnspan=2, sticky='w', pady=(20, 8))
        return row + 1

    @staticmethod
    def _label(parent, row, text):
        ttk.Label(parent, text=text, style='Controls.Card.TLabel', wraplength=205).grid(
            row=row, column=0, sticky='w', padx=(0, 14), pady=5)

    def _keyboard_fields(self, parent):
        ttk.Checkbutton(parent, text='Ativar teclado', style='Controls.TCheckbutton',
                        variable=self.keyboard_enabled).grid(row=2, column=0, columnspan=2, sticky='w')
        ttk.Label(parent, text='Ex.: Space ou Shift+Up. Use vírgula para alternativas.',
                  style='Controls.Muted.TLabel', wraplength=400).grid(row=3, column=0, columnspan=2, sticky='w', pady=(4, 0))
        groups = (
            ('Combate e ações', ('a', 'b', 'x', 'y', 'left_trigger', 'right_trigger', 'left_shoulder', 'right_shoulder')),
            ('Movimento', ('lstick_up', 'lstick_down', 'lstick_left', 'lstick_right', 'lstick_press')),
            ('Câmera', ('rstick_up', 'rstick_down', 'rstick_left', 'rstick_right', 'rstick_press')),
            ('Menus e direcional', ('back', 'start', 'dpad_up', 'dpad_down', 'dpad_left', 'dpad_right', 'guide')),
        )
        row = 4
        for title, keys in groups:
            row = self._group(parent, row, title)
            for key in keys:
                self._label(parent, row, controls.KEYBOARD_LABELS[key])
                ttk.Entry(parent, style='Controls.TEntry', textvariable=self.keyboard[key], width=17).grid(
                    row=row, column=1, sticky='ew', pady=4)
                row += 1
        row = self._group(parent, row, 'Mouse')
        ttk.Checkbutton(parent, text='Mouse controla a câmera', style='Controls.TCheckbutton',
                        variable=self.mouse_look).grid(row=row, column=0, columnspan=2, sticky='w', pady=(0, 8))
        self._label(parent, row+1, 'Sensibilidade')
        ttk.Spinbox(parent, from_=.01, to=10, increment=.1, width=9,
                    textvariable=self.mouse_sensitivity).grid(row=row+1, column=1, sticky='w')

    def _gamepad_fields(self, parent):
        actions = {key: (label, description) for key, label, description in controls.ACTIONS}
        groups = (
            ('Combate e ações', ('a', 'b', 'x', 'y', 'left_trigger', 'right_trigger', 'left_shoulder', 'right_shoulder')),
            ('Menus e direcional', ('back', 'start', 'dpad_up', 'dpad_down', 'dpad_left', 'dpad_right')),
            ('Analógicos', ('lstick_press', 'rstick_press')),
        )
        row = 2
        for title, keys in groups:
            row = self._group(parent, row, title)
            for key in keys:
                _, description = actions[key]
                self._label(parent, row, description)
                field = ttk.Combobox(parent, state='readonly', width=17, style='Controls.TCombobox',
                                     values=list(controls.PAD_LABELS.values()), textvariable=self.gamepad[key])
                field.grid(row=row, column=1, sticky='ew', pady=4)
                row += 1
        row = self._group(parent, row, 'Ajustes dos analógicos')
        labels = {'swap_sticks': 'Trocar os analógicos', 'invert_lx': 'Inverter movimento horizontal',
                  'invert_ly': 'Inverter movimento vertical', 'invert_rx': 'Inverter câmera horizontal',
                  'invert_ry': 'Inverter câmera vertical'}
        for key in controls.AXIS_FIELDS:
            ttk.Checkbutton(parent, text=labels[key], style='Controls.TCheckbutton', variable=self.axes[key]).grid(
                row=row, column=0, columnspan=2, sticky='w', pady=2)
            row += 1
        self._label(parent, row, 'Zona morta adicional (%)')
        ttk.Spinbox(parent, from_=0, to=30, textvariable=self.deadzone, width=6).grid(row=row, column=1, sticky='w')

    def _bind_scroll(self, widget):
        widget.bind('<MouseWheel>', self._scroll, add='+')
        widget.bind('<Button-4>', self._scroll, add='+')
        widget.bind('<Button-5>', self._scroll, add='+')
        for child in widget.winfo_children():
            self._bind_scroll(child)

    def _scroll(self, event):
        if getattr(event, 'num', None) in (4, 5):
            steps = -1 if event.num == 4 else 1
        else:
            delta = event.delta
            if not delta:
                return
            steps = -int(delta/120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
        self.canvas.yview_scroll(steps * 3, 'units')
        return 'break'

    def get_settings(self):
        reverse_layout = {label: key for key, label in controls.LAYOUTS.items()}
        reverse_buttons = {label: key for key, label in controls.PAD_LABELS.items()}
        try:
            config = {'schema': controls.SCHEMA, 'layout': reverse_layout[self.layout.get()],
                      'keyboard_enabled': self.keyboard_enabled.get(), 'mouse_look': self.mouse_look.get(),
                      'mouse_sensitivity': float(self.mouse_sensitivity.get()),
                      'keyboard': {key: var.get() for key, var in self.keyboard.items()},
                      'gamepad': {'bindings': {key: reverse_buttons[var.get()] for key, var in self.gamepad.items()},
                                  **{key: var.get() for key, var in self.axes.items()}, 'deadzone': self.deadzone.get()}}
        except (ValueError, KeyError, tk.TclError) as exc:
            from .errors import PortError
            raise PortError('CONTROLS_VALUE', 'Confira os valores dos controles.') from exc
        return controls.validate(config)

    def set_settings(self, config):
        config = controls.validate(config)
        self.layout.set(controls.LAYOUTS[config['layout']]); self.keyboard_enabled.set(config['keyboard_enabled'])
        self.mouse_look.set(config['mouse_look']); self.mouse_sensitivity.set(str(config['mouse_sensitivity']))
        for key, value in config['keyboard'].items(): self.keyboard[key].set(value)
        for key, value in config['gamepad']['bindings'].items(): self.gamepad[key].set(controls.PAD_LABELS[value])
        for key in controls.AXIS_FIELDS: self.axes[key].set(config['gamepad'][key])
        self.deadzone.set(config['gamepad']['deadzone'])
