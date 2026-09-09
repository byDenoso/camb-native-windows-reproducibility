from __future__ import annotations

from px_composite_043_patch import patch_texts


def test_patch_adds_peer_px_fluid_to_post_013_camb_sources() -> None:
    f90 = (
        "    end type TPeerAxionTwoField\n"
        "    public TQuintessence, TEarlyQuintessence, TDeformedEarlyQuintessence, TPeerAxionTwoField\n"
        "    function TDeformedEarlyQuintessence_PythonClass()\n"
    )
    py = "@fortran_class\nclass PeerAxionTwoField(EarlyQuintessence):\n    pass\n\n# short names for models that support w/wa\n"
    camb = (
        "    else if (DarkEneryModel == 'PEERAXIONTWOFIELD') then\n"
        "        allocate(TPeerAxionTwoField :: P%DarkEnergy)\n"
    )
    out_f90, out_py, out_camb = patch_texts(f90, py, camb)
    assert "type, extends(TEarlyQuintessence) :: TPeerPXFluid" in out_f90
    assert "procedure :: PerturbationEvolve => TPeerPXFluid_PerturbationEvolve" in out_f90
    assert "public TQuintessence, TEarlyQuintessence, TDeformedEarlyQuintessence, TPeerAxionTwoField, TPeerPXFluid" in out_f90
    assert "class PeerPXFluid(EarlyQuintessence):" in out_py
    assert "PEERPXFLUID" in out_camb
    assert "allocate(TPeerPXFluid :: P%DarkEnergy)" in out_camb
