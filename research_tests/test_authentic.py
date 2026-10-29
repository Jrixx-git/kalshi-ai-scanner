"""Adversarial point-in-time tests. Fabricated envelopes are test fixtures only."""
import copy
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
from research_lab.core import seal, instant
from research_lab.authentic import (captured, complete_pages, nba_features, nba_challenger,
    contract_window, weather_members, weather_settlement, first_release, market_probability)
from research_lab.survey import classify
from research_lab.providers import get_json


class AuthenticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd(), prefix='authentic-test-')
        self.root = Path(self.temp.name)
        self.game = dict(game_id='99', date='2026-10-29', tipoff_utc='2026-10-30T00:00:00Z', home_team_id='1', away_team_id='6')
        self.cutoff = '2026-10-29T18:00:00Z'

    def tearDown(self): self.temp.cleanup()

    def envelope(self, endpoint, payload, params=None, received='2026-10-29T17:00:00Z'):
        return seal(self.root, dict(endpoint=endpoint, parameters=params or {}, method='GET', status=200,
            requested_at=received, received_at=received, raw_utf8=json.dumps(payload)))

    def sources(self, modify=None, empty_injuries=True):
        rows=[]; basics=[]
        for team in (1,6):
            for i in range(5):
                r=dict(id=team*10+i, team={'id':team}, player={'id':team*10+i}, period=0,
                    pie=.1 if team==1 else .08, game={'id':11+team, 'date':'2026-10-28', 'status':'Final'})
                rows.append(r)
                basics.append(dict(id=r['id'], team=r['team'], player=r['player'], game=r['game'], min='48:00'))
        if modify: modify(rows, basics)
        params=dict(start_date='2026-10-14', end_date='2026-10-28')
        a=self.envelope('https://api.balldontlie.io/nba/v2/stats/advanced',
            {'data':rows,'meta':{'per_page':100}}, {**params,'period':0})
        b=self.envelope('https://api.balldontlie.io/v1/stats', {'data':basics,'meta':{'per_page':100}}, params)
        inj=[] if empty_injuries else [{'player':{'id':777,'team_id':1},'status':'Out'}]
        c=self.envelope('https://api.balldontlie.io/v1/player_injuries', {'data':inj,'meta':{'per_page':100}}, {'team_ids[]':[1,6]})
        return [a],[b],[c]

    def test_bound_features_derive_values_and_empty_injuries_are_not_missing(self):
        a,b,c=self.sources(empty_injuries=False)
        f=nba_features(self.root,a,b,c,self.game,self.cutoff)
        self.assertAlmostEqual(f['features'][0],.02); self.assertEqual(f['features'][1:], [1,0])
        with self.assertRaisesRegex(ValueError,'missing'): nba_features(self.root,a,b,[],self.game,self.cutoff)

    def test_future_capture_cannot_be_backdated_by_importer(self):
        d=self.envelope('https://api.balldontlie.io/v1/games',{'data':[]},received='2026-10-29T19:00:00Z')
        with self.assertRaisesRegex(ValueError,'after_decision'):
            captured(self.root,d,self.cutoff,'https://api.balldontlie.io/v1/games')

    def test_tampered_raw_is_rejected(self):
        a,b,c=self.sources(); (self.root/(a[0]+'.json')).write_text('{}')
        with self.assertRaisesRegex(ValueError,'hash_mismatch'): nba_features(self.root,a,b,c,self.game,self.cutoff)

    def test_target_game_stats_cannot_be_features(self):
        def mutate(a,b): a[0]['game']['id']=99
        a,b,c=self.sources(mutate)
        with self.assertRaisesRegex(ValueError,'current_future'): nba_features(self.root,a,b,c,self.game,self.cutoff)

    def test_nonfinal_history_is_rejected(self):
        def mutate(a,b): a[0]['game']['status']='Scheduled'
        a,b,c=self.sources(mutate)
        with self.assertRaisesRegex(ValueError,'nonfinal'): nba_features(self.root,a,b,c,self.game,self.cutoff)

    def test_incomplete_minutes_and_duplicate_player_are_rejected(self):
        for mutation in (lambda a,b:b.pop(), lambda a,b:a.append(dict(a[0],id=999))):
            a,b,c=self.sources(mutation)
            with self.assertRaises((KeyError,ValueError)): nba_features(self.root,a,b,c,self.game,self.cutoff)

    def test_cursor_truncation_never_means_complete(self):
        url='https://api.balldontlie.io/v1/stats'
        d=self.envelope(url, {'data':[{'id':1}], 'meta':{'per_page':1,'next_cursor':2}})
        with self.assertRaisesRegex(ValueError,'incomplete'): complete_pages(self.root,[d],self.cutoff,url,{})

    def test_labels_unavailable_at_decision_do_not_train_challenger(self):
        current={'decision_at':self.cutoff,'features':[.1,1,0],'specification':'lagged-pie-injury-v1'}
        rows=[dict(features=[.1,0,0],baseline=.55,y=1,outcome_available_at=self.cutoff,specification=current['specification'])]*25
        with self.assertRaisesRegex(ValueError,'insufficient'): nba_challenger(rows,current,.55)

    def test_dst_contract_windows_and_fixed_standard_day(self):
        a,b=contract_window('2026-11-01','America/New_York')
        self.assertEqual(instant(b)-instant(a),timedelta(hours=25))
        a,b=contract_window('2026-11-01','America/New_York',fixed_standard_offset=-5)
        self.assertEqual(instant(b)-instant(a),timedelta(hours=24))

    def test_members_bound_to_complete_trajectories(self):
        payload={'utc_offset_seconds':0, 'hourly_units':{'temperature_2m':'\u00b0C','temperature_2m_member01':'\u00b0C'},
          'hourly':{'time':['2026-10-30T00:00','2026-10-30T01:00'],'temperature_2m':[10,12],'temperature_2m_member01':[11,13]}}
        d=self.envelope('https://ensemble-api.open-meteo.com/v1/ensemble',payload,{'timezone':'UTC'})
        result=weather_members(self.root,d,self.cutoff,'2026-10-30T00:00Z','2026-10-30T02:00Z')
        self.assertEqual(result['member_maxima_C'],[12,13]);self.assertFalse(result['run_identity_verified'])
        with self.assertRaisesRegex(ValueError,'incomplete'): weather_members(self.root,d,self.cutoff,'2026-10-30T00:00Z','2026-10-30T03:00Z')

    def test_settlement_requires_explicit_rules_and_rounding(self):
        with self.assertRaisesRegex(ValueError,'unreviewed'): weather_settlement(20,{})
        spec=dict(ticker='TEST',station='KNYC',day='2026-10-30',source='NWS',source_product='CLI',
          window_start='2026-10-30T05:00Z',window_end='2026-10-31T05:00Z',rules_sha256='a'*64,
          unit='F',rounding='nearest_integer_half_up',operator='>=',threshold=68,reviewed=True)
        self.assertEqual(weather_settlement(20,spec),1)
        spec['operator']='>';self.assertEqual(weather_settlement(20,spec),0)

    def test_first_release_rejects_revised_levels(self):
        payload={'count':1,'observations':[{'date':'2026-09-01','value':'0.2','realtime_start':'2026-10-14'}], 'output_type':4,'units':'pch'}
        params={'series_id':'CPIAUCSL','output_type':4,'units':'pch'}
        url='https://api.stlouisfed.org/fred/series/observations'
        d=self.envelope(url,payload,params)
        r=first_release(self.root,d,'2026-09-01');self.assertEqual(r['value'],.2)
        self.assertEqual(r['outcome_available_at'],'2026-10-15T00:00:00Z')
        for key,value in (('output_type',1),('units','lin')):
            wrong={**params,key:value};d=self.envelope(url,payload,wrong)
            with self.assertRaisesRegex(ValueError,'initial_release'): first_release(self.root,d,'2026-09-01')

    def test_first_release_missing_panel_never_scores_zero(self):
        d=self.envelope('https://api.stlouisfed.org/fred/series/observations',
            {'count':2,'observations':[], 'output_type':4,'units':'pch'}, {'series_id':'CPIAUCSL','output_type':4,'units':'pch'})
        with self.assertRaisesRegex(ValueError,'incomplete'):first_release(self.root,d,'2026-09-01')

    def test_market_midpoint_is_not_ask_or_wrong_side(self):
        self.assertAlmostEqual(market_probability(.4,.5),.45)
        with self.assertRaises(ValueError):market_probability(.8,.5)

    def test_access_classification_never_inferrs_paid_tier(self):
        self.assertEqual(classify(200,{'data':[]}), 'accessible_empty_sample')
        self.assertIn('unknown',classify(429));self.assertIn('or_not_entitled',classify(401))

    def test_credential_echo_is_not_written_to_evidence(self):
        response=MagicMock();response.__enter__.return_value=response;response.status=200
        response.read.return_value=b'{"echo":"sensitive-test-key"}'
        opener=MagicMock();opener.open.return_value=response
        with patch('research_lab.providers.urllib.request.build_opener',return_value=opener):
            with self.assertRaises(RuntimeError):get_json('https://api.stlouisfed.org/test',{'api_key':'sensitive-test-key'},self.root)
        files=list(self.root.glob('*.json'));self.assertEqual(len(files),1)
        self.assertNotIn('sensitive-test-key',files[0].read_text())


if __name__=='__main__':unittest.main()
