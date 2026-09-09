from __future__ import annotations

import re

from px_composite_043_patch_v2 import (
    fix_generated_fortran_kind_shadow,
    fix_generated_fortran_state_refs,
)


def test_statefix_uses_persisted_camb_state_pointer_for_grhov() -> None:
    source = (
        "if (State%grhov <= 0._dl) then\n"
        "if (early_today >= State%grhov) then\n"
        "this%late_grhov0 = State%grhov - early_today\n"
        "this%late_frac0 = this%late_grhov0 / State%grhov\n"
    )
    fixed = fix_generated_fortran_state_refs(source)
    assert re.search(r"(?<!this%)State%grhov", fixed) is None
    assert fixed.count("this%State%grhov") == 4


def test_kindfix_renames_late_density_perturbation_without_shadowing_dl_kind() -> None:
    source = (
        "    real(dl) :: phi, phidot, de, ve, dl, vl, Hv3_over_k, one_plus_w\n"
        "    dl = y(w_ix+2)\n"
        "        ayprime(w_ix+1) = -2._dl*adotoa*ve\n"
        "            *(dl + one_plus_w*Hv3_over_k)\n"
        "            + k*this%late_cs2*dl/one_plus_w\n"
        "        ayprime(w_ix) = 0._dl\n"
    )
    fixed = fix_generated_fortran_kind_shadow(source)
    assert ", dl, vl," not in fixed
    assert fixed.count("dlate") == 4
    assert fixed.count("_dl") == 2
    assert "real(dl)" in fixed
