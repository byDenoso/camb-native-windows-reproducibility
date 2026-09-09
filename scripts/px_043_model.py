from __future__ import annotations


def late_grhov_t(a: float, grhov: float, frac0: float, w: float) -> float:
    a = float(a)
    if a <= 0.0:
        return 0.0
    return float(frac0) * float(grhov) * a ** (-1.0 - 3.0 * float(w))


def fluid_rhs(
    *,
    delta: float,
    velocity: float,
    adotoa: float,
    k: float,
    metric_z: float,
    w: float,
    cs2: float,
) -> tuple[float, float]:
    delta = float(delta)
    velocity = float(velocity)
    adotoa = float(adotoa)
    k = float(k)
    metric_z = float(metric_z)
    w = float(w)
    cs2 = float(cs2)
    if k == 0.0:
        raise ValueError("k must be non-zero")
    one_plus_w = 1.0 + w
    if abs(one_plus_w) <= 1e-12:
        return 0.0, 0.0
    hv3_over_k = 3.0 * adotoa * velocity / k
    ddelta = (
        -3.0 * adotoa * (cs2 - w) * (delta + one_plus_w * hv3_over_k)
        - one_plus_w * k * velocity
        - one_plus_w * k * metric_z
    )
    dvelocity = -adotoa * (1.0 - 3.0 * cs2) * velocity + k * cs2 * delta / one_plus_w
    return ddelta, dvelocity
