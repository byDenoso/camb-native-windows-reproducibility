#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from typing import Any

ACT_SHA = 'd3ca3ff9427ecb22141df32fb6b4398d3f9a3dcb1a10d22344b33c56a12b6484'
TOL = 1.0e-9
CAMB_TOL = 1.0e-12
SEEDS = (20260803, 20260813, 20260823, 20260902)
HARNESS_SHA = 'f2cf596eee66cc59554a966e3cf04157f01b928b1dd5f62375670fadb52a84ec'


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def decode_canonical_harness(repo: Path, work: Path) -> tuple[Path, bytes]:
    parts = sorted((repo / 'r1_scientific_harness/canonical_parts').glob('part*.b64'))
    expected_names = [f'part{i:02d}.b64' for i in range(1, 5)]
    if [p.name for p in parts] != expected_names:
        raise RuntimeError(f'canonical harness parts mismatch: {[p.name for p in parts]}')
    encoded = ''.join(''.join(p.read_text(encoding='ascii').split()) for p in parts)
    payload = base64.b64decode(encoded, validate=True)
    observed = sha256_bytes(payload)
    if observed != HARNESS_SHA:
        raise RuntimeError(f'canonical harness SHA mismatch: {observed}')
    archive = work / 'canonical-harness.tar.gz'
    archive.write_bytes(payload)
    with tarfile.open(archive, 'r:gz') as tf:
        tf.extractall(work)
    root = work / 'r1_scientific_harness'
    if not (root / 'peer_platform/paper_validation_v6.py').is_file():
        raise RuntimeError('canonical harness extraction incomplete')
    return root, payload


def receipt(gate: str, passed: bool, observed: dict[str, Any]) -> dict[str, Any]:
    return {'gate_id': gate, 'status': 'pass' if passed else 'fail', 'observed': observed}


