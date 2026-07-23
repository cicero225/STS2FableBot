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


def test_all_unknown_boons_fall_back_to_generic() -> None:
    """A screen of exclusively uncatalogued boons must not wedge the handler."""
    r = router()
    st = ancient_event([("Mystery Bauble", "Gain 20 Gold."),
                        ("Odd Trinket", "Upgrade a card.")])
    d = r.decide(st, LoopContext())
    assert isinstance(d, Decision)
    assert "ancient boon" not in d.rationale  # generic path handled it


def test_unknown_boon_cannot_hijack_catalog_screen() -> None:
    """Live 2026-07-16 (Silken Tress): a mixed screen must stay on the catalog path,
    with the unknown option's hot raw heuristic clamped — a '+31 Max HP' parse (46.5)
    must not beat Pael's Flesh (8.5), and the screen must not fall back to generic."""
    r = router()
    st = ancient_event([PAEL_FLESH,
                        ("Weird Fruit", "Gain 31 Max HP.")])  # raw heuristic 46.5
    d = r.decide(st, LoopContext())
    assert isinstance(d, Decision)
    assert "ancient boon" in d.rationale
    assert d.action.index == 0  # Flesh (8.5) over the clamped unknown (5.0)

    # but a mediocre catalog option loses to a decent unknown (clamped, still ranked)
    st2 = ancient_event([PAEL_HORN,  # catalog 3.0
                         ("Weird Fruit", "Gain 31 Max HP.")])
    d2 = r.decide(st2, LoopContext())
    assert isinstance(d2, Decision)
    assert d2.action.index == 1
    assert "unknown, heur-capped" in d2.rationale


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


def bundle_state(bundles, preview_showing=False, can_cancel=True):
    return parse_state({
        "state_type": "bundle_select",
        "bundle_select": {
            "screen_type": "bundle", "prompt": "Choose a bundle.",
            "preview_showing": preview_showing, "can_confirm": preview_showing,
            "can_cancel": can_cancel,
            "bundles": [
                {"index": i, "card_count": len(cards), "cards": [
                    {"index": j, "id": cid, "name": name, "type": typ,
                     "cost": cost, "star_cost": None, "description": desc,
                     "rarity": "Common", "is_upgraded": False, "keywords": []}
                    for j, (cid, name, typ, cost, desc) in enumerate(cards)
                ]}
                for i, cards in enumerate(bundles)
            ],
        },
        "run": {"act": 1, "floor": 1, "ascension": 0},
        "player": {
            "character": "The Ironclad", "hp": 80, "max_hp": 80, "block": 0,
            "gold": 99, "status": [], "relics": [], "potions": [],
            "max_potion_slots": 3,
            "deck": [],
        },
    })


def test_bundle_select_scores_contents() -> None:
    """Regression (run 1, 2026-07-16): the Neow pack screen was taken blind ('preview
    first bundle') and delivered Havoc, a planner-dead card the reward scorer docks to
    -9.8. Bundles are now scored by summed card value — the Havoc bundle must lose."""
    r = router()
    havoc_bundle = [
        ("BLOOD_WALL", "Blood Wall", "Skill", "2", "Lose 2 HP. Gain 16 Block."),
        ("HAVOC", "Havoc", "Skill", "1",
         "Play the top card of your Draw Pile and Exhaust it."),
    ]
    good_bundle = [
        ("POMMEL_STRIKE", "Pommel Strike", "Attack", "1", "Deal 9 damage. Draw 1 card."),
        ("IRON_WAVE", "Iron Wave", "Attack", "1", "Gain 5 Block. Deal 5 damage."),
    ]
    d = r.decide(bundle_state([havoc_bundle, good_bundle]), LoopContext())
    assert isinstance(d, Decision)
    assert d.action.index == 1
    assert "select bundle 1" in d.rationale

    # confirm follows once the preview we opened is showing
    ctx = LoopContext()
    ctx.screen_mem["bundle_picked"] = 1
    d2 = r.decide(bundle_state([havoc_bundle, good_bundle], preview_showing=True), ctx)
    assert isinstance(d2, Decision)
    assert "confirm" in d2.rationale


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


