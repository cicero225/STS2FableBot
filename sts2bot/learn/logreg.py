"""Tiny dependency-free logistic regression for label sanity baselines.

Not a production model — stage 1 proper is gradient-boosted trees (PLAN §9).
This exists so the stage-0 dataset's labels can be validated end-to-end
(does the deck carry signal beyond HP?) without adding any dependency.
Deterministic: fixed-seed shuffling, no wall-clock anywhere.
"""

from __future__ import annotations

import math
import random


def _standardize(rows: list[dict[str, float]]):
    feats = sorted({k for r in rows for k in r})
    mean = {}
    std = {}
    for k in feats:
        vals = [r.get(k, 0.0) for r in rows]
        m = sum(vals) / len(vals)
        v = sum((x - m) ** 2 for x in vals) / len(vals)
        mean[k] = m
        std[k] = math.sqrt(v) or 1.0
    return feats, mean, std


def train(
    rows: list[dict[str, float]],
    ys: list[int],
    *,
    epochs: int = 40,
    lr: float = 0.05,
    l2: float = 1e-4,
    seed: int = 0,
) -> dict:
    """SGD logistic regression on feature dicts. Returns a plain-dict model."""
    feats, mean, std = _standardize(rows)
    xs = [[(r.get(k, 0.0) - mean[k]) / std[k] for k in feats] for r in rows]
    w = [0.0] * len(feats)
    b = 0.0
    rng = random.Random(seed)
    order = list(range(len(xs)))
    for _ in range(epochs):
        rng.shuffle(order)
        for i in order:
            z = b + sum(wj * xj for wj, xj in zip(w, xs[i], strict=True))
            p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
            g = p - ys[i]
            b -= lr * g
            for j, xj in enumerate(xs[i]):
                w[j] -= lr * (g * xj + l2 * w[j])
    return {"features": feats, "mean": mean, "std": std, "w": w, "b": b}


def predict(model: dict, row: dict[str, float]) -> float:
    z = model["b"] + sum(
        wj * (row.get(k, 0.0) - model["mean"][k]) / model["std"][k]
        for k, wj in zip(model["features"], model["w"], strict=True))
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def auc(ys: list[int], ps: list[float]) -> float:
    """Rank-based AUC (ties get half credit)."""
    pairs = sorted(zip(ps, ys, strict=True))
    n_pos = sum(ys)
    n_neg = len(ys) - n_pos
    if not n_pos or not n_neg:
        return float("nan")
    # rank sum for positives, average ranks over ties
    ranks: dict[int, float] = {}
    i = 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        r = (i + j + 1) / 2.0  # average 1-based rank of the tie block
        for k in range(i, j):
            ranks[k] = r
        i = j
    rank_sum = sum(r for k, r in ranks.items() if pairs[k][1] == 1)
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
