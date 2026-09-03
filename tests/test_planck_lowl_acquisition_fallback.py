from pathlib import Path


def test_planck_lowl_workflow_has_official_irsa_discovery_and_fail_closed_fingerprint():
    source = Path('.github/workflows/r1-planck-lowl-identity.yml').read_text(encoding='utf-8')
    assert 'https://irsa.ipac.caltech.edu/data/Planck/release_3/software/' in source
    assert 'COM_Likelihood_Data-baseline_R3.00.tar.gz' in source
    assert 'https://pla.esac.esa.int/' in source
    # Frozen official PR3 baseline archive observed from IRSA on 2026-09-03.
    assert "'archive_sha256':'0b73171e3acc671c28184466a45485a2d1c1d93676b832abdfe688c7b04024e6'" in source
    # low_l only. 391768... is a different full-high-l payload tree and must never be reused here.
    assert "'file_count':29" in source
    assert "'total_bytes':8819443" in source
    assert "'tree_sha256':'fd9f703d1d8223760089bed8d7c0de1bfa0a06a6085c5a348aa875c959c6567c'" in source
    assert '391768a25928ba2ecedb585f64464fbbf1f623bddfb57e0f3106b7b8c4ea12c0' not in source
    assert "report['status']='verified'" in source
