import unittest
from unittest.mock import Mock,patch
import collect
class AuditTests(unittest.TestCase):
    def test_alias_and_mapping(self):
        games=[dict(HomeTeam='NY',AwayTeam='CLE',HomeTeamID=1,AwayTeamID=2,GameID=3)]
        rows=collect.mapping(games,[dict(GameID=3,HomeLineup=[dict(PlayerID=4)],AwayLineup=[])],[dict(GameID=3,PlayerID=4,Team='NY',TeamID=1,Name='DO_NOT_EXPORT',InjuryNotes='PRIVATE')],[])
        self.assertEqual(rows[0]['lineup_ids_in_projection'],1)
        self.assertNotIn('DO_NOT_EXPORT',str(rows));self.assertNotIn('PRIVATE',str(rows))
        self.assertTrue(all(r['classification']=='inconclusive' for r in rows))
    def test_ambiguous_game_fails_closed(self):
        g=dict(HomeTeam='NYK',AwayTeam='CLE',GameID=3)
        self.assertNotIn('sportsdataio_game_id',collect.mapping([g,g],[],[],[])[0])
    def test_get_no_query_secret_or_error_body(self):
        r=Mock();r.code=403;r.headers={};r.read.return_value=b'sensitive';r.__enter__=Mock(return_value=r);r.__exit__=Mock(return_value=False)
        op=Mock();op.open.return_value=r
        with patch('collect.urllib.request.build_opener',return_value=op): item,rows=collect.get('projections/json/InjuredPlayers','sensitive')
        req=op.open.call_args.args[0]
        self.assertEqual(req.get_method(),'GET');self.assertNotIn('sensitive',req.full_url)
        self.assertNotIn('sensitive',str(item));self.assertEqual(rows,[])
    def test_redirect_rejected(self): self.assertIsNone(collect.NoRedirect().redirect_request(None,None,None,None,None,None))
if __name__=='__main__':unittest.main()