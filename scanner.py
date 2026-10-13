"""Read-only Kalshi market scanner and paper-trade journal. No order endpoints."""
import argparse, csv, datetime as dt, json, pathlib, time, urllib.parse, urllib.request
BASE = 'https://api.elections.kalshi.com/trade-api/v2'
ROOT = pathlib.Path(__file__).resolve().parent
CATEGORIES = ('sports','crypto','politics','economics')
KEYWORDS = {'sports':('game','nba','nfl','mlb','nhl','football','basketball','baseball','soccer','tennis','win the match'), 'crypto':('bitcoin','ethereum','btc','eth','solana','crypto'), 'politics':('election','president','senate','house','governor','congress','vote'), 'economics':('inflation','cpi','fed','interest rate','unemployment','gdp','jobs report','recession')}
def fetch(path, params=None):
    url=BASE+path+'?'+urllib.parse.urlencode(params or {})
    req=urllib.request.Request(url,headers={'User-Agent':'PersonalKalshiResearchScanner/0.1'})
    with urllib.request.urlopen(req,timeout=20) as r: return json.load(r)
def category(m):
    s=' '.join(str(m.get(k,'')) for k in ('title','subtitle','ticker','event_ticker')).lower()
    for c,keys in KEYWORDS.items():
        if any(k in s for k in keys): return c
    return 'other'
def price(m,side):
    for k in (f'{side}_ask_dollars',):
        try:
            v=float(m.get(k));
            if 0<v<1:return v
        except (TypeError,ValueError): pass
    return None
def scan(pages):
    cursor=None; results=[]; seen=set()
    for _ in range(pages):
        args={'status':'open','limit':200,'mve_filter':'exclude'}
        if cursor: args['cursor']=cursor
        data=fetch('/markets',args)
        for m in data.get('markets',[]):
            ticker=m.get('ticker')
            if not ticker or ticker in seen:continue
            seen.add(ticker)
            c=category(m)
            if c not in CATEGORIES:continue
            results.append({'ticker':ticker,'category':c,'title':m.get('title',''),'yes_ask':price(m,'yes'),'no_ask':price(m,'no'),'volume':m.get('volume_fp',''),'close_time':m.get('close_time','')})
        cursor=data.get('cursor')
        if not cursor:break
        time.sleep(.25)
    return results
def save_csv(path,rows,fields):
    with open(path,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def load_estimates(path):
    if not path.exists():return {}
    with open(path,newline='',encoding='utf-8') as f:
        return {r['ticker']:float(r['estimated_yes_probability']) for r in csv.DictReader(f) if r.get('estimated_yes_probability')}
def opportunities(rows,estimates,fee_buffer):
    out=[]
    for r in rows:
        p=estimates.get(r['ticker'])
        if p is None or not 0<=p<=1:continue
        for side,prob in (('YES',p),('NO',1-p)):
            ask=r[side.lower()+'_ask']
            if ask is None:continue
            ev=prob-ask-fee_buffer
            if ev>0:out.append({**r,'side':side,'estimated_probability':round(prob,4),'entry_price':ask,'assumed_cost_buffer':fee_buffer,'estimated_net_ev_per_contract':round(ev,4)})
    return sorted(out,key=lambda x:x['estimated_net_ev_per_contract'],reverse=True)
def main():
    p=argparse.ArgumentParser(description='Kalshi research scanner: read-only + manual paper journal')
    p.add_argument('--pages',type=int,default=3);p.add_argument('--fee-buffer',type=float,default=.02)
    p.add_argument('--paper',action='store_true',help='Record a simulated trade, never send an order')
    p.add_argument('--ticker');p.add_argument('--side',choices=['YES','NO']);p.add_argument('--price',type=float);p.add_argument('--contracts',type=int,default=1)
    a=p.parse_args()
    if a.paper:
        if not a.ticker or not a.side or a.price is None or not 0<a.price<1 or a.contracts<1:p.error('Paper trade needs --ticker --side --price (0..1) and positive --contracts')
        path=ROOT/'paper_trades.csv'; fields=['timestamp_utc','ticker','side','price','contracts','simulated_cost','status','settlement','realized_pnl']
        old=list(csv.DictReader(path.open(newline='',encoding='utf-8'))) if path.exists() else []
        old.append({'timestamp_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'ticker':a.ticker,'side':a.side,'price':a.price,'contracts':a.contracts,'simulated_cost':round(a.price*a.contracts,2),'status':'OPEN','settlement':'','realized_pnl':''})
        save_csv(path,old,fields);print('Recorded PAPER trade only:',path);return
    rows=scan(max(1,min(a.pages,25)))
    fields=['ticker','category','title','yes_ask','no_ask','volume','close_time']
    save_csv(ROOT/'markets.csv',rows,fields)
    estimates=load_estimates(ROOT/'estimates.csv')
    opps=opportunities(rows,estimates,max(0,a.fee_buffer))
    save_csv(ROOT/'opportunities.csv',opps,fields+['side','estimated_probability','entry_price','assumed_cost_buffer','estimated_net_ev_per_contract'])
    print(f'Scanned {len(rows)} candidate markets. {len(opps)} positive modeled EV candidates.')
    print('Market data:',ROOT/'markets.csv');print('Opportunities:',ROOT/'opportunities.csv')
    if not estimates:print('No independent probability estimates yet. Add ticker,estimated_yes_probability to estimates.csv; market prices alone cannot establish EV.')
    for o in opps[:10]:print(o['category'],o['ticker'],o['side'],'EV',o['estimated_net_ev_per_contract'])
if __name__=='__main__':main()
