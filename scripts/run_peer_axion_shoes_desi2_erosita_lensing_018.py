from __future__ import annotations

import json
import math
import os
from pathlib import Path

import numpy as np

import run_peer_axion_twofield_014 as b14
import run_peer_axion_acttrain_017 as b17

TEST_ID = "T-DE26-PEER-PNGB-AXION-SHOES-DESI2-EROSITA-LENSING-018"
PREREG_DRIVE_ID = "1A2ngCTukzMyovkFC1Lg8EoUF-TPg7TetKValqLHjc_0"
OUT = Path(os.environ.get("PEER_018_OUT", "results/peer-axion-shoes-desi2-erosita-lensing-018"))
OUT.mkdir(parents=True, exist_ok=True)

LATE_F = 2.0
LATE_DELTA = 0.8
SHOES_H0 = 73.04
SHOES_SIGMA = 1.04
EROSITA_S8 = 0.86
EROSITA_S8_SIGMA = 0.01
C_KMS = 299792.458

# Official DESI DR2 Gaussian ALL GCcomb data from CobayaSampler/bao_data/desi_bao_dr2.
DESI_ROWS = [
    (0.295, 7.94167639, "DV_over_rs"),
    (0.510, 13.58758434, "DM_over_rs"),
    (0.510, 21.86294686, "DH_over_rs"),
    (0.706, 17.35069094, "DM_over_rs"),
    (0.706, 19.45534918, "DH_over_rs"),
    (0.934, 21.57563956, "DM_over_rs"),
    (0.934, 17.64149464, "DH_over_rs"),
    (1.321, 27.60085612, "DM_over_rs"),
    (1.321, 14.17602155, "DH_over_rs"),
    (1.484, 30.51190063, "DM_over_rs"),
    (1.484, 12.81699964, "DH_over_rs"),
    (2.330, 8.631545674846294, "DH_over_rs"),
    (2.330, 38.988973961958784, "DM_over_rs"),
]
DESI_COV = np.array([
[5.78998687e-03,0,0,0,0,0,0,0,0,0,0,0,0],
[0,2.83473742e-02,-3.26062007e-02,0,0,0,0,0,0,0,0,0,0],
[0,-3.26062007e-02,1.83928040e-01,0,0,0,0,0,0,0,0,0,0],
[0,0,0,3.23752442e-02,-2.37445646e-02,0,0,0,0,0,0,0,0],
[0,0,0,-2.37445646e-02,1.11469198e-01,0,0,0,0,0,0,0,0],
[0,0,0,0,0,2.61732816e-02,-1.12938006e-02,0,0,0,0,0,0],
[0,0,0,0,0,-1.12938006e-02,4.04183878e-02,0,0,0,0,0,0],
[0,0,0,0,0,0,0,1.05336516e-01,-2.90308418e-02,0,0,0,0],
[0,0,0,0,0,0,0,-2.90308418e-02,5.04233092e-02,0,0,0,0],
[0,0,0,0,0,0,0,0,0,5.83020277e-01,-1.95215562e-01,0,0],
[0,0,0,0,0,0,0,0,0,-1.95215562e-01,2.68336193e-01,0,0],
[0,0,0,0,0,0,0,0,0,0,0,1.02136194e-02,-2.31395216e-02],
[0,0,0,0,0,0,0,0,0,0,0,-2.31395216e-02,2.82685779e-01],
], dtype=float)


def configure_active():
    b14.active_params = b17.active_factory(LATE_F, LATE_DELTA)


def dm_dh(data, z: float) -> tuple[float, float]:
    dm = float(data.angular_diameter_distance(z) * (1.0 + z))
    dh = float(C_KMS / data.hubble_parameter(z))
    return dm, dh


