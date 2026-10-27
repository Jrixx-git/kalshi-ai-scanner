"""Read-only Kalshi orderbook adapter. No credentials or order endpoints."""
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

BASE = 'https://external-api.kalshi.com/trade-api/v2'

def quote_from_orderbook(ticker, payload, observed_at=None):
    book = payload.get('orderbook_fp')
    if not isinstance(book, dict):
        raise ValueError('Missing orderbook_fp')
    def best(side):
        levels = book.get(side)
        if not isinstance(levels, list):
            raise ValueError('Missing orderbook side')
        parsed = []
        for level in levels:
            if not isinstance(level, (list, tuple)) or len(level) != 2:
                raise ValueError('Malformed price level')
            p, q = map(lambda x: Decimal(str(x)), level)
            if not p.is_finite() or not q.is_finite() or not (0 < p < 1) or q <= 0:
                raise ValueError('Invalid price or size')
            parsed.append((p, q))
        return max(parsed, default=None)
    yes_bid = best('yes_dollars')
    no_bid = best('no_dollars')
    if yes_bid and no_bid and yes_bid[0] + no_bid[0] >= 1:
        raise ValueError('Crossed or locked orderbook')
    stamp = observed_at or datetime.now(timezone.utc).isoformat()
    result = {'ticker': ticker, 'observed_at': stamp}
    # Opposite-side bid implies the ask. Only whole-contract displayed size is used.
    for side, opposite in (('yes', no_bid), ('no', yes_bid)):
        if opposite:
            ask, size = 1 - opposite[0], int(opposite[1])
            if size > 0:
                result[f'{side}_ask'] = str(ask)
                result[f'{side}_ask_size'] = size
    return result

def fetch_orderbook(ticker, timeout=15):
    if not ticker or not all(c.isalnum() or c in '-_' for c in ticker):
        raise ValueError('Invalid ticker')
    url = BASE + '/markets/' + urllib.parse.quote(ticker, safe='') + '/orderbook?depth=1'
    req = urllib.request.Request(url, headers={'User-Agent': 'KalshiPaperResearch/0.2'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        payload = json.load(response)
    return quote_from_orderbook(ticker, payload)
