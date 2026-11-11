import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from nba_v09_prospective import collect, game_record, active, START, STOP, market_get
from nba_v08_valuation import timestamp


NOW = timestamp('2026-11-12T01:00:00Z')


class ProspectiveSafetyTests(unittest.TestCase):
    def test_window_and_no_network_after_expiry(self):
        self.assertTrue(active(START))
        self.assertFalse(active(STOP))
        with tempfile.TemporaryDirectory() as d, patch('nba_v09_prospective.fetch_games') as fetch:
            with self.assertRaises(ValueError):
                collect(d, now=STOP)
            fetch.assert_not_called()

    def test_missing_key_keeps_independent_and_injury_evidence(self):
        calls = []
        def schedule(day, root):
            calls.append(day)
            root.mkdir(parents=True, exist_ok=True)
            p = root/(day+'.json')
            p.write_text(json.dumps({'payload': {'events': [{'id':'independent-only'}]}}))
            return p
        def injury(root, **kwargs):
            calls.append('injury')
            return [{'publication_at':'2026-11-11T23:00:00Z', 'status':'raw_available_unparsed'}]
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {}, clear=True):
            r = collect(d, now=NOW, schedule_fetch=schedule, injury_fetch=injury)
            self.assertEqual(calls, ['2026-11-11', '2026-11-12', 'injury'])
            self.assertEqual(len(r['source_errors']), 2)
            self.assertEqual(r['bdl_requests'], 0)
            self.assertEqual(r['injury_raw_reports'], 1)
            self.assertFalse(r['dates'][0]['count_agrees'])
            self.assertEqual(len(list((Path(d)/'runs').glob('*.json'))), 1)
            with self.assertRaises(FileExistsError):
                collect(d, now=NOW, schedule_fetch=schedule, injury_fetch=injury)
            self.assertEqual(len(calls), 3)

    def test_unknown_or_started_game_never_qualifies(self):
        g = dict(id=1, date='2026-11-11', home_team={'id':2,'abbreviation':'BOS'},
                 visitor_team={'id':20,'abbreviation':'NYK'}, datetime='2026-11-12T02:00:00Z',
                 status_state='scheduled', period=0)
        self.assertEqual(game_record(g,NOW)['status'], 'pregame')
        self.assertEqual(game_record(g, timestamp(g['datetime']))['status'], 'not_verified_pregame')
        g['datetime']='invalid'
        self.assertEqual(game_record(g,NOW)['status'], 'unknown_schedule')

    def test_partial_pagination_not_promoted_and_secrets_not_written(self):
        def fetch(key, params):
            return {'data':[{'id':1}], 'meta': {'next_cursor': 2, 'per_page':100}}
        def fail(*args, **kwargs):
            raise OSError('provider error with sensitive text')
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'BALLDONTLIE_API_KEY':'private-test-key'}):
            r = collect(d, now=NOW, bdl_fetch=fetch, schedule_fetch=fail, injury_fetch=fail)
            self.assertLessEqual(r['bdl_requests'],4)
            self.assertFalse((Path(d)/'universe').exists())
            for p in Path(d).rglob('*.json'):
                self.assertNotIn('private-test-key',p.read_text())
                self.assertNotIn('sensitive text',p.read_text())

    def test_write_endpoints_refused(self):
        for path in ['/portfolio/orders', '/events/anything', 'https://evil.example']:
            with self.assertRaises(ValueError):
                market_get(path)


if __name__ == '__main__':
    unittest.main()
