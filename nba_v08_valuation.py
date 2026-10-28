"""Fail-closed NBA game matching and illustrative taker valuation; no orders."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, InvalidOperation
import re

D = Decimal
# Kalshi event ticker codes and display names; BDL code differences are explicit.
TEAMS = {
 'ATL':('ATL','Atlanta'), 'BOS':('BOS','Boston'), 'BKN':('BKN','Brooklyn'),
 'CHA':('CHA','Charlotte'), 'CHI':('CHI','Chicago'), 'CLE':('CLE','Cleveland'),
 'DAL':('DAL','Dallas'), 'DEN':('DEN','Denver'), 'DET':('DET','Detroit'),
 'GSW':('GSW','Golden State'), 'HOU':('HOU','Houston'), 'IND':('IND','Indiana'),
 'LAC':('LAC','Los Angeles C'), 'LAL':('LAL','Los Angeles L'),
 'MEM':('MEM','Memphis'), 'MIA':('MIA','Miami'), 'MIL':('MIL','Milwaukee'),
 'MIN':('MIN','Minnesota'), 'NOP':('NOP','New Orleans'), 'NYK':('NYK','New York'),
 'OKC':('OKC','Oklahoma City'), 'ORL':('ORL','Orlando'), 'PHI':('PHI','Philadelphia'),
 'PHX':('PHX','Phoenix'), 'POR':('POR','Portland'), 'SAC':('SAC','Sacramento'),
 'SAS':('SAS','San Antonio'), 'TOR':('TOR','Toronto'), 'UTA':('UTA','Utah'),
 'WAS':('WAS','Washington')}
ALIASES = {'GS':'GSW','NO':'NOP','NY':'NYK','SA':'SAS','UTAH':'UTA','WSH':'WAS','PHO':'PHX'}


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timestamp must include timezone')
    return result.astimezone(timezone.utc)


def match(game, market, *, schedule=None, now=None):
    """Require exact event, team selection, rules and scheduled start agreement."""
    home = ALIASES.get(game['home_team'], game['home_team'])
    away = ALIASES.get(game['away_team'], game['away_team'])
    if home not in TEAMS or away not in TEAMS or home == away:
        raise ValueError('Unknown teams')
    date = datetime.strptime(game['date'], '%Y-%m-%d')
    event = 'KXNBAGAME-' + date.strftime('%y%b%d').upper() + TEAMS[away][0] + TEAMS[home][0]
    ticker = market.get('ticker', '')
    if market.get('event_ticker') != event or ticker not in (event+'-'+TEAMS[home][0], event+'-'+TEAMS[away][0]):
        raise ValueError('Event identity mismatch')
    selected = home if ticker.endswith('-'+TEAMS[home][0]) else away
    name = TEAMS[selected][1]
    if market.get('status') != 'active' or market.get('market_type') != 'binary':
        raise ValueError('Market not active binary')
    if schedule is None:
        raise ValueError('Independent schedule evidence required')
    from nba_v08_schedule import verify
    verify(game, schedule, now or datetime.now(timezone.utc))
    # occurrence_datetime is not documented as scheduled tipoff. Still require
    # valid timezone-aware metadata, retain it as evidence, never adjust it.
    timestamp(market['occurrence_datetime'])
    if market.get('yes_sub_title') != name or market.get('title') != name + ' wins':
        raise ValueError('Market outcome mismatch')
    rule = market.get('rules_primary', '')
    day = date.strftime('%b ') + str(date.day) + date.strftime(', %Y')
    expected = f"If {name} wins the {TEAMS[away][1]} vs {TEAMS[home][1]} Pro Basketball game originally scheduled for {day}, then the market resolves to Yes."
    if rule != expected:
        raise ValueError('Unrecognized resolution rule')
    if 'fair price' not in market.get('rules_secondary', '').lower():
        raise ValueError('Unrecognized cancellation rule')
    return selected


def taker_fee(price, contracts, multiplier):
    price, multiplier = D(str(price)), D(str(multiplier))
    if not price.is_finite() or not multiplier.is_finite() or not 0 < price < 1 or multiplier <= 0 or not isinstance(contracts, int) or isinstance(contracts, bool) or contracts <= 0:
        raise ValueError('Invalid fee input')
    return (D('.07') * multiplier * contracts * price * (1-price) * 100).to_integral_value(rounding=ROUND_CEILING) / 100


def value(game, market, quote, series, *, now=None, slippage=D('.01'), min_edge=D('.03'), schedule=None):
    """One-contract conservative paper signal; quote must be timestamped and fresh."""
    try:
        now = now or datetime.now(timezone.utc)
        selected = match(game, market, schedule=schedule, now=now)
        if now.tzinfo is None or timestamp(game['tipoff_utc']) <= now:
            raise ValueError('Not pregame')
        age = (now - timestamp(quote['observed_at'])).total_seconds()
        if not 0 <= age <= 30 or quote['ticker'] != market['ticker']:
            raise ValueError('Stale quote')
        if series.get('ticker') != 'KXNBAGAME' or series.get('fee_type') not in ('quadratic','quadratic_with_maker_fees'):
            raise ValueError('Unsupported fee schedule')
        mult = D(str(series['fee_multiplier']))
        if not mult.is_finite() or not D('0') < mult <= D('10'):
            raise ValueError('Unsupported fee multiplier')
        slip = D(str(slippage))
        threshold = D(str(min_edge))
        if not slip.is_finite() or not threshold.is_finite() or slip < 0 or threshold < 0:
            raise ValueError('Invalid assumption')
        yes_ask, no_ask = D(str(quote['yes_ask'])), D(str(quote['no_ask']))
        if not yes_ask.is_finite() or not no_ask.is_finite() or yes_ask + no_ask <= 1:
            raise ValueError('Invalid or crossed book')
        hp = D(str(game['home_win_probability']))
        if not hp.is_finite() or not 0 <= hp <= 1:
            raise ValueError('Invalid probability')
        home = ALIASES.get(game['home_team'], game['home_team'])
        yp = hp if selected == home else 1-hp
        candidates = []
        for side, p in [('YES', yp), ('NO', 1-yp)]:
            raw = D(str(quote[side.lower()+'_ask']))
            size = quote[side.lower()+'_ask_size']
            if not isinstance(size, int) or isinstance(size, bool) or size < 1 or not raw.is_finite() or not 0 < raw < 1:
                continue
            price = raw + slip
            if not 0 < price < 1:
                continue
            fee = taker_fee(price, 1, mult)
            edge = p-price-fee
            if edge >= threshold:
                candidates.append({'side':side,'probability':str(p),'ask':str(raw),'assumed_price':str(price),'fee':str(fee),'net_edge':str(edge),'size':size})
        return max(candidates, key=lambda x: D(x['net_edge'])) if candidates else None
    except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError):
        return None
