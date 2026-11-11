"""Offline, full-schedule NBA coverage and matched as-of research; never orders."""
import argparse
import hashlib
import json
import math
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from pathlib import Path
from nba_forward_test import predictions, encode, immutable, verified_final
from nba_v08_valuation import timestamp, match, taker_fee
from nba_v08_fees import effective
from kalshi_orderbook import quote_from_orderbook
from nba_daily_predictions import lifecycle

D = Decimal
POLICY = dict(max_forecast_age_seconds=86400, max_capture_seconds=30,
              max_disagreement=0.08, max_spread=0.10, slippage=0.01, min_net_edge=0.03)


def evidence(directory):
    items = []
    for p in sorted(Path(directory).glob('*.json')):
        raw = p.read_bytes()
        if hashlib.sha256(raw).hexdigest() != p.stem:
            raise ValueError('Evidence digest mismatch: ' + str(p))
        items.append((p.stem, json.loads(raw)))
    return items


def loss(p, y):
    q = min(1-1e-15, max(1e-15, p))
    return (p-y)**2, -(y*math.log(q)+(1-y)*math.log(1-q))


def metrics(rows):
    if not rows:
        return dict(n=0, elo_brier=None, market_brier=None, elo_log_loss=None, market_log_loss=None)
    result = {'n': len(rows)}
    for label, field in [('elo', 'elo'), ('market', 'market')]:
        scores = [loss(r[field], r['outcome']) for r in rows]
        result[label+'_brier'] = sum(x[0] for x in scores)/len(rows)
        result[label+'_log_loss'] = sum(x[1] for x in scores)/len(rows)
    return result


def quality(p, market, spread):
    if not all(math.isfinite(x) and 0 <= x <= 1 for x in (p, market, spread)):
        return ['invalid_probability']
    reasons = []
    if abs(p-market) >= POLICY['max_disagreement']:
        reasons.append('major_model_market_divergence')
    if spread > POLICY['max_spread']:
        reasons.append('wide_spread')
    return reasons


def paired(game, bundle, snap, schedule):
    """Canonical home YES book, chosen independent of price, edge and outcome."""
    start, end, tip = map(timestamp, (snap['started_at'], snap['completed_at'], game['tipoff_utc']))
    if (snap.get('schema') != 'nba-kalshi-capture-v1' or snap.get('live_trading') is not False
            or snap.get('series') != 'KXNBAGAME' or not timestamp(bundle['observed_at']) <= start <= end < tip
            or not 0 <= (end-start).total_seconds() <= POLICY['max_capture_seconds']
            or not 0 <= (end-timestamp(game['generated_at_utc'])).total_seconds() <= POLICY['max_forecast_age_seconds']
            or timestamp(schedule['received_at']) > start):
        raise ValueError('asof_or_staleness')
    markets = []
    for m in snap['markets']:
        try:
            selected = match(game, m, schedule=schedule, now=end)
            markets.append((selected, m))
        except (KeyError, ValueError, TypeError):
            pass
    if len(markets) != 2 or len({m['ticker'] for _, m in markets}) != 2:
        raise ValueError('missing_or_ambiguous_contract_pair')
    from nba_v08_valuation import ALIASES
    home = ALIASES.get(game['home_team'], game['home_team'])
    market = next(m for team, m in markets if team == home)
    ticker = market['ticker']
    if ticker in snap['errors']:
        raise ValueError('book_retrieval_error')
    book = snap['orderbooks'][ticker]
    if not start <= timestamp(book['observed_at']) <= timestamp(book['received_at']) <= end:
        raise ValueError('book_asof')
    q = quote_from_orderbook(ticker, book['raw'], book['observed_at'])
    yes, no = D(q['yes_ask']), D(q['no_ask'])
    midpoint = float((1-no+yes)/2)
    p = float(game['home_win_probability'])
    if not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError('invalid_elo')
    return dict(elo=p, market=midpoint, spread=float(yes+no-1), ticker=ticker,
                quote=q, decision_at=end.isoformat(), flags=quality(p, midpoint, float(yes+no-1)))


