from pathlib import Path


def test_canonical_split_decoder_verifies_complete_frozen_source_archive():
    transport = Path('scripts/run_r1_robustness_v2.py').read_text(encoding='utf-8')
    assert 'archive-parts-v3.json' in transport
    assert 'archive_parts_v3' in transport
    assert '5add06fbc244116fbdf4415457a8609f061039853dfea3f571826e939b18ebd2' in transport
    assert 'raw_sha256' in transport
    assert 'encoded_sha256' in transport
    assert 'archive_sha256' in transport
    assert 'scientific harness file-set mismatch' in transport
    assert 'late_time_campaign_v5.py' in Path('r1_scientific_harness/source-manifest.json').read_text(encoding='utf-8')


def test_scientific_closure_installs_complete_decoder_and_config_compatibility():
    source = Path('scripts/run_r1_scientific_closure_v2.py').read_text(encoding='utf-8')
    assert 'decode_canonical_harness' in source
    assert "configs/paper_validation_v6.json" in source
    assert "paper_validation_v6.json" in source
    assert 'closure.decode_harness = decode_complete_harness' in source
