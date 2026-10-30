"""Controls tab; owns no launcher settings file and launches no game."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from . import controls

BG = '#090c0b'
CARD = '#131a16'
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
        header = ttk.Frame(self); header.pack(fill='x', pady=(0, 8))
        ttk.Label(header, text='Controles', font=('DejaVu Sans', 20, 'bold')).pack(side='left')
        ttk.Button(header, text='Restaurar padrão', command=lambda: self.set_settings(controls.defaults())).pack(side='right')
        options = ttk.Frame(self); options.pack(fill='x', pady=6)
        ttk.Label(options, text='Ícones no jogo').pack(side='left')
        ttk.Combobox(options, state='readonly', width=17, values=list(controls.LAYOUTS.values()), textvariable=self.layout).pack(side='left', padx=12)
        ttk.Label(options, text='Automático acompanha o controle em atividade.').pack(side='left')
        previews = ttk.Frame(self); previews.pack(fill='x', pady=8)
        self._draw_controller(previews, False)
        self._draw_controller(previews, True)
        wrapper = ttk.Frame(self); wrapper.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(wrapper, bg=BG, highlightthickness=0, height=310)
        scrollbar = ttk.Scrollbar(wrapper, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y'); self.canvas.pack(side='left', fill='both', expand=True)
        body = ttk.Frame(self.canvas)
        window = self.canvas.create_window(0, 0, window=body, anchor='nw')
        body.bind('<Configure>', lambda _: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda event: self.canvas.itemconfigure(window, width=event.width))
        body.columnconfigure(0, weight=1); body.columnconfigure(1, weight=1)
        keyboard = ttk.Frame(body); keyboard.grid(row=0, column=0, sticky='nsew', padx=(0, 18))
        gamepad = ttk.Frame(body); gamepad.grid(row=0, column=1, sticky='nsew')
        keyboard.columnconfigure(1, weight=1); gamepad.columnconfigure(1, weight=1)
        ttk.Label(keyboard, text='Teclado e mouse', font=('DejaVu Sans', 13, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w', pady=8)
        ttk.Checkbutton(keyboard, text='Ativar teclado', variable=self.keyboard_enabled).grid(row=1, column=0, columnspan=2, sticky='w')
        ttk.Label(keyboard, text='Ex.: Space, L, Shift+Up. Vírgula separa alternativas.', wraplength=440).grid(row=2, column=0, columnspan=2, sticky='w', pady=(4, 12))
        for row, key in enumerate(controls.KEYBOARD_DEFAULTS, 3):
            ttk.Label(keyboard, text=controls.KEYBOARD_LABELS[key]).grid(row=row, column=0, sticky='w', pady=3, padx=(0, 10))
            ttk.Entry(keyboard, textvariable=self.keyboard[key], width=19).grid(row=row, column=1, sticky='ew', pady=3)
        row += 1
        ttk.Checkbutton(keyboard, text='Mouse controla a câmera', variable=self.mouse_look).grid(row=row, column=0, columnspan=2, sticky='w', pady=(12, 4))
        ttk.Label(keyboard, text='Sensibilidade do mouse').grid(row=row+1, column=0, sticky='w')
        ttk.Spinbox(keyboard, from_=.01, to=10, increment=.1, width=10, textvariable=self.mouse_sensitivity).grid(row=row+1, column=1, sticky='w')
        ttk.Label(gamepad, text='Controle Xbox / PlayStation', font=('DejaVu Sans', 13, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w', pady=8)
        ttk.Label(gamepad, text='Comando do jogo → botão físico', wraplength=440).grid(row=1, column=0, columnspan=2, sticky='w', pady=(0, 8))
        for row, (key, label, description) in enumerate(controls.ACTIONS, 2):
            ttk.Label(gamepad, text=f'{label} · {description}').grid(row=row, column=0, sticky='w', padx=(0, 8), pady=3)
            ttk.Combobox(gamepad, state='readonly', width=17, values=list(controls.PAD_LABELS.values()), textvariable=self.gamepad[key]).grid(row=row, column=1, sticky='ew', pady=3)
        row += 1
        labels = {'swap_sticks': 'Trocar os analógicos', 'invert_lx': 'Inverter analógico esquerdo X',
                  'invert_ly': 'Inverter analógico esquerdo Y', 'invert_rx': 'Inverter câmera X', 'invert_ry': 'Inverter câmera Y'}
        for key in controls.AXIS_FIELDS:
            ttk.Checkbutton(gamepad, text=labels[key], variable=self.axes[key]).grid(row=row, column=0, columnspan=2, sticky='w', pady=3); row += 1
        ttk.Label(gamepad, text='Zona morta adicional (%)').grid(row=row, column=0, sticky='w')
        ttk.Spinbox(gamepad, from_=0, to=30, textvariable=self.deadzone, width=6).grid(row=row, column=1, sticky='w')
        ttk.Label(self, text='Use Salvar para aplicar as alterações na próxima abertura do jogo. As configurações não alteram o save.', wraplength=1000).pack(anchor='w', pady=(10, 0))

    @staticmethod
    def _draw_controller(parent, playstation):
        canvas = tk.Canvas(parent, width=370, height=112, bg=CARD, highlightthickness=0)
        canvas.pack(side='left', fill='x', expand=True, padx=(0, 10))
        canvas.create_text(12, 13, text='PlayStation' if playstation else 'Xbox', fill=INK, anchor='w', font=('DejaVu Sans', 11, 'bold'))
        canvas.create_polygon(74, 32, 130, 27, 222, 27, 278, 32, 303, 91, 273, 98, 240, 74, 112, 74, 79, 98, 49, 91, fill='#28372d', outline='#63836a', width=2, smooth=True)
        canvas.create_rectangle(90, 47, 101, 78, fill='#d7e0d9', outline='')
        canvas.create_rectangle(80, 57, 111, 68, fill='#d7e0d9', outline='')
        for x, y in ((143, 74), (213, 74)):
            canvas.create_oval(x-13, y-13, x+13, y+13, fill='#0b110d', outline='#63836a', width=2)
        for x, y, xbox, ps, color in ((268, 50, 'Y', '△', '#80d9b2'), (281, 65, 'B', '○', '#f1979a'),
                                     (255, 65, 'X', '□', '#dca1d2'), (268, 80, 'A', '×', '#9ec3f3')):
            canvas.create_text(x, y, text=ps if playstation else xbox, fill=color if playstation else ACCENT, font=('DejaVu Sans', 11, 'bold'))
        canvas.create_text(175, 43, text='Share    Options' if playstation else 'Back    Start', fill=MUTED, font=('DejaVu Sans', 7))
        return canvas

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
