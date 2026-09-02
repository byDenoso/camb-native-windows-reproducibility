#!/usr/bin/env python3
"""Small deterministic CAMB probe for R1 environment and repeatability receipts."""
from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
import sys


def run_once() -> dict[str, float]:
    import camb

    p = camb.CAMBparams()
    p.set_cosmology(H0=67.4, ombh2=0.0224, omch2=0.120, mnu=0.06, tau=0.054)
    p.InitPower.set_params(As=2.1e-9, ns=0.965)
    p.set_matter_power(redshifts=[0.0], kmax=2.0)
    r = camb.get_results(p)
    d = r.get_derived_params()
    return {
        "rdrag_mpc": float(d["rdrag"]),
        "theta_star_100": float(d["thetastar"]),
        "sigma8": float(r.get_sigma8_0()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--receipt", type=Path)
    args = ap.parse_args()
    import camb
    first = run_once()
    second = run_once()
    deltas = {k: abs(first[k] - second[k]) for k in first}
    tolerances = {"rdrag_mpc": 1e-12, "theta_star_100": 1e-12, "sigma8": 1e-12}
    passed = all(deltas[k] <= tolerances[k] for k in deltas)
    report = {
        "schema": "ascom-00323-r1-core-probe/v1",
        "platform": platform.platform(),
        "python": sys.version,
        "camb_version": getattr(camb, "__version__", "unknown"),
        "run_1": first,
        "run_2": second,
        "absolute_deltas": deltas,
        "tolerances": tolerances,
        "repeatability": "verified" if passed else "failed",
    }
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(text, end="")
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(text, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
