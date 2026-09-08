from __future__ import annotations

import math
import pytest

from peer_017_contract import (
    TEST_ID,
    PREREG_DRIVE_ID,
    TRAINING_GRID,
    choose_winner,
    classify_holdout,
)


def test_contract_identity_and_grid_are_frozen():
    assert TEST_ID == "T-DE26-PEER-PNGB-AXION-ACTTRAIN-SPTHOLDOUT-017"
    assert PREREG_DRIVE_ID == "1EEiGZrlZT42UesVsEF9N3f2Pf1zAV15YPFVrhDAO2Ck"
    assert len(TRAINING_GRID) == 20
    assert {c[0] for c in TRAINING_GRID} == {1.0, 1.5, 2.0, 3.0}
    assert {c[1] for c in TRAINING_GRID} == {0.10, 0.20, 0.35, 0.50, 0.80}
    assert all(f >= 1.0 for f, _ in TRAINING_GRID)


def test_choose_winner_minimizes_act_then_uses_frozen_tiebreak():
    rows = [
        {"late_f": 1.0, "late_delta": 0.20, "eligible": True, "delta_q_act": 2.0},
        {"late_f": 1.5, "late_delta": 0.50, "eligible": True, "delta_q_act": 2.20},
        {"late_f": 2.0, "late_delta": 0.50, "eligible": True, "delta_q_act": 2.20},
        {"late_f": 3.0, "late_delta": 0.80, "eligible": False, "delta_q_act": -10.0},
    ]
    # 2.20 is within 0.25 of the minimum 2.0; larger delta wins, then larger f.
    w = choose_winner(rows)
    assert w["late_f"] == 2.0
    assert w["late_delta"] == 0.50


def test_choose_winner_rejects_no_eligible_cells():
    with pytest.raises(ValueError, match="no eligible"):
        choose_winner([{"late_f": 1.0, "late_delta": 0.1, "eligible": False, "delta_q_act": 0.0}])


def test_holdout_gate_is_strict_and_does_not_move():
    assert classify_holdout(3.999999) == "PASS_ACTTRAIN_SPT_HOLDOUT_EXISTENCE"
    assert classify_holdout(4.0) == "FAIL_SPT_HOLDOUT"
    assert classify_holdout(10.0) == "FAIL_SPT_HOLDOUT"
    with pytest.raises(ValueError):
        classify_holdout(math.nan)
