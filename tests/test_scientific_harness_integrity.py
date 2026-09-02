from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'r1_scientific_harness' / 'ascom00323-paper-source.tar.gz'
MANIFEST = ROOT / 'r1_scientific_harness' / 'source-manifest.json'
MANIFEST_CANONICAL_SHA256 = '600cdef851ea4834f1e25456f51c9a044c6ef97f95c66d4888e20397b54d5f61'


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
    ).encode('utf-8')


def _load() -> tuple[bytes, bytes, dict]:
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    manifest_identity = canonical_json_bytes(manifest)
    assert sha256(manifest_identity) == MANIFEST_CANONICAL_SHA256
    archive_bytes = ARCHIVE.read_bytes()
    assert sha256(archive_bytes) == manifest['archive_sha256']
    return archive_bytes, manifest_identity, manifest


def test_canonical_harness_archive_matches_manifest():
    archive_bytes, _, manifest = _load()
    expected = {entry['path']: entry for entry in manifest['files']}
    observed = {}
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as tf:
        for member in tf.getmembers():
            assert not member.issym() and not member.islnk()
            path = PurePosixPath(member.name)
            assert not path.is_absolute() and '..' not in path.parts
            if not member.isfile():
                continue
            prefix = PurePosixPath('r1_scientific_harness')
            rel = path.relative_to(prefix).as_posix()
            f = tf.extractfile(member)
            assert f is not None
            data = f.read()
            observed[rel] = {'size_bytes': len(data), 'sha256': sha256(data)}
    assert set(observed) == set(expected)
    for rel, entry in expected.items():
        assert observed[rel]['size_bytes'] == entry['size_bytes']
        assert observed[rel]['sha256'] == entry['sha256']


def test_manifest_identity_is_line_ending_independent():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    lf = json.dumps(manifest, indent=2, sort_keys=False, ensure_ascii=False) + '\n'
    crlf = lf.replace('\n', '\r\n')
    assert sha256(lf.encode('utf-8')) != sha256(crlf.encode('utf-8'))
    assert sha256(canonical_json_bytes(json.loads(lf))) == MANIFEST_CANONICAL_SHA256
    assert sha256(canonical_json_bytes(json.loads(crlf))) == MANIFEST_CANONICAL_SHA256


def test_one_byte_corruption_changes_archive_identity():
    archive_bytes, _, manifest = _load()
    corrupted = bytearray(archive_bytes)
    corrupted[len(corrupted) // 2] ^= 0x01
    assert sha256(corrupted) != manifest['archive_sha256']
