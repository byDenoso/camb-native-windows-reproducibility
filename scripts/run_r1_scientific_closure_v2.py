#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from windows_fcntl_compat import install_fcntl_compat

install_fcntl_compat()

import pantheon_cross_platform
import run_r1_robustness_v2 as canonical_transport
import run_r1_scientific_closure as closure


def decode_complete_harness(repo: Path, work: Path) -> Path:
    root, _archive = canonical_transport.decode_canonical_harness(repo, work)
    canonical_config = root / 'configs/paper_validation_v6.json'
    compatibility_config = root / 'paper_validation_v6.json'
    if not canonical_config.is_file():
        raise RuntimeError('complete scientific archive missing configs/paper_validation_v6.json')
    compatibility_config.write_bytes(canonical_config.read_bytes())
    return root


closure.decode_harness = decode_complete_harness


if __name__ == '__main__':
    pantheon_cross_platform.install()
    raise SystemExit(closure.main())
