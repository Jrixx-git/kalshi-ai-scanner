import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from nba_team_development import supervise, run
from nba_team_inventory import inventory
from nba_forward_test import immutable, encode


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = datetime(2026, 11, 12, 0, tzinfo=timezone.utc)
        self.tick = 0
        self.g = dict(id=10, datetime=(self.now+timedelta(hours=1, seconds=10)).isoformat(),
                      home_team={}, date='2026-11-11')
        self.calls = []

    def sleep(self, seconds):
        self.now += timedelta(seconds=seconds)
        self.tick += seconds

    def seal(self, history, game, operational, output):
        self.calls.append(game['id'])
        row = dict(elo=None, features={'x':[None]*7}, sealed_at=self.now.isoformat())
        immutable(Path(output)/'inputs'/(str(game['id'])+'.json'), encode(row))
        return row

    def worker(self, games=None, **kw):
        return supervise(self.root, games or [self.g], self.root, self.root,
                         launched_at=kw.pop('launched_at', self.now),
                         max_wait=kw.pop('max_wait', 60), clock=lambda:self.now,
                         monotonic=lambda:self.tick, sleep=self.sleep, seal=self.seal, **kw)

    def test_waits_and_seals_at_actual_cutoff(self):
        r = self.worker()
        self.assertEqual(self.tick, 10)
        self.assertEqual(r[0]['reason'], 'sealed')
        self.assertEqual(r[0]['sealed_at'], self.now.isoformat())
        self.assertFalse(r[0]['baseline_available'])
        self.assertFalse(r[0]['complete_features'])

    def test_late_start_never_backdates_even_within_tolerance(self):
        self.now += timedelta(seconds=11)
        self.assertEqual(self.worker()[0]['reason'], 'missed_cutoff')
        self.assertEqual(self.calls, [])

    def test_future_horizon_and_independent_omissions_retained(self):
        self.assertEqual(self.worker(max_wait=5)[0]['reason'], 'outside_worker_horizon')
        self.assertEqual(self.worker([{'id':'espn:999'}])[0]['reason'], 'independent_only_or_unknown_identity')
        self.assertEqual(self.calls, [])

    def test_budget_cannot_seal_early_when_wall_clock_moves_back(self):
        def jump(seconds):
            self.tick += 100
            self.now -= timedelta(seconds=60)
        with patch.object(self, 'sleep', side_effect=jump):
            r = self.worker()
        self.assertEqual(r[0]['reason'], 'worker_budget_or_window_expired')
        self.assertEqual(self.calls, [])

    def test_duplicate_seal_is_not_attempted(self):
        self.worker()
        self.assertEqual(self.worker()[0]['reason'], 'already_sealed')
        self.assertEqual(self.calls, [10])

    def test_failed_fresh_schedule_does_not_qualify(self):
        def fail(game):
            raise ValueError('sensitive detail')
        r = self.worker(preflight=fail)
        self.assertEqual(r[0]['reason'], 'fresh_schedule_unverified')
        self.assertNotIn('sensitive', json.dumps(r))
        self.assertEqual(self.calls, [])

    def test_simultaneous_games_sealed_before_any_later_group(self):
        g2 = dict(self.g, id=11)
        self.worker([self.g, g2])
        self.assertEqual(self.calls, [10,11])

    def test_expired_window_makes_no_requests(self):
        with patch('nba_team_development.active', return_value=False), patch('nba_team_development.collect_history') as fetch:
            with self.assertRaises(ValueError):
                run(self.root, self.root)
            fetch.assert_not_called()

    def test_durable_slot_claim_suppresses_rerun_before_requests(self):
        slot = datetime.now(timezone.utc).strftime('%Y%m%dT%H')
        immutable(self.root/'slots'/slot/'claim.json', b'{}')
        with patch('nba_team_development.active', return_value=True), patch('nba_team_development.collect_history') as fetch:
            with self.assertRaises(FileExistsError):
                run(self.root, self.root)
            fetch.assert_not_called()

    def test_inventory_never_counts_unfinished_missing_or_bad_ordering(self):
        with patch('nba_team_inventory.verified_development_rows', return_value=[]):
            r = inventory(self.root, self.root, self.root)
        self.assertEqual((r['eligible_training'], r['eligible_later_validation']), (0,0))
        self.assertFalse(r['ready'])


if __name__ == '__main__':
    unittest.main()
