"""GET-only public/research adapters. Credentials never persisted in request evidence."""
import json
import csv
import io
import os
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta, date
from typing import Protocol
from .core import seal, number, instant


class Adapter(Protocol):
    def request(self, **kwargs): ...


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('redirect_rejected')


ALLOWED = {'api.balldontlie.io', 'api.sportsdata.io', 'api.stlouisfed.org',
           'single-runs-api.open-meteo.com', 'ensemble-api.open-meteo.com',
           'www.ncei.noaa.gov', 'api.weather.gov', 'external-api.kalshi.com', 'alfred.stlouisfed.org', 'www.bls.gov'}


def get_json(url, params, evidence_root, headers=None, response_format='json'):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED or parsed.query or parsed.fragment or parsed.username or parsed.port:
        raise ValueError('unsupported_endpoint')
    secret_names = ('api_key', 'apikey', 'key', 'access_token', 'token', 'authorization')
    safe_params = {k: ('REDACTED' if k.lower() in secret_names else v) for k,v in params.items()}
    credentials = [str(v) for k,v in params.items() if k.lower() in secret_names and v]
    credentials += [str(v) for k,v in (headers or {}).items()
                    if k.lower() in ('authorization', 'ocp-apim-subscription-key') and v]
    stamp = lambda: datetime.now(timezone.utc).isoformat()
    envelope = dict(endpoint=url, parameters=safe_params, requested_at=stamp(), method='GET')
    request = urllib.request.Request(url+'?'+urllib.parse.urlencode(params, doseq=True),
        headers={'User-Agent':'Kalshi-Isolated-Research/1.0', 'Accept':'application/json', **(headers or {})}, method='GET')
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(request, timeout=20) as response:
            raw = response.read(20_000_001)
            if len(raw)>20_000_000:
                raise ValueError('response_too_large')
            decoded = raw.decode('utf-8')
            if any(secret in decoded for secret in credentials):
                raise ValueError('credential_echo_rejected')
            envelope.update(status=response.status, received_at=stamp(), raw_utf8=decoded)
            payload = json.loads(envelope['raw_utf8']) if response_format=='json' else envelope['raw_utf8']
    except Exception as exc:
        # Never log exception URLs: FRED API keys are query parameters.
        reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
        error = ('tls_verification_failed' if isinstance(reason, ssl.SSLCertVerificationError) else
                 'dns_failed' if isinstance(reason, socket.gaierror) else type(exc).__name__)
        envelope.update(received_at=stamp(), error=error, status=getattr(exc,'code',None))
        digest=seal(evidence_root,envelope)
        raise RuntimeError(error+': evidence '+digest) from None
    digest=seal(evidence_root,envelope)
    return payload, digest, envelope


def key(name):
    value=os.environ.get(name)
    if not value:
        raise ValueError('missing_credential:'+name)
    return value


class BallDontLie:
    def request(self, *, resource, params, evidence_root):
        if resource not in ('games','stats','player_injuries'):
            raise ValueError('unsupported_resource')
        pages=[]; cursor=None; seen=set()
        for _ in range(200):
            query={**params,'per_page':100}
            if cursor is not None:query['cursor']=cursor
            payload,digest,env=get_json('https://api.balldontlie.io/v1/'+resource,query,evidence_root,{'Authorization':key('BALLDONTLIE_API_KEY')})
            if not isinstance(payload.get('data'),list) or not isinstance(payload.get('meta'),dict):
                raise ValueError('invalid_pagination')
            meta=payload['meta']
            if 'next_cursor' not in meta and 'per_page' not in meta:
                raise ValueError('incomplete_pagination')
            pages.append({'payload':payload,'evidence_sha256':digest,'received_at':env['received_at']})
            cursor=meta.get('next_cursor')
            if cursor is None:return pages
            if str(cursor) in seen or not payload['data']:raise ValueError('pagination_cycle')
            seen.add(str(cursor))
        raise ValueError('page_limit')


class SportsDataIO:
    def request(self, *, resource, game_date, evidence_root):
        # No silent assumption that trial numeric values are real.
        if resource not in ('StartingLineupsByDate','PlayerGameProjectionStatsByDate'):
            raise ValueError('unsupported_resource')
        date.fromisoformat(game_date)
        family='projections'
        return get_json(f'https://api.sportsdata.io/v3/nba/{family}/json/{resource}/{game_date}',{},evidence_root,
                        {'Ocp-Apim-Subscription-Key':key('SPORTSDATAIO_API_KEY')})


