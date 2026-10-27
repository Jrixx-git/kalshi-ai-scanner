import copy
import csv
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import nba_daily_predictions as daily
from nba_calibration import transform
from nba_elo import win_probability
from nba_backtest import predict_by_date


def game(gid=1, day='2026-10-25', state='final', home=1, away=2):
    return dict(id=gid,date=day,status_state=state,status='Final' if state=='final' else '7:00 pm ET',
                period=4 if state=='final' else 0,postponed=False,
                datetime=day+'T23:00:00Z',home_team=dict(id=home,abbreviation='H'),
                visitor_team=dict(id=away,abbreviation='A'),home_team_score=110,visitor_team_score=100)


class DailyTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,27,12,tzinfo=timezone.utc)
        self.history=[game()]
        self.schedule=[game(9,'2026-10-27','scheduled')]

    def predict(self,history=None,schedule=None):
        return daily.predict(self.history if history is None else history,
                             self.schedule if schedule is None else schedule,'2026-10-27',self.now)

    def test_exact_elo_and_frozen_calibration(self):
        rows,meta=self.predict()
        delta=20*(1-win_probability(1500,1500,65))
        raw=win_probability(1500+delta,1500-delta,65)
        self.assertAlmostEqual(rows[0]['raw_home_win_probability'],round(raw,6))
        self.assertAlmostEqual(rows[0]['home_win_probability'],round(transform(round(raw,6),1.23),6))
        self.assertEqual(meta['history_games'],1)
        self.assertFalse(meta['live_trading_enabled'])
        self.assertAlmostEqual(rows[0]['home_win_probability']+rows[0]['away_win_probability'],1)

    def test_future_and_same_day_outcomes_do_not_leak(self):
        original=self.predict()[0]
        for day in ('2026-10-27','2026-10-28'):
            g=game(2,day);g['home_team_score']=1;g['visitor_team_score']=999
            self.assertEqual(original,self.predict(self.history+[g])[0])

    def test_date_batch_updates_and_order_invariance(self):
        h=[game(),game(2,home=2,away=3)]
        ratings,n,last=daily.build_ratings(h,'2026-10-27')
        delta=20*(1-win_probability(1500,1500))
        self.assertAlmostEqual(ratings[2],1500)
        self.assertEqual(ratings,daily.build_ratings(list(reversed(h)),'2026-10-27')[0])
        self.assertAlmostEqual(ratings[3],1500-delta)

    def test_matches_existing_backtest(self):
        history=[game(),game(2,home=2,away=3),game(3,'2026-10-26',home=3,away=1)]
        upcoming=game(9,'2026-10-27','scheduled')
        def convert(g):
            return dict(game_id=g['id'],date=g['date'],home_team_id=g['home_team']['id'],
                        away_team_id=g['visitor_team']['id'],home_score=g['home_team_score'],away_score=g['visitor_team_score'])
        expected=predict_by_date([convert(g) for g in history+[upcoming]])[-1]['home_win_probability']
        rows,_=self.predict(history,[upcoming])
        self.assertEqual(rows[0]['raw_home_win_probability'],expected)

    def test_nonfinal_history_ignored(self):
        self.assertEqual(self.predict()[0],self.predict(self.history+[game(2,state='in_progress')])[0])

    def test_unsafe_schedule_skipped(self):
        for state in ('final','in_progress','postponed','canceled','unknown','delayed','suspended'):
            self.assertEqual(self.predict(schedule=[game(9,'2026-10-27',state)])[0],[])
        for key,value in [('datetime',None),('datetime','2026-10-27T10:00:00Z'),('datetime','2026-10-27T23:00:00'),('postponed',True),('period',1)]:
            g=copy.deepcopy(self.schedule[0]);g[key]=value
            self.assertEqual(self.predict(schedule=[g])[0],[])

    def test_old_api_status_fallback(self):
        g=copy.deepcopy(self.schedule[0]);del g['status_state']
        self.assertEqual(len(self.predict(schedule=[g])[0]),1)
        g['status']='TBD'
        self.assertEqual(self.predict(schedule=[g])[0],[])

    def test_missing_history_and_bad_scores(self):
        with self.assertRaises(ValueError): self.predict(history=[])
        with self.assertRaises(ValueError): self.predict(schedule=[game(9,'2026-10-27','scheduled',home=3)])
        g=game();g['home_team_score']=100
        with self.assertRaises(ValueError): self.predict(history=[g])
        with self.assertRaises(ValueError): self.predict(history=[game(),game()])
        with self.assertRaises(ValueError): self.predict(schedule=self.schedule*2)

    def test_pagination(self):
        calls=[]
        def fetch(key,params):
            calls.append(params)
            return dict(data=[game(len(calls))],meta=dict(next_cursor=100 if len(calls)==1 else None))
        rows=daily.fetch_games('test',[],fetch=fetch,pause=0)
        self.assertEqual(len(rows),2)
        self.assertIn(('cursor','100'),calls[1])

    def test_pagination_failures(self):
        for payload in [dict(data=[],meta={}),dict(data=[],meta=dict(next_cursor=1)),dict(data=[game(),game()],meta=dict(next_cursor=None))]:
            with self.assertRaises(ValueError): daily.fetch_games('test',[],fetch=lambda *a:payload,pause=0,max_pages=2)
        with self.assertRaises(ValueError): daily.fetch_games('',[])

    def test_export_and_empty_schedule(self):
        with tempfile.TemporaryDirectory() as d:
            rows,meta=self.predict()
            path=daily.export(rows,meta,d)
            with path.open(newline='') as f: saved=list(csv.DictReader(f))
            self.assertEqual(saved[0]['mode'],'RESEARCH_ONLY_NO_TRADING')
            self.assertEqual(json.loads(path.with_suffix('.json').read_text())['exported_games'],1)
            rows,meta=self.predict(schedule=[])
            daily.export(rows,meta,d)
            with path.open(newline='') as f: self.assertEqual(list(csv.DictReader(f)),[])

    def test_retrospective_date_rejected(self):
        with self.assertRaises(ValueError): daily.predict(self.history,self.schedule,'2026-10-26',self.now)

    def test_http_get_only(self):
        response=unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value=b'{"data":[],"meta":{"next_cursor":null}}'
        with patch('urllib.request.urlopen',return_value=response) as mock:
            daily.get_page('test-key',[('dates[]','2026-10-27')])
        request=mock.call_args.args[0]
        self.assertEqual(request.get_method(),'GET')
        self.assertEqual(request.host,'api.balldontlie.io')
        self.assertEqual(request.get_header('Authorization'),'test-key')

    def test_auth_failure_redacted_and_transient_retry(self):
        import urllib.error
        with patch('urllib.request.urlopen',side_effect=urllib.error.HTTPError('https://api.balldontlie.io',401,'unauthorized',{},None)):
            with self.assertRaisesRegex(RuntimeError,'HTTP 401') as caught:
                daily.get_page('secret-do-not-print',[])
        self.assertNotIn('secret-do-not-print',str(caught.exception))
        response=unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value=b'{"data":[],"meta":{"next_cursor":null}}'
        with patch('urllib.request.urlopen',side_effect=[urllib.error.HTTPError('url',429,'limit',{},None),response]) as mock, patch.object(daily.time,'sleep'):
            self.assertEqual(daily.get_page('test',[])['data'],[])
            self.assertEqual(mock.call_count,2)

    def test_full_cli_fetch_to_export_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            args=['nba_daily_predictions.py','--date','2026-10-27','--output-dir',directory]
            with patch.object(sys,'argv',args), patch.dict('os.environ',{'BALLDONTLIE_API_KEY':'test'}), patch.object(daily,'datetime',wraps=datetime) as clock, patch.object(daily,'fetch_games',side_effect=[self.history,self.schedule]) as fetch, patch.object(daily.time,'sleep'):
                clock.now.return_value=self.now
                daily.main()
                self.assertIn(('end_date','2026-10-26'),fetch.call_args_list[0].args[1])
                self.assertIn(('dates[]','2026-10-27'),fetch.call_args_list[1].args[1])
            csv_path=Path(directory)/'nba_predictions_2026-10-27.csv'
            self.assertTrue(csv_path.exists())
            with csv_path.open(newline='') as f: self.assertEqual(len(list(csv.DictReader(f))),1)
        with tempfile.TemporaryDirectory() as directory:
            args=['nba_daily_predictions.py','--date','2026-10-27','--output-dir',directory]
            with patch.object(sys,'argv',args), patch.object(daily,'datetime',wraps=datetime) as clock, patch.object(daily,'fetch_games',side_effect=RuntimeError('API unavailable')):
                clock.now.return_value=self.now
                with self.assertRaises(RuntimeError): daily.main()
            self.assertEqual(list(Path(directory).glob('*.csv')),[])


if __name__ == '__main__':
    unittest.main()
