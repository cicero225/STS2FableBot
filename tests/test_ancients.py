"""Ancients pass (PLAN §8.5.5a): boon catalog scoring at is_ancient events, and
owned boons acting as tag providers / draft steering in card rewards.

Anchor scenario throughout: A/B #3 on MY60EQE85L — the shared f18 PAEL event
(Horn / Tooth / Legion). The generic event heuristic was BAITED by Tooth's
"Remove 5 cards..." (+5 for 'remove') while the run-winning Legion parsed to ~0;
the owner picked Legion and won the run the bot died on.
"""

from sts2bot.client.models import parse_state
from sts2bot.policy.base import Decision, LoopContext
from sts2bot.policy.drafttags import boon_relic_context, load_ancient_boons
from sts2bot.policy.standard import StandardRouter

BOONS = load_ancient_boons()


def router() -> StandardRouter:
    return StandardRouter()


class C:
    def __init__(self, cid, name=None, typ="Attack", cost="1", upgraded=False):
        self.id = cid
        self.name = name or cid.replace("_", " ").title()
        self.type = typ
        self.cost = cost
        self.is_upgraded = upgraded


class R:
    def __init__(self, name):
        self.name = name
        self.id = name.upper().replace(" ", "_").replace("'", "")


def _starter(strikes=5, defends=4):
    deck = [C("STRIKE_IRONCLAD", "Strike") for _ in range(strikes)]
    deck += [C("DEFEND_IRONCLAD", "Defend", typ="Skill") for _ in range(defends)]
    deck.append(C("BASH", "Bash", cost="2"))
    return deck


def ancient_event(options, is_ancient=True, hp=68, max_hp=80):
    return parse_state({
        "state_type": "event",
        "event": {
            "event_id": "PAEL",
            "event_name": "Pael",
            "is_ancient": is_ancient,
            "in_dialogue": False,
            "body": None,
            "options": [
                {"index": i, "title": t, "description": d, "is_locked": False,
                 "is_proceed": False, "was_chosen": False, "keywords": []}
                for i, (t, d) in enumerate(options)
            ],
        },
        "run": {"act": 2, "floor": 18, "ascension": 0},
        "player": {
            "character": "The Ironclad", "hp": hp, "max_hp": max_hp, "block": 0,
            "gold": 200, "status": [], "relics": [], "potions": [],
            "max_potion_slots": 3,
        },
    })


PAEL_HORN = ("Pael's Horn", "Add 2 Relax to your Deck.")
PAEL_TOOTH = ("Pael's Tooth",
              "Remove 5 cards from your Deck. After each combat, randomly add 1 back Upgraded.")
PAEL_LEGION = ("Pael's Legion",
               "Doubles Block gained from a card, then goes to sleep for 2 turns.")
PAEL_FLESH = ("Pael's Flesh",
              "Gain an additional Energy at the start of your 3rd turn, and every turn after.")


def test_catalog_loaded() -> None:
    assert len(BOONS) >= 80
    assert "Pael's Legion" in BOONS
    assert BOONS["Pael's Flesh"]["provides"].get("energy_source")


def test_legion_beats_the_remove_bait() -> None:
    """The A/B #3 offer: catalog must pick Legion over Tooth — the generic heuristic
    provably would not (Tooth's 'Remove 5' text out-scores Legion's unparsed text)."""
    r = router()
    st = ancient_event([PAEL_HORN, PAEL_TOOTH, PAEL_LEGION])
    heur_tooth = r._event_option_value(st.event.options[1], 68, 80)
    heur_legion = r._event_option_value(st.event.options[2], 68, 80)
    assert heur_tooth > heur_legion  # the bait, preserved as regression documentation

    d = r.decide(st, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.index == 2
    assert "ancient boon" in d.rationale
    assert "Pael's Legion" in d.rationale


def test_flesh_tops_the_pael_pool() -> None:
    r = router()
    d = r.decide(ancient_event([PAEL_FLESH, PAEL_TOOTH, PAEL_LEGION]), LoopContext())
    assert isinstance(d, Decision)
    assert d.action.index == 0  # energy is king


def test_unknown_boons_fall_back_to_generic() -> None:
    """A future epoch's uncatalogued boons must not wedge the event handler."""
    r = router()
    st = ancient_event([("Mystery Bauble", "Gain 20 Gold."),
                        ("Odd Trinket", "Upgrade a card.")])
    d = r.decide(st, LoopContext())
    assert isinstance(d, Decision)
    assert "ancient boon" not in d.rationale  # generic path handled it


def test_non_ancient_event_never_uses_catalog() -> None:
    r = router()
    st = ancient_event([PAEL_HORN, PAEL_TOOTH, PAEL_LEGION], is_ancient=False)
    d = r.decide(st, LoopContext())
    assert isinstance(d, Decision)
    assert "ancient boon" not in d.rationale


def test_boon_deck_fit_scales_legion() -> None:
    """Legion is worth more to a deck that already generates block (owner's actual
    reasoning at f18: block-light deck -> pick the doubler, then draft the engine)."""
    r = router()
    entry = BOONS["Pael's Legion"]
    blocky = [*_starter(), C("SHRUG_IT_OFF", "Shrug It Off", typ="Skill"),
              C("IRON_WAVE", "Iron Wave")]
    assert r._boon_deck_fit(entry, blocky) > r._boon_deck_fit(entry, _starter())
    cap = max(db["cap"] for db in entry["deck_bonus"])
    huge = [*_starter(),
            *(C("SHRUG_IT_OFF", "Shrug It Off", typ="Skill") for _ in range(20))]
    assert r._boon_deck_fit(entry, huge) <= cap + 1e-9


def test_boon_relic_context_merges_owned_boons() -> None:
    provides, bonus = boon_relic_context(
        [R("Pael's Flesh"), R("Very Hot Cocoa"), R("Burning Blood")], BOONS)
    assert provides["energy_source"] >= 3.0  # two energy boons stack
    provides, bonus = boon_relic_context([R("Pael's Legion")], BOONS)
    assert provides.get("block_payoff")
    assert bonus.get("block_engine")


def test_energy_boon_lifts_draw_penalty() -> None:
    """Owned Pael's Flesh counts as an energy source: drafted draw stops being
    penalized (the draw dock exists for decks with no energy to spend it with)."""
    r = router()
    w = r.config.card_rewards
    pommel = C("POMMEL_STRIKE", "Pommel Strike")
    pommel.description = "Deal 9 damage. Draw 1 card."
    pommel.rarity = "Common"
    deck = _starter()
    without = r._card_score(pommel, len(deck), "The Ironclad", act=1, deck=deck)
    with_boon = r._card_score(pommel, len(deck), "The Ironclad", act=1, deck=deck,
                              relics=[R("Pael's Flesh")])
    assert with_boon - without >= abs(w.penalty_draw_no_energy) - 1e-6


def test_legion_steers_drafting_toward_block() -> None:
    """Owned Legion adds a flat draft bonus to block_engine providers — the
    boon->Barricade drafting causality the A/B exposed."""
    r = router()
    shrug = C("SHRUG_IT_OFF", "Shrug It Off", typ="Skill")
    shrug.description = "Gain 8 Block. Draw 1 card."
    shrug.rarity = "Common"
    deck = _starter()
    without = r._card_score(shrug, len(deck), "The Ironclad", act=2, deck=deck)
    with_boon = r._card_score(shrug, len(deck), "The Ironclad", act=2, deck=deck,
                              relics=[R("Pael's Legion")])
    expected = BOONS["Pael's Legion"]["draft_bonus"]["block_engine"]
    assert with_boon - without >= expected - 1e-6
