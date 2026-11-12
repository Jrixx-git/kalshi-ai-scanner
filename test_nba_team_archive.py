"""Verify real Git staging/checkout preserves receipt and baseline bytes."""
import subprocess
import tempfile
import unittest
from pathlib import Path


class EvidenceBytesTests(unittest.TestCase):
    def test_two_checkpoints_with_depth_one_fetch_and_unforced_push(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            remote,seed,worker=(root/n for n in ('remote.git','seed','worker'))
            for p in (remote,seed,worker):
                p.mkdir()
            def git(where,*args,check=True):
                return subprocess.run(['git',*args],cwd=where,check=check,
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            git(remote,'init','--bare','-q')
            for p in (seed,worker):
                git(p,'init','-q')
                git(p,'config','user.name','Offline archive test')
                git(p,'config','user.email','archive-test@example.invalid')
                git(p,'remote','add','origin',remote.as_uri())
            (seed/'original').write_bytes(b'authentic original\r\n')
            git(seed,'add','original')
            git(seed,'commit','-qm','seed')
            git(seed,'push','origin','HEAD:refs/heads/research/evidence')
            git(worker,'fetch','--depth=1','origin','refs/heads/research/evidence:refs/remotes/origin/team-development')
            old=git(worker,'rev-parse','refs/remotes/origin/team-development').stdout.decode().strip()
            git(worker,'read-tree',old)
            def append(name,parent):
                (worker/name).write_text(name)
                git(worker,'add',name)
                tree=git(worker,'write-tree').stdout.decode().strip()
                commit=git(worker,'commit-tree',tree,'-p',parent,'-m',name).stdout.decode().strip()
                git(worker,'push','origin',commit+':refs/heads/research/evidence')
                return commit
            first=append('prepared',old)
            # A tracking-ref refresh can be rejected because depth-one grafts
            # hide ancestry. FETCH_HEAD is an independent download destination.
            git(worker,'fetch','--depth=1','origin','refs/heads/research/evidence')
            current=git(worker,'rev-parse','FETCH_HEAD').stdout.decode().strip()
            self.assertEqual(current,first)
            git(worker,'read-tree',current)
            final=append('sealed',current)
            self.assertEqual(git(remote,'rev-parse','refs/heads/research/evidence').stdout.decode().strip(),final)
            self.assertEqual(set(git(remote,'ls-tree','--name-only',final).stdout.decode().splitlines()),
                             {'original','prepared','sealed'})

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
