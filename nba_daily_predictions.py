"""NBA v0.6: authenticated GET-only NBA data -> daily research CSV. No trading.

Uses frozen v0.5 temperature 1.23. Ratings use only final games strictly
before the target league date; all games on a history date share pre-date Elo.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from nba_calibration import transform
from nba_elo import win_probability

BASE = 'https://api.balldontlie.io/v1/games'
HISTORY_START = '2022-10-01'
TEMPERATURE = 1.23
FIELDS = ('game_id', 'date', 'tipoff_utc', 'home_team_id', 'away_team_id',
          'home_team', 'away_team', 'home_elo', 'away_elo',
          'raw_home_win_probability', 'home_win_probability',
          'away_win_probability', 'calibration_temperature',
          'generated_at_utc', 'history_before', 'mode')
EASTERN = ZoneInfo('America/New_York')


def utc_timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Timestamp must be a string')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise ValueError('Timestamp requires timezone')
    return result.astimezone(timezone.utc)


def game_date(game):
    value = str(game['date'])[:10]
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError('Invalid game date')
    return value


def teams(game):
    h, a = int(game['home_team']['id']), int(game['visitor_team']['id'])
    if h <= 0 or a <= 0 or h == a:
        raise ValueError('Invalid teams')
    return h, a


def lifecycle(game):
    # Prefer the provider's explicit lifecycle. Unknown/conflicting data fail closed.
    if game.get('postponed'):
        return 'postponed'
    state = game.get('status_state')
    if state is not None:
        return state
    if game.get('status') == 'Final':
        return 'final'
    if game.get('period') == 0 and re.fullmatch(r'\d{1,2}:\d{2}\s*[ap]m\s+ET', str(game.get('status', '')), re.I):
        return 'scheduled'
    return 'unknown'


def get_page(key, params):
    request = urllib.request.Request(BASE + '?' + urllib.parse.urlencode(params),
                                     headers={'Authorization': key, 'Accept': 'application/json',
                                              'User-Agent': 'NBAOfflineResearch/0.6'}, method='GET')
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            code = error.code
            if code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError(f'BALLDONTLIE HTTP {code}; no predictions exported') from None
            time.sleep(15 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise RuntimeError('BALLDONTLIE unavailable; no predictions exported') from None
            time.sleep(15 * (attempt + 1))


def fetch_games(key, params, *, fetch=get_page, pause=13, max_pages=200):
    if not key:
        raise ValueError('BALLDONTLIE_API_KEY is missing')
    if max_pages < 1:
        raise ValueError('Invalid page limit')
    result, ids, cursors = [], set(), set()
    cursor = None
    for _ in range(max_pages):
        query = list(params) + [('per_page', '100')]
        if cursor is not None:
            query.append(('cursor', str(cursor)))
        payload = fetch(key, query)
        if not isinstance(payload.get('data'), list) or 'next_cursor' not in payload.get('meta', {}):
            raise ValueError('Malformed API page or missing pagination metadata')
        for game in payload['data']:
            gid = int(game['id'])
            if gid <= 0 or gid in ids:
                raise ValueError('Invalid or duplicate game ID across API pages')
            ids.add(gid)
            result.append(game)
        cursor = payload['meta']['next_cursor']
        if cursor is None:
            return result
        if str(cursor) in cursors:
            raise ValueError('Repeated pagination cursor')
        cursors.add(str(cursor))
        time.sleep(pause)
    raise ValueError('Page limit reached; refusing incomplete history/schedule')


def build_ratings(history, before):
    grouped, seen = defaultdict(list), set()
    for game in history:
        gid = int(game['id'])
        if gid in seen:
            raise ValueError('Duplicate history game')
        seen.add(gid)
        day = game_date(game)
        if not HISTORY_START <= day < before or lifecycle(game) != 'final':
            continue
        h, a = teams(game)
        hs, av = int(game['home_team_score']), int(game['visitor_team_score'])
        if min(hs, av) <= 0 or hs == av:
            raise ValueError('Invalid final score')
        grouped[day].append((gid, h, a, int(hs > av)))
    ratings, n = {}, 0
    for day in sorted(grouped):
        changes = defaultdict(float)
        for _, h, a, outcome in sorted(grouped[day]):
            p = win_probability(ratings.get(h, 1500.), ratings.get(a, 1500.), 65)
            delta = 20 * (outcome - p)
            changes[h] += delta
            changes[a] -= delta
            n += 1
        for team, delta in changes.items():
            ratings[team] = ratings.get(team, 1500.) + delta
    if not n:
        raise ValueError('No eligible completed history')
    return ratings, n, max(grouped)


def predict(history, schedule, target_date, now):
    if now.utcoffset() is None:
        raise ValueError('Generation time requires timezone')
    target = date.fromisoformat(target_date)
    if target < now.astimezone(EASTERN).date():
        raise ValueError('Retrospective daily prediction is unsupported')
    ratings, n, last_day = build_ratings(history, target_date)
    rows, skipped, seen = [], [], set()
    for game in sorted(schedule, key=lambda g: int(g['id'])):
        gid = int(game['id'])
        if gid in seen:
            raise ValueError('Duplicate scheduled game')
        seen.add(gid)
        reason = None
        if game_date(game) != target_date:
            reason = 'different_date'
        elif lifecycle(game) != 'scheduled' or game.get('period') != 0:
            reason = 'not_confirmed_scheduled'
        else:
            try:
                tipoff = utc_timestamp(game['datetime'])
            except (KeyError, TypeError, ValueError):
                reason = 'missing_or_invalid_tipoff'
            if reason is None and tipoff <= now:
                reason = 'tipoff_already_passed'
        if reason:
            skipped.append(dict(game_id=gid, reason=reason))
            continue
        h, a = teams(game)
        if h not in ratings or a not in ratings:
            raise ValueError('Scheduled team missing from history; refusing cold-start prediction')
        raw = win_probability(ratings[h], ratings[a], 65)
        # Match six-decimal v0.5 fitting input before applying its frozen transform.
        p = transform(round(raw, 6), TEMPERATURE)
        rows.append(dict(game_id=gid, date=target_date, tipoff_utc=tipoff.isoformat(),
                         home_team_id=h, away_team_id=a,
                         home_team=game['home_team'].get('abbreviation', str(h)),
                         away_team=game['visitor_team'].get('abbreviation', str(a)),
                         home_elo=round(ratings[h],6), away_elo=round(ratings[a],6),
                         raw_home_win_probability=round(raw,6), home_win_probability=round(p,6),
                         away_win_probability=round(1-p,6), calibration_temperature=TEMPERATURE,
                         generated_at_utc=now.astimezone(timezone.utc).isoformat(),
                         history_before=target_date, mode='RESEARCH_ONLY_NO_TRADING'))
    rows.sort(key=lambda r:(r['tipoff_utc'],r['game_id']))
    return rows, dict(version='0.6', target_date=target_date, timezone='America/New_York',
                      generated_at_utc=now.astimezone(timezone.utc).isoformat(),
                      history_start=HISTORY_START, history_before=target_date,
                      last_history_date=last_day, history_games=n, rated_teams=len(ratings),
                      schedule_games=len(schedule), exported_games=len(rows), skipped=skipped,
                      calibration_version='0.5-recreated', temperature=TEMPERATURE,
                      elo=dict(k=20, initial=1500, home_advantage=65, updates='after each date'),
                      live_trading_enabled=False,
                      caveat='Exploratory calibrated Elo; no market prices or established trading edge. History availability timestamps and schedule completeness are not independently certified.')


def export(rows, metadata, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ('nba_predictions_' + metadata['target_date'] + '.csv')
    # A header-only file is an explicit successful no-games result.
    temporary = path.with_suffix('.csv.tmp')
    with temporary.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)
    metadata['csv_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix('.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', default='', help='NBA league date YYYY-MM-DD; default today in New York')
    parser.add_argument('--output-dir', default='daily_predictions')
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    target = date.fromisoformat(args.date) if args.date else now.astimezone(EASTERN).date()
    if target < now.astimezone(EASTERN).date() or target > now.astimezone(EASTERN).date()+timedelta(days=7):
        parser.error('Date must be today through seven days ahead in New York')
    key = os.environ.get('BALLDONTLIE_API_KEY', '')
    history = fetch_games(key, [('start_date',HISTORY_START),('end_date',(target-timedelta(days=1)).isoformat())])
    time.sleep(13)
    schedule = fetch_games(key, [('dates[]',target.isoformat())])
    # Recheck time after downloads so no game that started during fetching is exported.
    rows, metadata = predict(history, schedule, target.isoformat(), datetime.now(timezone.utc))
    metadata['retrieved_history_sha256'] = hashlib.sha256(json.dumps(history,sort_keys=True).encode()).hexdigest()
    path = export(rows, metadata, args.output_dir)
    print(f'Saved {len(rows)} research predictions to {path}; live trading disabled.')


if __name__ == '__main__':
    main()
