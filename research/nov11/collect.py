"""Isolated, bounded GET-only audit; retain aggregates, never player records."""
import csv
import hashlib
import json
import os
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'research/nov11/evidence'
PAIRS = [('NYK','CLE'),('TOR','BOS'),('SAS','CHI'),('MEM','DEN'),('MIL','LAL'),('UTA','ORL'),('POR','OKC')]
ALIASES = {'SA':'SAS','NY':'NYK','UTAH':'UTA','GS':'GSW','NO':'NOP','PHO':'PHX','BKN':'BKN'}
def team(x): return ALIASES.get(x,x)
def stamp(): return datetime.now(timezone.utc).isoformat()
def digest(b): return hashlib.sha256(b).hexdigest()
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None
def get(path,key):
    item = dict(endpoint='https://api.sportsdata.io/v3/nba/'+path,method='GET',requested_at=stamp())
    req=urllib.request.Request(item['endpoint'],headers={'Ocp-Apim-Subscription-Key':key,'Accept':'application/json'},method='GET')
    payload=[]
    try:
        opener=urllib.request.build_opener(NoRedirect())
        try: response=opener.open(req,timeout=25)
        except urllib.error.HTTPError as exc: response=exc
        with response:
            raw=response.read(10_000_001)
            item.update(status=response.code,received_at=stamp())
            if len(raw)>10_000_000 or key.encode() in raw: raise ValueError('rejected_response')
            item.update(response_sha256=digest(raw),response_bytes=len(raw),headers={k.lower():v for k,v in response.headers.items() if k.lower() in ('date','last-modified')})
            if response.code==200:
                parsed=json.loads(raw)
                if not isinstance(parsed,list): raise ValueError('unexpected_shape')
                payload=parsed
                item.update(rows=len(payload),fields=sorted({k for r in payload for k in r}),timestamps={k:dict(minimum=min(v),maximum=max(v),count=len(v)) for k in ('Updated','Created','DateTimeUTC','DateTime') if (v:=[str(r[k]) for r in payload if r.get(k)])})
    except Exception as exc: item['error_type']=type(exc).__name__
    return item,payload
def local():
    c=sqlite3.connect('file:'+str(ROOT/'paper_v08/state/ledger.sqlite3')+'?mode=ro',uri=True)
    c.row_factory=sqlite3.Row
    tables={r[0]:[v[1] for v in c.execute('pragma table_info('+r[0]+')')] for r in c.execute("select name from sqlite_master where type='table'")}
    positions=[dict(r) for r in c.execute("select * from trades") if '26NOV11' in str(dict(r))]
    entries=[dict(r) for r in c.execute('select signal_id, entry_json from paper_evidence') if r['signal_id'] in {p['signal_id'] for p in positions}]
    forecasts=[]
    for p in (ROOT/'forward_test/state/predictions').glob('*/metadata.json'):
        m=json.loads(p.read_text())
        if m.get('target_date')=='2026-11-11':
            manifest=json.loads(p.with_name('manifest.json').read_text())
            raw=p.with_name('predictions.csv').read_bytes()
            forecasts.append(dict(path=str(p.parent.relative_to(ROOT)),metadata=m,manifest=manifest,csv_hash_verified=digest(raw)==manifest['csv_sha256'],predictions=list(csv.DictReader(raw.decode().splitlines()))))
    return dict(tables=tables,positions=positions,entries=entries,forecasts=forecasts)
def mapping(games,lineups,projections,injuries):
    result=[]
    for a,b in PAIRS:
        gs=[g for g in games if {team(g.get('HomeTeam')),team(g.get('AwayTeam'))}=={a,b}]
        item=dict(pair=[a,b],game_matches=len(gs),classification='inconclusive',reason='Trial injury and statistical fields scrambled per provider dictionary; no authenticated as-of injury adjustment or validated win-probability conversion')
        if len(gs)==1:
            g=gs[0]; gid=g.get('GameID')
            ps=[p for p in projections if p.get('GameID')==gid]
            ls=[l for l in lineups if l.get('GameID')==gid]
            ids={p.get('PlayerID') for p in ps}
            lp=[p for l in ls for k in ('HomeLineup','AwayLineup') for p in (l.get(k) or [])]
            item.update(sportsdataio_game_id=gid,home=team(g.get('HomeTeam')),away=team(g.get('AwayTeam')),tipoff_utc=g.get('DateTimeUTC'),projection_rows=len(ps),lineup_game_rows=len(ls),lineup_player_rows=len(lp),lineup_ids_in_projection=sum(p.get('PlayerID') in ids for p in lp),duplicate_projection_player_ids=len(ps)-len(ids),projection_team_mismatch=sum(team(p.get('Team')) not in (a,b) for p in ps),projection_team_id_mismatch=sum(p.get('TeamID') not in (g.get('HomeTeamID'),g.get('AwayTeamID')) for p in ps),injury_rows_for_teams=sum(team(p.get('Team')) in (a,b) for p in injuries),projection_injury_nonnull=sum(bool(p.get('InjuryStatus')) for p in ps),projection_updated_values=sorted({p['Updated'] for p in ps if p.get('Updated')}),scrambled_values_excluded=True)
        result.append(item)
    return result
def main():
    key=os.environ.get('SPORTSDATAIO_API_KEY','')
    if not key: raise SystemExit('Required secret absent')
    evidence=dict(collected_at=stamp(),source_commit=os.environ.get('GITHUB_SHA'),run_id=os.environ.get('GITHUB_RUN_ID'),local=local(),requests=[],historical_asof_verified=False,benchmark_eligible=False)
    feeds=[]
    for path in ('scores/json/GamesByDate/2026-11-11','projections/json/StartingLineupsByDate/2026-11-11','projections/json/PlayerGameProjectionStatsByDate/2026-11-11','projections/json/InjuredPlayers'):
        item,rows=get(path,key); evidence['requests'].append(item);feeds.append(rows)
        if item.get('status')==429: break
    feeds += [[] for _ in range(4-len(feeds))]
    evidence['comparisons']=mapping(*feeds)
    evidence['timing_rule']='New collection is not evidence of availability at forecast seal or entry. Provider Updated is not first publication. Current injury endpoint is not historical.'
    encoded=json.dumps(evidence,indent=2,sort_keys=True).encode()
    if key.encode() in encoded: raise RuntimeError('Credential output rejected')
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'summary.json').write_bytes(encoded)
    print('Audit complete; only derived evidence retained.')
if __name__=='__main__': main()