# PEER pNGB + AxionLike 015 native-likelihood battery design

## Goal
Evaluate the exact Lambda-free two-field realization promoted by T-DE26-PEER-PNGB-AXION-NATIVE-2FIELD-RECAL-014 at frozen physical parameters against the exact registered native likelihood blocks in PREREG_T-DE26-PEER-PNGB-AXION-NATIVE-LIKE-BATTERY-015.

## Scientific contract
The authoritative preregistration is Drive document `1xUgIjdOoLEjAd6Vs45dodC8Elm5_THBqpgV9XeFQFTA`. This repository implementation must not change its active parameters, rivals, datasets, nuisance rules, thresholds, or claim boundary.

Active endpoint is the exact 014 solution. R1 is the same recalibrated early deformed-pNGB sector with standard Lambda closure. R2 is fixed matched LambdaCDM. Cosmological and scalar-field parameters are frozen. Only likelihood-native nuisance parameters are profiled.

## Architecture
The implementation is split into three responsibilities:

1. `peer_015_endpoints.py` installs the already validated native two-field CAMB patch, generates active/R1/R2 exact theory products, validates 014 replay tolerances, and writes one immutable endpoint bundle plus hashes.
2. `peer_015_likelihoods.py` consumes only that endpoint bundle and exact likelihood resources. Each block has an explicit adapter, self-test, nuisance profile, and typed blocker. It never regenerates cosmology during nuisance optimization.
3. `run_peer_axion_twofield_like_015.py` orchestrates preflight, endpoint generation, per-block likelihood evaluation, gate classification, deterministic replay, and a machine-readable result bundle.

The GitHub Actions workflow provides the runtime and immutable external resources. It must fail closed if a registered likelihood cannot be hydrated or its reference replay fails. A missing block yields `BLOCKED_NATIVE_LIKELIHOOD` for that block rather than a surrogate score.

## Likelihood blocks
- Planck PR4/NPIPE compact CamSpec, continuous 30<=ell<=1000 only.
- ACT current registered primary-CMB consumer-specific likelihood contract.
- SPT-3G Y1 TTTEEE exact likelihood.
- DESI DR2 official Gaussian BAO full covariance.
- Pantheon+ full covariance, SH0ES information excluded, with the registered additive SN magnitude nuisance treatment.

Planck, ACT and SPT primary CMB scores are reported separately and are not summed as independent evidence. DESI+Pantheon may be reported as a descriptive late-time sum under the preregistered independent-block approximation.

## Resource policy
Follow `NEXO · Science Resource Resolver V1 · 2026-09-04` exactly. Use exact asset hashes and registered reference replays. Do not reconstruct a scientific likelihood from prose if the native source/adapter cannot be pinned. Public download transport is acceptable only when the downloaded bytes are verified against the registered authority hash.

## Error model
Errors are typed as `EXECUTION_FAILURE`, `BLOCKED_NATIVE_LIKELIHOOD`, or scientific endpoint outcomes. Resource/import/hash/reference failures never become model FAILs. Per-block scientific stress is assigned only after the corresponding native likelihood and nuisance profile complete successfully.

## Testing
TDD tests cover frozen constants, no cosmological profiling, endpoint replay thresholds, typed blocker behavior, gate logic, CMB non-summing rule, late-time descriptive combination, and exact hash-based endpoint reuse. The Actions workflow additionally compiles patched CAMB 1.6.6 and executes the scientific battery.

## Persistence
The completed run produces JSON, CSV summaries, endpoint hashes and likelihood receipts as one workflow artifact. SCIENCE persists the heavy artifact and narrative result in Drive, then mirrors canonical metadata/provenance to Neon `science_v1` only after readback.