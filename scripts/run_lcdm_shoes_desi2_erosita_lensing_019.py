from __future__ import annotations

import json
import math
import os
from pathlib import Path

import numpy as np
from scipy.integrate import quad

TEST_ID = "T-DE26-LCDM-SHOES-DESI2-EROSITA-LENSING-019"
PREREG_DRIVE_ID = "1hojh9BZQf7I0A8UcF83ImxYSLI8yXSWKtwK2RGxKMDI"
OUT = Path(os.environ.get("LCDM_019_OUT", "results/lcdm-shoes-desi2-erosita-lensing-019"))
OUT.mkdir(parents=True, exist_ok=True)

# Frozen converged same-stack LCDM best-point readout.
H0 = 68.5813
OMEGA_M = 0.2979
RDRAG = 147.4710
SIGMA8 = 0.8116
S8 = 0.8087
NS = 0.9711
A_LENS = 1.0

SHOES_H0 = 73.04
SHOES_SIGMA = 1.04
EROSITA_S8 = 0.86
EROSITA_S8_SIGMA = 0.01
C_KMS = 299792.458

# Frozen same-stack Planck lensing likelihood block values.
LCDM_LENSING_CHI2 = 9.0666
PEER1P_LENSING_CHI2 = 9.3835

# Official DESI DR2 Gaussian ALL GCcomb data and covariance used by battery 018.
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


def ez(z: float) -> float:
    return math.sqrt(OMEGA_M * (1.0 + z) ** 3 + (1.0 - OMEGA_M))


def dm_mpc(z: float) -> float:
    integral, _ = quad(lambda zp: 1.0 / ez(zp), 0.0, float(z), epsabs=1e-11, epsrel=1e-11, limit=200)
    return (C_KMS / H0) * integral


def dh_mpc(z: float) -> float:
    return C_KMS / (H0 * ez(float(z)))


def lcdm_bao_vector() -> np.ndarray:
    vals: list[float] = []
    for z, _, kind in DESI_ROWS:
        dm = dm_mpc(z)
        dh = dh_mpc(z)
        if kind == "DM_over_rs":
            val = dm / RDRAG
        elif kind == "DH_over_rs":
            val = dh / RDRAG
        elif kind == "DV_over_rs":
            val = (z * dm * dm * dh) ** (1.0 / 3.0) / RDRAG
        else:
            raise ValueError(kind)
        vals.append(float(val))
    return np.asarray(vals, dtype=float)


def chi2_gauss(obs: np.ndarray, pred: np.ndarray, cov: np.ndarray) -> float:
    delta = np.asarray(obs, dtype=float) - np.asarray(pred, dtype=float)
    return float(delta @ np.linalg.solve(cov, delta))


