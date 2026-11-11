import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from nba_team_readiness import audit
from nba_team_development import targets
from nba_v09_challenger import collect_history, save


class ReadinessTests(unittest.TestCase):
    def test_empty_archive_does_not_admit_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = audit(tmp, Path(tmp)/'history')
            self.assertFalse(report['eligible'])
            self.assertEqual((report['eligible_training'], report['eligible_later_validation']), (0,0))

    def test_history_wrong_season_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            collect_history(tmp,2025,fetch=lambda _:b'{"data":[{"id":1,"season":2024,"status":"scheduled"}],"meta":{}}')
            with self.assertRaisesRegex(ValueError, 'wrong season'):
                audit(tmp,tmp)

    def test_raw_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            collect_history(tmp,2025,fetch=lambda _:b'{"data":[],"meta":{}}')
            next((Path(tmp)/'raw').iterdir()).write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'integrity'):
                audit(tmp,tmp)

    def test_independent_only_game_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            save(tmp,'universe',dict(pagination_complete=True,games=[dict(id=1)]))
            save(tmp,'runs',dict(independent_games=[dict(status='provider_identity_missing_or_unknown',event_id='9',date='2026-11-11')]))
            self.assertEqual({str(g['id']) for g in targets(tmp)}, {'1','espn:9'})

    def test_incomplete_target_universe_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            save(tmp,'universe',dict(pagination_complete=False,games=[]))
            with self.assertRaisesRegex(ValueError, 'completeness'):
                targets(tmp)

    def test_duplicate_target_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            save(tmp,'universe',dict(pagination_complete=True,games=[dict(id=1),dict(id=1)]))
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                targets(tmp)
