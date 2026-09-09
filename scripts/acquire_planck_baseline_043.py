from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

NAME = "COM_Likelihood_Data-baseline_R3.00.tar.gz"
EXPECTED_SHA = "0b73171e3acc671c28184466a45485a2d1c1d93676b832abdfe688c7b04024e6"
IRSA_INDEX = "https://irsa.ipac.caltech.edu/data/Planck/release_3/software/"
ESA = [
    "https://pla.esac.esa.int/pla/aio/product-action?COSMOLOGY.FILE_ID=" + NAME,
    "https://pla.esac.esa.int/pla-sl/data-action?COSMOLOGY.FILE_ID=" + NAME,
]
REQUIRED = [
    "plc_3.0/low_l/commander/commander_dx12_v3_2_29.clik",
    "plc_3.0/low_l/simall/simall_100x143_offlike5_EE_Aplanck_B.clik",
    "plc_3.0/hi_l/plik_lite/plik_lite_v22_TTTEEE.clik",
    "plc_3.0/lensing/smicadx12_Dec5_ftl_mv2_ndclpp_p_teb_consext8.clik_lensing",
]


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def get(url: str, timeout: int = 120):
    return urlopen(Request(url, headers={"User-Agent": "NEXO-DE26-043/1.0"}), timeout=timeout)


def download(out: Path) -> dict:
    candidates: list[tuple[str, str]] = []
    errors: list[dict] = []
    try:
        with get(IRSA_INDEX, 30) as response:
            html = response.read().decode("utf-8", "replace")
        parser = Links()
        parser.feed(html)
        for href in parser.hrefs:
            absolute = urljoin(IRSA_INDEX, href)
            if NAME.lower() in absolute.lower() or (
                "likelihood" in absolute.lower() and "baseline" in absolute.lower() and "r3.00" in absolute.lower()
            ):
                candidates.append(("NASA/IPAC IRSA PR3", absolute))
    except Exception as exc:
        errors.append({"source": "IRSA index", "error": repr(exc)})
    candidates.extend(("ESA Planck Legacy Archive", url) for url in ESA)
    seen: set[str] = set()
    unique = [(s, u) for s, u in candidates if not (u in seen or seen.add(u))]
    for source, url in unique:
        for attempt in range(1, 4):
            try:
                part = out.with_suffix(out.suffix + ".part")
                if part.exists():
                    part.unlink()
                h = hashlib.sha256()
                size = 0
                with get(url) as response, part.open("wb") as handle:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        handle.write(block)
                        h.update(block)
                        size += len(block)
                sha = h.hexdigest()
                if sha != EXPECTED_SHA:
                    raise RuntimeError(f"Planck archive SHA mismatch: {sha}")
                part.replace(out)
                return {"source": source, "url": url, "bytes": size, "sha256": sha, "errors": errors}
            except Exception as exc:
                errors.append({"source": source, "url": url, "attempt": attempt, "error": repr(exc)})
                if attempt < 3:
                    time.sleep(2 * attempt)
    raise RuntimeError(json.dumps(errors, indent=2))


def extract(archive: Path, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    markers = ("plc_3.0/low_l/", "plc_3.0/hi_l/plik_lite/", "plc_3.0/lensing/")
    with tarfile.open(archive, "r:gz") as tf:
        members = []
        for original in tf.getmembers():
            if not original.isfile():
                continue
            norm = original.name.replace("\\", "/").lstrip("./")
            selected = None
            for marker in markers:
                pos = norm.find(marker)
                if pos >= 0:
                    selected = norm[pos:]
                    break
            if selected is not None:
                original.name = selected
                members.append(original)
        tf.extractall(root, members=members, filter="data")
    missing = [path for path in REQUIRED if not (root / path).exists()]
    if missing:
        raise RuntimeError(f"Planck extraction missing required paths: {missing}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--receipt", type=Path, required=True)
    args = ap.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    archive = args.work / NAME
    selected = download(archive)
    extract_root = args.work / "planck"
    extract(archive, extract_root)
    receipt = {
        "schema": "nexo-planck-baseline-043/v1",
        "status": "verified",
        "expected_sha256": EXPECTED_SHA,
        "archive": str(archive),
        "planck_root": str(extract_root / "plc_3.0"),
        "required_paths": REQUIRED,
        **selected,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
