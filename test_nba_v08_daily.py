import tempfile, unittest, shutil
from pathlib import Path
from nba_v08_daily import fee_history,publish,run

class DailyAuditTests(unittest.TestCase):
 def test_pagination_and_cursor_loop(self):
  def fetch(path,params):
   return {'event_fee_changes':[{'event_ticker':'EVENT'}], 'cursor':'' if params.get('cursor') else 'next'}
  self.assertEqual(len(fee_history('EVENT',fetch)),2)
  with self.assertRaises(ValueError):fee_history('EVENT',lambda path,params:{'event_fee_changes':[],'cursor':'x'})
 def test_wrong_event_fails(self):
  with self.assertRaises(ValueError):fee_history('EVENT',lambda path,params:{'event_fee_changes':[{'event_ticker':'WRONG'}]})
 def test_audit_history_content_addressed(self):
  with tempfile.TemporaryDirectory() as d:
   one=publish(d,{'positions':[]}); two=publish(d,{'positions':[1]})
   self.assertNotEqual(one,two)
   self.assertTrue((Path(d)/'audits'/(one+'.json')).exists())
   self.assertEqual((Path(d)/'daily.json').read_bytes(),(Path(d)/'audits'/(two+'.json')).read_bytes())
 def test_real_archives_with_fixture_current_data(self):
  def fetch(path,params=None):
   if path=='/events/fee_changes':return {'event_fee_changes':[],'cursor':''}
   if path.endswith('/orderbook'):return {'orderbook_fp':{'yes_dollars':[['.40','10']],'no_dollars':[['.50','10']]}}
   return {'market':{'ticker':path.rsplit('/',1)[-1],'status':'active','result':''}}
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'state';shutil.copytree('paper_v08/state',root)
   r=run(root,fetch=fetch)
   self.assertGreaterEqual(r['open_positions']+r['settled_positions'],9)
   self.assertFalse(r['errors']);self.assertFalse(r['duplicate_games']);self.assertFalse(r['duplicate_events'])
   self.assertTrue(all(p['entry_verified'] for p in r['positions']))

if __name__=='__main__':unittest.main()
