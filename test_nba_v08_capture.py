import json
import tempfile
import unittest
from pathlib import Path
from nba_v08_capture import capture, discover, get


class CaptureTests(unittest.TestCase):
    def test_paginated_and_archive(self):
        calls = []
        def fetch(path, params):
            calls.append((path, params))
            if path == '/markets':
                if 'cursor' not in params:
                    return {'markets': [{'ticker': 'KXNBAGAME-26OCT27BKNBOS-BOS'}], 'cursor': 'next'}
                return {'markets': [], 'cursor': ''}
            return {'orderbook_fp': {'yes_dollars': [['0.2', '4']], 'no_dollars': []}}
        with tempfile.TemporaryDirectory() as root:
            path, markets, books, errors = capture(root, fetch)
            data = json.loads(Path(path).read_text())
            self.assertEqual((markets, books, errors), (1, 1, 0))
            self.assertFalse(data['live_trading'])
            self.assertEqual(data['orderbooks'][data['markets'][0]['ticker']]['raw']['orderbook_fp']['yes_dollars'][0][0], '0.2')
            self.assertEqual(calls[1][1]['cursor'], 'next')
    def test_repeated_cursor_fails(self):
        with self.assertRaises(ValueError):
            discover(lambda path, params: {'markets': [], 'cursor': 'same'})
    def test_unrelated_market_fails(self):
        with self.assertRaises(ValueError):
            discover(lambda path, params: {'markets': [{'ticker': 'KXNFL-X'}]})
    def test_order_endpoint_forbidden(self):
        with self.assertRaises(ValueError):
            get('/portfolio/orders')
    def test_failed_book_is_visible(self):
        def fetch(path, params):
            if path == '/markets': return {'markets': [{'ticker': 'KXNBAGAME-ABC-DEF'}]}
            raise OSError('offline')
        with tempfile.TemporaryDirectory() as root:
            path, _, books, errors = capture(root, fetch)
            self.assertEqual((books, errors), (0, 1))
            self.assertIn('KXNBAGAME-ABC-DEF', json.loads(path.read_text())['errors'])

if __name__ == '__main__': unittest.main()
