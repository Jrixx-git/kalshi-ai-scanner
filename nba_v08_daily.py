"""Audit paper positions and publish a public-data, cost-basis daily report."""
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from nba_forward_test import immutable, predictions
from nba_v08_capture import get
from nba_v08_schedule import verify
from nba_v08_valuation import match, timestamp, taker_fee
from kalshi_orderbook import quote_from_orderbook

D=Decimal

def fee_history(event, fetch=get):
    pages=[]; cursor=None; seen=set()
    for _ in range(100):
        params={'event_ticker':event,'limit':100}
        if cursor: params['cursor']=cursor
        page=fetch('/events/fee_changes',params)
        if not isinstance(page.get('event_fee_changes'),list): raise ValueError('Invalid fee history')
        if any(x.get('event_ticker')!=event for x in page['event_fee_changes']): raise ValueError('Wrong event fee history')
        pages.append(page); cursor=page.get('cursor')
        if not cursor:return pages
        if cursor in seen: raise ValueError('Repeated fee cursor')
        seen.add(cursor)
    raise ValueError('Fee history pagination limit')


def publish(root, report):
    raw=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    sha=hashlib.sha256(raw).hexdigest(); root=Path(root)
    immutable(root/'audits'/(sha+'.json'),raw)
    temp=root/'daily.json.tmp'; temp.write_bytes(raw); temp.replace(root/'daily.json')
    return sha


def current_evidence(ticker, fetch):
    observed=datetime.now(timezone.utc).isoformat()
    market=fetch('/markets/'+ticker)['market']
    book=fetch('/markets/'+ticker+'/orderbook',{'depth':1})
    received=datetime.now(timezone.utc).isoformat()
    pages=fee_history(ticker.rsplit('-',1)[0],fetch)
    return {'market':market,'orderbook':book,'fee_change_pages':pages,'request_started_at':observed,
            'book_received_at':received,'fee_observed_at':datetime.now(timezone.utc).isoformat()}


