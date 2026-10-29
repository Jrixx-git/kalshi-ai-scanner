"""Strict conversion helpers; no invented provider timestamps or identity mapping."""
from datetime import timedelta
from .core import instant, number


def member_maxima(hourly, start, end, columns):
    """Aggregate each full member trajectory over explicit UTC contract boundaries.

    Only hourly complete coverage is accepted; DST windows may contain 23/25 hours.
    The resulting hourly maximum is NOT asserted equal to a station daily maximum.
    """
    start,end=instant(start),instant(end)
    if start>=end or start.minute or end.minute:raise ValueError('invalid_day_window')
    times=[instant(t) for t in hourly['time']]
    if len(set(times))!=len(times):raise ValueError('duplicate_forecast_time')
    expected=[];t=start
    while t<end:expected.append(t);t+=timedelta(hours=1)
    if t!=end or any(t not in times for t in expected):raise ValueError('incomplete_day')
    indices=[times.index(t) for t in expected]
    result=[]
    if not columns or len(set(columns))!=len(columns):raise ValueError('invalid_members')
    for name in columns:
        values=hourly[name]
        if len(values)!=len(times):raise ValueError('forecast_shape')
        result.append(max(number(values[i]) for i in indices))
    return result


def official_tmax(payload,station,day):
    rows=[r for r in payload if r.get('STATION')==station and r.get('DATE')==day]
    if len(rows)!=1:raise ValueError('ambiguous_station_day')
    row=rows[0]
    # NCEI attributes: measurement, quality, source flags. Nonempty quality rejects.
    attrs=row.get('TMAX_ATTRIBUTES')
    if attrs is None or len(attrs.split(','))<3:raise ValueError('missing_observation_quality')
    if attrs.split(',')[1].strip():raise ValueError('observation_quality_flag')
    return number(row['TMAX'])


def player_features(players,canonical_game_id):
    """Combine externally mapped pregame estimates, never realized game minutes.

    Inputs must be joined and timestamp-checked by the importer, then the resulting
    feature record is checked again by runner. Reject duplicates and mixed games.
    """
    seen=set();sums={'home':[0.,0.,0.],'away':[0.,0.,0.]}
    for p in players:
        pid=p['canonical_player_id']
        if pid in seen or p['canonical_game_id']!=canonical_game_id:raise ValueError('player_identity')
        seen.add(pid)
        if p['side'] not in sums or p.get('minutes_kind')!='pregame_projection':raise ValueError('pregame_projection_required')
        minutes=number(p['projected_minutes']);availability=number(p['availability_probability'])
        if not 0<=minutes<=60 or not 0<=availability<=1:raise ValueError('invalid_player_projection')
        rating=number(p['lagged_advanced_rating']);starter=number(p['starter_probability'])
        if not 0<=starter<=1:raise ValueError('invalid_lineup_probability')
        v=sums[p['side']];v[0]+=rating*minutes/240;v[1]+=(1-availability)*minutes;v[2]+=rating*starter/5
    if not players or any(not any(p['side']==s for p in players) for s in sums):raise ValueError('both_teams_required')
    return dict(zip(('advanced_player_rating_diff','injury_minutes_diff','lineup_rating_diff'),
                    (h-a for h,a in zip(sums['home'],sums['away']))))
