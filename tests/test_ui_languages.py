import tkinter as tk
from tkinter import ttk
import unittest

from native_port import languages
from native_port.ui_languages import LanguageControls


class LanguageControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
            cls.root.withdraw()
        except tk.TclError as exc:
            raise unittest.SkipTest('Tk display unavailable: ' + str(exc))

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_two_independent_choices_and_no_portuguese_voice(self):
        panel = LanguageControls(self.root)
        try:
            boxes = [w for w in panel.winfo_children() if isinstance(w, ttk.Combobox)]
            self.assertEqual(len(boxes), 2)
            self.assertIn('Português', boxes[0]['values'])
            self.assertNotIn('Português', boxes[1]['values'])
            self.assertEqual(panel.get(), languages.defaults())
            panel.voice_language.set('Français')
            self.assertEqual(panel.get(), {'subtitle_language': 'pt-BR', 'voice_language': 'fr'})
        finally:
            panel.destroy()

    def test_loading_settings_is_quiet_and_selection_reports_typed_values(self):
        changes = []
        panel = LanguageControls(self.root, on_change=changes.append)
        try:
            panel.set({'subtitle_language': 'es', 'voice_language': 'de'})
            self.assertEqual(changes, [])
            panel._changed()
            self.assertEqual(changes, [{'subtitle_language': 'es', 'voice_language': 'de'}])
            self.assertEqual(panel.get(), {'subtitle_language': 'es', 'voice_language': 'de'})
        finally:
            panel.destroy()


if __name__ == '__main__':
    unittest.main()