def test_event_catalog_beats_decline_by_default() -> None:
    """Events pass (EVENTS_PASS.md): 50%+ of events were declined because the generic
    heuristic couldn't price their text. The title-keyed catalog engages instead —
    and the Slither trap ('Snake') stays negative, never taken over Proceed."""
    from sts2bot.policy.standard import StandardRouter

    r = StandardRouter(combat_stats=None, bestiary={})
    assert r.event_choices  # catalog loaded

    def event_state(options):
        return parse_state({
            "state_type": "event",
            "event": {"event_id": "SUNKEN_STATUE", "event_name": "Sunken Statue",
                      "is_ancient": False, "in_dialogue": False, "body": None,
                      "options": [
                          {"index": i, "title": t, "description": d,
                           "is_locked": False, "is_proceed": t == "Proceed",
                           "was_chosen": False, "keywords": []}
                          for i, (t, d) in enumerate(options)
                      ]},
            "run": {"act": 1, "floor": 8, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80,
                       "block": 0, "gold": 120, "status": [], "relics": [],
                       "potions": [], "max_potion_slots": 3},
        })

    # 'Grab the Sword' (free relic, catalog 5.5) must beat Proceed
    st = event_state([("Grab the Sword", "Obtain the Sword of Stone."),
                      ("Proceed", "Leave.")])
    d = r.decide(st, LoopContext())
    assert isinstance(d, Decision)
    assert "event catalog" in d.rationale and d.action.index == 0

    # Slither REVERSED (owner 2026-07-20): the option is good — the old trap was
    # a targeting mistake, and the enchant picker now takes the highest-cost card
    st2 = event_state([("Snake", "Enchant 1 card with Slither."),
                       ("Proceed", "Leave.")])
    d2 = r.decide(st2, LoopContext())
    assert isinstance(d2, Decision)
    assert d2.action.index == 0  # engage: Slither-on-Bash is +EV


def test_costless_unknown_event_option_engages() -> None:
    """Catalog v2 (2026-07-21): unparseable-but-COSTLESS options engage at the floor
    instead of declining (the event pool is EV-positive per Spirebird's own data);
    unknowns with a parsed cost keep the clamped heuristic and can still decline."""
    from sts2bot.policy.standard import StandardRouter

    r = StandardRouter(combat_stats=None, bestiary={})

    def ev(options):
        return parse_state({
            "state_type": "event",
            "event": {"event_id": "MYSTERY", "event_name": "Mystery",
                      "is_ancient": False, "in_dialogue": False, "body": None,
                      "options": [
                          {"index": i, "title": t, "description": d,
                           "is_locked": False, "is_proceed": t == "Proceed",
                           "was_chosen": False, "keywords": []}
                          for i, (t, d) in enumerate(options)
                      ]},
            "run": {"act": 1, "floor": 6, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80,
                       "block": 0, "gold": 100, "status": [], "relics": [],
                       "potions": [], "max_potion_slots": 3},
        })

    # costless mystery option: engage
    d = r.decide(ev([("Pull the Lever", "Something mysterious happens."),
                     ("Proceed", "Leave.")]), LoopContext())
    assert isinstance(d, Decision)
    assert d.action.index == 0

    # unknown WITH a parsed cost and no gain: still declined
    d2 = r.decide(ev([("Sacrifice", "Lose 20 HP. Something mysterious happens."),
                      ("Proceed", "Leave.")]), LoopContext())
    assert isinstance(d2, Decision)
    assert d2.action.index == 1


