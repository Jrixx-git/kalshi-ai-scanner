"""Separately versioned retrospective training and genuine forward shadows. No trading."""
import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from nba_calibration import metrics, transform
from nba_elo import win_probability
from nba_forward_test import encode, immutable
from nba_v08_valuation import timestamp
from nba_v09_challenger import (FIELDS, baseline, compare, features, history,
                                identity, probability, save, sha)

VERSION = 'nba-retrospective-elo-offset-v1'
POLICY = dict(version=VERSION, split='2026-10-01', l2=0.1, iterations=2000,
              step=0.1, min_train=500, min_validation=100,
              history_start='2025-10-01', missing='abstain',
              same_date='exclude_all', temperature=1.23,
              evidence='retrospective_reconstruction_not_point_in_time',
              injuries='excluded', market_training=False)


def implementation_hash():
    names = ('nba_retrospective.py', 'nba_v09_challenger.py', 'nba_calibration.py',
             'nba_elo.py', 'nba_forward_test.py')
    return sha({n: hashlib.sha256(Path(__file__).with_name(n).read_bytes().replace(
        b'\r\n', b'\n')).hexdigest() for n in names})


def vector(past, target):
    """Only strictly earlier league dates; identical field semantics to strict v1."""
    day = target['date'][:10]
    h, a = target['home'], target['away']
    prior = [g for g in past if g['date'] < day and g['game_id'] != target['game_id']]
    def team(t, home):
        rows = [g for g in prior if t in (g['home'], g['away'])]
        if not rows:
            return [None]*len(FIELDS)
        margins = [(g['hs']-g['aw'])*(1 if g['home'] == t else -1) for g in rows]
        rest = (date.fromisoformat(day)-date.fromisoformat(rows[-1]['date'])).days
        venue = [g for g in rows if (g['home'] == t) == home][-20:]
        out = dict(rest=min(rest, 7), b2b=int(rest == 1))
        for n in (5, 10):
            out['margin'+str(n)] = sum(margins[-n:])/n if len(rows) >= n else None
            out['win'+str(n)] = sum(m > 0 for m in margins[-n:])/n if len(rows) >= n else None
        out['venue20'] = sum((g['hs'] > g['aw']) == home for g in venue)/20 if len(venue) == 20 else None
        return [out[k] for k in FIELDS]
    return [x-y if x is not None and y is not None else None
            for x, y in zip(team(h, True), team(a, False))]


def reconstruct(games, before):
    grouped, seen = defaultdict(list), set()
    for g in sorted(games, key=lambda r: (r['date'], r['game_id'])):
        if g['game_id'] in seen:
            raise ValueError('Duplicate historical identity')
        seen.add(g['game_id'])
        if POLICY['history_start'] <= g['date'] < before:
            grouped[g['date']].append(g)
    ratings, past, rows, excluded = {}, [], [], []
    for day, group in sorted(grouped.items()):
        changes = defaultdict(float)
        for g in group:
            h, a = g['home'], g['away']
            raw = win_probability(ratings.get(h, 1500.), ratings.get(a, 1500.), 65)
            x = vector(past, g)
            y = int(g['hs'] > g['aw'])
            if all(v is not None for v in x):
                rows.append(dict(game_id=g['game_id'], date=day, x=x, outcome=y,
                    elo=round(transform(round(raw, 6), 1.23), 6),
                    feature_max_date=max(r['date'] for r in past),
                    historical_receipt_sha256=g['receipt_sha256']))
            else:
                excluded.append(dict(game_id=g['game_id'], date=day, reason='warmup_missing_features'))
            delta = 20*(y-raw)
            changes[h] += delta
            changes[a] -= delta
        for t, delta in changes.items():
            ratings[t] = ratings.get(t, 1500.)+delta
        past.extend(group)
    return rows, excluded


