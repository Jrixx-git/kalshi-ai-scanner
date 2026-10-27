"""Download complete NBA seasons using the existing authenticated downloader.
No secrets are logged; no orders or market API calls.
"""
import argparse
import csv
import os
from pathlib import Path
from nba_data import download, FIELDS


def collect(seasons, key, fetch=None):
    result = {}
    for season in seasons:
        kwargs = {'max_pages': 100, 'pause': 13}
        if fetch is not None:
            kwargs['fetch'] = fetch
        rows = download(season, key, **kwargs)
        if not rows:
            raise ValueError(f'No completed games for season {season}')
        for row in rows:
            result[row['game_id']] = row
        print(f'Season {season}: {len(rows)} completed games')
    return sorted(result.values(), key=lambda r: (r['date'], r['game_id']))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--seasons', nargs='+', type=int, default=[2022, 2023, 2024, 2025])
    p.add_argument('--output', default='nba_history.csv')
    args = p.parse_args()
    rows = collect(args.seasons, os.environ.get('BALLDONTLIE_API_KEY'))
    with Path(args.output).open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f'Total unique completed games: {len(rows)}')
    print('Check season coverage and dates before interpreting backtests.')

if __name__ == '__main__':
    main()
