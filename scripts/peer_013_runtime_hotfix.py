from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "scripts/run_peer_axion_twofield_013.py")
    text = path.read_text()
    before = hashlib.sha256(text.encode()).hexdigest()

    # Root cause: CAMBdata.get_dark_energy_rho_w() calls BackgroundDensityAndPressure
    # with grhov=1. The native 013 model intentionally normalizes its potential with
    # State%grhov, so the returned rho is not a dimensionless rho/rho_DE,0 closure
    # diagnostic for this custom model. The preregistered closure is H0 itself.
    old_closure = '''        d = camb.get_background(p)\n        rho_ratio, w = d.get_dark_energy_rho_w(1.0)\n        val = float(rho_ratio - 1.0)\n        cache[amp] = val\n        evals.append(\n            {\n                "late_amp": amp,\n                "rho_de_ratio": float(rho_ratio),\n                "combined_w0": float(w),\n                "late_w0": float(d.Params.DarkEnergy.late_w0),\n                "closure_residual": val,\n            }\n        )\n'''
    new_closure = '''        d = camb.get_background(p)\n        h0_realized = float(d.hubble_parameter(0.0))\n        _rho_api_raw, w = d.get_dark_energy_rho_w(1.0)\n        val = float(h0_realized / H0 - 1.0)\n        cache[amp] = val\n        evals.append(\n            {\n                "late_amp": amp,\n                "H0_realized": h0_realized,\n                "rho_de_api_raw": float(_rho_api_raw),\n                "combined_w0": float(w),\n                "late_w0": float(d.Params.DarkEnergy.late_w0),\n                "late_rho_ratio0": float(d.Params.DarkEnergy.late_rho_ratio0),\n                "closure_residual": val,\n            }\n        )\n'''
    text = replace_once(text, old_closure, new_closure, "H0 closure diagnostic")

    text = replace_once(
        text,
        '    rho0, wtot0 = active.get_dark_energy_rho_w(1.0)\n',
        '    rho_api_raw, wtot0 = active.get_dark_energy_rho_w(1.0)\n',
        "rho diagnostic variable",
    )
    text = replace_once(
        text,
        '            "rho_de_ratio0": float(rho0),\n',
        '            "rho_de_api_raw": float(rho_api_raw),\n',
        "rho diagnostic label",
    )

    # The rho_de_ratio0 condition was not in frozen G2. Keeping it would silently
    # strengthen the preregistration using a quantity whose Python helper has the
    # normalization mismatch above. Frozen G2 is H0 closure + w_late + q0 + no Lambda.
    text = replace_once(
        text,
        '        and a["q0"] < 0.0\n        and abs(a["rho_de_ratio0"] - 1.0) < 1e-5\n',
        '        and a["q0"] < 0.0\n',
        "restore frozen G2",
    )

    after = hashlib.sha256(text.encode()).hexdigest()
    if before == after:
        raise RuntimeError("runtime hotfix produced no change")
    path.write_text(text)

    # Readback assertions: exact intended semantic changes and no accidental gate move.
    reread = path.read_text()
    assert 'val = float(h0_realized / H0 - 1.0)' in reread
    assert '"rho_de_api_raw": float(rho_api_raw)' in reread
    assert 'abs(a["rho_de_ratio0"] - 1.0)' not in reread
    assert 'grid = [0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2]' in reread
    print(f"peer013 runtime fix applied: {before} -> {after}")


if __name__ == "__main__":
    main()
