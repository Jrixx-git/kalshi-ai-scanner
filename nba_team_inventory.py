"""Full verifier inventory, without fitting, predicting, or selecting on outcomes."""
import argparse
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from nba_v09_challenger import verified_development_rows, FIELDS
from nba_v08_valuation import timestamp
from nba_forward_test import encode


def inventory(history, inputs, operational):
    now = datetime.now(timezone.utc).isoformat()
    rows = verified_development_rows(history, inputs, operational, freeze_at=now)
    eligible = [r for r in rows if len(r['features']['x']) == len(FIELDS)
                and all(v is not None and math.isfinite(v) for v in r['features']['x'])
                and timestamp(r['features']['cutoff']) < timestamp(r['tipoff_utc'])
                < timestamp(r['outcome_received_at']) <= timestamp(now)]
    # Prospective chronology only. Earliest split admitting 100 known outcomes;
    # outcome values and model performance never participate in selecting it.
    splits = sorted({r['tipoff_utc'] for r in eligible}, key=timestamp)
    train, validation, split = len(eligible), 0, None
    for candidate in splits:
        before = [r for r in eligible if timestamp(r['tipoff_utc']) < timestamp(candidate)
                  and timestamp(r['outcome_received_at']) < timestamp(candidate)]
        if len(before) >= 100:
            train = len(before)
            validation = sum(timestamp(r['tipoff_utc']) >= timestamp(candidate) for r in eligible)
            split = candidate
            break
    seals = [json.loads(p.read_bytes()) for p in (Path(inputs)/'inputs').glob('*.json')]
    return dict(audited_at=now, development_seals=len(seals),
                full_verifier_completed_rows=len(rows), eligible_completed_games=len(eligible),
                eligible_training=train, eligible_later_validation=validation,
                proposed_validation_start=split, ready=train >= 100 and validation >= 30,
                missing_elo=sum(s.get('elo') is None for s in seals),
                missing_features=sum(any(v is None for v in s['features']['x']) for s in seals),
                coverage=dict(Counter(json.loads(p.read_bytes())['reason']
                    for p in (Path(inputs)/'coverage').glob('*.json'))),
                no_trade=True, live_trading=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--history', required=True)
    p.add_argument('--inputs', required=True)
    p.add_argument('--operational', default='forward_test/state')
    p.add_argument('--output', required=True)
    a = p.parse_args()
    report = inventory(a.history, a.inputs, a.operational)
    Path(a.output).write_bytes(encode(report))
    print(json.dumps(report, sort_keys=True))
