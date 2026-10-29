"""Deterministic synthetic fixtures only. Demonstrates plumbing, never real-world skill."""
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from .runner import run
from .core import seal


def fixture(family,n=48):
    events=[];base=datetime(2025,1,1,tzinfo=timezone.utc)
    for i in range(n):
        day=base+timedelta(days=i if family!='finance' else 32*i)
        stamp=lambda hours:(day+timedelta(hours=hours)).isoformat()
        def record(value,hour=-2,**extra):
            return dict(provider='SYNTHETIC',issued_at=stamp(hour-1),available_at=stamp(hour),retrieved_at=stamp(hour),
                availability_basis='synthetic',evidence_sha256='0'*64,value=value,**extra)
        row=dict(event_id=str(i),decision_at=stamp(0),target_at=stamp(24),outcome_available_at=stamp(30),cluster=day.date().isoformat())
        if family=='sports':
            row['inputs']={'legacy':record(.55,canonical_game_id=str(i)),
                'challenger':record(None,canonical_game_id=str(i),data_quality='verified_unscrambled',features={
                    'advanced_player_rating_diff':(i%5)-2,'injury_minutes_diff':(i%3)*2,'lineup_rating_diff':(i%7)/5}),
                'market':record(.6,canonical_game_id=str(i))}
            row['outcome']=record(int(i%3!=0),30)
        elif family=='weather':
            meta=dict(station='SYNTHETIC_STATION',day=(day+timedelta(days=1)).date().isoformat(),unit='C',day_definition='UTC_00_24')
            row.update(meta,threshold=20.,operator='>')
            temp=18+i%7
            row['inputs']={'public':record(temp,kind='forecast_run',run_id='synthetic-'+str(i),**meta),
                           'ensemble':record(None,kind='forecast_run',run_id='synthetic-'+str(i),member_maxima=[temp-1,temp,temp+2],**meta)}
            row['outcome']=record(temp+(i%3-1),30,kind='official_station_daily_max',**meta)
        else:
            # Four consecutive monthly levels preceding an explicitly named target month.
            target_month=2025*12+i
            def month(k):y,m=divmod(k,12);return f'{y:04d}-{m+1:02d}-01'
            row['target_period']=month(target_month);row['threshold']=.25
            row['inputs']={'vintage':record(None,series_id='CPIAUCSL',values=[{'date':month(target_month-4+j),'value':300+j*(.5+i%3/5)} for j in range(4)])}
            row['outcome']=record(.15+(i%5)*.05,30,kind='first_release_mom_percent',target_period=row['target_period'],series_id='CPIAUCSL')
        events.append(row)
    return {'family':family,'synthetic':True,'events':events}


def main():
    root=Path('research_outputs/synthetic');root.mkdir(parents=True,exist_ok=True)
    for family in ('sports','weather','finance'):
        data=fixture(family);input_id=seal(root/'inputs',data);report=run(data)
        report['input_sha256']=input_id
        rid=seal(root/'reports',report)
        print(json.dumps({'family':family,'synthetic':True,'scored':report['n'],'rejected':len(report['rejections']),'report_sha256':rid,'superiority_claim':False}))

if __name__=='__main__':main()
