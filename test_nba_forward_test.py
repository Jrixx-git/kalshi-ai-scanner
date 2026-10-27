import copy
import csv
import io
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nba_forward_test as f


class ForwardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        f.import_baseline('forward_test/baseline/artifact.zip', self.root)
        self.rows = list(f.predictions(self.root).values())
        self.games = [dict(id=int(r['game_id']), home_team={'id': int(r['home_team_id'])},
                           visitor_team={'id': int(r['away_team_id'])},
                           datetime=r['tipoff_utc'], date=r['date'], status='Final',
                           home_team_score=110, visitor_team_score=100)
                      for r, _, _ in self.rows]

    def score(self, games=None):
        return f.scoreboard(self.root, self.games if games is None else games, '2026-10-29T12:00:00Z')

    def payload(self):
        path = next((self.root/'predictions').glob('*/predictions.csv'))
        return path.read_bytes(), (path.parent/'metadata.json').read_bytes()

    def archive(self, rows=None, metadata=None, **kwargs):
        raw, meta = self.payload()
        if rows is not None:
            out = io.StringIO(newline='')
            writer = csv.DictWriter(out, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
            raw = out.getvalue().encode()
            m = json.loads(meta)
            m['csv_sha256'] = f.digest(raw)
            meta = f.encode(m)
        if metadata:
            m = json.loads(meta)
            m.update(metadata)
            meta = f.encode(m)
        return f.archive(raw, meta, self.root, commit=f.BASELINE_COMMIT,
                         run_id=99, observed_at=kwargs.pop('observed_at', '2026-10-27T21:00:00Z'), **kwargs)

    def test_baseline_exact_and_idempotent(self):
        f.import_baseline('forward_test/baseline/artifact.zip', self.root)
        self.assertEqual(len(f.predictions(self.root)), 4)
        self.assertEqual(len(list((self.root/'predictions').iterdir())), 1)
        self.assertAlmostEqual(float(self.rows[0][0]['home_win_probability']), .891554)

    def test_metrics_hand_calculation(self):
        s = self.score()['summary']
        ps = [float(x[0]['home_win_probability']) for x in self.rows]
        self.assertEqual(s['accuracy'], 1)
        self.assertAlmostEqual(s['brier'], sum((1-p)**2 for p in ps)/4)
        self.assertAlmostEqual(s['log_loss'], sum(-math.log(p) for p in ps)/4)

    def test_away_win(self):
        for g in self.games:
            g['visitor_team_score'] = 120
        self.assertEqual(self.score()['summary']['accuracy'], 0)

    def test_unresolved_excluded(self):
        for status, expected in [('Postponed','postponed'), ('Cancelled','cancelled'),
                                 ('Canceled','cancelled'), ('3rd Qtr','unknown'), ('','unknown')]:
            with self.subTest(status=status):
                for g in self.games:
                    g['status'] = status
                report = self.score()
                self.assertEqual(report['summary']['scored'], 0)
                self.assertIsNone(report['summary']['brier'])
                self.assertEqual(report['summary']['statuses'], {expected:4})

    def test_missing(self):
        self.assertEqual(self.score([])['summary']['statuses'], {'missing':4})

    def test_identity(self):
        self.games[0]['home_team']['id'] = 99
        self.assertEqual(self.score()['summary']['scored'], 3)

    def test_bad_scores(self):
        for value in [0, -1, True, 'oops', 100, None, 100.5]:
            with self.subTest(value=value):
                self.games[0]['home_team_score'] = value
                self.assertEqual(self.score()['games'][0]['status'], 'invalid_final')

    def test_conflicting_lifecycle(self):
        self.games[0]['status_state'] = 'live'
        self.assertEqual(self.score()['summary']['scored'], 3)

    def test_duplicates(self):
        self.assertEqual(self.score(self.games+self.games)['summary']['scored'], 4)
        conflict = copy.deepcopy(self.games[0])
        conflict['home_team_score'] += 1
        with self.assertRaises(ValueError):
            self.score(self.games+[conflict])

    def test_first_archive_wins(self):
        rows = [dict(r) for r, _, _ in self.rows]
        rows[0].update(home_win_probability='.1', away_win_probability='.9')
        self.archive(rows)
        self.assertAlmostEqual(self.score()['games'][0]['home_win_probability'], .891554)

    def test_late_or_backdated_archive(self):
        for timestamp in ['2026-10-27T23:30:00Z', '2026-10-28T05:00:00Z', '2026-10-27T19:00:00Z']:
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                self.archive(observed_at=timestamp)

    def test_invalid_prediction(self):
        for p, q in [('nan','nan'), ('inf','-inf'), ('1.1','-.1'), ('.4','.4')]:
            rows = [dict(r) for r, _, _ in self.rows]
            rows[0].update(home_win_probability=p, away_win_probability=q)
            with self.subTest(p=p), self.assertRaises(ValueError):
                self.archive(rows)

    def test_metadata_leakage_and_safety(self):
        for change in [dict(last_history_date='2026-10-27'), dict(history_before='2026-10-28'),
                       dict(live_trading_enabled=True), dict(exported_games=5), dict(csv_sha256='bad')]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.archive(metadata=change)

    def test_integrity(self):
        path = next((self.root/'predictions').glob('*/predictions.csv'))
        path.write_bytes(path.read_bytes()+b'\n')
        with self.assertRaises(ValueError):
            self.score()

    def test_bad_baseline(self):
        path = self.root/'bad.zip'
        path.write_bytes(b'bad')
        with self.assertRaises(ValueError):
            f.import_baseline(path, self.root)

    def test_rescheduled_same_id(self):
        self.games[0]['datetime'] = '2026-10-29T01:00:00Z'
        self.games[0]['date'] = '2026-10-29'
        self.assertEqual(self.score()['summary']['scored'], 4)

    def test_actual_tip_before_observation(self):
        self.games[0]['datetime'] = '2026-10-27T19:00:00Z'
        self.assertEqual(self.score()['summary']['scored'], 3)

    def test_future_final(self):
        self.games[0]['datetime'] = '2026-10-30T01:00:00Z'
        self.assertEqual(self.score()['summary']['scored'], 3)

    def test_retrieve_get_ids_and_snapshot(self):
        def fetch(key, gid):
            self.assertEqual(key, 'secret')
            return next(g for g in self.games if str(g['id']) == gid)
        with patch('nba_forward_test.datetime') as clock:
            from datetime import datetime
            clock.now.return_value = datetime.fromisoformat('2026-10-29T12:00:00+00:00')
            result = f.retrieve(self.root, 'secret', fetch=fetch, pause=0)
        self.assertEqual(result['summary']['scored'], 4)
        self.assertNotIn('secret', next((self.root/'results').glob('*.json')).read_text())

    def test_failed_fetch_no_result(self):
        def fail(*args, **kwargs):
            raise RuntimeError('offline')
        with self.assertRaises(RuntimeError):
            f.retrieve(self.root, 'secret', fetch=fail)
        self.assertFalse((self.root/'results').exists())

    def test_daily_denominators_and_markdown(self):
        self.games[0]['status'] = 'Postponed'
        report = self.score()
        self.assertEqual(report['daily']['2026-10-27']['scored'], 3)
        self.assertIn('| 2026-10-27 | 4 | 3 |', f.markdown(report))

    def test_prediction_identity_conflict(self):
        rows = [dict(r) for r, _, _ in self.rows]
        rows[0]['home_team_id'] = '99'
        self.archive(rows)
        with self.assertRaises(ValueError):
            self.score()

    def test_log_loss_endpoints_and_tie(self):
        root = self.root/'independent'
        raw, meta = self.payload()
        rows = list(csv.DictReader(io.StringIO(raw.decode())))
        for row, p in zip(rows, [0, 1, .5, .5]):
            row['home_win_probability'] = str(p)
            row['away_win_probability'] = str(1-p)
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        raw = stream.getvalue().encode()
        m = json.loads(meta)
        m['csv_sha256'] = f.digest(raw)
        f.archive(raw, f.encode(m), root, commit=f.BASELINE_COMMIT, run_id=99,
                  observed_at='2026-10-27T21:00:00Z')
        report = f.scoreboard(root, self.games, '2026-10-29T12:00:00Z')
        self.assertEqual(report['summary']['accuracy'], .75)
        self.assertTrue(math.isfinite(report['summary']['log_loss']))

    def test_final_cache_freeze_and_refresh(self):
        from datetime import datetime
        def fetch(key, gid):
            return next(g for g in self.games if str(g['id']) == gid)
        with patch('nba_forward_test.datetime') as clock:
            clock.now.return_value = datetime.fromisoformat('2026-11-10T12:00:00+00:00')
            f.retrieve(self.root, 'secret', fetch=fetch, pause=0)
            def fail(*args):
                raise RuntimeError('must use cache')
            report = f.retrieve(self.root, 'secret', fetch=fail, pause=0)
            self.assertEqual(report['summary']['scored'], 4)
            with self.assertRaises(RuntimeError):
                f.retrieve(self.root, 'secret', fetch=fail, pause=0, refresh_all=True)

    def test_http_get_single_game_and_404(self):
        import urllib.error
        response = io.BytesIO(json.dumps({'data':self.games[0]}).encode())
        with patch('nba_forward_test.urllib.request.urlopen', return_value=response) as opening:
            f.get_result('secret', str(self.games[0]['id']))
            request = opening.call_args.args[0]
            self.assertEqual(request.get_method(), 'GET')
            self.assertTrue(request.full_url.endswith('/'+str(self.games[0]['id'])))
        with patch('nba_forward_test.urllib.request.urlopen', side_effect=urllib.error.HTTPError('url',404,'missing',{},None)):
            self.assertIsNone(f.get_result('secret', '1'))

    def test_http_auth_redaction_and_missing_key(self):
        import urllib.error
        with self.assertRaises(ValueError):
            f.get_result('', '1')
        with patch('nba_forward_test.urllib.request.urlopen', side_effect=urllib.error.HTTPError('secret',401,'secret',{},None)):
            with self.assertRaisesRegex(RuntimeError, '^BALLDONTLIE HTTP 401$'):
                f.get_result('secret', '1')


if __name__ == '__main__':
    unittest.main()
