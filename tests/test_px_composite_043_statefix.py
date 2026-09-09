from __future__ import annotations

import re

from px_composite_043_patch_v2 import fix_generated_fortran_state_refs


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
