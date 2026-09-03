#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd
from scipy.linalg import cho_factor

import act_public_payload
import pantheon_cross_platform
import run_g15_regression as registered_source
import run_r1_scientific_closure as closure

MODULES = {
    "tests.test_optimized_runtime": 17,
    "tests.test_packaging_v6": 3,
    "tests.test_paper_validation_v6": 12,
    "tests.test_runtime_v3": 21,
    "tests.test_runtime_v4": 34,
}
EXPECTED_TOTAL = 87
SOURCE_ARCHIVE_SHA256 = "5add06fbc244116fbdf4415457a8609f061039853dfea3f571826e939b18ebd2"
PANTHEON_COMMIT = closure.PANTHEON_COMMIT
BAO_COMMIT = closure.BAO_COMMIT
ACT_PAYLOAD_SHA256 = act_public_payload.EXPECTED_PAYLOAD_SHA256
ACT_SPECTRA_HISTORICAL_SHA256 = "c65927c875c9ab0735cb6caf246750b38e7aa602af62456974b5abec0ca4c549"
ACT_GOLDEN_OBJECTIVE = 156.73503293246858
ACT_GOLDEN_A = 1.000112578332859
ACT_GOLDEN_P = 1.0022665092745313

# Sufficient-statistic projection of the frozen PEER n=3 ACT control.  These are
# the 45 TT + 45 TE + 45 EE bandpowers obtained from the historical spectra.
# The public fixture reconstructs one deterministic ell-space preimage and then
# verifies that reprojection recovers these 135 values before any regression test.
ACT_PROJECTED_CONTROL = np.asarray([
2208.686701231664,1865.5021435200258,1883.9047979312877,2227.547544412447,2507.5468276254214,2388.3382868373974,1896.418900626995,1355.8904742701116,1073.1036688700515,1089.0203401366587,1205.3179296812805,1206.2365997652917,1044.9310827483764,841.1423008447176,734.7428333619206,754.0056860788699,810.7417067804263,798.9621696404114,689.4967233505998,539.9249220482858,429.6091166879013,391.1315839809683,396.0272405037227,393.6750370402597,358.13227358663397,302.28613730618565,256.0171115461322,235.83155990555196,233.5786585759689,218.69290366587154,160.7537348509002,121.09733961883202,108.27856031683899,86.39897162653988,64.12946514633435,41.74409116527583,27.39882557106805,15.218255597690941,6.884756198136459,3.474391423601561,1.9892571388555824,1.3077958967254595,0.9714704391473437,0.7786776701262965,0.654733297969756,
24.719156566390225,-18.884179932219077,-95.37970811819321,-129.92220247490525,-86.0551615437238,-0.7777628765025077,53.54140652928735,37.64436057963984,-23.287869211043986,-70.49782879112895,-67.90501132148319,-29.630728099927953,1.5937150396956352,-2.366177719750089,-32.47148463539967,-56.96464242939241,-53.4194776967214,-26.94604203603344,-1.1767004625866386,5.010340584395699,-7.742953479382452,-23.8840587355713,-28.98861445353291,-21.288279241111297,-10.053561710289575,-5.201408000287443,-8.833335588175128,-15.308948639604287,-17.764588375027525,-10.943189705026471,-3.447725039941365,-6.847286303754969,-6.471504947542677,-3.3020503293554775,-3.801744079934879,-1.7704714512319044,-1.4634127599472464,-0.7317052454709158,-0.30326408444315567,-0.12654212057697414,-0.05917991627574426,-0.03148439978033928,-0.019763017343964802,-0.014089515864986645,-0.010917755317796244,
19.843977341717483,32.97343132386053,36.47831331803573,27.609411286728914,15.974116496030783,13.966755562401016,24.328421845209174,37.58300021662818,41.567358795283845,33.068292815277985,20.15403274122762,13.829853467507444,17.84316558615171,26.274310137802818,30.14987364591536,25.846946412804133,17.490791461228334,12.115698284890174,13.055580559826515,17.66149597630935,20.593925344273583,18.840977644164774,13.82871210841075,9.388963109192423,8.114729974201383,9.505019391905286,11.061684302645613,10.785478913068241,8.694610907302982,5.748343766968037,5.680014202254134,5.637653486910932,3.567646918805998,2.8838618288861717,2.4280538882769527,1.5020409203569367,0.9597612263591083,0.5175618988669038,0.2169119016698474,0.09459595902686434,0.045489721903450415,0.025152686010951376,0.015967067961184685,0.011438398485365164,0.008913732602071582
], dtype=float)

