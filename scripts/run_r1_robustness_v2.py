#!/usr/bin/env python3
from __future__ import annotations

import base64
from pathlib import Path
import sys
import tarfile

import run_r1_robustness as legacy


def decode_canonical_harness(repo: Path, work: Path) -> tuple[Path, bytes]:
    parts = sorted((repo / 'r1_scientific_harness/canonical_parts').glob('part*.b64'))
    expected_names = [f'part{i:02d}.b64' for i in range(1, 5)]
    if [p.name for p in parts] != expected_names:
        raise RuntimeError(f'canonical harness parts mismatch: {[p.name for p in parts]}')

    decoded_parts = []
    for path in parts:
        encoded = ''.join(path.read_text(encoding='ascii').split())
        decoded_parts.append(base64.b64decode(encoded, validate=True))
    payload = b''.join(decoded_parts)

    observed = legacy.sha256_bytes(payload)
    if observed != legacy.HARNESS_SHA:
        raise RuntimeError(f'canonical harness SHA mismatch: {observed}')

    archive = work / 'canonical-harness.tar.gz'
    archive.write_bytes(payload)
    with tarfile.open(archive, 'r:gz') as tf:
        tf.extractall(work)
    root = work / 'r1_scientific_harness'
    if not (root / 'peer_platform/paper_validation_v6.py').is_file():
        raise RuntimeError('canonical harness extraction incomplete')
    return root, payload


legacy.decode_canonical_harness = decode_canonical_harness

if __name__ == '__main__':
    raise SystemExit(legacy.main())
