"""NBA v0.8 paper-only bridge. Consumes sealed data; never sends an order."""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from kalshi_orderbook import quote_from_orderbook
from nba_forward_test import predictions
from nba_v08_capture import capture, get
from nba_v08_valuation import timestamp, value, TEAMS, ALIASES
from paper_engine import PaperEngine


def process_snapshot(snapshot_path, forecast_root, ledger_path, series, *, now=None):
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
    engine = PaperEngine(ledger_path)
    summary = {'games':len(games),'matched_signals':0,'entries':0,'rejected':0,'snapshot':snapshot_sha}
    try:
        for gid, (game, archive, manifest) in sorted(games.items()):
            decision_time = now or datetime.now(timezone.utc)
            if not 0 <= (decision_time - timestamp(snap['started_at'])).total_seconds() <= 30:
                summary['rejected'] += 1
                continue
            if timestamp(manifest['observed_at']) > timestamp(snap['started_at']) or timestamp(snap['started_at']) >= timestamp(game['tipoff_utc']):
                continue
            eligible = []
            for market in snap['markets']:
                ticker = market.get('ticker')
                book = snap['orderbooks'].get(ticker)
                if not book or ticker in snap['errors']:
                    continue
                try:
                    observed = timestamp(book['observed_at'])
                    received = timestamp(book['received_at'])
                    if not timestamp(snap['started_at']) <= observed <= received <= timestamp(snap['completed_at']):
                        continue
                    quote = quote_from_orderbook(ticker, book['raw'], book['observed_at'])
                    signal = value(game, market, quote, series, now=decision_time)
                    if signal:
                        eligible.append((Decimal(signal['net_edge']), ticker, signal, market, quote))
                except (KeyError, ValueError, TypeError, ArithmeticError):
                    continue
            if not eligible:
                summary['rejected'] += 1
                continue
            _, ticker, signal, market, quote = max(eligible, key=lambda x:(x[0],x[1]))
            summary['matched_signals'] += 1
            evidence = {'game_id':gid, 'archive':archive, 'forecast':game, 'snapshot_sha256':snapshot_sha,
                        'market':market, 'quote':quote, 'series':series, 'signal':signal,
                        'decision_at':decision_time.isoformat(), 'paper_only':True}
            ok, _ = engine.enter(signal_id='nba-game:'+gid, ticker=ticker, side=signal['side'],
                                 ask=signal['assumed_price'], ask_size=signal['size'], contracts=1,
                                 fee=signal['fee'], day=decision_time.date().isoformat(), evidence=evidence)
            summary['entries'] += int(ok)
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
    series = get('/series/KXNBAGAME')['series']
    now = datetime.now(timezone.utc)
    events = set()
    for game, _, manifest in predictions(forecast_root).values():
        try:
            home = ALIASES.get(game['home_team'], game['home_team'])
            away = ALIASES.get(game['away_team'], game['away_team'])
            if timestamp(manifest['observed_at']) < now < timestamp(game['tipoff_utc']) and home != away:
                date = datetime.strptime(game['date'], '%Y-%m-%d')
                events.add('KXNBAGAME-' + date.strftime('%y%b%d').upper() + TEAMS[away][0] + TEAMS[home][0])
        except (KeyError, ValueError, TypeError):
            continue
    target, _, _, target_errors = capture(root / 'snapshots', event_filter=events)
    entries = process_snapshot(target, forecast_root, ledger, series)
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
              'collection_errors':errors, 'target_collection_errors':target_errors, 'reconciliation':settlement, 'entries':entries,
              'cash':str(account.cash), 'open_cost':str(account.open_exposure), 'settled_trades':len(settled),
              'realized_equity':str(equity), 'max_realized_drawdown':str(max_drawdown), 'bankroll_history':history, 'open_positions':positions,
              'generated_at':datetime.now(timezone.utc).isoformat()}
    report = root / 'latest.json'
    temp = root / 'latest.json.tmp'
    temp.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    temp.replace(report)
    print(json.dumps(result, sort_keys=True))
    if errors or target_errors or settlement['errors']:
        raise RuntimeError('Incomplete data; inspect paper report')
    return result

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-dir', default='paper_v08/state')
    p.add_argument('--forecast-root', default='forward_test/state')
    args = p.parse_args()
    cycle(args.state_dir, args.forecast_root)
