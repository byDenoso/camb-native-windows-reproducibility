from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
from pathlib import Path

os.environ.setdefault("CLIPY_NOJAX", "True")

import numpy as np

import camb
from camb import dark_energy, model

from act_raw_likelihood_r1 import ACTCMBOnlyRaw
from px_043_contract import (
    ACT_MAX_DELTA_CHI2,
    CS2,
    M_MEV,
    OFFICIAL_CAMB_COMMIT,
    PLANCK_MAX_DELTA_CHI2,
    TEST_ID,
    W0,
    Y0,
    Z_TRIGGER,
    alpha_sym2,
    classify_likelihood_result,
)
from px_043_likelihood import (
    build_cmb_clipy_cls,
    build_lensing_clipy_cls,
    crop_cls_for_likelihood,
    default_nuisance,
)


H0 = 70.7950037531
OMBH2 = 0.0229
OMCH2 = 0.1253
NS = 0.99
AS = 2.1086e-9
TAU = 0.054
YHE = 0.24610714079970886
THETA_I = 2.89155
ETA = 0.1
FDE_TARGET = 0.08799998604980758
LOG10_ZC_TARGET = 3.81009478804089
ZC_TARGET = 10.0 ** LOG10_ZC_TARGET
LMAX = 9000
ACT_PAYLOAD_SHA = "d3ca3ff9427ecb22141df32fb6b4398d3f9a3dcb1a10d22344b33c56a12b6484"
PLANCK_ARCHIVE_SHA = "0b73171e3acc671c28184466a45485a2d1c1d93676b832abdfe688c7b04024e6"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head(path: Path) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return None


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
        p.set_for_lmax(LMAX, lens_potential_accuracy=1)
    else:
        p.WantCls = False
    if transfer:
        p.WantTransfer = True
        p.set_matter_power(redshifts=[0.0, 0.5, 1.0, 2.0], kmax=2.0)
    return p


def active_params(*, f: float, m: float, use_zc: bool, cmb: bool, transfer: bool) -> camb.CAMBparams:
    p = common_params(cmb=cmb, transfer=transfer)
    de = dark_energy.PeerPXFluid()
    de.set_params(
        eta=ETA,
        f=f,
        m=m,
        theta_i=THETA_I,
        use_zc=use_zc,
        zc=ZC_TARGET,
        fde_zc=FDE_TARGET,
        late_w=W0,
        late_cs2=CS2,
    )
    p.DarkEnergy = de
    return p


