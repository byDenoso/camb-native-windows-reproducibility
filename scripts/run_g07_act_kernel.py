#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time

import camb
import numpy as np

from act_raw_likelihood_r1 import ACTCMBOnlyRaw

EXPECTED_PAYLOAD_SHA = 'd3ca3ff9427ecb22141df32fb6b4398d3f9a3dcb1a10d22344b33c56a12b6484'
OBJECTIVE_TOL = 1e-9
MODEL_TOL = 1e-6


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_cls() -> dict[str, np.ndarray]:
    pars = camb.CAMBparams()
    pars.set_cosmology(ombh2=0.022, omch2=0.117, cosmomc_theta=104.09e-4, tau=0.065)
    pars.InitPower.set_params(As=2e-9, ns=0.96)
    pars.set_for_lmax(9000, lens_potential_accuracy=8)
    pars.set_accuracy(min_l_logl_sampling=6000)
    results = camb.get_results(pars)
    powers = results.get_total_cls(lmax=9000, CMB_unit='muK', raw_cl=False)
    return {'tt': powers[:, 0], 'ee': powers[:, 1], 'te': powers[:, 3]}


def measure(callback, repeats: int = 5):
    samples = []
    result = None
    for _ in range(repeats):
        start = time.perf_counter(); result = callback(); samples.append(time.perf_counter() - start)
    return result, float(statistics.median(samples)), samples


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--payload', type=Path, required=True)
    ap.add_argument('--receipt', type=Path, required=True)
    args = ap.parse_args()
    observed_sha = sha256(args.payload)
    if observed_sha != EXPECTED_PAYLOAD_SHA:
        raise RuntimeError(f'ACT payload hash mismatch: {observed_sha}')
    cls = build_cls()
    like = ACTCMBOnlyRaw(args.payload)
    like.fit_nuisance_direct(cls); like.fit_nuisance(cls)
    direct, direct_median, direct_samples = measure(lambda: like.fit_nuisance_direct(cls))
    optimized, optimized_median, optimized_samples = measure(lambda: like.fit_nuisance(cls))
    objective_delta = abs(direct.objective - optimized.objective)
    chi2_delta = abs(direct.chi2_ACT - optimized.chi2_ACT)
    prior_delta = abs(direct.chi2_calibration_prior - optimized.chi2_calibration_prior)
    model_delta = float(np.max(np.abs(direct.model_vector - optimized.model_vector)))
    passed = objective_delta <= OBJECTIVE_TOL and model_delta <= MODEL_TOL
    payload = {
        'gate_id': 'G07', 'status': 'verified' if passed else 'failed',
        'schema': 'ascom-00323-g07-act-kernel-parity/v3',
        'source_payload_sha256': observed_sha,
        'camb_version': camb.__version__,
        'workload': 'fresh native-Windows LambdaCDM spectra at the frozen official ACT test cosmology',
        'direct_objective': float(direct.objective), 'optimized_objective': float(optimized.objective),
        'objective_absolute_delta': float(objective_delta),
        'chi2_component_absolute_delta_diagnostic': float(chi2_delta),
        'calibration_prior_absolute_delta_diagnostic': float(prior_delta),
        'model_vector_max_absolute_delta': model_delta,
        'direct_median_seconds': direct_median, 'optimized_median_seconds': optimized_median,
        'measured_speedup': float(direct_median / optimized_median),
        'direct_samples_seconds': direct_samples, 'optimized_samples_seconds': optimized_samples,
        'acceptance': {'total_objective_tolerance': OBJECTIVE_TOL, 'model_vector_tolerance': MODEL_TOL},
        'historical_lineage': {'objective_delta': 1.4210854715202004e-13, 'component_speedup': 5.565937111326581},
        'claim_boundary': 'Fresh test certifies equality of the minimized total ACT objective and projected model vector on official payload bytes. The ACT chi2 and calibration-prior terms are retained as diagnostics because tiny nuisance-coordinate differences can redistribute between those terms while the total objective remains invariant.',
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == '__main__': raise SystemExit(main())
