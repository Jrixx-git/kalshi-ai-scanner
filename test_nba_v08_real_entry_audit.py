"""Reproduce the archived paper fill; settlement outcomes here are fixtures."""
import hashlib
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from decimal import Decimal
from kalshi_orderbook import quote_from_orderbook
from nba_v08_valuation import taker_fee
from paper_engine import PaperEngine

ROOT=Path('paper_v08/state')
SIGNAL='nba-game:21717974'
TICKER='KXNBAGAME-26OCT27PORLAL-POR'

class ArchivedEntryAudit(unittest.TestCase):
    def test_snapshot_depth_fee_and_provenance(self):
        db=sqlite3.connect(ROOT/'ledger.sqlite3')
        row=db.execute('SELECT price,contracts,fee FROM trades WHERE signal_id=?',(SIGNAL,)).fetchone()
        evidence=json.loads(db.execute('SELECT entry_json FROM paper_evidence WHERE signal_id=?',(SIGNAL,)).fetchone()[0]); db.close()
        self.assertEqual(row,('0.5500',1,'0.02'))
        sha=evidence['snapshot_sha256']; raw=(ROOT/'snapshots'/f'{sha}.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),sha)
        book=json.loads(raw)['orderbooks'][TICKER]
        yes=book['raw']['orderbook_fp']['yes_dollars']; best=max(yes,key=lambda x:Decimal(x[0]))
        self.assertEqual(best,['0.4600','34866.04'])
        quote=quote_from_orderbook(TICKER,book['raw'],book['observed_at'])
        self.assertEqual(quote['no_ask'],'0.5400'); self.assertGreaterEqual(quote['no_ask_size'],1)
        self.assertEqual(Decimal(row[0])-Decimal(quote['no_ask']),Decimal('.01'))
        self.assertEqual(evidence['series']['fee_multiplier'],1)
        self.assertEqual(taker_fee(row[0],row[1],1),Decimal(row[2]))
    def test_hypothetical_final_results_are_idempotent(self):
        # These outcomes are invented for testing and do not establish the real result.
        for result, price, expected in [('no','0','0.4300'),('yes','1','-0.5700')]:
            with self.subTest(result=result), tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'ledger.sqlite3'; shutil.copy2(ROOT/'ledger.sqlite3',path)
                engine=PaperEngine(path)
                engine.db.execute("UPDATE trades SET status='OPEN',settled_day=NULL,payout=NULL,pnl=NULL WHERE signal_id=?",(SIGNAL,))
                engine.db.execute('UPDATE paper_evidence SET settlement_json=NULL WHERE signal_id=?',(SIGNAL,))
                market={'ticker':TICKER,'status':'finalized','result':result,'settlement_value_dollars':price,'settlement_ts':'2026-10-28T07:00:00Z'}
                ok,pnl=engine.settle_finalized_market(SIGNAL,market,'2026-10-28T07:01:00Z')
                self.assertTrue(ok); self.assertEqual(Decimal(pnl),Decimal(expected))
                self.assertFalse(engine.settle_finalized_market(SIGNAL,market,'2026-10-28T07:01:00Z')[0])
                self.assertEqual(engine.db.execute('SELECT count(*) FROM trades WHERE signal_id=?',(SIGNAL,)).fetchone()[0],1)
                engine.close()

if __name__=='__main__': unittest.main()
