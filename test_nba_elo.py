import unittest
from nba_data import normalize, download
from nba_elo import predict_and_update, win_probability, evaluate

class NbaTests(unittest.TestCase):
    def test_even_teams_home_advantage(self):
        self.assertGreater(win_probability(1500,1500), .5)
    def test_pre_game_probability_not_leaked(self):
        g = [{'game_id':1,'date':'2024-01-01','home_team_id':1,'away_team_id':2,'home_score':100,'away_score':90},
             {'game_id':2,'date':'2024-01-02','home_team_id':1,'away_team_id':2,'home_score':90,'away_score':100}]
        preds, _ = predict_and_update(g, home_advantage=0)
        self.assertEqual(preds[0]['home_win_probability'], .5)
        self.assertGreater(preds[1]['home_win_probability'], .5)
    def test_holdout_only(self):
        g = [{'game_id':1,'date':'2024-01-01','home_team_id':1,'away_team_id':2,'home_score':100,'away_score':90},
             {'game_id':2,'date':'2024-01-02','home_team_id':1,'away_team_id':2,'home_score':90,'away_score':100}]
        preds, _ = predict_and_update(g)
        self.assertEqual(evaluate(preds,'2024-01-02')['holdout_games'], 1)
    def test_normalize_incomplete(self):
        self.assertIsNone(normalize({'id':1,'status':'Scheduled'}))
    def test_pagination(self):
        def fake(key,season,cursor):
            if cursor is None:
                return {'data':[], 'meta':{'next_cursor':1}}
            return {'data':[], 'meta':{'next_cursor':None}}
        self.assertEqual(download(2024,'test',max_pages=2,pause=0,fetch=fake),[])

if __name__ == '__main__': unittest.main()
