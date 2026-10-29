"""Source-bound research inputs. No importer-supplied feature values or backdating."""
import csv
import hashlib
import io
import json
import re
from html.parser import HTMLParser
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from statistics import mean
from zoneinfo import ZoneInfo
from .core import instant, number, probability, read_sealed
from .models import logistic_offset
from .evaluation import compare
from .normalization import member_maxima

EXPANSION_SPORTS = ('NBA', 'NHL', 'NFL', 'MLB', 'tennis', 'European soccer', 'Turkish Super Lig')


def captured(root, digest, cutoff, endpoint):
    envelope = read_sealed(root, digest)
    if envelope.get('endpoint') != endpoint or envelope.get('status') != 200 or envelope.get('method') != 'GET':
        raise ValueError('wrong_source_or_failed_capture')
    if not instant(envelope['requested_at']) <= instant(envelope['received_at']) <= instant(cutoff):
        raise ValueError('capture_after_decision')
    return json.loads(envelope['raw_utf8']), envelope


def complete_pages(root, digests, cutoff, endpoint, expected_params):
    if not digests or len(set(digests)) != len(digests):
        raise ValueError('missing_or_duplicate_pages')
    rows, seen, cursor, cursors = [], set(), None, set()
    for index, digest in enumerate(digests):
        payload, env = captured(root, digest, cutoff, endpoint)
        params = env['parameters']
        if any(params.get(k) != v for k, v in expected_params.items()) or params.get('cursor') != cursor:
            raise ValueError('query_or_cursor_mismatch')
        if not isinstance(payload.get('data'), list) or not isinstance(payload.get('meta'), dict):
            raise ValueError('invalid_page')
        meta = payload['meta']
        size = meta.get('per_page')
        if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= 100 or len(payload['data']) > size:
            raise ValueError('invalid_page_size')
        for row in payload['data']:
            identifier = row['id'] if 'id' in row else row['player']['id']
            if identifier in seen:
                raise ValueError('duplicate_source_row')
            seen.add(identifier); rows.append(row)
        cursor = meta.get('next_cursor')
        if cursor is not None:
            if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor <= 0 or cursor in cursors or not payload['data']:
                raise ValueError('invalid_cursor')
            cursors.add(cursor)
        if (cursor is None) != (index == len(digests)-1):
            raise ValueError('incomplete_or_extra_pages')
    return rows


