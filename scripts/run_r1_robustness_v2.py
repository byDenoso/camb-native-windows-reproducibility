#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tarfile

import run_r1_robustness as legacy

ARCHIVE_REL = Path('r1_scientific_harness/ascom00323-paper-source.tar.gz')
MANIFEST_REL = Path('r1_scientific_harness/source-manifest.json')
MANIFEST_CANONICAL_SHA256 = '600cdef851ea4834f1e25456f51c9a044c6ef97f95c66d4888e20397b54d5f61'


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
    ).encode('utf-8')


def _safe_extract(tf: tarfile.TarFile, destination: Path) -> None:
    root = destination.resolve()
    for member in tf.getmembers():
        target = (destination / member.name).resolve()
        if target != root and root not in target.parents:
            raise RuntimeError(f'unsafe tar member: {member.name}')
        if member.issym() or member.islnk():
            raise RuntimeError(f'links forbidden in scientific harness: {member.name}')
    tf.extractall(destination)


def decode_canonical_harness(repo: Path, work: Path) -> tuple[Path, bytes]:
    manifest = json.loads((repo / MANIFEST_REL).read_text(encoding='utf-8'))
    manifest_identity = canonical_json_bytes(manifest)
    observed_manifest = sha256_bytes(manifest_identity)
    if observed_manifest != MANIFEST_CANONICAL_SHA256:
        raise RuntimeError(
            'scientific harness canonical manifest identity mismatch: '
            f'{observed_manifest}'
        )

    archive_path = repo / ARCHIVE_REL
    archive_bytes = archive_path.read_bytes()
    observed_archive = sha256_bytes(archive_bytes)
    if observed_archive != manifest['archive_sha256']:
        raise RuntimeError(f'scientific harness archive mismatch: {observed_archive}')

    with tarfile.open(archive_path, 'r:gz') as tf:
        _safe_extract(tf, work)

    root = work / 'r1_scientific_harness'
    expected_paths = set()
    for entry in manifest['files']:
        rel = Path(entry['path'])
        expected_paths.add(rel.as_posix())
        path = root / rel
        if not path.is_file():
            raise RuntimeError(f'scientific harness file missing: {rel.as_posix()}')
        data = path.read_bytes()
        if len(data) != int(entry['size_bytes']):
            raise RuntimeError(f'scientific harness size mismatch: {rel.as_posix()}')
        if sha256_bytes(data) != entry['sha256']:
            raise RuntimeError(f'scientific harness hash mismatch: {rel.as_posix()}')

    actual_paths = {
        p.relative_to(root).as_posix()
        for p in root.rglob('*')
        if p.is_file()
    }
    if actual_paths != expected_paths:
        extra = sorted(actual_paths - expected_paths)
        missing = sorted(expected_paths - actual_paths)
        raise RuntimeError(
            f'scientific harness file-set mismatch: extra={extra}, missing={missing}'
        )

    if not (root / 'peer_platform/paper_validation_v6.py').is_file():
        raise RuntimeError('scientific harness extraction incomplete')
    return root, manifest_identity


_original_receipt = legacy.receipt


def receipt(gate: str, passed: bool, observed: dict):
    if gate == 'R01':
        observed = dict(observed)
        observed.pop('parts', None)
        observed['authority'] = 'canonical-json-manifest + verified source archive'
    return _original_receipt(gate, passed, observed)


legacy.HARNESS_SHA = MANIFEST_CANONICAL_SHA256
legacy.decode_canonical_harness = decode_canonical_harness
legacy.receipt = receipt

if __name__ == '__main__':
    raise SystemExit(legacy.main())
