from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from pathlib import Path
import traceback

import numpy as np
import camb
from camb import dark_energy

import run_peer_axion_twofield_014 as b14
from act_raw_likelihood_r1 import ACTCMBOnlyRaw
from peer_017_contract import (
    TEST_ID,
    PREREG_DRIVE_ID,
    OFFICIAL_CAMB_COMMIT,
    TRAINING_GRID,
    ACT_PAYLOAD_SHA256,
    ACT_014_GOLDEN_DELTA,
    ACT_014_GOLDEN_ACTIVE_OBJECTIVE,
    ACT_014_GOLDEN_R1_OBJECTIVE,
    choose_winner,
)

OUT = Path(os.environ.get("PEER_017_TRAIN_OUT", "results/peer-axion-acttrain-sptholdout-017/training"))
OUT.mkdir(parents=True, exist_ok=True)
ACT_PAYLOAD = Path(os.environ.get("PEER_ACT_PAYLOAD", "results/generated/act_dr6_cmbonly.bin"))
LMAX = 8501
RDRAG_REF = 143.07359092203805
THETA100_REF = 1.0401373761189423


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha_array(a: np.ndarray) -> str:
    x = np.ascontiguousarray(a)
    h = hashlib.sha256()
    h.update(x.dtype.str.encode("ascii"))
    h.update(np.asarray(x.shape, dtype=np.int64).tobytes())
    h.update(x.view(np.uint8))
    return h.hexdigest()


def active_factory(late_f: float, late_delta: float):
    theta = math.pi - float(late_delta)

    def active_params(*, f: float, m: float, late_amp: float, cmb: bool, transfer: bool):
        p = b14.common_params(cmb=cmb, transfer=transfer)
        de = dark_energy.PeerAxionTwoField()
        de.set_params(
            eta=0.1,
            f=f,
            m=m,
            theta_i=b14.THETA_I,
            use_zc=False,
            zc=b14.ZC_TARGET,
            fde_zc=b14.FDE_TARGET,
            late_f=float(late_f),
            late_theta_i=theta,
            late_amp=late_amp,
        )
        p.DarkEnergy = de
        return p

    return active_params


def high_l_endpoint(kind: str, *, f: float, m: float, amp: float):
    if kind == "active":
        p = b14.active_params(f=f, m=m, late_amp=amp, cmb=True, transfer=False)
    elif kind == "r1":
        p = b14.comparator_params(f=f, m=m, cmb=True, transfer=False)
    else:
        raise ValueError(kind)
    p.set_for_lmax(LMAX, lens_potential_accuracy=1)
    p.WantCls = True
    p.WantTransfer = False
    r = camb.get_results(p)
    dl = np.asarray(r.get_cmb_power_spectra(CMB_unit="muK", raw_cl=False)["total"], dtype=np.float64)
    if dl.shape[0] <= LMAX:
        raise RuntimeError(f"{kind} endpoint only covers ell={dl.shape[0]-1}")
    dl = np.ascontiguousarray(dl[: LMAX + 1])
    return {
        "tt": np.ascontiguousarray(dl[:, 0]),
        "ee": np.ascontiguousarray(dl[:, 1]),
        "bb": np.ascontiguousarray(dl[:, 2]),
        "te": np.ascontiguousarray(dl[:, 3]),
    }


def endpoint_hashes(x: dict[str, np.ndarray]) -> dict[str, str]:
    return {k: sha_array(v) for k, v in x.items()}


