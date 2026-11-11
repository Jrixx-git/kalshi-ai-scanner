"""Manual bounded development-input collection; deliberately no model argument."""
import argparse
import json
from pathlib import Path
from nba_v09_challenger import run_cutoffs, sha
from nba_v09_prospective import collect


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


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--history', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--max-wait-seconds', type=int, default=7200, choices=range(0,14401))
    a = p.parse_args()
    root = Path(a.output)
    collect(root/'source')
    # Explicit correct archive location; no mutable Elo regeneration or fallback.
    run_cutoffs(a.history, targets(root/'source'), 'forward_test/state', root,
                model=None, max_wait=a.max_wait_seconds)
