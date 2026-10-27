"""NBA Kalshi public-data capture. GET only; never places or simulates orders."""
import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

BASE = 'https://external-api.kalshi.com/trade-api/v2'
SERIES = 'KXNBAGAME'


def get(path, params=None, *, attempts=4):
    if not (path in ('/markets', '/series/KXNBAGAME') or re.fullmatch(r'/markets/KXNBAGAME-[A-Z0-9-]+(?:/orderbook)?', path)):
        raise ValueError('Only NBA market GET endpoints allowed')
    url = BASE + path + ('?' + urllib.parse.urlencode(params) if params else '')
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'NBA-Paper-Research/0.8'}, method='GET')
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise
            retry = exc.headers.get('Retry-After', '')
            delay = min(30, float(retry)) if retry.isdigit() else min(8, 2 ** attempt)
            time.sleep(delay)
    raise RuntimeError('Market retrieval exhausted')


def discover(fetch=get):
    cursor = None
    seen_cursors = set()
    markets = {}
    while True:
        args = {'series_ticker': SERIES, 'status': 'open', 'limit': 200}
        if cursor:
            args['cursor'] = cursor
        page = fetch('/markets', args)
        if not isinstance(page.get('markets'), list):
            raise ValueError('Invalid markets response')
        for market in page['markets']:
            ticker = market.get('ticker', '')
            if not re.fullmatch(r'KXNBAGAME-[A-Z0-9-]+', ticker):
                raise ValueError('Unexpected series ticker')
            if ticker in markets:
                raise ValueError('Duplicate market ticker')
            markets[ticker] = market
        cursor = page.get('cursor')
        if not cursor:
            return list(markets.values())
        if cursor in seen_cursors:
            raise ValueError('Repeated pagination cursor')
        seen_cursors.add(cursor)


def capture(root, fetch=get, *, workers=4, event_filter=None):
    started = datetime.now(timezone.utc).isoformat()
    markets = discover(fetch)
    if event_filter is not None:
        markets = [market for market in markets if market.get('event_ticker') in event_filter]
    books = {}
    errors = {}
    def read_book(market):
        ticker = market['ticker']
        observed_at = datetime.now(timezone.utc).isoformat()
        try:
            book = fetch('/markets/' + ticker + '/orderbook', {'depth': 0})
            if not isinstance(book.get('orderbook_fp'), dict):
                raise ValueError('Missing fixed-point orderbook')
            return ticker, {'observed_at': observed_at, 'received_at': datetime.now(timezone.utc).isoformat(), 'raw': book}, None
        except (OSError, ValueError, KeyError) as exc:
            return ticker, None, type(exc).__name__
    if not isinstance(workers, int) or not 1 <= workers <= 4:
        raise ValueError('Workers must be between 1 and 4')
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(read_book, market) for market in markets]):
            ticker, book, error = future.result()
            if error:
                errors[ticker] = error
            else:
                books[ticker] = book
    snapshot = {'schema': 'nba-kalshi-capture-v1', 'started_at': started,
                'completed_at': datetime.now(timezone.utc).isoformat(),
                'source': BASE, 'series': SERIES, 'markets': markets,
                'orderbooks': books, 'errors': errors, 'live_trading': False}
    data = (json.dumps(snapshot, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    digest = hashlib.sha256(data).hexdigest()
    path = Path(root) / (digest + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('xb') as f:
            f.write(data)
    except FileExistsError:
        if path.read_bytes() != data:
            raise ValueError('Archive conflict')
    return path, len(markets), len(books), len(errors)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', default='paper_v08/snapshots')
    args = p.parse_args()
    path, markets, books, errors = capture(args.output_dir)
    print(json.dumps({'path': str(path), 'markets': markets, 'orderbooks': books, 'errors': errors}))
    if errors:
        raise SystemExit(1)
