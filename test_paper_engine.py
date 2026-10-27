import tempfile
import unittest
from pathlib import Path
from paper_engine import PaperEngine

class PaperEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'ledger.db'
        self.engine = PaperEngine(self.path)
    def tearDown(self):
        self.engine.close()
        self.tmp.cleanup()
    def enter(self, signal_id='s1'):
        return self.engine.enter(signal_id=signal_id,ticker='TEST',side='YES',ask='.4',ask_size=100,contracts=10,fee='1',day='2026-10-27')
    def test_entry(self):
        self.assertTrue(self.enter()[0])
        self.assertEqual(self.engine.account('2026-10-27').open_exposure, 5)
    def test_duplicate(self):
        self.enter()
        self.assertFalse(self.enter()[0])
    def test_liquidity(self):
        self.assertFalse(self.engine.enter(signal_id='x',ticker='T',side='YES',ask='.4',ask_size=1,contracts=2,fee='0')[0])
    def test_position_limit(self):
        self.assertFalse(self.engine.enter(signal_id='x',ticker='T',side='YES',ask='.6',ask_size=200,contracts=100,fee='0')[0])
    def test_exposure_limit(self):
        for i in range(3):
            self.assertTrue(self.engine.enter(signal_id=str(i),ticker='T'+str(i),side='YES',ask='.49',ask_size=100,contracts=100,fee='1')[0])
        self.assertFalse(self.enter('extra')[0])  # daily budget binds before $500
    def test_aggregate_ticker_limit(self):
        self.assertTrue(self.enter('one')[0])
        self.assertFalse(self.engine.enter(signal_id='two',ticker='TEST',side='NO',ask='.5',ask_size=100,contracts=100,fee='0')[0])
    def test_daily_cutoff(self):
        for i in range(3):
            self.assertTrue(self.engine.enter(signal_id=str(i),ticker='T',side='YES',ask='.4',ask_size=100,contracts=100,fee='0',day='2026-10-27')[0])
            self.assertTrue(self.engine.settle(str(i),'NO',day='2026-10-27')[0])
        self.assertFalse(self.engine.enter(signal_id='after',ticker='T',side='YES',ask='.4',ask_size=100,contracts=100,fee='0',day='2026-10-27')[0])
    def test_persistence(self):
        self.enter()
        self.engine.close()
        self.engine = PaperEngine(self.path)
        self.assertFalse(self.enter()[0])
    def test_invalid_price(self):
        self.assertFalse(self.engine.enter(signal_id='x',ticker='T',side='YES',ask='NaN',ask_size=1,contracts=1,fee='0')[0])
    def test_settle_once(self):
        self.enter()
        self.assertTrue(self.engine.settle('s1','YES')[0])
        self.assertFalse(self.engine.settle('s1','YES')[0])
if __name__ == '__main__':
    unittest.main()
