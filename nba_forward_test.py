"""NBA v0.7 research scoreboard. GET-only results; no trading imports."""
import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nba_daily_predictions import BASE, utc_timestamp, positive_integer

BASELINE_SHA = '776d8acdcf04168b4f182cb5ea59c813869ee0fcf598878e99699320fec03171'
BASELINE_COMMIT = 'e58267c2a79ca43625a6cb7012c89d5940dd1bc6'
EPSILON = 1e-15


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def immutable(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('xb') as stream:
            stream.write(data)
    except FileExistsError:
        if path.read_bytes() != data:
            raise ValueError('Immutable archive conflict: ' + str(path))


def archive(csv_bytes, metadata_bytes, root, *, commit, run_id, observed_at,
            baseline=False, snapshots=None):
    """First published eligible prediction per game wins; later versions stay auditable."""
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Full source commit required')
    positive_integer(str(run_id), 'run ID')
    observed = utc_timestamp(observed_at)
    meta = json.loads(metadata_bytes)
    if meta.get('live_trading_enabled') is not False:
        raise ValueError('Research mode required')
    if digest(csv_bytes) != meta['csv_sha256']:
        raise ValueError('CSV digest mismatch')
    generated = utc_timestamp(meta['generated_at_utc'])
    if generated > observed:
        raise ValueError('Generation after observation')
    if meta['last_history_date'] >= meta['target_date'] or meta['history_before'] != meta['target_date']:
        raise ValueError('Future history leakage')
    if snapshots:
        history = json.loads(snapshots['history.json'])
        if digest(json.dumps(history, sort_keys=True).encode()) != meta['retrieved_history_sha256']:
            raise ValueError('History snapshot mismatch')
        if any(str(g['date'])[:10] >= meta['target_date'] for g in history):
            raise ValueError('Future history snapshot')
    rows = list(csv.DictReader(io.StringIO(csv_bytes.decode('utf-8'))))
    if len(rows) != meta['exported_games']:
        raise ValueError('Row count mismatch')
    seen = set()
    for row in rows:
        gid = positive_integer(row['game_id'], 'game ID')
        h = positive_integer(row['home_team_id'], 'team ID')
        a = positive_integer(row['away_team_id'], 'team ID')
        p, q = float(row['home_win_probability']), float(row['away_win_probability'])
        tip = utc_timestamp(row['tipoff_utc'])
        if (gid in seen or h == a or not math.isfinite(p) or not math.isfinite(q)
                or not 0 <= p <= 1 or not 0 <= q <= 1 or abs(p + q - 1) > 1e-6):
            raise ValueError('Invalid/duplicate prediction')
        seen.add(gid)
        if (row['mode'] != 'RESEARCH_ONLY_NO_TRADING' or row['date'] != meta['target_date']
                or row['history_before'] != row['date']
                or utc_timestamp(row['generated_at_utc']) != generated or not generated <= observed < tip):
            raise ValueError('Prediction lacks pre-tipoff provenance')
    if baseline and (commit != BASELINE_COMMIT or str(run_id) != '40576182725'):
        raise ValueError('Baseline provenance mismatch')
    bundle = dict(schema_version=1, source_commit=commit, run_id=str(run_id),
                  observed_at=observed_at, baseline=baseline,
                  csv_sha256=digest(csv_bytes), metadata_sha256=digest(metadata_bytes),
                  snapshots={k: digest(v) for k, v in (snapshots or {}).items()})
    identifier = digest(encode(bundle))
    directory = Path(root) / 'predictions' / identifier
    # Manifest is the completion marker: interrupted bundles are never scored.
    immutable(directory / 'predictions.csv', csv_bytes)
    immutable(directory / 'metadata.json', metadata_bytes)
    for name, data in (snapshots or {}).items():
        if name not in ('history.json', 'schedule.json'):
            raise ValueError('Invalid snapshot name')
        immutable(directory / name, data)
    immutable(directory / 'manifest.json', encode(bundle))
    return identifier


def import_baseline(path, root):
    data = Path(path).read_bytes()
    if digest(data) != BASELINE_SHA:
        raise ValueError('Baseline ZIP digest mismatch')
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        csv_name = next(n for n in z.namelist() if n.endswith('.csv'))
        json_name = next(n for n in z.namelist() if n.endswith('.json'))
        result = archive(z.read(csv_name), z.read(json_name), root,
                         commit=BASELINE_COMMIT, run_id='40576182725',
                         observed_at='2026-10-27T20:17:26Z', baseline=True)
    immutable(Path(root) / 'baseline' / 'artifact.zip', data)
    return result


def predictions(root):
    candidates = []
    for path in sorted((Path(root) / 'predictions').glob('*/manifest.json')):
        bundle = json.loads(path.read_bytes())
        if digest(encode(bundle)) != path.parent.name:
            raise ValueError('Manifest integrity failure')
        for filename, expected in [('predictions.csv', bundle['csv_sha256']),
                                   ('metadata.json', bundle['metadata_sha256']),
                                   *bundle['snapshots'].items()]:
            if digest((path.parent / filename).read_bytes()) != expected:
                raise ValueError('Archive integrity failure')
        for row in csv.DictReader(io.StringIO((path.parent / 'predictions.csv').read_text())):
            candidates.append((utc_timestamp(bundle['observed_at']), path.parent.name, row, bundle))
    selected = {}
    for _, identifier, row, bundle in sorted(candidates, key=lambda x: (x[0], x[1])):
        gid = row['game_id']
        if gid in selected:
            prior = selected[gid][0]
            if any(row[k] != prior[k] for k in ('home_team_id', 'away_team_id', 'date')):
                raise ValueError('Conflicting identity for game ' + gid)
        else:
            selected[gid] = row, identifier, bundle
    return selected


def result_state(game):
    status = str(game.get('status', '')).strip().lower()
    state = str(game.get('status_state', '')).strip().lower()
    if game.get('postponed') or status == 'postponed' or state == 'postponed':
        return 'postponed'
    if status in ('cancelled', 'canceled') or state in ('cancelled', 'canceled'):
        return 'cancelled'
    if status == 'final' and state in ('', 'final'):
        return 'final'
    return 'unknown'


def scoreboard(root, games, retrieved_at):
    retrieved = utc_timestamp(retrieved_at)
    by_id = {}
    for game in games:
        gid = str(positive_integer(game['id'], 'game ID'))
        if gid in by_id and game != by_id[gid]:
            raise ValueError('Conflicting result duplicates')
        by_id[gid] = game
    scored, counts = [], Counter()
    for gid, (row, identifier, bundle) in sorted(predictions(root).items()):
        if utc_timestamp(bundle['observed_at']) > retrieved:
            raise ValueError('Results observation precedes prediction archive')
        game = by_id.get(gid)
        state = 'missing' if game is None else result_state(game)
        item = dict(game_id=gid, date=row['date'], archive=identifier,
                    source_commit=bundle['source_commit'], status=state)
        if game is not None:
            if (str((game.get('home_team') or {}).get('id')) != row['home_team_id'] or
                    str((game.get('visitor_team') or {}).get('id')) != row['away_team_id']):
                state = 'identity_mismatch'
            elif state == 'final':
                try:
                    hs = positive_integer(game.get('home_team_score'), 'score')
                    av = positive_integer(game.get('visitor_team_score'), 'score')
                    # Rescheduled games with the same ID retain the original forecast.
                    actual_tip = utc_timestamp(game['datetime'])
                    if hs == av or actual_tip >= retrieved or utc_timestamp(bundle['observed_at']) >= actual_tip:
                        raise ValueError('Invalid final timing/score')
                except (ValueError, KeyError, TypeError):
                    state = 'invalid_final'
                else:
                    p, y = float(row['home_win_probability']), int(hs > av)
                    clipped = min(1-EPSILON, max(EPSILON, p))
                    item.update(home_win_probability=p, home_win=y,
                                correct=float((p >= .5) == bool(y)), brier=(p-y)**2,
                                log_loss=-(y*math.log(clipped)+(1-y)*math.log1p(-clipped)))
        item['status'] = state
        counts[state] += 1
        scored.append(item)
    finals = [x for x in scored if x['status'] == 'final']
    summary = dict(version='0.7', live_trading_enabled=False, retrieved_at=retrieved_at,
                   predicted=len(scored), scored=len(finals), statuses=dict(counts),
                   accuracy=None, brier=None, log_loss=None,
                   convention='One home-win Bernoulli per game; p=0.5 picks home; log loss clips at 1e-15')
    for metric, key in [('accuracy', 'correct'), ('brier', 'brier'), ('log_loss', 'log_loss')]:
        if finals:
            summary[metric] = sum(x[key] for x in finals) / len(finals)
    daily = {}
    for day in sorted({x['date'] for x in scored}):
        rows = [x for x in scored if x['date'] == day]
        done = [x for x in rows if x['status'] == 'final']
        daily[day] = dict(predicted=len(rows), scored=len(done),
                          statuses=dict(Counter(x['status'] for x in rows)))
        for metric, key in [('accuracy', 'correct'), ('brier', 'brier'), ('log_loss', 'log_loss')]:
            daily[day][metric] = sum(x[key] for x in done)/len(done) if done else None
    return dict(summary=summary, daily=daily, games=scored)


def get_result(key, gid):
    if not key:
        raise ValueError('BALLDONTLIE_API_KEY is missing')
    request = urllib.request.Request(BASE + '/' + str(positive_integer(gid, 'game ID')),
                                     headers={'Authorization': key, 'Accept': 'application/json'}, method='GET')
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            game = payload['data']
            if not isinstance(game, dict) or str(game['id']) != str(gid):
                raise ValueError('Malformed result response')
            return game
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError('BALLDONTLIE HTTP ' + str(error.code)) from None
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise RuntimeError('BALLDONTLIE unavailable') from None
        time.sleep(15 * (attempt + 1))


def verified_final(game, row, bundle, stamp, now):
    """Only identity-, score- and time-verified finals qualify for cache reuse."""
    try:
        observed = utc_timestamp(stamp)
        tip = utc_timestamp(game['datetime'])
        hs = positive_integer(game.get('home_team_score'), 'score')
        av = positive_integer(game.get('visitor_team_score'), 'score')
        return (result_state(game) == 'final' and hs != av
                and str(game['id']) == row['game_id']
                and str(game['home_team']['id']) == row['home_team_id']
                and str(game['visitor_team']['id']) == row['away_team_id']
                and utc_timestamp(bundle['observed_at']) < tip < observed <= now)
    except (ValueError, KeyError, TypeError):
        return False


def retrieve(root, key, *, fetch=get_result, pause=13, refresh_all=False,
             max_requests=60, max_seconds=1200):
    # Query IDs, not dates: postponements may move to another league date.
    selected = predictions(root)
    ids = sorted(selected, key=int)
    if min(max_requests, max_seconds, pause) < 0:
        raise ValueError('Budgets must be nonnegative')
    started = time.monotonic()
    games, observations, previous, attempts = [], {}, {}, {}
    now_dt = datetime.now(timezone.utc)
    # Final results are refreshed through seven days after tipoff, then frozen.
    # An explicit refresh-all can audit later provider corrections.
    for path in (Path(root) / 'results').glob('*.json'):
        raw = path.read_bytes()
        if digest(raw) != path.stem:
            raise ValueError('Result snapshot integrity failure')
        snapshot = json.loads(raw)
        for gid in snapshot.get('diagnostics', {}).get('attempted_ids', []):
            attempts[gid] = max(attempts.get(gid, ''), snapshot['retrieved_at'])
        for game in snapshot['games']:
            gid = str(game['id'])
            stamp = snapshot['observations'][gid]
            if gid not in previous or utc_timestamp(stamp) > utc_timestamp(previous[gid][1]):
                previous[gid] = game, stamp
    requests = 0
    diagnostics = dict(fetched=0, cached=0, deferred=0, upcoming=0, errors={}, attempted_ids=[])
    ids.sort(key=lambda gid: (attempts.get(gid, previous.get(gid, (None, '0001-01-01T00:00:00Z'))[1]), int(gid)))
    for gid in ids:
        cached, stamp = previous.get(gid, (None, None))
        frozen = False
        verified = cached is not None and verified_final(cached, selected[gid][0], selected[gid][2], stamp, now_dt)
        if verified and not refresh_all:
            try:
                frozen = utc_timestamp(cached['datetime']) + timedelta(days=7) <= utc_timestamp(stamp) <= now_dt
            except (KeyError, ValueError, TypeError):
                pass
        fresh = verified and not refresh_all and now_dt - utc_timestamp(stamp) < timedelta(hours=24)
        future = not refresh_all and utc_timestamp(selected[gid][0]['tipoff_utc']) > now_dt
        game = cached
        if future:
            diagnostics['upcoming'] += 1
        elif frozen or fresh:
            diagnostics['cached'] += 1
        elif requests >= max_requests or time.monotonic()-started + (pause if requests else 0) + 210 > max_seconds:
            # Reserve four 30-second timeouts and retry backoffs before starting.
            diagnostics['deferred'] += 1
        else:
            if requests:
                time.sleep(pause)
            requests += 1
            diagnostics['attempted_ids'].append(gid)
            try:
                fetched = fetch(key, gid)
                if fetched is not None:
                    if str(fetched.get('id')) != gid:
                        raise ValueError('Result ID mismatch')
                    game = fetched
                    stamp = datetime.now(timezone.utc).isoformat()
                else:
                    diagnostics['errors'][gid] = 'not_found'
                diagnostics['fetched'] += 1
            except (RuntimeError, OSError, ValueError, KeyError, TypeError) as error:
                # Fallback retains its original source observation timestamp.
                diagnostics['errors'][gid] = type(error).__name__
            print(json.dumps(dict(result_progress=gid, requests=requests,
                                  errors=len(diagnostics['errors']))), flush=True)
        if game is not None:
            games.append(game)
            observations[gid] = stamp
    now = datetime.now(timezone.utc).isoformat()
    diagnostics.update(requests=requests, max_requests=max_requests, max_seconds=max_seconds)
    raw = encode(dict(endpoint=BASE, retrieved_at=now, requested_ids=ids, games=games,
                      observations=observations, refresh_all=refresh_all, diagnostics=diagnostics))
    immutable(Path(root) / 'results' / (digest(raw) + '.json'), raw)
    report = scoreboard(root, games, now)
    report['result_snapshot_sha256'] = digest(raw)
    report['result_observations'] = observations
    report['retrieval'] = diagnostics
    report['summary']['partial_refresh'] = bool(diagnostics['errors'] or diagnostics['deferred'])
    return report


def markdown(report):
    s = report['summary']
    def number(value):
        return 'pending' if value is None else f'{value:.6f}'
    lines = ['# NBA v0.7 Forward Testing', '', 'RESEARCH_ONLY_NO_TRADING', '',
             f"Results checked: {s['retrieved_at']}", '',
             '| NBA date | Archived | Scored | Accuracy | Brier | Log loss |',
             '|---|---:|---:|---:|---:|---:|']
    if 'retrieval' in report:
        r = report['retrieval']
        lines[6:6] = [f"Refresh: {r['requests']} requests; {r['cached']} reused; {r['deferred']} deferred; {len(r['errors'])} errors. Cached source timestamps are retained.", '']
    for day, row in report['daily'].items():
        lines.append(f"| {day} | {row['predicted']} | {row['scored']} | {number(row['accuracy'])} | {number(row['brier'])} | {number(row['log_loss'])} |")
    lines += ['', 'Unresolved games are excluded from all metric denominators.', '',
              '| Game ID | NBA date | Status |', '|---|---|---|']
    lines.extend(f"| {x['game_id']} | {x['date']} | {x['status']} |" for x in report['games'])
    return '\n'.join(lines) + '\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', default='forward_test/state')
    sub = p.add_subparsers(dest='command', required=True)
    b = sub.add_parser('baseline')
    b.add_argument('--zip', default='forward_test/baseline/artifact.zip')
    a = sub.add_parser('archive')
    a.add_argument('--csv', required=True)
    a.add_argument('--commit', required=True)
    a.add_argument('--run-id', required=True)
    score = sub.add_parser('score')
    score.add_argument('--refresh-all', action='store_true')
    score.add_argument('--max-requests', type=int, default=60)
    score.add_argument('--max-seconds', type=int, default=1200)
    args = p.parse_args()
    if args.command == 'baseline':
        print(import_baseline(args.zip, args.root))
    elif args.command == 'archive':
        path = Path(args.csv)
        snapshots = {n: (path.parent / n).read_bytes() for n in ('history.json', 'schedule.json')}
        print(archive(path.read_bytes(), path.with_suffix('.json').read_bytes(), args.root,
                      commit=args.commit, run_id=args.run_id,
                      observed_at=datetime.now(timezone.utc).isoformat(), snapshots=snapshots))
    else:
        report = retrieve(args.root, os.environ.get('BALLDONTLIE_API_KEY', ''), refresh_all=args.refresh_all, max_requests=args.max_requests, max_seconds=args.max_seconds)
        path = Path(args.root) / 'scoreboard.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(encode(report))
        temporary.replace(path)
        path.with_suffix('.md').write_text(markdown(report), encoding='utf-8')
        print(json.dumps(dict(summary=report['summary'], retrieval=report['retrieval']), indent=2))


if __name__ == '__main__':
    main()
