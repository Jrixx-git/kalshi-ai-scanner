"""Five GET-only trial entitlement probes; summaries only, no raw feed or credentials."""
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def summarize(raw, key):
    decoded = raw.decode('utf-8')
    if any(value and value in decoded for value in (key, urllib.parse.quote(key, safe=''), json.dumps(key)[1:-1])):
        raise ValueError('credential_echo_rejected')
    payload = json.loads(decoded)
    records = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
    records = [r for r in records if isinstance(r, dict)]
    fields = sorted({k for r in records for k in r})
    timestamps = {k: sorted({str(r[k]) for r in records if r.get(k) is not None})[:8]
                  for k in ('Updated', 'Created', 'DateTime', 'Day', 'GameDate') if k in fields}
    return dict(rows=len(records), fields=fields, timestamp_fields=timestamps,
                timestamp_caveat='Provider fields do not prove first publication or historical as-of availability',
                explicit_scrambled_flags=sorted({str(r[k]) for r in records for k in ('Scrambled', 'IsScrambled') if k in r}))


def probe(path, key, opener):
    stamp = lambda: datetime.now(timezone.utc).isoformat()
    item = dict(endpoint='https://api.sportsdata.io'+path, method='GET', requested_at=stamp())
    request = urllib.request.Request(item['endpoint'], method='GET', headers={
        'Ocp-Apim-Subscription-Key':key, 'Accept':'application/json', 'User-Agent':'Isolated-Trial-Entitlement/1.0'})
    try:
        try:
            response = opener.open(request, timeout=25)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read(10_000_001)
            item.update(status=response.code, received_at=stamp())
            if len(raw) > 10_000_000:
                raise ValueError('response_too_large')
            # Only response fingerprints and derived schema are retained, never error bodies.
            item.update(response_sha256=hashlib.sha256(raw).hexdigest(), response_bytes=len(raw))
            if response.code == 200:
                item.update(summarize(raw, key))
                item['entitlement']='accessible' if item['rows'] else 'accessible_empty'
            else:
                item['entitlement']={401:'unauthorized',403:'forbidden',429:'rate_limited'}.get(response.code,'http_error')
    except Exception as exc:
        item.update(received_at=stamp(), error_type=type(exc).__name__, entitlement='probe_error')
    return item


def main():
    key = os.environ.get('SPORTSDATAIO_API_KEY', '')
    output = Path('entitlement_evidence')
    output.mkdir(exist_ok=True)
    report = dict(observed_at=datetime.now(timezone.utc).isoformat(), secret_present=bool(key),
                  source_commit=os.environ.get('GITHUB_SHA'), run_id=os.environ.get('GITHUB_RUN_ID'),
                  paper_only=True, benchmark_eligible=False, historical_asof_verified=False,
                  quality='trial_data_unverified; trial statistics may be scrambled',
                  policy_source='https://sportsdata.io/help/faq', checks=[])
    if key:
        today = datetime.now(ZoneInfo('America/New_York')).date()
        opener = urllib.request.build_opener(NoRedirect())
        paths = ['/v3/nba/scores/json/GamesByDate/'+today.isoformat()]
        for day in (today, today+timedelta(days=1)):
            for endpoint in ('StartingLineupsByDate','PlayerGameProjectionStatsByDate'):
                paths.append('/v3/nba/projections/json/'+endpoint+'/'+day.isoformat())
        for path in paths:
            item = probe(path, key, opener)
            report['checks'].append(item)
            if item.get('status') == 429:
                report['stopped_after_rate_limit']=True
                break
    encoded = (json.dumps(report,sort_keys=True,indent=2)+'\n').encode()
    # Final defense: reject all output if a credential appears in derived metadata.
    if key and key.encode() in encoded:
        raise RuntimeError('Credential output rejected')
    (output/'summary.json').write_bytes(encoded)
    print(json.dumps({'secret_present':bool(key),'checks':[{k:v for k,v in c.items() if k in ('endpoint','status','entitlement','rows','error_type')} for c in report['checks']]}))
    if not key:
        raise SystemExit('Required secret missing')


if __name__ == '__main__':
    main()
