from pathlib import Path


def test_pantheon_compilation_uses_scientific_equivalence_not_cross_os_byte_identity():
    source = Path("scripts/run_r1_scientific_closure.py").read_text(encoding="utf-8")

    # Frozen source bytes remain fail-closed authority.
    assert 'PANTHEON_TABLE_SHA = "1cb0fc379ef066afdc2ffd1857681cc478024570d8a3eba284fb645775198cf8"' in source
    assert 'PANTHEON_COV_SHA = "abf806d966485e64afdb359c87bffc0ecc00d05eff0a31ced66f247385df0fdc"' in source
    assert 'Pantheon table hash mismatch' in source
    assert 'Pantheon covariance hash mismatch' in source

    # Generated NPY/Cholesky bytes are platform-local artifacts, not cross-OS scientific identity.
    assert 'compiled Pantheon manifest mismatch' not in source
    assert 'expected_compiled_manifest = "01f86af61eb59ef3125b7a8f1acfb5a01eeddee8335e1f919f570ada4731adb5"' not in source

    # Compilation must prove the generated factor represents the frozen covariance scientifically.
    assert 'PANTHEON_NUMERICAL_TOL' in source
    assert 'max_covariance_reconstruction_abs' in source
    assert 'max_quadratic_form_abs_delta' in source
    assert 'scientific_equivalence' in source
    assert 'Pantheon compiled scientific equivalence failed' in source


def test_r15_requires_rebuild_determinism_and_scientific_equivalence():
    source = Path("scripts/run_r1_robustness.py").read_text(encoding="utf-8")
    assert "scientific_equivalence" in source
    assert "compiled_manifest_sha256" in source
    assert "same_platform_manifest_deterministic" in source
