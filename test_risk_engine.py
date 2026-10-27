import unittest
from decimal import Decimal as D
from risk_engine import PaperAccount, check_paper_trade

class RiskTests(unittest.TestCase):
    def test_small_trade_passes(self):
        self.assertTrue(check_paper_trade(PaperAccount(), 'YES', D('.40'), 10, D('1'))[0])
    def test_position_cap(self):
        self.assertFalse(check_paper_trade(PaperAccount(), 'YES', D('.60'), 100)[0])
    def test_exposure_cap(self):
        self.assertFalse(check_paper_trade(PaperAccount(open_exposure=D('490')), 'NO', D('.50'), 30)[0])
    def test_daily_cutoff(self):
        self.assertFalse(check_paper_trade(PaperAccount(realized_daily_pnl=D('-150')), 'YES', D('.40'), 10)[0])
    def test_fees_count_toward_limit(self):
        self.assertFalse(check_paper_trade(PaperAccount(), 'YES', D('.50'), 100, D('1'))[0])
    def test_invalid_contracts(self):
        self.assertFalse(check_paper_trade(PaperAccount(), 'YES', D('.50'), 0)[0])

if __name__ == '__main__':
    unittest.main()
