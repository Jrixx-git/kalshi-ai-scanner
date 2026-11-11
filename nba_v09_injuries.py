"""Bounded official NBA evidence collector. No player inference or trading."""
import argparse
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo
from nba_forward_test import immutable, encode
from nba_v08_valuation import timestamp

INDEX = 'https://official.nba.com/nba-injury-report-2026-27-season/'
PDF = re.compile(r'https://ak-static.cms.nba.com/referee/injury/Injury-Report_(\d{4}-\d{2}-\d{2})_(\d{2})_(\d{2})(AM|PM)\.pdf')
MAX_BYTES = 8 * 1024 * 1024


def publication(url):
    m = PDF.fullmatch(url)
    if not m:
        raise ValueError('Non-allowlisted report')
    d, h, minute, ampm = m.groups()
    local = datetime.strptime(d + ' ' + h + ':' + minute + ampm, '%Y-%m-%d %I:%M%p')
    return local.replace(tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc).isoformat()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirect refused')


def fetch(url):
    if url != INDEX and not PDF.fullmatch(url):
        raise ValueError('Non-allowlisted URL')
    req = urllib.request.Request(url, method='GET', headers={'User-Agent': 'NBA-Research/0.9'})
    with urllib.request.build_opener(NoRedirect).open(req, timeout=15) as response:
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('Response exceeds byte limit')
        return raw, {k: response.headers.get(k) for k in ('Content-Type', 'Last-Modified', 'ETag', 'Date')}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if tag == 'a' and key == 'href' and value and PDF.fullmatch(value):
                self.links.add(value)


def collect(root, *, max_reports=2, get=fetch):
    if type(max_reports) is not int or not 1 <= max_reports <= 4:
        raise ValueError('Report limit must be 1..4')
    records = []

    def retrieve(url):
        start = datetime.now(timezone.utc).isoformat()
        record = dict(url=url, requested_at=start, publication_at=publication(url) if url != INDEX else None,
                      publication_basis='filename Eastern time; content unverified', status='unavailable',
                      parsed_player_statuses_available=False)
        raw = None
        try:
            raw, headers = get(url)
            if len(raw) > MAX_BYTES or (url != INDEX and not raw.startswith(b'%PDF-')):
                raise ValueError('Invalid body')
            sha = hashlib.sha256(raw).hexdigest()
            immutable(Path(root) / 'raw' / sha, raw)
            record.update(status='raw_available_unparsed', sha256=sha, headers=headers)
        except (OSError, ValueError) as error:
            record['error'] = type(error).__name__
        record['retrieved_at'] = datetime.now(timezone.utc).isoformat()
        immutable(Path(root) / 'records' / (hashlib.sha256(encode(record)).hexdigest() + '.json'), encode(record))
        records.append(record)
        return raw

    raw = retrieve(INDEX)
    if raw is not None:
        parser = Links()
        parser.feed(raw.decode('utf-8', errors='replace'))
        now = datetime.now(timezone.utc)
        urls = [u for u in parser.links if timestamp(publication(u)) <= now]
        for url in sorted(urls, key=publication, reverse=True)[:max_reports]:
            retrieve(url)
    return records


def asof(record, decision):
    """Raw evidence is never promoted to verified player availability."""
    try:
        available = (record['status'] == 'raw_available_unparsed'
                     and timestamp(record['publication_at']) <= timestamp(record['requested_at'])
                     <= timestamp(record['retrieved_at']) <= timestamp(decision))
    except (KeyError, TypeError, ValueError):
        available = False
    return dict(raw_available_asof=available, player_availability_verified=False,
                no_trade=True, reason='player_status_unparsed_or_unavailable')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', default='research/nba_v09/injuries')
    p.add_argument('--max-reports', type=int, default=2)
    a = p.parse_args()
    print(json.dumps(collect(a.output, max_reports=a.max_reports), indent=2))