B1_HEADER = "H0,ombh2,omch2,ns,tau,logA,A_planck,Alens,peer_fede,logpost,omega_m,rdrag,chi2_CMB,chi2_BAO,chi2_LADDER,chi2_total_like,chi2_total_post,chain,dMB_mean_conditional,dMB_Cepheid_minus_HF,MB_HF,MB_Cepheid,H0_apparent_Cepheid,delta_H0_apparent"
B1_ROW = "71.188267372924813,0.022890657593082699,0.12753139641567701,0.99522773505026163,0.058171226659564097,3.051432810443873,0.99714094278132204,1.0715071049997051,0.1008655841892226,-661.9381276611125,0.29682103069974619,142.2122860083204,1010.7150946243612,11.851530577183439,299.92836937983594,1322.4949945813803,1323.876255322225,1,0.070554160987778905,0.060723420264341001,-19.31750167792184,-19.24694751693406,73.207083778153503,2.0188164052286908"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def save_array(path: Path, value: np.ndarray) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, value, allow_pickle=False)
    return {
        "path": str(path.name),
        "sha256": sha256_file(path),
        "shape": list(value.shape),
        "dtype": str(value.dtype),
    }


def _pantheon_raw(runtime: Path) -> tuple[pd.DataFrame, np.ndarray, Path, Path]:
    raw = runtime / "data/sn_data/PantheonPlus"
    table_path = raw / "Pantheon+SH0ES.dat"
    cov_path = raw / "Pantheon+SH0ES_STAT+SYS.cov"
    table = pd.read_csv(table_path, sep=r"\s+")
    flat = np.loadtxt(cov_path)
    n = len(table)
    if int(flat[0]) != n or flat[1:].size != n * n:
        raise RuntimeError("Pantheon public covariance shape mismatch")
    cov = flat[1:].reshape(n, n)
    cov = np.tril(cov) + np.tril(cov, -1).T
    return table, cov, table_path, cov_path


def compile_no_shoes(runtime: Path) -> dict:
    table, cov, table_path, cov_path = _pantheon_raw(runtime)
    # Historical noSH0ES selected set is exactly the main Hubble-flow set minus
    # all calibrators and five pre-cut low-z non-calibrator rows.  This mapping
    # was independently checked against the frozen 1,575-object arrays and its
    # covariance is the corresponding main-covariance submatrix to <3e-16 rel.
    excluded = {
        ("1999ac", 13.6652), ("1999ac", 13.7144),
        ("2009an", 14.0848), ("2009an", 13.9723),
        ("2004S", 13.8706),
    }
    keep = (table["zHD"].to_numpy(float) > 0.01) & (table["IS_CALIBRATOR"].to_numpy(int) == 0)
    cid = table["CID"].astype(str).to_numpy()
    mag = table["m_b_corr"].to_numpy(float)
    for name, value in excluded:
        keep &= ~((cid == name) & np.isclose(mag, value, rtol=0.0, atol=5e-12))
    idx = np.flatnonzero(keep)
    if idx.size != 1575:
        raise RuntimeError(f"historical noSH0ES reconstruction expected 1575 rows, got {idx.size}")
    selected_cov = cov[np.ix_(idx, idx)]
    factor, _ = cho_factor(selected_cov, lower=True, check_finite=False, overwrite_a=False)
    factor = np.tril(factor)
    arrays = {
        "magnitude": table.loc[keep, "m_b_corr"].to_numpy(float),
        "zcmb": table.loc[keep, "zHD"].to_numpy(float),
        "zhel": table.loc[keep, "zHEL"].to_numpy(float),
        "is_calibrator": np.zeros(idx.size, dtype=np.uint8),
        "ceph_dist": np.zeros(idx.size, dtype=float),
        "cholesky": factor,
    }
    compiled = runtime / "data/sn_data/PantheonPlus/compiled_v2"
    directory = compiled / "no_shoes"
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    manifest = json.loads((compiled / "manifest.json").read_text(encoding="utf-8"))
    files = {}
    for name, array in arrays.items():
        path = directory / f"{name}.npy"
        np.save(path, array, allow_pickle=False)
        files[name] = {
            "path": f"no_shoes/{path.name}", "sha256": sha256_file(path),
            "shape": list(array.shape), "dtype": str(array.dtype),
        }
    manifest["selections"]["no_shoes"] = {
        "n": int(idx.size), "calibrators": 0,
        "source": {
            "main_table_sha256": sha256_file(table_path),
            "main_covariance_sha256": sha256_file(cov_path),
            "transform": "main zHD>0.01, remove calibrators, remove frozen five-row pre-cut",
        },
        "files": files,
    }
    write_json(compiled / "manifest.json", manifest)
    return {"rows": int(idx.size), "manifest_sha256": sha256_file(compiled / "manifest.json")}


