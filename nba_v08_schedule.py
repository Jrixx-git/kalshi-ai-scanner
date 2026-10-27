"""Read-only independent NBA schedule evidence from Kalshi's ESPN settlement source."""
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from nba_v08_valuation import ALIASES, timestamp

ESPN_IDS = dict(ATL=1,BOS=2,BKN=17,CHA=30,CHI=4,CLE=5,DAL=6,DEN=7,DET=8,GSW=9,HOU=10,IND=11,LAC=12,LAL=13,MEM=29,MIA=14,MIL=15,MIN=16,NOP=3,NYK=18,OKC=25,ORL=19,PHI=20,PHX=21,POR=22,SAC=23,SAS=24,TOR=28,UTA=26,WAS=27)
BDL_IDS = dict(ATL=1,BOS=2,BKN=3,CHA=4,CHI=5,CLE=6,DAL=7,DEN=8,DET=9,GSW=10,HOU=11,IND=12,LAC=13,LAL=14,MEM=15,MIA=16,MIL=17,MIN=18,NOP=19,NYK=20,OKC=21,ORL=22,PHI=23,PHX=24,POR=25,SAC=26,SAS=27,TOR=28,UTA=29,WAS=30)
BASE = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates='


def capture_schedule(date, root):
    datetime.strptime(date,'%Y-%m-%d')
    observed = datetime.now(timezone.utc).isoformat()
    req = urllib.request.Request(BASE+date.replace('-',''), headers={'User-Agent':'NBA-Paper-Research/0.8'}, method='GET')
    with urllib.request.urlopen(req,timeout=20) as r:
        payload = json.load(r)
    obj = {'schema':'espn-nba-schedule-v1','requested_date':date,'requested_at':observed,
           'received_at':datetime.now(timezone.utc).isoformat(),'source':BASE+date.replace('-',''),'payload':payload}
    data = (json.dumps(obj,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    sha=hashlib.sha256(data).hexdigest(); path=Path(root)/(sha+'.json'); path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open('xb') as f: f.write(data)
    except FileExistsError:
        if path.read_bytes()!=data: raise ValueError('Schedule archive conflict')
    return path


def verify(game, evidence, now):
    """Require a fresh schedule, unique event, exact team IDs, tipoff and pregame state."""
    home=ALIASES.get(game['home_team'],game['home_team']); away=ALIASES.get(game['away_team'],game['away_team'])
    if home==away or home not in ESPN_IDS or away not in ESPN_IDS:
        raise ValueError('Unknown teams')
    if int(game['home_team_id']) != BDL_IDS[home] or int(game['away_team_id']) != BDL_IDS[away]:
        raise ValueError('BALLDONTLIE team IDs mismatch')
    date=game['date']; datetime.strptime(date,'%Y-%m-%d')
    if evidence.get('schema')!='espn-nba-schedule-v1' or evidence.get('requested_date')!=date or evidence.get('source')!=BASE+date.replace('-',''):
        raise ValueError('Schedule source or date mismatch')
    request, receipt=timestamp(evidence['requested_at']),timestamp(evidence['received_at'])
    age=(now-request).total_seconds()
    if receipt < request or receipt > now or not 0 <= age <= 300:
        raise ValueError('Stale schedule')
    events=evidence['payload']['events']
    if not isinstance(events,list): raise ValueError('Invalid schedule')
    found=[]
    for event in events:
        comps=event.get('competitions',[])
        if not isinstance(comps,list) or len(comps)!=1: continue
        sides=comps[0].get('competitors',[])
        if not isinstance(sides,list) or len(sides)!=2: continue
        by_side={s.get('homeAway'):s.get('team',{}) for s in sides}
        if set(by_side)!= {'home','away'}: continue
        def valid(t, code):
            abbr=t.get('abbreviation'); normalized=ALIASES.get(abbr,abbr)
            return normalized==code and str(t.get('id'))==str(ESPN_IDS[code])
        if valid(by_side['home'],home) and valid(by_side['away'],away): found.append(event)
    if len(found)!=1: raise ValueError('Missing or ambiguous schedule game')
    event=found[0]
    if not re.fullmatch(r'[0-9]+',str(event.get('id',''))): raise ValueError('Missing ESPN event ID')
    competition_id = event['competitions'][0].get('id')
    if str(competition_id) != str(event['id']):
        raise ValueError('ESPN event/competition mismatch')
    if abs((timestamp(event['date'])-timestamp(game['tipoff_utc'])).total_seconds()) > 60:
        raise ValueError('Schedule tipoff disagreement')
    typ=event['status']['type']
    if typ.get('state')!='pre' or typ.get('completed') is not False or typ.get('name')!='STATUS_SCHEDULED':
        raise ValueError('Game not scheduled pregame')
    if now >= min(timestamp(event['date']),timestamp(game['tipoff_utc'])):
        raise ValueError('Game already started')
    return {'espn_event_id':str(event['id']), 'tipoff_utc':event['date'], 'requested_at':evidence['requested_at'], 'received_at':evidence['received_at']}
