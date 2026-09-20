# PEER pNGB + AxionLike 015 Native Likelihood Battery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the frozen 015 fixed-endpoint native-likelihood battery for the exact 014 Lambda-free pNGB+AxionLike solution.

**Architecture:** Reuse the validated CAMB two-field patch from 014 to materialize immutable active/R1/R2 endpoint spectra and background observables once. Feed those endpoints into independently validated native likelihood adapters, profile only experiment-native nuisance parameters, classify the frozen gates, and persist full receipts.

**Tech Stack:** Python 3.12, CAMB 1.6.6, Fortran/gfortran, NumPy, SciPy, GitHub Actions, exact registered Planck/ACT/SPT/DESI/Pantheon likelihood assets.

**Spec:** `docs/superpowers/specs/2026-09-07-peer-axion-twofield-like-015-design.md`

## Global Constraints

- Scientific authority is Drive preregistration `1xUgIjdOoLEjAd6Vs45dodC8Elm5_THBqpgV9XeFQFTA`.
- Active/R1/R2 physical parameters are frozen; no cosmological or field profiling is allowed.
- Planck PR4 support is restricted to the registered compact continuous 30<=ell<=1000 contract.
- CMB experiments are never summed as independent evidence.
- Missing native resource/source/reference replay yields a typed blocker, never a surrogate likelihood.
- Heavy outputs must be uploaded as a workflow artifact for Drive persistence and Neon canonicalization after scientific readback.

---

### Task 1: Contract and gate unit tests

**Files:**
- Create: `tests/test_peer_axion_twofield_like_015.py`
- Create: `scripts/peer_015_contract.py`

**Interfaces:**
- Produces `MODEL_014`, `R1_MODEL`, `R2_MODEL`, `GateResult`, `classify_blocks(blocks)` and frozen constants for downstream scripts.

- [ ] Write tests that assert exact 014 constants, forbid cosmology-profile keys, assert `<+4` gate semantics, assert typed blocker propagation, and assert CMB scores are not summed.
- [ ] Run the test and verify RED because `scripts.peer_015_contract` does not exist.
- [ ] Implement the minimal immutable contract dataclasses and gate classifier.
- [ ] Run `pytest -q tests/test_peer_axion_twofield_like_015.py` and verify PASS.
- [ ] Commit.

### Task 2: Exact endpoint generation and 014 replay

**Files:**
- Create: `scripts/peer_015_endpoints.py`
- Reuse: `scripts/peer_axion_twofield_013_patch.py`
- Test: `tests/test_peer_axion_twofield_like_015.py`

**Interfaces:**
- Produces `generate_endpoints(output_dir) -> endpoint_manifest.json` containing active/R1/R2 CMB arrays, background observables, hashes and G1 replay metrics.

- [ ] Add failing tests for endpoint manifest schema, G1 tolerances and deterministic SHA helpers.
- [ ] Run tests and verify RED.
- [ ] Implement active/R1/R2 CAMB parameter builders using only frozen values from `peer_015_contract.py`.
- [ ] Export raw TT/TE/EE through ell=3200, lensing, BAO distances, SN luminosity-distance grid, rdrag/rstar/thetastar/H0, and deterministic SHA256 hashes.
- [ ] Repeat active generation with one thread and compare selected byte hashes.
- [ ] Run unit tests and the endpoint smoke command under patched CAMB.
- [ ] Commit.

### Task 3: Native likelihood adapter layer

**Files:**
- Create: `scripts/peer_015_likelihoods.py`
- Test: `tests/test_peer_axion_twofield_like_015.py`

**Interfaces:**
- Consumes endpoint manifest and environment-provided exact resource roots.
- Produces one `BlockResult` per `planck_pr4`, `act`, `spt_y1`, `desi_dr2`, `pantheon_noshoes` with status, Q/chi2 for active/R1/R2, nuisance receipt and resource hashes.

- [ ] Add failing tests for typed missing-resource blockers, no cosmology regeneration during nuisance profiling, and block result serialization.
- [ ] Implement DESI DR2 and Pantheon noSH0ES adapters using existing repo-supported public/canonical paths and exact covariance contracts.
- [ ] Implement SPT Y1 adapter by importing only the registered exact runtime; require `check_reference()` PASS before evaluation.
- [ ] Implement ACT adapter using the repo's current consumer-specific primary-CMB exact contract; fail closed if only a different ACT product is available.
- [ ] Implement Planck PR4 adapter using the registered compact CamSpec contract and exact asset hash; require reference-equivalence preflight.
- [ ] Run unit tests.
- [ ] Commit.

### Task 4: Scientific orchestrator and outputs

**Files:**
- Create: `scripts/run_peer_axion_twofield_like_015.py`
- Test: `tests/test_peer_axion_twofield_like_015.py`

**Interfaces:**
- Produces `result.json`, `blocks.csv`, `endpoint_manifest.json`, `resource_receipt.json` and terminal process code.

- [ ] Add a failing fixture-level test for G0-G8 classification and partial blocker handling.
- [ ] Implement preflight -> endpoints -> likelihood blocks -> gates -> claim-boundary result flow.
- [ ] Ensure scientific FAIL, resource BLOCKED, and execution FAILURE have distinct terminal statuses.
- [ ] Emit active-R1 deltas as gate statistics and active-R2 only as descriptive fixed-endpoint comparisons.
- [ ] Run all 015 tests.
- [ ] Commit.

### Task 5: GitHub Actions exact-runtime execution

**Files:**
- Create: `.github/workflows/peer-axion-twofield-like-015.yml`

**Interfaces:**
- Hydrates exact registered scientific resources, patches/compiles CAMB, runs tests and 015 battery, uploads artifact.

- [ ] Build workflow from the proven 014 CAMB compile flow.
- [ ] Add exact resource download/hydration steps with pinned hashes/reference checks for each native block.
- [ ] Run contract tests before scientific execution.
- [ ] Execute 015 with one-thread numerical settings.
- [ ] Upload `results/peer-axion-twofield-like-015/` even on scientific FAIL/BLOCKED so evidence survives.
- [ ] Open/update draft PR to trigger the workflow.
- [ ] Inspect full job logs and artifact; fix only implementation/runtime blockers without changing frozen science.

### Task 6: Scientific readback and canonical persistence

**Files:**
- No repository code changes unless a verified implementation bug is found.

- [ ] Download the final workflow artifact and verify its digest.
- [ ] Read `result.json` and independently recompute gate classification from block outputs.
- [ ] Create canonical Drive RESULT document with decision, metrics, blockers if any, resource hashes, GitHub provenance and claim boundary.
- [ ] Upload heavy artifact ZIP to the same canonical science folder.
- [ ] Upsert the test/revision/domain/provenance into Neon `science_v1` only after Drive readback.
- [ ] Query Neon to verify current revision and canonical provenance.
- [ ] Report only the verified scientific status.