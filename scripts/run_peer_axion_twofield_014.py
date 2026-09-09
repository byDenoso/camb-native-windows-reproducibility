from __future__ import annotations

import csv
import importlib.util
import json
import math
import os
import traceback
from pathlib import Path

import numpy as np
from scipy.optimize import brentq, root

import camb
from camb import dark_energy


TEST_ID = "T-DE26-PEER-PNGB-AXION-NATIVE-2FIELD-RECAL-014"
OUT = Path(os.environ.get("PEER_014_OUT", "results/peer-axion-twofield-014"))
OUT.mkdir(parents=True, exist_ok=True)

H0 = 70.7950037531
THETA_I = 2.89155
FDE_TARGET = 0.088
LOG10_ZC_TARGET = 3.81
ZC_TARGET = 10**LOG10_ZC_TARGET
CAL_F_TOL = 1e-5
CAL_LOGZ_TOL = 1e-4
LOCAL_FACTOR = 2.0
LOG_LOCAL_BOUND = math.log(LOCAL_FACTOR)
F013 = 0.1208288042833779
M013 = 6.337671319929203e-55
RDRAG_REF = 143.07359092203805
THETASTAR_REF = 1.0401373761189423
OFFICIAL_CAMB_COMMIT = "3ef0272d6f7ba1231128872e56e6d4c12af8267b"
PREREG_DRIVE_ID = "15JhkrG5vlgWSIry7TL7apX-06acSc2whU09aA2HmYuc"


