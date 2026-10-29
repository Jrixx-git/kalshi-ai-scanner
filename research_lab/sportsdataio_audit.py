"""Bounded trial schema audit. GET only; no raw feed redistribution or model writes."""
import hashlib
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from .core import seal
from .providers import NoRedirect

ROOT = Path('research_outputs/sportsdataio_trial')
SAFE_HEADERS = {'date', 'last-modified', 'retry-after', 'ratelimit-limit',
                'ratelimit-remaining', 'ratelimit-reset', 'x-ratelimit-limit',
                'x-ratelimit-remaining', 'x-ratelimit-reset', 'x-rate-limit-limit',
                'x-rate-limit-remaining', 'x-rate-limit-reset'}


def rows(payload):
    return payload if isinstance(payload, list) else payload.get('data', []) if isinstance(payload, dict) else []


def schema(payload):
    records = rows(payload)
    fields = sorted({k for r in records if isinstance(r, dict) for k in r})
    return {'rows': len(records), 'fields': fields,
            'nonnull_counts': {k: sum(r.get(k) is not None for r in records if isinstance(r, dict)) for k in fields},
            'pagination': payload.get('meta') if isinstance(payload, dict) else None}


def request(name, provider, path, params, key):
    host = 'api.sportsdata.io' if provider == 'sportsdataio' else 'api.balldontlie.io'
    header = 'Ocp-Apim-Subscription-Key' if provider == 'sportsdataio' else 'Authorization'
    url = 'https://' + host + path
    stamp = lambda: datetime.now(timezone.utc).isoformat()
    item = dict(name=name, provider=provider, endpoint=url, parameters=params,
                method='GET', requested_at=stamp(), benchmark_eligible=False)
    req = urllib.request.Request(url + ('?' + urllib.parse.urlencode(params, doseq=True) if params else ''),
            headers={header: key, 'Accept': 'application/json', 'User-Agent': 'Kalshi-Isolated-Research/1.0'}, method='GET')
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    payload = None
    try:
        try:
            response = opener.open(req, timeout=20)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read(10_000_001)
            if len(raw) > 10_000_000:
                raise ValueError('response_too_large')
            decoded = raw.decode('utf-8')
            if key in decoded:
                raise ValueError('credential_echo_rejected')
            item.update(status=response.code, received_at=stamp(),
                        response_sha256=hashlib.sha256(raw).hexdigest(), response_bytes=len(raw),
                        safe_response_headers={k.lower():v for k,v in response.headers.items() if k.lower() in SAFE_HEADERS})
            if response.code == 200:
                payload = json.loads(decoded)
                item.update(schema(payload), result='accessible_nonempty' if rows(payload) else 'accessible_empty_or_scalar')
            else:
                item['result'] = {401:'unauthorized_or_not_entitled',403:'forbidden_or_not_entitled',
                    404:'endpoint_or_resource_unavailable',429:'rate_limited_stop_provider'}.get(response.code,'request_failed')
                item['sanitized_error'] = decoded[:500]
    except Exception as exc:
        item.update(received_at=stamp(), status=item.get('status'), result='transport_or_parse_failed', error=type(exc).__name__)
    item['evidence_sha256'] = seal(ROOT/'provenance', item)
    return item, payload


def timestamps(payload):
    result = {}
    for field in ('Updated','Created','DateTime','DateTimeUTC','InjuryStartDate','updated_at','datetime'):
        values = [str(r[field]) for r in rows(payload) if isinstance(r, dict) and r.get(field)]
        if values:
            result[field] = dict(nonnull=len(values), minimum=min(values), maximum=max(values))
    return result


def identity_inventory(payload, fields):
    records = rows(payload)
    result = {}
    for field in fields:
        values = [r[field] for r in records if isinstance(r, dict) and r.get(field) is not None]
        result[field] = dict(nonnull=len(values), unique=len(set(values)))
    return result


