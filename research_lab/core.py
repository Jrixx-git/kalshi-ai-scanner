"""Immutable evidence and common point-in-time checks (stdlib only)."""
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path


def instant(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.utcoffset() is None:
        raise ValueError('timezone_required')
    return dt.astimezone(timezone.utc)


def number(value):
    if isinstance(value, bool):
        raise ValueError('boolean_not_number')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('nonfinite_number')
    return value


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def seal(root, value):
    raw = encode(value)
    digest = hashlib.sha256(raw).hexdigest()
    path = Path(root) / (digest+'.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('xb') as stream:
            stream.write(raw)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise ValueError('immutable_conflict')
    return digest


def read_sealed(root, digest):
    if not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('invalid_digest')
    raw = (Path(root)/(digest+'.json')).read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('evidence_hash_mismatch')
    return json.loads(raw)


def asof(record, cutoff, *, evidence_root=None, synthetic=False):
    """Availability is explicitly evidenced; historical retrieval alone is insufficient."""
    required = ('provider','issued_at','available_at','retrieved_at','evidence_sha256','availability_basis')
    if any(not record.get(k) for k in required):
        raise ValueError('missing_provenance')
    issued, available, retrieved = (instant(record[k]) for k in required[1:4])
    if not issued <= available <= instant(cutoff) or available > retrieved:
        raise ValueError('not_available_at_cutoff')
    basis = record['availability_basis']
    if basis == 'captured':
        if available != retrieved:
            raise ValueError('capture_availability_mismatch')
    elif basis == 'provider_vintage':
        if not record.get('availability_evidence'):
            raise ValueError('vintage_evidence_required')
    elif not (synthetic and basis == 'synthetic'):
        raise ValueError('unsupported_availability_basis')
    if record.get('scrambled') or record.get('reanalysis'):
        raise ValueError('scrambled_or_reanalysis')
    if not re.fullmatch('[0-9a-f]{64}', record['evidence_sha256']):
        raise ValueError('invalid_digest')
    if not synthetic:
        if evidence_root is None:
            raise ValueError('evidence_root_required')
        read_sealed(evidence_root, record['evidence_sha256'])
    return record


def probability(p):
    p = number(p)
    if not 0 <= p <= 1:
        raise ValueError('invalid_probability')
    return p


def prior_rows(rows, decision):
    return [r for r in rows if instant(r['outcome_available_at']) < instant(decision)]
