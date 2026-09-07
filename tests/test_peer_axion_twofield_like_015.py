from __future__ import annotations

import math
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from peer_015_contract import (
    MODEL_014,
    R1_MODEL,
    R2_MODEL,
    BlockResult,
    classify_blocks,
)


def test_014_physical_point_is_frozen_exactly():
    assert MODEL_014["f_early"] == pytest.approx(0.1250578159382164, rel=0, abs=0)
    assert MODEL_014["m_early"] == pytest.approx(5.631907724965834e-55, rel=0, abs=0)
    assert MODEL_014["late_amp"] == pytest.approx(0.6170978019891916, rel=0, abs=0)
    assert MODEL_014["H0"] == pytest.approx(70.7950037531, rel=0, abs=0)
    assert MODEL_014["ombh2"] == pytest.approx(0.0229)
    assert MODEL_014["omch2"] == pytest.approx(0.1253)
    assert MODEL_014["ns"] == pytest.approx(0.99)
    assert MODEL_014["As"] == pytest.approx(2.1086e-9)
    assert MODEL_014["tau"] == pytest.approx(0.054)
    assert MODEL_014["YHe"] == pytest.approx(0.24610714079970886)
    assert MODEL_014["mnu"] == pytest.approx(0.06)


def test_rivals_do_not_change_frozen_cosmology():
    for key in ("H0", "ombh2", "omch2", "ns", "As", "tau", "YHe", "mnu"):
        assert R1_MODEL[key] == MODEL_014[key]
        assert R2_MODEL[key] == MODEL_014[key]
    assert R1_MODEL["early"] is True
    assert R1_MODEL["late_axion"] is False
    assert R1_MODEL["lambda_closure"] is True
    assert R2_MODEL["early"] is False
    assert R2_MODEL["late_axion"] is False
    assert R2_MODEL["lambda_closure"] is True


def test_scientific_gate_is_strictly_less_than_plus_four():
    blocks = {
        name: BlockResult(name=name, status="PASS", delta_active_r1=3.999999, delta_active_r2=0.0)
        for name in ("planck_pr4", "act", "spt_y1", "desi_dr2", "pantheon_noshoes")
    }
    out = classify_blocks(blocks)
    assert out["G2"] and out["G3"] and out["G4"] and out["G5"] and out["G6"]
    assert out["G7"] is True
    assert out["G8"] == "ADVANCE_TO_LOCAL_PROFILE"

    blocks["planck_pr4"] = BlockResult(
        name="planck_pr4", status="PASS", delta_active_r1=4.0, delta_active_r2=0.0
    )
    out = classify_blocks(blocks)
    assert out["G2"] is False
    assert out["G7"] is False
    assert out["G8"] == "LOCALIZED_ENDPOINT_STRESS"


def test_native_resource_blocker_never_becomes_scientific_fail():
    blocks = {
        name: BlockResult(name=name, status="PASS", delta_active_r1=0.0, delta_active_r2=0.0)
        for name in ("planck_pr4", "act", "spt_y1", "desi_dr2", "pantheon_noshoes")
    }
    blocks["spt_y1"] = BlockResult(
        name="spt_y1",
        status="BLOCKED_NATIVE_LIKELIHOOD",
        delta_active_r1=None,
        delta_active_r2=None,
        blocker="BLOCKED_REFERENCE_REPLAY",
    )
    out = classify_blocks(blocks)
    assert out["G4"] is None
    assert out["G7"] is None
    assert out["G8"] == "BLOCKED_NATIVE_LIKELIHOOD"


def test_cmb_experiments_are_not_summed_as_independent_evidence():
    blocks = {
        "planck_pr4": BlockResult("planck_pr4", "PASS", -1.0, -2.0),
        "act": BlockResult("act", "PASS", 1.5, 2.0),
        "spt_y1": BlockResult("spt_y1", "PASS", 0.5, 1.0),
        "desi_dr2": BlockResult("desi_dr2", "PASS", -0.2, -0.1),
        "pantheon_noshoes": BlockResult("pantheon_noshoes", "PASS", 0.3, 0.2),
    }
    out = classify_blocks(blocks)
    assert out["cmb_worst_active_r1"] == pytest.approx(1.5)
    assert "cmb_sum_active_r1" not in out
    assert out["late_descriptive_sum_active_r1"] == pytest.approx(0.1)


def test_block_result_rejects_nonfinite_scientific_delta():
    with pytest.raises(ValueError):
        BlockResult("act", "PASS", math.nan, 0.0)