def compile_direct_ladder(runtime: Path) -> dict:
    table, cov, table_path, cov_path = _pantheon_raw(runtime)
    mask = (table["IS_CALIBRATOR"].to_numpy(int) == 1) | (table["USED_IN_SH0ES_HF"].to_numpy(int) == 1)
    idx = np.flatnonzero(mask)
    selected = table.loc[mask].reset_index(drop=True)
    selected_cov = cov[np.ix_(idx, idx)]
    factor, _ = cho_factor(selected_cov, lower=True, check_finite=False, overwrite_a=False)
    factor = np.tril(factor)
    root = runtime / "data/multi_anchor/direct_ladder_compiled_v1"
    root.mkdir(parents=True, exist_ok=True)
    selected.to_csv(root / "table.csv", index=False, float_format="%.17g")
    np.save(root / "cholesky.npy", factor, allow_pickle=False)
    is_cal = selected["IS_CALIBRATOR"].to_numpy(np.uint8)
    np.save(root / "is_calibrator.npy", is_cal, allow_pickle=False)
    manifest = {
        "schema": "peer-direct-ladder-compiled/v1",
        "n_total": int(len(table)), "n_ladder": int(len(selected)),
        "n_calibrator": int(is_cal.sum()), "n_hubble_flow": int((is_cal == 0).sum()),
        "covariance_min_eigenvalue": float(np.linalg.eigvalsh(selected_cov)[0]),
        "source": {"table_sha256": sha256_file(table_path), "covariance_sha256": sha256_file(cov_path)},
        "files": {name: {"path": name, "sha256": sha256_file(root / name)} for name in ("table.csv", "cholesky.npy", "is_calibrator.npy")},
    }
    if (manifest["n_total"], manifest["n_calibrator"], manifest["n_hubble_flow"]) != (1701, 77, 277):
        raise RuntimeError(f"direct-ladder count mismatch: {manifest}")
    write_json(root / "manifest.json", manifest)
    multi = runtime / "data/multi_anchor"
    multi.mkdir(parents=True, exist_ok=True)
    payload = (B1_HEADER + "\n" + B1_ROW + "\n").encode("utf-8")
    with (multi / "B1_split_MB_augmented.csv.gz").open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            gz.write(payload)
    return {"manifest_sha256": sha256_file(root / "manifest.json"), "canonical_point_projection": "first frozen B1 row"}


