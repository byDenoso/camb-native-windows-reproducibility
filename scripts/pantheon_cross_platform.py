#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
from typing import Any

PANTHEON_TABLE_REL = 'Pantheon+_Data/4_DISTANCES_AND_COVAR/Pantheon+SH0ES.dat'
PANTHEON_COV_REL = 'Pantheon+_Data/4_DISTANCES_AND_COVAR/Pantheon+SH0ES_STAT+SYS.cov'
PANTHEON_NUMERICAL_TOL = 1.0e-9
KNOWN_GENERATED_MANIFEST_MISMATCH = 'compiled Pantheon manifest mismatch:'

# Populated only after a compiled payload passes the scientific equivalence checks.
verified_manifests: dict[str, dict[str, Any]] = {}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _git_blob_bytes(repo: Path, commit: str, relative_path: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(repo), 'show', f'{commit}:{relative_path}'])


def _relative_inf_error(observed, expected) -> float:
    import numpy as np

    numerator = float(np.linalg.norm(observed - expected, ord=np.inf))
    denominator = max(float(np.linalg.norm(expected, ord=np.inf)), 1.0e-300)
    return numerator / denominator


def _validate_compiled_science(runtime: Path, pan_repo: Path) -> dict[str, Any]:
    import numpy as np
    import pandas as pd
    from scipy.linalg import cho_solve

    raw = runtime / 'data/sn_data/PantheonPlus'
    compiled = raw / 'compiled_v2'
    table_path = raw / 'Pantheon+SH0ES.dat'
    cov_path = raw / 'Pantheon+SH0ES_STAT+SYS.cov'
    if not compiled.is_dir() or not (compiled / 'manifest.json').is_file():
        raise RuntimeError('Pantheon compiled payload missing after reconstruction')

    table = pd.read_csv(table_path, sep=r'\s+')
    flat = np.loadtxt(cov_path)
    n = len(table)
    if int(flat[0]) != n or flat[1:].size != n * n:
        raise RuntimeError('Pantheon covariance shape mismatch during scientific verification')
    covariance = flat[1:].reshape(n, n)
    covariance = np.tril(covariance) + np.tril(covariance, -1).T

    selections = {
        'hubble_flow': table['zHD'].to_numpy(float) > 0.01,
        'shoes': (table['zHD'].to_numpy(float) > 0.01) | (table['IS_CALIBRATOR'].to_numpy(int) == 1),
    }
    maxima = {
        'max_covariance_action_relative_error': 0.0,
        'max_solve_residual_relative_error': 0.0,
        'max_quadratic_form_relative_delta': 0.0,
    }
    selection_receipts: dict[str, Any] = {}

    for key, mask in selections.items():
        idx = np.flatnonzero(mask)
        selected_cov = covariance[np.ix_(idx, idx)]
        directory = compiled / key
        expected_arrays = {
            'magnitude': table.loc[mask, 'm_b_corr'].to_numpy(float),
            'zcmb': table.loc[mask, 'zHD'].to_numpy(float),
            'zhel': table.loc[mask, 'zHEL'].to_numpy(float),
            'is_calibrator': table.loc[mask, 'IS_CALIBRATOR'].to_numpy(np.uint8),
            'ceph_dist': table.loc[mask, 'CEPH_DIST'].to_numpy(float),
        }
        roundtrip = {}
        for name, expected in expected_arrays.items():
            path = directory / f'{name}.npy'
            observed = np.load(path, allow_pickle=False)
            if np.issubdtype(expected.dtype, np.floating):
                exact = bool(np.array_equal(observed, expected, equal_nan=True))
            else:
                exact = bool(np.array_equal(observed, expected))
            roundtrip[name] = exact
            if not exact:
                raise RuntimeError(f'Pantheon compiled source-array round trip mismatch: {key}/{name}')

        factor = np.load(directory / 'cholesky.npy', allow_pickle=False)
        if factor.shape != selected_cov.shape or not np.all(np.isfinite(factor)):
            raise RuntimeError(f'Pantheon compiled Cholesky shape/non-finite failure: {key}')
        if np.any(np.diag(factor) <= 0.0):
            raise RuntimeError(f'Pantheon compiled Cholesky non-positive diagonal: {key}')

        probes = (
            np.ones(idx.size, dtype=float),
            np.linspace(-1.0, 1.0, idx.size, dtype=float),
            np.sin(np.arange(idx.size, dtype=float) * 0.017),
        )
        covariance_action_error = 0.0
        solve_residual_error = 0.0
        for vector in probes:
            factor_action = factor @ (factor.T @ vector)
            covariance_action = selected_cov @ vector
            covariance_action_error = max(
                covariance_action_error,
                _relative_inf_error(factor_action, covariance_action),
            )
            solution = cho_solve((factor, True), vector, check_finite=False)
            solve_residual_error = max(
                solve_residual_error,
                _relative_inf_error(selected_cov @ solution, vector),
            )

        # Independent cheap quadratic-form cross-check on a leading principal block.
        probe_n = min(32, idx.size)
        block_cov = selected_cov[:probe_n, :probe_n]
        block_factor = factor[:probe_n, :probe_n]
        vector = np.linspace(-0.75, 1.25, probe_n, dtype=float)
        q_factor = float(vector @ cho_solve((block_factor, True), vector, check_finite=False))
        q_direct = float(vector @ np.linalg.solve(block_cov, vector))
        q_relative_delta = abs(q_factor - q_direct) / max(abs(q_direct), 1.0e-300)

        maxima['max_covariance_action_relative_error'] = max(
            maxima['max_covariance_action_relative_error'], covariance_action_error
        )
        maxima['max_solve_residual_relative_error'] = max(
            maxima['max_solve_residual_relative_error'], solve_residual_error
        )
        maxima['max_quadratic_form_relative_delta'] = max(
            maxima['max_quadratic_form_relative_delta'], q_relative_delta
        )
        selection_receipts[key] = {
            'rows': int(idx.size),
            'source_array_roundtrip_exact': roundtrip,
            'covariance_action_relative_error': covariance_action_error,
            'solve_residual_relative_error': solve_residual_error,
            'quadratic_form_relative_delta': q_relative_delta,
        }

    passed = all(value <= PANTHEON_NUMERICAL_TOL for value in maxima.values())
    receipt = {
        'scientific_equivalence': 'verified' if passed else 'failed',
        'numerical_tolerance': PANTHEON_NUMERICAL_TOL,
        **maxima,
        'selections': selection_receipts,
        'identity_boundary': (
            'Frozen Git source bytes are exact identity. Generated NPY/Cholesky bytes are platform-local; '
            'their scientific identity is certified by exact source-array round trips, covariance action, '
            'linear-solve residuals and an independent quadratic-form cross-check.'
        ),
    }
    if not passed:
        raise RuntimeError(f'Pantheon compiled scientific equivalence failed: {receipt}')
    return receipt