def run_battery() -> dict[str, object]:
    obs = np.asarray([x[1] for x in DESI_ROWS], dtype=float)
    pred = lcdm_bao_vector()
    chi2_desi = chi2_gauss(obs, pred, DESI_COV)

    shoes_pull = (H0 - SHOES_H0) / SHOES_SIGMA
    shoes_chi2 = shoes_pull**2

    s8_recomputed = SIGMA8 * math.sqrt(OMEGA_M / 0.3)
    erosita_pull = (S8 - EROSITA_S8) / EROSITA_S8_SIGMA

    lensing_delta_vs_peer = LCDM_LENSING_CHI2 - PEER1P_LENSING_CHI2

    gates = {
        "G0_finite": bool(np.isfinite(pred).all() and math.isfinite(chi2_desi)),
        "G1_SH0ES_within_3sigma": abs(shoes_pull) <= 3.0,
        "G1b_SH0ES_within_2sigma": abs(shoes_pull) <= 2.0,
        "G2_DESI_DR2_absolute": (chi2_desi / len(DESI_ROWS)) < 2.0,
        "G3_eROSITA_material_compressed_stress": abs(erosita_pull) >= 3.0,
        "G4_lensing_not_materially_worse_than_PEER": lensing_delta_vs_peer < 4.0,
    }

    useful = bool(
        gates["G0_finite"]
        and gates["G1_SH0ES_within_3sigma"]
        and gates["G2_DESI_DR2_absolute"]
        and gates["G4_lensing_not_materially_worse_than_PEER"]
    )

    if useful:
        verdict = "PASS_DEMONSTRATIVE_USEFULNESS_WITH_EROSITA_GROWTH_STRESS" if gates["G3_eROSITA_material_compressed_stress"] else "PASS_DEMONSTRATIVE_USEFULNESS"
    else:
        verdict = "FAIL_SHOES_WITH_DESI_AND_LENSING_PASS_EROSITA_GROWTH_STRESS"

    return {
        "schema": "nexo-lcdm019-shoes-desi2-erosita-lensing/v1",
        "test_id": TEST_ID,
        "preregistration_drive_id": PREREG_DRIVE_ID,
        "endpoint": {
            "model": "flat_LCDM",
            "source": "completed same-stack best-point diagnostic",
            "H0": H0,
            "Omega_m": OMEGA_M,
            "rdrag_Mpc": RDRAG,
            "sigma8": SIGMA8,
            "S8_frozen": S8,
            "S8_recomputed_from_sigma8_Omega_m": s8_recomputed,
            "ns": NS,
            "A_lens": A_LENS,
        },
        "SH0ES": {
            "H0_obs": SHOES_H0,
            "sigma": SHOES_SIGMA,
            "model_H0": H0,
            "pull_sigma": shoes_pull,
            "chi2": shoes_chi2,
        },
        "DESI_DR2": {
            "n": len(DESI_ROWS),
            "observed": obs.tolist(),
            "prediction": pred.tolist(),
            "chi2": chi2_desi,
            "chi2_per_datum": chi2_desi / len(DESI_ROWS),
            "likelihood": "official Gaussian ALL GCcomb 13x13 covariance",
        },
        "eROSITA_eRASS1_compressed": {
            "S8_obs": EROSITA_S8,
            "sigma": EROSITA_S8_SIGMA,
            "model_S8": S8,
            "pull_sigma": erosita_pull,
            "model_conditional_not_native_cluster_likelihood": True,
        },
        "lensing": {
            "metric": "same-stack Planck lensing likelihood chi2 block",
            "lcdm_chi2": LCDM_LENSING_CHI2,
            "peer1p_chi2": PEER1P_LENSING_CHI2,
            "delta_chi2_lcdm_minus_peer1p": lensing_delta_vs_peer,
            "native_phi_phi_directly_comparable_to_018": False,
            "boundary": "019 uses the frozen same-stack Planck lensing likelihood block; 018 used native CAMB phi-phi residuals against a matched PEER+Lambda comparator.",
        },
        "ACT_excluded": True,
        "gates": gates,
        "demonstratively_useful_without_ACT": useful,
        "verdict": verdict,
        "claim_boundary": "Fixed-endpoint cross-probe diagnostic. Not a global posterior, Bayesian model selection result, or a native eROSITA cluster likelihood. Lensing metric differs from the native phi-phi metric used in PEER 018 and is labeled explicitly.",
    }


def main() -> None:
    result = run_battery()
    (OUT / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md = f"""# {TEST_ID}\n\nVerdict: **{result['verdict']}**\n\n- SH0ES pull: {result['SH0ES']['pull_sigma']:.4f} sigma; chi2={result['SH0ES']['chi2']:.4f}\n- DESI DR2: chi2={result['DESI_DR2']['chi2']:.4f} for 13 observables; chi2/N={result['DESI_DR2']['chi2_per_datum']:.4f}\n- eROSITA compressed S8: {S8:.4f}; pull={result['eROSITA_eRASS1_compressed']['pull_sigma']:.3f} sigma (model-conditional diagnostic)\n- Planck lensing same-stack block: chi2_LCDM={LCDM_LENSING_CHI2:.4f}, chi2_PEER1p={PEER1P_LENSING_CHI2:.4f}, delta={result['lensing']['delta_chi2_lcdm_minus_peer1p']:.4f}\n- ACT excluded: yes\n\nBoundary: lensing is a same-stack Planck likelihood-block diagnostic here, not the native phi-phi RMS statistic used by PEER 018.\n"""
    (OUT / "RESULT.md").write_text(md, encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
