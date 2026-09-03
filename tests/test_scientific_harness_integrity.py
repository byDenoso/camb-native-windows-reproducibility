from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = ROOT / 'r1_scientific_harness' / 'source-manifest.json'
PARTS_MANIFEST = ROOT / 'r1_scientific_harness' / 'archive-parts-v3.json'
PARTS_DIR = ROOT / 'r1_scientific_harness' / 'archive_parts_v3'
SOURCE_MANIFEST_CANONICAL_SHA256 = '600cdef851ea4834f1e25456f51c9a044c6ef97f95c66d4888e20397b54d5f61'
PARTS_MANIFEST_CANONICAL_SHA256 = 'ca99188fa37014bc9b9b3d7f936ffa19f219cca6aaa04f9acb9f25c1d0936b1a'
ARCHIVE_SHA256 = '5add06fbc244116fbdf4415457a8609f061039853dfea3f571826e939b18ebd2'


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def _load_json(path: Path, expected_sha: str) -> dict:
    value = json.loads(path.read_text(encoding='utf-8'))
    assert sha256(canonical_json_bytes(value)) == expected_sha
    return value


def _load() -> tuple[bytes, dict, dict]:
    source = _load_json(SOURCE_MANIFEST, SOURCE_MANIFEST_CANONICAL_SHA256)
    transport = _load_json(PARTS_MANIFEST, PARTS_MANIFEST_CANONICAL_SHA256)
    assert transport['part_count'] == len(transport['parts']) == 17
    chunks = []
    for entry in transport['parts']:
        encoded = ''.join((PARTS_DIR / entry['name']).read_text(encoding='ascii').split())
        assert len(encoded) == entry['encoded_chars']
        assert sha256(encoded.encode('ascii')) == entry['encoded_sha256']
        raw = base64.b64decode(encoded, validate=True)
        assert len(raw) == entry['raw_bytes']
        assert sha256(raw) == entry['raw_sha256']
        chunks.append(raw)
    archive = b''.join(chunks)
    assert len(archive) == transport['archive_size_bytes'] == 99336
    assert sha256(archive) == transport['archive_sha256'] == source['archive_sha256'] == ARCHIVE_SHA256
    return archive, source, transport


def test_canonical_harness_archive_matches_manifest():
    archive, source, _ = _load()
    expected = {entry['path']: entry for entry in source['files']}
    observed = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tf:
        for member in tf.getmembers():
            assert not member.issym() and not member.islnk()
            path = PurePosixPath(member.name)
            assert not path.is_absolute() and '..' not in path.parts
            if not member.isfile():
                continue
            rel = path.relative_to(PurePosixPath('r1_scientific_harness')).as_posix()
            f = tf.extractfile(member); assert f is not None
            data = f.read()
            observed[rel] = {'size_bytes': len(data), 'sha256': sha256(data)}
    assert set(observed) == set(expected)
    for rel, entry in expected.items():
        assert observed[rel]['size_bytes'] == entry['size_bytes']
        assert observed[rel]['sha256'] == entry['sha256']


def test_manifest_identity_is_line_ending_independent():
    source = json.loads(SOURCE_MANIFEST.read_text(encoding='utf-8'))
    lf = json.dumps(source, indent=2, ensure_ascii=False) + '\n'
    crlf = lf.replace('\n', '\r\n')
    assert sha256(lf.encode()) != sha256(crlf.encode())
    assert sha256(canonical_json_bytes(json.loads(lf))) == SOURCE_MANIFEST_CANONICAL_SHA256
    assert sha256(canonical_json_bytes(json.loads(crlf))) == SOURCE_MANIFEST_CANONICAL_SHA256


def test_one_byte_corruption_changes_archive_identity():
    archive, _, _ = _load()
    corrupted = bytearray(archive); corrupted[len(corrupted)//2] ^= 1
    assert sha256(corrupted) != ARCHIVE_SHA256


def test_segment_corruption_fails_before_archive_reconstruction():
    _, _, transport = _load()
    entry = transport['parts'][7]
    encoded = ''.join((PARTS_DIR / entry['name']).read_text(encoding='ascii').split())
    replacement = 'A' if encoded[100] != 'A' else 'B'
    corrupted = encoded[:100] + replacement + encoded[101:]
    assert sha256(corrupted.encode('ascii')) != entry['encoded_sha256']
