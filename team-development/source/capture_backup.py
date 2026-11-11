"""One-cutoff outage backup. Real future seals only; never automatically admitted."""
import argparse
import hashlib
import json
import math
import subprocess
import sys
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORE = ROOT.parent/'nba_collection_work'
sys.path[:0] = [str(CORE), str(CORE/'.test-deps')]
from nba_forward_test import encode, immutable, predictions
from nba_v09_challenger import history, sha, save
from nba_team_development import supervise
from nba_team_inventory import inventory
from nba_v09_prospective import capture_schedule, game_record, market_get
from nba_v08_schedule import verify, ESPN_IDS
from nba_v08_valuation import timestamp

HISTORY = ROOT/'team-history-runs/43081899525-1/team-history'
OUTPUT = ROOT/'backup-evidence'
SOURCE = OUTPUT/'source'


def prepare():
    now = datetime.now(timezone.utc)
    with tarfile.open(ROOT.parent/'nba-local-backup-history.tar') as archive:
        archive.extractall(ROOT, filter='data')
    finals = history(HISTORY, now.isoformat())
    forecasts = predictions(CORE/'forward_test/state')
    refs = [(r,d,b) for r,d,b in forecasts.values() if r['date']=='2026-11-11']
    bundles = {d for _,d,_ in refs}
    if len(bundles) != 1 or len(refs) != 10:
        raise ValueError('Unexpected authentic target archive')
    digest = bundles.pop()
    bundle_root = CORE/'forward_test/state/predictions'/digest
    raw = (bundle_root/'schedule.json').read_bytes()
    manifest = json.loads((bundle_root/'manifest.json').read_bytes())
    if hashlib.sha256(raw).hexdigest() != manifest['snapshots']['schedule.json']:
        raise ValueError('Original fixture digest')
    games = json.loads(raw)
    immutable(SOURCE/'original-provider-schedule.json', raw)
    immutable(SOURCE/'original-provider-manifest.json', (bundle_root/'manifest.json').read_bytes())
    independent = []
    for day in ('2026-11-11', '2026-11-12'):
        schedule = json.loads(capture_schedule(day, SOURCE/'schedules').read_bytes())
        for event in schedule['payload']['events']:
            row = dict(event_id=str(event['id']), date=day, tipoff_utc=event.get('date'), provider_ids=[])
            try:
                sides = {x['homeAway']:str(x['team']['id']) for x in event['competitions'][0]['competitors']}
                for g in games:
                    r = game_record(g, now)
                    if (r['date']==day and str(ESPN_IDS.get(r.get('home_team')))==sides['home']
                        and str(ESPN_IDS.get(r.get('away_team')))==sides['away']
                        and abs((timestamp(g['datetime'])-timestamp(event['date'])).total_seconds())<=60):
                        row['provider_ids'].append(g['id'])
            except (KeyError, ValueError, TypeError):
                pass
            independent.append(row)
            if len(row['provider_ids']) != 1:
                games.append(dict(id='espn:'+row['event_id'], date=day))
    immutable(SOURCE/'targets.json', encode(games))
    obj = dict(prepared_at=now.isoformat(), original_provider_bundle=digest,
               original_provider_observed_at=manifest['observed_at'],
               provider_source='authentic_legacy_fixture_snapshot_no_pagination_claim',
               independent_games=independent, targets_sha256=sha(games),
               code_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=CORE,text=True).strip(),
               history_archive_commit=subprocess.check_output(['git','rev-parse','refs/remotes/origin/team-history-backup'],cwd=CORE,text=True).strip(),
               verified_history_finals=len(finals), admitted_to_cohort=False,
               priority='cloud_primary_local_backup_only', no_trade=True, live_trading=False)
    immutable(SOURCE/'provenance.json', encode(obj))
    print(json.dumps(obj, sort_keys=True), flush=True)


def run():
    provenance = json.loads((SOURCE/'provenance.json').read_bytes())
    games = json.loads((SOURCE/'targets.json').read_bytes())
    if sha(games) != provenance['targets_sha256']:
        raise ValueError('Changed backup universe')
    launched = datetime.now(timezone.utc)
    future = [timestamp(g['datetime'])-timedelta(hours=1) for g in games if 'datetime' in g]
    first = min(future)
    budget = min(14400, max(0, math.ceil((first-launched).total_seconds())+120))
    with (OUTPUT/'worker-claim.json').open('x') as f:
        json.dump(dict(started_at=launched.isoformat(), max_wait_seconds=budget, admitted=False),f)
    schedules = {}

    def preflight(g):
        now = datetime.now(timezone.utc)
        day = g['date'][:10]
        if day not in schedules or (now-timestamp(schedules[day]['requested_at'])).total_seconds()>120:
            schedules[day] = json.loads(capture_schedule(day,SOURCE/'fresh-schedules').read_bytes())
        verify(game_record(g,now), schedules[day], datetime.now(timezone.utc))

    print(json.dumps(dict(stage='waiting_for_real_cutoff', launched_at=launched.isoformat(),
                         first_cutoff=first.isoformat(), budget_seconds=budget, admitted=False)),flush=True)
    rows = supervise(HISTORY,games,CORE/'forward_test/state',OUTPUT,launched_at=launched,
                     max_wait=budget,preflight=preflight)
    result = dict(completed_at=datetime.now(timezone.utc).isoformat(), coverage=rows,
                  admitted_to_cohort=False, no_trade=True, live_trading=False)
    immutable(OUTPUT/'result.json', encode(result))
    report = inventory(HISTORY, OUTPUT, CORE/'forward_test/state')
    immutable(OUTPUT/'inventory.json', encode(report))
    print(json.dumps(result,sort_keys=True),flush=True)
    print(json.dumps(report,sort_keys=True),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase',choices=('prepare','supervise'),required=True)
    a=p.parse_args()
    prepare() if a.phase=='prepare' else run()
