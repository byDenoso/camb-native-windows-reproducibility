from __future__ import annotations

import hashlib

from acquire_act_dr6_043 import ACT_SOURCE_URL, find_verified_fits


def test_act_source_url_is_official_frozen_lambda_payload() -> None:
    assert ACT_SOURCE_URL == (
        "https://lambda.gsfc.nasa.gov/data/act/pspipe/sacc_files/"
        "dr6_data_cmbonly.tar.gz"
    )


def test_find_verified_fits_selects_only_matching_payload(tmp_path) -> None:
    bad = tmp_path / "bad.fits"
    good = tmp_path / "v1.0" / "dr6_data_cmbonly.fits"
    good.parent.mkdir()
    bad.write_bytes(b"wrong")
    good.write_bytes(b"official-payload-fixture")
    expected = hashlib.sha256(good.read_bytes()).hexdigest()
    assert find_verified_fits(tmp_path, expected) == good
