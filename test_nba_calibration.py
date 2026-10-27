import csv
import math
import tempfile
import unittest
from pathlib import Path
from nba_calibration import evaluate, fit_temperature, metrics, read_predictions, transform


class CalibrationTests(unittest.TestCase):
    def test_transform(self):
        self.assertAlmostEqual(transform(.8,1),.8)
        self.assertAlmostEqual(transform(.5,2),.5)
        self.assertTrue(.5 < transform(.8,2) < .8)
        self.assertAlmostEqual(transform(.2,2),1-transform(.8,2))
        self.assertTrue(math.isfinite(transform(0,.001)))
        self.assertEqual(transform(1,.001),1)

    def test_invalid(self):
        for p in (-1,2,float('nan'),float('inf')):
            with self.assertRaises(ValueError): transform(p,1)
        for t in (0,-1,float('nan')):
            with self.assertRaises(ValueError): transform(.5,t)
        for ps,ys in [([],[]),([.5],[]),([.5],[2])]:
            with self.assertRaises(ValueError): fit_temperature(ps,ys)

    def test_metrics_edges(self):
        m=metrics([0,.1,.9,1],[0,0,1,1])
        self.assertAlmostEqual(m['brier'],.005)
        self.assertEqual([b['n'] for b in m['bins']],[1,1,0,0,0,0,0,0,0,2])
        self.assertEqual(metrics([.5,.5],[0,1])['brier'],.25)
        self.assertAlmostEqual(metrics([.5],[1])['log_loss'],math.log(2))

    def test_overconfidence(self):
        ps=[.9]*10; ys=[1]*6+[0]*4
        t=fit_temperature(ps,ys)
        self.assertGreater(t,1)
        self.assertLess(metrics([transform(p,t) for p in ps],ys)['log_loss'],metrics(ps,ys)['log_loss'])

    def rows(self):
        return [dict(date='2024-10-01',home_win_probability=.9,home_win=y) for y in [0,1,1]] + [dict(date='2025-10-01',home_win_probability=.8,home_win=1)]

    def test_test_outcomes_do_not_affect_fit(self):
        rows=self.rows(); a=evaluate(rows)
        rows[-1]['home_win']=0; b=evaluate(rows)
        self.assertEqual(a['temperature'],b['temperature'])
        self.assertNotEqual(a['test']['raw']['brier'],b['test']['raw']['brier'])
        self.assertEqual(a['validation']['raw']['n'],3)
        self.assertEqual(a['test']['raw']['n'],1)

    def test_empty_and_bad_windows(self):
        for v,t in [('2025-10-01','2024-10-01'),('2026-10-01','2027-10-01'),('2024-01-01','2027-10-01')]:
            with self.assertRaises(ValueError): evaluate(self.rows(),v,t)

    def test_earlier_rows_excluded(self):
        rows=self.rows(); a=evaluate(rows)
        rows.append(dict(date='2023-01-01',home_win_probability=.01,home_win=1))
        b=evaluate(rows)
        self.assertEqual(a['temperature'],b['temperature'])
        self.assertEqual(b['excluded_earlier_rows'],1)

    def test_csv_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'input.csv'
            header='game_id,date,home_team_id,away_team_id,home_win_probability,home_win\n'
            valid='1,2024-10-01,2,3,.8,1\n'
            p.write_text(header+valid)
            self.assertEqual(len(read_predictions(p)),1)
            for body in (valid+valid,valid.replace(',2,3,',',2,2,'),valid.replace('2024-10-01','bad'),valid.replace('.8','nan')):
                p.write_text(header+body)
                with self.assertRaises(ValueError): read_predictions(p)


if __name__ == '__main__':
    unittest.main()
