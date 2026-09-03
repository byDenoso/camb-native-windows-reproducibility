from pathlib import Path


def test_planck_lowl_workflow_has_official_irsa_discovery_and_fail_closed_fingerprint():
    source = Path('.github/workflows/r1-planck-lowl-identity.yml').read_text(encoding='utf-8')
    assert 'https://irsa.ipac.caltech.edu/data/Planck/release_3/software/' in source
    assert 'COM_Likelihood_Data-baseline_R3.00.tar.gz' in source
    assert 'https://pla.esac.esa.int/' in source
    assert "'file_count':72" in source
    assert "'total_bytes':17321811" in source
    assert "'tree_sha256':'391768a25928ba2ecedb585f64464fbbf1f623bddfb57e0f3106b7b8c4ea12c0'" in source
    assert "report['status']='verified'" in source
