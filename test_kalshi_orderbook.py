import unittest
from kalshi_orderbook import quote_from_orderbook

class OrderbookTests(unittest.TestCase):
    def test_opposite_bid_becomes_ask(self):
        q = quote_from_orderbook('TEST', {'orderbook_fp': {'yes_dollars': [['0.40','8.00']], 'no_dollars': [['0.35','12.00']]}})
        self.assertEqual(q['yes_ask'], '0.65')
        self.assertEqual(q['yes_ask_size'], 12)
        self.assertEqual(q['no_ask'], '0.60')
    def test_empty_book(self):
        q = quote_from_orderbook('TEST', {'orderbook_fp': {'yes_dollars': [], 'no_dollars': []}})
        self.assertNotIn('yes_ask', q)
    def test_crossed_book(self):
        with self.assertRaises(ValueError):
            quote_from_orderbook('TEST', {'orderbook_fp': {'yes_dollars': [['.6','1']], 'no_dollars': [['.5','1']]}})
    def test_fractional_size_not_overstated(self):
        q = quote_from_orderbook('TEST', {'orderbook_fp': {'yes_dollars': [], 'no_dollars': [['.2','1.75']]}})
        self.assertEqual(q['yes_ask_size'], 1)
    def test_invalid_size(self):
        with self.assertRaises(ValueError):
            quote_from_orderbook('TEST', {'orderbook_fp': {'yes_dollars': [], 'no_dollars': [['.2','-1']]}})
    def test_missing_schema(self):
        with self.assertRaises(ValueError):
            quote_from_orderbook('TEST', {})

if __name__ == '__main__':
    unittest.main()
