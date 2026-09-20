from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import sys
import traceback
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

import camb
from camb import dark_energy, model


OUT = Path(os.environ.get("PEER_013_OUT", "results/peer-axion-twofield-013"))
OUT.mkdir(parents=True, exist_ok=True)

H0 = 70.7950037531
OMBH2 = 0.0229
OMCH2 = 0.1253
NS = 0.99
AS = 2.1086e-9
TAU = 0.054
YHE = 0.24610714079970886
THETA_I = 2.89155
ZC_TARGET = 10**3.81
FDE_TARGET = 0.088
RDRAG_REF = 143.07359092203805
RSTAR_REF = 140.6336320124512
THETASTAR_REF = 1.0401373761189423
C_KMS = 299792.458
SH0ES_H0 = 73.04
SH0ES_SIGMA = 1.04

BAO_REF = {
    0.38: (1466.2603651826435, 3476.5265389124147),
    0.51: (1901.6308003978563, 3223.4514391647526),
    0.698: (2475.1030056778022, 2883.0058503696873),
    1.48: (4287.398728190654, 1850.7063241235521),
    2.0: (5134.3083838201965, 1433.4351502870209),
}


def hash_array(arr: np.ndarray) -> str:
    a = np.ascontiguousarray(arr)
    return hashlib.sha256(a.view(np.uint8)).hexdigest()


def common_params(*, cmb: bool, transfer: bool) -> camb.CAMBparams:
    p = camb.CAMBparams()
    p.set_cosmology(
        H0=H0,
        ombh2=OMBH2,
        omch2=OMCH2,
        mnu=0.06,
        omk=0.0,
        tau=TAU,
        YHe=YHE,
    )
    p.InitPower.set_params(As=AS, ns=NS)
    p.NonLinear = model.NonLinear_none
    if cmb:
        p.set_for_lmax(2500, lens_potential_accuracy=1)
    else:
        p.WantCls = False
    if transfer:
        p.WantTransfer = True
        p.set_matter_power(redshifts=[0.0], kmax=2.0)
    return p


def active_params(*, f: float, m: float, late_amp: float, use_zc: bool, cmb: bool, transfer: bool):
    p = common_params(cmb=cmb, transfer=transfer)
    de = dark_energy.PeerAxionTwoField()
    de.set_params(
        eta=0.1,
        f=f,
        m=m,
        theta_i=THETA_I,
        use_zc=use_zc,
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


def calibrate_early() -> tuple[float, float, dict]:
    p = active_params(f=0.05, m=5e-54, late_amp=0.62, use_zc=True, cmb=False, transfer=False)
    d = camb.get_background(p)
    de = d.Params.DarkEnergy
    info = {
        "f": float(de.f),
        "m": float(de.m),
        "zc_common_replay": float(de.zc),
        "fde_common_replay": float(de.fde_zc),
        "late_rho_ratio0_at_seed": float(de.late_rho_ratio0),
        "late_w0_at_seed": float(de.late_w0),
    }
    return float(de.f), float(de.m), info


def tune_late_amp(f: float, m: float) -> tuple[float, list[dict]]:
    evals: list[dict] = []
    cache: dict[float, float] = {}

    def closure(amp: float) -> float:
        if amp in cache:
            return cache[amp]
        p = active_params(f=f, m=m, late_amp=amp, use_zc=False, cmb=False, transfer=False)
        d = camb.get_background(p)
        rho_ratio, w = d.get_dark_energy_rho_w(1.0)
        val = float(rho_ratio - 1.0)
        cache[amp] = val
        evals.append(
            {
                "late_amp": amp,
                "rho_de_ratio": float(rho_ratio),
                "combined_w0": float(w),
                "late_w0": float(d.Params.DarkEnergy.late_w0),
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
        if fa * fb < 0:
            bracket = (a, b)
            break
    if bracket is None:
        raise RuntimeError(f"late amplitude closure root not bracketed: {values}")
    root = brentq(closure, bracket[0], bracket[1], xtol=1e-10, rtol=1e-10, maxiter=80)
    closure(root)
    return float(root), evals


def run_full_active(f: float, m: float, amp: float):
    p = active_params(f=f, m=m, late_amp=amp, use_zc=False, cmb=True, transfer=True)
    return p, camb.get_results(p)


def run_full_comparator(f: float, m: float):
    p = comparator_params(f=f, m=m, cmb=True, transfer=True)
    return p, camb.get_results(p)


def cmb_arrays(data):
    cls = data.get_cmb_power_spectra(CMB_unit="muK", raw_cl=True)
    total = np.asarray(cls["total"], dtype=np.float64)
    lens = np.asarray(data.get_lens_potential_cls(lmax=400, raw_cl=True), dtype=np.float64)
    transfer = np.asarray(data.get_matter_transfer_data().transfer_data)
    return total, lens, transfer


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x))))


