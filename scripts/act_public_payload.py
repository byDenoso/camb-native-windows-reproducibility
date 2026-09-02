#!/usr/bin/env python3
"""Reconstruct the paper's deterministic ACT DR6 CMB-only payload from public SACC data.

This script intentionally depends only on the public ACT DR6 SACC FITS file and sacc/numpy.
It writes the frozen ACTSACCv1 binary contract used by the paper and reports both the
source FITS SHA-256 and the reconstructed payload SHA-256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np

EXPECTED_FITS_SHA256 = "c887dc9178d81f5e5e0ce76eca0cd3c9f089056630ab78a1cc4bb28ff8751c29"
EXPECTED_PAYLOAD_SHA256 = "d3ca3ff9427ecb22141df32fb6b4398d3f9a3dcb1a10d22344b33c56a12b6484"
MAGIC = b"ACTSACCv1" + b"\0" * 7
POLS = ("TT", "TE", "EE")
ELL_MIN = 2
ELL_MAX = 8501
NBIN = 45
NDATA = 135


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def reconstruct(fits_path: Path, output: Path) -> dict:
    import sacc

    source_hash = sha256_file(fits_path)
    s = sacc.Sacc.load_fits(str(fits_path))
    pol_dt = {"t": "0", "e": "e", "b": "b"}

    ells = np.arange(ELL_MIN, ELL_MAX + 1, dtype="<i8")
    weights = np.zeros((3, len(ells), NBIN), dtype="<f8")
    data = np.zeros(NDATA, dtype="<f8")
    centers = np.zeros(NDATA, dtype="<f8")
    seen: list[int] = []
    culls: list[np.ndarray] = []

    for pidx, pol in enumerate(POLS):
        p1, p2 = pol.lower()
        dt = f"cl_{pol_dt[p1]}{pol_dt[p2]}"
        rows: list[tuple[int, float, float, np.ndarray, np.ndarray]] = []
        for tr1, tr2 in s.get_tracer_combinations(dt):
            ls, mu, ind = s.get_ell_cl(dt, tr1, tr2, return_ind=True)
            mask = np.logical_and(ls >= 600, ls <= 6500)
            if not np.all(mask):
                culls.append(np.asarray(ind[~mask], dtype=int))
            if not np.any(mask):
                continue
            selected_ind = np.asarray(ind[mask], dtype=int)
            selected_ls = np.asarray(ls[mask], dtype=float)
            selected_mu = np.asarray(mu[mask], dtype=float)
            window = s.get_bandpower_windows(selected_ind)
            w_values = np.asarray(window.values, dtype=int)
            w = np.asarray(window.weight, dtype=float)
            if w.ndim != 2:
                raise RuntimeError(f"unexpected ACT window rank {w.ndim}")
            if w.shape[0] != w_values.size and w.shape[1] == w_values.size:
                w = w.T
            if w.shape[0] != w_values.size or w.shape[1] != selected_ind.size:
                raise RuntimeError(
                    f"unexpected ACT window shape {w.shape}; values={w_values.size}, bins={selected_ind.size}"
                )
            for j, global_idx in enumerate(selected_ind):
                rows.append((int(global_idx), float(selected_ls[j]), float(selected_mu[j]), w_values, w[:, j]))

        rows.sort(key=lambda x: x[0])
        if len(rows) != NBIN:
            raise RuntimeError(f"{pol}: expected {NBIN} selected bandpowers, found {len(rows)}")
        for local_bin, (global_idx, center, datum, w_values, w_col) in enumerate(rows):
            if global_idx < 0 or global_idx >= NDATA:
                raise RuntimeError(f"{pol}: global index {global_idx} outside 0..{NDATA-1}")
            offsets = w_values - ELL_MIN
            if np.any(offsets < 0) or np.any(offsets >= len(ells)):
                raise RuntimeError(f"{pol}: window support outside ell={ELL_MIN}..{ELL_MAX}")
            weights[pidx, offsets, local_bin] = w_col
            data[global_idx] = datum
            centers[global_idx] = center
            seen.append(global_idx)

    if sorted(seen) != list(range(NDATA)):
        raise RuntimeError("ACT selected indices are not exactly 0..134")

    covariance = np.asarray(s.covariance.covmat, dtype="<f8").copy()
    if covariance.shape != (NDATA, NDATA):
        raise RuntimeError(f"expected ACT covariance {(NDATA, NDATA)}, got {covariance.shape}")
    for idx in culls:
        covariance[idx, :] = 0.0
        covariance[:, idx] = 0.0
        covariance[idx, idx] = 1e10

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as f:
        f.write(MAGIC)
        f.write(struct.pack("<4i", 3, NBIN, len(ells), NDATA))
        f.write(ells.tobytes(order="C"))
        f.write(weights.tobytes(order="C"))
        f.write(data.tobytes(order="C"))
        f.write(centers.tobytes(order="C"))
        f.write(covariance.tobytes(order="C"))

    payload_hash = sha256_file(output)
    report = {
        "schema": "ascom-00323-act-public-reconstruction/v1",
        "source_fits": str(fits_path),
        "source_fits_sha256": source_hash,
        "expected_source_fits_sha256": EXPECTED_FITS_SHA256,
        "source_fits_match": source_hash == EXPECTED_FITS_SHA256,
        "payload": str(output),
        "payload_bytes": output.stat().st_size,
        "payload_sha256": payload_hash,
        "expected_payload_sha256": EXPECTED_PAYLOAD_SHA256,
        "payload_match": payload_hash == EXPECTED_PAYLOAD_SHA256,
        "dimensions": {"npol": 3, "nbin": NBIN, "nell": len(ells), "ndata": NDATA},
        "centers_min": float(np.min(centers)),
        "centers_max": float(np.max(centers)),
        "cull_count": int(sum(len(x) for x in culls)),
    }
    report["status"] = "verified" if report["source_fits_match"] and report["payload_match"] else "failed"
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("fits", type=Path)
    ap.add_argument("--output", type=Path, default=Path("results/generated/act_dr6_cmbonly.bin"))
    ap.add_argument("--receipt", type=Path)
    args = ap.parse_args()
    report = reconstruct(args.fits, args.output)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(text, end="")
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(text, encoding="utf-8")
    return 0 if report["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
