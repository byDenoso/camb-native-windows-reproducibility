#!/usr/bin/env python3
from __future__ import annotations

# Import v2 for canonical split-harness transport and R01 receipt hardening.
import run_r1_robustness_v2  # noqa: F401
import run_r1_robustness as legacy
import pantheon_cross_platform


_previous_receipt = legacy.receipt


def receipt(gate: str, passed: bool, observed: dict):
    if gate == 'R15':
        observed = dict(observed)
        hashes = [observed.get('initial'), observed.get('rebuild_a'), observed.get('rebuild_b')]
        deterministic = bool(passed and len(set(hashes)) == 1 and None not in hashes)
        science_verified = bool(
            hashes
            and all(
                value in pantheon_cross_platform.verified_manifests
                and pantheon_cross_platform.verified_manifests[value].get('scientific_equivalence') == 'verified'
                for value in hashes
            )
        )
        observed['same_platform_manifest_deterministic'] = deterministic
        observed['scientific_equivalence'] = 'verified' if science_verified else 'failed'
        observed['verified_manifests'] = sorted(pantheon_cross_platform.verified_manifests)
        passed = deterministic and science_verified
    return _previous_receipt(gate, passed, observed)


legacy.receipt = receipt


if __name__ == '__main__':
    pantheon_cross_platform.install()
    raise SystemExit(legacy.main())
