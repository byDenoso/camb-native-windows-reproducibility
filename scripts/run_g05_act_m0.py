#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
from pathlib import Path

import numpy as np

ACT_COMMIT = '627aeafb88ae5ad1aa66b406bea2d65cfa66a27d'
HISTORICAL_LOGL = -395.4831594065799
OFFICIAL_TEST_TOLERANCE = 1.0e-2


def package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return 'not-installed'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--act-repo', type=Path, required=True)
    ap.add_argument('--receipt', type=Path, required=True)
    args = ap.parse_args()

    from cobaya.install import install
    from cobaya.model import get_model
    import camb

    info = {
        'params': {
            'ombh2': 0.022,
            'omch2': 0.117,
            'ns': 0.96,
            'As': 2e-9,
            'tau': 0.065,
            'cosmomc_theta': 104.09e-4,
        },
        'theory': {
            'camb': {
                'path': 'global',
                'extra_args': {
                    'lmax': 9000,
                    'lens_potential_accuracy': 8,
                    'min_l_logl_sampling': 6000,
                },
            }
        },
        'likelihood': {
            'act_dr6_cmbonly': {
                'stop_at_error': True,
                'input_file': 'dr6_data_cmbonly.fits',
                'params': {'A_act': 1.0, 'P_act': 1.0},
            }
        },
        'sampler': {'evaluate': None},
        'debug': False,
    }

    # Install/check only the likelihood payload. Installing the full model here would let
    # Cobaya materialize an unpinned CAMB checkout and shadow the registered wheel.
    install({'likelihood': info['likelihood']})

    model = get_model(info)
    values = model.loglikes()[0]
    observed = float(np.sum(values))
    delta = abs(observed - HISTORICAL_LOGL)
    passed = bool(np.isfinite(observed) and delta <= OFFICIAL_TEST_TOLERANCE)

    payload = {
        'gate_id': 'G05',
        'status': 'verified' if passed else 'failed',
        'schema': 'ascom-00323-g05-act-official-fixed-point/v3',
        'authority': {
            'repository': 'ACTCollaboration/DR6-ACT-lite',
            'commit': ACT_COMMIT,
            'upstream_test': 'act_dr6_cmbonly/tests/test_act.py::test_TTTEEE',
            'historical_receipt': 'PEER_CLOSURE_EXECUTION_20260729_v2.md',
        },
        'configuration': info['params'],
        'camb_extra_args': info['theory']['camb']['extra_args'],
        'runtime': {
            'camb_path_policy': info['theory']['camb']['path'],
            'camb_version': getattr(camb, '__version__', 'unknown'),
            'camb_module': str(Path(camb.__file__).resolve()),
            'cobaya_version': package_version('cobaya'),
            'sacc_version': package_version('sacc'),
            'numpy_version': package_version('numpy'),
            'scipy_version': package_version('scipy'),
        },
        'observed_loglike': observed,
        'historical_reference_loglike': HISTORICAL_LOGL,
        'absolute_delta_loglike': delta,
        'acceptance_tolerance': OFFICIAL_TEST_TOLERANCE,
        'chi2_equivalent': float(-2.0 * observed),
        'claim_boundary': (
            'Fresh native-Windows reproduction of the registered ACT DR6 null fixed point '
            'with the official global CAMB wheel. Planck low-l and DESI payload identities '
            'are verified independently under G04 and are not numerically summed into this ACT score.'
        ),
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
