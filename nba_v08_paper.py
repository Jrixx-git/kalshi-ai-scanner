"""NBA v0.8 paper-only bridge. Consumes sealed data; never sends an order."""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from kalshi_orderbook import quote_from_orderbook
from nba_forward_test import predictions, immutable
from nba_v08_capture import capture, get
from nba_v08_valuation import timestamp, value, match, taker_fee, TEAMS, ALIASES
from nba_v08_schedule import capture_schedule, verify
from nba_v08_fees import capture as capture_fee, effective as effective_fee
from paper_engine import PaperEngine


def save_report(root, result):
    root = Path(root)
    report = root / 'latest.json'
    temp = root / 'latest.json.tmp'
    if report.exists():
        prior = report.read_bytes()
        immutable(root / 'reports' / (hashlib.sha256(prior).hexdigest()+'.json'), prior)
    encoded = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()
    immutable(root / 'reports' / (hashlib.sha256(encoded).hexdigest()+'.json'), encoded)
    temp.write_bytes(encoded)
    temp.replace(report)


def process_snapshot(snapshot_path, forecast_root, ledger_path, series, *, schedule_paths=None, fee_paths=None, now=None):
    """Evaluate immutable snapshots against the first sealed v0.7 forecast per game."""
    initial_now = now or datetime.now(timezone.utc)
    path = Path(snapshot_path)
    data = path.read_bytes()
    snapshot_sha = hashlib.sha256(data).hexdigest()
    if path.stem != snapshot_sha:
        raise ValueError('Snapshot digest mismatch')
    snap = json.loads(data)
    if snap.get('schema') != 'nba-kalshi-capture-v1' or snap.get('live_trading') is not False or snap.get('series') != 'KXNBAGAME':
        raise ValueError('Invalid snapshot')
    if timestamp(snap['completed_at']) > initial_now or timestamp(snap['started_at']) > timestamp(snap['completed_at']):
        raise ValueError('Invalid snapshot timestamps')
    games = predictions(forecast_root)
    game_keys = {}
    for gid, (game, _, _) in games.items():
        try:
            key = (game['date'], *sorted((str(game['home_team_id']), str(game['away_team_id']))))
            game_keys.setdefault(key, []).append(gid)
        except KeyError:
            continue
    schedules = {}
    fees = {}
    for event, fee_path in (fee_paths or {}).items():
        p=Path(fee_path); raw=p.read_bytes(); digest=hashlib.sha256(raw).hexdigest()
        if p.stem!=digest:raise ValueError('Fee evidence digest mismatch')
        fees[event]=(json.loads(raw),digest)
    for date, schedule_path in (schedule_paths or {}).items():
        p = Path(schedule_path); raw = p.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
        if p.stem != digest: raise ValueError('Schedule digest mismatch')
        schedules[date] = (json.loads(raw), digest)
    engine = PaperEngine(ledger_path)
    summary = {'games':len(games),'matched_signals':0,'entries':0,'rejected':0,'snapshot':snapshot_sha,'decisions':[]}
    try:
        for gid, (game, archive, manifest) in sorted(games.items()):
            decision_time = now or datetime.now(timezone.utc)
            try:
                key = (game['date'], *sorted((str(game['home_team_id']),str(game['away_team_id']))))
                if len(game_keys[key]) != 1:
                    summary['rejected'] += 1
                    summary['decisions'].append({'game_id':gid,'reason':'duplicate_forecast_identity'})
                    continue
            except KeyError:
                summary['rejected'] += 1
                summary['decisions'].append({'game_id':gid,'reason':'missing_forecast_identity'})
                continue
            if not 0 <= (decision_time - timestamp(snap['started_at'])).total_seconds() <= 30:
                summary['rejected'] += 1
                summary['decisions'].append({'game_id':gid,'reason':'stale_market_snapshot'})
                continue
            if timestamp(manifest['observed_at']) > timestamp(snap['started_at']) or timestamp(snap['started_at']) >= timestamp(game['tipoff_utc']):
                summary['decisions'].append({'game_id':gid,'reason':'late_or_unsealed_forecast'})
                continue
            try:
                forecast_age=(decision_time-timestamp(game['generated_at_utc'])).total_seconds()
                if not 0 <= forecast_age <= 24*3600:
                    raise ValueError('Forecast older than 24 hours or from future')
            except (KeyError,ValueError,TypeError):
                summary['rejected'] += 1
                summary['decisions'].append({'game_id':gid,'reason':'stale_or_invalid_forecast'})
                continue
            try:
                schedule, schedule_hash = schedules[game['date']]
                if timestamp(schedule['received_at']) > timestamp(snap['started_at']): raise ValueError('Schedule observed after market snapshot')
                identity = verify(game, schedule, decision_time)
                home = ALIASES.get(game['home_team'], game['home_team']); away = ALIASES.get(game['away_team'], game['away_team'])
                date = datetime.strptime(game['date'], '%Y-%m-%d')
                event = 'KXNBAGAME-' + date.strftime('%y%b%d').upper() + TEAMS[away][0] + TEAMS[home][0]
                contracts = [m for m in snap['markets'] if m.get('event_ticker') == event]
                required = {event+'-'+TEAMS[home][0], event+'-'+TEAMS[away][0]}
                if len(contracts) != 2 or {m.get('ticker') for m in contracts} != required:
                    raise ValueError('Duplicate, missing or ambiguous contract')
                for market in contracts: match(game, market, schedule=schedule, now=decision_time)
            except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
                summary['rejected'] += 1
                summary['decisions'].append({'game_id':gid,'reason':'identity_rejected','detail':str(exc)})
                continue
            try:
                fee_record, fee_hash=fees[event]
                if timestamp(fee_record['received_at']) > timestamp(snap['started_at']):raise ValueError('Fee evidence after market snapshot')
                applied_series=effective_fee(fee_record,event,decision_time)
            except (KeyError,ValueError,TypeError,ArithmeticError) as exc:
                summary['rejected']+=1
                summary['decisions'].append({'game_id':gid,'reason':'fee_unverified','detail':str(exc),'identity':identity})
                continue
            eligible = []
            assessments = []
            had_book = False; had_positive = False
            for market in contracts:
                ticker = market.get('ticker')
                book = snap['orderbooks'].get(ticker)
                if not book or ticker in snap['errors']:
                    assessments.append({'ticker':ticker,'reason':'orderbook_unavailable','detail':snap['errors'].get(ticker)})
                    continue
                try:
                    observed = timestamp(book['observed_at'])
                    received = timestamp(book['received_at'])
                    if not timestamp(snap['started_at']) <= observed <= received <= timestamp(snap['completed_at']):
                        assessments.append({'ticker':ticker,'reason':'invalid_book_timestamps'})
                        continue
                    quote = quote_from_orderbook(ticker, book['raw'], book['observed_at'])
                    had_book = True
                    selected = match(game, market, schedule=schedule, now=decision_time)
                    hp = Decimal(str(game['home_win_probability']))
                    yes_probability = hp if selected == home else 1-hp
                    info = {'ticker':ticker, 'occurrence_datetime':market.get('occurrence_datetime'), 'quote_age_seconds':(decision_time-observed).total_seconds(), 'sides':[]}
                    for side, probability in [('YES',yes_probability),('NO',1-yes_probability)]:
                        k=side.lower()
                        if k+'_ask' in quote:
                            ask=Decimal(quote[k+'_ask']); assumed=ask+Decimal('.01')
                            item={'side':side,'model_probability':str(probability),'ask':str(ask),'size':quote[k+'_ask_size']}
                            if 0 < assumed < 1:
                                item['net_edge']=str(probability-assumed-taker_fee(assumed,1,applied_series['fee_multiplier']))
                                edge=Decimal(item['net_edge'])
                                item['reason']='eligible' if edge >= Decimal('.03') else ('edge_below_threshold' if edge > 0 else 'nonpositive_net_edge')
                            else:
                                item['reason']='invalid_price_or_fee_schedule'
                            info['sides'].append(item)
                        else:
                            info['sides'].append({'side':side,'model_probability':str(probability),'reason':'no_executable_ask'})
                    assessments.append(info)
                    had_positive = had_positive or value(game, market, quote, applied_series, now=decision_time, schedule=schedule, min_edge=Decimal('0.000001')) is not None
                    signal = value(game, market, quote, applied_series, now=decision_time, schedule=schedule)
                    if signal:
                        eligible.append((Decimal(signal['net_edge']), ticker, signal, market, quote))
                except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
                    assessments.append({'ticker':ticker,'reason':'invalid_market_or_book','detail':type(exc).__name__})
                    continue
            if not eligible:
                summary['rejected'] += 1
                summary['decisions'].append({'game_id':gid,'reason':'no_valid_quote' if not had_book else ('edge_below_threshold' if had_positive else 'no_positive_net_edge_or_invalid_quote'),'identity':identity,'assessments':assessments})
                continue
            _, ticker, signal, market, quote = max(eligible, key=lambda x:(x[0],x[1]))
            summary['matched_signals'] += 1
            evidence = {'game_id':gid, 'archive':archive, 'forecast':game, 'snapshot_sha256':snapshot_sha,
                        'market':market, 'quote':quote, 'series':applied_series, 'signal':signal, 'fee_evidence_sha256':fee_hash,
                        'schedule_sha256':schedule_hash, 'schedule_identity':identity,
                        'decision_at':decision_time.isoformat(), 'paper_only':True}
            ok, reason = engine.enter(signal_id='nba-game:'+gid, ticker=ticker, side=signal['side'],
                                 ask=signal['assumed_price'], ask_size=signal['size'], contracts=1,
                                 fee=signal['fee'], day=decision_time.date().isoformat(), evidence=evidence)
            summary['entries'] += int(ok)
            for assessment in assessments:
                for item in assessment.get('sides', []):
                    if item.get('reason') == 'eligible':
                        selected = assessment.get('ticker') == ticker and item['side'] == signal['side']
                        item['reason'] = ('paper_entry' if ok else 'risk_or_duplicate_rejection: '+reason) if selected else 'not_selected_lower_or_tied_edge'
            summary['decisions'].append({'game_id':gid,'ticker':ticker,'identity':identity,'signal':signal,'assessments':assessments,'reason':'paper_entry' if ok else reason})
        return summary
    finally:
        engine.close()


