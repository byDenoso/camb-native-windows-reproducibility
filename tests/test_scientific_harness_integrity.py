from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'r1_scientific_harness' / 'ascom00323-paper-source.tar.gz'
MANIFEST = ROOT / 'r1_scientific_harness' / 'source-manifest.json'
MANIFEST_SHA256 = '0e22e67bc23db9a36f2e45a14455fec40bdf590b2b1f4059f53615e76b6f17bd'


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load() -> tuple[bytes, bytes, dict]:
    manifest_bytes = MANIFEST.read_bytes()
    assert sha256(manifest_bytes) == MANIFEST_SHA256
    manifest = json.loads(manifest_bytes)
    archive_bytes = ARCHIVE.read_bytes()
    assert sha256(archive_bytes) == manifest['archive_sha256']
    return archive_bytes, manifest_bytes, manifest


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


def test_one_byte_corruption_changes_archive_identity():
    archive_bytes, _, manifest = _load()
    corrupted = bytearray(archive_bytes)
    corrupted[len(corrupted) // 2] ^= 0x01
    assert sha256(corrupted) != manifest['archive_sha256']