def physical_cell(late_f: float, late_delta: float, act: ACTCMBOnlyRaw):
    b14.active_params = active_factory(late_f, late_delta)
    f, m, amp, calibration, cal_evals, amp_evals = b14.calibrate_common_background()
    row: dict[str, object] = {
        "late_f": float(late_f),
        "late_delta": float(late_delta),
        "late_theta_i": float(math.pi - late_delta),
        "f_early": float(f) if math.isfinite(f) else None,
        "m_early": float(m) if math.isfinite(m) else None,
        "late_amp": float(amp) if math.isfinite(amp) else None,
        "calibration": calibration,
        "calibration_eval_count": len(cal_evals),
        "late_amp_eval_count": len(amp_evals),
        "eligible": False,
    }
    if not calibration.get("calibration_pass", False):
        row["ineligible_reason"] = "COMMON_BACKGROUND_RECALIBRATION"
        return row, None, None

    _, active = b14.run_full_active(f, m, amp)
    _, r1 = b14.run_full_comparator(f, m)
    a_arrays = b14.base.cmb_arrays(active)
    r_arrays = b14.base.cmb_arrays(r1)
    metrics, _, _ = b14.base.scientific_metrics(active, r1, a_arrays, r_arrays)
    a = metrics["active"]
    c = metrics["cmb"]
    g = metrics["geometry_growth"]

    gates = {
        "early_f": abs(float(a["f_peak"]) - 0.088) <= 0.005,
        "early_logz": abs(float(a["log10_z_peak"]) - 3.81) <= 0.02,
        "rdrag": abs(float(a["r_drag_Mpc"]) / RDRAG_REF - 1.0) < 0.005,
        "theta100": abs(float(a["100theta_star"]) / THETA100_REF - 1.0) < 0.005,
        "H0": abs(float(a["H0_realized"]) / b14.H0 - 1.0) < 1e-4,
        "late_acceleration": float(a["late_w0"]) <= -0.95 and float(a["q0"]) < 0.0,
        "finite": bool(metrics["finite_outputs"]),
        "cmb_shape": float(c["TT_rms_fractional"]) < 0.02 and float(c["EE_rms_fractional"]) < 0.02 and float(c["TE_rms_normalized"]) < 0.02,
        "lensing": float(c["phiphi_rms_fractional"]) < 0.05,
        "bao": float(g["BAO_max_abs_fractional"]) < 0.01,
        "growth": abs(float(g["sigma8_fractional"])) < 0.05 and abs(float(g["fsigma8_fractional"])) < 0.05,
        "sn": float(g["SN_mu_RMS_mag_after_offset"]) < 0.02,
    }

    active_hi = high_l_endpoint("active", f=f, m=m, amp=amp)
    active_hi_2 = high_l_endpoint("active", f=f, m=m, amp=amp)
    r1_hi = high_l_endpoint("r1", f=f, m=m, amp=amp)
    h1 = endpoint_hashes(active_hi)
    h2 = endpoint_hashes(active_hi_2)
    gates["deterministic"] = h1 == h2

    row["metrics"] = metrics
    row["gates"] = gates
    row["active_hashes"] = h1
    row["r1_hashes"] = endpoint_hashes(r1_hi)
    if not all(gates.values()):
        row["ineligible_reason"] = "PHYSICAL_ELIGIBILITY_GATE"
        return row, active_hi, r1_hi

    fit_a = act.fit_nuisance(active_hi)
    fit_r = act.fit_nuisance(r1_hi)
    delta = float(fit_a.objective - fit_r.objective)
    row["act"] = {
        "active": {
            "objective": float(fit_a.objective),
            "chi2": float(fit_a.chi2_ACT),
            "prior": float(fit_a.chi2_calibration_prior),
            "A_act": float(fit_a.A_act),
            "P_act": float(fit_a.P_act),
        },
        "r1": {
            "objective": float(fit_r.objective),
            "chi2": float(fit_r.chi2_ACT),
            "prior": float(fit_r.chi2_calibration_prior),
            "A_act": float(fit_r.A_act),
            "P_act": float(fit_r.P_act),
        },
    }
    row["delta_q_act"] = delta
    row["eligible"] = True
    return row, active_hi, r1_hi


