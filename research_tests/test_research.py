import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research_lab.core import asof,seal,read_sealed,number
from research_lab.demo import fixture
from research_lab.runner import run
from research_lab.evaluation import scores,compare
from research_lab.models import monthly_changes
from research_lab.normalization import member_maxima,official_tmax,player_features
from research_lab.providers import Alfred,AlfredCSV,SportsDataIO,alfred_values,get_json


class ResearchTests(unittest.TestCase):
    def test_hash_tampering(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd(), prefix='research-test-') as root:
            digest=seal(root,{'x':1});self.assertEqual(digest,seal(root,{'x':1}))
            (Path(root)/(digest+'.json')).write_text('{}')
            with self.assertRaisesRegex(ValueError,'hash_mismatch'):read_sealed(root,digest)

    def test_naive_and_future_availability(self):
        r=fixture('sports',1)['events'][0]['inputs']['legacy']
        for stamp in ('2025-01-02T00:00:00Z','2024-12-31T20:00:00'):
            r['available_at']=stamp
            with self.assertRaises(ValueError):asof(r,'2025-01-01T00:00:00Z',synthetic=True)

    def test_reanalysis_and_scrambled_rejected(self):
        for flag in ('reanalysis','scrambled'):
            d=fixture('weather',1);d['events'][0]['inputs']['ensemble'][flag]=True
            self.assertEqual(run(d)['accepted_events'],0)

    def test_synthetic_cannot_masquerade_as_real(self):
        d=fixture('sports',25);d['synthetic']=False
        self.assertEqual(run(d)['accepted_events'],0)

    def test_future_labels_do_not_change_earlier_predictions(self):
        d=fixture('sports',28);before=run(d)
        d['events'][-1]['outcome']['value']=1-d['events'][-1]['outcome']['value']
        after=run(d)
        self.assertEqual([r['predictions'] for r in before['forecasts']], [r['predictions'] for r in after['forecasts']])

    def test_delayed_labels_excluded_from_training(self):
        d=fixture('sports',30)
        for r in d['events'][:20]:r['outcome_available_at']='2030-01-01T00:00:00Z'
        self.assertEqual(run(d)['n'],0)

    def test_duplicate_event_fails(self):
        d=fixture('sports',2);d['events'][1]['event_id']='0'
        with self.assertRaisesRegex(ValueError,'duplicate'):run(d)

    def test_game_and_weather_identity(self):
        d=fixture('sports',1);d['events'][0]['inputs']['challenger']['canonical_game_id']='wrong'
        self.assertEqual(run(d)['accepted_events'],0)
        d=fixture('weather',1);d['events'][0]['outcome']['station']='wrong'
        self.assertEqual(run(d)['accepted_events'],0)

    def test_all_prototypes_run(self):
        for family in ('sports','weather','finance'):
            r=run(fixture(family,25))
            self.assertGreater(r['n'],0);self.assertEqual(r['rejections'],[])
            self.assertFalse(r['superiority_claim'])

    def test_proper_scores(self):
        r=scores([.25,.75],[0,1]);self.assertAlmostEqual(r['brier'],.0625)
        self.assertAlmostEqual(r['log_loss'],.28768207245)
        with self.assertRaises(ValueError):scores([float('nan')],[1])
        with self.assertRaises(ValueError):number(True)

    def test_few_clusters_suppress_interval(self):
        rows=[{'cluster':'same','y':1,'predictions':{'a':.5,'b':.6}}]*100
        self.assertIsNone(compare(rows,'a','b')['cluster_bootstrap_95_interval'])

    def test_empty_is_not_zero_loss(self):
        self.assertEqual(compare([],'a','b')['status'],'no_valid_comparisons')

    def test_finance_future_and_gaps_rejected(self):
        values=[{'date':f'2025-0{i}-01','value':100+i} for i in (1,2,3,4)]
        self.assertEqual(len(monthly_changes(values,'2025-05-01')),3)
        with self.assertRaises(ValueError):monthly_changes(values,'2025-04-01')
        with self.assertRaises(ValueError):monthly_changes(values,'2025-06-01')

    def test_alfred_wrong_vintage_rejected(self):
        p={'observations':[{'date':'2024-01-01','value':'100','realtime_start':'2025-01-02','realtime_end':'9999-12-31'}]}
        with self.assertRaisesRegex(ValueError,'wrong_vintage'):alfred_values(p,'2025-01-01')

    def test_alfred_requests_previous_day(self):
        payload={'count':0,'observations':[],'realtime_start':'2025-01-01','realtime_end':'2025-01-01'}
        with patch('research_lab.providers.key',return_value='secret'),patch('research_lab.providers.get_json',return_value=(payload,'0'*64,{'received_at':'2025-01-03T00:00:00Z'})) as get:
            Alfred().request(series_id='CPIAUCSL',cutoff='2025-01-02T12:00:00Z',evidence_root='unused')
            self.assertEqual(get.call_args.args[1]['realtime_end'],'2025-01-01')

    def test_sportsdata_endpoint(self):
        with patch('research_lab.providers.key',return_value='secret'),patch('research_lab.providers.get_json') as get:
            SportsDataIO().request(resource='StartingLineupsByDate',game_date='2025-01-01',evidence_root='unused')
            self.assertIn('/projections/json/StartingLineupsByDate/',get.call_args.args[0])

    def test_csv_latest_fallback_rejected(self):
        with patch('research_lab.providers.get_json',return_value=('observation_date,CPIAUCSL_20260101\n2024-01-01,100\n','0'*64,{'received_at':'2026-01-02T00:00:00Z'})):
            with self.assertRaisesRegex(ValueError,'header_mismatch'):
                AlfredCSV().request(series_id='CPIAUCSL',cutoff='2025-01-02T00:00:00Z',evidence_root='unused')

    def test_macro_outcome_identity(self):
        d=fixture('finance',1);d['events'][0]['outcome']['target_period']='1900-01-01'
        self.assertEqual(run(d)['accepted_events'],0)

    def test_actual_provenance_requires_evidence(self):
        d=fixture('sports',1);r=d['events'][0]['inputs']['legacy'];r['availability_basis']='captured'
        with self.assertRaisesRegex(ValueError,'evidence_root_required'):asof(r,d['events'][0]['decision_at'])

    def test_no_operational_imports_or_order_requests(self):
        import ast
        for path in Path('research_lab').glob('*.py'):
            tree=ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):
                    self.assertFalse(any(n.name.startswith(('nba_','paper_','risk_engine')) for n in node.names))
                if isinstance(node,ast.ImportFrom):
                    self.assertFalse((node.module or '').startswith(('nba_','paper_','risk_engine')))

    def test_unapproved_endpoint_rejected(self):
        for url in ('http://api.stlouisfed.org/x','https://evil.example/x','https://api.stlouisfed.org:123/x'):
            with self.assertRaises(ValueError):get_json(url,{},'unused')

    def test_hourly_aggregation_requires_complete_day(self):
        hourly={'time':['2025-01-01T00:00:00Z','2025-01-01T01:00:00Z'],'member':[10,20]}
        self.assertEqual(member_maxima(hourly,'2025-01-01T00:00:00Z','2025-01-01T02:00:00Z',['member']),[20])
        with self.assertRaisesRegex(ValueError,'incomplete'):member_maxima(hourly,'2025-01-01T00:00:00Z','2025-01-01T03:00:00Z',['member'])

    def test_official_quality_flag(self):
        r={'STATION':'X','DATE':'2025-01-01','TMAX':'21.1','TMAX_ATTRIBUTES':',X,1'}
        with self.assertRaises(ValueError):official_tmax([r],'X','2025-01-01')

    def test_realized_minutes_cannot_be_features(self):
        with self.assertRaises(ValueError):player_features([{'canonical_player_id':'1','canonical_game_id':'g','side':'home','minutes_kind':'realized'}],'g')

if __name__=='__main__':unittest.main()
