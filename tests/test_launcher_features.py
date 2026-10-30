import json
import os
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.environ.get('DISPLAY'), 'GUI requires DISPLAY/Xvfb')
class LauncherFeatureTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        project = patch('native_port.launcher.PROJECT', self.project)
        project.start()
        self.addCleanup(project.stop)
        from native_port.launcher import Launcher
        self.app = Launcher(self.root)
        self.addCleanup(self.app.close)

    def test_real_controls_tab_and_languages_live_on_game_page_not_save_selector(self):
        tabs = list(self.app.tabs.tabs())
        self.assertEqual(tabs[tabs.index(str(self.app.graphics_tab)) + 1], str(self.app.controls_tab))
        self.assertTrue(self.app.controls_panel.winfo_exists())
        self.assertTrue(self.app.language_controls.winfo_exists())
        self.assertNotIn('slot', ' '.join(self.app.tabs.tab(t, 'text').lower() for t in tabs))

    def test_save_and_play_forward_configured_input_and_both_languages(self):
        self.app.controls_panel.keyboard['a'].set('J')
        self.app.controls_panel.layout.set('PlayStation')
        self.app.language_controls.voice_language.set('Français')
        self.assertTrue(self.app.save_settings(quiet=True))
        from native_port import settings
        saved = settings.load(self.project)
        self.assertEqual(saved['controls']['keyboard']['a'], 'J')
        self.assertEqual(saved['languages'], {'subtitle_language': 'pt-BR', 'voice_language': 'fr'})
        command = self.app.play_command('/tmp/synthetic-game')
        config = json.loads(command[command.index('--controls-json') + 1])
        self.assertEqual(config['keyboard']['a'], 'J')
        self.assertEqual(config['layout'], 'playstation')
        self.assertEqual(command[command.index('--subtitle-language') + 1], 'pt-BR')
        self.assertEqual(command[command.index('--voice-language') + 1], 'fr')
        self.assertFalse((self.project / '.aster/runtime').exists())

    def test_navigation_and_game_options_fit_minimum_width_and_scroll(self):
        self.root.deiconify()
        self.root.geometry('1088x720')
        self.root.update()
        for button in self.app.nav_buttons.values():
            self.assertLessEqual(button.winfo_rootx() + button.winfo_width(),
                                 self.root.winfo_rootx() + self.root.winfo_width())
        self.app.tabs.select(self.app.game_tab)
        self.root.update()
        self.assertTrue(self.app.game_canvas.bbox('all'))
        self.app.game_canvas.yview_moveto(1)
        self.root.update()
        self.assertGreater(self.app.game_canvas.yview()[0], 0)


if __name__ == '__main__':
    unittest.main()
