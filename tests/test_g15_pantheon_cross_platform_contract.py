from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_g15_regression.py"


def test_g15_installs_registered_pantheon_cross_platform_gate_before_runtime_build():
    source = RUNNER.read_text(encoding="utf-8")
    assert "import pantheon_cross_platform" in source
    assert "pantheon_cross_platform.install()" in source
    assert source.index("pantheon_cross_platform.install()") < source.index("closure.build_runtime")
