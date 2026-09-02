#!/usr/bin/env python3
"""Verify the public DESI DR2 BAO data repository against the frozen paper manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

EXPECTED_COMMIT = "b7b8a36e9bccb063081f811f323cada21ab5fbdd"
EXPECTED_FILES = {
    "desi_bao_dr2/desi_gaussian_bao_ALL_GCcomb_cov.txt": "252a143274c8a07c78694c119617d36594f6d7965d00319ca611c6ffb886e509",
    "desi_bao_dr2/desi_gaussian_bao_ALL_GCcomb_mean.txt": "9ac154ab583ce759c0f7eef3c978c7c70a6ead2d18774caceadf1a350a640585",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", type=Path)
    ap.add_argument("--receipt", type=Path)
    args = ap.parse_args()
    root = args.repo.resolve()
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    rows = {}
    ok = head == EXPECTED_COMMIT
    for rel, expected in EXPECTED_FILES.items():
        path = root / rel
        observed = sha256_file(path) if path.is_file() else None
        match = observed == expected
        ok = ok and match
        rows[rel] = {"sha256": observed, "expected_sha256": expected, "match": match}
    report = {
        "schema": "ascom-00323-desi-dr2-public-identity/v1",
        "repository": "https://github.com/CobayaSampler/bao_data.git",
        "commit": head,
        "expected_commit": EXPECTED_COMMIT,
        "commit_match": head == EXPECTED_COMMIT,
        "files": rows,
        "status": "verified" if ok else "failed",
    }
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(text, end="")
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(text, encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
