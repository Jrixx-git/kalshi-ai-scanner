import unittest
from datetime import datetime, timedelta, timezone
from auto_paper import decide

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.o = {'ticker':'SPORTS-TEST', 'side':'YES', 'estimated_probability':'0.70'}
        self.q = {'ticker':'SPORTS-TEST', 'yes_ask':'0.50', 'yes_ask_size':10,
                  'estimated_total_fees':'0.01', 'observed_at':datetime.now(timezone.utc).isoformat()}
    def test_eligible(self): self.assertIsNotNone(decide(self.o,self.q)[0])
    def test_stale(self):
        self.q['observed_at']=(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()
        self.assertIsNone(decide(self.o,self.q)[0])
    def test_no_liquidity(self):
        self.q['yes_ask_size']=0
        self.assertIsNone(decide(self.o,self.q)[0])
    def test_low_edge(self):
        self.o['estimated_probability']='0.51'
        self.assertIsNone(decide(self.o,self.q)[0])
    def test_missing_fees(self):
        del self.q['estimated_total_fees']
        self.assertIsNone(decide(self.o,self.q)[0])
    def test_mismatch(self):
        self.q['ticker']='OTHER'
        self.assertIsNone(decide(self.o,self.q)[0])
    def test_bad_probability(self):
        self.o['estimated_probability']='NaN'
        self.assertIsNone(decide(self.o,self.q)[0])
if __name__=='__main__': unittest.main()