class Alfred:
    def request(self, *, series_id, cutoff, evidence_root):
        if not re.fullmatch('[A-Z0-9_]+',series_id):raise ValueError('invalid_series')
        # Date-only vintage cannot certify release-day intraday access.
        vintage=(instant(cutoff).date()-timedelta(days=1)).isoformat()
        params=dict(series_id=series_id,realtime_start=vintage,realtime_end=vintage,
                    api_key=key('FRED_API_KEY'),file_type='json',limit=100000)
        payload,digest,env=get_json('https://api.stlouisfed.org/fred/series/observations',params,evidence_root)
        if payload.get('realtime_start')!=vintage or payload.get('realtime_end')!=vintage:
            raise ValueError('vintage_mismatch')
        if payload.get('count')!=len(payload.get('observations',[])) or payload.get('offset',0)!=0:
            raise ValueError('incomplete_pagination')
        available=(date.fromisoformat(vintage)+timedelta(days=1)).isoformat()+'T00:00:00Z'
        return dict(provider='ALFRED:'+series_id,series_id=series_id,issued_at=vintage+'T00:00:00Z',available_at=available,
                    retrieved_at=env['received_at'],availability_basis='provider_vintage',
                    availability_evidence='ALFRED daily vintage '+vintage+'; previous UTC day only',
                    evidence_sha256=digest,values=alfred_values(payload,vintage))


def alfred_values(payload,vintage):
    rows=[]
    for r in payload['observations']:
        if not r['realtime_start'] <= vintage <= r['realtime_end']:raise ValueError('wrong_vintage')
        if r['value']=='.':continue
        rows.append({'date':r['date'],'value':number(r['value'])})
    if len({r['date'] for r in rows})!=len(rows):raise ValueError('duplicate_period')
    return sorted(rows,key=lambda r:r['date'])


class ForecastRuns:
    def request(self, *, latitude, longitude, run, model, evidence_root):
        instant(run)  # Caller must specify UTC offset; API expects UTC init time.
        if model not in ('gfs_seamless','ecmwf_ifs025'):
            raise ValueError('unsupported_model')
        params=dict(latitude=number(latitude),longitude=number(longitude),run=instant(run).strftime('%Y-%m-%dT%H:%M'),
                    models=model,hourly='temperature_2m',timezone='UTC',temperature_unit='celsius')
        return get_json('https://single-runs-api.open-meteo.com/v1/forecast',params,evidence_root)


class AlfredCSV:
    """Public vintage CSV fallback; header date must match, never latest-FRED fallback."""
    def request(self, *, series_id, cutoff, evidence_root):
        if not re.fullmatch('[A-Z0-9_]+',series_id):raise ValueError('invalid_series')
        vintage=(instant(cutoff).date()-timedelta(days=1)).isoformat()
        text,digest,env=get_json('https://alfred.stlouisfed.org/graph/alfredgraph.csv',
            {'id':series_id,'vintage_date':vintage},evidence_root,response_format='csv')
        rows=list(csv.reader(io.StringIO(text)))
        expected=series_id+'_'+vintage.replace('-','')
        if not rows or len(rows[0])!=2 or rows[0][1]!=expected:raise ValueError('csv_vintage_header_mismatch')
        values=[{'date':r[0],'value':number(r[1])} for r in rows[1:] if len(r)==2 and r[1] not in ('','.')] 
        if not values or len({r['date'] for r in values})!=len(values):raise ValueError('invalid_vintage_csv')
        return dict(provider='ALFRED_CSV:'+series_id,series_id=series_id,issued_at=vintage+'T00:00:00Z',
            available_at=(date.fromisoformat(vintage)+timedelta(days=1)).isoformat()+'T00:00:00Z',
            retrieved_at=env['received_at'],availability_basis='provider_vintage',
            availability_evidence='Public ALFRED requested vintage and matching column header '+expected,
            evidence_sha256=digest,values=values,limitation='Header is necessary, not independent proof of historical publication timing; date resolution only.')


class OfficialObservations:
    def request(self, *, station, start, end, evidence_root):
        # GHCN daily TMAX in standard units (Celsius); not a Kalshi settlement assertion.
        if not re.fullmatch('[A-Z0-9]{11}',station):raise ValueError('invalid_station')
        date.fromisoformat(start);date.fromisoformat(end)
        return get_json('https://www.ncei.noaa.gov/access/services/data/v1',
            dict(dataset='daily-summaries',stations=station,startDate=start,endDate=end,
                 dataTypes='TMAX',units='metric',format='json',includeAttributes='true'),evidence_root)
