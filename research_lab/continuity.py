"""Read-only daily coverage audit; a missing forecast is never a no-trade."""
import argparse
import csv
import hashlib
import io
import json
import sqlite3
from collections import Counter
from pathlib import Path
from .core import instant, read_sealed, seal

NO_TRADE = {'edge_below_threshold', 'no_positive_net_edge_or_invalid_quote'}


def inventory(repository, days):
    repository = Path(repository)
    forward = repository/'forward_test/state'; paper = repository/'paper_v08/state'
    schedules, forecasts, errors = {}, {}, []
    for folder in sorted((forward/'predictions').iterdir()):
        if not folder.is_dir(): continue
        try:
            meta_raw = (folder/'metadata.json').read_bytes(); meta = json.loads(meta_raw)
            if meta['target_date'] not in days: continue
            manifest = json.loads((folder/'manifest.json').read_bytes())
            csv_raw = (folder/'predictions.csv').read_bytes(); schedule_raw = (folder/'schedule.json').read_bytes()
            if hashlib.sha256(csv_raw).hexdigest() != manifest['csv_sha256'] or hashlib.sha256(meta_raw).hexdigest() != manifest['metadata_sha256'] or hashlib.sha256(schedule_raw).hexdigest() != manifest['snapshots']['schedule.json']:
                raise ValueError('forecast_archive_hash_mismatch')
            schedules.setdefault(meta['target_date'], {})
            for game in json.loads(schedule_raw):
                if game.get('postponed'): continue
                gid = str(game['id']); schedules.setdefault(meta['target_date'], {})[gid] = game
            for game in csv.DictReader(io.StringIO(csv_raw.decode())):
                if instant(manifest['observed_at']) >= instant(game['tipoff_utc']): continue
                current = forecasts.get(game['game_id'])
                if current is None or instant(manifest['observed_at']) < instant(current['sealed_at']):
                    forecasts[game['game_id']] = dict(game, sealed_at=manifest['observed_at'], archive=folder.name)
        except (KeyError, ValueError, OSError, TypeError) as exc:
            errors.append({'archive': folder.name, 'reason': str(exc)})
    decisions = {}
    for path in sorted((paper/'reports').glob('*.json')):
        try:
            report = read_sealed(paper/'reports', path.stem)
            snapshot = report.get('target_snapshot')
            if snapshot: read_sealed(paper/'snapshots', Path(snapshot).stem)
            for d in report['entries']['decisions']:
                gid = d['game_id']; f = forecasts.get(gid)
                if not f or instant(report['generated_at']) >= instant(f['tipoff_utc']): continue
                # Reports about expired old forecasts are not eligible pregame decisions.
                if not d.get('assessments') or not d.get('identity'): continue
                if instant(d['identity']['received_at']) >= instant(f['tipoff_utc']): continue
                decisions.setdefault(gid, []).append(d)
        except (KeyError, ValueError, OSError, TypeError) as exc:
            errors.append({'report': path.name, 'reason': str(exc)})
    db = sqlite3.connect((paper/'ledger.sqlite3').resolve().as_uri()+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        if db.execute('pragma integrity_check').fetchone()[0] != 'ok': raise ValueError('ledger_integrity')
        rows = {r['signal_id'].split(':', 1)[1]:dict(r) for r in db.execute('select * from trades')}
    finally: db.close()
    daily = []
    for day in days:
        scheduled = schedules.get(day, {}); missing_forecasts=[]; missing_quotes=[]; no_trades=[]; trades=[]; unclassified=[]
        for gid in sorted(scheduled):
            if gid not in forecasts: missing_forecasts.append(gid)
            if gid not in decisions: missing_quotes.append(gid)
            if gid in rows: trades.append(gid)
            elif any(d['reason'] in NO_TRADE for d in decisions.get(gid, [])): no_trades.append(gid)
            else: unclassified.append(gid)
        daily.append({'date':day,'schedule_archived':day in schedules,'eligible':len(scheduled),'sealed_pregame':len(scheduled)-len(missing_forecasts),
            'quote_assessments':len(scheduled)-len(missing_quotes),'paper_entries':len(trades),
            'no_trades':len(no_trades),'missing_forecasts':missing_forecasts,'missing_quotes':missing_quotes,
            'unclassified':unclassified,'paper_statuses':dict(Counter(rows[g]['status'] for g in trades))})
    return {'paper_only':True,'daily':daily,'integrity_errors':errors,'schedule_basis':'archived provider schedule union; external schedule completeness remains a separate check',
            'complete':not errors and all(d['schedule_archived'] and not d['missing_forecasts'] and not d['missing_quotes'] and not d['unclassified'] for d in daily)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', default='.')
    parser.add_argument('--days', nargs='+', required=True)
    parser.add_argument('--output', default='research_outputs/continuity')
    args=parser.parse_args(); output=Path(args.output).resolve()
    if any(p in ('paper_v08','forward_test','.github') for p in output.parts): raise ValueError('operational_output_forbidden')
    report=inventory(args.repository,args.days); digest=seal(output,report)
    print(json.dumps({'report_sha256':digest,**report},indent=2))
    if not report['complete']: raise SystemExit(1)


if __name__=='__main__':main()