def fit(rows):
    if len({r['game_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate fitting game')
    if any(len(r['x']) != len(FIELDS) or not all(math.isfinite(v) for v in r['x'])
           or r['outcome'] not in (0,1) or not 0 < r['elo'] < 1 for r in rows):
        raise ValueError('Invalid fitting row')
    train = [r for r in rows if r['date'] < POLICY['split']]
    validation = [r for r in rows if r['date'] >= POLICY['split']]
    if len(train) < POLICY['min_train'] or len(validation) < POLICY['min_validation']:
        raise ValueError('Insufficient retrospective training/validation (500/100)')
    if any(r['feature_max_date'] >= r['date'] for r in rows):
        raise ValueError('Target-date leakage')
    n = len(train)
    means = [sum(r['x'][j] for r in train)/n for j in range(len(FIELDS))]
    scales = [math.sqrt(sum((r['x'][j]-means[j])**2 for r in train)/n) or 1. for j in range(len(FIELDS))]
    model = dict(version=VERSION, policy=POLICY, fields=list(FIELDS),
                 means=means, scales=scales, weights=[0.]*len(FIELDS),
                 dataset_sha256=sha(rows), implementation_sha256=implementation_hash(),
                 training_dates=[train[0]['date'], train[-1]['date']],
                 validation_dates=[validation[0]['date'], validation[-1]['date']],
                 n_train=n, n_validation=len(validation),
                 historical_elo='reconstructed_from_2025_not_archived_operational_elo',
                 no_trade=True, live_trading=False)
    scaled = [[(v-m)/s for v,m,s in zip(r['x'],means,scales)] for r in train]
    offsets = [math.log(r['elo']/(1-r['elo'])) for r in train]
    for _ in range(POLICY['iterations']):
        grad = [POLICY['l2']*w for w in model['weights']]
        for r,x,offset in zip(train,scaled,offsets):
            z = offset+sum(w*v for w,v in zip(model['weights'],x))
            err = 1/(1+math.exp(-max(-35,min(35,z))))-r['outcome']
            for j,v in enumerate(x):
                grad[j] += err*v/n
        model['weights'] = [w-POLICY['step']*g for w,g in zip(model['weights'],grad)]
    model['validation'] = {label: metrics([r['elo'] if label == 'elo' else
        probability(r['elo'],r['x'],model) for r in validation], [r['outcome'] for r in validation])
        for label in ('elo','challenger')}
    model['model_sha256'] = sha(model)
    return model


def train(root, output, asof):
    now = datetime.now(timezone.utc)
    if timestamp(asof) > now:
        raise ValueError('Future data cutoff')
    games = history(root, asof)  # Verify original manifests, exact raw hashes and real receipts.
    rows, excluded = reconstruct(games, timestamp(asof).date().isoformat())
    model = fit(rows)
    save(output, 'datasets', dict(rows=rows, excluded=excluded, policy=POLICY,
        source_games_sha256=sha(games), data_cutoff_at=asof,
        provenance='downloaded retrospectively; no historical availability claim'))
    save(output, 'models', model)
    # Actual freeze is separate from deterministic model identity. Never backdate it.
    freeze = dict(schema=VERSION+'-freeze', model_sha256=model['model_sha256'],
        frozen_at=datetime.now(timezone.utc).isoformat(), data_cutoff_at=asof,
        no_trade=True, live_trading=False)
    immutable(Path(output)/'frozen.json', encode(dict(model=model, freeze=freeze)))
    return model


def verify(frozen):
    m, f = frozen['model'], frozen['freeze']
    if (m['model_sha256'] != sha({k:v for k,v in m.items() if k != 'model_sha256'})
            or m['version'] != VERSION or m['policy'] != POLICY
            or m['implementation_sha256'] != implementation_hash()
            or f['model_sha256'] != m['model_sha256']
            or timestamp(f['data_cutoff_at']) > timestamp(f['frozen_at'])
            or timestamp(f['frozen_at']) > datetime.now(timezone.utc)):
        raise ValueError('Frozen retrospective model mismatch')
    return m


def shadow(history_root, inputs, operational, output, frozen):
    """Consume genuine cutoff seals. Late publishing is explicitly excluded."""
    from nba_daily_predictions import lifecycle
    model = verify(frozen)
    output = Path(output)
    shadows = {}
    for p in sorted((Path(inputs)/'inputs').glob('*.json')):
        seal = json.loads(p.read_bytes())
        t, f = seal['target'], seal['features']
        gid = str(t['id'])
        path = output/'shadows'/model['model_sha256']/(gid+'.json')
        if path.exists():
            row = json.loads(path.read_bytes())
        else:
            now = datetime.now(timezone.utc)
            if not timestamp(frozen['freeze']['frozen_at']) < timestamp(f['cutoff']) <= timestamp(seal['sealed_at']) <= now < timestamp(t['datetime']):
                continue
            if not 1800 <= (timestamp(t['datetime'])-now).total_seconds() <= 3600:
                continue
            row = dict(schema=VERSION+'-shadow', target=t, features=f,
                model_sha256=model['model_sha256'], frozen_at=frozen['freeze']['frozen_at'],
                sealed_at=now.isoformat(), elo=seal['elo'], baseline_archive=seal['baseline_archive'],
                challenger=None, reasons=['market_not_yet_paired'], no_trade=True, live_trading=False)
            if seal['elo'] is None or any(v is None for v in f['x']):
                row['reasons'].append('missing_baseline_or_features')
            else:
                row['challenger'] = probability(seal['elo'], f['x'], model)
        elo, archive = baseline(operational,t,f['cutoff'])
        if (p.stem != gid or seal['schema'] != 'nba-team-input-v1'
                or seal['no_trade'] is not True or seal['live_trading'] is not False
                or not 3570 <= (timestamp(t['datetime'])-timestamp(f['cutoff'])).total_seconds() <= 3600
                or not 0 <= (timestamp(seal['sealed_at'])-timestamp(f['cutoff'])).total_seconds() <= 30
                or t.get('period') != 0 or lifecycle(t) != 'scheduled'
                or features(history_root,t,f['cutoff']) != f
                or (elo,archive) != (seal['elo'],seal['baseline_archive'])
                or row['target'] != t or row['features'] != f
                or row['model_sha256'] != model['model_sha256']
                or row['no_trade'] is not True or row['live_trading'] is not False
                or (row['elo'], row['baseline_archive']) != (elo,archive)
                or not timestamp(frozen['freeze']['frozen_at']) < timestamp(f['cutoff']) <= timestamp(seal['sealed_at']) <= timestamp(row['sealed_at']) < timestamp(t['datetime'])
                or row['challenger'] != (probability(elo,f['x'],model) if elo is not None and all(v is not None for v in f['x']) else None)):
            raise ValueError('Forward shadow evidence mismatch')
        immutable(path, encode(row))
        shadows[gid] = row
    return shadows


def daily(history_root, inputs, operational, output, frozen):
    from nba_v09_prospective import capture_schedule, market_get, active
    from nba_v08_capture import capture
    now = datetime.now(timezone.utc)
    if not active(now):
        raise ValueError('Outside bounded approved research collection window')
    shadows = shadow(history_root,inputs,operational,output,frozen)
    pending = [r for r in shadows.values() if 1800 <= (
        timestamp(r['target']['datetime'])-datetime.now(timezone.utc)).total_seconds() <= 3600]
    if pending:
        for day in sorted({r['target']['date'][:10] for r in pending}):
            capture_schedule(day,Path(output)/'schedules')
        calls = 0
        def bounded(path,params=None):
            nonlocal calls
            calls += 1
            if calls > 70:
                raise ValueError('Quote request budget')
            return market_get(path,params)
        capture(Path(output)/'snapshots',fetch=bounded,workers=1)
    universe = [json.loads(p.read_bytes()) for p in sorted((Path(inputs)/'inputs').glob('*.json'))]
    universe = [r['target'] for r in universe if timestamp(r['features']['cutoff']) > timestamp(frozen['freeze']['frozen_at'])]
    report = compare(universe, shadows, operational,
        [output], history_root, datetime.now(timezone.utc).isoformat())
    report.update(protocol=VERSION, provenance='genuine_forward_receipts',
                  model_sha256=frozen['model']['model_sha256'])
    save(output,'comparisons',report)
    print(json.dumps(dict(shadows=len(shadows), paired_scored=report['paired_scored'],metrics=report['metrics'])))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('train','reproduce','daily'))
    p.add_argument('--history',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--asof')
    p.add_argument('--inputs')
    p.add_argument('--operational')
    p.add_argument('--frozen')
    a = p.parse_args()
    if a.action == 'train':
        m = train(a.history,a.output,a.asof or datetime.now(timezone.utc).isoformat())
        print(json.dumps(m))
    else:
        frozen = json.loads(Path(a.frozen).read_bytes())
        m = verify(frozen)
        if a.action == 'reproduce':
            rows,_ = reconstruct(history(a.history,frozen['freeze']['data_cutoff_at']),
                timestamp(frozen['freeze']['data_cutoff_at']).date().isoformat())
            if fit(rows) != m:
                raise ValueError('Reproduction differs')
            print(m['model_sha256'])
        else:
            daily(a.history,a.inputs,a.operational,a.output,frozen)


if __name__ == '__main__':
    main()