def reconstruct_act_control(runtime: Path, fits_path: Path, source_root: Path) -> dict:
    act_dir = runtime / "share/act"
    act_dir.mkdir(parents=True, exist_ok=True)
    payload_path = act_dir / "act_dr6_cmbonly.bin"
    act_receipt = act_public_payload.reconstruct(fits_path, payload_path)
    if act_receipt["status"] != "verified":
        raise RuntimeError(f"ACT public reconstruction failed: {act_receipt}")
    from peer_platform.act_likelihood import load_act_likelihood
    like = load_act_likelihood(payload_path, expected_sha256=ACT_PAYLOAD_SHA256)
    arrays: dict[str, np.ndarray] = {}
    reproduced = []
    for pidx, key in enumerate(("tt", "te", "ee")):
        target = ACT_PROJECTED_CONTROL[pidx * 45:(pidx + 1) * 45]
        weights = np.asarray(like.weights[pidx], dtype=float)
        gram = weights.T @ weights
        ell_values = weights @ np.linalg.solve(gram, target)
        spectrum = np.zeros(9001, dtype=float)
        spectrum[np.asarray(like.ells, dtype=int)] = ell_values
        arrays[key] = spectrum
        reproduced.append(weights.T @ ell_values)
    reproduced_vector = np.concatenate(reproduced)
    projection_delta = float(np.max(np.abs(reproduced_vector - ACT_PROJECTED_CONTROL)))
    if projection_delta > 1.0e-9:
        raise RuntimeError(f"ACT sufficient-statistic reconstruction drift: {projection_delta}")
    np.savez_compressed(act_dir / "peer_n3_cls_lmax9000.npz", **arrays)
    projected = like.project_spectra(arrays)
    fit = like.fit_nuisance_specialized(projected)
    objective_delta = abs(float(fit.objective) - ACT_GOLDEN_OBJECTIVE)
    if objective_delta > 1.0e-8:
        raise RuntimeError(f"ACT golden objective mismatch after public reconstruction: {objective_delta}")
    golden = {
        "schema": "peer-act-dr6-cmbonly-golden-1",
        "test_id": "T-KPEER-ACTRD-004",
        "model": "PEER n=3",
        "dataset_sha256": ACT_PAYLOAD_SHA256,
        "source_fits_sha256": act_public_payload.EXPECTED_FITS_SHA256,
        "spectra": {
            "file": "peer_n3_cls_lmax9000.npz",
            "historical_spectra_sha256": ACT_SPECTRA_HISTORICAL_SHA256,
            "public_regression_representation": "deterministic ell-space preimage of identical 135 projected bandpowers",
        },
        "historical_reference": {"fit": {"objective": ACT_GOLDEN_OBJECTIVE, "A_act": ACT_GOLDEN_A, "P_act": ACT_GOLDEN_P}},
    }
    write_json(act_dir / "peer_n3_act.json", golden)
    config = {
        "schema": "peer-evaluation/v1", "name": "act-dr6-cmbonly-peer-n3-golden",
        "model": "peer_n3", "likelihood": "act_dr6_cmbonly",
        "inputs": {"payload": "share/act/act_dr6_cmbonly.bin", "spectra": "share/act/peer_n3_cls_lmax9000.npz", "golden": "share/act/peer_n3_act.json"},
        "repetitions": 3, "threads": 1,
    }
    write_json(runtime / "configs/likelihoods/act_dr6_peer_n3.json", config)
    return {"payload": act_receipt, "max_abs_projected_bandpower_delta": projection_delta, "objective_delta": objective_delta}


