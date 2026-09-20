from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

C_KM_S = 299792.458
OUT = Path("results/peer-axion-twofield-014")
OUT.mkdir(parents=True, exist_ok=True)

FROZEN_F = 0.1250578159382164
FROZEN_M = 5.631907724965834e-55
FROZEN_LATE_AMP = 0.6170978019891916

ROWS = [
    (0.295, "DV_over_rs"),
    (0.510, "DM_over_rs"),
    (0.510, "DH_over_rs"),
    (0.706, "DM_over_rs"),
    (0.706, "DH_over_rs"),
    (0.934, "DM_over_rs"),
    (0.934, "DH_over_rs"),
    (1.321, "DM_over_rs"),
    (1.321, "DH_over_rs"),
    (1.484, "DM_over_rs"),
    (1.484, "DH_over_rs"),
    (2.330, "DH_over_rs"),
    (2.330, "DM_over_rs"),
]


def load_runner():
    path = Path(__file__).with_name("run_peer_axion_twofield_014.py")
    spec = importlib.util.spec_from_file_location("peer014", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frozen 014 runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def vector(results):
    rd = float(results.get_derived_params()["rdrag"])
    out = []
    for z, kind in ROWS:
        da = float(results.angular_diameter_distance(z))
        dm = (1.0 + z) * da
        dh = C_KM_S / float(results.hubble_parameter(z))
        if kind == "DM_over_rs":
            value = dm / rd
        elif kind == "DH_over_rs":
            value = dh / rd
        elif kind == "DV_over_rs":
            value = (z * dm * dm * dh) ** (1.0 / 3.0) / rd
        else:
            raise ValueError(kind)
        out.append((z, kind, value, rd))
    return out


def main():
    r = load_runner()
    _, active = r.run_full_active(FROZEN_F, FROZEN_M, FROZEN_LATE_AMP)
    _, comparator = r.run_full_comparator(FROZEN_F, FROZEN_M)
    av = vector(active)
    cv = vector(comparator)
    path = OUT / "desi_dr2_full13_predictions.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["index", "z", "quantity", "active", "comparator", "active_rdrag_Mpc", "comparator_rdrag_Mpc"])
        for i, (a, c) in enumerate(zip(av, cv)):
            assert a[0] == c[0] and a[1] == c[1]
            w.writerow([i, a[0], a[1], a[2], c[2], a[3], c[3]])
    print(path.read_text())


if __name__ == "__main__":
    main()
