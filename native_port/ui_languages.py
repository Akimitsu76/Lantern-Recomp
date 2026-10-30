"""Launcher language section; runtime application is performed by game hooks."""
import tkinter as tk
from tkinter import ttk

from . import languages


class LanguageControls(ttk.Frame):
    """Embed in the launcher's options page; call get/set with saved settings."""
    def __init__(self, parent, value=None, on_change=None):
        super().__init__(parent, style='Card.TFrame', padding=16)
        self._on_change = on_change
        self._syncing = False
        self.subtitle_language = tk.StringVar(self)
        self.voice_language = tk.StringVar(self)
        self.columnconfigure(1, weight=1)
        ttk.Label(self, text='Idiomas do jogo', style='H2.TLabel').grid(
            row=0, column=0, columnspan=2, sticky='w', pady=(0, 12))
        for row, text, variable, choices in (
                (1, 'Interface e legendas', self.subtitle_language, languages.TEXT_LANGUAGES),
                (2, 'Voz', self.voice_language, languages.VOICE_LANGUAGES)):
            ttk.Label(self, text=text, style='Card.TLabel').grid(
                row=row, column=0, sticky='w', padx=(0, 20), pady=5)
            box = ttk.Combobox(self, textvariable=variable, state='readonly', width=24,
                               values=tuple(languages.LABELS[c] for c in choices))
            box.grid(row=row, column=1, sticky='ew', pady=5)
            box.bind('<<ComboboxSelected>>', self._changed)
        ttk.Label(self, style='CardMuted.TLabel', wraplength=650,
                  text='A interface e as legendas usam os textos originais da edição. '
                       'Esta edição não contém dublagem em português. '
                       'A mudança de idioma é aplicada ao iniciar o jogo.').grid(
                           row=3, column=0, columnspan=2, sticky='w', pady=(10, 0))
        self.set(value or languages.defaults())

    def set(self, value):
        value = languages.validate(value)
        self._syncing = True
        try:
            self.subtitle_language.set(languages.LABELS[value['subtitle_language']])
            self.voice_language.set(languages.LABELS[value['voice_language']])
        finally:
            self._syncing = False

    def get(self):
        codes = {label: code for code, label in languages.LABELS.items()}
        return languages.validate({
            'subtitle_language': codes.get(self.subtitle_language.get()),
            'voice_language': codes.get(self.voice_language.get())})

    def _changed(self, _event=None):
        if not self._syncing and self._on_change:
            self._on_change(self.get())
