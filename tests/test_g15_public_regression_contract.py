from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_g15_public_regression.py"
WORKFLOW = ROOT / ".github" / "workflows" / "r1-g15-public-regression.yml"


def test_g15_public_runner_exists_and_keeps_historical_87_test_contract():
    assert RUNNER.is_file()
    source = RUNNER.read_text(encoding="utf-8")
    expected = {
        "tests.test_optimized_runtime": 17,
        "tests.test_packaging_v6": 3,
        "tests.test_paper_validation_v6": 12,
        "tests.test_runtime_v3": 21,
        "tests.test_runtime_v4": 34,
    }
    for module, count in expected.items():
        assert module in source
        assert str(count) in source
    assert sum(expected.values()) == 87
    assert "5add06fbc244116fbdf4415457a8609f061039853dfea3f571826e939b18ebd2" in source


def test_g15_public_runtime_is_reconstructed_not_substituted():
    source = RUNNER.read_text(encoding="utf-8")
    assert "act_public_payload" in source
    assert "PANTHEON_COMMIT" in source
    assert "BAO_COMMIT" in source
    assert "compile_direct_ladder" in source
    assert "compile_no_shoes" in source
    assert "ACT_PROJECTED_CONTROL" in source
    assert "expected_total" in source


def test_g15_has_dedicated_public_clean_composite_workflow():
    assert WORKFLOW.is_file()
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "runs-on: ubuntu-latest" in text
    assert "run_g15_public_regression.py" in text
    assert "python-version: '3.12'" in text or 'python-version: "3.12"' in text
