import io
import unittest
import urllib.error
from unittest.mock import Mock
from trial_entitlements import probe, summarize, NoRedirect

class TrialTests(unittest.TestCase):
    def test_echo_rejected(self):
        with self.assertRaises(ValueError): summarize(b'{"error":"sensitive-key"}', 'sensitive-key')
    def test_schema_does_not_export_player_values(self):
        result=summarize(b'[{"Name":"PRIVATE_VALUE","Points":12,"Updated":"2026-11-11T12:00:00","IsScrambled":true}]','secret')
        self.assertEqual(result['rows'],1)
        self.assertNotIn('PRIVATE_VALUE',str(result))
        self.assertEqual(result['explicit_scrambled_flags'],['True'])
    def test_empty_is_accessible_empty_and_get_only(self):
        response=Mock();response.code=200;response.read.return_value=b'[]';response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        opener=Mock();opener.open.return_value=response
        result=probe('/v3/nba/projections/json/StartingLineupsByDate/2026-11-11','secret',opener)
        self.assertEqual(result['entitlement'],'accessible_empty')
        request=opener.open.call_args.args[0]
        self.assertEqual(request.get_method(),'GET')
        self.assertNotIn('secret',request.full_url)
    def test_denied_never_exports_error_body(self):
        opener=Mock();opener.open.side_effect=urllib.error.HTTPError('https://api.sportsdata.io',403,'denied',{},io.BytesIO(b'secret'))
        result=probe('/v3/nba/projections/json/StartingLineupsByDate/2026-11-11','secret',opener)
        self.assertEqual(result['entitlement'],'forbidden')
        self.assertNotIn('secret',str(result))
    def test_redirect_not_followed(self):
        self.assertIsNone(NoRedirect().redirect_request(None,None,None,None,None,None))

if __name__=='__main__':unittest.main()
