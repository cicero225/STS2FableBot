"""sts2bot.learn.gbt: dependency-free LightGBM-dump inference.

The playing side must never need lightgbm — these tests pin the hand-rolled
tree walker against a hand-built dump (exact values) and, when lightgbm is
importable, against the library's own predictions (parity).
"""

from __future__ import annotations

import gzip
import json
import math

import pytest

from sts2bot.learn import gbt

# two stumps: f0<=0.5 ? +1 : -1  and  f1<=2 ? +0.25 : +0.75
_DUMP = {"tree_info": [
    {"tree_structure": {
        "split_feature": 0, "threshold": 0.5, "decision_type": "<=",
        "left_child": {"leaf_value": 1.0},
        "right_child": {"leaf_value": -1.0}}},
    {"tree_structure": {
        "split_feature": 1, "threshold": 2.0, "decision_type": "<=",
        "left_child": {"leaf_value": 0.25},
        "right_child": {"leaf_value": 0.75}}},
]}


def test_predict_raw_walks_trees():
    assert gbt.predict_raw(_DUMP, [0.0, 0.0]) == 1.25
    assert gbt.predict_raw(_DUMP, [1.0, 3.0]) == -0.25


def test_predict_proba_uses_feature_order_and_sigmoid(tmp_path):
    model = {"meta": {"feature_order": ["hp_frac", "act"]},
             "heads": {"win": _DUMP}}
    p = tmp_path / "m.json.gz"
    p.write_bytes(gzip.compress(json.dumps(model).encode()))
    loaded = gbt.load_model(p)
    # absent features are 0.0: hp_frac=0 -> +1, act absent -> 0<=2 -> +0.25
    got = gbt.predict_proba(loaded, "win", {})
    assert got == pytest.approx(1 / (1 + math.exp(-1.25)))
    got = gbt.predict_proba(loaded, "win", {"hp_frac": 0.9, "act": 3})
    assert got == pytest.approx(1 / (1 + math.exp(0.25)))


def test_parity_with_lightgbm():
    lgb = pytest.importorskip("lightgbm")
    import numpy as np

    rng = np.random.default_rng(0)
    x = rng.normal(size=(500, 4))
    y = ((x[:, 0] + 0.5 * x[:, 1] * x[:, 2] + rng.normal(0, 0.3, 500)) > 0
         ).astype(int)
    booster = lgb.train(
        {"objective": "binary", "num_leaves": 7, "seed": 0, "verbosity": -1,
         "min_child_samples": 5},
        lgb.Dataset(x, label=y, feature_name=[f"f{i}" for i in range(4)]),
        num_boost_round=30)
    model = {"meta": {"feature_order": ["a", "b", "c", "d"]},
             "heads": {"win": booster.dump_model()}}
    theirs = booster.predict(x[:50])
    ours = [gbt.predict_proba(
        model, "win", dict(zip("abcd", row, strict=True))) for row in x[:50]]
    assert np.max(np.abs(np.array(ours) - theirs)) < 1e-9
