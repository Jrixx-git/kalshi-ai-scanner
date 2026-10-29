"""Summarize actual archived responses without inventing a matched backtest."""
import json
from pathlib import Path
from .core import read_sealed,seal
from .normalization import official_tmax,member_maxima


def main():
    root=Path('research_outputs/raw');items=[]
    for path in sorted(root.glob('*.json')):
        env=read_sealed(root,path.stem)
        item={k:env[k] for k in ('endpoint','requested_at','received_at')}
        item['evidence_sha256']=path.stem
        if env.get('error'):item['error']=env['error'];items.append(item);continue
        payload=json.loads(env['raw_utf8'])
        if 'single-runs-api' in env['endpoint']:
            if payload.get('utc_offset_seconds')!=0 or payload['hourly_units']['temperature_2m']!='°C':raise ValueError('unexpected_units')
            hourly=payload['hourly'];hourly['time']=[t+'Z' for t in hourly['time']]
            maximum=member_maxima(hourly,'2026-10-21T00:00:00Z','2026-10-22T00:00:00Z',['temperature_2m'])[0]
            item.update(hourly_values=len(hourly['time']),example_utc_day='2026-10-21',hourly_max_C=maximum,
                benchmark_eligible=False,reason='historical availability and settlement day mapping unverified; no matched archived ensemble')
        elif 'ncei.noaa.gov' in env['endpoint']:
            item.update(observation_rows=len(payload),station='USW00094728',example_day='2026-10-20',
                official_TMAX_C=official_tmax(payload,'USW00094728','2026-10-20'),
                benchmark_eligible=False,reason='current observation vintage; first report and Kalshi settlement source not established')
        items.append(item)
    report={'actual_access_checks':items,'empirical_benchmark_results':None,'superiority_claim':False}
    digest=seal('research_outputs/access_reports',report)
    print(json.dumps({'report_sha256':digest,**report},indent=2))

if __name__=='__main__':main()
