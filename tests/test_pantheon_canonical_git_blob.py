from pathlib import Path


def test_pantheon_materialization_uses_frozen_git_blob_authority():
    source = Path("scripts/run_r1_robustness_v2.py").read_text(encoding="utf-8")
    assert "def _install_pantheon_git_blob_materialization" in source
    assert "subprocess.check_output(['git', '-C'" in source
    assert "canonical Pantheon table Git blob hash mismatch" in source
    assert "canonical Pantheon covariance Git blob hash mismatch" in source
    assert "table_path.write_bytes(table_bytes)" in source
    assert "cov_path.write_bytes(cov_bytes)" in source
    assert "working_tree_table_sha256_before_canonicalization" in source
    assert "working_tree_covariance_sha256_before_canonicalization" in source
    assert "_install_pantheon_git_blob_materialization()" in source
