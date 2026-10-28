import copy,unittest
from datetime import datetime,timezone,timedelta
from nba_v08_fees import effective

class FeeTests(unittest.TestCase):
 def setUp(self):
  self.now=datetime(2026,10,28,12,tzinfo=timezone.utc); self.event='KXNBAGAME-26OCT28MIAATL'; t=(self.now-timedelta(seconds=10)).isoformat()
  self.record={'event_ticker':self.event,'requested_at':t,'received_at':t,'series_observed_at':t,'series':{'ticker':'KXNBAGAME','fee_type':'quadratic','fee_multiplier':1},'event':{'event_ticker':self.event,'series_ticker':'KXNBAGAME'},'pages':[{'event_fee_changes':[],'cursor':''}]}
 def change(self,when,typ='quadratic',mult=2):
  return {'event_ticker':self.event,'series_ticker':'KXNBAGAME','scheduled_ts':when.isoformat(),'fee_type_override':typ,'fee_multiplier_override':mult}
 def test_series_and_override(self):
  self.assertEqual(effective(self.record,self.event,self.now)['fee_multiplier'],'1')
  self.record['event'].update(fee_type_override='quadratic',fee_multiplier_override=2)
  self.record['pages'][0]['event_fee_changes']=[self.change(self.now-timedelta(minutes=1))]
  self.assertEqual(effective(self.record,self.event,self.now)['fee_multiplier'],'2')
 def test_stale_wrong_and_unsupported(self):
  with self.assertRaises(ValueError):effective(self.record,self.event,self.now+timedelta(minutes=6))
  with self.assertRaises(ValueError):effective(self.record,'OTHER',self.now)
  self.record['series']['fee_type']='flat'
  with self.assertRaises(ValueError):effective(self.record,self.event,self.now)
 def test_fee_change_during_observation_rejected(self):
  self.record['pages'][0]['event_fee_changes']=[self.change(self.now-timedelta(seconds=5))]
  with self.assertRaises(ValueError):effective(self.record,self.event,self.now)
 def test_conflict_and_partial_override_rejected(self):
  self.record['pages'][0]['event_fee_changes']=[self.change(self.now-timedelta(minutes=1))]
  with self.assertRaises(ValueError):effective(self.record,self.event,self.now)
  self.record['event']['fee_type_override']='quadratic'
  with self.assertRaises(ValueError):effective(self.record,self.event,self.now)
 def test_future_change_and_incomplete_page(self):
  self.record['pages'][0]['event_fee_changes']=[self.change(self.now+timedelta(minutes=1))]
  self.assertEqual(effective(self.record,self.event,self.now)['fee_multiplier'],'1')
  self.record['pages'][0]['cursor']='more'
  with self.assertRaises(ValueError):effective(self.record,self.event,self.now)

if __name__=='__main__': unittest.main()