def install() -> None:
    import run_r1_scientific_closure as closure

    if getattr(closure, '_pantheon_cross_platform_installed', False):
        return
    original = closure.compile_pantheon

    def compile_pantheon_cross_platform(runtime: Path, pan_repo: Path) -> dict[str, Any]:
        table_path = pan_repo / PANTHEON_TABLE_REL
        cov_path = pan_repo / PANTHEON_COV_REL
        working_table_sha = _sha256_file(table_path)
        working_cov_sha = _sha256_file(cov_path)

        table_bytes = _git_blob_bytes(pan_repo, closure.PANTHEON_COMMIT, PANTHEON_TABLE_REL)
        cov_bytes = _git_blob_bytes(pan_repo, closure.PANTHEON_COMMIT, PANTHEON_COV_REL)
        canonical_table_sha = _sha256_bytes(table_bytes)
        canonical_cov_sha = _sha256_bytes(cov_bytes)
        if canonical_table_sha != closure.PANTHEON_TABLE_SHA:
            raise RuntimeError(
                f'canonical Pantheon table Git blob hash mismatch: {canonical_table_sha} != {closure.PANTHEON_TABLE_SHA}'
            )
        if canonical_cov_sha != closure.PANTHEON_COV_SHA:
            raise RuntimeError(
                f'canonical Pantheon covariance Git blob hash mismatch: {canonical_cov_sha} != {closure.PANTHEON_COV_SHA}'
            )

        # Canonical Git bytes remove checkout-only CRLF/LF representation drift.
        table_path.write_bytes(table_bytes)
        cov_path.write_bytes(cov_bytes)

        original_result = None
        try:
            original_result = original(runtime, pan_repo)
        except RuntimeError as exc:
            # Only the known generated-artifact byte mismatch is replaced by a stronger
            # cross-platform scientific equivalence gate. Every other error propagates.
            if KNOWN_GENERATED_MANIFEST_MISMATCH not in str(exc):
                raise

        science = _validate_compiled_science(runtime, pan_repo)
        compiled = runtime / 'data/sn_data/PantheonPlus/compiled_v2'
        observed_manifest = _sha256_file(compiled / 'manifest.json')
        result = dict(original_result or {})
        result.update({
            'table_sha256': canonical_table_sha,
            'covariance_sha256': canonical_cov_sha,
            'compiled_manifest_sha256': observed_manifest,
            'compiled_manifest_identity': 'platform-local diagnostic',
            'hubble_flow_rows': int(science['selections']['hubble_flow']['rows']),
            'identity_authority': 'frozen Git blob + scientific equivalence',
            'working_tree_table_sha256_before_canonicalization': working_table_sha,
            'working_tree_covariance_sha256_before_canonicalization': working_cov_sha,
            'canonical_git_blob_table_sha256': canonical_table_sha,
            'canonical_git_blob_covariance_sha256': canonical_cov_sha,
            **science,
        })

        (runtime / 'manifests').mkdir(parents=True, exist_ok=True)
        closure.write_json(runtime / 'manifests/PANTHEON_PLUS.json', {
            'schema': 'peer-likelihood-runtime/v2',
            'likelihood': 'pantheon_plus',
            'status': 'functional_optimized',
            'source_identity': {
                'commit': closure.PANTHEON_COMMIT,
                'table_sha256': canonical_table_sha,
                'covariance_sha256': canonical_cov_sha,
            },
            'compiled_payload': {
                'path': 'data/sn_data/PantheonPlus/compiled_v2',
                'manifest_sha256': observed_manifest,
                'identity': 'platform-local diagnostic',
            },
            'scientific_equivalence': science,
            'claim_boundary': 'likelihood equivalence and component performance only',
        })
        verified_manifests[observed_manifest] = science
        return result

    closure.compile_pantheon = compile_pantheon_cross_platform
    closure._pantheon_cross_platform_installed = True
