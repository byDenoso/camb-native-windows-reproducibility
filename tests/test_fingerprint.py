from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from native_windows_camb.fingerprint import scientific_fingerprint


def test_fingerprint_is_order_independent_for_mapping_keys():
    a = scientific_fingerprint({"solver": "CAMB", "precision": {"lmax": 3000, "kmax": 10.0}})
    b = scientific_fingerprint({"precision": {"kmax": 10.0, "lmax": 3000}, "solver": "CAMB"})
    assert a == b


def test_fingerprint_changes_when_precision_changes():
    a = scientific_fingerprint({"solver": "CAMB", "lmax": 3000})
    b = scientific_fingerprint({"solver": "CAMB", "lmax": 3001})
    assert a != b
