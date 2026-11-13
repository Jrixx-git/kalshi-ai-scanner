import copy
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import nba_retrospective as r
from nba_v09_challenger import POLICY as STRICT_POLICY


class RetrospectiveTests(unittest.TestCase):
    def game(self, gid, day, hs=100, aw=90):
        return dict(game_id=gid,date=day,home=1,away=2,hs=hs,aw=aw,receipt_sha256='real-receipt')

    def test_target_and_same_date_never_features(self):
        past = [self.game(i, '2026-01-01') for i in range(40)]
        target = self.game(100,'2026-01-02')
        expected = r.vector(past,target)
        self.assertEqual(expected,r.vector(past+[target,self.game(101,'2026-01-02',200,1),
                                                  self.game(102,'2026-01-03',1,200)],target))
        self.assertNotEqual(expected,r.vector([self.game(i,'2026-01-01',1,200) for i in range(40)],target))

    def test_reconstruction_excludes_current_date_and_duplicate(self):
        games = [self.game(i,f'2026-01-{i:02}') for i in range(1,25)]
        rows,_ = r.reconstruct(games,'2026-01-24')
        self.assertTrue(rows)
        self.assertTrue(all(x['feature_max_date'] < x['date'] < '2026-01-24' for x in rows))
        changed = copy.deepcopy(games)
        changed[-2]['hs'] = 1
        other,_ = r.reconstruct(changed,'2026-01-24')
        self.assertEqual(rows[-1]['x'],other[-1]['x'])
        self.assertEqual(rows[-1]['elo'],other[-1]['elo'])
        with self.assertRaises(ValueError):
            r.reconstruct(games+[games[0]],'2026-02-01')

    def test_train_scaling_and_weights_ignore_holdout(self):
        rows = [dict(game_id=i,date='2026-01-01' if i < 500 else '2026-10-20',
                     feature_max_date='2025-12-31',x=[float(i%7)]*7,elo=.6,outcome=i%2)
                for i in range(600)]
        with patch.dict(r.POLICY,iterations=5):
            a = r.fit(rows)
            changed = copy.deepcopy(rows)
            for row in changed[500:]:
                row['x'] = [10000.]*7
                row['outcome'] = 1-row['outcome']
            b = r.fit(changed)
            for k in ('weights','means','scales'):
                self.assertEqual(a[k],b[k])
            self.assertEqual(a,r.fit(rows))
        self.assertEqual(STRICT_POLICY['min_train'],100)
        self.assertEqual(STRICT_POLICY['min_validation'],30)

    def test_gate_and_leakage(self):
        with self.assertRaises(ValueError):
            r.fit([])
        rows = [dict(game_id=i,date='2026-01-01' if i < 500 else '2026-10-20',
                     feature_max_date='2026-10-20',x=[0.]*7,elo=.6,outcome=1) for i in range(600)]
        with self.assertRaisesRegex(ValueError,'leakage'):
            r.fit(rows)

    def test_model_tampering(self):
        with self.assertRaises((ValueError,KeyError)):
            r.verify(dict(model=dict(model_sha256='fabricated'),freeze={}))

    def test_forward_seal_is_reverified_and_backfill_excluded(self):
        now = datetime.now(timezone.utc)
        tip = now+timedelta(minutes=50)
        cutoff = tip-timedelta(hours=1)
        feature = dict(cutoff=cutoff.isoformat(),x=[0.]*7)
        target = dict(id=1,datetime=tip.isoformat(),period=0,status='7:00 pm ET')
        seal = dict(schema='nba-team-input-v1',target=target,features=feature,
                    sealed_at=cutoff.isoformat(),elo=.6,baseline_archive='real-archive',
                    no_trade=True,live_trading=False)
        frozen = dict(model=dict(model_sha256='model'),freeze=dict(
            frozen_at=(cutoff-timedelta(minutes=1)).isoformat()))
        with TemporaryDirectory() as d:
            root = Path(d)
            (root/'inputs').mkdir()
            path = root/'inputs/1.json'
            path.write_bytes(r.encode(seal))
            with patch.object(r,'verify',return_value=frozen['model']), \
                 patch.object(r,'features',return_value=feature), \
                 patch.object(r,'baseline',return_value=(.6,'real-archive')), \
                 patch.object(r,'probability',return_value=.61):
                rows = r.shadow(root,root,root,root/'forward',frozen)
                self.assertEqual(rows['1']['challenger'],.61)
                self.assertLess(r.timestamp(rows['1']['sealed_at']),tip)
                self.assertEqual(rows,r.shadow(root,root,root,root/'forward',frozen))
                seal['elo'] = .7
                path.write_bytes(r.encode(seal))
                with self.assertRaises(ValueError):
                    r.shadow(root,root,root,root/'forward',frozen)
                seal['elo'] = .6
                path.write_bytes(r.encode(seal))
                frozen['freeze']['frozen_at'] = now.isoformat()
                self.assertEqual({},r.shadow(root,root,root,root/'late',frozen))


if __name__ == '__main__':
    unittest.main()
