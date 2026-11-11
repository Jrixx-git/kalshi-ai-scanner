"""Recover only the verified, originally sealed November 10 forecast bundle."""
import argparse
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from nba_forward_test import archive, encode, immutable

ARTIFACT_SHA256 = '9f465d48d6e09b5d486284add58f96251204d52d355246154e9ccd6a3c1f52c4'
BUNDLE = 'b8e4d2b8e4d6d7bd86bfc2c2a8b6c0a2dc30b2eefaa2bef5872583801e430106'
SOURCE_COMMIT = '9047ba40486343c6c7e438b1b04e734bc28ede78'
FILES = ('predictions.csv', 'metadata.json', 'history.json', 'schedule.json', 'manifest.json')


def recover(data, root):
    if hashlib.sha256(data).hexdigest() != ARTIFACT_SHA256:
        raise ValueError('Original artifact ZIP checksum mismatch')
    prefix = 'forward_test/state/predictions/' + BUNDLE + '/'
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if any(z.namelist().count(prefix + name) != 1 for name in FILES):
            raise ValueError('Missing or duplicate original archive member')
        original = {name: z.read(prefix + name) for name in FILES}
    manifest = json.loads(original['manifest.json'])
    if (manifest['run_id'] != '42860751065' or manifest['source_commit'] != SOURCE_COMMIT
            or manifest['observed_at'] != '2026-11-10T17:02:39.419340+00:00'):
        raise ValueError('Unexpected original provenance')
    # Validate in memory before writing any state; preserve the original seal exactly.
    import tempfile
    with tempfile.TemporaryDirectory() as temporary:
        identifier = archive(original['predictions.csv'], original['metadata.json'], temporary,
                             commit=SOURCE_COMMIT, run_id=manifest['run_id'],
                             observed_at=manifest['observed_at'],
                             snapshots={name: original[name] for name in ('history.json', 'schedule.json')})
        if identifier != BUNDLE or (Path(temporary) / 'predictions' / BUNDLE / 'manifest.json').read_bytes() != original['manifest.json']:
            raise ValueError('Original seal mismatch')
    directory = Path(root) / 'predictions' / BUNDLE
    # Preflight every destination before adding anything; conflicting evidence is never replaced.
    for name, content in original.items():
        destination = directory / name
        if destination.exists() and destination.read_bytes() != content:
            raise ValueError('Immutable archive conflict: ' + str(destination))
    receipt = Path(root) / 'recoveries' / 'artifact-13783993857.json'
    if receipt.exists():
        prior = json.loads(receipt.read_bytes())
        if prior['artifact_sha256'] != ARTIFACT_SHA256 or prior['bundle'] != BUNDLE:
            raise ValueError('Recovery receipt conflict')
    for name in FILES:
        immutable(directory / name, original[name])
    if not receipt.exists():
        immutable(receipt, encode(dict(
            recovered_at=datetime.now(timezone.utc).isoformat(),
            artifact_id=13783993857, artifact_sha256=ARTIFACT_SHA256,
            artifact_created_at='2026-11-10T17:02:44Z',
            source_run='https://github.com/Jrixx-git/kalshi-ai-scanner/actions/runs/42860751065',
            source_commit=SOURCE_COMMIT, bundle=BUNDLE,
            original_observed_at=manifest['observed_at'],
            method='Copy original sealed bytes from checksum-verified Actions artifact; no predictions regenerated',
            files={name:hashlib.sha256(content).hexdigest() for name, content in original.items()})))
    return BUNDLE


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('artifact', type=Path)
    p.add_argument('--root', default='forward_test/state')
    args = p.parse_args()
    print(recover(args.artifact.read_bytes(), args.root))
