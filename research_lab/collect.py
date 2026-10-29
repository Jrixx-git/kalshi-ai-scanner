"""Explicit one-shot research collection. No scheduler, trial signup or live trading."""
import argparse
import json
from pathlib import Path
from .providers import Alfred, AlfredCSV, ForecastRuns, OfficialObservations, BallDontLie, SportsDataIO
from .core import seal


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default='research_outputs')
    subs=p.add_subparsers(dest='provider',required=True)
    f=subs.add_parser('alfred');f.add_argument('--series',default='CPIAUCSL');f.add_argument('--cutoff',required=True)
    f=subs.add_parser('alfred-csv');f.add_argument('--series',default='CPIAUCSL');f.add_argument('--cutoff',required=True)
    w=subs.add_parser('weather');w.add_argument('--latitude',type=float,required=True);w.add_argument('--longitude',type=float,required=True);w.add_argument('--run',required=True);w.add_argument('--model',default='gfs_seamless')
    o=subs.add_parser('observations');o.add_argument('--station',required=True);o.add_argument('--start',required=True);o.add_argument('--end',required=True)
    b=subs.add_parser('balldontlie');b.add_argument('--resource',choices=['games','stats','player_injuries'],required=True)
    s=subs.add_parser('sportsdataio');s.add_argument('--resource',choices=['StartingLineupsByDate','PlayerGameProjectionStatsByDate'],required=True);s.add_argument('--date',required=True)
    args=p.parse_args();root=Path(args.root).resolve()
    if any(x in ('paper_v08','forward_test','.github') for x in root.parts):raise ValueError('operational_output_forbidden')
    evidence=root/'raw'
    try:
        if args.provider=='alfred':result=Alfred().request(series_id=args.series,cutoff=args.cutoff,evidence_root=evidence)
        elif args.provider=='alfred-csv':result=AlfredCSV().request(series_id=args.series,cutoff=args.cutoff,evidence_root=evidence)
        elif args.provider=='weather':result=ForecastRuns().request(latitude=args.latitude,longitude=args.longitude,run=args.run,model=args.model,evidence_root=evidence)
        elif args.provider=='observations':result=OfficialObservations().request(station=args.station,start=args.start,end=args.end,evidence_root=evidence)
        elif args.provider=='balldontlie':result=BallDontLie().request(resource=args.resource,params={},evidence_root=evidence)
        else:result=SportsDataIO().request(resource=args.resource,game_date=args.date,evidence_root=evidence)
        digest=seal(root/'collections',{'provider':args.provider,'data':result,'mode':'RESEARCH_ONLY_NO_TRADING'})
        print(json.dumps({'collection_sha256':digest,'status':'captured_not_yet_validated_for_benchmark'}))
    except (ValueError,RuntimeError) as exc:
        digest=seal(root/'collections',{'provider':args.provider,'error':str(exc),'mode':'RESEARCH_ONLY_NO_TRADING'})
        print(json.dumps({'collection_sha256':digest,'status':'blocked','reason':str(exc)}))
        raise SystemExit(1)

if __name__=='__main__':main()
