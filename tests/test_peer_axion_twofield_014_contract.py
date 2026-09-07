from pathlib import Path


def test_014_runner_materializes_frozen_common_background_recalibration_contract():
    path = Path("scripts/run_peer_axion_twofield_014.py")
    assert path.exists(), "014 runner is not implemented yet"
    text = path.read_text()
    assert 'TEST_ID = "T-DE26-PEER-PNGB-AXION-NATIVE-2FIELD-RECAL-014"' in text
    assert 'FDE_TARGET = 0.088' in text
    assert 'LOG10_ZC_TARGET = 3.81' in text
    assert 'CAL_F_TOL = 1e-5' in text
    assert 'CAL_LOGZ_TOL = 1e-4' in text
    assert 'LOCAL_FACTOR = 2.0' in text
    assert 'def calibrate_common_background' in text
    assert 'root(' in text
    assert 'math.log(f)' in text or 'np.log(f)' in text
    assert 'tune_late_amp' in text
    assert 'late_f=1.0' in text
    assert 'late_theta_i=math.pi - 0.8' in text
    assert 'frac_lambda0=1.0' in text
    assert 'G4' in text and 'G7' in text and 'G8' in text