def test_slippery_bridge_gamble_rule() -> None:
    """Owner mechanics + screenshot (2026-07-22): the sub-screen's 'Overcome' title
    collides with the stage-1 catalog entry — description-matched now. Junk shown ->
    accept (free thinning); keeper shown -> pay X and reroll while cheap; too-steep X
    -> accept even a keeper; Quest cards always rerolled."""
    from sts2bot.policy.standard import StandardRouter

    r = StandardRouter(combat_stats=None, bestiary={})

    def bridge(card_name, x, deck_cards, hp=60):
        return parse_state({
            "state_type": "event",
            "event": {"event_id": "SLIPPERY_BRIDGE", "event_name": "Slippery Bridge",
                      "is_ancient": False, "in_dialogue": False, "body": None,
                      "options": [
                          {"index": 0, "title": "Overcome",
                           "description": f"{card_name} is removed from your Deck.",
                           "is_locked": False, "is_proceed": False,
                           "was_chosen": False, "keywords": []},
                          {"index": 1, "title": "Hold On",
                           "description": f"Lose {x} HP. The card in the above "
                                          "option is randomized.",
                           "is_locked": False, "is_proceed": False,
                           "was_chosen": False, "keywords": []},
                      ]},
            "run": {"act": 1, "floor": 10, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": hp, "max_hp": 80,
                       "block": 0, "gold": 100, "status": [], "relics": [],
                       "potions": [], "max_potion_slots": 3,
                       "deck": deck_cards},
        })

    def card(name, typ="Attack", cid=None):
        return {"index": 0, "id": cid or name.upper().replace(" ", "_"),
                "name": name, "type": typ, "cost": "1", "is_upgraded": False}

    # curse shown: remove it (free thinning)
    d = r.decide(bridge("Debt", 3, [card("Debt", "Curse")]), LoopContext())
    assert d.action.index == 0 and "free thinning" in d.rationale

    # keeper shown, cheap X: reroll
    d2 = r.decide(bridge("Uppercut", 3, [card("Uppercut")]), LoopContext())
    assert d2.action.index == 1

    # keeper shown, X too steep: accept the loss
    d3 = r.decide(bridge("Uppercut", 12, [card("Uppercut")]), LoopContext())
    assert d3.action.index == 0

    # Quest card shown: always reroll (never surrender the coupon cheaply)
    d4 = r.decide(bridge("Spoils Map", 3, [card("Spoils Map", "Quest")]),
                  LoopContext())
    assert d4.action.index == 1


def test_event_fight_options_carry_implicit_hp_cost() -> None:
    """Lantern Key death (2026-07-22): 'Fight to obtain the Key' read as a free
    relic at 25/85 HP. Fight options now price an expected monster loss through
    the hp-cost gates: refused when hurt, allowed when healthy."""
    from sts2bot.policy.standard import StandardRouter

    r = StandardRouter(combat_stats=None, bestiary={})

    def lantern(hp):
        return parse_state({
            "state_type": "event",
            "event": {"event_id": "THE_LANTERN_KEY", "event_name": "Lantern Key",
                      "is_ancient": False, "in_dialogue": False, "body": None,
                      "options": [
                          {"index": 0, "title": "Return the Key",
                           "description": "Gain 100 Gold.", "is_locked": False,
                           "is_proceed": False, "was_chosen": False, "keywords": []},
                          {"index": 1, "title": "Keep the Key",
                           "description": "Fight to obtain the Key.",
                           "is_locked": False, "is_proceed": False,
                           "was_chosen": False, "keywords": []},
                      ]},
            "run": {"act": 2, "floor": 22, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": hp, "max_hp": 85,
                       "block": 0, "gold": 120, "status": [], "relics": [],
                       "potions": [], "max_potion_slots": 3},
        })

    # 25/85 (29%): the fight option must be refused -> take the gold
    d = r.decide(lantern(25), LoopContext())
    assert d.action.index == 0

    # 80/85: fighting for a key relic is a legitimate choice again
    d2 = r.decide(lantern(80), LoopContext())
    assert d2.action.index == 1