def reconcile(ledger_path, *, fetch=get):
    engine = PaperEngine(ledger_path)
    result = {'checked':0, 'settled':0, 'pending':0, 'errors':0}
    try:
        rows = engine.db.execute("SELECT signal_id,ticker FROM trades WHERE status='OPEN' AND signal_id IN (SELECT signal_id FROM paper_evidence)").fetchall()
        for signal_id, ticker in rows:
            result['checked'] += 1
            try:
                observed = datetime.now(timezone.utc).isoformat()
                market = fetch('/markets/'+ticker)['market']
                received = datetime.now(timezone.utc).isoformat()
                if market.get('status') != 'finalized':
                    result['pending'] += 1
                    continue
                ok, _ = engine.settle_finalized_market(signal_id, market, received)
                result['settled' if ok else 'errors'] += 1
            except (OSError, ValueError, KeyError, TypeError):
                result['errors'] += 1
        return result
    finally:
        engine.close()


def cycle(root, forecast_root='forward_test/state'):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    ledger = root / 'ledger.sqlite3'
    settlement = reconcile(ledger)
    path, markets, books, errors = capture(root / 'snapshots')
    series_observed_at=datetime.now(timezone.utc).isoformat()
    series = get('/series/KXNBAGAME')['series']
    now = datetime.now(timezone.utc)
    events = set()
    dates = set()
    for game, _, manifest in predictions(forecast_root).values():
        try:
            home = ALIASES.get(game['home_team'], game['home_team'])
            away = ALIASES.get(game['away_team'], game['away_team'])
            if timestamp(manifest['observed_at']) < now < timestamp(game['tipoff_utc']) and home != away:
                date = datetime.strptime(game['date'], '%Y-%m-%d')
                events.add('KXNBAGAME-' + date.strftime('%y%b%d').upper() + TEAMS[away][0] + TEAMS[home][0])
                dates.add(game['date'])
        except (KeyError, ValueError, TypeError):
            continue
    schedule_paths = {date:capture_schedule(date, root / 'schedules') for date in sorted(dates)}
    fee_paths={}; fee_errors={}
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending={pool.submit(capture_fee,event,root/'fees',series,series_observed_at):event for event in events}
        for future in as_completed(pending):
            event=pending[future]
            try:fee_paths[event]=future.result()
            except (OSError,ValueError,KeyError,TypeError) as exc:fee_errors[event]=type(exc).__name__
    target, _, _, target_errors = capture(root / 'snapshots', event_filter=events)
    entries = process_snapshot(target, forecast_root, ledger, series, schedule_paths=schedule_paths, fee_paths=fee_paths)
    engine = PaperEngine(ledger)
    try:
        account = engine.account()
        settled = engine.db.execute("SELECT t.signal_id,t.pnl,e.settlement_json FROM trades t JOIN paper_evidence e ON t.signal_id=e.signal_id WHERE t.status='SETTLED'").fetchall()
        settled.sort(key=lambda row: (timestamp(json.loads(row[2])['observed_at']), row[0]))
        equity = peak = Decimal('5000')
        max_drawdown = Decimal('0')
        history = []
        for signal_id, pnl, evidence in settled:
            equity += Decimal(pnl)
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, peak-equity)
            history.append({'signal_id':signal_id, 'settled_at':json.loads(evidence)['observed_at'], 'realized_pnl':pnl, 'equity':str(equity)})
        positions = [dict(zip(('signal_id','ticker','side','price','contracts','fee','opened_day'), row)) for row in
                     engine.db.execute("SELECT signal_id,ticker,side,price,contracts,fee,opened_day FROM trades WHERE status='OPEN' ORDER BY signal_id")]
    finally:
        engine.close()
    result = {'paper_only':True, 'snapshot':str(path), 'target_snapshot':str(target), 'markets':markets, 'books':books,
              'collection_errors':errors, 'target_collection_errors':target_errors, 'fee_capture_errors':fee_errors, 'reconciliation':settlement, 'entries':entries,
              'cash':str(account.cash), 'open_cost':str(account.open_exposure), 'settled_trades':len(settled),
              'realized_equity':str(equity), 'max_realized_drawdown':str(max_drawdown), 'bankroll_history':history, 'open_positions':positions,
              'generated_at':datetime.now(timezone.utc).isoformat()}
    save_report(root, result)
    print(json.dumps(result, sort_keys=True))
    if errors or target_errors or fee_errors or settlement['errors']:
        raise RuntimeError('Incomplete data; inspect paper report')
    return result

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-dir', default='paper_v08/state')
    p.add_argument('--forecast-root', default='forward_test/state')
    args = p.parse_args()
    cycle(args.state_dir, args.forecast_root)