def write_runtime_contracts(runtime: Path) -> dict:
    like_dir = runtime / "manifests/likelihoods"
    like_dir.mkdir(parents=True, exist_ok=True)
    pantheon_compiled = runtime / "data/sn_data/PantheonPlus/compiled_v2"
    write_json(like_dir / "ACT_DR6_CMBONLY.json", {
        "schema": "peer-likelihood-manifest-1", "name": "ACT DR6 CMB-only TT/TE/EE", "status": "golden_pass",
        "location": {"payload_runtime_relative": "share/act/act_dr6_cmbonly.bin"},
        "fingerprints": {"official_source_fits_sha256": act_public_payload.EXPECTED_FITS_SHA256, "deterministic_payload_sha256": ACT_PAYLOAD_SHA256},
    })
    write_json(like_dir / "PANTHEON_PLUS.json", {
        "schema": "peer-likelihood-runtime/v2", "likelihood": "pantheon_plus", "status": "functional_optimized",
        "compiled_payload": {"path": "data/sn_data/PantheonPlus/compiled_v2", "manifest_sha256": sha256_file(pantheon_compiled / "manifest.json")},
    })
    write_json(like_dir / "PLANCK_2018_LOWL.json", {
        "schema": "peer-planck-lowl-runtime/v1", "status": "identity_verified_separately",
        "likelihoods": {"lowT": {"expected": -11.62573983}, "lowE": {"expected": -197.9897922}},
        "claim_boundary": "G15 regression manifest only; Planck payload identity is closed independently under G04",
    })
    write_json(like_dir / "SPT3G_D1_LITE.json", {
        "schema": "peer-likelihood-runtime/v1", "likelihood": "spt3g_d1_lite_ttteee", "status": "blocked_external_binary_transfer",
        "blocker": {"promotion_forbidden": True, "cause": "not part of ASCOM-00323 public regression fixture"},
    })

    # Strict integrity token for the files actually consumed by the 87-test public fixture.
    include_roots = [
        runtime / "configs/likelihoods",
        runtime / "manifests/likelihoods",
        runtime / "share/act",
        runtime / "data/sn_data/PantheonPlus/compiled_v2",
        runtime / "data/multi_anchor",
        runtime / "data/bao_data/desi_bao_dr2",
    ]
    files = []
    for root in include_roots:
        if not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            rel = path.relative_to(runtime).as_posix()
            files.append({"path": rel, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    if not files:
        raise RuntimeError("G15 integrity contract unexpectedly empty")
    write_json(runtime / "manifests/SESSION_INTEGRITY.json", {
        "schema": "peer-integrity-contract/v1", "files": files,
        "claim_boundary": "public clean-composite G15 regression fixture; scientific data identities are gated independently",
    })
    return {"integrity_files": len(files), "integrity_bytes": int(sum(x["size_bytes"] for x in files))}


def write_launcher(runtime: Path) -> None:
    launcher = runtime / "peer-likelihood-python"
    launcher.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\nBASE=$(CDPATH= cd -- \"$(dirname -- \"$0\")\" && pwd)\n"
        "PEER_PY=${PEER_PYTHON:-$(command -v python3)}\n"
        "if ! \"$PEER_PY\" -c 'import platform,sys; raise SystemExit(0 if platform.python_implementation()==\"CPython\" and sys.version_info[:2]==(3,12) else 1)' >/dev/null 2>&1; then\n"
        "  echo 'ERROR: PEER likelihood runtime requires CPython 3.12' >&2; exit 69; fi\n"
        "exec \"$PEER_PY\" \"$@\"\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)


def build_public_clean_composite(repo: Path, work: Path, act_fits: Path) -> tuple[Path, Path, dict]:
    source_root, source_provenance = registered_source.reconstruct_registered_source(repo, work / "registered-source")
    if source_provenance["archive_sha256"] != SOURCE_ARCHIVE_SHA256:
        raise RuntimeError("registered source archive identity drift")
    pantheon_cross_platform.install()
    bao, pan = closure.clone_data(work / "public-data")
    runtime, pantheon = closure.build_runtime(work / "public-runtime", bao, pan)
    raw_table = runtime / "data/sn_data/PantheonPlus/Pantheon+SH0ES.dat"
    removed = source_root / "removed/data/sn_data/PantheonPlus"
    removed.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw_table, removed / raw_table.name)
    no_shoes = compile_no_shoes(runtime)
    ladder = compile_direct_ladder(runtime)
    sys.path.insert(0, str(source_root))
    act = reconstruct_act_control(runtime, act_fits, source_root)
    contracts = write_runtime_contracts(runtime)
    write_launcher(runtime)
    return runtime, source_root, {
        "source": source_provenance,
        "pantheon": pantheon,
        "no_shoes": no_shoes,
        "direct_ladder": ladder,
        "act": act,
        "contracts": contracts,
        "public_sources": {"pantheon_commit": PANTHEON_COMMIT, "bao_commit": BAO_COMMIT},
    }


def run_exact_87(source_root: Path, runtime: Path, repo: Path) -> tuple[list[dict], int, bool]:
    env = os.environ.copy()
    env["PEER_LIKELIHOOD_RUNTIME_ROOT"] = str(runtime)
    env["PEER_LIKELIHOOD_SOURCES_ROOT"] = str(source_root)
    env["PEER_PYTHON"] = sys.executable
    env["PYTHONPATH"] = os.pathsep.join([str(source_root), str(repo / "scripts"), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = "1"
    records = []
    total = 0
    all_pass = True
    for module, expected in MODULES.items():
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", module, "-v"], cwd=source_root, env=env,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, errors="replace",
        )
        match = re.search(r"Ran\s+(\d+)\s+tests?", proc.stdout)
        observed = int(match.group(1)) if match else None
        passed = proc.returncode == 0 and observed == expected
        all_pass = all_pass and passed
        if observed is not None:
            total += observed
        records.append({
            "module": module, "expected_tests": expected, "observed_tests": observed,
            "returncode": proc.returncode, "status": "pass" if passed else "fail",
            "output_tail": proc.stdout[-8000:],
        })
    return records, total, all_pass and total == EXPECTED_TOTAL


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--act-fits", type=Path, required=True)
    ap.add_argument("--receipt", type=Path, required=True)
    args = ap.parse_args()
    repo = args.repo.resolve(); work = args.work.resolve(); work.mkdir(parents=True, exist_ok=True)
    runtime, source_root, provenance = build_public_clean_composite(repo, work, args.act_fits.resolve())
    records, total, verified = run_exact_87(source_root, runtime, repo)
    payload = {
        "gate_id": "G15", "schema": "ascom-00323-g15-public-clean-composite/v1",
        "status": "verified" if verified else "failed",
        "expected_total": EXPECTED_TOTAL, "observed_total": total,
        "modules": records, "provenance": provenance,
        "claim_boundary": "Exact registered 87-test source suite rerun from a public clean composite reconstructed from frozen source/data identities; Windows-specific gates are G01/G14/G16-G18.",
    }
    write_json(args.receipt.resolve(), payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if verified else 2


if __name__ == "__main__":
    raise SystemExit(main())
