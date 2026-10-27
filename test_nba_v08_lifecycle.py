import hashlib
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from test_nba_v08_valuation import ValuationTests
from nba_v08_paper import process_snapshot
from paper_engine import PaperEngine

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        sample = ValuationTests(); sample.setUp()
        self.game, self.market, self.now, self.series = sample.game, sample.market, sample.now, sample.series
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = self.root / 'ledger.db'
        self.bundle = {'observed_at': (self.now-timedelta(seconds=10)).isoformat()}
        self.forecasts = {'1': (self.game, 'a'*64, self.bundle)}
    def tearDown(self): self.tmp.cleanup()
    def snapshot(self, market=None, *, old=False):
        stamp = (self.now-timedelta(seconds=40 if old else 5)).isoformat()
        market = market or self.market
        snap = {'schema':'nba-kalshi-capture-v1','started_at':stamp,'completed_at':stamp,
                'series':'KXNBAGAME','live_trading':False,'markets':[market],'errors':{},
                'orderbooks':{market['ticker']:{'observed_at':stamp,'received_at':stamp,'raw':{'orderbook_fp':{'yes_dollars':[['.47','10']], 'no_dollars':[['.50','10']]}}}}}
        data = json.dumps(snap,sort_keys=True).encode()
        path = self.root / (hashlib.sha256(data).hexdigest()+'.json'); path.write_bytes(data)
        return path
    def process(self,path):
        with patch('nba_v08_paper.predictions',return_value=self.forecasts):
            return process_snapshot(path,self.root,self.ledger,self.series,now=self.now)
    def test_entry_settlement_restart_and_idempotency(self):
        path = self.snapshot()
        self.assertEqual(self.process(path)['entries'],1)
        self.assertEqual(self.process(path)['entries'],0)
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
        bad = dict(self.market, occurrence_datetime='2026-10-28T02:30:00Z')
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

if __name__ == '__main__': unittest.main()
