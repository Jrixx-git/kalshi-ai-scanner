"""Bounded prospective development collection; no fitting or trading entry point."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
import time
import os
import re
from nba_v09_challenger import seal_input, collect_history, save, sha
from nba_v09_prospective import collect, active, STOP
from nba_v08_valuation import timestamp
from nba_forward_test import immutable, encode


def targets(root):
    root = Path(root)
    found = {}
    for path in sorted((root/'universe').glob('*.json')):
        obj = json.loads(path.read_bytes())
        if path.stem != sha(obj) or obj.get('pagination_complete') is not True:
            raise ValueError('Universe integrity/completeness')
        for game in obj['games']:
            if str(game['id']) in found:
                raise ValueError('Duplicate provider target')
            found[str(game['id'])] = game
    for path in sorted((root/'runs').glob('*.json')):
        obj = json.loads(path.read_bytes())
        if path.stem != sha(obj):
            raise ValueError('Universe run integrity')
        for event in obj['independent_games']:
            if event['status'] != 'identity_matched':
                gid = 'espn:'+event['event_id']
                found[gid] = dict(id=gid, date=event['date'])
    return list(found.values())


def supervise(history, games, operational, output, *, launched_at, max_wait=3600,
              clock=None, sleep=time.sleep, monotonic=time.monotonic, seal=seal_input,
              preflight=None):
    """Use actual wall time for seals and monotonic time only for the wait budget."""
    if not 0 <= max_wait <= 14400:
        raise ValueError('Wait budget must be 0..14400 seconds')
    clock = clock or (lambda: datetime.now(timezone.utc))
    started = clock()
    deadline = monotonic() + max_wait
    horizon = min(started + timedelta(seconds=max_wait), STOP)
    rows, groups = [], {}

    def record(t, reason, **extra):
        row = dict(game_id=str(t['id']), reason=reason, observed_at=clock().isoformat(),
                   launched_at=launched_at.isoformat(), no_trade=True, **extra)
        save(output, 'coverage', row)
        rows.append(row)

    for t in games:
        try:
            due = timestamp(t['datetime']) - timedelta(hours=1)
            if 'home_team' not in t:
                raise KeyError('identity')
        except (KeyError, ValueError, TypeError):
            record(t, 'independent_only_or_unknown_identity')
            continue
        if (Path(output)/'inputs'/(str(t['id'])+'.json')).exists():
            record(t, 'already_sealed')
        elif launched_at >= due or started > due + timedelta(seconds=30):
            record(t, 'missed_cutoff', cutoff=due.isoformat())
        elif due >= horizon:
            record(t, 'outside_worker_horizon', cutoff=due.isoformat())
        else:
            groups.setdefault(due, []).append(t)
    for due, group in sorted(groups.items()):
        check_at = due - timedelta(seconds=90)
        while clock() < check_at and monotonic() < deadline and active(clock()):
            sleep(min(5, (check_at-clock()).total_seconds(), max(0, deadline-monotonic())))
        allowed = []
        for t in group:
            if monotonic() >= deadline or not active(clock()):
                record(t, 'worker_budget_or_window_expired', cutoff=due.isoformat())
                continue
            try:
                if preflight is not None:
                    preflight(t)
                allowed.append(t)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                record(t, 'fresh_schedule_unverified', error_type=type(exc).__name__)
        while clock() < due and monotonic() < deadline and active(clock()):
            sleep(min(5, (due-clock()).total_seconds(), max(0, deadline-monotonic())))
        for t in allowed:
            if clock() < due or monotonic() >= deadline or not active(clock()):
                record(t, 'worker_budget_or_window_expired', cutoff=due.isoformat())
                continue
            try:
                row = seal(history, t, operational, output)
                record(t, 'sealed', baseline_available=row['elo'] is not None,
                       complete_features=all(v is not None for v in row['features']['x']),
                       sealed_at=row['sealed_at'])
            except (ValueError, KeyError, OSError, TypeError) as exc:
                # Exception text may include provider data or credentials.
                record(t, 'seal_failed', error_type=type(exc).__name__, cutoff=due.isoformat())
    return rows


def prepare(history, output, *, max_wait=3600):
    if not 0 <= max_wait <= 14400:
        raise ValueError('Wait budget must be 0..14400 seconds')
    launched = datetime.now(timezone.utc)
    if not active(launched):
        raise ValueError('Outside approved collection window')
    root = Path(output)
    slot = launched.strftime('%Y%m%dT%H')
    claim = root/'slots'/slot/'claim.json'
    claim.parent.mkdir(parents=True, exist_ok=True)
    # A durable restored claim suppresses reruns, including failed partial runs.
    with claim.open('x') as f:
        json.dump(dict(started_at=launched.isoformat(), stop_at=STOP.isoformat(),
                       no_trade=True, max_wait_seconds=max_wait), f)
    evidence = claim.parent
    errors = {}
    for season in (2025, 2026):
        try:
            collect_history(history, season, max_pages=20)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            errors['history-'+str(season)] = type(exc).__name__
    # Provider failure never removes the independent universe from the receipt.
    sources = collect(evidence/'source')
    games = targets(evidence/'source')
    print(json.dumps(dict(stage='supervising', slot=slot, actual_at=datetime.now(timezone.utc).isoformat(),
          targets=[dict(id=str(t['id']), tipoff=t.get('datetime')) for t in games],
          source_errors=sources['source_errors'], history_errors=errors)), flush=True)
    plan = dict(launched_at=launched.isoformat(), slot=slot, history_errors=errors,
                source_errors=sources['source_errors'], max_wait_seconds=max_wait,
                source_targets_sha256=sha(games), no_trade=True)
    immutable(evidence/'plan.json', encode(plan))
    return slot


def schedule_verifier(output, *, clock=None, fetch=None):
    from nba_v09_prospective import capture_schedule, game_record
    from nba_v08_schedule import verify
    clock = clock or (lambda: datetime.now(timezone.utc))
    fetch = fetch or capture_schedule
    schedules, requests = {}, 0

    def check(t):
        nonlocal requests
        day = t['date'][:10]
        now = clock()
        if day not in schedules or (now-timestamp(schedules[day]['requested_at'])).total_seconds() > 120:
            if requests >= 12:
                raise ValueError('Fresh schedule request budget')
            requests += 1
            schedules[day] = json.loads(fetch(day, Path(output)/'fresh-schedules').read_bytes())
        # The response cannot be verified against a time sampled before its
        # receipt. Refresh the clock after network I/O, including the first game.
        now = clock()
        verify(game_record(t, now), schedules[day], now)

    return check


def resume(history, output, slot, *, operational='forward_test/state'):
    if not re.fullmatch(r'\d{8}T\d{2}', slot):
        raise ValueError('Invalid slot')
    root = Path(output)
    evidence = root/'slots'/slot
    plan = json.loads((evidence/'plan.json').read_bytes())
    launched = timestamp(plan['launched_at'])
    max_wait = plan['max_wait_seconds']
    if not active(datetime.now(timezone.utc)) or not 0 <= max_wait <= 14400:
        raise ValueError('Expired worker or invalid budget')
    games = targets(evidence/'source')
    if plan['source_targets_sha256'] != sha(games):
        raise ValueError('Prepared universe changed')
    # A worker cannot be resumed twice, even after an incomplete attempt.
    with (evidence/'worker-claim.json').open('x') as f:
        json.dump(dict(started_at=datetime.now(timezone.utc).isoformat(), no_trade=True), f)
    rows = supervise(history, games, operational, root,
                     launched_at=launched, max_wait=max_wait, preflight=schedule_verifier(evidence))
    report = dict(schema='nba-team-development-run-v1', launched_at=launched.isoformat(),
                  completed_at=datetime.now(timezone.utc).isoformat(), slot=slot,
                  source_errors=plan['source_errors'], history_errors=plan['history_errors'],
                  coverage=rows, no_trade=True, live_trading=False)
    immutable(evidence/'result.json', encode(report))
    print(json.dumps(report, sort_keys=True))
    return report


def run(history, output, *, max_wait=3600, operational='forward_test/state'):
    slot = prepare(history, output, max_wait=max_wait)
    return resume(history, output, slot, operational=operational)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--history', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--operational', default='forward_test/state')
    p.add_argument('--max-wait-seconds', type=int, default=3600, choices=range(0,14401))
    p.add_argument('--phase', choices=('all', 'prepare', 'supervise'), default='all')
    p.add_argument('--slot')
    a = p.parse_args()
    if a.phase == 'prepare':
        slot = prepare(a.history, a.output, max_wait=a.max_wait_seconds)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
                f.write('slot='+slot+'\n')
    elif a.phase == 'supervise':
        if not a.slot:
            p.error('--slot required for supervise')
        resume(a.history, a.output, a.slot, operational=a.operational)
    else:
        run(a.history, a.output, max_wait=a.max_wait_seconds, operational=a.operational)