def _load_base013():
    path = Path(__file__).with_name("run_peer_axion_twofield_013.py")
    spec = importlib.util.spec_from_file_location("peer013_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frozen 013 runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = OUT
    return module


base = _load_base013()


def common_params(*, cmb: bool, transfer: bool):
    return base.common_params(cmb=cmb, transfer=transfer)


def active_params(*, f: float, m: float, late_amp: float, cmb: bool, transfer: bool):
    p = common_params(cmb=cmb, transfer=transfer)
    de = dark_energy.PeerAxionTwoField()
    de.set_params(
        eta=0.1,
        f=f,
        m=m,
        theta_i=THETA_I,
        use_zc=False,
        zc=ZC_TARGET,
        fde_zc=FDE_TARGET,
        late_f=1.0,
        late_theta_i=math.pi - 0.8,
        late_amp=late_amp,
    )
    p.DarkEnergy = de
    return p


def comparator_params(*, f: float, m: float, cmb: bool, transfer: bool):
    p = common_params(cmb=cmb, transfer=transfer)
    de = dark_energy.DeformedEarlyQuintessence()
    de.set_params(
        eta=0.1,
        f=f,
        m=m,
        theta_i=THETA_I,
        use_zc=False,
        zc=ZC_TARGET,
        fde_zc=FDE_TARGET,
        frac_lambda0=1.0,
    )
    p.DarkEnergy = de
    return p


def inside_local_corridor(f: float, m: float) -> bool:
    if not (math.isfinite(f) and math.isfinite(m) and f > 0.0 and m > 0.0):
        return False
    log_f = math.log(f)
    log_m = math.log(m)
    return (
        abs(log_f - math.log(F013)) <= LOG_LOCAL_BOUND + 1e-12
        and abs(log_m - math.log(M013)) <= LOG_LOCAL_BOUND + 1e-12
    )


def tune_late_amp(f: float, m: float) -> tuple[float, list[dict]]:
    if not inside_local_corridor(f, m):
        raise ValueError("late closure requested outside preregistered local corridor")
    evals: list[dict] = []
    cache: dict[float, float] = {}

    def closure(amp: float) -> float:
        if amp in cache:
            return cache[amp]
        p = active_params(f=f, m=m, late_amp=amp, cmb=False, transfer=False)
        d = camb.get_background(p)
        h0_realized = float(d.hubble_parameter(0.0))
        rho_api_raw, w = d.get_dark_energy_rho_w(1.0)
        val = float(h0_realized / H0 - 1.0)
        cache[amp] = val
        evals.append(
            {
                "late_amp": amp,
                "H0_realized": h0_realized,
                "rho_de_api_raw": float(rho_api_raw),
                "combined_w0": float(w),
                "late_w0": float(d.Params.DarkEnergy.late_w0),
                "late_rho_ratio0": float(d.Params.DarkEnergy.late_rho_ratio0),
                "closure_residual": val,
            }
        )
        return val

    grid = [0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2]
    values = [(x, closure(x)) for x in grid]
    bracket = None
    for (a, fa), (b, fb) in zip(values[:-1], values[1:]):
        if fa == 0.0:
            return a, evals
        if fa * fb < 0.0:
            bracket = (a, b)
            break
    if bracket is None:
        raise RuntimeError(f"late amplitude H0 closure root not bracketed: {values}")
    amp_root = brentq(closure, bracket[0], bracket[1], xtol=1e-10, rtol=1e-10, maxiter=80)
    closure(amp_root)
    return float(amp_root), evals


def _measure_common_background(f: float, m: float) -> tuple[dict, list[dict]]:
    if not inside_local_corridor(f, m):
        raise ValueError("common-background measurement outside preregistered local corridor")
    amp, amp_evals = tune_late_amp(f, m)
    p = active_params(f=f, m=m, late_amp=amp, cmb=False, transfer=False)
    d = camb.get_background(p)
    de = d.Params.DarkEnergy
    measure = {
        "f": float(f),
        "m": float(m),
        "late_amp": float(amp),
        "H0_realized": float(d.hubble_parameter(0.0)),
        "f_peak": float(de.fde_zc),
        "z_peak": float(de.zc),
        "log10_z_peak": float(math.log10(de.zc)),
        "late_w0": float(de.late_w0),
        "late_rho_ratio0": float(de.late_rho_ratio0),
    }
    return measure, amp_evals


def _outside_local_penalty(logfm: np.ndarray) -> np.ndarray:
    penalty = np.zeros(2, dtype=float)
    for i, value in enumerate(np.asarray(logfm, dtype=float)):
        if value > LOG_LOCAL_BOUND:
            penalty[i] = 0.1 + value - LOG_LOCAL_BOUND
        elif value < -LOG_LOCAL_BOUND:
            penalty[i] = -0.1 + value + LOG_LOCAL_BOUND
    return penalty


def calibrate_common_background() -> tuple[float, float, float, dict, list[dict], list[dict]]:
    evaluations: list[dict] = []

    def residual(logfm: np.ndarray) -> np.ndarray:
        f = F013 * math.exp(float(logfm[0]))
        m = M013 * math.exp(float(logfm[1]))
        if not inside_local_corridor(f, m):
            penalty = _outside_local_penalty(logfm)
            evaluations.append(
                {
                    "status": "outside_local_corridor",
                    "f": float(f) if math.isfinite(f) else None,
                    "m": float(m) if math.isfinite(m) else None,
                    "log_f_ratio": float(logfm[0]),
                    "log_m_ratio": float(logfm[1]),
                    "penalty_f": float(penalty[0]),
                    "penalty_m": float(penalty[1]),
                }
            )
            return penalty
        measure, amp_evals = _measure_common_background(f, m)
        measure["status"] = "physical_evaluation"
        measure["log_f_ratio"] = float(logfm[0])
        measure["log_m_ratio"] = float(logfm[1])
        measure["residual_f_peak"] = measure["f_peak"] - FDE_TARGET
        measure["residual_log10_z_peak"] = measure["log10_z_peak"] - LOG10_ZC_TARGET
        measure["late_amp_eval_count"] = len(amp_evals)
        evaluations.append(measure)
        return np.array(
            [measure["residual_f_peak"], measure["residual_log10_z_peak"]],
            dtype=float,
        )

    x0 = np.array([0.0, 0.0], dtype=float)
    solved = root(
        residual,
        x0,
        method="hybr",
        options={"xtol": 1e-10, "maxfev": 80, "eps": 1e-4, "factor": 0.2},
    )
    f = F013 * math.exp(float(solved.x[0]))
    m = M013 * math.exp(float(solved.x[1]))
    local = inside_local_corridor(f, m)
    if not local:
        calibration = {
            "solver_success": bool(solved.success),
            "solver_message": str(solved.message),
            "solver_nfev": int(getattr(solved, "nfev", -1)),
            "f": float(f) if math.isfinite(f) else None,
            "m": float(m) if math.isfinite(m) else None,
            "late_amp": None,
            "f_peak": None,
            "z_peak": None,
            "log10_z_peak": None,
            "abs_f_peak_residual": None,
            "abs_log10_z_peak_residual": None,
            "local_factor2_pass": False,
            "calibration_pass": False,
        }
        return f, m, float("nan"), calibration, evaluations, []

    final, amp_evals = _measure_common_background(f, m)
    f_resid = abs(final["f_peak"] - FDE_TARGET)
    z_resid = abs(final["log10_z_peak"] - LOG10_ZC_TARGET)
    calibration_pass = bool(local and f_resid <= CAL_F_TOL and z_resid <= CAL_LOGZ_TOL)
    calibration = {
        "solver_success": bool(solved.success),
        "solver_message": str(solved.message),
        "solver_nfev": int(getattr(solved, "nfev", -1)),
        "f": float(f),
        "m": float(m),
        "late_amp": float(final["late_amp"]),
        "f_peak": float(final["f_peak"]),
        "z_peak": float(final["z_peak"]),
        "log10_z_peak": float(final["log10_z_peak"]),
        "abs_f_peak_residual": float(f_resid),
        "abs_log10_z_peak_residual": float(z_resid),
        "local_factor2_pass": bool(local),
        "calibration_pass": calibration_pass,
    }
    return float(f), float(m), float(final["late_amp"]), calibration, evaluations, amp_evals


def run_full_active(f: float, m: float, amp: float):
    p = active_params(f=f, m=m, late_amp=amp, cmb=True, transfer=True)
    return p, camb.get_results(p)


def run_full_comparator(f: float, m: float):
    p = comparator_params(f=f, m=m, cmb=True, transfer=True)
    return p, camb.get_results(p)


def gate_decisions(metrics: dict, deterministic: bool, calibration: dict) -> dict:
    a = metrics["active"]
    cmbm = metrics["cmb"]
    gg = metrics["geometry_growth"]
    g0 = True
    g1 = (
        calibration["calibration_pass"]
        and abs(a["f_peak"] - FDE_TARGET) <= 0.005
        and abs(a["log10_z_peak"] - LOG10_ZC_TARGET) <= 0.02
        and abs(a["r_drag_Mpc"] / RDRAG_REF - 1.0) < 0.005
        and abs(a["100theta_star"] / THETASTAR_REF - 1.0) < 0.005
    )
    g2 = abs(a["H0_realized"] / H0 - 1.0) < 1e-4 and a["late_w0"] <= -0.95 and a["q0"] < 0.0
    g3 = metrics["finite_outputs"] and deterministic
    g4 = cmbm["TT_rms_fractional"] < 0.02 and cmbm["EE_rms_fractional"] < 0.02 and cmbm["TE_rms_normalized"] < 0.02
    g5 = cmbm["phiphi_rms_fractional"] < 0.05
    g6 = gg["BAO_max_abs_fractional"] < 0.01 and abs(gg["sigma8_fractional"]) < 0.05 and abs(gg["fsigma8_fractional"]) < 0.05
    g7 = gg["SN_mu_RMS_mag_after_offset"] < 0.02
    gates = {"G0": g0, "G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "G6": g6, "G7": g7}
    gates["G8"] = all(gates.values())
    return gates


def write_calibration_csv(evaluations: list[dict]) -> None:
    if not evaluations:
        return
    keys = sorted({k for row in evaluations for k in row.keys()})
    with (OUT / "calibration_evaluations.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(evaluations)


def main() -> None:
    early_f, early_m, late_amp, calibration, cal_evals, final_amp_evals = calibrate_common_background()
    write_calibration_csv(cal_evals)

    if not calibration["calibration_pass"]:
        summary = {
            "test_id": TEST_ID,
            "status": "FAIL_COMMON_BACKGROUND_LOCAL_RECALIBRATION",
            "preregistration_drive_id": PREREG_DRIVE_ID,
            "official_camb_commit": OFFICIAL_CAMB_COMMIT,
            "workflow_repository_commit": os.environ.get("GITHUB_SHA"),
            "calibration": calibration,
            "calibration_evaluations": cal_evals,
            "final_late_amp_evaluations": final_amp_evals,
            "gates": {"G0": True, "G1": False, "G2": False, "G3": False, "G4": False, "G5": False, "G6": False, "G7": False, "G8": False},
            "claim_boundary": "Local common-background recalibration test only; downstream Boltzmann gates are not executed if calibration fails.",
        }
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        print(json.dumps(summary, indent=2, sort_keys=True))
        raise SystemExit(2)

    _, active = run_full_active(early_f, early_m, late_amp)
    _, comp = run_full_comparator(early_f, early_m)
    active_arrays = base.cmb_arrays(active)
    comp_arrays = base.cmb_arrays(comp)

    _, active2 = run_full_active(early_f, early_m, late_amp)
    active2_arrays = base.cmb_arrays(active2)
    hashes1 = {
        "cmb_total": base.hash_array(active_arrays[0][:2501, :]),
        "lensing": base.hash_array(active_arrays[1][:401, :]),
        "transfer": base.hash_array(active_arrays[2]),
    }
    hashes2 = {
        "cmb_total": base.hash_array(active2_arrays[0][:2501, :]),
        "lensing": base.hash_array(active2_arrays[1][:401, :]),
        "transfer": base.hash_array(active2_arrays[2]),
    }
    deterministic = hashes1 == hashes2

    metrics, zsn, dmum_marg = base.scientific_metrics(active, comp, active_arrays, comp_arrays)
    if "rho_de_ratio0" in metrics["active"]:
        metrics["active"]["rho_de_api_raw"] = metrics["active"].pop("rho_de_ratio0")
    gates = gate_decisions(metrics, deterministic, calibration)
    base.write_csvs(metrics, zsn, dmum_marg, active_arrays, comp_arrays)

    summary = {
        "test_id": TEST_ID,
        "status": "PASS_NATIVE_TWO_FIELD_BOLTZMANN_EXISTENCE_AFTER_COMMON_BACKGROUND_RECALIBRATION" if gates["G8"] else "FAIL_NATIVE_TWO_FIELD_BOLTZMANN_GATES_AFTER_RECALIBRATION",
        "preregistration_drive_id": PREREG_DRIVE_ID,
        "camb_version": getattr(camb, "__version__", "unknown"),
        "official_camb_commit": OFFICIAL_CAMB_COMMIT,
        "workflow_repository_commit": os.environ.get("GITHUB_SHA"),
        "recombination_backend": type(active.Params.Recomb).__name__,
        "calibration": calibration,
        "calibration_evaluations": cal_evals,
        "frozen_early_f": early_f,
        "frozen_early_m": early_m,
        "late_amp_root": late_amp,
        "final_late_amp_evaluations": final_amp_evals,
        "metrics": metrics,
        "determinism": {"pass": deterministic, "hashes_run1": hashes1, "hashes_run2": hashes2},
        "gates": gates,
        "claim_boundary": "Native two-field CAMB Boltzmann existence after a preregistered local common-background early recalibration; no global likelihood preference, Bayes factor, UV or naturalness claim.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not gates["G8"]:
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
