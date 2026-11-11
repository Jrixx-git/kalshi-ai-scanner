import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import nba_forecast_recovery as recovery
from nba_forward_test import predictions


class RecoveryTests(unittest.TestCase):
    def fixture(self):
        source = Path('forward_test/state/predictions') / recovery.BUNDLE
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as z:
            for name in recovery.FILES:
                z.writestr('forward_test/state/predictions/' + recovery.BUNDLE + '/' + name,
                           (source / name).read_bytes())
        return stream.getvalue()

    def test_copy_preserves_seal_timestamps_and_is_idempotent(self):
        data = self.fixture()
        with tempfile.TemporaryDirectory() as root, patch.object(recovery, 'ARTIFACT_SHA256', hashlib.sha256(data).hexdigest()):
            recovery.recover(data, root)
            receipt = Path(root) / 'recoveries/artifact-13783993857.json'
            before = receipt.read_bytes()
            self.assertEqual(len(predictions(root)), 6)
            for name in recovery.FILES:
                self.assertEqual((Path(root) / 'predictions' / recovery.BUNDLE / name).read_bytes(),
                                 (Path('forward_test/state/predictions') / recovery.BUNDLE / name).read_bytes())
            recovery.recover(data, root)
            self.assertEqual(receipt.read_bytes(), before)

    def test_modified_artifact_rejected_without_state(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, 'checksum'):
                recovery.recover(self.fixture() + b'changed', root)
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_existing_conflict_is_never_overwritten(self):
        data = self.fixture()
        with tempfile.TemporaryDirectory() as root, patch.object(recovery, 'ARTIFACT_SHA256', hashlib.sha256(data).hexdigest()):
            destination = Path(root) / 'predictions' / recovery.BUNDLE / 'predictions.csv'
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b'existing evidence')
            with self.assertRaisesRegex(ValueError, 'conflict'):
                recovery.recover(data, root)
            self.assertEqual(destination.read_bytes(), b'existing evidence')
            self.assertEqual(list(destination.parent.iterdir()), [destination])


if __name__ == '__main__':
    unittest.main()
