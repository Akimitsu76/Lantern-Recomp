"""Offline product-image cards shared by the Windows and Linux launcher."""
from pathlib import Path
import math
import tkinter as tk

ASSETS = Path(__file__).resolve().parent / 'resources' / 'controllers'
MODELS = {
    'xbox': ('Xbox', 'Xbox Wireless Controller · Series X|S', 'xbox-series.png', '#b4ed74'),
    'playstation': ('PlayStation', 'DualSense · PlayStation 5', 'dualsense.png', '#8fbaff'),
}


class ControllerCard(tk.Canvas):
    def __init__(self, parent, family, variable):
        super().__init__(parent, width=420, height=245, background='#111a16',
                         highlightthickness=1, highlightbackground='#283a30',
                         cursor='hand2', takefocus=True)
        self.family, self.variable = family, variable
        self._photo = self._source = None
        self._pending = None
        self.image_error = None
        self._hover = False
        self.bind('<Configure>', self._schedule)
        self.bind('<Enter>', lambda _: self._hovered(True))
        self.bind('<Leave>', lambda _: self._hovered(False))
        self.bind('<Button-1>', self._select)
        self.bind('<Return>', self._select)
        self.bind('<space>', self._select)
        self.bind('<FocusIn>', self._schedule)
        self.bind('<FocusOut>', self._schedule)
        self.bind('<Destroy>', self._destroyed, add='+')
        self._trace = variable.trace_add('write', self._schedule)

    def _select(self, _=None):
        self.variable.set(MODELS[self.family][0])
        self.focus_set()
        return 'break'

    def _hovered(self, value):
        self._hover = value
        self._schedule()

    def _destroyed(self, event):
        if event.widget is self:
            if self._pending is not None:
                self.after_cancel(self._pending)
            self.variable.trace_remove('write', self._trace)

    def _schedule(self, *_):
        if self.winfo_exists():
            if self._pending is not None:
                self.after_cancel(self._pending)
            self._pending = self.after(35, self._paint)

    def _paint(self):
        self._pending = None
        if not self.winfo_exists():
            return
        width = max(260, self.winfo_width())
        name, subtitle, filename, accent = MODELS[self.family]
        selected = self.variable.get() == name
        self.configure(highlightbackground=accent if selected or self._hover else '#283a30',
                       highlightcolor=accent)
        self.delete('all')
        self.create_text(20, 21, text=name, anchor='w', fill='#f0f4f8',
                         font=('DejaVu Sans', 12, 'bold'))
        self.create_text(20, 44, text=subtitle, anchor='w', fill='#9aaa9f',
                         font=('DejaVu Sans', 9))
        if selected:
            self.create_text(width-18, 21, text='SELECIONADO', anchor='e',
                             fill=accent, font=('DejaVu Sans', 8, 'bold'))
        self.image_error = None
        try:
            from PIL import Image, ImageTk, ImageOps
            if self._source is None:
                with Image.open(ASSETS / filename) as original:
                    original = original.convert('RGBA')
                    # Remove only empty display margins; bundled source bytes
                    # and all product details are preserved unchanged.
                    bounds = original.getchannel('A').getbbox()
                    self._source = original.crop(bounds) if bounds else original.copy()
            fitted = ImageOps.contain(self._source, (min(width-44, 390), 164), Image.Resampling.LANCZOS)
            self._photo = ImageTk.PhotoImage(fitted, master=self)
        except ImportError:
            try:
                original = tk.PhotoImage(master=self, file=str(ASSETS / filename))
                factor = max(1, math.ceil(original.width() / (width-44)), math.ceil(original.height() / 164))
                self._photo = original.subsample(factor)
            except tk.TclError as exc:
                self.image_error = str(exc)
                self._photo = None
        except (OSError, tk.TclError) as exc:
            self.image_error = str(exc)
            self._photo = None
        if self._photo is not None:
            self.create_image(width/2, 153, image=self._photo)
        else:
            self.create_text(width/2, 151, text='Imagem do controle indisponível', fill='#9aaa9f')