def frac_rms(active: np.ndarray, comp: np.ndarray) -> tuple[float, float]:
    mask = np.isfinite(active) & np.isfinite(comp) & (np.abs(comp) > 1e-300)
    frac = (active[mask] - comp[mask]) / comp[mask]
    return rms(frac), float(np.max(np.abs(frac)))


def scientific_metrics(active, comp, active_arrays, comp_arrays):
    total_a, lens_a, transfer_a = active_arrays
    total_c, lens_c, transfer_c = comp_arrays

    derived_a = active.get_derived_params()
    derived_c = comp.get_derived_params()
    de_a = active.Params.DarkEnergy

    ell = np.arange(min(total_a.shape[0], total_c.shape[0]))
    hi = (ell >= 30) & (ell <= 2500)
    tt_rms, tt_max = frac_rms(total_a[hi, 0], total_c[hi, 0])
    ee_rms, ee_max = frac_rms(total_a[hi, 1], total_c[hi, 1])
    te_diff = total_a[hi, 3] - total_c[hi, 3]
    te_rms_norm = rms(te_diff) / rms(total_c[hi, 3])

    low = (ell >= 2) & (ell <= 29)
    low_tt_norm = rms(total_a[low, 0] - total_c[low, 0]) / rms(total_c[low, 0])
    low_tt_max_abs = float(np.max(np.abs(total_a[low, 0] - total_c[low, 0])))

    L = np.arange(min(lens_a.shape[0], lens_c.shape[0]))
    lm = (L >= 8) & (L <= 400)
    pp_rms, pp_max = frac_rms(lens_a[lm, 0], lens_c[lm, 0])

    rdrag_a = float(derived_a["rdrag"])
    bao_rows = []
    bao_max = 0.0
    for z, (dm_ref, dh_ref) in BAO_REF.items():
        dm = float(active.comoving_radial_distance(z))
        dh = C_KMS / float(active.hubble_parameter(z))
        dm_ratio = dm / rdrag_a
        dh_ratio = dh / rdrag_a
        dm_ref_ratio = dm_ref / RDRAG_REF
        dh_ref_ratio = dh_ref / RDRAG_REF
        fdm = dm_ratio / dm_ref_ratio - 1.0
        fdh = dh_ratio / dh_ref_ratio - 1.0
        bao_max = max(bao_max, abs(fdm), abs(fdh))
        bao_rows.append(
            {
                "z": z,
                "DM_Mpc": dm,
                "DH_Mpc": dh,
                "DM_over_rd": dm_ratio,
                "DH_over_rd": dh_ratio,
                "PEER_DM_over_rd": dm_ref_ratio,
                "PEER_DH_over_rd": dh_ref_ratio,
                "frac_DM": fdm,
                "frac_DH": fdh,
            }
        )

    sigma8_a = float(np.ravel(active.get_sigma8())[-1])
    sigma8_c = float(np.ravel(comp.get_sigma8())[-1])
    fs8_a = float(np.ravel(active.get_fsigma8())[-1])
    fs8_c = float(np.ravel(comp.get_fsigma8())[-1])
    sigma8_frac = sigma8_a / sigma8_c - 1.0
    fs8_frac = fs8_a / fs8_c - 1.0

    zsn = np.geomspace(0.01, 2.3, 128)
    dla = np.array([(1.0 + z) * active.comoving_radial_distance(float(z)) for z in zsn])
    dlc = np.array([(1.0 + z) * comp.comoving_radial_distance(float(z)) for z in zsn])
    dmum = 5.0 * np.log10(dla / dlc)
    offset = float(np.mean(dmum))
    dmum_marg = dmum - offset
    sn_rms = rms(dmum_marg)

    H00 = float(active.hubble_parameter(0.0))
    dz = 1e-4
    H01 = float(active.hubble_parameter(dz))
    q0 = -1.0 + (H01 - H00) / dz / H00

    rho0, wtot0 = active.get_dark_energy_rho_w(1.0)
    fpeak = float(de_a.fde_zc)
    zpeak = float(de_a.zc)
    logzpeak = math.log10(zpeak)
    theta_a = float(derived_a["thetastar"])
    rstar_a = float(derived_a["rstar"])

    finite = bool(
        np.all(np.isfinite(total_a[:2501, [0, 1, 3]]))
        and np.all(np.isfinite(lens_a[:401, 0]))
        and np.all(np.isfinite(transfer_a))
    )

    metrics = {
        "active": {
            "f_peak": fpeak,
            "z_peak": zpeak,
            "log10_z_peak": logzpeak,
            "r_drag_Mpc": rdrag_a,
            "r_star_Mpc": rstar_a,
            "100theta_star": theta_a,
            "H0_realized": H00,
            "rho_de_ratio0": float(rho0),
            "combined_w0": float(wtot0),
            "late_w0": float(de_a.late_w0),
            "late_rho_ratio0": float(de_a.late_rho_ratio0),
            "q0": float(q0),
            "sigma8": sigma8_a,
            "fsigma8": fs8_a,
        },
        "comparator": {
            "r_drag_Mpc": float(derived_c["rdrag"]),
            "r_star_Mpc": float(derived_c["rstar"]),
            "100theta_star": float(derived_c["thetastar"]),
            "H0_realized": float(comp.hubble_parameter(0.0)),
            "sigma8": sigma8_c,
            "fsigma8": fs8_c,
        },
        "cmb": {
            "TT_rms_fractional": tt_rms,
            "TT_max_abs_fractional": tt_max,
            "EE_rms_fractional": ee_rms,
            "EE_max_abs_fractional": ee_max,
            "TE_rms_normalized": float(te_rms_norm),
            "low_l_TT_rms_normalized": float(low_tt_norm),
            "low_l_TT_max_abs_uK2": low_tt_max_abs,
            "phiphi_rms_fractional": pp_rms,
            "phiphi_max_abs_fractional": pp_max,
        },
        "geometry_growth": {
            "BAO_max_abs_fractional": float(bao_max),
            "sigma8_fractional": float(sigma8_frac),
            "fsigma8_fractional": float(fs8_frac),
            "SN_mu_RMS_mag_after_offset": float(sn_rms),
            "SN_additive_offset_mag": offset,
        },
        "finite_outputs": finite,
        "bao_rows": bao_rows,
        "shoes_descriptive": {
            "SH0ES_H0": SH0ES_H0,
            "SH0ES_sigma": SH0ES_SIGMA,
            "delta_H0": H00 - SH0ES_H0,
            "delta_sigma_if_gaussian_prior_only": (H00 - SH0ES_H0) / SH0ES_SIGMA,
        },
    }
    return metrics, zsn, dmum_marg


