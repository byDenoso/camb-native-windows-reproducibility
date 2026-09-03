from pathlib import Path


def test_robustness_preserves_camb_compatible_numeric_runtime():
    workflow = Path('.github/workflows/r1-robustness.yml').read_text(encoding='utf-8')
    # run_r1_core.ps1 materializes the CAMB-compatible stack before the
    # adversarial replay. Robustness must not overwrite it with the separate
    # historical scientific-closure stack. The workflow verifies the preserved
    # versions explicitly rather than reinstalling them.
    assert "numpy.__version__=='2.4.4'" in workflow
    assert "scipy.__version__=='1.17.1'" in workflow
    assert "pandas.__version__=='3.0.5'" in workflow
    assert "psutil.__version__=='7.0.0'" in workflow
    assert 'numpy==2.5.1 scipy==1.18.0' not in workflow
