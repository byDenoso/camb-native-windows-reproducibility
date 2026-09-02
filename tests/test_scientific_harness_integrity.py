from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import string

ROOT = Path(__file__).resolve().parents[1]
PARTS = ROOT / "r1_scientific_harness" / "canonical_parts"
EXPECTED_SHA256 = "f2cf596eee66cc59554a966e3cf04157f01b928b1dd5f62375670fadb52a84ec"
_BASE64_CHARS = set(string.ascii_letters + string.digits + "+/=")


def _archive_bytes() -> bytes:
    part_paths = sorted(PARTS.glob("part*.b64"))
    assert [p.name for p in part_paths] == [f"part{i:02d}.b64" for i in range(1, 5)]
    decoded_parts = []
    for path in part_paths:
        raw = path.read_text(encoding="ascii")
        invalid = {ch for ch in raw if not ch.isspace() and ch not in _BASE64_CHARS}
        assert not invalid, f"{path.name} contains non-Base64 characters: {sorted(invalid)!r}"
        encoded = "".join(raw.split())
        decoded_parts.append(base64.b64decode(encoded, validate=True))
    return b"".join(decoded_parts)


def test_canonical_harness_parts_match_frozen_archive_identity():
    observed = hashlib.sha256(_archive_bytes()).hexdigest()
    assert observed == EXPECTED_SHA256


def test_one_byte_corruption_changes_harness_identity():
    payload = bytearray(_archive_bytes())
    payload[len(payload) // 2] ^= 0x01
    assert hashlib.sha256(payload).hexdigest() != EXPECTED_SHA256
