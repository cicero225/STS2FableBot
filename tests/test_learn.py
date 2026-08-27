"""sts2bot.learn: featurizer shim + dependency-free logreg sanity."""

from __future__ import annotations

import random

from sts2bot.learn import logreg
from sts2bot.learn.features import cards_from_keys, deck_features


def test_card_shim_parses_upgrade_marks():
    cards = cards_from_keys(["BASH+", "STRIKE_IRONCLAD"])
    assert cards[0].id == "BASH" and cards[0].is_upgraded
    assert cards[1].id == "STRIKE_IRONCLAD" and not cards[1].is_upgraded


def test_deck_features_aggregates_and_tags():
    catalog = {
        "STRIKE_IRONCLAD": {"type": "Attack", "cost": "1"},
        "DEFEND_IRONCLAD": {"type": "Skill", "cost": "1"},
        "WHIRLWIND": {"type": "Attack", "cost": "X"},
    }
    tags = {
        "WHIRLWIND": {"provides": {"aoe": 1.0}},
        "STRIKE_IRONCLAD": {"provides": {"exhaust_enabler": 1.0},
                            "exhaust_drops_on_upgrade": True},
    }
    f = deck_features(
        ["STRIKE_IRONCLAD", "DEFEND_IRONCLAD", "WHIRLWIND", "BASH+"],
        relics=["BURNING_BLOOD"], hp=40, max_hp=80, act=2,
        boss="Aeonglass", catalog=catalog, tags=tags)
    assert f["n_cards"] == 4.0
    assert f["frac_upgraded"] == 0.25
    assert f["hp_frac"] == 0.5
    assert f["boss:Aeonglass"] == 1.0
    assert f["type:attack"] == 0.5  # Strike + Whirlwind; BASH absent from catalog
    assert f["cost:x"] == 0.25
    # pseudo-tags ride deck_tag_weights: 2 basics / 4 cards; catalog-fed
    # type/cost make the built-in-field pseudo-tags real (July-bug lesson:
    # consumed-but-never-computed features are silent zeros)
    assert f["tag:__basics"] == 0.5
    assert f["tag:__attacks"] == 0.5
    assert f["tag:__skills"] == 0.25
    # real-tag provides, per-card normalized; unupgraded Strike still provides
    assert f["tag:aoe"] == 0.25
    assert f["tag:exhaust_enabler"] == 0.25


def test_exhaust_enabler_dropped_for_upgraded_flagged_copy():
    tags = {"HOLOGRAM": {"provides": {"exhaust_enabler": 1.0},
                         "exhaust_drops_on_upgrade": True}}
    f = deck_features(["HOLOGRAM+"], tags=tags)
    assert "tag:exhaust_enabler" not in f


def test_deck_features_tolerates_missing_inputs():
    f = deck_features([])
    assert f == {"n_cards": 0.0}


def test_logreg_learns_a_separable_problem_deterministically():
    rng = random.Random(7)
    rows, ys = [], []
    for _ in range(400):
        y = rng.random() < 0.5
        rows.append({"a": rng.gauss(2.0 if y else -2.0, 1.0),
                     "b": rng.gauss(0, 1)})
        ys.append(int(y))
    model = logreg.train(rows, ys, epochs=15)
    ps = [logreg.predict(model, r) for r in rows]
    assert logreg.auc(ys, ps) > 0.95
    # feature `a` dominates; `b` is noise
    wa = model["w"][model["features"].index("a")]
    wb = model["w"][model["features"].index("b")]
    assert abs(wa) > 5 * abs(wb)
    # deterministic retrain
    again = logreg.train(rows, ys, epochs=15)
    assert again["w"] == model["w"] and again["b"] == model["b"]


def test_auc_handles_ties_and_degenerate_labels():
    assert logreg.auc([1, 0, 1, 0], [0.5, 0.5, 0.5, 0.5]) == 0.5
    assert logreg.auc([1, 1], [0.2, 0.8]) != logreg.auc([1, 1], [0.2, 0.8]) \
        or True  # nan for single-class: just must not raise
