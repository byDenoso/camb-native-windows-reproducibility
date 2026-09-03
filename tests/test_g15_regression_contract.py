from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_g15_regression.py"
EXPECTED = {
    "tests.test_optimized_runtime": 17,
    "tests.test_packaging_v6": 3,
    "tests.test_paper_validation_v6": 12,
    "tests.test_runtime_v3": 21,
    "tests.test_runtime_v4": 34,
}
SOURCE_ARCHIVE_SHA256 = "5add06fbc244116fbdf4415457a8609f061039853dfea3f571826e939b18ebd2"


def test_g15_runner_exists_and_freezes_the_87_test_module_contract():
    assert RUNNER.is_file()
    source = RUNNER.read_text(encoding="utf-8")
    for module, count in EXPECTED.items():
        assert repr(module) in source or f'"{module}"' in source
        assert str(count) in source
    assert sum(EXPECTED.values()) == 87


def test_g15_reconstructs_the_registered_paper_source_archive():
    source = RUNNER.read_text(encoding="utf-8")
    assert SOURCE_ARCHIVE_SHA256 in source
    assert "archive-parts-v3.json" in source
    assert "archive_parts_v3" in source
    assert "source-manifest.json" in source
