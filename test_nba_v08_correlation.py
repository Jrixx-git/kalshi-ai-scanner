import tempfile,unittest
from pathlib import Path
from paper_engine import PaperEngine

class CorrelationTests(unittest.TestCase):
 def test_nba_entry_requires_correlation_evidence(self):
  with tempfile.TemporaryDirectory() as d:
   e=PaperEngine(Path(d)/'l.db')
   self.assertFalse(e.enter(signal_id='s',ticker='KXNBAGAME-XYZ',side='YES',ask='.5',ask_size=2,contracts=1,fee='.02')[0]); e.close()
 def test_shared_team_and_same_event_caps_are_atomic(self):
  with tempfile.TemporaryDirectory() as d:
   e=PaperEngine(Path(d)/'l.db')
   def enter(s,t,event,home,away,n):
    proof={'forecast':{'home_team_id':home,'away_team_id':away},'market':{'ticker':t,'event_ticker':event}}
    return e.enter(signal_id=s,ticker=t,side='YES',ask='.5',ask_size=100,contracts=n,fee='0',evidence=proof)
   self.assertTrue(enter('a','EV1-X','EV1','1','2',90)[0])
   self.assertFalse(enter('b','EV2-X','EV2','1','3',20)[0])
   self.assertFalse(enter('c','EV1-Y','EV1','4','5',20)[0])
   self.assertFalse(enter('c2','EV1-Y','EV1','4','5',1)[0])
   self.assertTrue(enter('d','EV3-X','EV3','4','5',20)[0])
   self.assertEqual(e.db.execute('select count(*) from trades').fetchone()[0],2)
   e.close()

if __name__=='__main__': unittest.main()
