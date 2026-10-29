"""Bounded authentic-data survey using existing credentials; GET-only, no enrollment."""
import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .core import read_sealed, seal
from .providers import get_json, AlfredCSV
from .authentic import weather_members, contract_window, weather_contract, bls_first_release

BDL = {
    'games': ('/v1/games', {'dates[]': None}),
    'player_stats': ('/v1/stats', {'game_ids[]': [21717975]}),
    'advanced_stats': ('/nba/v2/stats/advanced', {'game_ids[]': [21717975], 'period': 0}),
    'injuries': ('/v1/player_injuries', {}),
    'lineups': ('/v1/lineups', {'game_ids[]': [21717987]}),
}


def classify(status, payload=None):
    if status == 401: return 'unauthorized_or_not_entitled'
    if status == 403: return 'forbidden_or_not_entitled'
    if status == 429: return 'rate_limited_entitlement_unknown'
    if status == 404: return 'endpoint_or_resource_unavailable'
    if status != 200: return 'request_failed_entitlement_unknown'
    if not isinstance(payload, dict) or not isinstance(payload.get('data'), list): return 'unexpected_response'
    return 'accessible_nonempty_sample' if payload['data'] else 'accessible_empty_sample'


def attempt(name, url, params, root, headers=None, response_format='json'):
    try:
        payload, digest, env = get_json(url, params, root/'raw', headers, response_format)
        report = {'name': name, 'status': env['status'], 'evidence_sha256': digest,
                  'received_at': env['received_at'], 'result': 'captured'}
        return report, payload
    except RuntimeError as exc:
        digest = str(exc).rsplit(' ', 1)[-1]
        env = read_sealed(root/'raw', digest)
        return {'name': name, 'status': env.get('status'), 'error': env.get('error'),
                'received_at': env['received_at'], 'evidence_sha256': digest,
                'result': 'blocked'}, None


