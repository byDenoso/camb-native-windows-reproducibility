from pathlib import Path


def test_planck_paper_payload_workflow_has_official_discovery_and_frozen_fail_closed_fingerprint():
    source = Path('.github/workflows/r1-planck-lowl-identity.yml').read_text(encoding='utf-8')
    assert 'https://irsa.ipac.caltech.edu/data/Planck/release_3/software/' in source
    assert 'COM_Likelihood_Data-baseline_R3.00.tar.gz' in source
    assert 'https://pla.esac.esa.int/' in source
    # Frozen official PR3 baseline archive observed from IRSA on 2026-09-03.
    assert "'archive_sha256':'0b73171e3acc671c28184466a45485a2d1c1d93676b832abdfe688c7b04024e6'" in source
    # Frozen paper/runtime contract from 2026-08-04: PlikLite + lensing + lowT + lowE
    # plus the official baseline README at the root of share/planck.
    # Do not replace this with the later low_l-only 29-file subset.
    assert "'file_count':72" in source
    assert "'total_bytes':17321811" in source
    assert "'tree_sha256':'391768a25928ba2ecedb585f64464fbbf1f623bddfb57e0f3106b7b8c4ea12c0'" in source
    assert 'readme_baseline.md' in source
    assert 'plik_lite' in source
    assert 'lensing' in source
    assert 'low_l' in source
    assert "report['status']='verified'" in source