def gate_decisions(metrics, deterministic: bool):
    a = metrics["active"]
    cmbm = metrics["cmb"]
    gg = metrics["geometry_growth"]
    g0 = True
    g1 = (
        abs(a["f_peak"] - FDE_TARGET) <= 0.005
        and abs(a["log10_z_peak"] - 3.81) <= 0.02
        and abs(a["r_drag_Mpc"] / RDRAG_REF - 1.0) < 0.005
        and abs(a["100theta_star"] / THETASTAR_REF - 1.0) < 0.005
    )
    g2 = (
        abs(a["H0_realized"] / H0 - 1.0) < 1e-4
        and a["late_w0"] <= -0.95
        and a["q0"] < 0.0
        and abs(a["rho_de_ratio0"] - 1.0) < 1e-5
    )
    g3 = metrics["finite_outputs"] and deterministic
    g4 = cmbm["TT_rms_fractional"] < 0.02 and cmbm["EE_rms_fractional"] < 0.02 and cmbm["TE_rms_normalized"] < 0.02
    g5 = cmbm["phiphi_rms_fractional"] < 0.05
    g6 = gg["BAO_max_abs_fractional"] < 0.01 and abs(gg["sigma8_fractional"]) < 0.05 and abs(gg["fsigma8_fractional"]) < 0.05
    g7 = gg["SN_mu_RMS_mag_after_offset"] < 0.02
    gates = {"G0": g0, "G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "G6": g6, "G7": g7}
    gates["G8"] = all(gates.values())
    return gates


def write_csvs(metrics, zsn, dmum_marg, active_arrays, comp_arrays):
    with (OUT / "bao.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(metrics["bao_rows"][0].keys()))
        w.writeheader()
        w.writerows(metrics["bao_rows"])

    with (OUT / "sn_residuals.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["z", "delta_mu_after_offset_mag"])
        for z, dmu in zip(zsn, dmum_marg):
            w.writerow([float(z), float(dmu)])

    ta, la, _ = active_arrays
    tc, lc, _ = comp_arrays
    with (OUT / "spectral_differences.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ell", "TT_active", "TT_comp", "EE_active", "EE_comp", "TE_active", "TE_comp"])
        n = min(2501, ta.shape[0], tc.shape[0])
        for ell in range(2, n):
            w.writerow([ell, ta[ell,0], tc[ell,0], ta[ell,1], tc[ell,1], ta[ell,3], tc[ell,3]])

    with (OUT / "lensing_differences.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["L", "phiphi_active", "phiphi_comp"])
        n = min(401, la.shape[0], lc.shape[0])
        for L in range(2, n):
            w.writerow([L, la[L,0], lc[L,0]])


def main():
    early_f, early_m, calibration = calibrate_early()
    late_amp, amp_evals = tune_late_amp(early_f, early_m)

    active_pars, active = run_full_active(early_f, early_m, late_amp)
    comp_pars, comp = run_full_comparator(early_f, early_m)
    active_arrays = cmb_arrays(active)
    comp_arrays = cmb_arrays(comp)

    # Fresh second execution for deterministic native one-thread replay.
    _, active2 = run_full_active(early_f, early_m, late_amp)
    active2_arrays = cmb_arrays(active2)
    hashes1 = {
        "cmb_total": hash_array(active_arrays[0][:2501, :]),
        "lensing": hash_array(active_arrays[1][:401, :]),
        "transfer": hash_array(active_arrays[2]),
    }
    hashes2 = {
        "cmb_total": hash_array(active2_arrays[0][:2501, :]),
        "lensing": hash_array(active2_arrays[1][:401, :]),
        "transfer": hash_array(active2_arrays[2]),
    }
    deterministic = hashes1 == hashes2

    metrics, zsn, dmum_marg = scientific_metrics(active, comp, active_arrays, comp_arrays)
    gates = gate_decisions(metrics, deterministic)
    write_csvs(metrics, zsn, dmum_marg, active_arrays, comp_arrays)

    summary = {
        "test_id": "T-DE26-PEER-PNGB-AXION-NATIVE-2FIELD-013",
        "status": "PASS_NATIVE_TWO_FIELD_BOLTZMANN_EXISTENCE" if gates["G8"] else "FAIL_NATIVE_TWO_FIELD_BOLTZMANN_GATES",
        "camb_version": getattr(camb, "__version__", "unknown"),
        "official_camb_commit": "3ef0272d6f7ba1231128872e56e6d4c12af8267b",
        "workflow_repository_commit": os.environ.get("GITHUB_SHA"),
        "recombination_backend": type(active.Params.Recomb).__name__,
        "early_calibration": calibration,
        "frozen_early_f": early_f,
        "frozen_early_m": early_m,
        "late_amp_root": late_amp,
        "late_amp_evaluations": amp_evals,
        "metrics": metrics,
        "determinism": {"pass": deterministic, "hashes_run1": hashes1, "hashes_run2": hashes2},
        "gates": gates,
        "claim_boundary": "Native two-field CAMB Boltzmann existence only; no global likelihood preference or UV/naturalness claim.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not gates["G8"]:
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        failure = {
            "test_id": "T-DE26-PEER-PNGB-AXION-NATIVE-2FIELD-013",
            "status": "EXECUTION_FAILURE",
            "exception": repr(exc),
            "traceback": traceback.format_exc(),
        }
        (OUT / "failure.json").write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n")
        raise
