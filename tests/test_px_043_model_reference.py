from __future__ import annotations

import math

from px_043_contract import CS2, W0
from px_043_model import fluid_rhs, late_grhov_t


def test_late_background_normalizes_at_a1_and_scales_conservatively() -> None:
    grhov = 7.5
    frac = 0.999
    assert late_grhov_t(1.0, grhov, frac, W0) == frac * grhov
    a = 0.5
    expected = frac * grhov * a ** (-1.0 - 3.0 * W0)
    assert math.isclose(late_grhov_t(a, grhov, frac, W0), expected, rel_tol=0.0, abs_tol=1e-15)


def test_late_fluid_rhs_matches_camb_constant_w_form() -> None:
    delta = 2.5e-5
    velocity = -1.2e-5
    adotoa = 0.004
    k = 0.08
    metric_z = 3.0e-6
    ddelta, dvelocity = fluid_rhs(
        delta=delta,
        velocity=velocity,
        adotoa=adotoa,
        k=k,
        metric_z=metric_z,
        w=W0,
        cs2=CS2,
    )
    hv3_over_k = 3.0 * adotoa * velocity / k
    expected_delta = (
        -3.0 * adotoa * (CS2 - W0) * (delta + (1.0 + W0) * hv3_over_k)
        - (1.0 + W0) * k * velocity
        - (1.0 + W0) * k * metric_z
    )
    expected_velocity = -adotoa * (1.0 - 3.0 * CS2) * velocity + k * CS2 * delta / (1.0 + W0)
    assert math.isclose(ddelta, expected_delta, rel_tol=1e-15, abs_tol=0.0)
    assert math.isclose(dvelocity, expected_velocity, rel_tol=1e-15, abs_tol=0.0)
