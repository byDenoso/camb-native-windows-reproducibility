from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
from pathlib import Path
from urllib.request import Request, urlopen

ACT_SOURCE_URL = (
    "https://lambda.gsfc.nasa.gov/data/act/pspipe/sacc_files/"
    "dr6_data_cmbonly.tar.gz"
)
EXPECTED_FITS_SHA256 = "c887dc9178d81f5e5e0ce76eca0cd3c9f089056630ab78a1cc4bb28ff8751c29"
USER_AGENT = "NEXO-T-DE26-PX-043/1.0"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def find_verified_fits(root: Path, expected_sha: str = EXPECTED_FITS_SHA256) -> Path:
    matches: list[Path] = []
    for path in sorted(root.rglob("*.fits")):
        if path.is_file() and sha256_file(path) == expected_sha:
            matches.append(path)
    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly one ACT DR6 FITS with sha256={expected_sha}; found {matches}"
        )
    return matches[0]


def download(url: str, destination: Path) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    if temp.exists():
        temp.unlink()
    h = hashlib.sha256()
    size = 0
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=180) as response, temp.open("wb") as handle:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            handle.write(block)
            h.update(block)
            size += len(block)
    temp.replace(destination)
    return {"url": url, "bytes": size, "sha256": h.hexdigest()}


def acquire(work: Path, output: Path, receipt: Path | None = None) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    archive = work / "dr6_data_cmbonly.tar.gz"
    extracted = work / "extracted"
    if extracted.exists():
        shutil.rmtree(extracted)
    extracted.mkdir(parents=True)

    archive_info = download(ACT_SOURCE_URL, archive)
    with tarfile.open(archive, "r:gz") as tf:
        tf.extractall(extracted, filter="data")

    source_fits = find_verified_fits(extracted)
    observed_sha = sha256_file(source_fits)
    if observed_sha != EXPECTED_FITS_SHA256:
        raise RuntimeError(
            f"ACT DR6 source hash mismatch: observed={observed_sha} expected={EXPECTED_FITS_SHA256}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_fits, output)
    output_sha = sha256_file(output)
    if output_sha != EXPECTED_FITS_SHA256:
        raise RuntimeError("copied ACT DR6 FITS failed identity verification")

    report = {
        "schema": "nexo-t-de26-px-043-act-acquisition/v1",
        "status": "verified",
        "source": "NASA/GSFC LAMBDA ACT DR6 CMB-only official likelihood payload",
        "source_url": ACT_SOURCE_URL,
        "archive": archive_info,
        "source_fits_relative_path": source_fits.relative_to(extracted).as_posix(),
        "fits_sha256": output_sha,
        "expected_fits_sha256": EXPECTED_FITS_SHA256,
        "output": str(output),
    }
    if receipt is not None:
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, default=Path(".r1/act-dr6-043"))
    parser.add_argument("--output", type=Path, default=Path(".r1/act_dr6_source.fits"))
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    report = acquire(args.work, args.output, args.receipt)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
