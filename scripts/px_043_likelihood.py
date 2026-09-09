from __future__ import annotations

import numpy as np


def build_cmb_clipy_cls(raw_cmb_cls: np.ndarray) -> np.ndarray:
    """Convert CAMB raw C_l [ell, TT, EE, BB, TE] to ClipY [TT,EE,BB,TE,TB,EB]."""
    raw = np.asarray(raw_cmb_cls, dtype=float)
    if raw.ndim != 2 or raw.shape[1] < 4:
        raise ValueError("expected CAMB raw CMB spectra with shape (ell, >=4)")
    out = np.zeros((6, raw.shape[0]), dtype=float)
    out[0] = raw[:, 0]
    out[1] = raw[:, 1]
    out[2] = raw[:, 2]
    out[3] = raw[:, 3]
    return out


def build_lensing_clipy_cls(raw_cmb_cls: np.ndarray, raw_pp_cls: np.ndarray) -> np.ndarray:
    """Convert CAMB raw C_l plus C_L^phiphi to ClipY lensing [PP,TT,EE,BB,TE,TB,EB]."""
    raw = np.asarray(raw_cmb_cls, dtype=float)
    pp = np.asarray(raw_pp_cls, dtype=float)
    if raw.ndim != 2 or raw.shape[1] < 4:
        raise ValueError("expected CAMB raw CMB spectra with shape (ell, >=4)")
    if pp.ndim != 1:
        raise ValueError("expected one-dimensional raw phi-phi spectrum")
    n = max(raw.shape[0], pp.size)
    out = np.zeros((7, n), dtype=float)
    out[0, : pp.size] = pp
    out[1, : raw.shape[0]] = raw[:, 0]
    out[2, : raw.shape[0]] = raw[:, 1]
    out[3, : raw.shape[0]] = raw[:, 2]
    out[4, : raw.shape[0]] = raw[:, 3]
    return out


def default_nuisance(likelihood) -> dict[str, float]:
    """Read nuisance defaults from a ClipY self-test vector without inventing values."""
    default = np.asarray(likelihood.default_par, dtype=float)
    _, nuisance = likelihood.normalize(default)
    return {str(k): float(v) for k, v in nuisance.items()}


def crop_cls_for_likelihood(cls: np.ndarray, likelihood) -> np.ndarray:
    """Return enough multipoles and rows for the likelihood's declared lmax contract."""
    lmax = np.asarray(likelihood.lmax, dtype=int)
    if cls.ndim != 2 or cls.shape[0] < lmax.size:
        raise ValueError(f"spectra rows {cls.shape[0]} do not cover likelihood rows {lmax.size}")
    need = int(np.max(lmax)) + 1
    if cls.shape[1] < need:
        raise ValueError(f"spectra lmax {cls.shape[1]-1} below likelihood requirement {need-1}")
    return np.asarray(cls[: lmax.size, :need], dtype=float)
