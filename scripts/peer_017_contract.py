from __future__ import annotations

import math
from typing import Iterable, Mapping

TEST_ID = "T-DE26-PEER-PNGB-AXION-ACTTRAIN-SPTHOLDOUT-017"
PREREG_DRIVE_ID = "1EEiGZrlZT42UesVsEF9N3f2Pf1zAV15YPFVrhDAO2Ck"
TEST_FOLDER_ID = "175ecE5-8vXM8l9t_OR7i8_qbUXP-SA2K"
OFFICIAL_CAMB_COMMIT = "3ef0272d6f7ba1231128872e56e6d4c12af8267b"
SPT_DATA_COMMIT = "bfe809a140087d19412aa6bc8c8d4ba18840b315"
SPT_CANDL_VERSION = "2.0.3"
SPT_OFFICIAL_TEST_LOGL = -83.20924274
SPT_HOLDOUT_THRESHOLD = 4.0
ACT_PAYLOAD_SHA256 = "d3ca3ff9427ecb22141df32fb6b4398d3f9a3dcb1a10d22344b33c56a12b6484"
ACT_014_GOLDEN_DELTA = 27.027222181083687
ACT_014_GOLDEN_ACTIVE_OBJECTIVE = 195.85443789889788
ACT_014_GOLDEN_R1_OBJECTIVE = 168.8272157178142

F_VALUES = (1.0, 1.5, 2.0, 3.0)
DELTA_VALUES = (0.10, 0.20, 0.35, 0.50, 0.80)
TRAINING_GRID = tuple((f, delta) for f in F_VALUES for delta in DELTA_VALUES)


def choose_winner(rows: Iterable[Mapping[str, object]]) -> dict[str, object]:
    eligible = [dict(row) for row in rows if bool(row.get("eligible"))]
    eligible = [row for row in eligible if math.isfinite(float(row["delta_q_act"]))]
    if not eligible:
        raise ValueError("no eligible ACT-training cells")
    best = min(float(row["delta_q_act"]) for row in eligible)
    tie = [row for row in eligible if float(row["delta_q_act"]) <= best + 0.25]
    # Frozen tiebreak: larger delta first, then larger f. If still tied, lower ACT score.
    tie.sort(key=lambda row: (-float(row["late_delta"]), -float(row["late_f"]), float(row["delta_q_act"])))
    return tie[0]


def classify_holdout(delta_q_spt: float) -> str:
    value = float(delta_q_spt)
    if not math.isfinite(value):
        raise ValueError("non-finite SPT holdout contrast")
    return "PASS_ACTTRAIN_SPT_HOLDOUT_EXISTENCE" if value < SPT_HOLDOUT_THRESHOLD else "FAIL_SPT_HOLDOUT"
