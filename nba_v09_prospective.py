"""Bounded prospective source evidence; no predictions, ledger writes or orders."""
import argparse
import hashlib
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from nba_daily_predictions import EASTERN, fetch_games, lifecycle
from nba_forward_test import encode, immutable
from nba_v08_capture import capture, BASE
from nba_v08_schedule import BASE as SCHEDULE_BASE, ESPN_IDS
from nba_v08_valuation import ALIASES, TEAMS, match, timestamp
from nba_v09_injuries import collect as injuries

START = timestamp('2026-11-11T18:00:00Z')
STOP = timestamp('2026-11-25T18:00:00Z')
MAX_MARKET_REQUESTS = 70
MAX_BDL_REQUESTS = 4
MAX_BYTES = 8 * 1024 * 1024


def market_get(path, params=None, *, attempts=1):
    from nba_v09_injuries import NoRedirect
    import re
    if path != '/markets' and not re.fullmatch(r'/markets/KXNBAGAME-[A-Z0-9-]+/orderbook', path):
        raise ValueError('Research GET endpoint refused')
    url = BASE + path + ('?' + urllib.parse.urlencode(params) if params else '')
    req = urllib.request.Request(url, method='GET', headers={'User-Agent': 'NBA-Research/0.9'})
    with urllib.request.build_opener(NoRedirect).open(req, timeout=15) as response:
        raw = response.read(MAX_BYTES+1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Kalshi byte budget')
    return json.loads(raw)


def capture_schedule(day, root):
    from nba_v09_injuries import NoRedirect
    datetime.strptime(day, '%Y-%m-%d')
    url = SCHEDULE_BASE + day.replace('-', '')
    started = datetime.now(timezone.utc).isoformat()
    req = urllib.request.Request(url, method='GET', headers={'User-Agent':'NBA-Research/0.9'})
    with urllib.request.build_opener(NoRedirect).open(req, timeout=15) as response:
        raw = response.read(MAX_BYTES+1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Schedule byte budget')
    obj = dict(schema='espn-nba-schedule-v1', requested_date=day, requested_at=started,
               received_at=datetime.now(timezone.utc).isoformat(), source=url, payload=json.loads(raw))
    return save(Path(root).parent, Path(root).name, obj)


def active(now):
    return START <= now < STOP


def save(root, kind, obj):
    raw = encode(obj)
    path = Path(root) / kind / (hashlib.sha256(raw).hexdigest() + '.json')
    immutable(path, raw)
    return path


def game_record(g, now):
    """Retain every supplied game, including unresolvable schedule entries."""
    row = dict(game_id=str(g.get('id')), date=str(g.get('date', ''))[:10],
               status='unknown_schedule', market_status='not_attempted', no_trade=True)
    try:
        h, a = (ALIASES.get(g[k]['abbreviation'], g[k]['abbreviation'])
                for k in ('home_team', 'visitor_team'))
        if h not in TEAMS or a not in TEAMS or h == a:
            raise ValueError('identity')
        tip = timestamp(g['datetime'])
        row.update(home_team=h, away_team=a, home_team_id=g['home_team']['id'],
                   away_team_id=g['visitor_team']['id'], tipoff_utc=tip.isoformat())
        row['status'] = ('pregame' if lifecycle(g) == 'scheduled' and g.get('period') == 0
                         and now < tip else 'not_verified_pregame')
        row['seconds_to_tip_at_request'] = (tip-now).total_seconds()
        row['event_ticker'] = 'KXNBAGAME-' + datetime.strptime(row['date'], '%Y-%m-%d').strftime('%y%b%d').upper() + a + h
    except (KeyError, ValueError, TypeError, AttributeError):
        pass
    return row


def collect(root, *, now=None, bdl_fetch=None, market_fetch=market_get,
            schedule_fetch=capture_schedule, injury_fetch=injuries):
    now = now or datetime.now(timezone.utc)
    if not active(now):
        raise ValueError('Outside approved research collection window')
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    # Exclusive slot claim also protects direct local invocations. Remote claims
    # are persisted on the dedicated evidence branch by the serialized workflow.
    slot = now.strftime('%Y%m%dT%H')
    claim = root / ('claim-' + slot + '.json')
    with claim.open('x') as f:
        json.dump(dict(slot=slot, requested_at=now.isoformat(), live_trading=False), f)
    summary = dict(schema='nba-v09-prospective-v2', slot=slot, started_at=now.isoformat(),
                   stop_at=STOP.isoformat(), live_trading=False, no_trade=True,
                   source_errors={}, dates=[], games=[], independent_games=[], bdl_requests=0, market_requests=0,
                   injury_player_status='unparsed_unverified')
    save(root, 'receipts', summary)
    key = os.environ.get('BALLDONTLIE_API_KEY', '')

    def bdl_page(api_key, params):
        if summary['bdl_requests'] >= MAX_BDL_REQUESTS:
            raise ValueError('BALLDONTLIE request budget')
        summary['bdl_requests'] += 1
        started = datetime.now(timezone.utc).isoformat()
        # Fixed origin, redirects refused, no retries, bounded bytes/time.
        from nba_v09_injuries import NoRedirect
        req = urllib.request.Request('https://api.balldontlie.io/v1/games?' + urllib.parse.urlencode(params),
            headers={'Authorization': api_key, 'User-Agent': 'NBA-Research/0.9'}, method='GET')
        if bdl_fetch is None:
            with urllib.request.build_opener(NoRedirect).open(req, timeout=15) as response:
                raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError('BALLDONTLIE byte budget')
            payload = json.loads(raw)
        else:
            payload = bdl_fetch(api_key, params)
        # Authorization is never serialized. Each page has its actual receipt.
        save(root, 'bdl_pages', dict(requested_at=started, received_at=datetime.now(timezone.utc).isoformat(),
             params=params, payload=payload, source='https://api.balldontlie.io/v1/games'))
        return payload

    schedules = {}
    for delta in (0, 1):
        day = (now.astimezone(EASTERN).date()+timedelta(days=delta)).isoformat()
        status = dict(date=day, universe='unavailable', independent_schedule='unavailable')
        summary['dates'].append(status)
        try:
            started = datetime.now(timezone.utc).isoformat()
            games = fetch_games(key, [('dates[]', day)], fetch=bdl_page, pause=0, max_pages=2)
            receipt = datetime.now(timezone.utc).isoformat()
            save(root, 'universe', dict(source='https://api.balldontlie.io/v1/games',
                 requested_date=day, requested_at=started, received_at=receipt,
                 pagination_complete=True, games=games))
            summary['games'].extend(game_record(g, now) for g in games)
            status['universe'] = 'complete_provider_response'
            status['games'] = len(games)
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
            summary['source_errors']['bdl-'+day] = type(error).__name__
        try:
            p = schedule_fetch(day, root/'schedules')
            schedules[day] = json.loads(Path(p).read_bytes())
            status['independent_schedule'] = 'raw_available'
            # Independent-only events explicitly expose provider omissions.
            status['independent_event_ids'] = [str(e.get('id')) for e in schedules[day]['payload']['events']]
            status['provider_game_count'] = status.get('games')
            status['independent_event_count'] = len(status['independent_event_ids'])
            status['count_agrees'] = status.get('games') == status['independent_event_count']
            for event in schedules[day]['payload']['events']:
                # Independent-only games remain explicit even if provider retrieval failed.
                entry = dict(date=day, event_id=str(event.get('id')), provider_game_ids=[],
                             tipoff_utc=event.get('date'), status='provider_identity_missing_or_unknown')
                try:
                    sides = {s['homeAway']: str(s['team']['id'])
                             for s in event['competitions'][0]['competitors']}
                    entry['provider_game_ids'] = [r['game_id'] for r in summary['games']
                        if r['date'] == day and str(ESPN_IDS.get(r.get('home_team'))) == sides['home']
                        and str(ESPN_IDS.get(r.get('away_team'))) == sides['away']
                        and abs((timestamp(r['tipoff_utc'])-timestamp(event['date'])).total_seconds()) <= 60]
                    if len(entry['provider_game_ids']) == 1:
                        entry['status'] = 'identity_matched'
                except (KeyError, TypeError, ValueError, IndexError, AttributeError):
                    pass
                summary['independent_games'].append(entry)
        except (OSError, ValueError, KeyError, TypeError) as error:
            summary['source_errors']['schedule-'+day] = type(error).__name__

    events = {r['event_ticker'] for r in summary['games'] if r['status'] == 'pregame'}
    snap = None

    def bounded_market(path, params=None):
        if summary['market_requests'] >= MAX_MARKET_REQUESTS:
            raise ValueError('Kalshi request budget')
        summary['market_requests'] += 1
        # Single worker makes request accounting deterministic.
        return market_fetch(path, params, attempts=1)

    try:
        if events:
            p, _, _, _ = capture(root/'snapshots', fetch=bounded_market, workers=1, event_filter=events)
            snap = json.loads(p.read_bytes())
        for row in summary['games']:
            if row['status'] != 'pregame':
                row['market_status'] = 'ineligible_or_unknown_tipoff'
                continue
            good = []
            for m in (snap or {}).get('markets', []):
                try:
                    match(row, m, schedule=schedules.get(row['date']), now=timestamp(snap['completed_at']))
                    good.append(m['ticker'])
                except (ValueError, TypeError, KeyError, AttributeError):
                    pass
            row['matched_contracts'] = good
            row['book_errors'] = {t: snap['errors'][t] for t in good if t in snap['errors']}
            row['market_status'] = ('raw_pair_available' if len(good) == 2 and not row['book_errors']
                                    else 'missing_or_invalid_pair')
            # Raw receipt times still govern downstream as-of eligibility.
    except (OSError, ValueError, KeyError, TypeError) as error:
        summary['source_errors']['kalshi'] = type(error).__name__
        for row in summary['games']:
            if row['status'] == 'pregame':
                row['market_status'] = 'capture_unavailable'
    # An authenticated provider failure must not suppress public injury evidence.
    try:
        records = injury_fetch(root/'injuries', max_reports=2)
        summary['injury_records'] = len(records)
        summary['injury_raw_reports'] = sum(r.get('publication_at') is not None and
            r['status'] == 'raw_available_unparsed' for r in records)
        if not summary['injury_raw_reports']:
            summary['source_errors']['injuries'] = 'NoRawReportAvailable'
    except (OSError, ValueError, KeyError, TypeError) as error:
        summary['source_errors']['injuries'] = type(error).__name__
    summary['completed_at'] = datetime.now(timezone.utc).isoformat()
    save(root, 'runs', summary)
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    result = collect(args.output)
    print(json.dumps(result, sort_keys=True))
    if result['source_errors']:
        raise SystemExit(1)
