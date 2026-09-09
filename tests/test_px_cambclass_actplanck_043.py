from __future__ import annotations

import math

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


def test_043_contract_is_frozen_before_runtime() -> None:
    assert TEST_ID == "T-DE26-PX-CAMBCLASS-ACTPLANCK-LIKELIHOOD-RUNTIME-043"
    assert OFFICIAL_CAMB_COMMIT == "3ef0272d6f7ba1231128872e56e6d4c12af8267b"
    assert W0 == -0.9927201860086855
    assert CS2 == 0.0009124677221481836
    assert Y0 == 1.0018299447408243
    assert M_MEV == 2.3108224581047114
    assert Z_TRIGGER == 3.0521159193018397
    assert ACT_MAX_DELTA_CHI2 == 4.0
    assert PLANCK_MAX_DELTA_CHI2 == 4.0


def test_sym2_alpha_is_geometric_and_not_retuned() -> None:
    expected = math.log(10.0) ** 4
    assert alpha_sym2(4) == expected
    assert abs(expected - 28.110123573894416) < 1e-13


def test_likelihood_gate_requires_both_holdouts() -> None:
    assert classify_likelihood_result(delta_chi2_act=3.99, delta_chi2_planck=3.99) == "PASS_BOTH"
    assert classify_likelihood_result(delta_chi2_act=4.01, delta_chi2_planck=0.0) == "FAIL_ACT"
    assert classify_likelihood_result(delta_chi2_act=0.0, delta_chi2_planck=4.01) == "FAIL_PLANCK"
    assert classify_likelihood_result(delta_chi2_act=5.0, delta_chi2_planck=5.0) == "FAIL_BOTH"
