import os
from pathlib import Path


def _camb_root() -> Path:
    root = os.environ.get("CAMB_SOURCE")
    assert root, "CAMB_SOURCE must point to the checked-out CAMB 1.6.6 source tree"
    return Path(root)


def test_native_two_field_class_is_registered():
    root = _camb_root()
    f90 = (root / "fortran" / "DarkEnergyQuintessence.f90").read_text()
    py = (root / "camb" / "dark_energy.py").read_text()
    camb_f90 = (root / "fortran" / "camb.f90").read_text()

    assert "type, extends(TEarlyQuintessence) :: TPeerAxionTwoField" in f90
    assert "TPeerAxionTwoField_PerturbationEvolve" in f90
    assert "TPeerAxionTwoField_PerturbedStressEnergy" in f90
    assert "this%num_perturb_equations = 4" in f90
    assert "late_phi_a" in f90 and "late_phidot_a" in f90
    assert "class PeerAxionTwoField(EarlyQuintessence):" in py
    assert "PEERAXIONTWOFIELD" in camb_f90
    assert "allocate(TPeerAxionTwoField :: P%DarkEnergy)" in camb_f90


def test_active_model_has_no_lambda_offset():
    root = _camb_root()
    f90 = (root / "fortran" / "DarkEnergyQuintessence.f90").read_text()
    start = f90.index("function TPeerAxionTwoField_EarlyVofPhi")
    end = f90.index("end function TPeerAxionTwoField_EarlyVofPhi", start)
    block = f90[start:end]
    assert "State%grhov" not in block
    assert "frac_lambda0" not in block


def test_two_native_scalar_perturbation_pairs_are_evolved():
    root = _camb_root()
    f90 = (root / "fortran" / "DarkEnergyQuintessence.f90").read_text()
    start = f90.index("subroutine TPeerAxionTwoField_PerturbationEvolve")
    end = f90.index("end subroutine TPeerAxionTwoField_PerturbationEvolve", start)
    block = f90[start:end]
    for token in ("w_ix", "w_ix+1", "w_ix+2", "w_ix+3", "EarlyVofPhi", "LateVofPhi"):
        assert token in block
