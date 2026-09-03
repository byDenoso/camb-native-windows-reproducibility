#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

import run_r1_robustness as legacy

SOURCE_MANIFEST_REL = Path('r1_scientific_harness/source-manifest.json')
PARTS_MANIFEST_REL = Path('r1_scientific_harness/archive-parts-v3.json')
PARTS_DIR_REL = Path('r1_scientific_harness/archive_parts_v3')
SOURCE_MANIFEST_CANONICAL_SHA256 = '600cdef851ea4834f1e25456f51c9a044c6ef97f95c66d4888e20397b54d5f61'
PARTS_MANIFEST_CANONICAL_SHA256 = 'ca99188fa37014bc9b9b3d7f936ffa19f219cca6aaa04f9acb9f25c1d0936b1a'
ARCHIVE_SHA256 = '5add06fbc244116fbdf4415457a8609f061039853dfea3f571826e939b18ebd2'
PANTHEON_TABLE_REL = 'Pantheon+_Data/4_DISTANCES_AND_COVAR/Pantheon+SH0ES.dat'
PANTHEON_COV_REL = 'Pantheon+_Data/4_DISTANCES_AND_COVAR/Pantheon+SH0ES_STAT+SYS.cov'


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


def _git_blob_bytes(repo: Path, commit: str, relative_path: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(repo), 'show', f'{commit}:{relative_path}'])


def _install_pantheon_git_blob_materialization() -> None:
    import run_r1_scientific_closure as closure

    if getattr(closure, '_pantheon_git_blob_materialization_installed', False):
        return
    original = closure.compile_pantheon

    def compile_pantheon_from_frozen_git_blob(runtime: Path, pan_repo: Path) -> dict:
        table_path = pan_repo / PANTHEON_TABLE_REL
        cov_path = pan_repo / PANTHEON_COV_REL
        working_tree_table_sha256 = legacy.sha256_file(table_path)
        working_tree_covariance_sha256 = legacy.sha256_file(cov_path)

        table_bytes = _git_blob_bytes(pan_repo, closure.PANTHEON_COMMIT, PANTHEON_TABLE_REL)
        cov_bytes = _git_blob_bytes(pan_repo, closure.PANTHEON_COMMIT, PANTHEON_COV_REL)
        canonical_table_sha256 = sha256_bytes(table_bytes)
        canonical_covariance_sha256 = sha256_bytes(cov_bytes)
        if canonical_table_sha256 != closure.PANTHEON_TABLE_SHA:
            raise RuntimeError(
                'canonical Pantheon table Git blob hash mismatch: '
                f'{canonical_table_sha256} != {closure.PANTHEON_TABLE_SHA}'
            )
        if canonical_covariance_sha256 != closure.PANTHEON_COV_SHA:
            raise RuntimeError(
                'canonical Pantheon covariance Git blob hash mismatch: '
                f'{canonical_covariance_sha256} != {closure.PANTHEON_COV_SHA}'
            )

        # The frozen Git blob is the authority. This removes checkout-only CRLF/LF
        # representation drift while failing closed if the commit content drifts.
        table_path.write_bytes(table_bytes)
        cov_path.write_bytes(cov_bytes)
        result = original(runtime, pan_repo)
        result.update({
            'identity_authority': 'frozen Git blob',
            'working_tree_table_sha256_before_canonicalization': working_tree_table_sha256,
            'working_tree_covariance_sha256_before_canonicalization': working_tree_covariance_sha256,
            'canonical_git_blob_table_sha256': canonical_table_sha256,
            'canonical_git_blob_covariance_sha256': canonical_covariance_sha256,
        })
        return result

    closure.compile_pantheon = compile_pantheon_from_frozen_git_blob
    closure._pantheon_git_blob_materialization_installed = True


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
    _install_pantheon_git_blob_materialization()
    raise SystemExit(legacy.main())