def nba_features(root, advanced_pages, basic_pages, injury_pages, game, decision):
    """Lagged player PIE/minute weighted team strength; no current-game stats/lineups.

    This is a separate challenger specification, not a replacement for projected
    player impact. Missing games/teams/statuses reject rather than become zero.
    """
    if instant(decision) >= instant(game['tipoff_utc']):
        raise ValueError('not_pregame')
    day = game['date']; home, away = int(game['home_team_id']), int(game['away_team_id'])
    if home == away or min(home, away) <= 0:
        raise ValueError('team_identity')
    end = (date.fromisoformat(day)-timedelta(days=1)).isoformat()
    start = (date.fromisoformat(day)-timedelta(days=15)).isoformat()
    teams = [home, away]
    stats = complete_pages(root, advanced_pages, decision,
        'https://api.balldontlie.io/nba/v2/stats/advanced',
        {'start_date': start, 'end_date': end, 'period': 0})
    basics = complete_pages(root, basic_pages, decision, 'https://api.balldontlie.io/v1/stats',
        {'start_date': start, 'end_date': end})
    minutes_by_player_game = {}
    for r in basics:
        if int(r['team']['id']) not in teams: continue
        key = (str(r['game']['id']), r['player']['id'], int(r['team']['id']))
        if key in minutes_by_player_game: raise ValueError('duplicate_basic_player_game')
        value = r['min']
        if isinstance(value, str) and re.fullmatch(r'\d+:\d{2}', value):
            m, s = map(int, value.split(':'))
            if s >= 60: raise ValueError('invalid_minutes')
            value = m+s/60
        minutes_by_player_game[key] = number(value)
    injuries = complete_pages(root, injury_pages, decision,
        'https://api.balldontlie.io/v1/player_injuries', {'team_ids[]': teams})
    by_team = {home: {}, away: {}}
    for row in stats:
        g = row['game']; tid = int(row['team']['id'])
        if tid not in teams: continue
        if str(g['id']) == str(game['game_id']) or not start <= g['date'][:10] <= end:
            raise ValueError('current_future_or_wrong_team_stats')
        # Older dates alone are not proof of finality (e.g. a postponed game).
        if g.get('status') != 'Final' and g.get('status_state') != 'final':
            raise ValueError('nonfinal_history')
        if row.get('period') != 0:
            raise ValueError('non_full_game_stats')
        minutes = minutes_by_player_game[(str(g['id']), row['player']['id'], tid)]
        pie = number(row['pie'])
        if not 0 <= minutes <= 70 or not -1 <= pie <= 1:
            raise ValueError('invalid_advanced_stat')
        bucket = by_team[tid].setdefault(str(g['id']), [])
        pid = row['player']['id']
        if any(p[0] == pid for p in bucket):
            raise ValueError('duplicate_player_game')
        bucket.append((pid, minutes, pie))
    strength, counts = {}, {}
    for tid in teams:
        values = []
        for players in by_team[tid].values():
            total = sum(p[1] for p in players)
            if len(players) < 5 or not 230 <= total <= 350:
                raise ValueError('incomplete_team_minutes')
            values.append(sum(m*p for _, m, p in players)/total)
        if not values:
            raise ValueError('no_lagged_team_history')
        strength[tid] = mean(values); counts[tid] = len(values)
    unavailable = dict.fromkeys(teams, 0); injury_ids = set()
    for row in injuries:
        player = row['player']; tid = int(player['team_id']); pid = player['id']
        if tid not in teams or pid in injury_ids:
            raise ValueError('injury_identity')
        injury_ids.add(pid)
        status = row['status'].strip().lower()
        if status not in ('out', 'doubtful', 'questionable', 'probable', 'day-to-day', 'available'):
            raise ValueError('unknown_injury_status')
        unavailable[tid] += int(status == 'out')
    return {'features': [strength[home]-strength[away], unavailable[home]-unavailable[away],
                         counts[home]-counts[away]],
            'feature_names': ['lagged_pie_diff', 'out_player_count_diff', 'history_games_diff'],
            'decision_at': decision, 'game_id': str(game['game_id']),
            'source_digests': list(advanced_pages)+list(basic_pages)+list(injury_pages),
            'specification': 'lagged-pie-injury-v1', 'paper_only': True}


def nba_challenger(training, current, baseline):
    eligible = [row for row in training if instant(row['outcome_available_at']) < instant(current['decision_at'])]
    if any(row.get('specification') != current['specification'] for row in eligible):
        raise ValueError('mixed_feature_specifications')
    return logistic_offset(eligible, current['features'], probability(baseline))


def frozen_forecast(archive, game_id, decision):
    archive = __import__('pathlib').Path(archive)
    manifest = json.loads((archive/'manifest.json').read_text())
    raw = (archive/'predictions.csv').read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest['csv_sha256'] or instant(manifest['observed_at']) > instant(decision):
        raise ValueError('invalid_or_late_baseline')
    rows = [r for r in csv.DictReader(io.StringIO(raw.decode())) if r['game_id'] == str(game_id)]
    if len(rows) != 1 or instant(decision) >= instant(rows[0]['tipoff_utc']):
        raise ValueError('missing_or_late_baseline')
    r = rows[0]
    if r['calibration_temperature'] != '1.23' or r['history_before'] != r['date']:
        raise ValueError('baseline_not_frozen')
    return r


def market_probability(yes_bid, no_bid):
    """One market's YES midpoint, not a profitable or executable fill claim."""
    y, n = probability(yes_bid), probability(no_bid)
    if y+n > 1 or y == 0 or n == 0:
        raise ValueError('invalid_or_crossed_market')
    return (y+1-n)/2


def nba_market(root, market_digest, book_digest, game, decision):
    """Strict single-contract midpoint comparator with canonical game orientation."""
    months = ('JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC')
    day = date.fromisoformat(game['date'])
    event = f"KXNBAGAME-{day.year%100:02d}{months[day.month-1]}{day.day:02d}{game['away_team']}{game['home_team']}"
    envelope = read_sealed(root, market_digest)
    market = json.loads(envelope['raw_utf8'])['market']; ticker = market['ticker']
    suffix = ticker.rsplit('-', 1)[-1]
    if market.get('event_ticker') != event or ticker != event+'-'+suffix or suffix not in (game['home_team'],game['away_team']):
        raise ValueError('market_game_identity')
    captured(root, market_digest, decision, 'https://external-api.kalshi.com/trade-api/v2/markets/'+ticker)
    if market.get('status') != 'active' or market.get('result'):
        raise ValueError('market_not_pregame_active')
    payload, book_env = captured(root, book_digest, decision, 'https://external-api.kalshi.com/trade-api/v2/markets/'+ticker+'/orderbook')
    if (instant(decision)-instant(book_env['received_at'])).total_seconds() > 30:
        raise ValueError('stale_market_comparator')
    def bid(side):
        levels = payload['orderbook_fp'][side+'_dollars']
        valid = [(probability(p), number(n)) for p,n in levels]
        if any(n <= 0 for _,n in valid) or not valid: raise ValueError('empty_or_invalid_depth')
        return max(p for p,_ in valid)
    p = market_probability(bid('yes'),bid('no'))
    return p if suffix == game['home_team'] else 1-p


