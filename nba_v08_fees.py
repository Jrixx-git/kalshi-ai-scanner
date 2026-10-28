"""Read-only event fee evidence; fail closed on ambiguous or stale schedules."""
import hashlib,json
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from nba_forward_test import immutable
from nba_v08_valuation import timestamp
from nba_v08_capture import get
from nba_v08_daily import fee_history


def capture(event,root,series,series_observed_at,fetch=get):
    started=datetime.now(timezone.utc).isoformat()
    data=fetch('/events/'+event,{'exclude_markets':'true'})['event']
    pages=fee_history(event,fetch)
    received=datetime.now(timezone.utc).isoformat()
    record={'event_ticker':event,'series':series,'series_observed_at':series_observed_at,
            'event':data,'pages':pages,'requested_at':started,'received_at':received}
    raw=(json.dumps(record,sort_keys=True,indent=2,allow_nan=False)+'\n').encode(); sha=hashlib.sha256(raw).hexdigest()
    path=Path(root)/(sha+'.json'); immutable(path,raw); return path


def effective(record,event,now):
    start=timestamp(record['requested_at']); end=timestamp(record['received_at']); series_time=timestamp(record['series_observed_at'])
    if record['event_ticker']!=event or not series_time<=start<=end<=now or (now-series_time).total_seconds()>300:
        raise ValueError('Stale or mismatched fee evidence')
    s=record['series']; data=record['event']; pages=record['pages']
    if s.get('ticker')!='KXNBAGAME' or data.get('event_ticker')!=event or data.get('series_ticker')!='KXNBAGAME':raise ValueError('Fee identity mismatch')
    if s.get('last_updated_ts') and timestamp(s['last_updated_ts'])>series_time:raise ValueError('Series changed after request')
    if not isinstance(pages,list) or not pages:raise ValueError('Missing fee history')
    changes=[]
    for i,page in enumerate(pages):
        if not isinstance(page.get('event_fee_changes'),list) or not isinstance(page.get('cursor'),str):raise ValueError('Invalid fee history')
        if i<len(pages)-1 and not page.get('cursor'):raise ValueError('Incomplete fee history')
        if i==len(pages)-1 and page.get('cursor'):raise ValueError('Incomplete fee history')
        for x in page['event_fee_changes']:
            if x.get('event_ticker')!=event or x.get('series_ticker')!='KXNBAGAME':raise ValueError('Fee history identity mismatch')
            t=timestamp(x['scheduled_ts'])
            if start < t <= now:raise ValueError('Fee changed during observation')
            if t<=now:changes.append((t,x))
    current=(data.get('fee_type_override'),data.get('fee_multiplier_override'))
    if (current[0] is None)!=(current[1] is None):raise ValueError('Incomplete fee override')
    if changes:
        changes.sort(key=lambda x:x[0]); t,x=changes[-1]
        if len(changes)>1 and changes[-2][0]==t:raise ValueError('Ambiguous fee changes')
        if (x.get('fee_type_override'),x.get('fee_multiplier_override'))!=current:raise ValueError('Fee override conflict')
    typ,mult=current if current[0] is not None else (s.get('fee_type'),s.get('fee_multiplier'))
    mult=Decimal(str(mult))
    if typ not in ('quadratic','quadratic_with_maker_fees') or not mult.is_finite() or not Decimal(0)<mult<=Decimal(10):raise ValueError('Unsupported fee schedule')
    return {'ticker':'KXNBAGAME','fee_type':typ,'fee_multiplier':str(mult),'source':'event' if current[0] is not None else 'series'}
