"""Team-only, receipt-time NBA research. No orders or paper-ledger integration."""
import argparse
import hashlib
import json
import math
import os
from datetime import date, datetime, timezone
from pathlib import Path
from nba_forward_test import encode, immutable
from nba_v08_valuation import timestamp

VERSION = 'nba-team-offset-v1'
# BALLDONTLIE NBA identities, in provider ID order. Never infer IDs from names.
TEAMS = 'ATL BOS BKN CHA CHI CLE DAL DEN DET GSW HOU IND LAC LAL MEM MIA MIL MIN NOP NYK OKC ORL PHI PHX POR SAC SAS TOR UTA WAS'.split()
FIELDS = ('rest', 'b2b', 'margin5', 'win5', 'margin10', 'win10', 'venue20')
POLICY = dict(version=VERSION, l2=0.1, iterations=2000, step=0.1,
              min_train=100, min_validation=30, missing='abstain',
              injuries='unknown_excluded', elo_temperature=1.23)


def sha(obj):
    return hashlib.sha256(encode(obj)).hexdigest()


def save(root, kind, obj):
    p = Path(root) / kind / (sha(obj) + '.json')
    immutable(p, encode(obj))
    return p


def identity(team):
    i = team['id']
    if type(i) is not int or not 1 <= i <= 30 or team['abbreviation'] != TEAMS[i-1]:
        raise ValueError('Unverified BALLDONTLIE identity')
    return i


def final(g):
    h, a = identity(g['home_team']), identity(g['visitor_team'])
    hs, aw = g['home_team_score'], g['visitor_team_score']
    if (g['status'] != 'Final' or h == a or type(g['id']) is not int or g['id'] <= 0
            or any(type(s) is not int or s <= 0 for s in (hs, aw)) or hs == aw):
        raise ValueError('Unverified final game')
    d = date.fromisoformat(g['date'][:10])
    return dict(game_id=g['id'], date=d.isoformat(), home=h, away=a, hs=hs, aw=aw)


def collect_history(root, season, *, max_pages=20, fetch=None, clock=None):
    """Archive exact response bytes before parsing. Page ceiling fails closed."""
    import urllib.request
    import urllib.parse
    from nba_v09_injuries import NoRedirect
    clock = clock or (lambda: datetime.now(timezone.utc))
    key = os.environ.get('BALLDONTLIE_API_KEY', '')
    if fetch is None and not key:
        raise ValueError('BALLDONTLIE_API_KEY unavailable; no collection attempted')
    if not 1 <= max_pages <= 30:
        raise ValueError('Page budget must be 1..30')
    def network(url):
        req = urllib.request.Request(url, headers={'Authorization': key, 'Accept': 'application/json'})
        with urllib.request.build_opener(NoRedirect).open(req, timeout=15) as r:
            raw = r.read(8*1024*1024+1)
        if len(raw) > 8*1024*1024:
            raise ValueError('History byte budget')
        return raw
    fetch = fetch or network
    cursor, seen, pages = None, set(), []
    for _ in range(max_pages):
        params = [('seasons[]', str(int(season))), ('per_page', '100')]
        if cursor is not None:
            params.append(('cursor', str(cursor)))
        url = 'https://api.balldontlie.io/v1/games?' + urllib.parse.urlencode(params)
        start = clock().isoformat()
        raw = fetch(url)
        end = clock().isoformat()
        if key and key.encode() in raw:
            raise ValueError('Credential echo refused before archival')
        digest = hashlib.sha256(raw).hexdigest()
        immutable(Path(root)/'raw'/digest, raw)
        receipt = dict(schema='bdl-team-history-v1', source=url, requested_at=start,
                       received_at=end, raw_sha256=digest)
        p = save(root, 'receipts', receipt)
        pages.append(p.name)
        payload = json.loads(raw)
        if not isinstance(payload.get('data'), list) or 'meta' not in payload:
            raise ValueError('Malformed history page')
        nxt = payload['meta'].get('next_cursor')
        if nxt is None:
            return save(root, 'collections', dict(pages=pages, complete=True, season=season))
        if nxt in seen:
            raise ValueError('Repeated history cursor')
        seen.add(nxt)
        cursor = nxt
    raise ValueError('History page ceiling: partial raw evidence retained')