def hypothetical(row, fees):
    """One contract per game, canonical home YES/NO; verified fee evidence only."""
    if row['flags']:
        return {'status': 'blocked_quality'}
    candidates = []
    for _, record in fees:
        try:
            if timestamp(record['received_at']) > timestamp(row['snapshot_started_at']):
                continue
            applied = effective(record, row['ticker'].rsplit('-', 1)[0], timestamp(row['decision_at']))
            candidates.append(applied)
        except (ValueError, KeyError, TypeError, ArithmeticError):
            pass
    if not candidates or len({str(x) for x in candidates}) != 1:
        return {'status': 'fee_unavailable_or_conflicting'}
    choices = []
    for side, probability in [('yes', D(str(row['elo']))), ('no', 1-D(str(row['elo'])))]:
        price = D(row['quote'][side+'_ask']) + D(str(POLICY['slippage']))
        if not 0 < price < 1:
            continue
        fee = taker_fee(price, 1, candidates[0]['fee_multiplier'])
        edge = probability-price-fee
        if edge >= D(str(POLICY['min_net_edge'])):
            choices.append((edge, side, price, fee))
    if not choices:
        return {'status': 'no_edge'}
    edge, side, price, fee = max(choices)
    outcome = row.get('outcome')
    pnl = None if outcome is None else str(D(outcome if side == 'yes' else 1-outcome)-price-fee)
    return dict(status='hypothetical_only_injury_unverified', side=side, price=str(price),
                fee=str(fee), net_edge=str(edge), pnl=pnl, contracts=1,
                admitted_paper_trade=False)


