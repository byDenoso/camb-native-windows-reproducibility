from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np

from peer_015_contract import MODEL_014, R1_MODEL, R2_MODEL

H0_014 = 70.79500375310349
RDRAG_014 = 143.10924612032258
THETA100_014 = 1.0422199456800059
G1_H0_REL = 1.0e-6
G1_RDRAG_REL = 1.0e-5
G1_THETA_REL = 1.0e-5
OFFICIAL_CAMB_COMMIT = "3ef0272d6f7ba1231128872e56e6d4c12af8267b"


def hash_array(arr: np.ndarray) -> str:
    a = np.ascontiguousarray(arr)
    h = hashlib.sha256()
    h.update(a.dtype.str.encode("ascii"))
    h.update(np.asarray(a.shape, dtype=np.int64).tobytes())
    h.update(a.view(np.uint8))
    return h.hexdigest()


def endpoint_replay_pass(metrics: dict[str, float]) -> bool:
    return bool(
        abs(float(metrics["H0"]) / H0_014 - 1.0) < G1_H0_REL
        and abs(float(metrics["rdrag"]) / RDRAG_014 - 1.0) < G1_RDRAG_REL
        and abs(float(metrics["theta100"]) / THETA100_014 - 1.0) < G1_THETA_REL
    )


def _load_014_module():
    path = Path(__file__).with_name("run_peer_axion_twofield_014.py")
    spec = importlib.util.spec_from_file_location("peer014_frozen", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frozen 014 runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _set_high_l(p: Any, lmax: int) -> Any:
    p.set_for_lmax(int(lmax), lens_potential_accuracy=1)
    p.WantCls = True
    p.WantTransfer = False
    return p


def _model_params(name: str, *, lmax: int):
    frozen = _load_014_module()
    if name == "active":
        p = frozen.active_params(
            f=float(MODEL_014["f_early"]),
            m=float(MODEL_014["m_early"]),
            late_amp=float(MODEL_014["late_amp"]),
            cmb=True,
            transfer=False,
        )
    elif name == "r1":
        p = frozen.comparator_params(
            f=float(R1_MODEL["f_early"]),
            m=float(R1_MODEL["m_early"]),
            cmb=True,
            transfer=False,
        )
    elif name == "r2":
        p = frozen.common_params(cmb=True, transfer=False)
    else:
        raise ValueError(f"unknown endpoint {name}")
    return _set_high_l(p, lmax)


def _extract_cls(results: Any, lmax: int) -> dict[str, np.ndarray]:
    spectra = results.get_cmb_power_spectra(CMB_unit="muK", raw_cl=True)
    total = np.asarray(spectra["total"], dtype=np.float64)
    if total.shape[0] <= lmax:
        raise RuntimeError(f"CAMB total spectrum covers {total.shape[0]-1}, requested {lmax}")
    total = np.ascontiguousarray(total[: lmax + 1])
    return {
        "TT": np.ascontiguousarray(total[:, 0]),
        "EE": np.ascontiguousarray(total[:, 1]),
        "BB": np.ascontiguousarray(total[:, 2]),
        "TE": np.ascontiguousarray(total[:, 3]),
    }


def _metrics(results: Any) -> dict[str, float]:
    derived = results.get_derived_params()
    return {
        "H0": float(results.hubble_parameter(0.0)),
        "rdrag": float(derived["rdrag"]),
        "rstar": float(derived["rstar"]),
        "theta100": float(derived["thetastar"]),
    }


@dataclass
class Endpoint:
    name: str
    results: Any
    cls: dict[str, np.ndarray]
    metrics: dict[str, float]

    def hashes(self) -> dict[str, str]:
        return {key: hash_array(value) for key, value in self.cls.items()}


@dataclass
class EndpointSet:
    active: Endpoint
    r1: Endpoint
    r2: Endpoint
    active_repeat: Endpoint
    manifest: dict[str, Any]


def _one_endpoint(name: str, *, lmax: int) -> Endpoint:
    import camb

    params = _model_params(name, lmax=lmax)
    results = camb.get_results(params)
    return Endpoint(name=name, results=results, cls=_extract_cls(results, lmax), metrics=_metrics(results))


def generate_endpoints(output_dir: str | Path, *, lmax: int = 9000) -> EndpointSet:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    active = _one_endpoint("active", lmax=lmax)
    active_repeat = _one_endpoint("active", lmax=lmax)
    r1 = _one_endpoint("r1", lmax=lmax)
    r2 = _one_endpoint("r2", lmax=lmax)

    hashes_active = active.hashes()
    hashes_repeat = active_repeat.hashes()
    deterministic = hashes_active == hashes_repeat
    replay = endpoint_replay_pass(active.metrics)

    endpoints = {"active": active, "r1": r1, "r2": r2}
    for name, endpoint in endpoints.items():
        np.savez_compressed(
            out / f"endpoint_{name}.npz",
            TT=endpoint.cls["TT"],
            TE=endpoint.cls["TE"],
            EE=endpoint.cls["EE"],
            BB=endpoint.cls["BB"],
        )

    manifest: dict[str, Any] = {
        "schema": "nexo-peer015-endpoints/v1",
        "official_camb_commit": OFFICIAL_CAMB_COMMIT,
        "lmax": int(lmax),
        "frozen_models": {"active": MODEL_014, "r1": R1_MODEL, "r2": R2_MODEL},
        "metrics": {name: endpoint.metrics for name, endpoint in endpoints.items()},
        "hashes": {name: endpoint.hashes() for name, endpoint in endpoints.items()},
        "active_repeat_hashes": hashes_repeat,
        "deterministic": deterministic,
        "G1_endpoint_replay": replay,
        "G1_tolerances": {
            "H0_relative": G1_H0_REL,
            "rdrag_relative": G1_RDRAG_REL,
            "theta100_relative": G1_THETA_REL,
        },
    }
    (out / "endpoint_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return EndpointSet(active=active, r1=r1, r2=r2, active_repeat=active_repeat, manifest=manifest)
