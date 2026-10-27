"""Download completed NBA games from BALLDONTLIE; never prints or stores API keys."""
import argparse
import csv
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = 'https://api.balldontlie.io/v1/games'
FIELDS = ('game_id','date','home_team_id','away_team_id','home_score','away_score')


def get_page(api_key, season, cursor=None):
    params = [('seasons[]', str(season)), ('per_page', '100')]
    if cursor is not None:
        params.append(('cursor', str(cursor)))
    req = urllib.request.Request(BASE + '?' + urllib.parse.urlencode(params), headers={
        'Authorization': api_key, 'Accept': 'application/json',
        'User-Agent': 'KalshiPaperResearch/0.3'})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.load(resp)


def normalize(game):
    if game.get('status') != 'Final' or game.get('postseason') is None:
        # Status may be a completed timestamp in some API versions; scores alone are insufficient.
        if game.get('status') != 'Final':
            return None
    try:
        row = dict(game_id=int(game['id']), date=str(game['date'])[:10],
                   home_team_id=int(game['home_team']['id']), away_team_id=int(game['visitor_team']['id']),
                   home_score=int(game['home_team_score']), away_score=int(game['visitor_team_score']))
    except (KeyError, TypeError, ValueError):
        return None
    if row['home_team_id'] == row['away_team_id'] or row['home_score'] == row['away_score']:
        return None
    return row


def download(season, api_key, *, max_pages=2, pause=13, fetch=get_page):
    if not api_key:
        raise ValueError('BALLDONTLIE_API_KEY is missing')
    cursor = None
    seen = set()
    rows = []
    for page in range(max_pages):
        payload = fetch(api_key, season, cursor)
        for game in payload.get('data', []):
            row = normalize(game)
            if row and row['game_id'] not in seen:
                rows.append(row)
                seen.add(row['game_id'])
        next_cursor = payload.get('meta', {}).get('next_cursor')
        if next_cursor is None or next_cursor == cursor:
            break
        cursor = next_cursor
        if page + 1 < max_pages:
            time.sleep(pause)
    return sorted(rows, key=lambda r: (r['date'], r['game_id']))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--season', type=int, required=True, help='Season starting year, e.g. 2024')
    p.add_argument('--max-pages', type=int, default=2)
    p.add_argument('--output', default='nba_games.csv')
    args = p.parse_args()
    rows = download(args.season, os.environ.get('BALLDONTLIE_API_KEY'), max_pages=max(1, min(args.max_pages, 10)))
    with open(args.output, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f'Saved {len(rows)} completed games to {args.output} (partial if page limit reached).')

if __name__ == '__main__':
    main()
