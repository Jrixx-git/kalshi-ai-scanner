import unittest
from nba_backtest import predict_by_date

class BacktestTests(unittest.TestCase):
    def test_same_day_results_do_not_leak(self):
        games = [
            dict(game_id=1, date='2024-01-01', home_team_id=1, away_team_id=2, home_score=110, away_score=90),
            dict(game_id=2, date='2024-01-01', home_team_id=1, away_team_id=3, home_score=110, away_score=90),
            dict(game_id=3, date='2024-01-02', home_team_id=1, away_team_id=2, home_score=110, away_score=90),
        ]
        out = predict_by_date(games, home_advantage=0)
        self.assertEqual(out[0]['home_win_probability'], .5)
        self.assertEqual(out[1]['home_win_probability'], .5)
        self.assertGreater(out[2]['home_win_probability'], .5)
    def test_duplicate_rejected(self):
        g = dict(game_id=1, date='2024-01-01', home_team_id=1, away_team_id=2, home_score=110, away_score=90)
        with self.assertRaises(ValueError):
            predict_by_date([g, g])

if __name__ == '__main__':
    unittest.main()