def desi_vector(data) -> np.ndarray:
    rdrag = float(data.get_derived_params()["rdrag"])
    vals = []
    for z, _, kind in DESI_ROWS:
        dm, dh = dm_dh(data, z)
        if kind == "DM_over_rs":
            val = dm / rdrag
        elif kind == "DH_over_rs":
            val = dh / rdrag
        elif kind == "DV_over_rs":
            dv = (z * dm * dm * dh) ** (1.0 / 3.0)
            val = dv / rdrag
        else:
            raise ValueError(kind)
        vals.append(val)
    return np.asarray(vals, dtype=float)


def chi2_gauss(obs: np.ndarray, pred: np.ndarray, cov: np.ndarray) -> float:
    delta = obs - pred
    return float(delta @ np.linalg.solve(cov, delta))


def omega_m_from_params(data) -> float:
    p = data.Params
    try:
        return float(p.omegam)
    except Exception:
        h = float(p.H0) / 100.0
        omnuh2 = float(getattr(p, "omnuh2", 0.06 / 93.14))
        return float((p.ombh2 + p.omch2 + omnuh2) / h**2)


def main() -> None:
    configure_active()
    f, m, amp, calibration, _, _ = b14.calibrate_common_background()
    if not calibration.get("calibration_pass", False):
        raise RuntimeError(f"common-background recalibration failed: {calibration}")

    _, active = b14.run_full_active(f, m, amp)
    _, comp = b14.run_full_comparator(f, m)
    aa = b14.base.cmb_arrays(active)
    ca = b14.base.cmb_arrays(comp)
    metrics, _, _ = b14.base.scientific_metrics(active, comp, aa, ca)

    # SH0ES
    h0_a = float(metrics["active"]["H0_realized"])
    h0_c = float(metrics["comparator"]["H0_realized"])
    pull_shoes_a = (h0_a - SHOES_H0) / SHOES_SIGMA
    pull_shoes_c = (h0_c - SHOES_H0) / SHOES_SIGMA
    chi2_shoes_a = pull_shoes_a**2
    chi2_shoes_c = pull_shoes_c**2

    # DESI DR2 exact Gaussian compressed likelihood.
    obs = np.asarray([x[1] for x in DESI_ROWS], dtype=float)
    pred_a = desi_vector(active)
    pred_c = desi_vector(comp)
    chi2_desi_a = chi2_gauss(obs, pred_a, DESI_COV)
    chi2_desi_c = chi2_gauss(obs, pred_c, DESI_COV)
    delta_desi = chi2_desi_a - chi2_desi_c

    # eROSITA eRASS1 compressed, explicitly model-conditional diagnostic.
    om_a = omega_m_from_params(active)
    om_c = omega_m_from_params(comp)
    s8_a = float(metrics["active"]["sigma8"]) * math.sqrt(om_a / 0.3)
    s8_c = float(metrics["comparator"]["sigma8"]) * math.sqrt(om_c / 0.3)
    pull_er_a = (s8_a - EROSITA_S8) / EROSITA_S8_SIGMA
    pull_er_c = (s8_c - EROSITA_S8) / EROSITA_S8_SIGMA

    # Native lensing potential stress against matched PEER+Lambda comparator.
    lens_rms = float(metrics["cmb"]["phiphi_rms_fractional"])
    lens_max = float(metrics["cmb"]["phiphi_max_abs_fractional"])

    gates = {
        "G0_native_finite": bool(metrics["finite_outputs"]),
        "G1_SH0ES_within_3sigma": abs(pull_shoes_a) <= 3.0,
        "G1b_SH0ES_within_2sigma": abs(pull_shoes_a) <= 2.0,
        "G2_DESI_DR2_absolute": chi2_desi_a / len(DESI_ROWS) < 2.0,
        "G2b_DESI_DR2_delta": delta_desi < 4.0,
        "G3_eROSITA_material_compressed_stress": abs(pull_er_a) >= 3.0,
        "G4_lensing_rms": lens_rms < 0.05,
        "G4b_lensing_max": lens_max < 0.10,
    }
    useful = bool(gates["G0_native_finite"] and gates["G1_SH0ES_within_3sigma"] and gates["G2_DESI_DR2_absolute"] and gates["G2b_DESI_DR2_delta"] and gates["G4_lensing_rms"] and gates["G4b_lensing_max"])

    result = {
        "schema": "nexo-peer018-shoes-desi2-erosita-lensing/v1",
        "test_id": TEST_ID,
        "preregistration_drive_id": PREREG_DRIVE_ID,
        "endpoint": {"late_f_Mpl": LATE_F, "late_delta_rad": LATE_DELTA, "f_early": f, "m_early": m, "late_amp": amp},
        "calibration": calibration,
        "SH0ES": {
            "H0_obs": SHOES_H0, "sigma": SHOES_SIGMA,
            "active_H0": h0_a, "comparator_H0": h0_c,
            "active_pull_sigma": pull_shoes_a, "active_chi2": chi2_shoes_a,
            "comparator_pull_sigma": pull_shoes_c, "comparator_chi2": chi2_shoes_c,
            "delta_chi2_active_minus_comparator": chi2_shoes_a - chi2_shoes_c,
        },
        "DESI_DR2": {
            "n": len(DESI_ROWS),
            "observed": obs.tolist(),
            "active_prediction": pred_a.tolist(),
            "comparator_prediction": pred_c.tolist(),
            "active_chi2": chi2_desi_a,
            "comparator_chi2": chi2_desi_c,
            "active_chi2_per_datum": chi2_desi_a / len(DESI_ROWS),
            "delta_chi2_active_minus_comparator": delta_desi,
        },
        "eROSITA_eRASS1_compressed": {
            "S8_obs": EROSITA_S8, "sigma": EROSITA_S8_SIGMA,
            "definition": "sigma8*(Omega_m/0.3)^0.5",
            "model_conditional_not_native_PEER_likelihood": True,
            "active_Omega_m": om_a, "active_sigma8": float(metrics["active"]["sigma8"]), "active_S8": s8_a, "active_pull_sigma": pull_er_a,
            "comparator_Omega_m": om_c, "comparator_sigma8": float(metrics["comparator"]["sigma8"]), "comparator_S8": s8_c, "comparator_pull_sigma": pull_er_c,
        },
        "lensing": {
            "native_phi_phi_rms_fractional": lens_rms,
            "native_phi_phi_max_abs_fractional": lens_max,
            "reference": "matched PEER-early + Lambda comparator",
            "ACT_excluded": True,
        },
        "background_sanity": {
            "rdrag_Mpc": float(metrics["active"]["r_drag_Mpc"]),
            "theta100": float(metrics["active"]["100theta_star"]),
            "late_w0": float(metrics["active"]["late_w0"]),
            "q0": float(metrics["active"]["q0"]),
            "sigma8": float(metrics["active"]["sigma8"]),
            "fsigma8": float(metrics["active"]["fsigma8"]),
        },
        "gates": gates,
        "demonstratively_useful_without_ACT": useful,
        "verdict": "PASS_DEMONSTRATIVE_USEFULNESS_WITH_EROSITA_GROWTH_STRESS" if useful else "FAIL_DEMONSTRATIVE_USEFULNESS",
        "claim_boundary": "eROSITA S8 is a model-conditional compressed diagnostic, not a PEER-native cluster likelihood. No global posterior/model selection claim.",
    }
    (OUT / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md = f"""# {TEST_ID}\n\nVerdict: **{result['verdict']}**\n\n- SH0ES pull: {pull_shoes_a:.4f} sigma; chi2={chi2_shoes_a:.4f}\n- DESI DR2: chi2={chi2_desi_a:.4f} for {len(DESI_ROWS)} observables; delta chi2(active-R1)={delta_desi:.4f}\n- eROSITA compressed S8: active S8={s8_a:.5f}, pull={pull_er_a:.3f} sigma (MODEL-CONDITIONAL STRESS ONLY)\n- Lensing phi-phi RMS={100*lens_rms:.4f}%, max={100*lens_max:.4f}%\n- ACT excluded: yes\n"""
    (OUT / "RESULT.md").write_text(md, encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
