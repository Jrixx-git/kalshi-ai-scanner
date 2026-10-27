"""Chronological pre-game NBA Elo baseline; not an independently validated trading edge."""
import argparse
import csv
import math


def win_probability(home_rating, away_rating, home_advantage=65):
    return 1 / (1 + 10 ** ((away_rating - home_rating - home_advantage) / 400))


def predict_and_update(games, *, k=20, initial=1500, home_advantage=65):
    ratings = {}
    predictions = []
    previous_key = None
    for game in sorted(games, key=lambda g: (g['date'], int(g['game_id']))):
        key = (game['date'], int(game['game_id']))
        if previous_key == key:
            raise ValueError('Duplicate game')
        previous_key = key
        home = int(game['home_team_id'])
        away = int(game['away_team_id'])
        hs, aw = int(game['home_score']), int(game['away_score'])
        if home == away or hs == aw:
            raise ValueError('Invalid final score or teams')
        h, a = ratings.get(home, initial), ratings.get(away, initial)
        p = win_probability(h, a, home_advantage)
        predictions.append({'game_id': int(game['game_id']), 'date': game['date'],
                            'home_team_id': home, 'away_team_id': away,
                            'home_win_probability': round(p, 6), 'home_win': int(hs > aw)})
        delta = k * (int(hs > aw) - p)
        ratings[home] = h + delta
        ratings[away] = a - delta
    return predictions, ratings


def evaluate(predictions, cutoff):
    test = [r for r in predictions if r['date'] >= cutoff]
    if not test:
        raise ValueError('No games in holdout period')
    brier = sum((r['home_win_probability'] - r['home_win']) ** 2 for r in test) / len(test)
    log_loss = -sum(r['home_win'] * math.log(max(1e-12, r['home_win_probability'])) +
                    (1-r['home_win']) * math.log(max(1e-12, 1-r['home_win_probability'])) for r in test) / len(test)
    return {'holdout_games': len(test), 'brier_score': round(brier, 6), 'log_loss': round(log_loss, 6)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', default='nba_games.csv')
    p.add_argument('--cutoff', required=True, help='YYYY-MM-DD start of holdout evaluation')
    p.add_argument('--output', default='nba_elo_predictions.csv')
    args = p.parse_args()
    with open(args.input, newline='', encoding='utf-8') as f:
        games = list(csv.DictReader(f))
    predictions, _ = predict_and_update(games)
    with open(args.output, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=('game_id','date','home_team_id','away_team_id','home_win_probability','home_win'))
        writer.writeheader()
        writer.writerows(predictions)
    print(evaluate(predictions, args.cutoff))
    print('Elo model is a baseline; not yet calibrated or mapped to Kalshi tickers.')

if __name__ == '__main__':
    main()
