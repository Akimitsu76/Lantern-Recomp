"""Frozen Linux Tk/Xft uses its own Fontconfig config, before Tk initializes.

This process environment change neither installs fonts nor changes host files.
The config lists no system directories: load_fonts registers the shipped faces.
"""
import os
from pathlib import Path
import sys

if sys.platform.startswith('linux') and hasattr(sys, '_MEIPASS'):
    config = Path(sys._MEIPASS) / 'launcher_fontconfig.conf'
    if config.is_file() and not config.is_symlink():
        os.environ['FONTCONFIG_FILE'] = str(config)
