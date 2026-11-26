from pathlib import Path
import tempfile
import unittest

from native_port import session_stats
from native_port.errors import PortError


class SessionStatsTests(unittest.TestCase):
    def test_missing_or_corrupt_history_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(session_stats.load(root), session_stats.defaults())
            path = root / session_stats.STATS_PATH
            path.parent.mkdir(parents=True)
            path.write_text('{not json', encoding='utf8')
            self.assertEqual(session_stats.load(root), session_stats.defaults())

    def test_finish_accumulates_sessions_and_last_played(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = session_stats.finish(root, 1_000, ended_epoch=1_125, fps_target='60')
            self.assertEqual(first['total_seconds'], 125)
            self.assertEqual(first['sessions'], 1)
            self.assertEqual(first['last_duration_seconds'], 125)
            self.assertEqual(first['last_fps_target'], '60')
            self.assertTrue(first['last_played'].startswith('1970-01-01T00:18:45'))
            second = session_stats.finish(root, 2_000, ended_epoch=2_030, fps_target='30')
            self.assertEqual(second['total_seconds'], 155)
            self.assertEqual(second['sessions'], 2)
            self.assertEqual(second['last_duration_seconds'], 30)
            self.assertEqual(session_stats.load(root), second)

    def test_negative_or_invalid_start_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(PortError):
                session_stats.finish(Path(directory), 0)

    def test_display_helpers_are_stable(self):
        self.assertEqual(session_stats.format_total(0), '0min')
        self.assertEqual(session_stats.format_total(59), '0min')
        self.assertEqual(session_stats.format_total(3_661), '1h 01min')
        self.assertEqual(session_stats.format_last(None), 'Nenhuma sessão registrada')
        self.assertEqual(session_stats.format_last('invalid'), 'Data indisponível')


if __name__ == '__main__':
    unittest.main()
