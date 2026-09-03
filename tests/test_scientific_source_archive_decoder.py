from pathlib import Path


def test_scientific_decoder_uses_complete_frozen_source_archive_parts():
    source = Path('scripts/run_r1_scientific_closure.py').read_text(encoding='utf-8')
    assert 'archive-parts-v3.json' in source
    assert 'archive_parts_v3' in source
    assert '5add06fbc244116fbdf4415457a8609f061039853dfea3f571826e939b18ebd2' in source
    assert "raw_sha256" in source
    assert "encoded_sha256" in source
    assert "archive_sha256" in source
    assert "late_time_campaign_v5.py" in Path('r1_scientific_harness/source-manifest.json').read_text(encoding='utf-8')


def test_scientific_config_comes_from_complete_archive_layout():
    source = Path('scripts/run_r1_scientific_closure.py').read_text(encoding='utf-8')
    assert 'configs/paper_validation_v6.json' in source
