from __future__ import annotations

import base64
from collections import Counter
import hashlib
from pathlib import Path
import re
import string

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_r1_scientific_closure.py"
ARCHIVE_B64 = ROOT / "r1_scientific_harness" / "harness.tar.gz.b64"
_BASE64_CHARS = set(string.ascii_letters + string.digits + "+/=")


def _declared_hash() -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    match = re.search(r'^HARNESS_TAR_SHA\s*=\s*"([0-9a-f]{64})"$', text, flags=re.MULTILINE)
    assert match, "run_r1_scientific_closure.py must declare HARNESS_TAR_SHA"
    return match.group(1)


def _archive_bytes() -> bytes:
    raw = ARCHIVE_B64.read_text(encoding="utf-8")
    invalid = Counter(ch for ch in raw if not ch.isspace() and ch not in _BASE64_CHARS)
    assert not invalid, f"versioned harness contains non-Base64 characters: {dict(invalid)}"
    encoded = "".join(raw.split())
    return base64.b64decode(encoded, validate=True)


def test_declared_harness_hash_matches_versioned_archive():
    observed = hashlib.sha256(_archive_bytes()).hexdigest()
    assert observed == _declared_hash()


def test_one_byte_corruption_changes_harness_identity():
    payload = bytearray(_archive_bytes())
    payload[len(payload) // 2] ^= 0x01
    assert hashlib.sha256(payload).hexdigest() != _declared_hash()
