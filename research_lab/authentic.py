"""Source-bound research inputs. No importer-supplied feature values or backdating."""
import csv
import hashlib
import io
import json
import re
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
    payload, _ = captured(root, book_digest, decision, 'https://external-api.kalshi.com/trade-api/v2/markets/'+ticker+'/orderbook')
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
            if g.get('status') != 'Final' or instant(result_env['received_at']) < instant(game['tipoff_utc']):
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
