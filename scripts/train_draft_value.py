"""Stage 1 (PLAN §9): train the draft/event value model and export it.

V(run state) = P(win | deck, relics, hp, act, floor, act boss) as a LightGBM
binary model, plus the boss-conditional head P(beat current act boss | same).
Draft candidates are then scored as ΔV = V(deck + card) - V(deck) — the
"pick model as a delta over the shared value head" ruling, which sidesteps
the off-policy problem (we only ever observe the chosen pick's outcome, but
we observe VALUES for every deck the bot ever held).

Training needs lightgbm (`pip install -e .[learn]`); the exported artifact
(data/models/draft_value_v1.json.gz) is plain JSON consumed by the
dependency-free predictor in sts2bot.learn.gbt — the bot never imports
lightgbm. Dominant config era only; split by run (sts2bot.learn.data).

Also emits an offline eval (logs/reports/draft_value_v1.md): head AUCs vs
the logreg baseline, pure-python-vs-lightgbm verification, and the ΔV draft
analysis (agreement with the bot's picks + top disagreement cards — the
reviewable substrate for deciding the blend weight).

Usage: python scripts/train_draft_value.py [--datasets DIR] [--out FILE]
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402  (arrives with lightgbm)

from sts2bot.learn import gbt, logreg  # noqa: E402
from sts2bot.learn.data import is_test_run, jsonl_rows  # noqa: E402
from sts2bot.learn.features import deck_features  # noqa: E402
from sts2bot.policy.drafttags import load_draft_tags  # noqa: E402

DS = ROOT / "logs" / "datasets"
OUT = ROOT / "data" / "models" / "draft_value_v1.json.gz"

# Regularized hard: rows within a run are highly correlated (deck evolves
# slowly), so the EFFECTIVE sample is ~2.2k runs, not ~60k rows — the first
# 300x31 fit memorized run identity (train AUC .989 / test .634). Small
# leaves + big min_child + per-run row weights + early stopping on a by-run
# validation fold.
PARAMS = {
    "objective": "binary",
    "num_leaves": 15,
    "learning_rate": 0.03,
    "min_child_samples": 200,
    "lambda_l2": 10.0,
    "feature_fraction": 0.7,
    "bagging_fraction": 0.7,
    "bagging_freq": 1,
    "seed": 0,
    "deterministic": True,
    "force_row_wise": True,
    "num_threads": 4,
    "verbosity": -1,
}
MAX_TREES = 2000
EARLY_STOP = 100


def _is_val_run(run_id: str) -> bool:
    """20% of TRAIN runs, for early stopping (salted so it never overlaps the
    test split definition in learn.data)."""
    import hashlib
    return int(hashlib.md5((run_id + "|val").encode()).hexdigest(), 16) % 5 == 0


def build_rows(ds: Path) -> tuple[list[dict], str]:
    runs = {r["run_id"]: r for r in jsonl_rows(ds / "runs.jsonl")}
    era = Counter(r["config_hash"] for r in runs.values()
                  if r["outcome_valid"]).most_common(1)[0][0]
    catalog = json.loads(
        (ROOT / "data" / "card_catalog.json").read_text(encoding="utf-8"),
    )["cards"]
    tags = load_draft_tags()
    rows = []
    for table in ("drafts", "events", "rests"):
        for d in jsonl_rows(ds / f"{table}.jsonl"):
            if not d.get("outcome_valid") or d.get("config_hash") != era:
                continue
            if not d.get("deck") or d.get("victory") is None:
                continue
            feats = deck_features(
                d["deck"], relics=d.get("relics"), hp=d.get("hp"),
                max_hp=d.get("max_hp"), act=d.get("act"),
                boss=d.get("act_boss"), catalog=catalog, tags=tags)
            if d.get("floor") is not None:
                feats["floor"] = float(d["floor"])
            rows.append({
                "run_id": d["run_id"], "table": table, "x": feats,
                "y_win": int(d["victory"]),
                "y_boss": (None if d.get("beat_act_boss") is None
                           else int(d["beat_act_boss"])),
                "raw": d if table == "drafts" else None,
            })
    return rows, era


def _matrix(rows, order):
    idx = {k: i for i, k in enumerate(order)}
    m = np.zeros((len(rows), len(order)))
    for i, r in enumerate(rows):
        for k, v in r.items():
            j = idx.get(k)
            if j is not None:
                m[i, j] = v
    return m


def _auc_cal(yt, ps):
    a = logreg.auc(list(yt), list(ps))
    order = np.argsort(ps)
    k = max(1, len(order) // 5)
    cal = [(float(np.mean([ps[i] for i in idx])),
            float(np.mean([yt[i] for i in idx])), len(idx))
           for idx in (order[q:q + k] for q in range(0, len(order), k))]
    return a, cal


def main() -> int:
    import lightgbm as lgb

    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", type=Path, default=DS)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    rows, era = build_rows(args.datasets)
    order = sorted({k for r in rows for k in r["x"]})
    sanitized = [f"f{i}" for i in range(len(order))]
    train = [r for r in rows if not is_test_run(r["run_id"])]
    test = [r for r in rows if is_test_run(r["run_id"])]
    run_rows = Counter(r["run_id"] for r in rows)
    print(f"era {era}: {len(train)} train / {len(test)} test rows, "
          f"{len(order)} features")
    lines = ["# draft_value_v1 — stage 1 value heads", "",
             f"Era {era}; {len(train)} train / {len(test)} test rows "
             f"(split by run); {len(order)} features; LightGBM "
             f"{PARAMS['num_leaves']} leaves, early-stopped, per-run row "
             "weights.", ""]

    heads: dict[str, dict] = {}
    boosters: dict[str, object] = {}
    best_iters: dict[str, int] = {}
    for head in ("win", "boss"):
        key = f"y_{head}"
        fit = [r for r in train
               if r[key] is not None and not _is_val_run(r["run_id"])]
        val = [r for r in train
               if r[key] is not None and _is_val_run(r["run_id"])]
        te = [r for r in test if r[key] is not None]
        xfit = _matrix([r["x"] for r in fit], order)
        xval = _matrix([r["x"] for r in val], order)
        xte = _matrix([r["x"] for r in te], order)
        # each RUN contributes ~equally regardless of how long it lived
        wfit = np.array([1.0 / run_rows[r["run_id"]] for r in fit])
        wval = np.array([1.0 / run_rows[r["run_id"]] for r in val])
        dfit = lgb.Dataset(xfit, label=np.array([r[key] for r in fit]),
                           weight=wfit, feature_name=sanitized)
        dval = lgb.Dataset(xval, label=np.array([r[key] for r in val]),
                           weight=wval, reference=dfit)
        booster = lgb.train(
            PARAMS, dfit, num_boost_round=MAX_TREES, valid_sets=[dval],
            callbacks=[lgb.early_stopping(EARLY_STOP, verbose=False)])
        best_iters[head] = booster.best_iteration
        yte = np.array([r[key] for r in te])
        a_te, cal = _auc_cal(yte, booster.predict(xte))
        a_fit, _ = _auc_cal(np.array([r[key] for r in fit]),
                            booster.predict(xfit))
        base = float(yte.mean())
        print(f"{head}: test AUC {a_te:.3f} (train {a_fit:.3f}), "
              f"{booster.best_iteration} trees, base {base:.3f}")
        lines += [f"## {head} head", "",
                  f"- test AUC **{a_te:.3f}** (train {a_fit:.3f}; "
                  f"{booster.best_iteration} trees; "
                  f"base rate {100 * base:.1f}%, n {len(te)})",
                  "- calibration (test quintiles, predicted -> actual): "
                  + ", ".join(f"{p:.2f}->{a:.2f}" for p, a, _ in cal), ""]
        heads[head] = booster.dump_model()
        boosters[head] = booster

    model = {
        "meta": {
            "name": "draft_value_v1", "era": era,
            "feature_order": order,
            "n_train": len(train), "params": PARAMS, "n_trees": best_iters,
            "labels": {"win": "victory", "boss": "beat_act_boss"},
        },
        "heads": heads,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(gzip.compress(
        json.dumps(model, separators=(",", ":")).encode("utf-8"), 9))
    size_mb = args.out.stat().st_size / 1e6
    print(f"wrote {args.out} ({size_mb:.2f} MB)")

    # verify the dependency-free predictor against lightgbm itself
    loaded = gbt.load_model(args.out)
    sample = test[:200]
    xs = _matrix([r["x"] for r in sample], order)
    for head in ("win", "boss"):
        ours = np.array([gbt.predict_proba(loaded, head, r["x"])
                         for r in sample])
        theirs = boosters[head].predict(xs)
        diff = float(np.max(np.abs(ours - theirs)))
        assert diff < 1e-9, f"{head} predictor mismatch: {diff}"
    lines += [f"Pure-python predictor verified vs lightgbm on "
              f"{len(sample)} rows (max |diff| < 1e-9). "
              f"Artifact {size_mb:.2f} MB.", ""]
    print("pure-python predictor verified")

    # ΔV draft analysis on test-set draft rows: does each head's delta agree
    # with the bot's hand-tuned picks, and where not, on which cards? (The
    # boss head is the closer horizon — likely the better pick signal.)
    drafts = [r for r in test if r["raw"] is not None]
    cand_feats: list[list[dict]] = []
    for r in drafts:
        d = r["raw"]
        per = []
        for o in d["offers"]:
            f2 = dict(deck_features(
                [*d["deck"], o["key"]], relics=d.get("relics"),
                hp=d.get("hp"), max_hp=d.get("max_hp"), act=d.get("act"),
                boss=d.get("act_boss"), catalog=_CATALOG, tags=_TAGS))
            if d.get("floor") is not None:
                f2["floor"] = float(d["floor"])
            per.append(f2)
        cand_feats.append(per)

    lines += ["## ΔV draft analysis (test drafts)", ""]
    for head in ("win", "boss"):
        booster = boosters[head]
        agree = n_scored = n_zero = 0
        dv_stats: list[float] = []
        by_card: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for r, per in zip(drafts, cand_feats, strict=True):
            d = r["raw"]
            cands = [o["key"] for o in d["offers"]]
            vs = booster.predict(_matrix([r["x"], *per], order))
            dvs = [float(v - vs[0]) for v in vs[1:]]
            dv_stats.extend(dvs)
            n_zero += sum(1 for v in dvs if v == 0.0)
            best_i = int(np.argmax(dvs))
            model_pick = cands[best_i]
            if d.get("can_skip") and dvs[best_i] < 0:
                model_pick = None
            n_scored += 1
            if model_pick == d.get("picked"):
                agree += 1
            ranked = sorted(range(len(cands)), key=lambda i: -dvs[i])
            for rank_pos, i in enumerate(ranked):
                by_card[cands[i].rstrip("+")].append(
                    (rank_pos == 0, cands[i] == (d.get("picked") or "")))
        dv = np.array(dv_stats)
        lines += [f"### {head}-head ΔV", "",
                  f"- {n_scored} drafts; model pick == bot pick on "
                  f"**{100 * agree / max(1, n_scored):.1f}%**; exact-zero ΔV "
                  f"on {100 * n_zero / max(1, len(dv_stats)):.1f}% of "
                  "candidates (piecewise-constant trees)",
                  f"- ΔV distribution: mean {dv.mean():+.4f}, "
                  f"std {dv.std():.4f}, p5 {np.percentile(dv, 5):+.4f}, "
                  f"p95 {np.percentile(dv, 95):+.4f} (blend-scale reference)",
                  ""]
        dis = []
        for card, pairs in by_card.items():
            if len(pairs) < 15:
                continue
            m = sum(a for a, _ in pairs) / len(pairs)
            b = sum(x for _, x in pairs) / len(pairs)
            dis.append((m - b, card, m, b, len(pairs)))
        dis.sort()
        lines += ["Top disagreements (model top-1 rate vs bot pick rate, "
                  "min 15 offers):", "",
                  "| card | offers | model top-1 | bot picked |",
                  "|---|---|---|---|"]
        for _gap, card, m, b, n in (*dis[:8], *dis[-8:]):
            lines.append(
                f"| {card} | {n} | {100 * m:.0f}% | {100 * b:.0f}% |")
        lines.append("")

    rpt = ROOT / "logs" / "reports" / "draft_value_v1.md"
    rpt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {rpt}")
    return 0


# module-level so the ΔV loop can reuse them (populated in build_rows' scope
# would be cleaner; kept simple: load once here)
_CATALOG = json.loads(
    (ROOT / "data" / "card_catalog.json").read_text(encoding="utf-8"))["cards"]
_TAGS = load_draft_tags()


if __name__ == "__main__":
    raise SystemExit(main())
