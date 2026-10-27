"""Offline temperature calibration for nba_backtest.py CSV output. Standard library only.

Fit on a chronological validation window, freeze temperature, then evaluate later
predictions. No network, credentials, trading imports, or order submission.
"""
import argparse
import csv
import hashlib
import json
import math
from datetime import date
from pathlib import Path


def check(ps, ys):
    if not ps or len(ps) != len(ys):
        raise ValueError('Expected nonempty equal-length probabilities and labels')
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in ps):
        raise ValueError('Invalid probability')
    if any(y not in (0, 1) for y in ys):
        raise ValueError('Invalid binary outcome')


def transform(p, temperature):
    if not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError('Invalid probability')
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError('Temperature must be positive and finite')
    p = min(1 - 1e-12, max(1e-12, p))
    z = (math.log(p) - math.log1p(-p)) / temperature
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


def metrics(ps, ys):
    check(ps, ys)
    clipped = [min(1 - 1e-12, max(1e-12, p)) for p in ps]
    bins = []
    for i in range(10):
        pairs = [(p, y) for p, y in zip(ps, ys) if min(9, int(p * 10)) == i]
        n = len(pairs)
        bins.append(dict(lower=i / 10, upper=(i + 1) / 10, n=n,
                         mean_probability=sum(p for p, _ in pairs) / n if n else None,
                         observed_rate=sum(y for _, y in pairs) / n if n else None))
    return dict(n=len(ps), brier=sum((p-y)**2 for p,y in zip(ps,ys))/len(ps),
                log_loss=-sum(y*math.log(p)+(1-y)*math.log1p(-p) for p,y in zip(clipped,ys))/len(ps),
                ece=sum(b['n']*abs(b['mean_probability']-b['observed_rate']) for b in bins if b['n'])/len(ps),
                bins=bins)


def fit_temperature(ps, ys):
    """Minimize validation log loss on a fixed 0.50..3.00 grid (step 0.01).

    Prefer temperature closest to 1 on a tie. Bounds are intentionally fixed;
    a boundary solution is reported so users can inspect fit limitations.
    """
    check(ps, ys)
    def loss(t):
        qs = [transform(p, t) for p in ps]
        return -sum(y*math.log(max(q,1e-12))+(1-y)*math.log(max(1-q,1e-12)) for q,y in zip(qs,ys))/len(ps)
    return min((i/100 for i in range(50,301)), key=lambda t: (loss(t), abs(t-1)))


def read_predictions(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    seen = set()
    for r in rows:
        day = date.fromisoformat(r['date'])
        if day.isoformat() != r['date']:
            raise ValueError('Dates must be YYYY-MM-DD')
        gid = int(r['game_id'])
        if gid in seen:
            raise ValueError('Duplicate game ID')
        seen.add(gid)
        if int(r['home_team_id']) == int(r['away_team_id']):
            raise ValueError('Self matchup')
        r['home_win_probability'] = float(r['home_win_probability'])
        r['home_win'] = int(r['home_win'])
    check([r['home_win_probability'] for r in rows], [r['home_win'] for r in rows])
    return rows


def evaluate(rows, validation_start='2024-10-01', test_start='2025-10-01'):
    for d in (validation_start, test_start):
        if date.fromisoformat(d).isoformat() != d:
            raise ValueError('Cutoffs must be YYYY-MM-DD')
    if validation_start >= test_start:
        raise ValueError('Validation must precede test')
    validation = [r for r in rows if validation_start <= r['date'] < test_start]
    test = [r for r in rows if r['date'] >= test_start]
    ps = lambda rs: [r['home_win_probability'] for r in rs]
    ys = lambda rs: [r['home_win'] for r in rs]
    check(ps(test), ys(test))
    temperature = fit_temperature(ps(validation), ys(validation))
    result = dict(version='0.5-recreated', temperature=temperature,
                  boundary_fit=temperature in (.5,3), validation_start=validation_start,
                  test_start=test_start, excluded_earlier_rows=len(rows)-len(validation)-len(test),
                  method='Frozen temperature; fixed grid chosen by validation log loss',
                  status='Exploratory retrospective evaluation; test outcomes were previously reviewed. No trading edge established.')
    for name, rs in [('validation', validation), ('test', test)]:
        result[name] = dict(start=min(r['date'] for r in rs), end=max(r['date'] for r in rs),
                            raw=metrics(ps(rs),ys(rs)),
                            calibrated=metrics([transform(p,temperature) for p in ps(rs)],ys(rs)))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', default='nba_backtest_predictions.csv')
    parser.add_argument('--validation-start', default='2024-10-01')
    parser.add_argument('--test-start', default='2025-10-01')
    parser.add_argument('--output', default='nba_calibration_results.json')
    args = parser.parse_args()
    if Path(args.input).resolve() == Path(args.output).resolve():
        parser.error('Output must differ from input')
    result = evaluate(read_predictions(args.input), args.validation_start, args.test_start)
    result['source_sha256'] = hashlib.sha256(Path(args.input).read_bytes()).hexdigest()
    Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('temperature','boundary_fit','status')}))


if __name__ == '__main__':
    main()
