from __future__ import annotations

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
from peer_016_contract import (
    TEST_ID,
    PREREG_DRIVE_ID,
    OFFICIAL_CAMB_COMMIT,
    H0_TARGET,
    EARLY_F_TARGET,
    EARLY_LOG10Z_TARGET,
    EARLY_F_TOL,
    EARLY_LOG10Z_TOL,
    RDRAG_REFERENCE,
    THETA100_REFERENCE,
    LATE_F,
    LATE_THETA_I,
)

OUT = Path(os.environ.get("PEER_016_OUT", "results/peer-axion-act-repair-016"))
OUT.mkdir(parents=True, exist_ok=True)
LMAX_ACT = 8501


def sha_array(a: np.ndarray) -> str:
    x = np.ascontiguousarray(a)
    h = hashlib.sha256()
    h.update(x.dtype.str.encode("ascii"))
    h.update(np.asarray(x.shape, dtype=np.int64).tobytes())
    h.update(x.view(np.uint8))
    return h.hexdigest()


def active_params_016(*, f: float, m: float, late_amp: float, cmb: bool, transfer: bool):
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
        late_f=LATE_F,
        late_theta_i=LATE_THETA_I,
        late_amp=late_amp,
    )
    p.DarkEnergy = de
    return p


# Reuse the frozen 014 calibration machinery with only the pre-ACT 016 late witness changed.
b14.active_params = active_params_016


def calibration_and_background():
    f, m, amp, calibration, evaluations, amp_evals = b14.calibrate_common_background()
    p = active_params_016(f=f, m=m, late_amp=amp, cmb=False, transfer=False)
    d = camb.get_background(p)
    derived = d.get_derived_params()
    de = d.Params.DarkEnergy
    h00 = float(d.hubble_parameter(0.0))
    dz = 1.0e-4
    h01 = float(d.hubble_parameter(dz))
    q0 = -1.0 + (h01 - h00) / dz / h00
    background = {
        "H0": h00,
        "rdrag": float(derived["rdrag"]),
        "rstar": float(derived["rstar"]),
        "theta100": float(derived["thetastar"]),
        "f_peak": float(de.fde_zc),
        "z_peak": float(de.zc),
        "log10_z_peak": float(math.log10(de.zc)),
        "late_w0": float(de.late_w0),
        "late_rho_ratio0": float(de.late_rho_ratio0),
        "q0": float(q0),
    }
    g1 = bool(
        calibration["calibration_pass"]
        and abs(background["f_peak"] - EARLY_F_TARGET) <= EARLY_F_TOL
        and abs(background["log10_z_peak"] - EARLY_LOG10Z_TARGET) <= EARLY_LOG10Z_TOL
        and abs(background["H0"] / H0_TARGET - 1.0) < 1e-4
        and abs(background["rdrag"] / RDRAG_REFERENCE - 1.0) < 0.005
        and abs(background["theta100"] / THETA100_REFERENCE - 1.0) < 0.005
    )
    g2 = bool(background["late_w0"] <= -0.95 and background["q0"] < 0.0)
    return f, m, amp, calibration, evaluations, amp_evals, background, g1, g2


def high_l_endpoint(name: str, *, f: float, m: float, amp: float):
    if name == "active":
        p = active_params_016(f=f, m=m, late_amp=amp, cmb=True, transfer=False)
    elif name == "r1":
        p = b14.comparator_params(f=f, m=m, cmb=True, transfer=False)
    else:
        raise ValueError(name)
    p.set_for_lmax(LMAX_ACT, lens_potential_accuracy=1)
    p.WantCls = True
    p.WantTransfer = False
    r = camb.get_results(p)
    dl = np.asarray(r.get_cmb_power_spectra(CMB_unit="muK", raw_cl=False)["total"], dtype=np.float64)
    if dl.shape[0] <= LMAX_ACT:
        raise RuntimeError(f"endpoint {name} only covers ell={dl.shape[0]-1}")
    dl = np.ascontiguousarray(dl[: LMAX_ACT + 1])
    return r, {"tt": dl[:, 0], "ee": dl[:, 1], "bb": dl[:, 2], "te": dl[:, 3]}


def save_endpoint(name: str, arrays: dict[str, np.ndarray]) -> dict[str, str]:
    np.savez_compressed(OUT / f"endpoint_{name}_Dl_uK2.npz", **arrays)
    return {key: sha_array(value) for key, value in arrays.items()}


