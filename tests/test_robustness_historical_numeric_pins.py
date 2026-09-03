from pathlib import Path


def test_robustness_replays_historical_numeric_runtime_pins():
    workflow = Path('.github/workflows/r1-robustness.yml').read_text(encoding='utf-8')
    assert 'numpy==2.5.1' in workflow
    assert 'scipy==1.18.0' in workflow
    assert 'pandas==3.0.5' in workflow
    assert 'psutil==7.0.0' in workflow
