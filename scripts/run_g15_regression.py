#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

import pantheon_cross_platform
import run_r1_scientific_closure as closure

# G15 runs the exact historical tests on native Windows, so generated Pantheon
# NPY/Cholesky bytes are platform-local diagnostics. Install the already-registered
# cross-platform gate before any runtime construction: source Git bytes remain exact
# identity and the generated factor must prove numerical equivalence at 1e-9.
pantheon_cross_platform.install()

MODULES = {
    "tests.test_optimized_runtime": 17,
    "tests.test_packaging_v6": 3,
    "tests.test_paper_validation_v6": 12,
    "tests.test_runtime_v3": 21,
    "tests.test_runtime_v4": 34,
}
EXPECTED_TOTAL = 87
SOURCE_ARCHIVE_SHA256 = "5add06fbc244116fbdf4415457a8609f061039853dfea3f571826e939b18ebd2"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def reconstruct_registered_source(repo: Path, work: Path) -> tuple[Path, dict]:
    fixture = repo / "r1_scientific_harness"
    parts_manifest_path = fixture / "archive-parts-v3.json"
    source_manifest_path = fixture / "source-manifest.json"
    parts_dir = fixture / "archive_parts_v3"

    parts_manifest = json.loads(parts_manifest_path.read_text(encoding="utf-8"))
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if parts_manifest.get("archive_sha256") != SOURCE_ARCHIVE_SHA256:
        raise RuntimeError("archive-parts-v3.json does not point to the registered paper source archive")
    if source_manifest.get("archive_sha256") != SOURCE_ARCHIVE_SHA256:
        raise RuntimeError("source-manifest.json does not point to the registered paper source archive")

    chunks: list[bytes] = []
    part_receipts = []
    for part in parts_manifest["parts"]:
        path = parts_dir / part["name"]
        encoded = "".join(path.read_text(encoding="ascii").split()).encode("ascii")
        if len(encoded) != int(part["encoded_chars"]):
            raise RuntimeError(f"encoded length mismatch for {part['name']}")
        if sha256_bytes(encoded) != part["encoded_sha256"]:
            raise RuntimeError(f"encoded SHA mismatch for {part['name']}")
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) != int(part["raw_bytes"]):
            raise RuntimeError(f"raw length mismatch for {part['name']}")
        if sha256_bytes(raw) != part["raw_sha256"]:
            raise RuntimeError(f"raw SHA mismatch for {part['name']}")
        chunks.append(raw)
        part_receipts.append({"name": part["name"], "raw_sha256": part["raw_sha256"], "raw_bytes": len(raw)})

    archive_bytes = b"".join(chunks)
    if len(archive_bytes) != int(parts_manifest["archive_size_bytes"]):
        raise RuntimeError("registered source archive byte count mismatch")
    if sha256_bytes(archive_bytes) != SOURCE_ARCHIVE_SHA256:
        raise RuntimeError("registered source archive SHA mismatch after reconstruction")

    archive_path = work / "ascom00323-paper-source.tar.gz"
    archive_path.write_bytes(archive_bytes)
    extract_root = work / "paper-source"
    extract_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as tf:
        tf.extractall(extract_root, filter="data")

    anchors = sorted(extract_root.rglob("tests/test_optimized_runtime.py"))
    if len(anchors) != 1:
        raise RuntimeError(f"cannot identify unique registered paper source root: {anchors}")
    source_root = anchors[0].parent.parent

    checked_files = 0
    for item in source_manifest["files"]:
        path = source_root / item["path"]
        if not path.is_file():
            raise RuntimeError(f"registered source file missing after reconstruction: {item['path']}")
        if path.stat().st_size != int(item["size_bytes"]):
            raise RuntimeError(f"registered source size mismatch: {item['path']}")
        if sha256_file(path) != item["sha256"]:
            raise RuntimeError(f"registered source SHA mismatch: {item['path']}")
        checked_files += 1

    provenance = {
        "archive": source_manifest.get("archive", "ascom00323-paper-source.tar.gz"),
        "archive_sha256": SOURCE_ARCHIVE_SHA256,
        "archive_size_bytes": len(archive_bytes),
        "part_count": len(part_receipts),
        "source_manifest_files_verified": checked_files,
        "base_runtime_sha256": source_manifest.get("base_runtime_sha256"),
        "paper_overlay_sha256": source_manifest.get("paper_overlay_sha256"),
    }
    return source_root, provenance


def locate_test_file(source_root: Path, module: str) -> Path:
    filename = module.rsplit(".", 1)[-1] + ".py"
    matches = sorted(p for p in source_root.rglob(filename) if p.is_file())
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one frozen G15 test file {filename}, found {len(matches)}: {matches}")
    return matches[0]