def history(root, cutoff):
    """First observed final wins, later corrections cannot replace it."""
    cutoff = timestamp(cutoff)
    complete_pages = set()
    for p in (Path(root)/'collections').glob('*.json'):
        manifest = json.loads(p.read_bytes())
        if p.stem != sha(manifest) or manifest.get('complete') is not True:
            raise ValueError('Collection manifest integrity')
        eligible = True
        collection_games = set()
        for name in manifest['pages']:
            if Path(name).name != name:
                raise ValueError('Invalid page reference')
            page = Path(root)/'receipts'/name
            receipt = json.loads(page.read_bytes())
            if page.stem != sha(receipt):
                raise ValueError('Receipt digest mismatch')
            if timestamp(receipt['received_at']) > cutoff:
                eligible = False
            raw = (Path(root)/'raw'/receipt['raw_sha256']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != receipt['raw_sha256']:
                raise ValueError('Raw history digest mismatch')
            for g in json.loads(raw)['data']:
                gid = g['id']
                if gid in collection_games:
                    raise ValueError('Duplicate game within collection')
                collection_games.add(gid)
        if eligible:
            complete_pages.update(manifest['pages'])
    receipts = []
    for p in (Path(root)/'receipts').glob('*.json'):
        if p.name not in complete_pages:
            continue
        obj = json.loads(p.read_bytes())
        if p.stem != sha(obj) or obj['schema'] != 'bdl-team-history-v1':
            raise ValueError('Receipt digest/schema mismatch')
        if not obj['source'].startswith('https://api.balldontlie.io/v1/games?'):
            raise ValueError('Unexpected history source')
        start, end = timestamp(obj['requested_at']), timestamp(obj['received_at'])
        if start > end:
            raise ValueError('Reversed receipt')
        if end <= cutoff:
            receipts.append((end, p.stem, obj))
    games = {}
    for end, digest, r in sorted(receipts):
        raw = (Path(root)/'raw'/r['raw_sha256']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != r['raw_sha256']:
            raise ValueError('Raw history digest mismatch')
        local = set()
        for g in json.loads(raw)['data']:
            if g.get('status') != 'Final':
                continue
            row = final(g)
            if row['game_id'] in local:
                raise ValueError('Duplicate game in history page')
            local.add(row['game_id'])
            row.update(received_at=end.isoformat(), receipt_sha256=digest)
            old = games.get(row['game_id'])
            if old and (old['home'], old['away'], old['date']) != (row['home'], row['away'], row['date']):
                raise ValueError('Game identity changed')
            games.setdefault(row['game_id'], row)
    return sorted(games.values(), key=lambda x: (x['date'], x['game_id']))


def features(root, target, cutoff):
    from nba_daily_predictions import EASTERN
    h, a = identity(target['home_team']), identity(target['visitor_team'])
    day = date.fromisoformat(target['date'][:10])
    if (h == a or type(target['id']) is not int or target['id'] <= 0 or timestamp(cutoff) >= timestamp(target['datetime'])
            or timestamp(target['datetime']).astimezone(EASTERN).date() != day):
        raise ValueError('Invalid target identity/cutoff')
    rows = [g for g in history(root, cutoff) if g['date'] < day.isoformat() and g['game_id'] != target['id']]
    season = day.year if day.month >= 10 else day.year-1
    covered = False
    for p in (Path(root)/'collections').glob('*.json'):
        manifest = json.loads(p.read_bytes())
        if manifest['season'] == season and all(timestamp(json.loads(
                (Path(root)/'receipts'/name).read_bytes())['received_at']) <= timestamp(cutoff)
                for name in manifest['pages']):
            covered = True
    if not covered:
        rows = []
    def team(t, home):
        past = [g for g in rows if t in (g['home'], g['away'])]
        margins = [(g['hs']-g['aw'])*(1 if g['home'] == t else -1) for g in past]
        delta = (day-date.fromisoformat(past[-1]['date'])).days if past else None
        out = dict(rest=min(delta, 7) if delta is not None else None,
                   b2b=int(delta == 1) if delta is not None else None, n=len(past), home=int(home))
        for n in (5, 10):
            out['n'+str(n)] = min(n, len(past))
            out['margin'+str(n)] = sum(margins[-n:])/n if len(past) >= n else None
            out['win'+str(n)] = sum(m > 0 for m in margins[-n:])/n if len(past) >= n else None
        venue = [g for g in past if (g['home'] == t) == home][-20:]
        out['venue_n'] = len(venue)
        out['venue20'] = (sum((g['hs'] > g['aw']) == home for g in venue)/20 if len(venue) == 20 else None)
        return out
    home, away = team(h, True), team(a, False)
    x = [home[k]-away[k] if home[k] is not None and away[k] is not None else None for k in FIELDS]
    return dict(version=VERSION, game_id=target['id'], date=day.isoformat(), cutoff=cutoff,
                history_coverage='current_season_archived' if covered else 'missing_current_season_archive',
                home=home, away=away, x=x, history_sha256=sha(rows),
                receipts=sorted({g['receipt_sha256'] for g in rows}), injuries='unknown_excluded')


def probability(offset, x, model):
    z = math.log(offset/(1-offset)) + sum(w*(v-m)/s for w,v,m,s in
        zip(model['weights'], x, model['means'], model['scales']))
    return 1/(1+math.exp(-max(-35, min(35, z))))


def _fit(rows, *, freeze_at, validation_start):
    """Fixed L2; train-only scaling; holdout never refitted. Input is sealed research rows."""
    freeze, split = timestamp(freeze_at), timestamp(validation_start)
    if split >= freeze or freeze > datetime.now(timezone.utc):
        raise ValueError('Validation must precede freeze')
    ordered = sorted(rows, key=lambda r: (r['features']['date'], r['features']['game_id']))
    seen, train_rows, val_rows = set(), [], []
    for r in ordered:
        f = r['features']
        gid = f['game_id']
        if gid in seen:
            raise ValueError('Duplicate training game')
        seen.add(gid)
        cutoff, tip, outcome_at = map(timestamp, (f['cutoff'], r['tipoff_utc'], r['outcome_received_at']))
        if (f['version'] != VERSION or not cutoff < tip < outcome_at <= freeze
                or r['outcome'] not in (0, 1) or not 0 < r['elo'] < 1
                or r.get('baseline_verified') is not True or r.get('feature_verified') is not True):
            raise ValueError('Unverified/as-of training evidence')
        if any(v is None for v in f['x']):
            continue
        if len(f['x']) != len(FIELDS) or not all(math.isfinite(v) for v in f['x']):
            raise ValueError('Invalid features')
        if tip < split:
            if outcome_at >= split:
                raise ValueError('Training result unavailable at validation start')
            train_rows.append(r)
        else:
            val_rows.append(r)
    if len(train_rows) < POLICY['min_train'] or len(val_rows) < POLICY['min_validation']:
        raise ValueError('Insufficient verified as-of train/validation rows (100/30 required)')
    n = len(train_rows)
    means = [sum(r['features']['x'][j] for r in train_rows)/n for j in range(len(FIELDS))]
    scales = [math.sqrt(sum((r['features']['x'][j]-means[j])**2 for r in train_rows)/n) or 1 for j in range(len(FIELDS))]
    model = dict(version=VERSION, policy=POLICY.copy(), fields=FIELDS, weights=[0.]*len(FIELDS),
                 implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 means=means, scales=scales, freeze_at=freeze_at, validation_start=validation_start,
                 training_first_date=train_rows[0]['features']['date'], training_last_date=train_rows[-1]['features']['date'],
                 training_sha256=sha(ordered), n_train=n, n_validation=len(val_rows))
    for _ in range(POLICY['iterations']):
        grad = [POLICY['l2']*w for w in model['weights']]
        for r in train_rows:
            x = r['features']['x']
            err = probability(r['elo'], x, model)-r['outcome']
            for j in range(len(FIELDS)):
                grad[j] += err*(x[j]-means[j])/scales[j]/n
        model['weights'] = [w-POLICY['step']*g for w,g in zip(model['weights'],grad)]
    model['validation'] = {}
    for label in ('elo', 'challenger'):
        ps = [r['elo'] if label == 'elo' else probability(r['elo'], r['features']['x'], model) for r in val_rows]
        model['validation'][label] = dict(brier=sum((p-r['outcome'])**2 for p,r in zip(ps,val_rows))/len(ps),
            log_loss=-sum(r['outcome']*math.log(p)+(1-r['outcome'])*math.log(1-p) for p,r in zip(ps,val_rows))/len(ps))
    model['model_sha256'] = sha(model)
    return model


def verify_model(model):
    body = {k:v for k,v in model.items() if k != 'model_sha256'}
    if (model['model_sha256'] != sha(body) or model['version'] != VERSION or model['policy'] != POLICY
            or model['implementation_sha256'] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()):
        raise ValueError('Frozen model mismatch')


def baseline(operational_root, target, cutoff):
    from nba_forward_test import predictions
    item = predictions(operational_root).get(str(target['id']))
    if item is None:
        return None, None
    row, digest, bundle = item
    if (timestamp(bundle['observed_at']) > timestamp(cutoff)
            or timestamp(row['generated_at_utc']) > timestamp(cutoff)
            or timestamp(row['tipoff_utc']) != timestamp(target['datetime'])
            or row['date'] != target['date'][:10]
            or int(row['home_team_id']) != identity(target['home_team'])
            or int(row['away_team_id']) != identity(target['visitor_team'])
            or float(row['calibration_temperature']) != 1.23):
        raise ValueError('Operational baseline identity/as-of mismatch')
    p = float(row['home_win_probability'])
    if not 0 < p < 1:
        raise ValueError('Invalid operational probability')
    return p, digest


def seal_input(root, target, operational_root, output, *, clock=None, purpose='development'):
    """Accumulate pregame training inputs without inventing a trained model."""
    clock = clock or (lambda: datetime.now(timezone.utc))
    if purpose not in ('development','evaluation'):
        raise ValueError('Unknown input purpose')
    start = clock()
    tip = timestamp(target['datetime'])
    if not 3570 <= (tip-start).total_seconds() <= 3600:
        raise ValueError('Outside 60-minute feature sealing window')
    from nba_daily_predictions import lifecycle
    if target.get('period') != 0 or lifecycle(target) != 'scheduled':
        raise ValueError('Not verified pregame')
    f = features(root, target, start.isoformat())
    elo, archive = baseline(operational_root, target, start.isoformat())
    end = clock()
    if not start <= end < tip or (end-start).total_seconds() > 30:
        raise ValueError('Input sealing latency')
    row = dict(schema='nba-team-input-v1', target=target, features=f, elo=elo,
               purpose=purpose,
               baseline_archive=archive, sealed_at=end.isoformat(), no_trade=True,
               live_trading=False)
    immutable(Path(output)/'inputs'/(str(target['id'])+'.json'), encode(row))
    return row


def train(root, inputs, operational_root, output, *, freeze_at, validation_start):
    """Verify sealed raw-derived inputs and final receipts before fitting/freezing."""
    results = {r['game_id']:r for r in history(root, freeze_at)}
    rows = []
    for path in sorted((Path(inputs)/'inputs').glob('*.json')):
        r = json.loads(path.read_bytes())
        if r.get('purpose') == 'evaluation':
            continue
        if r.get('purpose') != 'development':
            raise ValueError('Unspecified development cohort')
        t, f = r['target'], r['features']
        if (path.stem != str(t['id']) or r['schema'] != 'nba-team-input-v1'
                or r['no_trade'] is not True or r['live_trading'] is not False
                or not timestamp(f['cutoff']) <= timestamp(r['sealed_at']) < timestamp(t['datetime'])
                or (timestamp(r['sealed_at'])-timestamp(f['cutoff'])).total_seconds() > 30
                or not 3570 <= (timestamp(t['datetime'])-timestamp(f['cutoff'])).total_seconds() <= 3600
                or f != features(root, t, f['cutoff'])):
            raise ValueError('Sealed input verification failed')
        p, archive = baseline(operational_root, t, f['cutoff'])
        if (p, archive) != (r['elo'], r['baseline_archive']):
            raise ValueError('Baseline changed')
        result = results.get(t['id'])
        if result is None or p is None:
            continue
        if (result['home'],result['away'],result['date']) != (identity(t['home_team']),identity(t['visitor_team']),t['date'][:10]):
            raise ValueError('Training outcome identity mismatch')
        rows.append(dict(features=f, elo=p, outcome=int(result['hs'] > result['aw']),
                         tipoff_utc=t['datetime'], outcome_received_at=result['received_at'],
                         baseline_verified=True, feature_verified=True))
    model = _fit(rows, freeze_at=freeze_at, validation_start=validation_start)
    # A supplied data cutoff never backdates the actual model freeze.
    model['training_cutoff_at'] = freeze_at
    model['freeze_at'] = datetime.now(timezone.utc).isoformat()
    del model['model_sha256']
    model['model_sha256'] = sha(model)
    save(output, 'models', model)
    return model


def shadow(root, target, cutoff, model, operational_root, output):
    """Explicit abstention persists; one immutable forecast per model/game."""
    verify_model(model)
    from nba_daily_predictions import lifecycle
    if target.get('period') != 0 or lifecycle(target) != 'scheduled':
        raise ValueError('Not verified pregame')
    now = datetime.now(timezone.utc)
    if not timestamp(model['freeze_at']) <= timestamp(cutoff) <= now < timestamp(target['datetime']):
        raise ValueError('Freeze/cutoff/actual receipt/tip ordering')
    # Do not backdate a feature build. Caller supplies its actual decision time.
    if (now-timestamp(cutoff)).total_seconds() > 30:
        raise ValueError('Retrospective shadow forecast refused')
    f = features(root, target, cutoff)
    elo, archive = baseline(operational_root, target, cutoff)
    reasons = []
    if any(v is None for v in f['x']):
        reasons.append('insufficient_team_history')
    if elo is None:
        reasons.append('missing_verified_operational_elo')
    elif not 0 < elo < 1:
        raise ValueError('Invalid baseline probability')
    sealed = datetime.now(timezone.utc)
    if (not 3570 <= (timestamp(target['datetime'])-timestamp(cutoff)).total_seconds() <= 3600
            or not sealed < timestamp(target['datetime']) or (sealed-timestamp(cutoff)).total_seconds() > 30):
        raise ValueError('Outside preregistered cutoff')
    row = dict(schema='nba-team-shadow-v1', features=f, target=target, baseline_archive=archive,
               model_sha256=model['model_sha256'],
               sealed_at=sealed.isoformat(), elo=elo, challenger=None, market=None,
               reasons=reasons+['market_not_yet_paired'], no_trade=True, live_trading=False)
    if not reasons:
        row['challenger'] = probability(elo, f['x'], model)
    path = Path(output)/model['model_sha256']/(str(target['id'])+'.json')
    immutable(path, encode(row))
    return row


def compare(universe, shadows, operational_root, market_roots, history_root, asof):
    """Universe includes independent-only events; keep every missing pair explicitly."""
    from nba_v09_research import paired, evidence, loss
    from nba_forward_test import predictions
    forecasts = predictions(operational_root)
    finals = {str(r['game_id']):r for r in history(history_root, asof)}
    snaps = [(digest,obj) for root in market_roots for digest,obj in evidence(Path(root)/'snapshots')]
    schedules = [(digest,obj) for root in market_roots for digest,obj in evidence(Path(root)/'schedules')]
    rows, seen = [], set()
    for target in universe:
        gid = str(target['id'])
        if gid in seen:
            raise ValueError('Duplicate universe identity')
        seen.add(gid)
        row = dict(game_id=gid, date=target['date'][:10], no_trade=True, reasons=[], market=None)
        rows.append(row)
        s = shadows.get(gid)
        if s is None:
            row['reasons'].append('missing_shadow')
            continue
        if s['target'] != target or timestamp(s['sealed_at']) > timestamp(asof):
            raise ValueError('Shadow identity/as-of mismatch')
        row.update(elo=s['elo'], challenger=s['challenger'], model_sha256=s['model_sha256'])
        row['reasons'].extend(r for r in s['reasons'] if r != 'market_not_yet_paired')
        candidates = []
        if gid in forecasts:
            game, archive, bundle = forecasts[gid]
            if archive != s['baseline_archive']:
                raise ValueError('Comparison baseline mismatch')
            for digest,snap in snaps:
                end = timestamp(snap['completed_at'])
                minutes = (timestamp(target['datetime'])-end).total_seconds()/60
                if not 30 <= minutes <= 60 or not timestamp(s['sealed_at']) <= timestamp(snap['started_at']) <= end <= timestamp(asof):
                    continue
                for schedule_digest,schedule in schedules:
                    try:
                        q = paired(game,bundle,snap,schedule)
                    except (ValueError, KeyError, TypeError, ArithmeticError):
                        continue
                    candidates.append((end,digest,schedule_digest,q))
        if candidates:
            _,digest,sd,q = min(candidates, key=lambda x:x[:3])
            row.update(market=q['market'], quote_snapshot=digest, schedule_snapshot=sd)
        else:
            row['reasons'].append('missing_valid_cutoff_quote')
        result = finals.get(gid)
        if result is not None:
            if (result['home'],result['away'],result['date']) != (identity(target['home_team']),identity(target['visitor_team']),target['date'][:10]):
                raise ValueError('Comparison final identity mismatch')
            if timestamp(result['received_at']) <= timestamp(target['datetime']):
                raise ValueError('Final predates tip')
            row['outcome'] = int(result['hs'] > result['aw'])
        else:
            row['reasons'].append('missing_verified_final')
    scored = [r for r in rows if all(r.get(k) is not None for k in ('elo','challenger','market','outcome'))]
    metrics = {}
    for label in ('elo','challenger','market'):
        scores = [loss(r[label],r['outcome']) for r in scored]
        metrics[label] = dict(n=len(scores), brier=sum(x[0] for x in scores)/len(scores) if scores else None,
            log_loss=sum(x[1] for x in scores)/len(scores) if scores else None,
            calibration=[dict(bin=i, n=sum(i/10 <= r[label] < (i+1)/10 or (i == 9 and r[label] == 1) for r in scored)) for i in range(10)])
        for b in metrics[label]['calibration']:
            group = [r for r in scored if min(9,int(r[label]*10)) == b['bin']]
            b.update(mean_probability=sum(r[label] for r in group)/len(group) if group else None,
                     win_rate=sum(r['outcome'] for r in group)/len(group) if group else None)
    dates = sorted({r['date'] for r in scored})
    intervals = {}
    if len(dates) >= 2:
        import random
        rng = random.Random(9)
        blocks = {d:[r for r in scored if r['date'] == d] for d in dates}
        for control in ('elo','market'):
            samples = []
            for _ in range(1000):
                sample = [r for d in rng.choices(dates,k=len(dates)) for r in blocks[d]]
                samples.append(sum((r['challenger']-r['outcome'])**2-(r[control]-r['outcome'])**2 for r in sample)/len(sample))
            samples.sort()
            intervals[control] = [samples[24],samples[974]]
    bins = []
    for lo,hi in ((0,.03),(.03,.08),(.08,1.01)):
        group = [r for r in scored if lo <= abs(r['challenger']-r['market']) < hi]
        bins.append(dict(lower=lo,upper=hi,n=len(group)))
    return dict(schema='nba-team-comparison-v1', asof=asof, no_trade=True, rows=rows,
                denominator=len(rows), paired_scored=len(scored), league_dates=len(dates),
                evaluation_ready=len(scored)>=200 and len(dates)>=30,
                metrics=metrics, disagreement_bins=bins, brier_difference_date_block_ci95=intervals)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--history', default='research/nba_v09/team_history')
    p.add_argument('--season', type=int)
    p.add_argument('--max-pages', type=int, default=20)
    p.add_argument('--action', choices=('collect','train','cutoff','compare'), default='collect')
    p.add_argument('--inputs', default='research/nba_v09/team_challenger')
    p.add_argument('--operational', default='forward_test')
    p.add_argument('--output', default='research/nba_v09/team_challenger')
    p.add_argument('--targets', help='JSON array of provider and independent-only target records')
    p.add_argument('--model', help='Explicit frozen model JSON; never auto-select latest')
    p.add_argument('--freeze-at')
    p.add_argument('--validation-start')
    p.add_argument('--market-roots', nargs='*', default=[])
    p.add_argument('--asof')
    p.add_argument('--max-wait-seconds', type=int, default=7200)
    a = p.parse_args()
    if a.action == 'collect':
        if a.season is None:
            p.error('--season required')
        print(collect_history(a.history, a.season, max_pages=a.max_pages))
    elif a.action == 'train':
        if not a.freeze_at or not a.validation_start:
            p.error('--freeze-at and --validation-start required')
        print(train(a.history,a.inputs,a.operational,a.output,freeze_at=a.freeze_at,
                    validation_start=a.validation_start)['model_sha256'])
    else:
        if not a.targets:
            p.error('--targets required')
        targets = json.loads(Path(a.targets).read_bytes())
        if a.action == 'cutoff':
            run_cutoffs(a.history, targets, a.operational, a.output,
                        json.loads(Path(a.model).read_bytes()) if a.model else None,
                        max_wait=a.max_wait_seconds)
        else:
            if not a.asof or not a.model:
                p.error('--asof and --model required')
            model = json.loads(Path(a.model).read_bytes())
            verify_model(model)
            shadows = {}
            for f in (Path(a.inputs)/model['model_sha256']).glob('*.json'):
                r = json.loads(f.read_bytes())
                if r['model_sha256'] != model['model_sha256'] or f.stem != str(r['target']['id']):
                    raise ValueError('Shadow model/game mismatch')
                expected = features(a.history,r['target'],r['features']['cutoff'])
                elo, archive = baseline(a.operational,r['target'],r['features']['cutoff'])
                predicted = probability(elo,expected['x'],model) if elo is not None and all(v is not None for v in expected['x']) else None
                if (r['features'] != expected or (r['elo'],r['baseline_archive'],r['challenger']) != (elo,archive,predicted)
                        or r['no_trade'] is not True or r['live_trading'] is not False):
                    raise ValueError('Shadow evidence mismatch')
                shadows[f.stem] = r
            print(save(a.output,'comparisons',compare(targets,shadows,a.operational,a.market_roots,a.history,a.asof)))


def run_cutoffs(root, targets, operational_root, output, model=None, *, max_wait=7200):
    """Dedicated bounded waiter. Must launch before cutoff; late games stay missing."""
    import time
    from datetime import timedelta
    if not 0 <= max_wait <= 14400:
        raise ValueError('Wait budget must be 0..14400 seconds')
    if model is not None:
        verify_model(model)
    deadline = time.monotonic()+max_wait
    groups = {}
    for t in targets:
        if 'datetime' not in t or 'home_team' not in t:
            save(output,'coverage',dict(game_id=t['id'],reason='independent_only_unresolved_identity',no_trade=True))
            continue
        due = timestamp(t['datetime'])-timedelta(minutes=60)
        groups.setdefault(due,[]).append(t)
    for due,group in sorted(groups.items()):
        while datetime.now(timezone.utc) < due and time.monotonic() < deadline:
            time.sleep(min(10,max(0,(due-datetime.now(timezone.utc)).total_seconds()),max(0,deadline-time.monotonic())))
        sealed = []
        for t in sorted(group,key=lambda t:str(t['id'])):
            try:
                seal_input(root,t,operational_root,output,purpose='evaluation' if model is not None else 'development')
                if model is not None:
                    shadow(root,t,datetime.now(timezone.utc).isoformat(),model,operational_root,output)
                sealed.append(t)
            except (ValueError, KeyError, OSError) as exc:
                save(output,'coverage',dict(game_id=t['id'],reason=type(exc).__name__,no_trade=True))
        if not sealed:
            continue
        try:
            # Seal simultaneous games before making serialized network requests.
            from nba_v09_prospective import market_get, capture_schedule
            from nba_v08_capture import capture
            for day in sorted({t['date'][:10] for t in sealed}):
                capture_schedule(day,Path(output)/'schedules')
            calls = 0
            def bounded_get(path,params=None):
                nonlocal calls
                calls += 1
                if calls > 70:
                    raise ValueError('Cutoff market request budget')
                return market_get(path,params)
            capture(Path(output)/'snapshots',fetch=bounded_get,workers=1)
        except (ValueError, KeyError, OSError) as exc:
            for t in sealed:
                save(output,'coverage',dict(game_id=t['id'],reason='market_'+type(exc).__name__,no_trade=True))


if __name__ == '__main__':
    main()
