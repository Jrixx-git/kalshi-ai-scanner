"""Fail-closed bridge: validated opportunities + fresh quote snapshots -> PAPER ledger.
No real order endpoints, no credential handling, no invented liquidity.
"""
import argparse
import csv
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from paper_engine import PaperEngine

D = Decimal

def decide(opportunity, quote, *, max_age_seconds=30, min_edge=D('0.03')):
    """Return (candidate, reason). All inputs must be independently supplied."""
    try:
        ticker = opportunity['ticker']
        side = opportunity['side'].upper()
        if side not in ('YES', 'NO') or ticker != quote['ticker']:
            return None, 'Ticker/side mismatch'
        p = D(str(opportunity['estimated_probability']))
        ask = D(str(quote[side.lower() + '_ask']))
        size = int(quote[side.lower() + '_ask_size'])
        fee = D(str(quote['estimated_total_fees']))
        ts = datetime.fromisoformat(quote['observed_at'].replace('Z', '+00:00'))
        if ts.tzinfo is None:
            return None, 'Quote missing timezone'
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        if age < 0 or age > max_age_seconds:
            return None, 'Stale or future quote'
        if not all(x.is_finite() for x in (p, ask, fee)) or not D('0') <= p <= D('1'):
            return None, 'Invalid probability'
        if not D('0') < ask < D('1') or size <= 0 or fee < 0:
            return None, 'Invalid quote/liquidity/fees'
        # Conservative 1-contract test: fee supplied for exactly one contract.
        edge = p - ask - fee
        if edge < min_edge:
            return None, 'Insufficient modeled edge'
        return dict(signal_id=f"{ticker}:{side}:{quote['observed_at']}", ticker=ticker,
                    side=side, ask=str(ask), ask_size=size, contracts=1, fee=str(fee)), 'Eligible for assumed paper fill'
    except (KeyError, ValueError, TypeError, InvalidOperation, OverflowError):
        return None, 'Missing or invalid input'

def run(opportunities_file, quotes_file, ledger):
    with open(opportunities_file, newline='', encoding='utf-8') as f:
        opportunities = list(csv.DictReader(f))
    with open(quotes_file, encoding='utf-8') as f:
        quotes = json.load(f)
    if not isinstance(quotes, list):
        raise ValueError('quotes file must be a JSON array')
    quote_by_ticker = {q['ticker']: q for q in quotes}
    engine = PaperEngine(ledger)
    try:
        for o in opportunities:
            q = quote_by_ticker.get(o.get('ticker'))
            if q is None:
                print(o.get('ticker'), 'SKIP: No verified quote')
                continue
            trade, reason = decide(o, q)
            if trade is None:
                print(o.get('ticker'), 'SKIP:', reason)
                continue
            ok, message = engine.enter(**trade)
            print(o['ticker'], 'PAPER' if ok else 'SKIP', message)
    finally:
        engine.close()

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Paper-only bridge; requires independent fresh quote JSON')
    ap.add_argument('--opportunities', default='opportunities.csv')
    ap.add_argument('--quotes', required=True)
    ap.add_argument('--ledger', default='paper_ledger.sqlite3')
    args = ap.parse_args()
    run(args.opportunities, args.quotes, args.ledger)
