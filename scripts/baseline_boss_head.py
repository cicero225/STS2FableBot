"""Label-sanity baseline for the PLAN §9 boss-conditional value head.

Question it answers: from the stage-0 dataset, is P(survive the act boss)
predictable at boss entry — and does the DECK carry signal beyond HP and boss
identity? (If not, the labels or the featurization are broken and stage 1
would be built on sand.)

Pure-python logistic regression (sts2bot.learn.logreg — no new deps), three
nested feature sets ablated:
  ctx   act + boss identity + entry hp_frac + max_hp
  deck  + catalog aggregates (type mix, cost curve, upgrade frac, n relics)
  full  + tag-table weighted provides-counts (drafttags lens)

Split is BY RUN (hash), never by row, so multi-boss runs can't leak.
Restricted to the dominant config era by default (--all-eras to override):
cross-era mixing is exactly the nested-feedback trap PLAN §9 warns about.

Usage: python scripts/baseline_boss_head.py [--datasets DIR] [--all-eras]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sts2bot.learn import logreg  # noqa: E402
from sts2bot.learn.features import deck_features  # noqa: E402
from sts2bot.policy.drafttags import load_draft_tags  # noqa: E402
from sts2bot.policy.forward import canonical_enemy_name  # noqa: E402

DS = ROOT / "logs" / "datasets"


def _rows(path: Path):
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _is_test(run_id: str) -> bool:
    return int(hashlib.md5(run_id.encode()).hexdigest(), 16) % 5 == 0


def build_examples(ds: Path, dominant_only: bool) -> list[dict]:
    runs = {r["run_id"]: r for r in _rows(ds / "runs.jsonl")}
    era = None
    if dominant_only:
        era = Counter(r["config_hash"] for r in runs.values()
                      if r["outcome_valid"]).most_common(1)[0][0]

    # deck snapshots: any decision row carries the deck at its seq
    snaps: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for table in ("drafts", "events", "rests"):
        for d in _rows(ds / f"{table}.jsonl"):
            if d.get("seq") is not None and d.get("deck"):
                snaps[d["run_id"]].append((d["seq"], d))
    for v in snaps.values():
        v.sort(key=lambda t: t[0])

    catalog = json.loads(
        (ROOT / "data" / "card_catalog.json").read_text(encoding="utf-8"),
    )["cards"]
    tags = load_draft_tags()

    examples = []
    for f in _rows(ds / "fights.jsonl"):
        if not (f["is_boss"] and f["outcome_valid"]):
            continue
        run = runs.get(f["run_id"])
        if run is None or (era and run["config_hash"] != era):
            continue
        if f.get("hp_end") is None or f.get("hp_start") is None:
            continue
        prior = [d for s, d in snaps.get(f["run_id"], [])
                 if f["seq_start"] is not None and s < f["seq_start"]]
        if not prior:
            continue
        last = prior[-1]
        boss = " + ".join(sorted({canonical_enemy_name(e)
                                  for e in f["enemies"]})) or "?"
        feats = deck_features(
            last["deck"], relics=last.get("relics"),
            hp=f["hp_start"], max_hp=f.get("max_hp") or last.get("max_hp"),
            act=f.get("act"), boss=boss, catalog=catalog, tags=tags)
        examples.append({
            "run_id": f["run_id"], "boss": boss, "act": f.get("act"),
            "y": 1 if f["hp_end"] > 0 else 0, "x": feats,
        })
    return examples


_SETS = {
    "boss-only": ("act", "boss:"),
    "hp-only": ("hp_frac", "max_hp"),
    "ctx": ("act", "hp_frac", "max_hp", "boss:"),
    "deck": ("act", "hp_frac", "max_hp", "boss:", "n_cards", "frac_upgraded",
             "n_relics", "type:", "cost:"),
    "full": ("act", "hp_frac", "max_hp", "boss:", "n_cards", "frac_upgraded",
             "n_relics", "type:", "cost:", "tag:"),
}


def _filter(x: dict, prefixes) -> dict:
    return {k: v for k, v in x.items()
            if any(k == p or (p.endswith(":") and k.startswith(p))
                   for p in prefixes)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", type=Path, default=DS)
    ap.add_argument("--all-eras", action="store_true")
    args = ap.parse_args()

    ex = build_examples(args.datasets, dominant_only=not args.all_eras)
    train_ex = [e for e in ex if not _is_test(e["run_id"])]
    test_ex = [e for e in ex if _is_test(e["run_id"])]
    base = sum(e["y"] for e in test_ex) / max(1, len(test_ex))
    lines = ["# Boss-head baseline (label sanity, PLAN §9 stage 0)", "",
             f"Examples: {len(ex)} boss fights "
             f"({len(train_ex)} train / {len(test_ex)} test, split by run); "
             f"test survival base rate {100 * base:.1f}%", ""]

    per_boss = Counter((e["boss"], e["y"]) for e in ex)
    bosses = sorted({e["boss"] for e in ex})
    lines += ["| boss | n | survive% |", "|---|---|---|"]
    for b in bosses:
        n = per_boss[(b, 0)] + per_boss[(b, 1)]
        lines.append(f"| {b} | {n} | {100 * per_boss[(b, 1)] / n:.0f}% |")
    lines.append("")

    # min-support pruning: a feature nonzero in <2% of train rows gets a tiny
    # std, so standardization inflates it into a huge weight fit to a handful
    # of runs (first run's top weights: shiv/frost/summon sources on IRONCLAD
    # decks — a few colorless pickups). Prune before training.
    support: Counter[str] = Counter()
    for e in train_ex:
        support.update(k for k, v in e["x"].items() if v)
    min_n = max(2, len(train_ex) // 50)
    rare = {k for k, n in support.items() if n < min_n and not k.startswith("boss:")}
    for e in ex:
        for k in rare:
            e["x"].pop(k, None)
    lines.append(f"(pruned {len(rare)} features with train support < {min_n})")
    lines.append("")

    full_model = None
    preds_by_set: dict[str, list[float]] = {}
    for name, prefixes in _SETS.items():
        xs = [_filter(e["x"], prefixes) for e in train_ex]
        ys = [e["y"] for e in train_ex]
        model = logreg.train(xs, ys, epochs=25)
        ps = [logreg.predict(model, _filter(e["x"], prefixes))
              for e in test_ex]
        preds_by_set[name] = ps
        yt = [e["y"] for e in test_ex]
        a = logreg.auc(yt, ps)
        brier = sum((p - y) ** 2 for p, y in zip(ps, yt, strict=True)) / len(yt)
        lines.append(f"- **{name}**: test AUC {a:.3f}, Brier {brier:.3f}")
        print(f"{name}: AUC {a:.3f} Brier {brier:.3f} "
              f"({len(model['features'])} features)")
        if name == "full":
            full_model = (model, ps, yt)

    # the setup question, directly: WITHIN one boss's fights, do deck features
    # rank survival better than entry HP alone? (boss identity is constant
    # within a row, so this isolates the deck's contribution)
    yt = [e["y"] for e in test_ex]
    lines += ["", "## Within-boss test AUC (hp-only vs full)", "",
              "| boss | n test | surv% | AUC hp-only | AUC full |",
              "|---|---|---|---|---|"]
    for b in bosses:
        idx = [i for i, e in enumerate(test_ex) if e["boss"] == b]
        if len(idx) < 25:
            continue
        yb = [yt[i] for i in idx]
        if not (0 < sum(yb) < len(yb)):
            continue
        a_hp = logreg.auc(yb, [preds_by_set["hp-only"][i] for i in idx])
        a_full = logreg.auc(yb, [preds_by_set["full"][i] for i in idx])
        lines.append(f"| {b} | {len(idx)} | {100 * sum(yb) / len(yb):.0f}% "
                     f"| {a_hp:.3f} | {a_full:.3f} |")

    model, ps, yt = full_model
    lines += ["", "## Calibration (full model, test quintiles)", "",
              "| predicted | actual | n |", "|---|---|---|"]
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    k = max(1, len(order) // 5)
    for q in range(0, len(order), k):
        idx = order[q:q + k]
        lines.append(f"| {sum(ps[i] for i in idx) / len(idx):.2f} "
                     f"| {sum(yt[i] for i in idx) / len(idx):.2f} "
                     f"| {len(idx)} |")

    ranked = sorted(zip(model["features"], model["w"], strict=True), key=lambda t: -abs(t[1]))
    lines += ["", "## Strongest weights (full model, standardized)", ""]
    lines += [f"- `{k}`: {w:+.2f}" for k, w in ranked[:20]]
    lines += [
        "", "## Caveats", "",
        "- Sanity baseline only: LINEAR model, so per-boss deck interactions "
        "(what 'setup' means) can only appear in the within-boss table, and a "
        "single global weight per tag can't specialize per boss — stage 1's "
        "GBT exists precisely for those interactions.",
        "- Within-boss test slices are small (25-92 rows); treat single-boss "
        "AUCs as direction, not measurement.",
        "- Entry HP partly ENCODES deck quality (good decks arrive healthy), "
        "so 'deck adds little over HP' understates the deck's causal role.",
        "- Survivorship: only decks that REACHED the boss are scored.",
    ]

    out = ROOT / "logs" / "reports" / "baseline_boss_head.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
