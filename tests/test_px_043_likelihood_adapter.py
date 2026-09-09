from __future__ import annotations

import numpy as np

from px_043_likelihood import build_cmb_clipy_cls, build_lensing_clipy_cls


def test_cmb_clipy_order_is_tt_ee_bb_te_tb_eb() -> None:
    raw = np.zeros((6, 4), dtype=float)
    raw[:, 0] = [10, 11, 12, 13, 14, 15]
    raw[:, 1] = [20, 21, 22, 23, 24, 25]
    raw[:, 2] = [30, 31, 32, 33, 34, 35]
    raw[:, 3] = [40, 41, 42, 43, 44, 45]
    out = build_cmb_clipy_cls(raw)
    assert out.shape == (6, 6)
    assert np.all(out[0, :4] == raw[:, 0])
    assert np.all(out[1, :4] == raw[:, 1])
    assert np.all(out[2, :4] == raw[:, 2])
    assert np.all(out[3, :4] == raw[:, 3])
    assert np.all(out[4] == 0.0)
    assert np.all(out[5] == 0.0)


def test_lensing_clipy_order_starts_pp_then_cmb() -> None:
    raw = np.zeros((5, 4), dtype=float)
    raw[:, 0] = [1, 2, 3, 4, 5]
    raw[:, 1] = [6, 7, 8, 9, 10]
    raw[:, 2] = [11, 12, 13, 14, 15]
    raw[:, 3] = [16, 17, 18, 19, 20]
    pp = np.arange(5, dtype=float) + 100.0
    out = build_lensing_clipy_cls(raw, pp)
    assert out.shape == (7, 5)
    assert np.all(out[0] == pp)
    assert np.all(out[1] == raw[:, 0])
    assert np.all(out[2] == raw[:, 1])
    assert np.all(out[3] == raw[:, 2])
    assert np.all(out[4] == raw[:, 3])
    assert np.all(out[5:] == 0.0)