def main() -> None:
    f, m, amp, calibration, cal_evals, amp_evals, background, g1, g2 = calibration_and_background()
    if not (g1 and g2):
        summary = {
            "test_id": TEST_ID,
            "status": "FAIL_PRE_ACT_REPAIR_BACKGROUND_GATE",
            "preregistration_drive_id": PREREG_DRIVE_ID,
            "official_camb_commit": OFFICIAL_CAMB_COMMIT,
            "workflow_repository_commit": os.environ.get("GITHUB_SHA"),
            "late_witness": {"late_f": LATE_F, "late_theta_i": LATE_THETA_I},
            "calibration": calibration,
            "background": background,
            "G1": g1,
            "G2": g2,
        }
        (OUT / "summary_pre_act.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        print(json.dumps(summary, indent=2, sort_keys=True))
        raise SystemExit(2)

    _, active_full = b14.run_full_active(f, m, amp)
    _, r1_full = b14.run_full_comparator(f, m)
    a_arrays = b14.base.cmb_arrays(active_full)
    r_arrays = b14.base.cmb_arrays(r1_full)
    _, active_full_2 = b14.run_full_active(f, m, amp)
    a2_arrays = b14.base.cmb_arrays(active_full_2)
    hashes_full_1 = {
        "cmb_total": b14.base.hash_array(a_arrays[0][:2501, :]),
        "lensing": b14.base.hash_array(a_arrays[1][:401, :]),
        "transfer": b14.base.hash_array(a_arrays[2]),
    }
    hashes_full_2 = {
        "cmb_total": b14.base.hash_array(a2_arrays[0][:2501, :]),
        "lensing": b14.base.hash_array(a2_arrays[1][:401, :]),
        "transfer": b14.base.hash_array(a2_arrays[2]),
    }
    deterministic_full = hashes_full_1 == hashes_full_2
    metrics, zsn, dmum = b14.base.scientific_metrics(active_full, r1_full, a_arrays, r_arrays)
    b14.base.write_csvs(metrics, zsn, dmum, a_arrays, r_arrays)

    cmbm = metrics["cmb"]
    gg = metrics["geometry_growth"]
    g4 = bool(metrics["finite_outputs"] and deterministic_full)
    g5 = bool(cmbm["TT_rms_fractional"] < 0.02 and cmbm["EE_rms_fractional"] < 0.02 and cmbm["TE_rms_normalized"] < 0.02)
    g6 = bool(cmbm["phiphi_rms_fractional"] < 0.05)
    g7 = bool(
        gg["BAO_max_abs_fractional"] < 0.01
        and abs(gg["sigma8_fractional"]) < 0.05
        and abs(gg["fsigma8_fractional"]) < 0.05
        and gg["SN_mu_RMS_mag_after_offset"] < 0.02
    )

    _, act_a = high_l_endpoint("active", f=f, m=m, amp=amp)
    _, act_a2 = high_l_endpoint("active", f=f, m=m, amp=amp)
    _, act_r1 = high_l_endpoint("r1", f=f, m=m, amp=amp)
    h_a = save_endpoint("active", act_a)
    h_a2 = {k: sha_array(v) for k, v in act_a2.items()}
    h_r1 = save_endpoint("r1", act_r1)
    deterministic_act = h_a == h_a2

    summary = {
        "test_id": TEST_ID,
        "status": "READY_FOR_REGISTERED_ACT_PROFILE" if all((g1, g2, g4, g5, g6, g7, deterministic_act)) else "FAIL_PRE_ACT_REPAIR_EXISTENCE_GATE",
        "preregistration_drive_id": PREREG_DRIVE_ID,
        "camb_version": getattr(camb, "__version__", "unknown"),
        "official_camb_commit": OFFICIAL_CAMB_COMMIT,
        "workflow_repository_commit": os.environ.get("GITHUB_SHA"),
        "late_witness": {"late_f": LATE_F, "late_theta_i": LATE_THETA_I, "late_delta": math.pi - LATE_THETA_I},
        "calibration": calibration,
        "calibration_evaluations": cal_evals,
        "late_amp_evaluations": amp_evals,
        "frozen_early_f": f,
        "frozen_early_m": m,
        "late_amp_root": amp,
        "background": background,
        "existence_metrics": metrics,
        "determinism_full": {"pass": deterministic_full, "run1": hashes_full_1, "run2": hashes_full_2},
        "act_endpoint_hashes": {"active": h_a, "active_repeat": h_a2, "r1": h_r1, "pass": deterministic_act},
        "gates_before_act": {"G0_CAMB": True, "G1": g1, "G2": g2, "G4": g4 and deterministic_act, "G5": g5, "G6": g6, "G7": g7},
        "claim_boundary": "Pre-ACT-selected f_l=0.5, delta=0.260138 Lambda-free physical revision. ACT result still required. No global profile or naturalness claim.",
    }
    (OUT / "summary_pre_act.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if summary["status"] != "READY_FOR_REGISTERED_ACT_PROFILE":
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as exc:
        failure = {
            "test_id": TEST_ID,
            "status": "EXECUTION_FAILURE",
            "exception": repr(exc),
            "traceback": traceback.format_exc(),
        }
        (OUT / "failure.json").write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n")
        raise
