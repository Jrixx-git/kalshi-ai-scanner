"""Offline API-envelope, pacing, and persistent-history regression tests."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import nba_daily_predictions as daily
from test_nba_daily_predictions import game


class FetchTests(unittest.TestCase):
    def test_terminal_variants_including_full_and_empty_pages(self):
        for data in ([], [game()], [game(i) for i in range(1, 101)]):
            for meta in ({'next_cursor': None}, {'per_page': 100},
                         {'per_page': 100, 'next_cursor': None}):
                with self.subTest(n=len(data), meta=meta):
                    fetch = Mock(return_value={'data': data, 'meta': meta})
                    self.assertEqual(daily.fetch_games('key', [], fetch=fetch), data)
                    fetch.assert_called_once()

    def test_malformed_envelopes_and_cursors(self):
        bad = [None, [], {}, {'data': [], 'meta': None}, {'data': [], 'meta': []},
               {'data': [], 'meta': {}}, {'data': {}, 'meta': {'next_cursor': None}}]
        for cursor in (True, False, 0, -1, 1.5, '', 'abc', [], {}):
            bad.append({'data': [game()], 'meta': {'next_cursor': cursor}})
        for size in (0, 101, True, 'bad', None):
            bad.append({'data': [], 'meta': {'per_page': size}})
        bad += [{'data': [game()], 'meta': {'per_page': 100, 'next_page': 2}},
                {'data': [None], 'meta': {'next_cursor': None}},
                {'data': [dict(id=True)], 'meta': {'next_cursor': None}}]
        for payload in bad:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                daily.fetch_games('key', [], fetch=lambda *args: payload, pause=0)

    def test_cursor_and_default_pacing(self):
        fetch = Mock(side_effect=[{'data': [game()], 'meta': {'next_cursor': '100'}},
                                  {'data': [game(2)], 'meta': {'per_page': 100}}])
        with patch.object(daily.time, 'sleep') as sleep:
            self.assertEqual(len(daily.fetch_games('key', [], fetch=fetch)), 2)
        sleep.assert_called_once_with(2)
        self.assertIn(('cursor', '100'), fetch.call_args.args[1])

    def test_repeated_cursor_duplicate_id_and_page_limit(self):
        for pages, limit in (([{'data': [game(i)], 'meta': {'next_cursor': 9}}
                              for i in (1, 2)], 3),
                             ([{'data': [game()], 'meta': {'next_cursor': 9}},
                               {'data': [game()], 'meta': {'next_cursor': None}}], 3),
                             ([{'data': [game()], 'meta': {'next_cursor': 9}}], 1)):
            with self.assertRaises(ValueError):
                daily.fetch_games('key', [], fetch=Mock(side_effect=pages), pause=0,
                                  max_pages=limit)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2022, 11, 3, 12, tzinfo=timezone.utc)
        self.g = game(day='2022-10-25')

    def load(self, directory, fetch, before='2022-11-01', now=None):
        with patch.object(daily.time, 'sleep'):
            return daily.load_history('key', before, directory, fetch=fetch,
                                      now=now or self.now)

    def test_reuse_and_expiration(self):
        with tempfile.TemporaryDirectory() as directory:
            fetch = Mock(return_value={'data': [self.g], 'meta': {'per_page': 100}})
            self.assertEqual(self.load(directory, fetch), [self.g])
            fetch.reset_mock()
            self.assertEqual(self.load(directory, fetch), [self.g])
            fetch.assert_not_called()
            self.load(directory, fetch, now=self.now + timedelta(minutes=6))
            fetch.assert_called_once()

    def test_old_month_ttl_and_future_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            now = self.now + timedelta(days=20)
            fetch = Mock(return_value={'data': [self.g], 'meta': {'next_cursor': None}})
            self.load(directory, fetch, now=now)
            fetch.reset_mock()
            self.load(directory, fetch, now=now + timedelta(hours=23))
            fetch.assert_not_called()
            self.load(directory, fetch, now=now + timedelta(days=7))
            self.assertEqual(fetch.call_count, 1)
            self.load(directory, fetch, now=now)
            self.assertEqual(fetch.call_count, 2)

    def test_corruption_refetch_and_no_stale_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            fetch = Mock(return_value={'data': [self.g], 'meta': {'next_cursor': None}})
            self.load(directory, fetch)
            path = next(Path(directory).glob('*.json'))
            record = json.loads(path.read_text())
            record['games'][0]['home_team_score'] = 999
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(RuntimeError, 'offline'):
                self.load(directory, Mock(side_effect=RuntimeError('offline')))
            self.load(directory, fetch)
            self.assertEqual(fetch.call_count, 2)

    def test_completed_month_survives_later_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            fetch = Mock(side_effect=[{'data': [self.g], 'meta': {'per_page': 100}},
                                      RuntimeError('offline')])
            with self.assertRaises(RuntimeError):
                self.load(directory, fetch, before='2022-11-03')
            self.assertEqual(len(list(Path(directory).glob('*.json'))), 1)
            fetch = Mock(return_value={'data': [], 'meta': {'per_page': 100}})
            self.assertEqual(self.load(directory, fetch, before='2022-11-03'), [self.g])
            fetch.assert_called_once()
            self.assertIn(('start_date', '2022-11-01'), fetch.call_args.args[1])

    def test_invalid_history_never_cached(self):
        for change in ({'date': '2022-11-01'}, {'home_team_score': 0},
                       {'home_team_score': 100}, {'home_team': {'id': 2}}):
            with tempfile.TemporaryDirectory() as directory:
                g = copy.deepcopy(self.g)
                g.update(change)
                fetch = Mock(return_value={'data': [g], 'meta': {'per_page': 100}})
                with self.assertRaises(ValueError):
                    self.load(directory, fetch)
                self.assertEqual(list(Path(directory).glob('*.json')), [])


if __name__ == '__main__':
    unittest.main()
