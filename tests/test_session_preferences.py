import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import play_green_lantern as play
from native_port import controls, languages, settings
from native_port.errors import PortError


class SessionPreferenceTests(unittest.TestCase):
    def test_saved_settings_round_trip_keeps_controls_languages_and_graphics_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            config = settings.defaults(directory)
            config['controls']['keyboard']['a'] = 'J'
            config['languages'] = {'subtitle_language': 'pt-BR', 'voice_language': 'fr'}
            config['graphics']['fps_target'] = '60'
            settings.save(config, directory)
            restored = settings.load(directory)
            self.assertEqual(restored['controls']['keyboard']['a'], 'J')
            self.assertEqual(restored['languages'], config['languages'])
            self.assertEqual(restored['graphics']['fps_target'], '60')
            self.assertFalse((Path(directory) / '.aster/runtime').exists())

    def test_legacy_schema_gains_preferences_without_losing_existing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            old = {'schema': 1, 'source': '', 'workspace': str(Path(directory) / '.aster'), 'jobs': 3}
            restored = settings.validate(old, directory)
            self.assertEqual(restored['jobs'], 3)
            self.assertEqual(restored['controls'], controls.defaults())
            self.assertEqual(restored['languages'], languages.defaults())

    def test_gui_cli_payload_becomes_native_flags_once_with_independent_languages(self):
        control = controls.defaults()
        control['keyboard']['a'] = 'J'
        control['layout'] = 'playstation'
        parser, args = play.parse_arguments(['--controls-json', json.dumps(control),
                                            '--subtitle-language', 'pt-BR', '--voice-language', 'fr'])
        data = play.resolve_graphics(parser, args, '30')
        command = play.build_command(Path('.'), Path('host'), Path('dump'), Path('profile'),
                                     Path('log'), args, '30', data, 'fifo')
        self.assertEqual([flag for flag in command if flag.startswith('--mnk_mode=')], ['--mnk_mode=true'])
        self.assertIn('--keybind_a=J', command)
        self.assertIn('--aster_controller_layout=playstation', command)
        self.assertIn('--aster_ui_language=11', command)
        self.assertIn('--aster_spoken_language=1', command)
        self.assertNotIn('--aster_spoken_language=11', command)

    def test_language_availability_failure_occurs_without_creating_any_runtime(self):
        _, args = play.parse_arguments(['--subtitle-language', 'pt-BR', '--voice-language', 'fr'])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(PortError):
                play.session_preferences_arguments(args, directory)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_malformed_controls_and_unshipped_voice_are_rejected(self):
        for encoded in ('not-json', '[]', '{"schema":7}', 'x' * 16385):
            args = argparse.Namespace(controls_json=encoded, subtitle_language=None, voice_language=None)
            with self.subTest(encoded=encoded[:20]), self.assertRaises(PortError):
                play.session_preferences_arguments(args)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            play.parse_arguments(['--voice-language', 'pt-BR'])


if __name__ == '__main__':
    unittest.main()