def require_gnu_tar(env: dict[str, str]) -> dict[str, str]:
    candidates: list[Path] = []
    if os.name == "nt":
        candidates.extend(
            [
                Path("C:/Program Files/Git/usr/bin/tar.exe"),
                Path("C:/Program Files (x86)/Git/usr/bin/tar.exe"),
            ]
        )
    discovered = shutil.which("tar", path=env.get("PATH"))
    if discovered:
        candidates.append(Path(discovered))
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen or not candidate.is_file():
            continue
        seen.add(key)
        probe = subprocess.run(
            [str(candidate), "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            errors="replace",
        )
        first_line = probe.stdout.splitlines()[0] if probe.stdout else ""
        if probe.returncode == 0 and "GNU tar" in probe.stdout:
            env["PATH"] = str(candidate.parent) + os.pathsep + env.get("PATH", "")
            return {"path": str(candidate), "version": first_line}
    raise RuntimeError("GNU tar is required for the frozen packaging_v6 tests; BSD tar is not accepted")


def install_child_fcntl_compat(repo: Path, work: Path, env: dict[str, str]) -> Path:
    compat = work / "windows-python-compat"
    compat.mkdir(parents=True, exist_ok=True)
    sitecustomize = compat / "sitecustomize.py"
    sitecustomize.write_text(
        "from windows_fcntl_compat import install_fcntl_compat\n"
        "install_fcntl_compat()\n",
        encoding="utf-8",
    )
    env["PYTHONPATH"] = os.pathsep.join(
        [str(compat), str(repo / "scripts"), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    return sitecustomize


def build_public_runtime(repo: Path, work: Path) -> tuple[Path, dict]:
    public_data = work / "public-data"
    public_data.mkdir(parents=True, exist_ok=True)
    bao, pan = closure.clone_data(public_data)
    runtime, pantheon = closure.build_runtime(work / "public-runtime", bao, pan)
    return runtime, {
        "construction": "public Cobaya BAO + frozen PantheonPlusSH0ES source through registered R1 compiler with cross-platform scientific equivalence gate",
        "bao_commit": closure.BAO_COMMIT,
        "pantheon_commit": closure.PANTHEON_COMMIT,
        "pantheon": pantheon,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--receipt", type=Path, required=True)
    args = ap.parse_args()

    repo = args.repo.resolve()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    harness = closure.decode_harness(repo, work)
    source_root, source_provenance = reconstruct_registered_source(repo, work)
    runtime_root, runtime_provenance = build_public_runtime(repo, work)

    env = os.environ.copy()
    env["PEER_LIKELIHOOD_RUNTIME_ROOT"] = str(runtime_root)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(source_root), str(harness), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    sitecustomize = install_child_fcntl_compat(repo, work, env)
    gnu_tar = require_gnu_tar(env)
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = "1"

    records = []
    total = 0
    all_pass = True
    for module, expected_count in MODULES.items():
        test_file = locate_test_file(source_root, module)
        test_dir = test_file.parent
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                str(test_dir),
                "-p",
                test_file.name,
                "-v",
            ],
            cwd=source_root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            errors="replace",
        )
        match = re.search(r"Ran\s+(\d+)\s+tests?", proc.stdout)
        observed_count = int(match.group(1)) if match else None
        passed = proc.returncode == 0 and observed_count == expected_count
        all_pass = all_pass and passed
        if observed_count is not None:
            total += observed_count
        records.append({
            "module": module,
            "test_file": str(test_file.relative_to(source_root)).replace("\\", "/"),
            "expected_tests": expected_count,
            "observed_tests": observed_count,
            "returncode": proc.returncode,
            "status": "pass" if passed else "fail",
            "output_tail": proc.stdout[-6000:],
        })

    verified = all_pass and total == EXPECTED_TOTAL
    payload = {
        "gate_id": "G15",
        "schema": "ascom-00323-g15-regression/v4",
        "status": "verified" if verified else "failed",
        "observed": {
            "workflow": "isolated Python process per exact registered historical test file reconstructed from the content-addressed paper source archive",
            "modules": records,
            "expected_total": EXPECTED_TOTAL,
            "observed_total": total,
            "harness_archive_sha256": closure.HARNESS_TAR_SHA,
            "paper_source": source_provenance,
            "runtime_root": str(runtime_root),
            "runtime_provenance": runtime_provenance,
            "windows_portability": {
                "sitecustomize": str(sitecustomize),
                "fcntl_compat": "scripts/windows_fcntl_compat.py",
                "gnu_tar": gnu_tar,
                "pantheon_generated_payload_identity": "platform-local diagnostic; frozen Git source bytes + numerical equivalence are authoritative",
            },
        },
        "claim_boundary": "Fresh native-Windows replay of the paper's exact registered 87-test source regression suite. Test identities and counts are frozen; no substitute tests are accepted.",
    }
    write_json(args.receipt, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if verified else 2


if __name__ == "__main__":
    raise SystemExit(main())
