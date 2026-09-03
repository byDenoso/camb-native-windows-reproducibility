from pathlib import Path


def test_pantheon_cross_platform_layer_preserves_source_identity_and_numeric_contract():
    historical = Path("scripts/run_r1_scientific_closure.py").read_text(encoding="utf-8")
    compat = Path("scripts/pantheon_cross_platform.py").read_text(encoding="utf-8")

    # Frozen source bytes remain fail-closed authority in the recovered executor.
    assert 'PANTHEON_TABLE_SHA = "1cb0fc379ef066afdc2ffd1857681cc478024570d8a3eba284fb645775198cf8"' in historical
    assert 'PANTHEON_COV_SHA = "abf806d966485e64afdb359c87bffc0ecc00d05eff0a31ced66f247385df0fdc"' in historical
    assert 'Pantheon table hash mismatch' in historical
    assert 'Pantheon covariance hash mismatch' in historical

    # The active compatibility layer may intercept only the known generated-manifest mismatch.
    assert 'compiled Pantheon manifest mismatch:' in compat
    assert 'canonical Pantheon table Git blob hash mismatch' in compat
    assert 'canonical Pantheon covariance Git blob hash mismatch' in compat
    assert 'PANTHEON_NUMERICAL_TOL' in compat
    assert 'max_covariance_action_relative_error' in compat
    assert 'max_solve_residual_relative_error' in compat
    assert 'max_quadratic_form_relative_delta' in compat
    assert 'scientific_equivalence' in compat
    assert 'Pantheon compiled scientific equivalence failed' in compat


def test_active_windows_workflows_separate_historical_closure_and_camb_robustness_stacks():
    robust = Path(".github/workflows/r1-robustness.yml").read_text(encoding="utf-8")
    closure = Path(".github/workflows/r1-scientific-closure.yml").read_text(encoding="utf-8")
    assert "scripts\\run_r1_robustness_v3.py" in robust
    assert "scripts\\run_r1_scientific_closure_v2.py" in closure

    # Scientific closure certifies the historical numerical stack used for the paper.
    assert "numpy==2.5.1 scipy==1.18.0 pandas==3.0.5" in closure

    # Robustness includes fresh CAMB subprocess probes; it must preserve the CAMB-compatible
    # stack materialized by run_r1_core.ps1 rather than overwrite it with closure-only pins.
    assert "numpy.__version__=='2.4.4'" in robust
    assert "scipy.__version__=='1.17.1'" in robust
    assert "pandas.__version__=='3.0.5'" in robust
    assert "numpy==2.5.1 scipy==1.18.0 pandas==3.0.5" not in robust


def test_r15_requires_same_platform_determinism_and_scientific_equivalence():
    source = Path("scripts/run_r1_robustness_v3.py").read_text(encoding="utf-8")
    assert "same_platform_manifest_deterministic" in source
    assert "scientific_equivalence" in source
    assert "verified_manifests" in source
