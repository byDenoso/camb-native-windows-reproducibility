from __future__ import annotations

import math

TEST_ID = "T-DE26-PX-CAMBCLASS-ACTPLANCK-LIKELIHOOD-RUNTIME-043"
OFFICIAL_CAMB_COMMIT = "3ef0272d6f7ba1231128872e56e6d4c12af8267b"

# Frozen inherited endpoint. No retuning is allowed in T-043.
W0 = -0.9927201860086855
CS2 = 0.0009124677221481836
Y0 = 1.0018299447408243
M_MEV = 2.3108224581047114
Z_TRIGGER = 3.0521159193018397

# Holdout materiality gates, frozen before likelihood execution.
ACT_MAX_DELTA_CHI2 = 4.0
PLANCK_MAX_DELTA_CHI2 = 4.0


def alpha_sym2(d: int = 4) -> float:
    if d < 2:
        raise ValueError("spacetime dimension must be >=2")
    n_src = d * (d + 1) // 2
    return math.log(float(n_src)) ** 4


def classify_likelihood_result(*, delta_chi2_act: float, delta_chi2_planck: float) -> str:
    act_fail = float(delta_chi2_act) > ACT_MAX_DELTA_CHI2
    planck_fail = float(delta_chi2_planck) > PLANCK_MAX_DELTA_CHI2
    if act_fail and planck_fail:
        return "FAIL_BOTH"
    if act_fail:
        return "FAIL_ACT"
    if planck_fail:
        return "FAIL_PLANCK"
    return "PASS_BOTH"
