import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from nba_forward_test import predictions
from nba_v08_schedule import verify, BASE
from nba_v08_valuation import match

class IdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.games = predictions('forward_test/state')
        cls.payload=json.loads(Path('testdata/espn_2026-10-27.json').read_text())
        snap=json.loads(Path('paper_v08/state/snapshots/3c51dae95dfae7ac664eb4b2ebe35786d9e89378e26d67e808389a19a017954a.json').read_text())
        cls.markets=snap['markets']
        cls.now=datetime(2026,10,27,21,0,tzinfo=timezone.utc)
    def evidence(self):
        stamp=(self.now-timedelta(seconds=10)).isoformat()
        return {'schema':'espn-nba-schedule-v1','requested_date':'2026-10-27','source':BASE+'20261027','requested_at':stamp,'received_at':stamp,'payload':copy.deepcopy(self.payload)}
    def test_four_archived_games_and_eight_real_contracts(self):
        expected={'21717971':'401909877','21717972':'401909878','21717973':'401909879','21717974':'401909880'}
        for gid,eid in expected.items():
            game=self.games[gid][0]; ev=self.evidence()
            self.assertEqual(verify(game,ev,self.now)['espn_event_id'],eid)
            markets=[m for m in self.markets if game['away_team']+game['home_team'] in m['event_ticker']]
            self.assertEqual(len(markets),2)
            for m in markets: self.assertIn(match(game,m,schedule=ev,now=self.now),[game['home_team'],game['away_team']])
    def test_team_ids_and_date_rejected(self):
        game=copy.deepcopy(self.games['21717971'][0]); evidence=self.evidence()
        game['home_team_id']='14'
        with self.assertRaises(ValueError): verify(game,evidence,self.now)
        game=self.games['21717971'][0]; evidence['requested_date']='2026-10-28'
        with self.assertRaises(ValueError): verify(game,evidence,self.now)
        evidence=self.evidence(); evidence['payload']['events'][0]['competitions'][0]['competitors'][0]['team']['id']='13'
        with self.assertRaises(ValueError): verify(game,evidence,self.now)
    def test_duplicate_events_are_ambiguous(self):
        e=self.evidence(); e['payload']['events'].append(copy.deepcopy(e['payload']['events'][0]))
        with self.assertRaises(ValueError): verify(self.games['21717971'][0],e,self.now)
    def test_stale_live_and_unaware_time_rejected(self):
        game=self.games['21717971'][0]; e=self.evidence()
        with self.assertRaises(ValueError): verify(game,e,self.now+timedelta(minutes=6))
        e=self.evidence(); e['payload']['events'][0]['status']['type']['state']='in'
        with self.assertRaises(ValueError): verify(game,e,self.now)
        e=self.evidence(); e['payload']['events'][0]['date']='2026-10-27T23:30:00'
        with self.assertRaises(ValueError): verify(game,e,self.now)
    def test_dst_offsets_are_instant_based(self):
        game=copy.deepcopy(self.games['21717971'][0]); game['date']='2026-11-01'; game['tipoff_utc']='2026-11-02T00:30:00Z'
        now=datetime(2026,11,1,20,tzinfo=timezone.utc); e=self.evidence(); e.update(requested_date='2026-11-01',source=BASE+'20261101',requested_at=now.isoformat(),received_at=now.isoformat())
        e['payload']['events']=e['payload']['events'][:1]; e['payload']['events'][0]['date']='2026-11-01T19:30:00-05:00'
        self.assertEqual(verify(game,e,now)['espn_event_id'],'401909877')
        e['payload']['events'][0]['date']='2026-11-01T19:30:00-04:00'
        with self.assertRaises(ValueError): verify(game,e,now)
    def test_spring_dst_offset(self):
        game=copy.deepcopy(self.games['21717971'][0]); game.update(date='2027-03-14',tipoff_utc='2027-03-14T23:30:00Z')
        now=datetime(2027,3,14,20,tzinfo=timezone.utc); e=self.evidence(); e.update(requested_date='2027-03-14',source=BASE+'20270314',requested_at=now.isoformat(),received_at=now.isoformat())
        e['payload']['events']=e['payload']['events'][:1]; e['payload']['events'][0]['date']='2027-03-14T19:30:00-04:00'
        self.assertEqual(verify(game,e,now)['espn_event_id'],'401909877')
        e['payload']['events'][0]['date']='2027-03-14T19:30:00-05:00'
        with self.assertRaises(ValueError): verify(game,e,now)

if __name__=='__main__': unittest.main()