def run(root='paper_v08/state', forecast_root='forward_test/state', *, fetch=get):
    root=Path(root); forecasts=predictions(forecast_root)
    latest=json.loads((root/'latest.json').read_text())
    db=sqlite3.connect(root/'ledger.sqlite3')
    rows=db.execute('SELECT t.signal_id,t.ticker,t.side,t.price,t.contracts,t.fee,t.status,t.pnl,e.entry_json,e.settlement_json FROM trades t LEFT JOIN paper_evidence e ON t.signal_id=e.signal_id ORDER BY t.signal_id').fetchall(); db.close()
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={ticker:pool.submit(current_evidence,ticker,fetch) for _,ticker,_,_,_,_,status,_,_,_ in rows if status=='OPEN'}
    ids=Counter(); events=Counter(); team_cost=defaultdict(lambda:D(0)); positions=[]; errors=[]; totals=D(0); marks=D(0); complete_mark=True
    for sid,ticker,side,price,n,fee,status,pnl,entry,settlement in rows:
        try:
            e=json.loads(entry); game=e['forecast']; event=e['market']['event_ticker']; ids[game['game_id']]+=1; events[event]+=1
            entry_cost=D(price)*n+D(fee)
            if status=='OPEN':
                totals+=entry_cost
                for team in (game['home_team'],game['away_team']):team_cost[team]+=entry_cost
            sp=root/'snapshots'/(e['snapshot_sha256']+'.json'); sr=sp.read_bytes()
            ep=root/'schedules'/(e['schedule_sha256']+'.json'); er=ep.read_bytes()
            if hashlib.sha256(sr).hexdigest()!=e['snapshot_sha256'] or hashlib.sha256(er).hexdigest()!=e['schedule_sha256']:raise ValueError('Evidence digest mismatch')
            snap=json.loads(sr); schedule=json.loads(er); now=timestamp(e['decision_at'])
            chosen=forecasts.get(game['game_id'])
            if not chosen or chosen[1]!=e['archive'] or chosen[0]!=game:raise ValueError('First forecast differs')
            if timestamp(chosen[2]['observed_at']) > timestamp(snap['started_at']) or now >= timestamp(game['tipoff_utc']):raise ValueError('Late forecast or entry')
            verify(game,schedule,now); match(game,e['market'],schedule=schedule,now=now)
            book=snap['orderbooks'][ticker]; quote=quote_from_orderbook(ticker,book['raw'],book['observed_at'])
            ask=D(quote[side.lower()+'_ask']); age=(now-timestamp(book['observed_at'])).total_seconds()
            if not 0<=age<=30 or n>quote[side.lower()+'_ask_size'] or D(price)!=ask+D('.01') or D(fee)!=taker_fee(price,n,1):raise ValueError('Entry depth, quote, price or fee mismatch')
            p={'signal_id':sid,'ticker':ticker,'side':side,'status':status,'entry_cost':str(entry_cost),'original_ask':str(ask),'displayed_depth':quote[side.lower()+'_ask_size'],'quote_age_seconds':age,'fee_estimate':fee,'entry_verified':True,'pnl':pnl,'fee_verification':'estimate; event fee history not captured at entry'}
            if status=='OPEN':
                try:
                    raw=futures[ticker].result(); market=raw['market']; booknow=raw['orderbook']; received=raw['book_received_at']; pages=raw['fee_change_pages']
                    if market.get('ticker')!=ticker:raise ValueError('Current market mismatch')
                    blob=(json.dumps(raw,sort_keys=True,indent=2,allow_nan=False)+'\n').encode(); sha=hashlib.sha256(blob).hexdigest(); immutable(root/'audit_snapshots'/(sha+'.json'),blob)
                    p.update(market_status=market.get('status'),market_result=market.get('result'),current_evidence_sha256=sha,fee_changes_returned=sum(len(z['event_fee_changes']) for z in pages))
                    if market.get('status')=='finalized': p['action']='awaiting next reconciliation'
                    levels=booknow['orderbook_fp'][side.lower()+'_dollars']; parsed=[(D(str(x[0])),D(str(x[1]))) for x in levels]; eligible=[(a,b) for a,b in parsed if a.is_finite() and b.is_finite() and D(0)<a<D(1) and b>=n]
                    if market.get('status')=='active' and eligible:
                        bid=max(eligible)[0]; val=bid*n-entry_cost; marks+=val
                        p.update(mark_bid=str(bid),mark_observed_at=received,unrealized_before_exit_fee=str(val))
                    else:complete_mark=False
                except (OSError,ValueError,KeyError,TypeError,ArithmeticError) as exc:
                    complete_mark=False; p['current_error']=type(exc).__name__; errors.append(sid+':'+type(exc).__name__)
            elif status=='SETTLED':
                if not settlement: raise ValueError('Missing settlement evidence')
                p['settlement']=json.loads(settlement)
            positions.append(p)
        except (ValueError,KeyError,TypeError,ArithmeticError,OSError) as exc:
            errors.append(sid+':'+type(exc).__name__)
            positions.append({'signal_id':sid,'ticker':ticker,'status':status,'entry_verified':False,'error':type(exc).__name__})
            if status=='OPEN':complete_mark=False
    if any(n>1 for n in ids.values()) or any(n>1 for n in events.values()):errors.append('duplicate game or event')
    rejected=[{'game_id':x.get('game_id'),'reason':x.get('reason')} for x in latest['entries']['decisions'] if x.get('reason')!='paper_entry']
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'paper_only':True,'positions':positions,'rejected':rejected,'errors':errors,
            'open_positions':sum(x[6]=='OPEN' for x in rows),'settled_positions':sum(x[6]=='SETTLED' for x in rows),
            'recorded_open_cost':str(totals),'realized_pnl':str(sum((D(x[7]) for x in rows if x[6]=='SETTLED'),D(0))),
            'cash':latest['cash'],'realized_equity':latest['realized_equity'],'gross_unrealized_before_exit_fee':str(marks) if complete_mark else None,
            'team_cost_exposure':{k:str(v) for k,v in sorted(team_cost.items())},'duplicate_games':[k for k,v in ids.items() if v>1],
            'duplicate_events':[k for k,v in events.items() if v>1],
            'notes':'Cost risk assumes full stake loss and recorded entry fees; prices are observations, not guaranteed fills. Open marks omit exit fees and are not realized P&L. Cross-game dependence is not quantified.'}
    sha=publish(root,report); print(json.dumps({'report_sha256':sha,'open':report['open_positions'],'settled':report['settled_positions'],'errors':errors}))
    if errors:raise RuntimeError('Daily audit incomplete')
    return report

if __name__=='__main__':run()
