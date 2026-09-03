#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import run_r1_scientific_closure as closure

MODULES = {
    "tests.test_optimized_runtime": 17,
    "tests.test_packaging_v6": 3,
    "tests.test_paper_validation_v6": 12,
    "tests.test_runtime_v3": 21,
    "tests.test_runtime_v4": 34,
}
EXPECTED_TOTAL = 87


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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

    env = os.environ.copy()
    env["PYTHONPATH"] = str(harness) + os.pathsep + env.get("PYTHONPATH", "")
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = "1"

    records = []
    total = 0
    all_pass = True
    for module, expected_count in MODULES.items():
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", module, "-v"],
            cwd=harness,
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
            "expected_tests": expected_count,
            "observed_tests": observed_count,
            "returncode": proc.returncode,
            "status": "pass" if passed else "fail",
            "output_tail": proc.stdout[-4000:],
        })

    verified = all_pass and total == EXPECTED_TOTAL
    payload = {
        "gate_id": "G15",
        "schema": "ascom-00323-g15-regression/v1",
        "status": "verified" if verified else "failed",
        "observed": {
            "workflow": "isolated Python process per test module",
            "modules": records,
            "expected_total": EXPECTED_TOTAL,
            "observed_total": total,
            "harness_archive_sha256": closure.HARNESS_TAR_SHA,
        },
        "claim_boundary": "Fresh replay of the paper's registered 87-test source regression suite from the frozen R1 harness.",
    }
    write_json(args.receipt, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if verified else 2


if __name__ == "__main__":
    raise SystemExit(main())
