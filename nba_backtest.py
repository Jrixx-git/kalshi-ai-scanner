"""Pre-game Elo predictions: all games on the same date use pre-date ratings."""
import argparse
import csv
from collections import defaultdict
from nba_elo import win_probability, evaluate


def predict_by_date(games, *, k=20, initial=1500, home_advantage=65):
    grouped = defaultdict(list)
    seen = set()
    for game in games:
        gid = int(game['game_id'])
        if gid in seen:
            raise ValueError('Duplicate game ID')
        seen.add(gid)
        grouped[game['date']].append(game)
    ratings = {}
    predictions = []
    for date in sorted(grouped):
        changes = defaultdict(float)
        for game in sorted(grouped[date], key=lambda g: int(g['game_id'])):
            h, a = int(game['home_team_id']), int(game['away_team_id'])
            hs, avs = int(game['home_score']), int(game['away_score'])
            if h == a or hs == avs:
                raise ValueError('Invalid game')
            p = win_probability(ratings.get(h, initial), ratings.get(a, initial), home_advantage)
            predictions.append({'game_id': int(game['game_id']), 'date': date,
                                'home_team_id': h, 'away_team_id': a,
                                'home_win_probability': round(p, 6), 'home_win': int(hs > avs)})
            delta = k * (int(hs > avs) - p)
            changes[h] += delta
            changes[a] -= delta
        for team, change in changes.items():
            ratings[team] = ratings.get(team, initial) + change
    return predictions


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', default='nba_history.csv')
    p.add_argument('--cutoff', default='2025-10-01')
    p.add_argument('--output', default='nba_backtest_predictions.csv')
    args = p.parse_args()
    with open(args.input, newline='', encoding='utf-8') as f:
        games = list(csv.DictReader(f))
    predictions = predict_by_date(games)
    with open(args.output, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['game_id','date','home_team_id','away_team_id','home_win_probability','home_win'])
        w.writeheader()
        w.writerows(predictions)
    print('Holdout:', evaluate(predictions, args.cutoff))
    print('Caution: fixed Elo parameters; season coverage and calibration still require review.')

if __name__ == '__main__':
    main()
