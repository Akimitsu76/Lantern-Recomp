from pathlib import Path
import tempfile
import unittest

from native_port import languages
from native_port.errors import PortError


class LanguageSettingsTests(unittest.TestCase):
    def test_original_text_and_voice_are_separate_engine_selections(self):
        args = languages.cvar_arguments({'subtitle_language': 'pt-BR', 'voice_language': 'en'})
        self.assertEqual(args, ['--aster_ui_language=11', '--aster_spoken_language=0'])
        self.assertNotIn('--user_language=11', args)

    def test_change_voice_does_not_replace_text_selection(self):
        self.assertEqual(languages.cvar_arguments({'subtitle_language': 'pt-BR', 'voice_language': 'fr'}),
                         ['--aster_ui_language=11', '--aster_spoken_language=1'])

    def test_native_defaults_do_not_add_override_flags(self):
        self.assertEqual(languages.cvar_arguments({'subtitle_language': 'auto', 'voice_language': 'auto'}), [])

    def test_portuguese_is_not_offered_as_an_unshipped_voice(self):
        self.assertIn('pt-BR', languages.TEXT_LANGUAGES)
        self.assertNotIn('pt-BR', languages.VOICE_LANGUAGES)
        with self.assertRaises(PortError):
            languages.validate({'voice_language': 'pt-BR'})

    def test_settings_are_strict_and_defaults_are_independent(self):
        for value in (None, [], {'subtitle_language': 11}, {'voice_language': True},
                      {'subtitle_language': 'not-a-language'}, {'arbitrary': 'value'}):
            with self.subTest(value=value), self.assertRaises(PortError):
                languages.validate(value)
        one = languages.defaults()
        one['voice_language'] = 'de'
        self.assertEqual(languages.defaults()['voice_language'], 'en')

    def test_inventory_requires_real_edition_and_selected_voice_bank(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('gl/common/sku_x360.bin_be', 'gl/x360/levels/gui.lvl_760',
                         'gl/x360/sound/fmod/dialog_en.fsb'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(languages.EUROPE_SKU if name.endswith('bin_be') else b'fixture')
            original = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            available = languages.availability(root)
            self.assertTrue(available['reviewed_europe_sku'])
            self.assertIn('pt-BR', available['text'])
            self.assertEqual(available['voice'], ('auto', 'en'))
            self.assertEqual(languages.require_available(languages.defaults(), root), languages.defaults())
            with self.assertRaises(PortError):
                languages.require_available({'voice_language': 'fr'}, root)
            self.assertEqual(original, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_unknown_or_missing_edition_does_not_guess_portuguese_support(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(languages.availability(directory)['text'], ('auto',))
            with self.assertRaises(PortError):
                languages.require_available(languages.defaults(), directory)
            self.assertEqual(languages.cvar_arguments(
                {'subtitle_language': 'auto', 'voice_language': 'auto'}, directory), [])


if __name__ == '__main__':
    unittest.main()