def compare_nba_events(root, events, archive_root):
    """Offline walk-forward panel reconstructed from raw hashes, never free-form features.

    Missing data becomes an explicit rejection. Every labeled event needs a sealed
    official-provider result captured after tipoff. The baseline stays frozen.
    """
    from pathlib import Path
    training, scored, rejections, seen = [], [], [], set()
    for event in sorted(events, key=lambda r: instant(r['decision_at'])):
        gid = str(event['game_id'])
        if gid in seen: raise ValueError('duplicate_event')
        seen.add(gid)
        try:
            digest = event['archive']
            if not re.fullmatch('[0-9a-f]{64}', digest): raise ValueError('invalid_archive')
            game = frozen_forecast(Path(archive_root)/digest, gid, event['decision_at'])
            row = nba_features(root, event['advanced_pages'], event['basic_pages'], event['injury_pages'], game, event['decision_at'])
            result_env = read_sealed(root, event['result_digest'])
            result, _ = captured(root, event['result_digest'], result_env['received_at'], 'https://api.balldontlie.io/v1/games/'+gid)
            g = result['data']
            if str(g['id']) != gid or int(g['home_team']['id']) != int(game['home_team_id']) or int(g['visitor_team']['id']) != int(game['away_team_id']):
                raise ValueError('outcome_game_identity')
            if g.get('status') != 'Final' or g.get('postponed') or g.get('date', '')[:10] != game['date'] or instant(result_env['received_at']) < instant(game['tipoff_utc']):
                raise ValueError('outcome_not_final')
            h,a = number(g['home_team_score']),number(g['visitor_team_score'])
            if h == a or min(h,a) <= 0: raise ValueError('invalid_final_score')
            row.update(y=int(h>a), baseline=probability(game['home_win_probability']),
                outcome_available_at=result_env['received_at'], cluster=game['date'])
            eligible=[r for r in training if instant(r['outcome_available_at']) < instant(row['decision_at'])]
            if len(eligible) >= 20:
                row['predictions']={'elo':row['baseline'],'challenger':nba_challenger(eligible,row,row['baseline'])}
                if event.get('market_digest') and event.get('book_digest'):
                    row['predictions']['market']=nba_market(root,event['market_digest'],event['book_digest'],game,event['decision_at'])
                scored.append(row)
            training.append(row)
        except (KeyError,ValueError,TypeError,OSError) as exc:
            rejections.append({'game_id':gid,'reason':str(exc)})
    paired=[r for r in scored if 'market' in r['predictions']]
    return {'specification':'lagged-pie-injury-v1','eligible':len(events),'accepted':len(training),
        'rejections':rejections,'warmup':len(training)-len(scored),'elo_comparison':compare(scored,'elo','challenger'),
        'market_comparison':compare(paired,'market','challenger'),'forecasts':scored,'superiority_claim':False,'paper_only':True}


def contract_window(day, zone, *, fixed_standard_offset=None):
    d = date.fromisoformat(day)
    tz = ZoneInfo(zone) if fixed_standard_offset is None else timezone(timedelta(hours=number(fixed_standard_offset)))
    return (datetime.combine(d, time(), tz).astimezone(timezone.utc).isoformat(),
            datetime.combine(d+timedelta(days=1), time(), tz).astimezone(timezone.utc).isoformat())


