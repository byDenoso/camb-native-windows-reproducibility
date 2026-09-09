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


def patch_texts(f90: str, py: str, camb: str) -> tuple[str, str, str]:
    out_f90, out_py, out_camb = patch_texts_v1(f90, py, camb)
    return fix_generated_fortran_state_refs(out_f90), out_py, out_camb


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
