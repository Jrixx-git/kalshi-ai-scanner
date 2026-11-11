"""Workflow invariants protecting time-sensitive paper evidence collection."""
import unittest
from pathlib import Path

class ResultWorkflowTest(unittest.TestCase):
    def test_paper_evidence_precedes_bounded_scoring(self):
        text = Path('.github/workflows/nba-forward-test.yml').read_text()
        self.assertLess(text.index('Seal predictions before'), text.index('Capture and reconcile'))
        self.assertLess(text.index('Persist NBA paper evidence'), text.index('Retrieve official provider'))
        self.assertIn('timeout-minutes: 25', text)
        self.assertIn('--max-requests 60 --max-seconds 1200', text)
        self.assertIn("if: always() && steps.score.outcome == 'failure'", text)
        self.assertIn("LIVE_TRADING_ENABLED: 'false'", text)
