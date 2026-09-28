"""Stage 2 (PLAN section 9, owner-approved 2026-09-28): the OFFER-unit pick model.

Unit = one offered card at one draft screen (every offer, picked or not): the
intention-to-treat framing of scripts/offer_counterfactuals.py, so the bot's
own picks cannot confound the labels. Features = the deck-state lens
(sts2bot.learn.features.deck_features) + the offered card (id one-hot,
type/rarity/cost, tag provides). Labels are DENSE, not the 10%-of-runs win:

  boss  : beat_act_boss   (binary; ~40-60% base)     -> LightGBM binary head
  hp3   : hp_delta_next3  (HP over the next 3 fights) -> LightGBM regression head
  win   : victory         (binary; kept for reference)

Reports (logs/reports/<name>.md): per-head test metrics on the run split,
shadow-ranker agreement with the bot's picks, and a sanity check that the
model's per-card mean score recovers the model-free ITT ranking. Nothing here
is wired into drafting: the deployment path is a SHADOW re-ranker for several
batches first (log the model's pick beside the bot's; score disagreements on
the counterfactual basis).

Era selection: --since (run started_at date) and/or --code-heads (comma list
of meta code_head values) -- the fixed-code era begins 2026-09-11 (shop fix +
observed capability pricing). lightgbm is the [learn] extra; the bot never
imports it (pure-python predictor in sts2bot.learn.gbt).
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from train_draft_value import EARLY_STOP, MAX_TREES, PARAMS, _is_val_run, _matrix  # noqa: E402

from sts2bot.learn import gbt, logreg  # noqa: E402
from sts2bot.learn.data import is_test_run, jsonl_rows  # noqa: E402
from sts2bot.learn.features import deck_features  # noqa: E402
from sts2bot.policy.drafttags import load_draft_tags  # noqa: E402

DS = ROOT / "logs" / "datasets"
OUT = ROOT / "data" / "models" / "offer_model_v1.json.gz"


def card_features(offer: dict, tags: dict) -> dict[str, float]:
    key = offer.get("key") or ""
    base = key.rstrip("+")
    f: dict[str, float] = {f"card:{base}": 1.0, "cupg": 1.0 if key.endswith("+") else 0.0}
    if offer.get("type"):
        f[f"ctype:{str(offer['type']).lower()}"] = 1.0
    if offer.get("rarity"):
        f[f"crarity:{str(offer['rarity']).lower()}"] = 1.0
    cost = str(offer.get("cost") or "")
    bucket = (cost if cost in ("0", "1", "2")
              else "x" if cost.upper() == "X" else "3plus" if cost else "none")
    f[f"ccost:{bucket}"] = 1.0
    entry = tags.get(base.upper()) or {}
    for tag, w in (entry.get("provides") or {}).items():
        f[f"ctag:{tag}"] = float(w)
    needs = entry.get("needs") or {}
    if isinstance(needs, dict):  # the tag table stores needs as a list of tags or a weighted dict
        for tag, w in needs.items():
            f[f"cneed:{tag}"] = float(w)
    else:
        for tag in needs:
            f[f"cneed:{tag if isinstance(tag, str) else tag.get('tag', '')}"] = 1.0
    return f


def build_rows(ds: Path, since: str | None, code_heads: set[str] | None):
    runs = {r["run_id"]: r for r in jsonl_rows(ds / "runs.jsonl")}
    catalog = json.loads(
        (ROOT / "data" / "card_catalog.json").read_text(encoding="utf-8"))["cards"]
    tags = load_draft_tags()
    rows = []
    n_drafts = 0
    for d in jsonl_rows(ds / "drafts.jsonl"):
        run = runs.get(d["run_id"]) or {}
        if not d.get("outcome_valid") or d.get("victory") is None:
            continue
        if since and (run.get("started_at") or "") < since:
            continue
        if code_heads and run.get("code_head") not in code_heads:
            continue
        if not d.get("offers"):
            continue
        n_drafts += 1
        deck = deck_features(
            d.get("deck") or [], relics=d.get("relics"), hp=d.get("hp"),
            max_hp=d.get("max_hp"), act=d.get("act"), boss=d.get("act_boss"),
            catalog=catalog, tags=tags)
        if d.get("floor") is not None:
            deck["floor"] = float(d["floor"])
        for i, off in enumerate(d["offers"]):
            x = dict(deck)
            x.update(card_features(off, tags))
            rows.append({
                "run_id": d["run_id"], "draft": (d["run_id"], d["seq"]),
                "card": (off.get("key") or "").rstrip("+"), "offer_index": i,
                "picked": off.get("key") == d.get("picked"),
                "x": x,
                "y_boss": None if d.get("beat_act_boss") is None else int(d["beat_act_boss"]),
                "y_hp3": None if d.get("hp_delta_next3") is None else float(d["hp_delta_next3"]),
                "y_win": int(d["victory"]),
            })
    return rows, n_drafts


def _rank_corr(a: list[float], b: list[float]) -> float:
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for rank, i in enumerate(order):
            r[i] = float(rank)
        return r
    if len(a) < 3:
        return float("nan")
    return statistics.correlation(ranks(a), ranks(b))


def main() -> int:
    import numpy as np

    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", type=Path, default=DS)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--report", default="offer_model_v1.md")
    ap.add_argument("--since", default=None, help="run started_at >= YYYY-MM-DD")
    ap.add_argument("--code-heads", default=None, help="comma-separated meta code_head values")
    ap.add_argument("--min-card-offers", type=int, default=20)
    args = ap.parse_args()
    heads_filter = set(args.code_heads.split(",")) if args.code_heads else None

    rows, n_drafts = build_rows(args.datasets, args.since, heads_filter)
    n_runs = len({r["run_id"] for r in rows})
    if not rows:
        print("no rows for that era selection")
        return 1
    order = sorted({k for r in rows for k in r["x"]})
    sanitized = [f"f{i}" for i in range(len(order))]
    train = [r for r in rows if not is_test_run(r["run_id"])]
    test = [r for r in rows if is_test_run(r["run_id"])]
    run_rows = Counter(r["run_id"] for r in rows)
    print(f"{n_runs} runs, {n_drafts} drafts, {len(rows)} offer rows "
          f"({len(train)} train / {len(test)} test), {len(order)} features")
    lines = ["# offer_model_v1 -- stage 2 offer-unit pick model", "",
             f"Era: since={args.since} code_heads={args.code_heads}; {n_runs} runs, "
             f"{n_drafts} drafts, {len(rows)} offer rows ({len(train)} train / "
             f"{len(test)} test, split by run); {len(order)} features. Unit = one "
             "offered card (ITT framing: picked or not). LightGBM, per-run row "
             "weights, early-stopped on a run-salted validation fifth.", ""]

    try:
        import lightgbm as lgb
    except ImportError:
        print("lightgbm missing: pip install -e .[learn]")
        return 1

    heads: dict[str, dict] = {}
    boosters: dict[str, object] = {}
    n_trees: dict[str, int] = {}
    specs = {"boss": ("y_boss", "binary"), "hp3": ("y_hp3", "regression"),
             "win": ("y_win", "binary")}
    for head, (key, objective) in specs.items():
        fit = [r for r in train if r[key] is not None and not _is_val_run(r["run_id"])]
        val = [r for r in train if r[key] is not None and _is_val_run(r["run_id"])]
        te = [r for r in test if r[key] is not None]
        if len(fit) < 200 or len(val) < 50 or len(te) < 50:
            lines += [f"## {head} head", "",
                      f"- skipped: too few rows (fit {len(fit)}, val {len(val)}, "
                      f"test {len(te)})", ""]
            print(f"{head}: skipped (fit {len(fit)} val {len(val)} test {len(te)})")
            continue
        params = dict(PARAMS, objective=objective)
        if objective == "regression":
            params["metric"] = "l2"
        xfit, xval, xte = (_matrix([r["x"] for r in part], order) for part in (fit, val, te))
        wfit = np.array([1.0 / run_rows[r["run_id"]] for r in fit])
        wval = np.array([1.0 / run_rows[r["run_id"]] for r in val])
        dfit = lgb.Dataset(xfit, label=np.array([r[key] for r in fit]), weight=wfit,
                           feature_name=sanitized)
        dval = lgb.Dataset(xval, label=np.array([r[key] for r in val]), weight=wval,
                           reference=dfit)
        booster = lgb.train(params, dfit, num_boost_round=MAX_TREES, valid_sets=[dval],
                            callbacks=[lgb.early_stopping(EARLY_STOP, verbose=False)])
        n_trees[head] = booster.best_iteration
        yte = np.array([r[key] for r in te])
        pte = booster.predict(xte)
        if objective == "binary":
            a_te = logreg.auc([int(v) for v in yte], list(pte))
            a_fit = logreg.auc([int(r[key]) for r in fit], list(booster.predict(xfit)))
            base = float(yte.mean())
            print(f"{head}: test AUC {a_te:.3f} (train {a_fit:.3f}), "
                  f"{booster.best_iteration} trees, base {base:.3f}")
            lines += [f"## {head} head (binary)", "",
                      f"- test AUC **{a_te:.3f}** (train {a_fit:.3f}; "
                      f"{booster.best_iteration} trees; "
                      f"base rate {100 * base:.1f}%, n {len(te)})", ""]
        else:
            rmse = float(np.sqrt(np.mean((pte - yte) ** 2)))
            sd = float(np.std(yte))
            corr = float(np.corrcoef(pte, yte)[0, 1]) if len(te) > 2 else float("nan")
            print(f"{head}: test RMSE {rmse:.1f} vs label sd {sd:.1f} (corr {corr:.3f}), "
                  f"{booster.best_iteration} trees")
            lines += [f"## {head} head (regression on hp_delta_next3)", "",
                      f"- test RMSE **{rmse:.1f}** vs label sd {sd:.1f}; corr {corr:.3f}; "
                      f"{booster.best_iteration} trees; n {len(te)}", ""]
        heads[head] = booster.dump_model()
        boosters[head] = booster

    # ---- shadow-ranker stats on test drafts (boss head) ----
    if "boss" in boosters:
        by_draft: dict[tuple, list] = defaultdict(list)
        xs = _matrix([r["x"] for r in test], order)
        ps = boosters["boss"].predict(xs)
        for r, p in zip(test, ps, strict=True):
            by_draft[r["draft"]].append((float(p), r))
        agree = n_dr = 0
        spread = []
        for cands in by_draft.values():
            if len(cands) < 2:
                continue
            n_dr += 1
            top = max(cands, key=lambda t: t[0])
            agree += top[1]["picked"]
            spread.append(top[0] - min(c[0] for c in cands))
        lines += ["## shadow ranker (boss head, test drafts)", "",
                  f"- {n_dr} drafts with >=2 offers; model top-1 == bot pick on "
                  f"**{100 * agree / max(1, n_dr):.1f}%**; top-vs-bottom score spread "
                  f"median {statistics.median(spread):.3f}, p90 "
                  f"{sorted(spread)[int(0.9 * len(spread))]:.3f}", ""]
        print(f"shadow: agreement {100 * agree / max(1, n_dr):.1f}% over {n_dr} drafts")

        # ---- sanity: per-card model score vs model-free ITT (test rows) ----
        card_scores: dict[str, list[float]] = defaultdict(list)
        card_labels: dict[str, list[int]] = defaultdict(list)
        for r, p in zip(test, ps, strict=True):
            if r["y_boss"] is None:
                continue
            card_scores[r["card"]].append(float(p))
            card_labels[r["card"]].append(int(r["y_boss"]))
        cards = [c for c in card_scores if len(card_scores[c]) >= args.min_card_offers]
        if len(cards) >= 5:
            ms = [statistics.mean(card_scores[c]) for c in cards]
            itt = [statistics.mean(card_labels[c]) for c in cards]
            rc = _rank_corr(ms, itt)
            lines += ["## sanity: per-card mean model score vs per-card ITT (test rows)", "",
                      f"- {len(cards)} cards with >= {args.min_card_offers} test offers; "
                      f"rank correlation **{rc:.2f}** (the model should recover the "
                      "model-free offer ranking, then add deck context on top)", ""]
            ranked = sorted(zip(ms, itt, cards, strict=True), reverse=True)
            lines += ["| card | model mean P(beat boss) | ITT P(beat boss) | n |",
                      "|---|---|---|---|"]
            for m, it, c in [*ranked[:10], ("...", "...", "..."), *ranked[-10:]]:
                if c == "...":
                    lines.append("| ... | | | |")
                else:
                    lines.append(f"| {c} | {m:.3f} | {it:.3f} | {len(card_scores[c])} |")
            lines.append("")
            print(f"per-card rank corr vs ITT: {rc:.2f} over {len(cards)} cards")

    if heads:
        model = {"meta": {"name": "offer_model_v1", "since": args.since,
                          "code_heads": args.code_heads, "feature_order": order,
                          "n_runs": n_runs, "n_rows": len(rows), "params": PARAMS,
                          "n_trees": n_trees,
                          "labels": {"boss": "beat_act_boss", "hp3": "hp_delta_next3",
                                     "win": "victory"},
                          "deployment": "shadow re-ranker only (PLAN section 9)"},
                 "heads": heads}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(gzip.compress(
            json.dumps(model, separators=(",", ":")).encode("utf-8"), 9))
        loaded = gbt.load_model(args.out)
        sample = [r for r in test if r["y_boss"] is not None][:200]
        if "boss" in boosters and sample:
            ours = np.array([gbt.predict_proba(loaded, "boss", r["x"]) for r in sample])
            theirs = boosters["boss"].predict(_matrix([r["x"] for r in sample], order))
            diff = float(np.max(np.abs(ours - theirs)))
            assert diff < 1e-9, f"predictor mismatch {diff}"
            lines += [f"Pure-python predictor verified vs lightgbm on {len(sample)} rows "
                      f"(max |diff| {diff:.1e}). Artifact "
                      f"{args.out.stat().st_size / 1e6:.2f} MB.", ""]
        print(f"wrote {args.out}")
    rep = ROOT / "logs" / "reports" / args.report
    rep.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report -> {rep}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
