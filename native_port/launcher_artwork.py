"""Original procedural launcher artwork. No game or reference-project assets."""
from __future__ import annotations

import tkinter as tk


class LanternHero(tk.Canvas):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, background='#080c0b', highlightthickness=0,
                         height=310, **kwargs)
        self._image = None
        self.image_error = None
        self._pending = None
        self._status = 'SEU DUMP. SEU PROGRESSO. SEU PC.'
        self.bind('<Configure>', self._resize)
        self.bind('<Destroy>', self._destroy, add='+')

    def _destroy(self, event):
        if event.widget is self and self._pending:
            self.after_cancel(self._pending)
            self._pending = None

    def _resize(self, _):
        if self._pending:
            self.after_cancel(self._pending)
        self._pending = self.after(60, self._paint)

    def set_status(self, value):
        self._status = value
        self.itemconfigure('hero-status', text=value)

    def _paint(self):
        self._pending = None
        if not self.winfo_exists():
            return
        width, height = max(1, self.winfo_width()), max(1, self.winfo_height())
        self.delete('all')
        self.image_error = None
        try:
            from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageTk
            base = Image.new('RGB', (width, height), '#080c0b')
            radial = ImageOps.invert(Image.radial_gradient('L')).resize((height*3, height*3))
            light = Image.new('L', (width, height))
            light.paste(radial, (int(width*.79-height*1.5), -height))
            light = light.point(lambda x: int(max(0, x-90)*.50))
            base.paste('#1e603b', mask=light)
            glow = Image.new('RGBA', (width, height))
            draw = ImageDraw.Draw(glow)
            cx, cy, radius = int(width*.80), int(height*.49), int(height*.34)
            draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius),
                         outline=(130, 234, 137, 145), width=9)
            draw.line((cx-radius*.76, cy-radius*.77, cx+radius*.76, cy+radius*.77),
                      fill=(128, 232, 136, 90), width=5)
            base = Image.alpha_composite(base.convert('RGBA'), glow.filter(ImageFilter.GaussianBlur(20)))
            self._image = ImageTk.PhotoImage(base, master=self)
            self.create_image(0, 0, image=self._image, anchor='nw')
        except (ImportError, OSError, tk.TclError) as error:
            self._image = None
            self.image_error = f'{type(error).__name__}: {error}'
        cx, cy, radius = width*.80, height*.49, height*.34
        for factor, color in [(1.65, '#173329'), (1.33, '#224b36'), (1, '#689756'), (.79, '#264e35')]:
            r = radius*factor
            self.create_oval(cx-r, cy-r, cx+r, cy+r, outline=color, width=1)
        # A geometric energy seal drawn specifically for this launcher.
        r = radius*.58
        self.create_oval(cx-r, cy-r, cx+r, cy+r, outline='#b4ed74', width=3)
        self.create_line(cx-r, cy-r*1.32, cx+r, cy-r*1.32, fill='#b4ed74', width=4)
        self.create_line(cx-r, cy+r*1.32, cx+r, cy+r*1.32, fill='#b4ed74', width=4)
        self.create_line(cx-r, cy-r*1.32, cx-r, cy+r*1.32, fill='#7da65b', width=2)
        self.create_line(cx+r, cy-r*1.32, cx+r, cy+r*1.32, fill='#7da65b', width=2)
        size = max(29, min(59, int(height*.16), int(width*.052)))
        left = 32
        self.create_text(left, 24, anchor='nw', text='ASTER NATIVE  /  XBOX 360 → PC',
                         fill='#9aaa9f', font=('DejaVu Sans', 9, 'bold'))
        title_y = max(54, height*.22)
        self.create_text(left, title_y, anchor='nw', text='GREEN', fill='#f3f5f0',
                         font=('DejaVu Sans Condensed', size, 'bold'))
        self.create_text(left, title_y+size*1.45, anchor='nw', text='LANTERN', fill='#b4ed74',
                         font=('DejaVu Sans Condensed', size, 'bold'))
        self.create_text(left+2, title_y+size*3, anchor='nw', text='RISE OF THE MANHUNTERS',
                         fill='#d2d8d2', font=('DejaVu Sans', max(9, size//5), 'bold'))
        self.create_text(left, height-23, anchor='w', tags='hero-status', text=self._status,
                         fill='#8b9d92', font=('DejaVu Sans', 9))
