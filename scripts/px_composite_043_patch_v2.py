from __future__ import annotations

import re
import sys
from pathlib import Path

from px_composite_043_patch import patch_texts as patch_texts_v1


def fix_generated_fortran_state_refs(text: str) -> str:
    fixed, count = re.subn(r"(?<!this%)State%grhov", "this%State%grhov", text)
    if count != 4:
        raise RuntimeError(f"T-043 state-reference fix expected 4 replacements, found {count}")
    return fixed


def fix_generated_fortran_kind_shadow(text: str) -> str:
    replacements = (
        (
            "real(dl) :: phi, phidot, de, ve, dl, vl, Hv3_over_k, one_plus_w",
            "real(dl) :: phi, phidot, de, ve, dlate, vl, Hv3_over_k, one_plus_w",
            "late perturbation declaration",
        ),
        ("    dl = y(w_ix+2)", "    dlate = y(w_ix+2)", "late perturbation assignment"),
        (
            "*(dl + one_plus_w*Hv3_over_k)",
            "*(dlate + one_plus_w*Hv3_over_k)",
            "late perturbation rest-frame density",
        ),
        (
            "k*this%late_cs2*dl/one_plus_w",
            "k*this%late_cs2*dlate/one_plus_w",
            "late perturbation pressure-gradient term",
        ),
    )
    fixed = text
    for old, new, label in replacements:
        count = fixed.count(old)
        if count != 1:
            raise RuntimeError(f"T-043 kind-shadow fix for {label} expected 1 replacement, found {count}")
        fixed = fixed.replace(old, new, 1)
    return fixed


def patch_texts(f90: str, py: str, camb: str) -> tuple[str, str, str]:
    out_f90, out_py, out_camb = patch_texts_v1(f90, py, camb)
    out_f90 = fix_generated_fortran_state_refs(out_f90)
    out_f90 = fix_generated_fortran_kind_shadow(out_f90)
    return out_f90, out_py, out_camb


def patch(root: Path) -> None:
    f90_path = root / "fortran" / "DarkEnergyQuintessence.f90"
    py_path = root / "camb" / "dark_energy.py"
    camb_path = root / "fortran" / "camb.f90"
    f90, py, camb = patch_texts(f90_path.read_text(), py_path.read_text(), camb_path.read_text())
    f90_path.write_text(f90)
    py_path.write_text(py)
    camb_path.write_text(camb)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: px_composite_043_patch_v2.py /path/to/CAMB")
    patch(Path(sys.argv[1]).resolve())
