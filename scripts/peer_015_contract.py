from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

TEST_ID = "T-DE26-PEER-PNGB-AXION-NATIVE-LIKE-BATTERY-015"
BLOCK_NAMES = ("planck_pr4", "act", "spt_y1", "desi_dr2", "pantheon_noshoes")

MODEL_014 = {
    "early": True,
    "late_axion": True,
    "lambda_closure": False,
    "eta": 0.1,
    "theta_early": 2.89155,
    "f_early": 0.1250578159382164,
    "m_early": 5.631907724965834e-55,
    "late_f": 1.0,
    "late_theta": math.pi - 0.8,
    "late_amp": 0.6170978019891916,
    "H0": 70.7950037531,
    "ombh2": 0.0229,
    "omch2": 0.1253,
    "ns": 0.99,
    "As": 2.1086e-9,
    "tau": 0.054,
    "YHe": 0.24610714079970886,
    "mnu": 0.06,
    "omk": 0.0,
}

R1_MODEL = {
    **MODEL_014,
    "early": True,
    "late_axion": False,
    "lambda_closure": True,
    "late_amp": None,
}

R2_MODEL = {
    **MODEL_014,
    "early": False,
    "late_axion": False,
    "lambda_closure": True,
    "f_early": None,
    "m_early": None,
    "late_amp": None,
}

FORBIDDEN_PROFILE_KEYS = frozenset(
    {
        "H0",
        "ombh2",
        "omch2",
        "ns",
        "As",
        "tau",
        "YHe",
        "mnu",
        "omk",
        "eta",
        "theta_early",
        "f_early",
        "m_early",
        "late_f",
        "late_theta",
        "late_amp",
    }
)


@dataclass(frozen=True)
class BlockResult:
    name: str
    status: str
    delta_active_r1: float | None
    delta_active_r2: float | None
    blocker: str | None = None

    def __post_init__(self) -> None:
        if self.name not in BLOCK_NAMES:
            raise ValueError(f"unknown 015 block: {self.name}")
        if self.status == "PASS":
            for value in (self.delta_active_r1, self.delta_active_r2):
                if value is None or not math.isfinite(float(value)):
                    raise ValueError("PASS block requires finite active deltas")
        elif self.status == "BLOCKED_NATIVE_LIKELIHOOD":
            if not self.blocker:
                raise ValueError("blocked likelihood requires typed blocker")
        else:
            raise ValueError(f"unsupported block status: {self.status}")


def classify_blocks(blocks: Mapping[str, BlockResult]) -> dict[str, object]:
    missing = [name for name in BLOCK_NAMES if name not in blocks]
    if missing:
        raise ValueError(f"missing 015 blocks: {missing}")

    gate_map = {
        "G2": "planck_pr4",
        "G3": "act",
        "G4": "spt_y1",
        "G5": "desi_dr2",
        "G6": "pantheon_noshoes",
    }
    out: dict[str, object] = {}
    blocked = False
    scientific_passes: list[bool] = []
    for gate, name in gate_map.items():
        block = blocks[name]
        if block.status == "BLOCKED_NATIVE_LIKELIHOOD":
            out[gate] = None
            blocked = True
            continue
        passed = float(block.delta_active_r1) < 4.0
        out[gate] = passed
        scientific_passes.append(passed)

    cmb = [blocks[name] for name in ("planck_pr4", "act", "spt_y1")]
    if all(block.status == "PASS" for block in cmb):
        out["cmb_worst_active_r1"] = max(float(block.delta_active_r1) for block in cmb)
    else:
        out["cmb_worst_active_r1"] = None

    late = [blocks["desi_dr2"], blocks["pantheon_noshoes"]]
    if all(block.status == "PASS" for block in late):
        out["late_descriptive_sum_active_r1"] = sum(float(block.delta_active_r1) for block in late)
    else:
        out["late_descriptive_sum_active_r1"] = None

    if blocked:
        out["G7"] = None
        out["G8"] = "BLOCKED_NATIVE_LIKELIHOOD"
    else:
        g7 = all(bool(out[gate]) for gate in gate_map)
        out["G7"] = g7
        out["G8"] = "ADVANCE_TO_LOCAL_PROFILE" if g7 else "LOCALIZED_ENDPOINT_STRESS"
    return out
