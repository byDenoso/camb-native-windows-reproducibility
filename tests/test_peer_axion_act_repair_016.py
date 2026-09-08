from __future__ import annotations

import math
import pytest

from peer_016_contract import (
    ACT_PAYLOAD_SHA256,
    ACT_GOLDEN_OBJECTIVE,
    EARLY_F_TARGET,
    EARLY_LOG10Z_TARGET,
    LATE_DELTA,
    LATE_F,
    classify_act_delta,
)


def test_pre_act_012_late_witness_is_frozen_exactly():
    assert LATE_F == pytest.approx(0.5, rel=0, abs=0)
    assert LATE_DELTA == pytest.approx(0.260138, rel=0, abs=0)
    assert EARLY_F_TARGET == pytest.approx(0.088, rel=0, abs=0)
    assert EARLY_LOG10Z_TARGET == pytest.approx(3.81, rel=0, abs=0)


def test_act_identity_and_golden_reference_are_frozen():
    assert ACT_PAYLOAD_SHA256 == "d3ca3ff9427ecb22141df32fb6b4398d3f9a3dcb1a10d22344b33c56a12b6484"
    assert ACT_GOLDEN_OBJECTIVE == pytest.approx(156.73503293248388, rel=0, abs=0)


def test_act_repair_gate_is_strictly_less_than_plus_four():
    assert classify_act_delta(3.999999) == "PASS_ACT_REPAIR_GATE"
    assert classify_act_delta(4.0) == "FAIL_MATERIAL_ACT_STRESS"
    assert classify_act_delta(27.027222181083687) == "FAIL_MATERIAL_ACT_STRESS"


def test_nonfinite_act_delta_is_execution_failure():
    with pytest.raises(ValueError):
        classify_act_delta(math.nan)
