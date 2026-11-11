import copy
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import nba_v09_challenger as c


def game(i=1, day='2026-01-01', hs=110, aw=100):
    return dict(id=i, date=day, datetime=day+'T23:00:00Z', status='Final', period=4,
                home_team={'id':1,'abbreviation':'ATL'}, visitor_team={'id':2,'abbreviation':'BOS'},
                home_team_score=hs, visitor_team_score=aw)


def archive(root, games, received='2026-02-01T00:00:00Z'):
    raw = c.encode(dict(data=games,meta={}))
    digest = hashlib.sha256(raw).hexdigest()
    c.immutable(Path(root)/'raw'/digest,raw)
    p = c.save(root,'receipts',dict(schema='bdl-team-history-v1',
        source='https://api.balldontlie.io/v1/games?seasons[]=2025',
        requested_at=received,received_at=received,raw_sha256=digest))
    c.save(root,'collections',dict(pages=[p.name],complete=True,season=2025))
    return p


def target():
    g = game(900, '2026-02-02')
    g.update(status='scheduled',status_state='scheduled',period=0)
    return g


def fitting_rows():
    out = []
    for i in range(130):
        d = datetime(2025,1,1,tzinfo=timezone.utc)+timedelta(days=i)
        out.append(dict(features=dict(version=c.VERSION, game_id=i, date=d.date().isoformat(),
            cutoff=d.isoformat(), x=[float((i+j)%7) for j in range(7)]),
            tipoff_utc=(d+timedelta(hours=1)).isoformat(),
            outcome_received_at=(d+timedelta(hours=5)).isoformat(),
            elo=.6,outcome=i%2,baseline_verified=True,feature_verified=True))
    return out


class ChallengerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_raw_archive_real_receipts_and_digest(self):
        raw = b'{"data": [], "meta": {"next_cursor": null}}'
        times = iter([datetime(2026,1,1,tzinfo=timezone.utc),datetime(2026,1,1,0,0,1,tzinfo=timezone.utc)])
        result = c.collect_history(self.root,2025,fetch=lambda _:raw,clock=lambda:next(times))
        self.assertTrue(json.loads(result.read_bytes())['complete'])
        receipt = json.loads(next((self.root/'receipts').glob('*')).read_bytes())
        self.assertNotEqual(receipt['requested_at'],receipt['received_at'])
        self.assertEqual((self.root/'raw'/receipt['raw_sha256']).read_bytes(),raw)

    def test_pagination_ceiling_keeps_raw_without_complete(self):
        with self.assertRaisesRegex(ValueError,'ceiling'):
            c.collect_history(self.root,2025,max_pages=1,fetch=lambda _:c.encode(dict(data=[],meta={'next_cursor':2})))
        self.assertEqual(len(list((self.root/'raw').glob('*'))),1)
        self.assertFalse((self.root/'collections').exists())

    def test_repeated_cursor_rejected(self):
        with self.assertRaisesRegex(ValueError,'Repeated'):
            c.collect_history(self.root,2025,fetch=lambda _:c.encode(dict(data=[],meta={'next_cursor':2})))

    def test_late_history_unavailable_at_earlier_cutoff(self):
        archive(self.root,[game()])
        self.assertEqual(c.history(self.root,'2026-01-31T23:00:00Z'),[])
        self.assertEqual(len(c.history(self.root,'2026-02-01T00:00:00Z')),1)

    def test_same_day_and_target_outcome_excluded(self):
        archive(self.root,[game(1,'2026-02-02'),game(900,'2026-01-01')])
        f = c.features(self.root,target(),'2026-02-02T22:00:00Z')
        self.assertEqual(f['home']['n'],0)

    def test_short_history_is_missing_not_zero(self):
        archive(self.root,[game()])
        f = c.features(self.root,target(),'2026-02-02T22:00:00Z')
        self.assertIsNone(f['home']['margin5'])
        self.assertIsNone(f['home']['venue20'])
        self.assertEqual(f['home']['n5'],1)
        self.assertEqual(f['injuries'],'unknown_excluded')

    def test_previous_season_alone_cannot_supply_current_form(self):
        archive(self.root,[game()])
        t = target()
        t.update(date='2026-11-11',datetime='2026-11-11T23:00:00Z')
        f = c.features(self.root,t,'2026-11-11T22:00:00Z')
        self.assertEqual(f['history_coverage'],'missing_current_season_archive')
        self.assertEqual(f['home']['n'],0)

    def test_full_features_rest_b2b_form_venue(self):
        archive(self.root,[game(i+1,(datetime(2026,1,13)+timedelta(days=i)).date().isoformat()) for i in range(20)],'2026-02-02T01:00:00Z')
        f = c.features(self.root,target(),'2026-02-02T22:00:00Z')
        self.assertEqual(f['home']['rest'],1)
        self.assertEqual(f['home']['b2b'],1)
        self.assertEqual(f['home']['margin10'],10)
        self.assertEqual(f['home']['win5'],1)
        self.assertEqual(f['home']['venue20'],1)
        self.assertEqual(f['away']['venue20'],0)
        self.assertEqual(f['x'][2],20)

    def test_rest_capped_and_home_explicit(self):
        archive(self.root,[game()])
        f = c.features(self.root,target(),'2026-02-02T22:00:00Z')
        self.assertEqual(f['home']['rest'],7)
        self.assertEqual((f['home']['home'],f['away']['home']),(1,0))

    def test_identity_mismatch_fails_closed(self):
        g = game()
        g['home_team']['abbreviation']='BOS'
        archive(self.root,[g])
        with self.assertRaisesRegex(ValueError,'identity'):
            c.history(self.root,'2026-02-03T00:00:00Z')

    def test_duplicate_rejected(self):
        archive(self.root,[game(),game()])
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            c.history(self.root,'2026-02-03T00:00:00Z')

    def test_final_score_validation(self):
        for g in (game(hs=100),game(hs=-1),game(hs=110.5)):
            with self.assertRaises(ValueError):
                c.final(g)

    def test_corrections_do_not_replace_first_final(self):
        archive(self.root,[game()])
        archive(self.root,[game(hs=90)],'2026-02-02T00:00:00Z')
        self.assertEqual(c.history(self.root,'2026-02-03T00:00:00Z')[0]['hs'],110)

    def test_raw_tamper_detected(self):
        archive(self.root,[game()])
        next((self.root/'raw').glob('*')).write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'digest'):
            c.history(self.root,'2026-02-03T00:00:00Z')

    def test_deterministic_features_independent_of_page_order(self):
        archive(self.root,[game(2),game(1)])
        first = c.features(self.root,target(),'2026-02-02T22:00:00Z')
        self.assertEqual(c.sha(first),c.sha(c.features(self.root,target(),'2026-02-02T22:00:00Z')))

    def test_post_tip_cutoff_rejected(self):
        with self.assertRaises(ValueError):
            c.features(self.root,target(),'2026-02-02T23:00:00Z')

    def test_immutable_conflict(self):
        c.immutable(self.root/'sealed',b'a')
        with self.assertRaises(ValueError):
            c.immutable(self.root/'sealed',b'b')

    def test_fit_deterministic_frozen_and_validation_not_fitted(self):
        rows = fitting_rows()
        args = dict(freeze_at='2026-01-01T00:00:00Z',validation_start='2025-04-11T00:00:00Z')
        model = c._fit(rows,**args)
        self.assertEqual(model,c._fit(list(reversed(rows)),**args))
        changed = copy.deepcopy(rows)
        for r in changed[100:]:
            r['outcome']=1-r['outcome']
            r['features']['x']=[1000.]*7
        other = c._fit(changed,**args)
        self.assertEqual(model['weights'],other['weights'])
        self.assertEqual(model['means'],other['means'])
        c.verify_model(model)
        model['weights'][0]+=1
        with self.assertRaises(ValueError):
            c.verify_model(model)

    def test_future_outcome_and_duplicate_fit_rejected(self):
        rows = fitting_rows()
        args = dict(freeze_at='2026-01-01T00:00:00Z',validation_start='2025-04-11T00:00:00Z')
        rows[-1]['outcome_received_at']='2026-02-01T00:00:00Z'
        with self.assertRaises(ValueError):
            c._fit(rows,**args)
        rows = fitting_rows()
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            c._fit(rows+[rows[0]],**args)

    def test_fit_insufficient_coverage_is_blocked(self):
        with self.assertRaisesRegex(ValueError,'Insufficient'):
            c.train(self.root,self.root,self.root,self.root,freeze_at='2026-01-01T00:00:00Z',validation_start='2025-04-11T00:00:00Z')
        self.assertFalse((self.root/'models').exists())

    def test_late_training_result_cannot_enter_validation(self):
        rows = fitting_rows()
        rows[0]['outcome_received_at']='2025-04-11T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'validation start'):
            c._fit(rows,freeze_at='2026-01-01T00:00:00Z',validation_start='2025-04-11T00:00:00Z')

    def test_comparison_preserves_independent_only_missingness(self):
        out = c.compare([target()],{},self.root,[],self.root,'2026-02-03T00:00:00Z')
        self.assertEqual(out['denominator'],1)
        self.assertEqual(out['paired_scored'],0)
        self.assertEqual(out['rows'][0]['reasons'],['missing_shadow'])
        self.assertIsNone(out['metrics']['market']['brier'])
        self.assertFalse(out['evaluation_ready'])

    def test_comparison_selects_first_complete_cutoff_quote_not_best_price(self):
        t = target()
        snap1 = dict(started_at='2026-02-02T22:01:00Z',completed_at='2026-02-02T22:01:05Z',p=.7)
        snap2 = dict(started_at='2026-02-02T22:02:00Z',completed_at='2026-02-02T22:02:05Z',p=.2)
        late = dict(started_at='2026-02-02T22:45:00Z',completed_at='2026-02-02T22:45:05Z',p=.9)
        shadow = dict(target=t,sealed_at='2026-02-02T22:00:01Z',elo=.6,challenger=.55,
                      model_sha256='frozen',baseline_archive='archive',reasons=[])
        result = dict(game_id=900,date=t['date'],home=1,away=2,hs=110,aw=100,received_at='2026-02-03T03:00:00Z')
        def evidence(path):
            return [('z',snap2),('a',snap1),('x',late)] if path.name == 'snapshots' else [('schedule',{})]
        with patch('nba_forward_test.predictions',return_value={'900':({},'archive',{})}), patch('nba_v09_research.evidence',side_effect=evidence), patch('nba_v09_research.paired',side_effect=lambda g,b,s,sc:dict(market=s['p'])), patch.object(c,'history',return_value=[result]):
            out = c.compare([t],{'900':shadow},self.root,[self.root],self.root,'2026-02-03T04:00:00Z')
        self.assertEqual(out['rows'][0]['market'],.7)
        self.assertEqual(out['paired_scored'],1)
        self.assertAlmostEqual(out['metrics']['challenger']['brier'],.45**2)

    def test_partial_collection_pages_never_form_history(self):
        c.collect_history(self.root,2025,fetch=lambda _:c.encode(dict(data=[game()],meta={})))
        next((self.root/'collections').glob('*')).unlink()
        self.assertEqual(c.history(self.root,'2026-12-01T00:00:00Z'),[])

    def test_missing_baseline_is_explicit(self):
        self.assertEqual(c.baseline(self.root,target(),'2026-02-02T22:00:00Z'),(None,None))

    def test_seal_refuses_late_input_and_preserves_no_forecast(self):
        clock = lambda: datetime(2026,2,2,22,5,tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError,'window'):
            c.seal_input(self.root,target(),self.root,self.root,clock=clock)
        self.assertFalse((self.root/'inputs').exists())

    def test_cutoff_runner_does_not_capture_when_deadline_missed(self):
        with patch('nba_v09_prospective.market_get') as fetch:
            c.run_cutoffs(self.root,[target()],self.root,self.root,max_wait=0)
        fetch.assert_not_called()
        self.assertEqual(len(list((self.root/'coverage').glob('*'))),1)

    def test_evaluation_inputs_never_enter_training(self):
        c.immutable(self.root/'inputs'/'900.json',c.encode(dict(purpose='evaluation')))
        with self.assertRaisesRegex(ValueError,'Insufficient'):
            c.train(self.root,self.root,self.root,self.root,freeze_at='2026-01-01T00:00:00Z',validation_start='2025-04-11T00:00:00Z')

    def test_provider_cannot_echo_key_into_archive(self):
        with patch.dict('os.environ',{'BALLDONTLIE_API_KEY':'private-test-secret'}):
            with self.assertRaisesRegex(ValueError,'Credential echo'):
                c.collect_history(self.root,2025,fetch=lambda _:b'private-test-secret')
        self.assertFalse((self.root/'raw').exists())

    def test_input_seal_is_actual_time_and_missing_elo_is_retained(self):
        now = datetime(2026,2,2,22,tzinfo=timezone.utc)
        row = c.seal_input(self.root,target(),self.root,self.root,clock=lambda:now)
        self.assertEqual(row['sealed_at'],now.isoformat())
        self.assertIsNone(row['elo'])
        self.assertTrue(row['no_trade'])
        self.assertEqual(json.loads((self.root/'inputs'/'900.json').read_bytes()),row)

    def test_shadow_abstains_without_history_and_is_immutable(self):
        model = c._fit(fitting_rows(),freeze_at='2026-01-01T00:00:00Z',validation_start='2025-04-11T00:00:00Z')
        now = datetime(2026,2,2,22,tzinfo=timezone.utc)
        with patch.object(c,'datetime') as dt:
            dt.now.return_value=now
            row = c.shadow(self.root,target(),now.isoformat(),model,self.root,self.root)
        self.assertIsNone(row['challenger'])
        self.assertIn('insufficient_team_history',row['reasons'])
        self.assertIn('missing_verified_operational_elo',row['reasons'])
        self.assertFalse(row['live_trading'])


if __name__ == '__main__':
    unittest.main()
