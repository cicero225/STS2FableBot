"""Pure-python inference over exported LightGBM tree dumps.

The training side (scripts/train_draft_value.py) needs lightgbm; the PLAYING
side must not — same pattern as the tag table: a script bakes an artifact,
the bot consumes plain JSON. Model files are gzip'd JSON:

  {"meta": {..., "feature_order": [...]},
   "heads": {"win": <lightgbm dump_model() dict>, "boss": <dump>}}

feature_order holds the REAL feature names (deck_features keys — "tag:aoe",
"boss:Aeonglass"); lightgbm itself is fed sanitized f0..fn names because its
dump chokes on special JSON characters, so the dump's own feature_names are
ignored here. Absent features are 0.0 (deck_features omits what's missing),
so NaN/default_left handling is never exercised — numeric "<=" splits only.
"""

from __future__ import annotations

import gzip
import json
import math
from pathlib import Path


def load_model(path: Path | str) -> dict:
    p = Path(path)
    raw = p.read_bytes()
    if p.suffix == ".gz" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def predict_raw(dump: dict, x: list[float]) -> float:
    """Sum of tree leaf values for a dense feature vector."""
    s = 0.0
    for t in dump["tree_info"]:
        node = t["tree_structure"]
        while "split_feature" in node:
            node = (node["left_child"]
                    if x[node["split_feature"]] <= node["threshold"]
                    else node["right_child"])
        s += node["leaf_value"]
    return s


def predict_proba(model: dict, head: str, feats: dict[str, float]) -> float:
    """P(label) from a feature dict for one head of a loaded model file."""
    order = model["meta"]["feature_order"]
    x = [feats.get(k, 0.0) for k in order]
    raw = predict_raw(model["heads"][head], x)
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, raw))))
