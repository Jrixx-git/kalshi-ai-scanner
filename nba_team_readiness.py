"""Read-only evidence inventory. Never backdate, fit, or write operational state."""
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from nba_forward_test import predictions
from nba_v09_challenger import history, sha
from nba_v08_valuation import timestamp


def audit(root, history_root):
    root, history_root = Path(root), Path(history_root)
    now = datetime.now(timezone.utc).isoformat()
    forecasts = predictions(root/'forward_test/state')
    bundles = list((root/'forward_test/state/predictions').glob('*/manifest.json'))
    pregame = sum(timestamp(b['observed_at']) < timestamp(r['tipoff_utc'])
                  and timestamp(r['generated_at_utc']) < timestamp(r['tipoff_utc'])
                  for r, _, b in forecasts.values())
    collections = []
    for path in sorted((history_root/'collections').glob('*.json')):
        obj = json.loads(path.read_bytes())
        if path.stem != sha(obj) or obj['complete'] is not True:
            raise ValueError('Collection integrity')
        counts, ids, times = Counter(), set(), []
        for name in obj['pages']:
            receipt = json.loads((history_root/'receipts'/name).read_bytes())
            raw = (history_root/'raw'/receipt['raw_sha256']).read_bytes()
            if Path(name).stem != sha(receipt) or hashlib.sha256(raw).hexdigest() != receipt['raw_sha256']:
                raise ValueError('Page integrity')
            payload = json.loads(raw)
            for game in payload['data']:
                if game['id'] in ids or game['season'] != obj['season']:
                    raise ValueError('Duplicate or wrong season')
                ids.add(game['id'])
                counts[game['status']] += 1
            times.append(receipt['received_at'])
        if payload['meta'].get('next_cursor') is not None:
            raise ValueError('Unfinished pagination')
        collections.append(dict(season=obj['season'], pages=len(obj['pages']), games=len(ids),
                                statuses=dict(counts), first_receipt=min(times), last_receipt=max(times)))
    finals = history(history_root, now)
    seals = list(root.glob('research/**/inputs/*.json'))
    # Inventory is intentionally conservative: seals require the train() verifier.
    # With no seals the exact eligible train/validation counts are both zero.
    return dict(schema='nba-team-readiness-v1', audited_at=now, no_trade=True,
                operational_bundles=len(bundles), operational_unique_games=len(forecasts),
                operational_pregame_games=pregame, collections=collections,
                verified_first_observed_finals=len(finals), development_input_files=len(seals),
                eligible_training=0 if not seals else None,
                eligible_later_validation=0 if not seals else None,
                training_required=100, validation_required=30, eligible=False,
                blockers=['No qualifying development seals' if not seals else 'Run full sealed-input verifier',
                          'Legacy normalized history has bundle timestamps and hashes, not complete raw-page receipts',
                          'New history receipts cannot establish availability before their actual retrieval',
                          'No supervised cutoff worker has been demonstrated'],
                legacy_history_files=sum((p.parent/'history.json').exists() for p in bundles))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', default='.')
    p.add_argument('--history', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    report = audit(a.root, a.history)
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    Path(a.output).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, sort_keys=True))
