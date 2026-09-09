from __future__ import annotations

import sys
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "scripts/run_peer_axion_twofield_014.py")
    text = path.read_text()

    old = '''        p = active_params(f=f, m=m, late_amp=amp, cmb=False, transfer=False)\n        d = camb.get_background(p)\n'''
    new = '''        p = active_params(f=f, m=m, late_amp=amp, cmb=False, transfer=False)\n        with (OUT / "calibration_trace.jsonl").open("a") as _tf:\n            _tf.write(json.dumps({"phase": "late_closure_before", "f": f, "m": m, "amp": amp}) + "\\n")\n        print(f"TRACE late_closure_before f={f:.17g} m={m:.17g} amp={amp:.17g}", flush=True)\n        d = camb.get_background(p)\n'''
    text = replace_once(text, old, new, "late closure trace")

    old = '''        f = math.exp(float(logfm[0]))\n        m = math.exp(float(logfm[1]))\n        measure, amp_evals = _measure_common_background(f, m)\n'''
    new = '''        f = math.exp(float(logfm[0]))\n        m = math.exp(float(logfm[1]))\n        with (OUT / "calibration_trace.jsonl").open("a") as _tf:\n            _tf.write(json.dumps({"phase": "residual_before", "f": f, "m": m}) + "\\n")\n        print(f"TRACE residual_before f={f:.17g} m={m:.17g}", flush=True)\n        measure, amp_evals = _measure_common_background(f, m)\n        with (OUT / "calibration_trace.jsonl").open("a") as _tf:\n            _tf.write(json.dumps({"phase": "residual_after", "f": f, "m": m, "f_peak": measure["f_peak"], "log10_z_peak": measure["log10_z_peak"]}) + "\\n")\n'''
    text = replace_once(text, old, new, "residual trace")

    path.write_text(text)
    print("peer014 diagnostic trace instrumentation applied")


if __name__ == "__main__":
    main()
