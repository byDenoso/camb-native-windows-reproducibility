from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
import math
import os
from pathlib import Path
import traceback

import numpy as np
from scipy.optimize import minimize

from peer_017_contract import (
    TEST_ID,
    PREREG_DRIVE_ID,
    SPT_DATA_COMMIT,
    SPT_CANDL_VERSION,
    SPT_OFFICIAL_TEST_LOGL,
    classify_holdout,
)

TRAIN = Path(os.environ.get("PEER_017_TRAIN_IN", "results/peer-axion-acttrain-sptholdout-017/training"))
OUT = Path(os.environ.get("PEER_017_SPT_OUT", "results/peer-axion-acttrain-sptholdout-017/spt_holdout"))
OUT.mkdir(parents=True, exist_ok=True)
SPT_REPO = Path(os.environ.get("PEER_SPT_DATA_REPO", ".r1/spt_candl_data"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_like():
    import candl
    import spt_candl_data

    version = metadata.version("candl")
    if version != SPT_CANDL_VERSION:
        raise RuntimeError(f"candl version mismatch: {version}")
    like = candl.Like(spt_candl_data.SPT3G_D1_TnE_lite, feedback=False)
    return like, candl, spt_candl_data


def official_self_test(like, spt_candl_data) -> dict[str, object]:
    test_spec_path = Path(spt_candl_data.__file__).resolve().parent / "tests" / "SPT3G_D1_TnE_test_spec.txt"
    spec = np.loadtxt(test_spec_path)
    pars = {
        "Tcal": 1.001,
        "Ecal": 0.999,
        "tau": 0.054,
        "Dl": {
            "ell": spec[:, 0],
            "TT": spec[:, 1],
            "TE": spec[:, 2],
            "EE": spec[:, 3],
            "BB": spec[:, 4],
            "pp": spec[:, 5],
            "kk": spec[:, 6],
        },
    }
    observed = float(like.log_like(pars))
    error = abs(observed - SPT_OFFICIAL_TEST_LOGL)
    # Much tighter than candl's public 0.1% self-test threshold while retaining cross-runtime headroom.
    passed = bool(math.isfinite(observed) and error < 1.0e-4)
    return {
        "observed_logl": observed,
        "expected_logl": SPT_OFFICIAL_TEST_LOGL,
        "absolute_error": error,
        "pass": passed,
        "test_spectrum_sha256": sha256_file(test_spec_path),
    }


def endpoint_params(npz_path: Path, like, tcal: float, ecal: float) -> dict[str, object]:
    z = np.load(npz_path)
    n = int(like.N_ell_bins_theory)
    lo, hi = 2, 2 + n
    def arr(name: str) -> np.ndarray:
        x = np.asarray(z[name], dtype=float)
        if x.size < hi:
            raise RuntimeError(f"{npz_path.name}:{name} has {x.size}, need {hi}")
        return np.ascontiguousarray(x[lo:hi])
    return {
        "Tcal": float(tcal),
        "Ecal": float(ecal),
        "tau": 0.054,
        "Dl": {"TT": arr("tt"), "TE": arr("te"), "EE": arr("ee"), "BB": arr("bb")},
    }


def q_value(like, npz_path: Path, tcal: float, ecal: float) -> float:
    # candl Like.log_like is the (negative) log likelihood. Q=-2 logL.
    return float(-2.0 * float(like.log_like(endpoint_params(npz_path, like, tcal, ecal))))


def profile(like, npz_path: Path) -> dict[str, object]:
    starts = [(1.0, 1.0), (0.995, 1.01), (1.005, 0.99), (0.99, 1.02), (1.01, 0.98)]
    runs: list[dict[str, float]] = []
    for start in starts:
        def fun(x):
            t, e = map(float, x)
            # Broad numerical guard only. The physical optimum is expected near unity.
            if not (0.8 < t < 1.2 and 0.7 < e < 1.3):
                return 1.0e12 + 1.0e8 * ((t - 1.0) ** 2 + (e - 1.0) ** 2)
            return q_value(like, npz_path, t, e)
        result = minimize(fun, np.asarray(start, dtype=float), method="Nelder-Mead", options={"xatol": 1e-10, "fatol": 1e-10, "maxiter": 3000})
        if not result.success:
            result = minimize(fun, np.asarray(start, dtype=float), method="Powell", options={"xtol": 1e-10, "ftol": 1e-10, "maxiter": 3000})
        t, e = map(float, result.x)
        runs.append({"q": float(fun((t, e))), "Tcal": t, "Ecal": e, "success": bool(result.success)})
    best = min(runs, key=lambda r: r["q"])
    spread = max(r["q"] for r in runs) - min(r["q"] for r in runs)
    return {"best": best, "runs": runs, "objective_spread": float(spread), "robust": bool(spread < 1e-6)}


def main() -> None:
    winner_path = TRAIN / "winner_receipt.json"
    if not winner_path.exists():
        raise RuntimeError("winner receipt missing")
    winner = json.loads(winner_path.read_text(encoding="utf-8"))
    if winner.get("SPT_NOT_EVALUATED_WHEN_WRITTEN") is not True or winner.get("holdout_opened") is not False:
        raise RuntimeError("winner receipt does not prove pre-holdout freeze")

    active_path = TRAIN / "winner_active_Dl_uK2.npz"
    r1_path = TRAIN / "winner_r1_Dl_uK2.npz"
    for path in (active_path, r1_path):
        if not path.exists():
            raise RuntimeError(f"missing frozen winner endpoint {path}")

    like, _, spt_candl_data = load_like()
    self_test = official_self_test(like, spt_candl_data)
    if not self_test["pass"]:
        raise RuntimeError(f"SPT official self-test failed: {self_test}")

    active = profile(like, active_path)
    r1 = profile(like, r1_path)
    if not (active["robust"] and r1["robust"]):
        raise RuntimeError(f"SPT nuisance profile is start-sensitive: active={active['objective_spread']} r1={r1['objective_spread']}")
    delta = float(active["best"]["q"] - r1["best"]["q"])
    decision = classify_holdout(delta)

    result = {
        "schema": "nexo-peer017-spt-holdout/v1",
        "test_id": TEST_ID,
        "preregistration_drive_id": PREREG_DRIVE_ID,
        "winner_receipt_sha256": sha256_file(winner_path),
        "winner": winner["winner"],
        "spt_authority": {
            "repository": "SouthPoleTelescope/spt_candl_data",
            "commit": SPT_DATA_COMMIT,
            "candl_version": metadata.version("candl"),
            "dataset": "SPT3G_D1_TnE_lite",
            "n_bins": int(like.N_bins_total),
            "ell_max": int(like.ell_max),
            "profile": "Tcal with official prior; Ecal free; tau fixed identically at 0.054",
        },
        "official_self_test": self_test,
        "active": active,
        "r1": r1,
        "delta_q_spt_active_minus_r1": delta,
        "gate_strict_lt": 4.0,
        "decision": decision,
        "planck_transport_required": decision == "PASS_ACTTRAIN_SPT_HOLDOUT_EXISTENCE",
        "claim_boundary": "Independent SPT-3G D1 TnE-lite fixed-endpoint holdout after ACT-only model selection. No posterior preference or global evidence claim.",
    }
    (OUT / "spt_holdout_result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        failure = {"test_id": TEST_ID, "status": "EXECUTION_FAILURE", "exception": repr(exc), "traceback": traceback.format_exc()}
        (OUT / "failure.json").write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        raise