def audit(forecast_root, market_root, additional_market_root=None):
    forecast_root, market_root = Path(forecast_root), Path(market_root)
    forecasts = predictions(forecast_root)
    manifests = sorted((forecast_root/'predictions').glob('*/manifest.json'))
    # Validated archive manifests pin schedule bytes. Universe includes unforecast games.
    universe, schedule_sources = {}, {}
    for p in manifests:
        manifest = json.loads(p.read_bytes())
        if 'schedule.json' not in manifest['snapshots']:
            continue
        for g in json.loads((p.parent/'schedule.json').read_bytes()):
            gid = str(g['id'])
            identity = (str(g['date'])[:10], str(g['home_team']['id']), str(g['visitor_team']['id']))
            if gid in universe and universe[gid]['identity'] != identity:
                raise ValueError('Conflicting schedule identity')
            try:
                eligible = (lifecycle(g) == 'scheduled' and g.get('period') == 0
                    and timestamp(manifest['observed_at']) < timestamp(g['datetime']))
            except (KeyError, ValueError, TypeError):
                eligible = False
            if gid in universe:
                eligible = eligible or universe[gid]['eligible']
            universe[gid] = dict(identity=identity, eligible=eligible)
            schedule_sources.setdefault(gid, []).append(p.parent.name)
    for gid in forecasts:
        universe.setdefault(gid, dict(identity=None, eligible=True))
    # A separate archived history inventory checks for games omitted from schedules.
    # It is discovery evidence only: never manufactures a pregame forecast or quote.
    history_games = {}
    first_date = min((u['identity'][0] for u in universe.values() if u['identity']), default='9999-12-31')
    for p in manifests:
        manifest = json.loads(p.read_bytes())
        if 'history.json' not in manifest['snapshots']:
            continue
        for g in json.loads((p.parent/'history.json').read_bytes()):
            if str(g['date'])[:10] >= first_date:
                history_games[str(g['id'])] = g
    history_missing = sorted(set(history_games)-set(universe))
    for gid in history_missing:
        g = history_games[gid]
        universe[gid] = dict(identity=(str(g['date'])[:10], str(g['home_team']['id']),
            str(g['visitor_team']['id'])), eligible=False, eligibility_unknown=True)
    roots = [market_root] + ([Path(additional_market_root)] if additional_market_root else [])
    for root in roots:
        for sha, record in evidence(root/'universe'):
            if record.get('pagination_complete') is not True or record.get('source') != 'https://api.balldontlie.io/v1/games':
                raise ValueError('Incomplete or foreign universe')
            for g in record['games']:
                gid = str(g['id'])
                identity = (str(g['date'])[:10], str(g['home_team']['id']), str(g['visitor_team']['id']))
                if gid in universe and universe[gid]['identity'] not in (None, identity):
                    raise ValueError('Conflicting universe identity')
                eligible = (lifecycle(g)=='scheduled' and g.get('period')==0
                    and timestamp(record['requested_at']) <= timestamp(record['received_at']) < timestamp(g['datetime']))
                universe[gid] = dict(identity=identity, eligible=eligible or universe.get(gid, {}).get('eligible', False))
                schedule_sources.setdefault(gid, []).append(sha)
    snapshots = list({sha: obj for root in roots for sha,obj in evidence(root/'snapshots')}.items())
    schedules = list({sha: obj for root in roots for sha,obj in evidence(root/'schedules')}.items())
    fees = list({sha: obj for root in roots for sha,obj in evidence(root/'fees')}.items())
    results = evidence(forecast_root/'results')
    selected_games = set()
    ledger = market_root/'ledger.sqlite3'
    if ledger.exists():
        with closing(sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro', uri=True)) as db:
            for (entry,) in db.execute('SELECT entry_json FROM paper_evidence'):
                if entry:
                    selected_games.add(str(json.loads(entry)['forecast']['game_id']))
    result_by_id = {}
    now = datetime.now(timezone.utc)
    for sha, r in results:
        for g in r['games']:
            gid = str(g['id'])
            if gid not in forecasts:
                continue
            stamp = r.get('observations', {}).get(gid, r['retrieved_at'])
            game, _, bundle = forecasts[gid]
            if verified_final(g, game, bundle, stamp, now):
                y = int(g['home_team_score'] > g['visitor_team_score'])
                if gid in result_by_id and result_by_id[gid][0] != y:
                    raise ValueError('Conflicting final result')
                result_by_id[gid] = (y, sha)
    rows = []
    for gid, u in sorted(universe.items()):
        row = dict(game_id=gid, schedule_identity=u['identity'], eligible=u['eligible'],
                   schedule_archives=schedule_sources.get(gid, []), status='missing_forecast',
                   no_trade=True, historically_selected=gid in selected_games,
                   eligibility_unknown=u.get('eligibility_unknown', False),
                   injury_status='unavailable_asof_player_status_unverified')
        rows.append(row)
        if gid not in forecasts or not u['eligible']:
            if not u['eligible']:
                row['status'] = 'historical_game_without_pregame_schedule' if u.get('eligibility_unknown') else 'schedule_ineligible'
            continue
        game, archive, bundle = forecasts[gid]
        row.update(archive=archive, date=game['date'], elo=float(game['home_win_probability']))
        attempts, matches = Counter(), []
        for sha, snap in snapshots:
            # Retain failed attempts but never pick a later quote based on outcomes/edge.
            for schedule_sha, schedule in schedules:
                if schedule.get('requested_date') != game['date']:
                    continue
                try:
                    pair = paired(game, bundle, snap, schedule)
                    pair.update(snapshot=sha, schedule=schedule_sha, snapshot_started_at=snap['started_at'])
                    matches.append(pair)
                except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
                    attempts[str(exc) if isinstance(exc, ValueError) else type(exc).__name__] += 1
        row['failed_pair_attempts'] = dict(attempts)
        row['valid_pair_observations'] = len(matches)
        if not matches:
            row['status'] = 'missing_valid_asof_quote'
            continue
        row.update(min(matches, key=lambda r: (timestamp(r['decision_at']), r['snapshot'], r['schedule'])))
        row['status'] = 'matched'
        if gid in result_by_id:
            row['outcome'], row['result_snapshot'] = result_by_id[gid]
        row['paper_scenario'] = hypothetical(row, fees)
    paired_rows = [r for r in rows if r['status'] == 'matched']
    scored = [r for r in paired_rows if 'outcome' in r]
    calibration = {}
    for label in ('elo', 'market'):
        calibration[label] = []
        for i in range(10):
            subset = [r for r in scored if min(9, int(r[label]*10)) == i]
            calibration[label].append(dict(lower=i/10, upper=(i+1)/10, n=len(subset),
                mean_probability=sum(r[label] for r in subset)/len(subset) if subset else None,
                observed_home_win_rate=sum(r['outcome'] for r in subset)/len(subset) if subset else None))
    bins = []
    for lo, hi in [(0, .03), (.03, .08), (.08, .15), (.15, 1.01)]:
        subset = [r for r in scored if lo <= abs(r['elo']-r['market']) < hi]
        bins.append(dict(lower=lo, upper=hi, **metrics(subset)))
    pnl_rows = [r for r in paired_rows if r['paper_scenario'].get('pnl') is not None]
    daily = {}
    for r in rows:
        day = r.get('date') or (r['schedule_identity'][0] if r['schedule_identity'] else 'unknown')
        daily.setdefault(day, Counter())[r['status']] += 1
    dates = sorted({u['identity'][0] for u in universe.values() if u['identity']})
    gaps = []
    if dates:
        current = date.fromisoformat(dates[0])
        while current <= date.fromisoformat(dates[-1]):
            if current.isoformat() not in dates:
                gaps.append(current.isoformat())
            current += timedelta(days=1)
    return dict(schema='nba-v09-research-v1', generated_at=now.isoformat(), paper_only=True,
        policy=POLICY, rows=rows, counts=dict(universe=len(rows), eligible=sum(r['eligible'] for r in rows),
        sealed_forecasts=len(forecasts), matched=len(paired_rows), scored=len(scored),
        missing_forecast=sum(r['status']=='missing_forecast' for r in rows),
        missing_valid_asof_quote=sum(r['status']=='missing_valid_asof_quote' for r in rows),
        admitted_paper_trades=0), daily={k: dict(v) for k,v in sorted(daily.items())},
        matched_metrics=metrics(scored), calibration=calibration, disagreement_bins=bins,
        schedule_date_coverage=dict(first=dates[0] if dates else None, last=dates[-1] if dates else None,
            archived_dates=dates, dates_without_schedule_evidence=gaps),
        historical_inventory_crosscheck=dict(games=len(history_games), missing_from_pregame_universe=history_missing,
            caveat='Same provider; later history is discovery only, not proof of pregame eligibility or independent completeness.'),
        selection_bias_audit={label: dict(total=sum(r['historically_selected']==selected for r in rows),
            matched=sum(r['historically_selected']==selected for r in paired_rows),
            **metrics([r for r in scored if r['historically_selected']==selected]))
            for label, selected in [('historically_selected', True), ('not_selected', False)]},
        quality_flag_counts=dict(Counter(flag for r in paired_rows for flag in r['flags'])),
        paper_scenario_statuses=dict(Counter(r['paper_scenario']['status'] for r in paired_rows)),
        hypothetical_fee_adjusted_pnl=dict(settled_scenarios=len(pnl_rows),
            net=str(sum((D(r['paper_scenario']['pnl']) for r in pnl_rows), D(0)))),
        source_inventory=dict(snapshots=len(snapshots), schedules=len(schedules), fees=len(fees), results=len(results)),
        limits=['Universe is archived schedule union, not proof of complete NBA season coverage; missing dates unknown.',
        'Archive/snapshot availability can be selective; matched subset is not representative by assumption.',
        'Earliest valid complete capture after seal, canonical home contract midpoint; not a closing line or fill.',
        'Scores use identical games; descriptive only, no independence or edge significance claim.',
        'Hypothetical one-contract scenarios omit portfolio limits and require verified fees; no fills guaranteed.',
        'Player injury availability remains unverified; all admissions blocked. SportsDataIO excluded.'])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--forecast-root', default='forward_test/state')
    p.add_argument('--market-root', default='paper_v08/state')
    p.add_argument('--additional-market-root')
    p.add_argument('--output', default='research/nba_v09/audit.json')
    a = p.parse_args()
    report = audit(a.forecast_root, a.market_root, a.additional_market_root)
    immutable(a.output, encode(report))
    print(json.dumps({k: report[k] for k in ('counts', 'matched_metrics', 'hypothetical_fee_adjusted_pnl')}))
