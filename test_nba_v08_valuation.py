import unittest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from nba_v08_valuation import match, taker_fee, value

class ValuationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 27, 20, 0, tzinfo=timezone.utc)
        self.game = {'date':'2026-10-27','tipoff_utc':'2026-10-27T23:30:00Z', 'home_team':'BOS','away_team':'BKN','home_team_id':'2','away_team_id':'3','home_win_probability':'.8'}
        self.market = {'ticker':'KXNBAGAME-26OCT27BKNBOS-BOS','event_ticker':'KXNBAGAME-26OCT27BKNBOS','occurrence_datetime':'2026-10-27T23:30:00Z','market_type':'binary','status':'active','title':'Boston wins','yes_sub_title':'Boston','rules_primary':'If Boston wins the Brooklyn vs Boston Pro Basketball game originally scheduled for Oct 27, 2026, then the market resolves to Yes.','rules_secondary':'A canceled game resolves to a fair price.'}
        self.quote = {'ticker':self.market['ticker'], 'observed_at':self.now.isoformat(), 'yes_ask':'.50','yes_ask_size':10,'no_ask':'.53','no_ask_size':10}
        stamp=self.now.isoformat()
        self.schedule={'schema':'espn-nba-schedule-v1','requested_date':'2026-10-27','source':'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20261027','requested_at':stamp,'received_at':stamp,'payload':{'events':[{'id':'401909877','date':'2026-10-27T23:30:00Z','status':{'type':{'state':'pre','completed':False,'name':'STATUS_SCHEDULED'}},'competitions':[{'id':'401909877','competitors':[{'homeAway':'home','team':{'id':'2','abbreviation':'BOS'}},{'homeAway':'away','team':{'id':'17','abbreviation':'BKN'}}]}]}]}}
        self.series = {'ticker':'KXNBAGAME','fee_type':'quadratic_with_maker_fees','fee_multiplier':1}
    def test_match_and_fee(self):
        self.assertEqual(match(self.game,self.market,schedule=self.schedule,now=self.now),'BOS')
        self.assertEqual(taker_fee('.5',1,1),Decimal('.02'))
        self.assertEqual(taker_fee('.5',100,1),Decimal('1.75'))
        result = value(self.game,self.market,self.quote,self.series,now=self.now,schedule=self.schedule)
        self.assertEqual(result['side'],'YES')
        self.assertEqual(result['net_edge'],'0.27')
    def test_reject_wrong_identity_and_rules(self):
        for k, v in [('ticker','KXNBAGAME-26OCT27BKNBOS-BKN'),('title','Brooklyn wins'),('rules_secondary',''),('status','closed'),('occurrence_datetime','2026-10-28T23:30:00')]:
            m = dict(self.market, **{k:v})
            self.assertIsNone(value(self.game,m,self.quote,self.series,now=self.now,schedule=self.schedule), k)
    def test_stale_or_post_tipoff(self):
        self.assertIsNone(value(self.game,self.market,self.quote,self.series,now=self.now+timedelta(seconds=31),schedule=self.schedule))
        self.assertIsNone(value(self.game,self.market,self.quote,self.series,now=datetime(2026,10,28,tzinfo=timezone.utc),schedule=self.schedule))
    def test_fee_or_liquidity_unknown_rejected(self):
        self.assertIsNone(value(self.game,self.market,self.quote,dict(self.series,fee_multiplier=2),now=self.now,schedule=self.schedule))
        self.assertIsNone(value(self.game,self.market,dict(self.quote,yes_ask_size=0),self.series,now=self.now,schedule=self.schedule))
    def test_negative_edge_rejected(self):
        game = dict(self.game,home_win_probability='.5')
        self.assertIsNone(value(game,self.market,self.quote,self.series,now=self.now,schedule=self.schedule))
    def test_crossed_and_negative_slippage_rejected(self):
        self.assertIsNone(value(self.game,self.market,dict(self.quote,no_ask='.40'),self.series,now=self.now,schedule=self.schedule))
        self.assertIsNone(value(self.game,self.market,self.quote,self.series,now=self.now,slippage=Decimal('-.01'),schedule=self.schedule))
    def test_occurrence_is_secondary_when_schedule_confirms(self):
        market = dict(self.market, occurrence_datetime='2026-10-28T02:30:00Z')
        self.assertIsNotNone(value(self.game,market,self.quote,self.series,now=self.now,schedule=self.schedule))
    def test_independent_schedule_required(self):
        self.assertIsNone(value(self.game,self.market,self.quote,self.series,now=self.now))

if __name__ == '__main__': unittest.main()
