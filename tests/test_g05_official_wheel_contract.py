from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_g05_act_m0.py"


def test_g05_forces_registered_global_camb_wheel():
    source = RUNNER.read_text(encoding="utf-8")
    assert "'path': 'global'" in source or '"path": "global"' in source


def test_g05_does_not_auto_install_theory_from_unpinned_upstream():
    source = RUNNER.read_text(encoding="utf-8")
    assert "install(info)" not in source
