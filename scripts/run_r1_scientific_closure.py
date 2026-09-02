#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time

import numpy as np
import pandas as pd
from scipy.linalg import cho_factor

PANTHEON_COMMIT = "c447f0fea703fcd0fff57de5000947b5ca81286b"
BAO_COMMIT = "b7b8a36e9bccb063081f811f323cada21ab5fbdd"
PANTHEON_TABLE_SHA = "1cb0fc379ef066afdc2ffd1857681cc478024570d8a3eba284fb645775198cf8"
PANTHEON_COV_SHA = "abf806d966485e64afdb359c87bffc0ecc00d05eff0a31ced66f247385df0fdc"
HARNESS_TAR_SHA = "9a40807f4f42fe49a998544510dc15a8abce7dcad242021fefe5e095e008d46c"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(*args: str, cwd: Path | None = None) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def decode_harness(repo: Path, work: Path) -> Path:
    archive = work / "harness.tar.gz"
    archive.write_bytes(base64.b64decode((repo / "r1_scientific_harness/harness.tar.gz.b64").read_text().strip()))
    observed = sha256(archive)
    if observed != HARNESS_TAR_SHA:
        raise RuntimeError(f"harness archive hash mismatch: {observed}")
    with tarfile.open(archive, "r:gz") as tf:
        tf.extractall(work)
    root = work / "r1_scientific_harness"
    benchmark = gzip.decompress(base64.b64decode((repo / "r1_scientific_harness/benchmark_v5.py.gz.b64").read_text().strip()))
    (root / "peer_platform/benchmark_v5.py").write_bytes(benchmark)
    return root


def clone_data(work: Path) -> tuple[Path, Path]:
    bao = work / "bao_data"
    run("git", "-c", "core.autocrlf=false", "clone", "--filter=blob:none", "https://github.com/CobayaSampler/bao_data.git", str(bao))
    run("git", "checkout", "--detach", BAO_COMMIT, cwd=bao)

    pan = work / "pantheon-release"
    run("git", "-c", "core.autocrlf=false", "clone", "--filter=blob:none", "--no-checkout", "https://github.com/PantheonPlusSH0ES/DataRelease.git", str(pan))
    run("git", "sparse-checkout", "init", "--cone", cwd=pan)
    run("git", "sparse-checkout", "set", "Pantheon+_Data/4_DISTANCES_AND_COVAR", cwd=pan)
    run("git", "checkout", "--detach", PANTHEON_COMMIT, cwd=pan)
    return bao, pan


def compile_pantheon(runtime: Path, pan_repo: Path) -> dict:
    src = pan_repo / "Pantheon+_Data/4_DISTANCES_AND_COVAR"
    table_src = src / "Pantheon+SH0ES.dat"
    cov_src = src / "Pantheon+SH0ES_STAT+SYS.cov"
    if sha256(table_src) != PANTHEON_TABLE_SHA:
        raise RuntimeError("Pantheon table hash mismatch")
    if sha256(cov_src) != PANTHEON_COV_SHA:
        raise RuntimeError("Pantheon covariance hash mismatch")

    raw = runtime / "data/sn_data/PantheonPlus"
    raw.mkdir(parents=True, exist_ok=True)
    table_path = raw / table_src.name
    cov_path = raw / cov_src.name
    shutil.copy2(table_src, table_path)
    shutil.copy2(cov_src, cov_path)

    table = pd.read_csv(table_path, sep=r"\s+")
    flat = np.loadtxt(cov_path)
    n = len(table)
    if int(flat[0]) != n or flat[1:].size != n * n:
        raise RuntimeError("Pantheon covariance shape mismatch")
    cov = flat[1:].reshape(n, n)
    asym = float(np.max(np.abs(cov - cov.T)))
    if asym > 5e-8:
        raise RuntimeError(f"Pantheon text asymmetry exceeds contract: {asym}")
    cov = np.tril(cov) + np.tril(cov, -1).T

    compiled = raw / "compiled_v2"
    if compiled.exists():
        shutil.rmtree(compiled)
    compiled.mkdir(parents=True)
    manifest = {
        "schema": "peer-pantheon-compiled/v2",
        "source": {"table_sha256": sha256(table_path), "covariance_sha256": sha256(cov_path), "rows": n, "max_text_asymmetry": asym},
        "selections": {},
    }
    selections = {
        "hubble_flow": table["zHD"].to_numpy(float) > 0.01,
        "shoes": (table["zHD"].to_numpy(float) > 0.01) | (table["IS_CALIBRATOR"].to_numpy(int) == 1),
    }
    for key, mask in selections.items():
        idx = np.flatnonzero(mask)
        selected_cov = cov[np.ix_(idx, idx)]
        factor, _ = cho_factor(selected_cov, lower=True, check_finite=False, overwrite_a=False)
        factor = np.tril(factor)
        arrays = {
            "magnitude": table.loc[mask, "m_b_corr"].to_numpy(float),
            "zcmb": table.loc[mask, "zHD"].to_numpy(float),
            "zhel": table.loc[mask, "zHEL"].to_numpy(float),
            "is_calibrator": table.loc[mask, "IS_CALIBRATOR"].to_numpy(np.uint8),
            "ceph_dist": table.loc[mask, "CEPH_DIST"].to_numpy(float),
            "cholesky": factor,
        }
        directory = compiled / key
        directory.mkdir()
        files = {}
        for name, array in arrays.items():
            path = directory / f"{name}.npy"
            np.save(path, array, allow_pickle=False)
            files[name] = {"path": f"{key}/{path.name}", "sha256": sha256(path), "shape": list(array.shape), "dtype": str(array.dtype)}
        manifest["selections"][key] = {"n": int(idx.size), "calibrators": int(arrays["is_calibrator"].sum()), "files": files}
    write_json(compiled / "manifest.json", manifest)
    expected_compiled_manifest = "01f86af61eb59ef3125b7a8f1acfb5a01eeddee8335e1f919f570ada4731adb5"
    observed_manifest = sha256(compiled / "manifest.json")
    if observed_manifest != expected_compiled_manifest:
        raise RuntimeError(f"compiled Pantheon manifest mismatch: {observed_manifest}")

    (runtime / "manifests").mkdir(parents=True, exist_ok=True)
    write_json(runtime / "manifests/PANTHEON_PLUS.json", {
        "schema": "peer-likelihood-runtime/v1",
        "likelihood": "pantheon_plus",
        "status": "functional_optimized",
        "compiled_payload": {"path": "data/sn_data/PantheonPlus/compiled_v2", "manifest_sha256": observed_manifest},
        "claim_boundary": "likelihood equivalence and component performance only",
    })
    return {"table_sha256": sha256(table_path), "covariance_sha256": sha256(cov_path), "compiled_manifest_sha256": observed_manifest, "hubble_flow_rows": int(manifest["selections"]["hubble_flow"]["n"])}


