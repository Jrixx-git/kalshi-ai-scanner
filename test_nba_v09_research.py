import copy
import json
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path
from nba_v09_research import audit, paired, quality, hypothetical, metrics, evidence
from nba_v09_injuries import collect, publication, asof, fetch, INDEX
from nba_forward_test import predictions
from nba_v09_collect import collect as prospective_collect


class ResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = audit('forward_test/state', 'paper_v08/state')
        cls.row = next(r for r in cls.report['rows'] if r['status'] == 'matched')
        cls.game, _, cls.bundle = predictions('forward_test/state')[cls.row['game_id']]
        cls.snap = json.loads((Path('paper_v08/state/snapshots')/(cls.row['snapshot']+'.json')).read_bytes())
        cls.schedule = json.loads((Path('paper_v08/state/schedules')/(cls.row['schedule']+'.json')).read_bytes())

    def test_all_forecasts_accounted_no_admissions(self):
        r = self.report
        self.assertEqual(r['counts']['eligible'], r['counts']['matched']+r['counts']['missing_valid_asof_quote']+r['counts']['missing_forecast'])
        self.assertTrue(all(x['no_trade'] for x in r['rows']))
        self.assertEqual(r['counts']['scored'], r['matched_metrics']['n'])
        self.assertEqual(sum(x['n'] for x in r['disagreement_bins']), r['counts']['scored'])

    def test_future_seal_and_post_tip_quote_rejected(self):
        bundle = dict(self.bundle, observed_at='2099-01-01T00:00:00Z')
        with self.assertRaises(ValueError):
            paired(self.game, bundle, self.snap, self.schedule)
        snap = copy.deepcopy(self.snap)
        snap['completed_at'] = self.game['tipoff_utc']
        with self.assertRaises(ValueError):
            paired(self.game, self.bundle, snap, self.schedule)

    def test_identity_and_book_time_rejected(self):
        snap = copy.deepcopy(self.snap)
        snap['markets'] = []
        with self.assertRaises(ValueError):
            paired(self.game, self.bundle, snap, self.schedule)
        snap = copy.deepcopy(self.snap)
        snap['orderbooks'][self.row['ticker']]['received_at'] = '2099-01-01T00:00:00Z'
        with self.assertRaises(ValueError):
            paired(self.game, self.bundle, snap, self.schedule)

    def test_spurs_divergence_and_missing_fees_fail_closed(self):
        self.assertIn('major_model_market_divergence', quality(.809, .90, .02))
        self.assertIn('invalid_probability', quality(float('nan'), .5, .01))
        row = dict(self.row, flags=[])
        self.assertEqual(hypothetical(row, [])['status'], 'fee_unavailable_or_conflicting')
        row['flags'] = ['major_model_market_divergence']
        self.assertEqual(hypothetical(row, [])['status'], 'blocked_quality')
        self.assertIn('wide_spread', quality(.5, .5, .11))

    def test_tampered_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/('0'*64+'.json')).write_text('{}')
            with self.assertRaises(ValueError):
                evidence(directory)

    def test_future_fees_cannot_justify_earlier_entry(self):
        row = dict(self.row, flags=[])
        fees = evidence('paper_v08/state/fees')
        future = [(sha, dict(record, received_at='2099-01-01T00:00:00Z')) for sha,record in fees]
        self.assertEqual(hypothetical(row, future)['status'], 'fee_unavailable_or_conflicting')

    def test_metrics_known_values_and_empty(self):
        r = metrics([dict(elo=.5, market=.75, outcome=1)])
        self.assertEqual(r['elo_brier'], .25)
        self.assertEqual(r['market_brier'], .0625)
        self.assertIsNone(metrics([])['elo_brier'])

    def test_schedule_game_without_forecast_stays_in_denominator(self):
        forecasts = predictions('forward_test/state')
        gid = next(r['game_id'] for r in self.report['rows'] if r['schedule_archives'])
        del forecasts[gid]
        with patch('nba_v09_research.predictions', return_value=forecasts):
            result = audit('forward_test/state', 'paper_v08/state')
        self.assertEqual(result['counts']['universe'], self.report['counts']['universe'])
        self.assertEqual(next(r for r in result['rows'] if r['game_id']==gid)['status'], 'missing_forecast')


class InjuryTests(unittest.TestCase):
    def test_allowlist_and_eastern_publication(self):
        url = 'https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-11-11_11_00AM.pdf'
        self.assertEqual(publication(url), '2026-11-11T16:00:00+00:00')
        for bad in [url+'?x=1', 'http://localhost/a.pdf', url.replace('nba.com', 'nba.com.evil')]:
            with self.assertRaises(ValueError):
                fetch(bad)

    def test_bounded_immutable_raw_and_asof(self):
        urls = ['https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-01-01_01_00AM.pdf',
                'https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-01-01_02_00AM.pdf']
        calls = []
        def get(url):
            calls.append(url)
            return (''.join('<a href="'+u+'">report</a>' for u in urls).encode() if url == INDEX else b'%PDF-test'), {}
        with tempfile.TemporaryDirectory() as directory:
            records = collect(directory, max_reports=1, get=get)
            self.assertEqual(len(calls), 2)
            report = records[-1]
            self.assertEqual((Path(directory)/'raw'/report['sha256']).read_bytes(), b'%PDF-test')
            self.assertFalse(asof(report, '2025-01-01T00:00:00Z')['raw_available_asof'])
            state = asof(report, datetime.now(timezone.utc).isoformat())
            self.assertTrue(state['raw_available_asof'])
            self.assertFalse(state['player_availability_verified'])
            self.assertTrue(state['no_trade'])

    def test_failure_does_not_claim_healthy_or_retry(self):
        calls = []
        def get(url):
            calls.append(url)
            raise OSError('offline')
        with tempfile.TemporaryDirectory() as directory:
            records = collect(directory, get=get)
            self.assertEqual(len(calls), 1)
            self.assertEqual(records[0]['status'], 'unavailable')

    def test_limits_and_invalid_pdf(self):
        with self.assertRaises(ValueError):
            collect('unused', max_reports=5)
        url = 'https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-01-01_01_00AM.pdf'
        def get(u):
            return (('<a href="'+url+'">report</a>').encode() if u==INDEX else b'<html>bad</html>'), {}
        with tempfile.TemporaryDirectory() as directory:
            records = collect(directory, get=get)
            self.assertEqual(records[-1]['status'], 'unavailable')


class ProspectiveTests(unittest.TestCase):
    def test_retrospective_capture_rejected_before_network(self):
        with patch('nba_v09_collect.fetch_games') as get:
            with self.assertRaises(ValueError):
                prospective_collect('2020-01-01', 'unused')
            get.assert_not_called()

    def test_missing_existing_key_fails_before_quote_collection(self):
        from nba_daily_predictions import EASTERN
        day = datetime.now(timezone.utc).astimezone(EASTERN).date().isoformat()
        with patch.dict('os.environ', {}, clear=True), patch('nba_v09_collect.capture') as capture:
            with self.assertRaises(ValueError):
                prospective_collect(day, 'unused')
            capture.assert_not_called()


if __name__ == '__main__':
    unittest.main()