def main() -> None:
    payload_hash = sha256_file(ACT_PAYLOAD)
    if payload_hash != ACT_PAYLOAD_SHA256:
        raise RuntimeError(f"ACT payload identity mismatch: {payload_hash}")
    act = ACTCMBOnlyRaw(ACT_PAYLOAD)

    rows: list[dict[str, object]] = []
    endpoints: dict[tuple[float, float], tuple[dict[str, np.ndarray] | None, dict[str, np.ndarray] | None]] = {}
    for late_f, late_delta in TRAINING_GRID:
        row, active_hi, r1_hi = physical_cell(late_f, late_delta, act)
        rows.append(row)
        endpoints[(float(late_f), float(late_delta))] = (active_hi, r1_hi)
        print(json.dumps({
            "late_f": late_f,
            "late_delta": late_delta,
            "eligible": row.get("eligible"),
            "delta_q_act": row.get("delta_q_act"),
            "reason": row.get("ineligible_reason"),
        }, sort_keys=True))

    # Registered 014 endpoint is a frozen internal golden replay inside the training grid.
    golden = next(row for row in rows if row["late_f"] == 1.0 and row["late_delta"] == 0.80)
    if not golden.get("eligible"):
        raise RuntimeError("014 golden cell became physically ineligible")
    gact = golden["act"]
    golden_check = {
        "active_objective_error": abs(float(gact["active"]["objective"]) - ACT_014_GOLDEN_ACTIVE_OBJECTIVE),
        "r1_objective_error": abs(float(gact["r1"]["objective"]) - ACT_014_GOLDEN_R1_OBJECTIVE),
        "delta_error": abs(float(golden["delta_q_act"]) - ACT_014_GOLDEN_DELTA),
    }
    golden_check["pass"] = max(golden_check.values()) < 2.0e-4
    if not golden_check["pass"]:
        raise RuntimeError(f"014 ACT golden replay failed: {golden_check}")

    winner = choose_winner(rows)
    key = (float(winner["late_f"]), float(winner["late_delta"]))
    active_win, r1_win = endpoints[key]
    if active_win is None or r1_win is None:
        raise RuntimeError("winner endpoint arrays missing")

    np.savez_compressed(OUT / "winner_active_Dl_uK2.npz", **active_win)
    np.savez_compressed(OUT / "winner_r1_Dl_uK2.npz", **r1_win)

    winner_receipt = {
        "schema": "nexo-peer017-act-training-winner/v1",
        "test_id": TEST_ID,
        "preregistration_drive_id": PREREG_DRIVE_ID,
        "workflow_repository_commit": os.environ.get("GITHUB_SHA"),
        "official_camb_commit": OFFICIAL_CAMB_COMMIT,
        "act_payload_sha256": payload_hash,
        "training_grid_size": len(TRAINING_GRID),
        "eligible_count": sum(bool(row.get("eligible")) for row in rows),
        "winner": winner,
        "winner_endpoint_hashes": {
            "active": endpoint_hashes(active_win),
            "r1": endpoint_hashes(r1_win),
        },
        "selection_rule": "minimum ACT deltaQ among eligible cells; within +0.25 choose larger delta, then larger f",
        "golden_replay_014": golden_check,
        "SPT_NOT_EVALUATED_WHEN_WRITTEN": True,
        "holdout_opened": False,
    }
    (OUT / "winner_receipt.json").write_text(json.dumps(winner_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "training_scores.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with (OUT / "training_scores.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["late_f", "late_delta", "eligible", "delta_q_act", "ineligible_reason"])
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in writer.fieldnames})

    print(json.dumps({
        "status": "ACT_TRAINING_COMPLETE_WINNER_FROZEN",
        "winner": {k: winner.get(k) for k in ("late_f", "late_delta", "delta_q_act", "f_early", "m_early", "late_amp")},
        "eligible_count": winner_receipt["eligible_count"],
        "golden_replay": golden_check,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        failure = {
            "test_id": TEST_ID,
            "status": "EXECUTION_FAILURE",
            "exception": repr(exc),
            "traceback": traceback.format_exc(),
        }
        (OUT / "failure.json").write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        raise