def weather_members(root, digest, decision, start, end):
    if instant(decision) >= instant(start):
        raise ValueError('weather_capture_not_before_target_window')
    payload, env = captured(root, digest, decision, 'https://ensemble-api.open-meteo.com/v1/ensemble')
    if env['parameters'].get('timezone') != 'UTC' or payload.get('utc_offset_seconds') != 0:
        raise ValueError('weather_timezone')
    hourly = dict(payload['hourly'])
    hourly['time'] = [t+'Z' if re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d', t) else t for t in hourly['time']]
    cols = sorted(k for k in hourly if re.fullmatch(r'temperature_2m(?:_member\d+)?', k))
    if len(cols) < 2 or any(payload['hourly_units'].get(k) != '\u00b0C' for k in cols):
        raise ValueError('missing_members_or_units')
    return {'member_maxima_C': member_maxima(hourly, start, end, cols), 'member_count': len(cols),
            'available_at': env['received_at'], 'basis': 'captured_forecast_snapshot',
            'run_identity_verified': False, 'evidence_sha256': digest}


def weather_settlement(value_C, spec):
    """Apply only an explicitly reviewed contract rule; no guessed NWS mapping."""
    required = ('ticker', 'station', 'day', 'source', 'source_product', 'window_start', 'window_end',
                'rules_sha256', 'unit', 'rounding', 'operator', 'threshold', 'reviewed')
    if any(k not in spec for k in required) or spec['reviewed'] is not True:
        raise ValueError('settlement_definition_unreviewed')
    if spec['source'] != 'NWS' or spec['source_product'] != 'CLI' or not re.fullmatch('[0-9a-f]{64}', spec['rules_sha256']):
        raise ValueError('unsupported_settlement_source')
    if instant(spec['window_start']) >= instant(spec['window_end']):
        raise ValueError('invalid_settlement_window')
    v = Decimal(str(number(value_C)))
    if spec['unit'] == 'F': v = v*9/5+32
    elif spec['unit'] != 'C': raise ValueError('unsupported_unit')
    if spec['rounding'] == 'nearest_integer_half_up': v = v.quantize(Decimal(1), rounding=ROUND_HALF_UP)
    elif spec['rounding'] != 'none': raise ValueError('unsupported_rounding')
    threshold = Decimal(str(number(spec['threshold'])))
    if spec['operator'] == '>': return int(v > threshold)
    if spec['operator'] == '>=': return int(v >= threshold)
    raise ValueError('unsupported_operator')


def weather_contract(root, digest, ticker, cutoff):
    """Bind strike/source metadata to captured Kalshi rules, never to a template."""
    envelope=read_sealed(root,digest)
    payload, _=captured(root,digest,cutoff,'https://external-api.kalshi.com/trade-api/v2/markets')
    if envelope['parameters'].get('series_ticker') != 'KXHIGHNY': raise ValueError('wrong_weather_series')
    matches=[m for m in payload['markets'] if m['ticker']==ticker]
    if len(matches)!=1: raise ValueError('weather_contract_identity')
    market=matches[0]; primary=market['rules_primary']; secondary=market.get('rules_secondary','')
    if 'according to The Weather Company' in primary:
        source='The Weather Company'
    elif 'National Weather Service' in primary:
        source='NWS'
    else: raise ValueError('unrecognized_weather_settlement_source')
    kind=market['strike_type']
    if kind not in ('greater','less','between'): raise ValueError('unsupported_weather_strike')
    floor=market.get('floor_strike'); cap=market.get('cap_strike')
    if kind=='greater' and (floor is None or cap is not None): raise ValueError('invalid_greater_strike')
    if kind=='less' and (cap is None or floor is not None): raise ValueError('invalid_less_strike')
    if kind=='between' and (floor is None or cap is None or number(floor)>number(cap)): raise ValueError('invalid_between_strike')
    return {'ticker':ticker,'settlement_source':source,'strike_type':kind,'floor_strike':floor,'cap_strike':cap,
        'rules_sha256':hashlib.sha256((primary+'\n'+secondary).encode()).hexdigest(),
        'raw_evidence_sha256':digest,'source_mapping_verified':False,
        'blocked_reason':'final Weather Company observations, contract day boundary and rounding must be verified' if source=='The Weather Company' else 'exact CLI station/day/finality and rounding must be verified'}


def require_weather_label_source(contract, observation_source):
    if observation_source != contract['settlement_source']:
        raise ValueError('weather_settlement_source_mismatch')
    if not contract.get('source_mapping_verified'):
        raise ValueError('weather_settlement_mapping_unverified')


def first_release(root, digest, target_period):
    """Use provider's first-release MoM transform; never difference revised levels."""
    env = read_sealed(root, digest); p = env['parameters']
    if env.get('endpoint') != 'https://api.stlouisfed.org/fred/series/observations' or env.get('status') != 200:
        raise ValueError('wrong_first_release_source')
    if p.get('series_id') != 'CPIAUCSL' or p.get('output_type') != 4 or p.get('units') != 'pch':
        raise ValueError('initial_release_mom_required')
    payload = json.loads(env['raw_utf8'])
    if payload.get('output_type') != 4 or payload.get('units') != 'pch' or payload.get('count') != len(payload.get('observations', [])) or payload.get('offset', 0) != 0:
        raise ValueError('incomplete_or_wrong_first_release_response')
    rows = [r for r in payload['observations'] if r['date'] == target_period]
    if len(rows) != 1 or rows[0]['value'] == '.': raise ValueError('missing_or_duplicate_first_release')
    r = rows[0]
    # A vintage date is not an intraday publication timestamp. Next UTC day is
    # deliberately conservative for training availability; not a release-time claim.
    available = (date.fromisoformat(r['realtime_start'])+timedelta(days=1)).isoformat()+'T00:00:00Z'
    if instant(available) > instant(env['received_at']): raise ValueError('first_release_not_yet_available')
    return {'value': number(r['value']), 'target_period': target_period, 'series_id': 'CPIAUCSL',
            'kind': 'first_release_mom_percent', 'outcome_available_at': available,
            'timing_resolution': 'daily_conservative_next_UTC_day', 'evidence_sha256': digest}


def bls_first_release(root, digest):
    """Parse the archived headline MoM, not today's revised historical CPI series."""
    env=read_sealed(root,digest)
    endpoint=env['endpoint']
    if not re.fullmatch(r'https://www\.bls\.gov/news\.release/archives/cpi_\d{8}\.htm',endpoint) or env.get('status') != 200:
        raise ValueError('archived_bls_cpi_required')
    class Text(HTMLParser):
        def __init__(self): super().__init__(); self.parts=[]
        def handle_data(self,data): self.parts.append(data)
    parser=Text();parser.feed(env['raw_utf8']);text=' '.join(' '.join(parser.parts).split())
    heading=re.search(r'CONSUMER PRICE INDEX\s*-\s*([A-Z]+)\s+(\d{4})',text)
    headline=re.search(r'The Consumer Price Index for All Urban Consumers \(CPI-U\) (?:(increased|decreased|rose|fell) (\d+(?:\.\d+)?) percent|was unchanged) in ([A-Za-z]+) on a seasonally adjusted basis',text)
    embargo=re.search(r'8:30 a\.m\. \(ET\) [A-Za-z]+, ([A-Za-z]+ \d{1,2}, \d{4})',text)
    if not heading or not headline or not embargo: raise ValueError('unrecognized_bls_release_layout')
    month=datetime.strptime(heading[1].title(),'%B').month;year=int(heading[2])
    if headline[3].lower()!=heading[1].lower():raise ValueError('bls_target_identity')
    release=datetime.strptime(embargo[1],'%B %d, %Y').replace(hour=8,minute=30,tzinfo=ZoneInfo('America/New_York'))
    if endpoint.rsplit('_',1)[1] != release.strftime('%m%d%Y')+'.htm':raise ValueError('bls_archive_date_mismatch')
    if instant(env['received_at']) < release:raise ValueError('bls_future_release')
    value=number(headline[2]) if headline[2] else 0.
    if headline[1] in ('decreased','fell'):value=-value
    return {'kind':'first_release_mom_percent','value':value,'target_period':f'{year:04d}-{month:02d}-01',
        'series_id':'CPIAUCSL','source':'BLS archived CPI release','publication_at_utc':release.astimezone(timezone.utc).isoformat(),
        'timing_basis':'archived release embargo attestation; not contemporaneous capture',
        'rounding':'published_headline_percent','evidence_sha256':digest}


def main():
    import argparse
    from pathlib import Path
    from .core import seal
    p=argparse.ArgumentParser(description='Reconstruct a source-bound offline NBA comparison; no trading.')
    p.add_argument('panel',help='JSON array of source descriptors; values are derived from raw hashes')
    p.add_argument('--evidence-root',required=True)
    p.add_argument('--archive-root',default='forward_test/state/predictions')
    p.add_argument('--output',default='research_outputs/bound')
    args=p.parse_args();output=Path(args.output).resolve()
    if any(v in ('paper_v08','forward_test','.github') for v in output.parts):raise ValueError('operational_output_forbidden')
    report=compare_nba_events(args.evidence_root,json.loads(Path(args.panel).read_text()),args.archive_root)
    digest=seal(output,report);print(json.dumps({'report_sha256':digest,**report},indent=2))


if __name__=='__main__':main()
