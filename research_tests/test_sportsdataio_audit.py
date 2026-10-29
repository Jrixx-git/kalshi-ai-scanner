import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research_lab import sportsdataio_audit as audit


class Response(io.BytesIO):
    code = 200
    headers = {'Date':'Thu, 29 Oct 2026 21:00:00 GMT','Ocp-Apim-Subscription-Key':'test-only-secret','Set-Cookie':'not-for-artifacts'}


class TrialAuditTests(unittest.TestCase):
    def test_response_echo_does_not_persist_credential(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as root:
            with patch.object(audit,'ROOT',Path(root)), patch.object(audit.urllib.request,'build_opener') as opener:
                opener.return_value.open.return_value=Response(b'{"data":"test-only-secret"}')
                item,payload=audit.request('test','sportsdataio','/v3/nba/scores/json/Players',{},'test-only-secret')
                self.assertIsNone(payload)
                self.assertEqual(item['error'],'ValueError')
                self.assertNotIn('test-only-secret',''.join(p.read_text() for p in Path(root).rglob('*.json')))

    def test_only_safe_headers_and_schema_are_archived(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as root:
            with patch.object(audit,'ROOT',Path(root)), patch.object(audit.urllib.request,'build_opener') as opener:
                opener.return_value.open.return_value=Response(b'[{"PlayerID":123,"Minutes":31,"Updated":"2026-10-29T10:00:00"}]')
                item,payload=audit.request('test','sportsdataio','/v3/nba/projections/json/PlayerGameProjectionStatsByDate/2026-10-30',{},'test-only-secret')
                self.assertEqual(item['status'],200)
                self.assertEqual(item['safe_response_headers'],{'date':'Thu, 29 Oct 2026 21:00:00 GMT'})
                archived=''.join(p.read_text() for p in Path(root).rglob('*.json'))
                self.assertNotIn('test-only-secret',archived)
                self.assertNotIn('"Minutes": 31',archived)
                self.assertFalse(item['benchmark_eligible'])
                self.assertEqual(opener.return_value.open.call_args.args[0].get_method(),'GET')

    def test_null_and_scalar_payloads_cannot_become_records(self):
        for payload in (None,7,'test',{}):
            self.assertEqual(audit.rows(payload),[])
            self.assertEqual(audit.timestamps(payload),{})


if __name__=='__main__':unittest.main()