def build_runtime(work: Path, bao: Path, pan: Path) -> tuple[Path, dict]:
    runtime = work / "runtime"
    (runtime / "data").mkdir(parents=True, exist_ok=True)
    shutil.copytree(bao, runtime / "data/bao_data", ignore=shutil.ignore_patterns(".git"))
    pantheon = compile_pantheon(runtime, pan)
    return runtime, pantheon


def balanced_cobaya(campaign, *, seed: int = 17) -> dict:
    from peer_platform.benchmark_v5 import _UncachedCobayaAdapterV5
    from peer_platform.cobaya_campaign_v5 import TieredCobayaAdapterV5, run_bounded_cobaya_smoke
    from peer_platform.paper_validation_v6 import latin_hypercube_points, _baseline_logp

    def make(kind: str):
        if kind == "baseline":
            return _UncachedCobayaAdapterV5(campaign, quadrature_order=64)
        return TieredCobayaAdapterV5(campaign, quadrature_order=64, shape_cache_capacity=64, scale_cache_capacity=128)

    for kind in ("baseline", "optimized"):
        run_bounded_cobaya_smoke(make(kind), accepted_samples=4, seed=seed, output_root=None)

    order = ["baseline", "optimized", "optimized", "baseline", "baseline", "optimized", "optimized", "baseline", "baseline", "optimized"]
    records = {"baseline": [], "optimized": []}
    for kind in order:
        adapter = make(kind)
        result = run_bounded_cobaya_smoke(adapter, accepted_samples=4, seed=seed, output_root=None)
        records[kind].append({"wall_seconds": float(result["wall_seconds"]), "adapter_metrics": result["adapter_metrics"]})

    baseline = [x["wall_seconds"] for x in records["baseline"]]
    optimized = [x["wall_seconds"] for x in records["optimized"]]
    bmed = float(statistics.median(baseline)); omed = float(statistics.median(optimized))
    bmetrics = records["baseline"][0]["adapter_metrics"]; ometrics = records["optimized"][0]["adapter_metrics"]

    points = latin_hypercube_points(120, seed=seed)
    from peer_platform.cobaya_campaign_v5 import TieredCobayaAdapterV5
    opt = TieredCobayaAdapterV5(campaign, quadrature_order=64, shape_cache_capacity=128, scale_cache_capacity=128)
    max_delta = 0.0
    for point in points:
        base = _baseline_logp(campaign, point, quadrature_order=64)
        fast = float(opt.logp(**point))
        max_delta = max(max_delta, abs(base-fast))

    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(5000):
        bs = rng.choice(baseline, size=len(baseline), replace=True)
        os_ = rng.choice(optimized, size=len(optimized), replace=True)
        boots.append(float(np.median(bs) / np.median(os_)))
    lo, mid, hi = np.quantile(boots, [0.025, 0.5, 0.975])
    speed = bmed / omed
    status = "pass" if speed > 1.0 and max_delta <= 1e-9 and bmetrics["shape_computations"] > ometrics["shape_computations"] else "fail"
    return {
        "schema": "ascom-00323-r1-balanced-cobaya/v1",
        "status": status,
        "seed": seed,
        "accepted_samples_per_run": 4,
        "warmup_runs_per_mode": 1,
        "timed_runs_per_mode": 5,
        "order": order,
        "results": {
            "baseline_wall_seconds": baseline,
            "optimized_wall_seconds": optimized,
            "baseline_median_seconds": bmed,
            "optimized_median_seconds": omed,
            "measured_wall_speedup": speed,
            "bootstrap_speedup_median": float(mid),
            "bootstrap_speedup_95_interval": [float(lo), float(hi)],
            "equivalence_points": 120,
            "max_abs_log_likelihood_delta": max_delta,
            "shape_computations": {"baseline": bmetrics["shape_computations"], "optimized": ometrics["shape_computations"]},
            "scale_preparations": {"baseline": bmetrics["scale_preparations"], "optimized": ometrics["scale_preparations"]},
        },
        "claim_boundary": "warmed order-balanced bounded Cobaya plumbing benchmark; no convergence or posterior claim",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--receipts", type=Path, required=True)
    args = ap.parse_args()
    repo = args.repo.resolve(); work = args.work.resolve(); receipts = args.receipts.resolve()
    work.mkdir(parents=True, exist_ok=True); receipts.mkdir(parents=True, exist_ok=True)

    harness = decode_harness(repo, work)
    sys.path.insert(0, str(harness))
    bao, pan = clone_data(work)
    runtime, pantheon_receipt = build_runtime(work, bao, pan)
    write_json(receipts / "G04d-pantheon-plus-public.json", {"schema": "ascom-00323-pantheon-plus-public/v1", "status": "verified", "commit": PANTHEON_COMMIT, **pantheon_receipt})

    from peer_platform.late_time_campaign_v5 import LateTimeCampaignV5
    from peer_platform.paper_validation_v6 import equivalence_grid, multi_start_minimizer_equivalence, profile_equivalence, scaling_benchmark, memory_stability, run_failure_injection

    cfg = json.loads((harness / "paper_validation_v6.json").read_text())
    campaign = LateTimeCampaignV5.load(runtime)
    identity = {"desi_points": int(campaign.desi.values.size), "boss_eboss_datasets": len(campaign.boss_eboss.names), "pantheon_objects": int(campaign.pantheon.n), "python": sys.version, "platform": sys.platform}
    write_json(receipts / "late-time-runtime-identity.json", {"schema": "ascom-00323-late-time-runtime/v1", "status": "verified", **identity})

    stages = {}
    eq = cfg["equivalence_grid"]; stages["G09"] = equivalence_grid(campaign, points=eq["points"], seed=eq["seed"], quadrature_order=eq["quadrature_order"], tolerance=eq["tolerance"])
    mi = cfg["minimizer"]; stages["G10"] = multi_start_minimizer_equivalence(campaign, starts=mi["contexts"], seed=mi["seed"], quadrature_order=mi["quadrature_order"], maxiter=mi["maxiter"], tolerance=mi["tolerance"])
    pr = cfg["profile"]; stages["G11"] = profile_equivalence(campaign, omega_grid=pr["omega_grid"], quadrature_order=pr["quadrature_order"], tolerance=pr["tolerance"])
    sc = cfg["scaling"]; scaling = scaling_benchmark(campaign, batch_sizes=sc["batch_sizes"], repetitions=sc["repetitions"], quadrature_order=sc["quadrature_order"], tolerance=sc["tolerance"]); stages["G12_G13"] = scaling
    me = cfg["memory"]; stages["memory"] = memory_stability(campaign, evaluations=me["evaluations"], quadrature_order=me["quadrature_order"], maximum_growth_bytes=me["maximum_growth_bytes"])
    stages["failure"] = run_failure_injection(runtime)
    stages["G14"] = balanced_cobaya(campaign, seed=17)

    for gate, result in stages.items():
        write_json(receipts / f"{gate}.json", {"gate_id": gate, "status": "verified" if result.get("status") == "pass" else "failed", "observed": result, "source": "fresh Windows R1 scientific closure"})

    all_pass = all(v.get("status") == "pass" for v in stages.values())
    summary = {
        "schema": "ascom-00323-r1-scientific-closure/v1",
        "status": "verified" if all_pass else "failed",
        "gates": {k: v.get("status") for k, v in stages.items()},
        "key_metrics": {
            "G09_max_abs_logl_delta": stages["G09"].get("max_abs_log_likelihood_delta"),
            "G10_max_abs_objective_delta": stages["G10"].get("max_abs_objective_delta"),
            "G11_max_abs_profile_delta": stages["G11"].get("max_abs_delta_chi2_difference"),
            "G14_speedup": stages["G14"].get("results", {}).get("measured_wall_speedup"),
            "G14_max_abs_logl_delta": stages["G14"].get("results", {}).get("max_abs_log_likelihood_delta"),
        },
        "publication_boundary": "Closes late-time deterministic/software gates only; M0 and ACT/r_drag CAMB gates are separate receipts.",
    }
    write_json(receipts / "scientific-closure-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if all_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
