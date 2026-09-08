from __future__ import annotations

import math

import run_lcdm_shoes_desi2_erosita_lensing_019 as r19


def test_frozen_lcdm_endpoint_identity():
    assert r19.TEST_ID == "T-DE26-LCDM-SHOES-DESI2-EROSITA-LENSING-019"
    assert r19.PREREG_DRIVE_ID == "1hojh9BZQf7I0A8UcF83ImxYSLI8yXSWKtwK2RGxKMDI"
    assert r19.H0 == 68.5813
    assert r19.OMEGA_M == 0.2979
    assert r19.RDRAG == 147.4710
    assert r19.SIGMA8 == 0.8116
    assert r19.S8 == 0.8087


def test_exact_desi_dr2_flat_lcdm_battery_value():
    result = r19.run_battery()
    desi = result["DESI_DR2"]
    assert desi["n"] == 13
    assert math.isclose(desi["chi2"], 11.996314270886952, rel_tol=0.0, abs_tol=2e-8)
    assert math.isclose(desi["chi2_per_datum"], 0.9227934054528425, rel_tol=0.0, abs_tol=2e-9)
    assert result["gates"]["G2_DESI_DR2_absolute"] is True


def test_shoes_and_erosita_localize_lcdm_stress():
    result = r19.run_battery()
    assert result["gates"]["G1_SH0ES_within_3sigma"] is False
    assert result["gates"]["G1b_SH0ES_within_2sigma"] is False
    assert result["gates"]["G3_eROSITA_material_compressed_stress"] is True
    assert result["SH0ES"]["pull_sigma"] < -4.0
    assert result["eROSITA_eRASS1_compressed"]["pull_sigma"] < -5.0


def test_lensing_uses_frozen_same_stack_likelihood_block_not_native_phi_phi():
    result = r19.run_battery()
    lens = result["lensing"]
    assert lens["metric"] == "same-stack Planck lensing likelihood chi2 block"
    assert math.isclose(lens["lcdm_chi2"], 9.0666, abs_tol=1e-12)
    assert math.isclose(lens["peer1p_chi2"], 9.3835, abs_tol=1e-12)
    assert result["gates"]["G4_lensing_not_materially_worse_than_PEER"] is True
    assert lens["native_phi_phi_directly_comparable_to_018"] is False


def test_act_is_excluded_and_failure_does_not_short_circuit_other_probes():
    result = r19.run_battery()
    assert result["ACT_excluded"] is True
    assert "DESI_DR2" in result and "eROSITA_eRASS1_compressed" in result and "lensing" in result
    assert result["demonstratively_useful_without_ACT"] is False
    assert result["verdict"] == "FAIL_SHOES_WITH_DESI_AND_LENSING_PASS_EROSITA_GROWTH_STRESS"