def comparator_params(*, f: float, m: float, cmb: bool, transfer: bool) -> camb.CAMBparams:
    p = common_params(cmb=cmb, transfer=transfer)
    de = dark_energy.DeformedEarlyQuintessence()
    de.set_params(
        eta=ETA,
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
    seed = active_params(f=0.05, m=5e-54, use_zc=True, cmb=False, transfer=False)
    bg = camb.get_background(seed)
    de = bg.Params.DarkEnergy
    receipt = {
        "f": float(de.f),
        "m": float(de.m),
        "fde_zc": float(de.fde_zc),
        "zc": float(de.zc),
        "log10_zc": float(math.log10(float(de.zc))),
        "late_frac0": float(de.late_frac0),
        "late_grhov0": float(de.late_grhov0),
    }
    return float(de.f), float(de.m), receipt


def spectra(results) -> dict[str, np.ndarray]:
    raw = np.asarray(results.get_cmb_power_spectra(CMB_unit="muK", raw_cl=True)["total"], dtype=float)
    dl = np.asarray(results.get_cmb_power_spectra(CMB_unit="muK", raw_cl=False)["total"], dtype=float)
    pp = np.asarray(results.get_lens_potential_cls(lmax=LMAX, raw_cl=True), dtype=float)[:, 0]
    return {"raw": raw, "dl": dl, "pp": pp}


def act_fit(act: ACTCMBOnlyRaw, dl: np.ndarray) -> dict:
    theory = {"tt": dl[:, 0], "ee": dl[:, 1], "te": dl[:, 3]}
    fit = act.fit_nuisance(theory)
    return {
        "objective": float(fit.objective),
        "chi2_ACT": float(fit.chi2_ACT),
        "chi2_calibration_prior": float(fit.chi2_calibration_prior),
        "A_act": float(fit.A_act),
        "P_act": float(fit.P_act),
    }


def scalar_loglike(value) -> float:
    arr = np.asarray(value, dtype=float).reshape(-1)
    if arr.size != 1 or not np.isfinite(arr[0]):
        raise RuntimeError(f"likelihood did not return one finite value: {arr}")
    return float(arr[0])


def planck_component(path: Path, cls: np.ndarray) -> tuple[float, dict]:
    import clipy

    if not path.exists():
        raise FileNotFoundError(path)
    lkl = clipy.clik(str(path))
    nuisance = default_nuisance(lkl)
    theory = crop_cls_for_likelihood(cls, lkl)
    loglike = scalar_loglike(lkl(theory, nuisance))
    return -2.0 * loglike, {
        "path": str(path),
        "lmax": [int(x) for x in np.asarray(lkl.lmax).tolist()],
        "nuisance": nuisance,
        "loglike": loglike,
        "chi2_like": -2.0 * loglike,
    }


def planck_stack(planck_root: Path, spec: dict[str, np.ndarray]) -> dict:
    cmb_cls = build_cmb_clipy_cls(spec["raw"])
    lens_cls = build_lensing_clipy_cls(spec["raw"], spec["pp"])
    paths = {
        "highl_pliklite_TTTEEE": planck_root / "hi_l" / "plik_lite" / "plik_lite_v22_TTTEEE.clik",
        "lowT_commander": planck_root / "low_l" / "commander" / "commander_dx12_v3_2_29.clik",
        "lowE_simall": planck_root / "low_l" / "simall" / "simall_100x143_offlike5_EE_Aplanck_B.clik",
        "lensing_PR3": planck_root / "lensing" / "smicadx12_Dec5_ftl_mv2_ndclpp_p_teb_consext8.clik_lensing",
    }
    components: dict[str, dict] = {}
    total = 0.0
    for name, path in paths.items():
        cls = lens_cls if name == "lensing_PR3" else cmb_cls
        chi2, meta = planck_component(path, cls)
        components[name] = meta
        total += chi2
    return {"chi2_like_total": float(total), "components": components}


def frac_rms(a: np.ndarray, b: np.ndarray, lo: int, hi: int) -> float:
    n = min(a.size, b.size, hi + 1)
    aa = np.asarray(a[lo:n], dtype=float)
    bb = np.asarray(b[lo:n], dtype=float)
    mask = np.isfinite(aa) & np.isfinite(bb) & (np.abs(bb) > 1e-300)
    return float(np.sqrt(np.mean(np.square((aa[mask] - bb[mask]) / bb[mask]))))


def realized_metrics(results, spec: dict[str, np.ndarray]) -> dict:
    d = results.get_derived_params()
    de = results.Params.DarkEnergy
    sigma8 = np.asarray(results.get_sigma8(), dtype=float)
    fs8 = np.asarray(results.get_fsigma8(), dtype=float)
    rho0, wtot0 = results.get_dark_energy_rho_w(1.0)
    return {
        "H0": float(results.hubble_parameter(0.0)),
        "rdrag_Mpc": float(d["rdrag"]),
        "rstar_Mpc": float(d["rstar"]),
        "thetastar_100": float(d["thetastar"]),
        "fde_zc": float(de.fde_zc),
        "zc": float(de.zc),
        "log10_zc": float(math.log10(float(de.zc))),
        "rho_de_ratio0": float(rho0),
        "w_de_total0": float(wtot0),
        "sigma8": [float(x) for x in sigma8.tolist()],
        "fsigma8": [float(x) for x in fs8.tolist()],
        "finite_cmb": bool(np.all(np.isfinite(spec["raw"][: LMAX + 1, [0, 1, 3]]))),
        "finite_pp": bool(np.all(np.isfinite(spec["pp"][: min(2501, spec["pp"].size)]))),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--act-payload", type=Path, required=True)
    ap.add_argument("--planck-root", type=Path, required=True)
    ap.add_argument("--camb-source", type=Path, required=False)
    ap.add_argument("--output", type=Path, default=Path("results/px-043/px_043_result.json"))
    args = ap.parse_args()

    act_hash = sha256_file(args.act_payload)
    if act_hash != ACT_PAYLOAD_SHA:
        raise SystemExit(f"ACT payload SHA mismatch: {act_hash}")
    camb_head = git_head(args.camb_source) if args.camb_source else None
    if camb_head is not None and camb_head != OFFICIAL_CAMB_COMMIT:
        raise SystemExit(f"CAMB commit mismatch: {camb_head}")

    f, m, calibration = calibrate_early()

    active_p = active_params(f=f, m=m, use_zc=False, cmb=True, transfer=True)
    comp_p = comparator_params(f=f, m=m, cmb=True, transfer=True)
    active = camb.get_results(active_p)
    comp = camb.get_results(comp_p)

    active_spec = spectra(active)
    comp_spec = spectra(comp)

    act = ACTCMBOnlyRaw(args.act_payload)
    act_active = act_fit(act, active_spec["dl"])
    act_comp = act_fit(act, comp_spec["dl"])
    delta_act = float(act_active["objective"] - act_comp["objective"])

    planck_active = planck_stack(args.planck_root, active_spec)
    planck_comp = planck_stack(args.planck_root, comp_spec)
    delta_planck = float(planck_active["chi2_like_total"] - planck_comp["chi2_like_total"])

    component_deltas = {
        key: float(planck_active["components"][key]["chi2_like"] - planck_comp["components"][key]["chi2_like"])
        for key in planck_active["components"]
    }

    classification = classify_likelihood_result(delta_chi2_act=delta_act, delta_chi2_planck=delta_planck)
    active_metrics = realized_metrics(active, active_spec)
    comp_metrics = realized_metrics(comp, comp_spec)

    cmb_delta = {
        "TT_rms_frac_l30_2500": frac_rms(active_spec["raw"][:, 0], comp_spec["raw"][:, 0], 30, 2500),
        "EE_rms_frac_l30_2500": frac_rms(active_spec["raw"][:, 1], comp_spec["raw"][:, 1], 30, 2500),
        "phiphi_rms_frac_L8_400": frac_rms(active_spec["pp"], comp_spec["pp"], 8, 400),
    }

    payload = {
        "schema": "nexo-t-de26-px-actplanck-043/v1",
        "test_id": TEST_ID,
        "status": "COMPLETE_RUNTIME" if classification == "PASS_BOTH" else "COMPLETE_RUNTIME_SCIENTIFIC_FAIL",
        "decision": classification,
        "claim_boundary": (
            "Native CAMB effective-fluid observational holdout for PEER-early + separately conserved low-cs late P(X) proxy. "
            "The microscopic composite DM trigger and UV reflection mechanism are not implemented by this runtime."
        ),
        "frozen_contract": {
            "official_camb_commit": OFFICIAL_CAMB_COMMIT,
            "w0": W0,
            "cs2": CS2,
            "Y0": Y0,
            "M_meV": M_MEV,
            "z_trigger": Z_TRIGGER,
            "alpha_sym2": alpha_sym2(4),
            "ACT_max_delta_chi2": ACT_MAX_DELTA_CHI2,
            "Planck_max_delta_chi2": PLANCK_MAX_DELTA_CHI2,
            "no_cosmological_retune": True,
            "planck_nuisance_policy": "fixed likelihood self-test defaults; no cosmological or nuisance profiling",
            "act_nuisance_policy": "A_act and P_act profiled exactly as inherited ACTCMBOnlyRaw contract",
        },
        "runtime_identity": {
            "camb_python_version": getattr(camb, "__version__", None),
            "camb_source_head": camb_head,
            "act_payload_sha256": act_hash,
            "expected_act_payload_sha256": ACT_PAYLOAD_SHA,
            "expected_planck_archive_sha256": PLANCK_ARCHIVE_SHA,
        },
        "early_calibration": calibration,
        "active": active_metrics,
        "comparator": comp_metrics,
        "cmb_relative": cmb_delta,
        "ACT": {
            "active": act_active,
            "comparator": act_comp,
            "delta_chi2_objective_active_minus_comparator": delta_act,
            "gate_pass": bool(delta_act <= ACT_MAX_DELTA_CHI2),
        },
        "Planck": {
            "active": planck_active,
            "comparator": planck_comp,
            "component_delta_chi2_active_minus_comparator": component_deltas,
            "delta_chi2_like_active_minus_comparator": delta_planck,
            "gate_pass": bool(delta_planck <= PLANCK_MAX_DELTA_CHI2),
        },
        "net": {
            "classification": classification,
            "both_holdouts_pass": classification == "PASS_BOTH",
            "delta_chi2_ACT": delta_act,
            "delta_chi2_Planck": delta_planck,
        },
    }

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    payload["payload_sha256"] = hashlib.sha256(canonical).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
