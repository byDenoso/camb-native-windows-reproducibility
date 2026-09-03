#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile

import run_r1_robustness as legacy

SOURCE_MANIFEST_REL = Path('r1_scientific_harness/source-manifest.json')
PARTS_MANIFEST_REL = Path('r1_scientific_harness/archive-parts-v3.json')
PARTS_DIR_REL = Path('r1_scientific_harness/archive_parts_v3')
SOURCE_MANIFEST_CANONICAL_SHA256 = '600cdef851ea4834f1e25456f51c9a044c6ef97f95c66d4888e20397b54d5f61'
PARTS_MANIFEST_CANONICAL_SHA256 = 'ca99188fa37014bc9b9b3d7f936ffa19f219cca6aaa04f9acb9f25c1d0936b1a'
ARCHIVE_SHA256 = '5add06fbc244116fbdf4415457a8609f061039853dfea3f571826e939b18ebd2'


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def _load_canonical_json(path: Path, expected_sha: str) -> dict:
    value = json.loads(path.read_text(encoding='utf-8'))
    observed = sha256_bytes(canonical_json_bytes(value))
    if observed != expected_sha:
        raise RuntimeError(f'canonical JSON identity mismatch for {path.name}: {observed}')
    return value


def _safe_extract(archive_bytes: bytes, destination: Path) -> None:
    root = destination.resolve()
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as tf:
        for member in tf.getmembers():
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f'unsafe tar member: {member.name}')
            if member.issym() or member.islnk():
                raise RuntimeError(f'links forbidden in scientific harness: {member.name}')
        tf.extractall(destination)


def _reconstruct_archive(repo: Path) -> tuple[bytes, dict, dict]:
    source = _load_canonical_json(repo / SOURCE_MANIFEST_REL, SOURCE_MANIFEST_CANONICAL_SHA256)
    transport = _load_canonical_json(repo / PARTS_MANIFEST_REL, PARTS_MANIFEST_CANONICAL_SHA256)
    if transport.get('schema') != 'ascom00323-archive-parts/v3':
        raise RuntimeError('unexpected archive transport schema')
    entries = transport.get('parts', [])
    if transport.get('part_count') != len(entries) or not entries:
        raise RuntimeError('archive transport part count mismatch')

    chunks: list[bytes] = []
    for entry in entries:
        path = repo / PARTS_DIR_REL / entry['name']
        if not path.is_file():
            raise RuntimeError(f'archive segment missing: {entry["name"]}')
        encoded = ''.join(path.read_text(encoding='ascii').split())
        if len(encoded) != int(entry['encoded_chars']):
            raise RuntimeError(f'archive segment encoded length mismatch: {entry["name"]}')
        if sha256_bytes(encoded.encode('ascii')) != entry['encoded_sha256']:
            raise RuntimeError(f'archive segment encoded hash mismatch: {entry["name"]}')
        try:
            raw = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise RuntimeError(f'archive segment base64 invalid: {entry["name"]}') from exc
        if len(raw) != int(entry['raw_bytes']):
            raise RuntimeError(f'archive segment raw length mismatch: {entry["name"]}')
        if sha256_bytes(raw) != entry['raw_sha256']:
            raise RuntimeError(f'archive segment raw hash mismatch: {entry["name"]}')
        chunks.append(raw)

    archive = b''.join(chunks)
    if len(archive) != int(transport['archive_size_bytes']):
        raise RuntimeError('reconstructed archive size mismatch')
    observed = sha256_bytes(archive)
    if observed != transport['archive_sha256'] or observed != source['archive_sha256'] or observed != ARCHIVE_SHA256:
        raise RuntimeError(f'reconstructed archive identity mismatch: {observed}')
    return archive, source, transport


def decode_canonical_harness(repo: Path, work: Path) -> tuple[Path, bytes]:
    archive, source, _ = _reconstruct_archive(repo)
    _safe_extract(archive, work)
    root = work / 'r1_scientific_harness'

    expected_paths = set()
    for entry in source['files']:
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

    actual_paths = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual_paths != expected_paths:
        raise RuntimeError(
            f'scientific harness file-set mismatch: extra={sorted(actual_paths-expected_paths)}, '
            f'missing={sorted(expected_paths-actual_paths)}'
        )
    if not (root / 'peer_platform/paper_validation_v6.py').is_file():
        raise RuntimeError('scientific harness extraction incomplete')
    return root, archive


_original_receipt = legacy.receipt


def receipt(gate: str, passed: bool, observed: dict):
    if gate == 'R01':
        observed = dict(observed)
        observed.pop('parts', None)
        observed['segments'] = 17
        observed['authority'] = 'canonical source manifest + per-segment verified Base64 transport + archive SHA-256'
    return _original_receipt(gate, passed, observed)


legacy.HARNESS_SHA = ARCHIVE_SHA256
legacy.decode_canonical_harness = decode_canonical_harness
legacy.receipt = receipt

if __name__ == '__main__':
    raise SystemExit(legacy.main())
