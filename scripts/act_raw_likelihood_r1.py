from __future__ import annotations

# Source lineage: PEER_ACT_LIKELIHOOD_OPT_20260802.tar.zst (2026-08-02),
# act_raw_likelihood.py. This copy is used only for fresh ASCOM-00323 R1
# component validation against the independently reconstructed official ACT
# payload. Scientific payload identity is checked outside this module.

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
import struct
from typing import Iterable, Mapping

import numpy as np
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import minimize

BLOCK_NAMES = ('TT', 'TE', 'EE')
BLOCK_SLICES = {'TT': slice(0, 45), 'TE': slice(45, 90), 'EE': slice(90, 135)}


@dataclass(frozen=True)
class ProjectedSpectra:
    tt: np.ndarray
    te: np.ndarray
    ee: np.ndarray

    def vector(self, A_act: float, P_act: float) -> np.ndarray:
        A2 = float(A_act) ** 2
        P = float(P_act)
        return np.concatenate((self.tt / A2, self.te / (A2 * P), self.ee / (A2 * P * P)))


@dataclass(frozen=True)
class NuisanceFit:
    objective: float
    chi2_ACT: float
    chi2_calibration_prior: float
    A_act: float
    P_act: float
    model_vector: np.ndarray
    residual: np.ndarray


class ACTCMBOnlyRaw:
    def __init__(self, path: str | Path):
        raw = Path(path).read_bytes()
        if raw[:9] != b'ACTSACCv1':
            raise ValueError('bad magic')
        off = 16
        npol, nbin, nell, ndata = struct.unpack_from('<4i', raw, off)
        off += 16
        if (npol, nbin, nell, ndata) != (3, 45, 8500, 135):
            raise ValueError((npol, nbin, nell, ndata))
        self.npol, self.nbin, self.nell, self.ndata = npol, nbin, nell, ndata
        self.ells = np.frombuffer(raw, dtype='<i8', count=nell, offset=off).copy(); off += 8 * nell
        n = npol * nell * nbin
        self.weights = np.frombuffer(raw, dtype='<f8', count=n, offset=off).copy().reshape(npol, nell, nbin); off += 8 * n
        self.data = np.frombuffer(raw, dtype='<f8', count=ndata, offset=off).copy(); off += 8 * ndata
        self.centers = np.frombuffer(raw, dtype='<f8', count=ndata, offset=off).copy(); off += 8 * ndata
        self.cov = np.frombuffer(raw, dtype='<f8', count=ndata * ndata, offset=off).copy().reshape(ndata, ndata)
        self.cov = 0.5 * (self.cov + self.cov.T)
        self._cho = cho_factor(self.cov, lower=True, check_finite=True)
        self._subset_indices = {}
        self._subset_cho = {}
        for size in range(1, len(BLOCK_NAMES) + 1):
            for selected in combinations(BLOCK_NAMES, size):
                key = frozenset(selected)
                indices = np.concatenate([np.arange(BLOCK_SLICES[name].start, BLOCK_SLICES[name].stop) for name in BLOCK_NAMES if name in key]).astype(int, copy=False)
                self._subset_indices[key] = indices
                self._subset_cho[key] = self._cho if len(key) == len(BLOCK_NAMES) else cho_factor(self.cov[np.ix_(indices, indices)], lower=True, check_finite=True)

    def project_spectra(self, cls: Mapping[str, np.ndarray]) -> ProjectedSpectra:
        projected = []
        for p, key in enumerate(('tt', 'te', 'ee')):
            values = np.asarray(cls[key], dtype=float)
            if values.ndim != 1 or values.size <= int(self.ells[-1]):
                raise ValueError(f'{key} spectrum does not cover ell={int(self.ells[-1])}')
            projected.append(self.weights[p].T @ values[self.ells])
        return ProjectedSpectra(*projected)

    def bandpower_vector_projected(self, projected: ProjectedSpectra, A_act: float, P_act: float) -> np.ndarray:
        return projected.vector(A_act, P_act)

    def bandpower_vector_direct(self, cls: Mapping[str, np.ndarray], A_act: float, P_act: float) -> np.ndarray:
        out = []
        for p, key in enumerate(('tt', 'te', 'ee')):
            dat = np.asarray(cls[key], dtype=float)[self.ells] / (float(A_act) * float(A_act))
            if key == 'te': dat /= float(P_act)
            elif key == 'ee': dat /= float(P_act) * float(P_act)
            out.append(self.weights[p].T @ dat)
        return np.concatenate(out)

    def chi2_from_residual(self, residual: np.ndarray) -> float:
        r = np.asarray(residual, dtype=float)
        return float(r @ cho_solve(self._cho, r, check_finite=False))

    def chi2_projected(self, projected: ProjectedSpectra, A_act: float, P_act: float) -> float:
        return self.chi2_from_residual(self.data - self.bandpower_vector_projected(projected, A_act, P_act))

    def chi2_direct(self, cls: Mapping[str, np.ndarray], A_act: float, P_act: float) -> float:
        return self.chi2_from_residual(self.data - self.bandpower_vector_direct(cls, A_act, P_act))

    @staticmethod
    def _fit_result(projected: ProjectedSpectra, data: np.ndarray, chi2_function, *, start=(1.0, 1.0), sigma=0.003) -> NuisanceFit:
        def fun(x):
            A, P = map(float, x)
            return float(chi2_function(A, P) + ((A - 1.0) / sigma) ** 2)
        initial = np.asarray(start, dtype=float)
        result = minimize(fun, initial, method='L-BFGS-B', bounds=((0.95, 1.05), (0.9, 1.1)), options={'ftol': 1e-14, 'gtol': 1e-9, 'maxiter': 500})
        if not result.success:
            result = minimize(fun, initial, method='Powell', bounds=((0.95, 1.05), (0.9, 1.1)), options={'xtol': 1e-11, 'ftol': 1e-12, 'maxiter': 1000})
        A, P = map(float, result.x)
        chi2 = float(chi2_function(A, P)); prior = float(((A - 1.0) / sigma) ** 2)
        model = projected.vector(A, P); residual = np.asarray(data, dtype=float) - model
        return NuisanceFit(chi2 + prior, chi2, prior, A, P, model, residual)

    def fit_nuisance_direct(self, cls: Mapping[str, np.ndarray], start=(1.0, 1.0), sigma=0.003) -> NuisanceFit:
        projected = self.project_spectra(cls)
        return self._fit_result(projected, self.data, lambda A, P: self.chi2_direct(cls, A, P), start=start, sigma=sigma)

    def fit_nuisance(self, cls: Mapping[str, np.ndarray], start=(1.0, 1.0), sigma=0.003) -> NuisanceFit:
        projected = self.project_spectra(cls)
        return self._fit_result(projected, self.data, lambda A, P: self.chi2_projected(projected, A, P), start=start, sigma=sigma)
