import hashlib
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from test_nba_v08_valuation import ValuationTests
from nba_v08_paper import process_snapshot, save_report
from paper_engine import PaperEngine

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        sample = ValuationTests(); sample.setUp()
        self.game, self.market, self.now, self.series = sample.game, sample.market, sample.now, sample.series
        self.game.update(home_team_id='2', away_team_id='3')
        self.game['generated_at_utc']=(self.now-timedelta(minutes=1)).isoformat()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = self.root / 'ledger.db'
        self.bundle = {'observed_at': (self.now-timedelta(seconds=10)).isoformat()}
        self.forecasts = {'1': (self.game, 'a'*64, self.bundle)}
        stamp=(self.now-timedelta(seconds=7)).isoformat()
        self.schedule={'schema':'espn-nba-schedule-v1','requested_date':'2026-10-27','requested_at':stamp,'received_at':stamp,
          'source':'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20261027',
          'payload':{'events':[{'id':'401909877','date':'2026-10-27T23:30:00Z','status':{'type':{'state':'pre','completed':False,'name':'STATUS_SCHEDULED'}},'competitions':[{'id':'401909877','competitors':[{'homeAway':'home','team':{'id':'2','abbreviation':'BOS'}},{'homeAway':'away','team':{'id':'17','abbreviation':'BKN'}}]}]}]}}
        data=json.dumps(self.schedule,sort_keys=True).encode(); self.schedule_path=self.root/(hashlib.sha256(data).hexdigest()+'.json'); self.schedule_path.write_bytes(data)
    def tearDown(self): self.tmp.cleanup()
    def snapshot(self, market=None, *, old=False):
        stamp = (self.now-timedelta(seconds=40 if old else 5)).isoformat()
        market = market or self.market
        away = dict(self.market, ticker='KXNBAGAME-26OCT27BKNBOS-BKN', title='Brooklyn wins', yes_sub_title='Brooklyn', rules_primary='If Brooklyn wins the Brooklyn vs Boston Pro Basketball game originally scheduled for Oct 27, 2026, then the market resolves to Yes.')
        snap = {'schema':'nba-kalshi-capture-v1','started_at':stamp,'completed_at':stamp,
                'series':'KXNBAGAME','live_trading':False,'markets':[market,away],'errors':{},
                'orderbooks':{m['ticker']:{'observed_at':stamp,'received_at':stamp,'raw':{'orderbook_fp':{'yes_dollars':[['.47','10']], 'no_dollars':[['.50','10']]}}} for m in [market,away]}}
        data = json.dumps(snap,sort_keys=True).encode()
        path = self.root / (hashlib.sha256(data).hexdigest()+'.json'); path.write_bytes(data)
        return path
    def process(self,path):
        with patch('nba_v08_paper.predictions',return_value=self.forecasts):
            return process_snapshot(path,self.root,self.ledger,self.series,schedule_paths={'2026-10-27':self.schedule_path},now=self.now)
    def test_entry_settlement_restart_and_idempotency(self):
        path = self.snapshot()
        first=self.process(path)
        self.assertEqual(first['entries'],1)
        reasons=[side['reason'] for assessment in first['decisions'][0]['assessments'] for side in assessment['sides']]
        self.assertIn('paper_entry',reasons)
        self.assertIn('not_selected_lower_or_tied_edge',reasons)
        repeated=self.process(path)
        self.assertEqual(repeated['entries'],0)
        self.assertEqual(repeated['decisions'][0]['reason'],'Duplicate signal')
        engine = PaperEngine(self.ledger)
        self.assertEqual(str(engine.account('2026-10-27').open_exposure),'0.53')
        final = {'ticker':self.market['ticker'],'status':'finalized','result':'yes','settlement_value_dollars':'1.00','settlement_ts':'2026-10-28T03:00:00Z'}
        self.assertFalse(engine.settle_finalized_market('nba-game:1',final,'2026-10-28T02:00:00Z')[0])
        self.assertTrue(engine.settle_finalized_market('nba-game:1',final,'2026-10-28T03:01:00Z')[0])
        self.assertFalse(engine.settle_finalized_market('nba-game:1',final,'2026-10-28T03:01:00Z')[0])
        self.assertEqual(str(engine.account('2026-10-28').cash),'5000.47')
        evidence = engine.db.execute('SELECT entry_json,settlement_json FROM paper_evidence').fetchone()
        self.assertTrue(all(evidence)); engine.close()
        self.assertEqual(self.process(path)['entries'],0)
    def test_ambiguous_time_and_stale_snapshot_rejected(self):
        bad = dict(self.market, ticker='KXNBAGAME-26OCT27BKNBOS-WRONG')
        self.assertEqual(self.process(self.snapshot(bad))['entries'],0)
        self.assertEqual(self.process(self.snapshot(old=True))['entries'],0)
    def test_scalar_fair_value_settlement(self):
        self.process(self.snapshot())
        engine = PaperEngine(self.ledger)
        final = {'ticker':self.market['ticker'],'status':'finalized','result':'scalar','settlement_value_dollars':'.45','settlement_ts':'2026-10-28T03:00:00Z'}
        self.assertTrue(engine.settle_finalized_market('nba-game:1',final,'2026-10-28T03:01:00Z')[0])
        self.assertEqual(str(engine.account('2026-10-28').cash),'4999.92')
        engine.close()
    def test_settlement_rejects_wrong_ticker_and_contradiction(self):
        self.process(self.snapshot())
        engine = PaperEngine(self.ledger)
        final = {'ticker':self.market['ticker'],'status':'finalized','result':'yes','settlement_value_dollars':'0.00','settlement_ts':'2026-10-28T03:00:00Z'}
        self.assertFalse(engine.settle_finalized_market('nba-game:1', final,'2026-10-28T03:01:00Z')[0])
        final.update(ticker='KXNBAGAME-OTHER', settlement_value_dollars='1.00')
        self.assertFalse(engine.settle_finalized_market('nba-game:1', final,'2026-10-28T03:01:00Z')[0])
        self.assertEqual(str(engine.account().open_exposure),'0.53')
        engine.close()
    def test_snapshot_tampering_rejected(self):
        path=self.snapshot(); path.write_text('{}')
        with self.assertRaises(ValueError): self.process(path)
    def test_duplicate_contracts_rejected(self):
        path=self.snapshot(); data=json.loads(path.read_text())
        data['markets'].append(dict(data['markets'][0]))
        raw=json.dumps(data,sort_keys=True).encode(); path=self.root/(hashlib.sha256(raw).hexdigest()+'.json'); path.write_bytes(raw)
        result=self.process(path)
        self.assertEqual(result['entries'],0)
        self.assertIn('ambiguous', result['decisions'][0]['detail'])
    def test_duplicate_forecast_game_rejected(self):
        self.forecasts['2']=(dict(self.game), 'b'*64, self.bundle)
        result=self.process(self.snapshot())
        self.assertEqual(result['entries'],0)
        self.assertEqual([d['reason'] for d in result['decisions']],['duplicate_forecast_identity']*2)
    def test_stale_forecast_rejected(self):
        self.game['generated_at_utc']=(self.now-timedelta(hours=25)).isoformat()
        result=self.process(self.snapshot())
        self.assertEqual(result['entries'],0)
        self.assertEqual(result['decisions'][0]['reason'],'stale_or_invalid_forecast')
    def test_reports_preserve_previous_decisions(self):
        previous=b'{"legacy":true}\n'
        (self.root/'latest.json').write_bytes(previous)
        save_report(self.root, {'decisions':[{'game_id':'1','reason':'edge_below_threshold'}]})
        first=(self.root/'latest.json').read_bytes()
        save_report(self.root, {'decisions':[{'game_id':'2','reason':'no_executable_ask'}]})
        second=(self.root/'latest.json').read_bytes()
        for data in (previous,first,second):
            self.assertEqual((self.root/'reports'/(hashlib.sha256(data).hexdigest()+'.json')).read_bytes(),data)

if __name__ == '__main__': unittest.main()
