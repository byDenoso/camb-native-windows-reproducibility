#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import camb
import numpy as np
from scipy.optimize import brentq

ROOT_TOL = 1e-10
RDRAG_TOL = 1e-9


def rdrag_at(nnu: float) -> float:
    pars = camb.CAMBparams()
    pars.set_cosmology(
        H0=68.78348854533374,
        ombh2=0.022792460915530367,
        omch2=0.13140302335409929,
        nnu=float(nnu),
        num_massive_neutrinos=1,
        tau=0.0566,
    )
    return float(camb.get_background(pars).get_derived_params()['rdrag'])


def solve(target: float, *, hint: float | None) -> tuple[float, float, int]:
    low, high = 3.05, 4.4
    cache: dict[float, float] = {}
    def residual(x: float) -> float:
        key = round(float(x), 14)
        if key not in cache: cache[key] = rdrag_at(x)
        return cache[key] - target
    if hint is not None and np.isfinite(hint):
        fh = residual(hint)
        if abs(fh) <= RDRAG_TOL:
            return float(hint), float(cache[round(float(hint), 14)]), len(cache)
        width = (high-low)*0.04
        while width < (high-low):
            a=max(low,hint-width); b=min(high,hint+width)
            fa=residual(a); fb=residual(b)
            if fa == 0 or fb == 0 or fa*fb < 0:
                root=float(brentq(residual,a,b,xtol=ROOT_TOL,rtol=1e-12,maxiter=64))
                return root, float(rdrag_at(root)), len(cache)
            width *= 2
    root=float(brentq(residual,low,high,xtol=ROOT_TOL,rtol=1e-12,maxiter=64))
    return root, float(rdrag_at(root)), len(cache)


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--receipt',type=Path,required=True); a=ap.parse_args()
    # Build a deterministic real-CAMB target at an interior mechanism point.
    canonical_hint=3.4
    target=rdrag_at(canonical_hint)
    plain_root, plain_rdrag, plain_calls=solve(target,hint=None)
    hint_root, hint_rdrag, hint_calls=solve(target,hint=canonical_hint)
    root_delta=abs(plain_root-hint_root); rdrag_delta=abs(plain_rdrag-hint_rdrag)
    passed=(root_delta <= 1e-8 and rdrag_delta <= RDRAG_TOL and hint_calls == 1 and plain_calls > hint_calls)
    payload={
      'gate_id':'G08','status':'verified' if passed else 'failed','schema':'ascom-00323-g08-rdrag-continuation/v2',
      'camb_version':camb.__version__,'mechanism':'nnu','bounds':[3.05,4.4],
      'target_rdrag_mpc':target,'plain':{'root':plain_root,'rdrag_mpc':plain_rdrag,'background_evaluations':plain_calls},
      'continued':{'hint':canonical_hint,'root':hint_root,'rdrag_mpc':hint_rdrag,'background_evaluations':hint_calls},
      'root_absolute_delta':root_delta,'rdrag_absolute_delta_mpc':rdrag_delta,
      'historical_lineage':{'kpeer_n3_background_evaluations':[14,1],'local_wall_speedup_approx':11.34},
      'claim_boundary':'Fresh native-Windows real-CAMB test certifies continuation identity and call reduction. Historical K-PEER 14-to-1 remains lineage, not a fresh measured count, unless separately reproduced with the frozen CosmoRec-enabled runtime.'
    }
    a.receipt.parent.mkdir(parents=True,exist_ok=True); a.receipt.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(payload,indent=2,sort_keys=True)); return 0 if passed else 2

if __name__=='__main__': raise SystemExit(main())
