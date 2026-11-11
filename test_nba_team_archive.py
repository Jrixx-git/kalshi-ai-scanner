"""Verify real Git staging/checkout preserves receipt and baseline bytes."""
import subprocess
import tempfile
import unittest
from pathlib import Path


class EvidenceBytesTests(unittest.TestCase):
    def test_research_archive_roundtrip_with_windows_line_endings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def git(*args):
                return subprocess.run(['git', *args], cwd=root, check=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

            git('init', '-q')
            git('config', 'core.autocrlf', 'true')
            (root/'.gitattributes').write_bytes(Path('.gitattributes').read_bytes())
            files = {
                'team-development/baseline/predictions/example/predictions.csv': b'game_id,p\r\n10,0.6\r\n',
                'team-development/team-history/raw/example': b'{\r\n  "data": []\r\n}\r\n',
                'team-development/slots/example/source/injuries/raw/example': b'%PDF-1.7\r\n\x00\xff\n',
            }
            for name, raw in files.items():
                p = root/name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(raw)
            git('add', '--', '.gitattributes', 'team-development')
            for name, raw in files.items():
                self.assertEqual(git('show', ':'+name), raw)
            destination = root/'restored'
            destination.mkdir()
            git('checkout-index', '--all', '--prefix='+destination.as_posix()+'/')
            for name, raw in files.items():
                self.assertEqual((destination/name).read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
