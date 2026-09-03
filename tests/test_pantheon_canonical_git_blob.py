from pathlib import Path


def test_pantheon_materialization_uses_canonical_git_blob_bytes():
    source = Path("scripts/run_r1_scientific_closure.py").read_text(encoding="utf-8")
    assert "def git_blob_bytes(" in source
    compile_section = source.split("def compile_pantheon", 1)[1].split("def build_runtime", 1)[0]
    assert "git_blob_bytes(pan_repo, PANTHEON_COMMIT" in compile_section
    assert "table_path.write_bytes(table_bytes)" in compile_section
    assert "cov_path.write_bytes(cov_bytes)" in compile_section
    assert "working_tree_table_sha256" in compile_section
    assert "working_tree_covariance_sha256" in compile_section
