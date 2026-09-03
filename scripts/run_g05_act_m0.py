#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from cobaya.install import install
from cobaya.model import get_model

ACT_COMMIT = '627aeafb88ae5ad1aa66b406bea2d65cfa66a27d'
HISTORICAL_LOGL = -395.4831594065799
OFFICIAL_TEST_TOLERANCE = 1e-2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--act-repo', type=Path, required=True)
    ap.add_argument('--receipt', type=Path, required=True)
    args = ap.parse_args()
    repo = args.act_repo.resolve()
    sys.path.insert(0, str(repo))

    info = {
        'params': {
            'ombh2': 0.022,
            'omch2': 0.117,
            'ns': 0.96,
            'As': 2e-9,
            'tau': 0.065,
            'cosmomc_theta': 104.09e-4,
        },
        'theory': {'camb': {'extra_args': {
            'lmax': 9000,
            'lens_potential_accuracy': 8,
            'min_l_logl_sampling': 6000,
        }}},
        'likelihood': {
            'act_dr6_cmbonly': {
                'stop_at_error': True,
                'input_file': 'dr6_data_cmbonly.fits',
                'params': {'A_act': 1.0, 'P_act': 1.0},
            }
        },
        'sampler': {'evaluate': None},
    }
    install(info)
    model = get_model(info)
    values = model.loglikes()[0]
    observed = float(np.sum(values))
    delta = abs(observed - HISTORICAL_LOGL)
    passed = bool(np.isfinite(observed) and delta <= OFFICIAL_TEST_TOLERANCE)
    payload = {
        'gate_id': 'G05',
        'status': 'verified' if passed else 'failed',
        'schema': 'ascom-00323-g05-act-official-fixed-point/v2',
        'authority': {
            'repository': 'ACTCollaboration/DR6-ACT-lite',
            'commit': ACT_COMMIT,
            'upstream_test': 'act_dr6_cmbonly/tests/test_act.py::test_TTTEEE',
        },
        'configuration': info['params'],
        'camb_extra_args': info['theory']['camb']['extra_args'],
        'observed_loglike': observed,
        'historical_reference_loglike': HISTORICAL_LOGL,
        'absolute_delta_loglike': delta,
        'acceptance_tolerance': OFFICIAL_TEST_TOLERANCE,
        'chi2_equivalent': float(-2.0 * observed),
        'claim_boundary': 'Fresh native-Windows reproduction of the frozen official ACT DR6 CMB-only fixed point. Planck low-l and DESI identities are verified separately under G04; they are not summed into this ACT-only reference value.',
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