def main():
    sdio = os.environ.get('SPORTSDATAIO_API_KEY')
    bdl = os.environ.get('BALLDONTLIE_API_KEY')
    if not sdio:
        raise SystemExit('SPORTSDATAIO_API_KEY presence check failed; value never printed')
    today = datetime.now(ZoneInfo('America/New_York')).date()
    target = today + timedelta(days=1)
    # NBA first; one request per resource/date, no pagination or automatic retries.
    checks = [
        ('nba_projections','sportsdataio',f'/v3/nba/projections/json/PlayerGameProjectionStatsByDate/{target}',{}),
        ('nba_lineups','sportsdataio',f'/v3/nba/projections/json/StartingLineupsByDate/{target}',{}),
        ('nba_injuries','sportsdataio','/v3/nba/projections/json/InjuredPlayers',{}),
        ('nba_roster','sportsdataio','/v3/nba/scores/json/Players',{}),
        ('nba_games','sportsdataio',f'/v3/nba/scores/json/GamesByDate/{target}',{}),
        ('nba_historical_projections','sportsdataio',f'/v3/nba/projections/json/PlayerGameProjectionStatsByDate/{today-timedelta(days=1)}',{}),
        ('nhl_projections','sportsdataio',f'/v3/nhl/projections/json/PlayerGameProjectionStatsByDate/{target}',{}),
        ('nfl_week','sportsdataio','/v3/nfl/scores/json/CurrentWeek',{}),
        ('soccer_projections','sportsdataio',f'/v4/soccer/projections/json/PlayerGameProjectionStatsByDate/3/{target}',{}),
        ('soccer_competitions','sportsdataio','/v4/soccer/scores/json/Competitions',{}),
    ]
    report = dict(secret_name='SPORTSDATAIO_API_KEY', secret_present=True,
        observed_at=datetime.now(timezone.utc).isoformat(), target_date=str(target),
        mode='RESEARCH_ONLY_NO_TRADING', api_call_budget={'sportsdataio_max':11,'balldontlie_max':3},
        data_quality='scrambled_trial', authentic_pregame_samples_accepted=0, checks=[],
        historical_asof_verified=False, publication_time_verified=False,
        baker={'status':'not_verified','requests':0,'reason':'No documented NBA BAKER prediction route verified; do not probe invented endpoints or relabel Legacy projections.'})
    payloads = {}
    stopped = set()
    for name, provider, path, params in checks:
        if provider in stopped:
            report['checks'].append(dict(name=name,result='skipped_after_auth_or_rate_limit'))
            continue
        if report['checks']:
            time.sleep(2)
        item, payload = request(name,provider,path,params,sdio)
        item['timestamp_inventory'] = timestamps(payload)
        report['checks'].append(item)
        payloads[name] = payload
        if item.get('status') in (401,429):
            stopped.add(provider)
        if name == 'nfl_week' and isinstance(payload,int) and 1 <= payload <= 18 and provider not in stopped:
            time.sleep(2)
            item, data = request('nfl_projections',provider,
                f'/v3/nfl/projections/json/PlayerGameProjectionStatsByWeek/{today.year}REG/{payload}',{},sdio)
            item['timestamp_inventory'] = timestamps(data)
            report['checks'].append(item)
            if item.get('status') in (401,429): stopped.add(provider)
    if bdl:
        for name, path, params in [
            ('bdl_games','/v1/games',{'dates[]':str(target),'per_page':100}),
            ('bdl_players','/v1/players/active',{'per_page':100}),
            ('bdl_injuries','/v1/player_injuries',{'per_page':100})]:
            if 'balldontlie' in stopped: break
            time.sleep(13)
            item,payload = request(name,'balldontlie',path,params,bdl)
            report['checks'].append(item);payloads[name]=payload
            if item.get('status') in (401,429): stopped.add('balldontlie')
    report['identity_inventory'] = {
        'sdio_players':identity_inventory(payloads.get('nba_roster'),('PlayerID','NbaDotComPlayerID','SportRadarPlayerID')),
        'sdio_games':identity_inventory(payloads.get('nba_games'),('GameID','GlobalGameID')),
        'bdl_players':identity_inventory(payloads.get('bdl_players'),('id','nba_id','nba_player_id')),
        'bdl_games':identity_inventory(payloads.get('bdl_games'),('id',))}
    # Cross-provider player IDs belong to separate namespaces. Never equate their integers.
    report['cross_provider_identity'] = dict(verified_player_pairs=0,
        reason='No pre-approved SDIO PlayerID to BALLDONTLIE id crosswalk. Names/teams alone are insufficient; partial BDL roster sample is not complete coverage.')
    game_pairs=[]
    for s in rows(payloads.get('nba_games')):
        for b in rows(payloads.get('bdl_games')):
            if (s.get('HomeTeam')==b.get('home_team',{}).get('abbreviation') and
                s.get('AwayTeam')==b.get('visitor_team',{}).get('abbreviation')):
                game_pairs.append(dict(sdio_game_id=s.get('GameID'), bdl_game_id=b.get('id'),
                    sdio_tipoff_utc=s.get('DateTimeUTC'), bdl_tipoff=b.get('datetime'),
                    status='candidate_requires_tipoff_and_uniqueness_review'))
    report['game_identity_candidates']=game_pairs
    report['model_gate'] = 'Rejected: scrambled trial; no verified authentic pregame panel, publication history or player crosswalk. Do not import trial numeric values into forecasting or operational paper trading.'
    report['timing_caveat'] = 'Updated/Created timestamps and HTTP Date are observations, not proof of first publication or historical cutoff availability. DateTime is an event time.'
    report['raw_feed_policy'] = 'Responses inspected only in memory; artifacts retain schema counts, hashes, timestamps and candidate game IDs, not raw feed values or headers containing credentials.'
    report['actual_api_calls']=sum('endpoint' in c for c in report['checks'])
    digest=seal(ROOT/'reports',report)
    (ROOT/'summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    print('Sealed report SHA256: '+digest)


if __name__=='__main__':main()

