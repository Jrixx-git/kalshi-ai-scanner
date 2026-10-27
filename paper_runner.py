"""One-shot, read-only market scan -> quote -> validated PAPER entry.
No real orders. Estimates must be independently sourced and fee estimates supplied.
"""
import argparse
import csv
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from scanner import scan
from kalshi_orderbook import fetch_orderbook
from auto_paper import decide
from paper_engine import PaperEngine


def load_probabilities(path):
    result = {}
    with open(path, newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            ticker = row.get('ticker', '').strip()
            try:
                p = Decimal(row['estimated_yes_probability'])
            except (KeyError, InvalidOperation, TypeError):
                continue
            if ticker and p.is_finite() and 0 <= p <= 1:
                result[ticker] = p
    return result


def run(*, pages, estimates_file, fees_file, ledger, max_markets=30, scan_fn=scan, quote_fn=fetch_orderbook):
    """Fail closed on missing data; fee map is a one-contract conservative estimate.
    The scanner's keyword sports classification is provisional, not league verified.
    """
    estimates = load_probabilities(estimates_file)
    with open(fees_file, encoding='utf-8') as handle:
        fees = json.load(handle)
    if not isinstance(fees, dict):
        raise ValueError('Fee estimates must be a ticker-to-USD JSON object')
    stats = {'considered': 0, 'paper_entries': 0, 'skipped': 0, 'errors': 0}
    engine = PaperEngine(ledger)
    try:
        markets = [m for m in scan_fn(pages) if m.get('category') == 'sports' and m.get('ticker') in estimates]
        for market in markets[:max_markets]:
            stats['considered'] += 1
            ticker = market['ticker']
            if ticker not in fees:
                stats['skipped'] += 1
                continue
            try:
                fee = Decimal(str(fees[ticker]))
                if not fee.is_finite() or fee < 0:
                    stats['skipped'] += 1
                    continue
                quote = quote_fn(ticker)
                quote['estimated_total_fees'] = str(fee)
                p = estimates[ticker]
                candidates = []
                for side, probability in [('YES', p), ('NO', 1-p)]:
                    opportunity = {'ticker': ticker, 'side': side, 'estimated_probability': str(probability)}
                    trade, reason = decide(opportunity, quote)
                    if trade is not None:
                        candidates.append((Decimal(str(probability)) - Decimal(trade['ask']) - fee, trade))
                if not candidates:
                    stats['skipped'] += 1
                    continue
                _, best = max(candidates, key=lambda item: item[0])
                # One open position per ticker, even across repeated runs.
                exists = engine.db.execute("SELECT 1 FROM trades WHERE ticker=? AND status='OPEN' LIMIT 1", (ticker,)).fetchone()
                if exists:
                    stats['skipped'] += 1
                    continue
                ok, _ = engine.enter(**best)
                stats['paper_entries' if ok else 'skipped'] += 1
            except (ValueError, KeyError, TypeError, OSError, TimeoutError) as exc:
                print(f'{ticker}: skipped due to data error: {type(exc).__name__}')
                stats['errors'] += 1
    finally:
        engine.close()
    return stats


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='One-shot paper-only Kalshi research runner')
    parser.add_argument('--pages', type=int, default=3)
    parser.add_argument('--estimates', required=True, type=Path)
    parser.add_argument('--fees', required=True, type=Path)
    parser.add_argument('--ledger', default='paper_ledger.sqlite3')
    args = parser.parse_args()
    print(json.dumps(run(pages=max(1, min(args.pages, 25)), estimates_file=args.estimates,
                         fees_file=args.fees, ledger=args.ledger)))