def run_probe(repo: Path, receipt_path: Path, threads: int) -> dict[str, Any]:
    env = os.environ.copy()
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        env[key] = str(threads)
    subprocess.run(
        [sys.executable, str(repo / 'scripts/r1_core_probe.py'), '--receipt', str(receipt_path)],
        check=True, env=env,
    )
    return json.loads(receipt_path.read_text(encoding='utf-8-sig'))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', type=Path, required=True)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--receipts', type=Path, required=True)
    args = ap.parse_args()
    repo = args.repo.resolve(); work = args.work.resolve(); out = args.receipts.resolve()
    work.mkdir(parents=True, exist_ok=True); out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(repo / 'src'))
    sys.path.insert(0, str(repo / 'scripts'))

    from native_windows_camb.fingerprint import scientific_fingerprint
    from native_windows_camb.integrity import verify_hashes
    import run_r1_scientific_closure as closure

    gates: dict[str, dict[str, Any]] = {}

    # R01: canonical split harness identity and bit-flip sensitivity.
    harness_work = work / 'harness'; harness_work.mkdir(parents=True, exist_ok=True)
    harness, payload = decode_canonical_harness(repo, harness_work)
    observed = sha256_bytes(payload)
    corrupted = bytearray(payload); corrupted[len(corrupted)//2] ^= 1
    r = receipt('R01', observed == HARNESS_SHA and sha256_bytes(corrupted) != observed,
                {'observed_sha256': observed, 'expected_sha256': HARNESS_SHA,
                 'corrupted_sha256': sha256_bytes(corrupted), 'parts': 4})
    gates['R01'] = r; write_json(out/'R01.json', r)

    # R02: generic content integrity must fail closed on missing and corrupted files.
    integ = work / 'integrity'; integ.mkdir(exist_ok=True)
    p = integ / 'payload.bin'; p.write_bytes(b'ascom-00323-robustness')
    expected = {'payload.bin': sha256_file(p)}
    ok_before, errors_before = verify_hashes(integ, expected)
    p.write_bytes(p.read_bytes() + b'!')
    ok_after, errors_after = verify_hashes(integ, expected)
    ok_missing, errors_missing = verify_hashes(integ, {'missing.bin': '0'*64})
    r = receipt('R02', ok_before and not ok_after and not ok_missing,
                {'before_errors': errors_before, 'corruption_errors': errors_after, 'missing_errors': errors_missing})
    gates['R02'] = r; write_json(out/'R02.json', r)

    # R03: scientific fingerprint determinism/sensitivity/fail-closed non-finite values.
    a = scientific_fingerprint({'solver':'CAMB','precision':{'lmax':3000,'kmax':10.0}})
    b = scientific_fingerprint({'precision':{'kmax':10.0,'lmax':3000},'solver':'CAMB'})
    c = scientific_fingerprint({'solver':'CAMB','precision':{'lmax':3001,'kmax':10.0}})
    rejected = []
    for value in (float('nan'), float('inf'), float('-inf')):
        try: scientific_fingerprint({'x': value})
        except ValueError: rejected.append(True)
        else: rejected.append(False)
    r = receipt('R03', a == b and a != c and all(rejected),
                {'order_independent': a == b, 'precision_sensitive': a != c, 'non_finite_rejected': rejected})
    gates['R03'] = r; write_json(out/'R03.json', r)

    # Build the exact recovered released late-time runtime once for R04/R09-R16.
    sys.path.insert(0, str(harness))
    public_data = work / 'public-data'; public_data.mkdir(parents=True, exist_ok=True)
    bao, pan = closure.clone_data(public_data)
    runtime, pan_receipt = closure.build_runtime(work / 'runtime-build', bao, pan)
    from peer_platform.late_time_campaign_v5 import LateTimeCampaignV5
    from peer_platform.cobaya_campaign_v5 import TieredCobayaAdapterV5
    from peer_platform.paper_validation_v6 import (
        PARAMETER_BOUNDS, _baseline_logp, equivalence_grid, latin_hypercube_points,
        memory_stability, run_failure_injection,
    )
    campaign = LateTimeCampaignV5.load(runtime)
    nominal = {'omega_m':0.30,'H0':70.0,'sigma8':0.81,'rdrag_mpc':147.0,'M_B':-19.3}

    # R04: relocation to a path with spaces and Unicode must not change results.
    base_value = _baseline_logp(campaign, nominal, quadrature_order=64)
    relocated_root = work / 'relocated path ç α' / 'runtime'
    relocated_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(runtime, relocated_root)
    relocated = LateTimeCampaignV5.load(relocated_root)
    relocated_value = _baseline_logp(relocated, nominal, quadrature_order=64)
    r = receipt('R04', abs(base_value-relocated_value) <= TOL,
                {'baseline': base_value, 'relocated': relocated_value, 'abs_delta': abs(base_value-relocated_value), 'path': str(relocated_root)})
    gates['R04'] = r; write_json(out/'R04.json', r)

    # R05: line-ending mutation changes working bytes but not the canonical Git blob identity.
    rel = 'desi_bao_dr2/desi_gaussian_bao_ALL_GCcomb_mean.txt'
    canonical = subprocess.check_output(['git','-C',str(bao),'show',f'{closure.BAO_COMMIT}:{rel}'])
    canonical_sha = sha256_bytes(canonical)
    crlf = canonical.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
    r = receipt('R05', canonical_sha == '9ac154ab583ce759c0f7eef3c978c7c70a6ead2d18774caceadf1a350a640585' and sha256_bytes(crlf) != canonical_sha,
                {'canonical_sha256': canonical_sha, 'crlf_sha256': sha256_bytes(crlf), 'canonical_authority': 'Git blob'})
    gates['R05'] = r; write_json(out/'R05.json', r)

    # R06: ACT public payload must detect a one-byte mutation.
    act = repo / '.r1/act_dr6_cmbonly.bin'
    if not act.is_file():
        raise RuntimeError(f'ACT payload missing from core materialization: {act}')
    act_bytes = act.read_bytes(); bitflip = bytearray(act_bytes); bitflip[len(bitflip)//2] ^= 1
    r = receipt('R06', sha256_bytes(act_bytes) == ACT_SHA and sha256_bytes(bitflip) != ACT_SHA,
                {'source_sha256': sha256_bytes(act_bytes), 'expected_sha256': ACT_SHA, 'bitflip_sha256': sha256_bytes(bitflip), 'bytes': len(act_bytes)})
    gates['R06'] = r; write_json(out/'R06.json', r)

    # R07: five fresh CAMB processes must reproduce the same observables.
    probes = [run_probe(repo, work/f'probe-{i}.json', 1)['run_1'] for i in range(5)]
    keys = ('rdrag_mpc','sigma8','theta_star_100')
    spreads = {k: max(x[k] for x in probes)-min(x[k] for x in probes) for k in keys}
    r = receipt('R07', all(abs(v) <= CAMB_TOL for v in spreads.values()), {'processes': 5, 'spreads': spreads, 'tolerance': CAMB_TOL})
    gates['R07'] = r; write_json(out/'R07.json', r)

    # R08: thread-count perturbation must not alter the CAMB probe beyond tolerance.
    t1 = run_probe(repo, work/'probe-thread1.json', 1)['run_1']
    t2 = run_probe(repo, work/'probe-thread2.json', 2)['run_1']
    deltas = {k: abs(t1[k]-t2[k]) for k in keys}
    r = receipt('R08', all(v <= CAMB_TOL for v in deltas.values()), {'thread1': t1, 'thread2': t2, 'absolute_deltas': deltas, 'tolerance': CAMB_TOL})
    gates['R08'] = r; write_json(out/'R08.json', r)

    # R09: cold/warm/clear cache identity with positive hit evidence.
    adapter = TieredCobayaAdapterV5(campaign, quadrature_order=64, shape_cache_capacity=4, scale_cache_capacity=4)
    cold = adapter.logp(**nominal); m1 = adapter.metrics()
    warm = adapter.logp(**nominal); m2 = adapter.metrics()
    adapter.clear(); cleared = adapter.logp(**nominal); m3 = adapter.metrics()
    pass_r09 = max(abs(cold-warm), abs(cold-cleared)) <= TOL and m2['shape_hits'] > m1['shape_hits'] and m2['scale_hits'] > m1['scale_hits'] and m3['shape_computations'] > m2['shape_computations']
    r = receipt('R09', pass_r09, {'values':[cold,warm,cleared], 'metrics_after_cold':m1, 'metrics_after_warm':m2, 'metrics_after_clear_replay':m3, 'tolerance':TOL})
    gates['R09'] = r; write_json(out/'R09.json', r)

    # R10: multi-seed 64-point parity stress.
    seed_rows = []
    for seed in SEEDS:
        result = equivalence_grid(campaign, points=64, seed=seed, quadrature_order=64, tolerance=TOL)
        seed_rows.append({'seed': seed, 'status': result['status'], 'max_abs_log_likelihood_delta': result['max_abs_log_likelihood_delta']})
    r = receipt('R10', all(x['status']=='pass' for x in seed_rows), {'runs':seed_rows, 'tolerance':TOL})
    gates['R10'] = r; write_json(out/'R10.json', r)

    # R11: all 32 corners of the frozen five-dimensional domain.
    names = ('omega_m','H0','sigma8','rdrag_mpc','M_B')
    corners = [dict(zip(names, values)) for values in itertools.product(*(PARAMETER_BOUNDS[n] for n in names))]
    corner_adapter = TieredCobayaAdapterV5(campaign, quadrature_order=64, shape_cache_capacity=64, scale_cache_capacity=64)
    corner_deltas = []
    for point in corners:
        base = _baseline_logp(campaign, point, quadrature_order=64)
        fast = corner_adapter.logp(**point)
        corner_deltas.append(abs(base-fast))
    r = receipt('R11', max(corner_deltas) <= TOL, {'corners':len(corners), 'max_abs_log_likelihood_delta':max(corner_deltas), 'tolerance':TOL})
    gates['R11'] = r; write_json(out/'R11.json', r)

    # R12: force shape/scale LRU evictions, then replay an evicted early point.
    points = latin_hypercube_points(24, seed=20260902)
    tiny = TieredCobayaAdapterV5(campaign, quadrature_order=64, shape_cache_capacity=2, scale_cache_capacity=3)
    for point in points:
        tiny.logp(**point)
    metrics_before_replay = tiny.metrics()
    replay = tiny.logp(**points[0]); baseline_replay = _baseline_logp(campaign, points[0], quadrature_order=64)
    metrics_after_replay = tiny.metrics()
    r = receipt('R12', abs(replay-baseline_replay)<=TOL and metrics_before_replay['shape_evictions']>0 and metrics_before_replay['scale_evictions']>0,
                {'shape_evictions':metrics_before_replay['shape_evictions'], 'scale_evictions':metrics_before_replay['scale_evictions'], 'replay_abs_delta':abs(replay-baseline_replay), 'metrics_after_replay':metrics_after_replay})
    gates['R12'] = r; write_json(out/'R12.json', r)

    # R13: inherited negative controls must all remain fail-closed.
    negative = run_failure_injection(runtime)
    r = receipt('R13', negative.get('status')=='pass', negative)
    gates['R13'] = r; write_json(out/'R13.json', r)

    # R14: 4x paper memory duration, same 128 MiB hard ceiling.
    mem = memory_stability(campaign, evaluations=1024, quadrature_order=64, maximum_growth_bytes=134217728)
    r = receipt('R14', mem.get('status')=='pass', mem)
    gates['R14'] = r; write_json(out/'R14.json', r)

    # R15: reconstruct Pantheon+ twice in independent roots; compiled manifest identity must match.
    rta = work/'pantheon-rebuild-a'; rtb = work/'pantheon-rebuild-b'
    a_pan = closure.compile_pantheon(rta, pan); b_pan = closure.compile_pantheon(rtb, pan)
    same_pan = a_pan['compiled_manifest_sha256'] == b_pan['compiled_manifest_sha256'] == pan_receipt['compiled_manifest_sha256']
    r = receipt('R15', same_pan, {'initial':pan_receipt['compiled_manifest_sha256'], 'rebuild_a':a_pan['compiled_manifest_sha256'], 'rebuild_b':b_pan['compiled_manifest_sha256']})
    gates['R15'] = r; write_json(out/'R15.json', r)

    # R16: identical seed in a fresh campaign object must reproduce the numerical decision exactly.
    first = equivalence_grid(campaign, points=64, seed=20260803, quadrature_order=64, tolerance=TOL)
    fresh_campaign = LateTimeCampaignV5.load(runtime)
    second = equivalence_grid(fresh_campaign, points=64, seed=20260803, quadrature_order=64, tolerance=TOL)
    r = receipt('R16', first['status']=='pass' and second['status']=='pass' and first['max_abs_log_likelihood_delta']==second['max_abs_log_likelihood_delta'],
                {'first_max_delta':first['max_abs_log_likelihood_delta'], 'second_max_delta':second['max_abs_log_likelihood_delta'], 'seed':20260803})
    gates['R16'] = r; write_json(out/'R16.json', r)

    all_pass = all(g['status']=='pass' for g in gates.values())
    summary = {
        'schema':'ascom-00323-r1-robustness/v1',
        'status':'verified' if all_pass else 'failed',
        'required_gates':list(gates),
        'gate_statuses':{k:v['status'] for k,v in gates.items()},
        'claim_boundary':'Adversarial robustness of the reproducibility artifact and late-time deterministic validation. It does not promote M0, ACT/CosmoRec mechanism tests, posterior, evidence or cosmological model-preference claims.',
    }
    write_json(out/'robustness-summary.json', summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if all_pass else 2


if __name__ == '__main__':
    raise SystemExit(main())
