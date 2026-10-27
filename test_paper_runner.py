import csv
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from paper_runner import run, load_probabilities
from paper_engine import PaperEngine

class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.est = self.root/'estimates.csv'
        self.est.write_text('ticker,estimated_yes_probability\nNBA-TEST,0.80\n', encoding='utf-8')
        self.fees = self.root/'fees.json'
        self.fees.write_text(json.dumps({'NBA-TEST':'0.01'}), encoding='utf-8')
        self.ledger = self.root/'ledger.sqlite3'
        self.markets = lambda pages: [{'ticker':'NBA-TEST','category':'sports'}]
    def tearDown(self): self.temp.cleanup()
    def quote(self, ticker, *, age=0):
        return {'ticker':ticker,'yes_ask':'0.50','yes_ask_size':20,
                'observed_at':(datetime.now(timezone.utc)-timedelta(seconds=age)).isoformat()}
    def execute(self, quote_fn=None):
        return run(pages=1,estimates_file=self.est,fees_file=self.fees,ledger=self.ledger,
                   scan_fn=self.markets,quote_fn=quote_fn or self.quote)
    def test_enters_one_paper_trade(self):
        self.assertEqual(self.execute()['paper_entries'],1)
        db=PaperEngine(self.ledger)
        self.assertEqual(len(db._open()) if hasattr(db,'_open') else db.db.execute("SELECT count(*) FROM trades").fetchone()[0],1)
        db.close()
    def test_repeated_run_no_duplicate_position(self):
        self.execute()
        self.assertEqual(self.execute()['paper_entries'],0)
    def test_stale_quote_rejected(self):
        self.assertEqual(self.execute(lambda t:self.quote(t,age=120))['paper_entries'],0)
    def test_missing_fee_rejected(self):
        self.fees.write_text('{}',encoding='utf-8')
        self.assertEqual(self.execute()['paper_entries'],0)
    def test_missing_probability_rejected(self):
        self.est.write_text('ticker,estimated_yes_probability\n',encoding='utf-8')
        self.assertEqual(self.execute()['considered'],0)
    def test_non_sports_ignored(self):
        self.markets=lambda pages:[{'ticker':'NBA-TEST','category':'crypto'}]
        self.assertEqual(self.execute()['considered'],0)
    def test_invalid_probability_ignored(self):
        self.est.write_text('ticker,estimated_yes_probability\nNBA-TEST,NaN\n',encoding='utf-8')
        self.assertEqual(load_probabilities(self.est),{})

if __name__=='__main__': unittest.main()
