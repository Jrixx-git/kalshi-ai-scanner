"""Prospective full-day GET-only capture using the existing BALLDONTLIE key."""
import argparse
import hashlib
import os
from datetime import datetime, date, timezone
from pathlib import Path
from nba_daily_predictions import fetch_games, EASTERN
from nba_forward_test import encode, immutable
from nba_v08_capture import capture, get
from nba_v08_schedule import capture_schedule
from nba_v08_fees import capture as capture_fee
from nba_v09_injuries import collect as injuries


def collect(day, root):
    target = date.fromisoformat(day)
    if target != datetime.now(timezone.utc).astimezone(EASTERN).date():
        raise ValueError('Only today; no retrospective quote reconstruction')
    root = Path(root)
    started = datetime.now(timezone.utc).isoformat()
    games = fetch_games(os.environ.get('BALLDONTLIE_API_KEY', ''), [('dates[]', day)], max_pages=2)
    receipt = datetime.now(timezone.utc).isoformat()
    raw = encode(dict(source='https://api.balldontlie.io/v1/games', requested_date=day,
        requested_at=started, received_at=receipt, games=games, pagination_complete=True))
    immutable(root/'universe'/(hashlib.sha256(raw).hexdigest()+'.json'), raw)
    # Independent source/rules checks in the audit determine eligible pairs.
    capture_schedule(day, root/'schedules')
    calls = 0
    def bounded_get(path, params=None):
        nonlocal calls
        calls += 1
        if calls > 120:
            raise ValueError('Public market request budget exhausted')
        return get(path, params, attempts=1)
    # Capture all discovered NBA books, never restrict to selected paper trades.
    snapshot, markets, books, errors = capture(root/'snapshots', fetch=bounded_get)
    import json
    payload = json.loads(snapshot.read_bytes())
    events = sorted({m['event_ticker'] for m in payload['markets']})
    # Fee observations follow this quote; later runs may use them if fresh.
    # Never relabel them as available before this first capture.
    if len(events) > 40:
        raise ValueError('Event budget exceeded')
    series_at = datetime.now(timezone.utc).isoformat()
    series = bounded_get('/series/KXNBAGAME')['series']
    failures = []
    for event in events:
        try:
            capture_fee(event, root/'fees', series, series_at, fetch=bounded_get)
        except (ValueError, OSError, KeyError) as error:
            failures.append(dict(event=event, error=type(error).__name__))
    injuries(root/'injuries', max_reports=2)
    summary = dict(games=len(games), markets=markets, books=books, book_errors=errors,
                   market_requests=calls, fee_errors=failures, completed_at=datetime.now(timezone.utc).isoformat())
    raw = encode(summary)
    immutable(root/'runs'/(hashlib.sha256(raw).hexdigest()+'.json'), raw)
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--date', default=datetime.now(timezone.utc).astimezone(EASTERN).date().isoformat())
    p.add_argument('--output', default='research/nba_v09/prospective')
    a = p.parse_args()
    print(encode(collect(a.date, a.output)).decode())