def survey(root, *, pause=13):
    wall_start=time.perf_counter();cpu_start=time.process_time()
    root = Path(root).resolve()
    if any(p in ('paper_v08', 'forward_test', '.github') for p in root.parts):
        raise ValueError('operational_output_forbidden')
    now = datetime.now(timezone.utc); today = now.date().isoformat()
    report = {'observed_at': now.isoformat(), 'paper_only': True, 'operations': [], 'sports': [], 'weather': [], 'finance': [],
              'empirical_comparisons': 0, 'superiority_claim': False}
    item, position = attempt('outstanding_paper_market',
        'https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT29SACNOP-SAC', {}, root)
    if isinstance(position, dict):
        market = position['market']
        item.update(ticker=market['ticker'], market_status=market['status'], market_result=market.get('result'),
                    action='existing paper reconciliation required' if market['status']=='finalized' else 'await finalization; no ledger change')
    report['operations'].append(item)
    key = os.environ.get('BALLDONTLIE_API_KEY')
    if not key:
        report['sports'].append({'result': 'missing_existing_BALLDONTLIE_credential'})
    else:
        for i, (name, (path, args)) in enumerate(BDL.items()):
            if i: time.sleep(pause)
            args = {k: today if v is None else v for k, v in args.items()}
            item, payload = attempt(name, 'https://api.balldontlie.io'+path,
                {**args, 'per_page': 1}, root, {'Authorization': key})
            item['access'] = classify(item['status'], payload)
            if payload is not None:
                item.update(sample_rows=len(payload.get('data', [])),
                            sample_fields=sorted(payload['data'][0]) if payload.get('data') else [],
                            complete=not payload.get('meta', {}).get('next_cursor'))
            item['pregame_use'] = ('excluded: provider documents post-tipoff availability' if name == 'lineups' else
                                   'lagged completed games only' if name in ('advanced_stats', 'player_stats') else
                                   'capture time is availability; no historical backdating')
            report['sports'].append(item)
    report['sports'].append({'name': 'player_projections', 'result': 'no_documented_dedicated_endpoint_verified',
                             'note': 'Do not substitute completed-game minutes, betting props or DFS rows for pregame minutes projections.'})
    day = (now.date()+timedelta(days=1)).isoformat()
    start, end = contract_window(day, 'America/New_York')
    base = {'latitude': 40.7789, 'longitude': -73.9692, 'hourly': 'temperature_2m',
            'timezone': 'UTC', 'temperature_unit': 'celsius', 'forecast_days': 3}
    item, payload = attempt('prospective_ensemble', 'https://ensemble-api.open-meteo.com/v1/ensemble',
                            {**base, 'models': 'gfs_seamless'}, root)
    if payload is not None:
        try:
            parsed = weather_members(root/'raw', item['evidence_sha256'], item['received_at'], start, end)
            item.update(parsed, target_day=day, window_start=start, window_end=end,
                        benchmark_eligible=False, reason='unverified exact run identity and NWS contract mapping; future outcome pending')
        except (ValueError, KeyError, TypeError) as exc:
            item.update(benchmark_eligible=False, reason=str(exc))
    report['weather'].append(item)
    run = (now-timedelta(days=1)).strftime('%Y-%m-%dT00:00')
    item, _ = attempt('archived_deterministic', 'https://single-runs-api.open-meteo.com/v1/forecast',
                      {**base, 'forecast_days': 7, 'models': 'gfs_seamless', 'run': run}, root)
    item.update(benchmark_eligible=False, reason='initialization is not publication; historical availability unverified')
    report['weather'].append(item)
    item, _ = attempt('official_station_observations', 'https://www.ncei.noaa.gov/access/services/data/v1',
        {'dataset': 'daily-summaries', 'stations': 'USW00094728', 'startDate': (now.date()-timedelta(days=10)).isoformat(),
         'endDate': (now.date()-timedelta(days=2)).isoformat(), 'dataTypes': 'TMAX', 'units': 'metric',
         'format': 'json', 'includeAttributes': 'true'}, root)
    item.update(benchmark_eligible=False, reason='GHCN summary is not automatically the NWS CLI settlement report')
    report['weather'].append(item)
    for name, path, params in [('temperature_contract_rules', '/series/KXHIGHNY', {}),
                               ('temperature_contracts', '/markets', {'series_ticker': 'KXHIGHNY', 'status': 'open', 'limit': 20})]:
        item, payload = attempt(name, 'https://external-api.kalshi.com/trade-api/v2'+path, params, root)
        if isinstance(payload, dict) and name == 'temperature_contracts':
            item['contracts'] = [weather_contract(root/'raw', item['evidence_sha256'], m['ticker'], item['received_at']) for m in payload.get('markets', [])]
        report['weather'].append(item)
    fred = os.environ.get('FRED_API_KEY')
    if fred:
        item, payload = attempt('cpi_initial_release_mom', 'https://api.stlouisfed.org/fred/series/observations',
            {'series_id': 'CPIAUCSL', 'api_key': fred, 'file_type': 'json', 'output_type': 4,
             'units': 'pch', 'realtime_start': '2020-01-01', 'realtime_end': today,
             'observation_start': '2020-01-01', 'limit': 100000}, root)
        if isinstance(payload, dict):
            item['initial_release_rows'] = len(payload.get('observations', []))
        report['finance'].append(item)
    else:
        report['finance'].append({'name': 'cpi_initial_release_mom', 'result': 'missing_existing_FRED_credential', 'benchmark_eligible': False})
    item, html = attempt('bls_archived_first_release', 'https://www.bls.gov/news.release/archives/cpi_02132024.htm', {}, root, response_format='html')
    if html is not None:
        try:
            item.update(label=bls_first_release(root/'raw', item['evidence_sha256']), benchmark_eligible=False,
                        reason='authentic outcome only; matched pre-release vintage features still missing')
        except (ValueError,KeyError,TypeError) as exc:item.update(result='parser_blocked',reason=str(exc))
    report['finance'].append(item)
    try:
        vintage = AlfredCSV().request(series_id='CPIAUCSL', cutoff=now.isoformat(), evidence_root=root/'raw')
        report['finance'].append({'name': 'alfred_vintage_csv', 'result': 'captured', 'evidence_sha256': vintage['evidence_sha256'],
                                  'observations': len(vintage['values']), 'benchmark_eligible': False,
                                  'reason': 'one vintage is not a first-release outcome panel'})
    except (ValueError, RuntimeError) as exc:
        report['finance'].append({'name': 'alfred_vintage_csv', 'result': 'blocked', 'reason': str(exc)})
    report['performance_gate'] = 'No authentic matched labeled panel; do not score software fixtures as predictive evidence.'
    report['runtime']={'wall_seconds':round(time.perf_counter()-wall_start,3),
        'cpu_seconds':round(time.process_time()-cpu_start,3),
        'hosting_note':'Collection smoke workload only; not a 24/7 load, latency or availability benchmark.'}
    try:
        import resource
        report['runtime']['linux_peak_rss_KiB']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except ImportError:pass
    digest = seal(root/'reports', report)
    (root/'latest.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'report_sha256': digest, 'report': report}, indent=2))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', default='research_outputs/authentic')
    args = p.parse_args(); survey(args.output)


if __name__ == '__main__': main()
