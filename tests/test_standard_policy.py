"""Behavioral tests for the StandardRouter (P1 policies)."""

import json
from pathlib import Path

from sts2bot.client.actions import PlayCard
from sts2bot.client.models import parse_state
from sts2bot.policy.base import Decision, LoopContext, Wait
from sts2bot.policy.standard import StandardRouter

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "doc_states.json").read_text(encoding="utf-8")
)


def router() -> StandardRouter:
    return StandardRouter()


def make_combat(hand, enemies, energy=3, hp=70, max_hp=80, state_type="monster", potions=None):
    return parse_state(
        {
            "state_type": state_type,
            "battle": {"round": 1, "turn": "player", "is_play_phase": True, "enemies": enemies},
            "run": {"act": 1, "floor": 3, "ascension": 0},
            "player": {
                "character": "The Ironclad",
                "hp": hp,
                "max_hp": max_hp,
                "block": 0,
                "gold": 99,
                "energy": energy,
                "max_energy": 3,
                "hand": hand,
                "draw_pile_count": 5,
                "discard_pile_count": 0,
                "exhaust_pile_count": 0,
                "status": [],
                "relics": [],
                "potions": potions or [],
                "max_potion_slots": 3,
            },
        }
    )


def card(index, name, cost, desc, target="AnyEnemy", can_play=True, ctype="Attack"):
    return {
        "index": index,
        "id": name.upper().replace(" ", "_"),
        "name": name,
        "type": ctype,
        "cost": str(cost),
        "star_cost": None,
        "description": desc,
        "target_type": target,
        "can_play": can_play,
        "unplayable_reason": None,
        "is_upgraded": False,
        "keywords": [],
    }


def enemy(eid, hp, intent_label="6", block=0):
    return {
        "entity_id": eid,
        "combat_id": 1,
        "name": eid.title(),
        "hp": hp,
        "max_hp": hp,
        "block": block,
        "status": [],
        "intents": [
            {"type": "Attack", "label": intent_label, "title": "Attack", "description": ""}
        ],
    }


def test_combat_goes_for_lethal() -> None:
    state = make_combat(
        hand=[
            card(0, "Strike", 1, "Deal 6 damage."),
            card(1, "Strike", 1, "Deal 6 damage."),
            card(2, "Defend", 1, "Gain 5 Block.", target="Self", ctype="Skill"),
        ],
        enemies=[enemy("NIBBIT_0", 10, intent_label="12")],
    )
    decision = router().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    assert isinstance(decision.action, PlayCard)
    # killing the enemy beats blocking its 12 damage
    assert decision.action.payload()["card_index"] in (0, 1)


def test_combat_applies_vulnerable_before_damage() -> None:
    state = make_combat(
        hand=[
            card(0, "Strike", 1, "Deal 6 damage."),
            card(1, "Bash", 2, "Deal 8 damage. Apply 2 Vulnerable."),
        ],
        enemies=[enemy("GUARD_0", 60)],
        energy=3,
    )
    decision = router().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    # Bash first so the follow-up Strike benefits from Vulnerable
    assert decision.action.payload()["card_index"] == 1
    assert "Bash" in decision.rationale.split(">")[0]


def test_combat_blocks_when_kill_impossible() -> None:
    state = make_combat(
        hand=[
            card(0, "Strike", 1, "Deal 6 damage."),
            card(1, "Defend", 1, "Gain 5 Block.", target="Self", ctype="Skill"),
            card(2, "Defend", 1, "Gain 5 Block.", target="Self", ctype="Skill"),
        ],
        enemies=[enemy("BRUTE_0", 80, intent_label="3x4")],
        energy=2,
    )
    decision = router().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    # 12 incoming, can't remotely kill 80hp: plan must include both Defends
    assert "Defend" in decision.rationale


def test_combat_potion_when_dire() -> None:
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("BOSS_0", 100, intent_label="20")],
        hp=15,
        max_hp=80,
        state_type="boss",
        potions=[
            {
                "id": "FIRE_POTION",
                "name": "Fire Potion",
                "description": "Deal 20 damage to target enemy.",
                "slot": 0,
                "can_use_in_combat": True,
                "target_type": "AnyEnemy",
                "keywords": [],
            }
        ],
    )
    decision = router().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    assert decision.action.payload()["action"] == "use_potion"


def test_actions_disabled_waits() -> None:
    """Run 16 (Act 2!) died to hammering plays into a scripted lockout; the fork
    exposes battle.actions_disabled and combat must wait on it."""
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("SCRIPTED_0", 50)],
    )
    raw = state.model_dump(by_alias=True)
    raw["battle"]["actions_disabled"] = True
    from sts2bot.client.models import parse_state as ps

    decision = router().decide(ps(raw), LoopContext())
    assert isinstance(decision, Wait)
    assert "disabled" in decision.reason


def test_pack_fight_focuses_fire() -> None:
    """Run 13 spread damage across a 4-Nibbit pack and died from full HP. With the
    focus term, follow-up hits go to the already-wounded enemy."""

    def pack(first_hp: int):
        enemies = [enemy(f"NIBBIT_{i}", 20, intent_label="10") for i in range(4)]
        enemies[2]["hp"] = first_hp  # NIBBIT_2 took the first hit
        return make_combat(
            hand=[card(0, "Strike", 1, "Deal 6 damage.")],
            enemies=enemies,
            energy=1,
        )

    decision = router().decide(pack(first_hp=14), LoopContext())
    assert isinstance(decision, Decision)
    payload = decision.action.payload()
    assert payload["action"] == "play_card"
    assert payload["target"] == "NIBBIT_2"  # finish what you started


OFFERING_DESC = "Lose 6 HP. Gain 2 Energy. Draw 3 cards."


def test_offering_played_when_healthy_shelved_when_hurt() -> None:
    """Owner: Offering went almost unplayed — HP cost visible, draw value not.
    With draw revalued and HP scarcity-scaled it plays at high HP, not at low."""

    def offering_state(hp):
        return make_combat(
            hand=[
                card(0, "Offering", 0, OFFERING_DESC, target="Self", ctype="Skill"),
                card(1, "Strike", 1, "Deal 6 damage."),
            ],
            enemies=[enemy("GUARD_0", 60, intent_label="10")],
            hp=hp,
            max_hp=80,
            energy=3,
        )

    healthy = router().decide(offering_state(hp=78), LoopContext())
    assert isinstance(healthy, Decision)
    assert "Offering" in healthy.rationale

    hurt = router().decide(offering_state(hp=20), LoopContext())
    assert isinstance(hurt, Decision)
    assert "Offering" not in hurt.rationale


def test_desperation_draw_before_lethal_hit() -> None:
    """Owner bonus case: lethal hit the face while Offering sat in hand."""
    state = make_combat(
        hand=[card(0, "Offering", 0, OFFERING_DESC, target="Self", ctype="Skill")],
        enemies=[enemy("BRUTE_0", 90, intent_label="25")],
        hp=12,
        max_hp=80,
        energy=0,  # nothing else affordable; normally Offering would be shelved at 15% HP
    )
    decision = router().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    assert "desperation draw" in decision.rationale
    assert decision.action.payload()["card_index"] == 0


def test_desperation_draw_targets_attack_cards() -> None:
    """Run 29: desperation fired on Pommel Strike (attack that draws) with no
    target — 8 errors at The Kin. Targeted draw cards must get a target."""
    state = make_combat(
        hand=[
            card(0, "Pommel Strike", 1, "Deal 9 damage. Draw 1 card.")  # AnyEnemy
        ],
        enemies=[enemy("THE_KIN_0", 90, intent_label="30")],
        hp=10,
        max_hp=80,
        energy=1,
    )
    decision = router().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    payload = decision.action.payload()
    assert payload["action"] == "play_card"
    assert payload.get("target") == "THE_KIN_0"


def _defend(index, can_play, reason):
    return {
        "index": index,
        "id": "DEFEND_R",
        "name": "Defend",
        "type": "Skill",
        "cost": "1",
        "star_cost": None,
        "description": "Gain 5 Block.",
        "target_type": "Self",
        "can_play": can_play,
        "unplayable_reason": reason,
        "is_upgraded": False,
        "keywords": [],
    }


def test_hook_blocked_hand_waits_then_plays() -> None:
    """Run 33: a transient 'BlockedByHook' hand reported every card unplayable; the
    planner ended the turn early and dropped 14 HP -> 3. Re-poll instead."""
    enemies = [enemy("BEAST_0", 200, intent_label="16")]
    blocked = make_combat(
        hand=[_defend(0, False, "BlockedByHook"), _defend(1, False, "BlockedByHook")],
        enemies=enemies,
        energy=2,
        hp=14,
        max_hp=101,
        state_type="boss",
    )
    ctx = LoopContext()
    waited = router().decide(blocked, ctx)
    assert isinstance(waited, Wait) and "hook" in waited.reason

    ready = make_combat(
        hand=[_defend(0, True, None), _defend(1, True, None)],
        enemies=enemies,
        energy=2,
        hp=14,
        max_hp=101,
        state_type="boss",
    )
    played = router().decide(ready, ctx)
    assert isinstance(played, Decision)
    assert played.action.payload()["action"] == "play_card"


def test_hook_retry_cap_eventually_ends_turn() -> None:
    r = router()
    cap = r.config.combat.hook_retry_limit
    blocked = make_combat(
        hand=[_defend(0, False, "BlockedByHook")],
        enemies=[enemy("BEAST_0", 200, intent_label="16")],
        energy=2,
        hp=14,
        max_hp=101,
        state_type="boss",
    )
    ctx = LoopContext()
    decisions = [r.decide(blocked, ctx) for _ in range(cap + 1)]
    assert all(isinstance(d, Wait) for d in decisions[:cap])
    assert isinstance(decisions[cap], Decision)
    assert decisions[cap].action.payload()["action"] == "end_turn"


def test_genuine_unplayable_hand_ends_turn() -> None:
    """NotEnoughEnergy is a real reason, not a transient hook — end the turn."""
    state = make_combat(
        hand=[card(0, "Bash", 2, "Deal 8 damage.", can_play=False)],
        enemies=[enemy("X_0", 40, intent_label="6")],
        energy=1,
    )
    # card() leaves unplayable_reason None; set the real reason
    raw = state.model_dump(by_alias=True)
    raw["player"]["hand"][0]["unplayable_reason"] = "NotEnoughEnergy"
    from sts2bot.client.models import parse_state as ps

    decision = router().decide(ps(raw), LoopContext())
    assert isinstance(decision, Decision)
    assert decision.action.payload()["action"] == "end_turn"


def test_hail_mary_throws_multiple_potions() -> None:
    """Owner: hail-mary on a boss used only one of two potions (the one-per-round
    cap). With per-slot tracking it drinks both (different slots) across polls."""

    def state():
        return make_combat(
            hand=[card(0, "Strike", 1, "Deal 6 damage.")],
            enemies=[enemy("BOSS_0", 200, intent_label="30")],
            hp=10,
            max_hp=80,
            state_type="boss",
            potions=[
                {
                    "id": "FYSH",
                    "name": "Fysh Oil",
                    "description": "Gain 1 Strength and 1 Dexterity.",
                    "slot": 0,
                    "can_use_in_combat": True,
                    "target_type": "None",
                    "keywords": [],
                },
                {
                    "id": "SPEED",
                    "name": "Speed Potion",
                    "description": "Gain 1 Dexterity.",
                    "slot": 2,
                    "can_use_in_combat": True,
                    "target_type": "None",
                    "keywords": [],
                },
            ],
        )

    r = router()
    ctx = LoopContext()
    d1 = r.decide(state(), ctx)
    d2 = r.decide(state(), ctx)
    assert isinstance(d1, Decision) and d1.action.payload()["action"] == "use_potion"
    assert isinstance(d2, Decision) and d2.action.payload()["action"] == "use_potion"
    assert {d1.action.payload()["slot"], d2.action.payload()["slot"]} == {0, 2}


def test_no_pointless_plays_against_non_attacker() -> None:
    """Owner observation: Production into Defends vs a non-attacking enemy is pure
    waste. Play friction should leave only the useful play (Strike)."""
    enemies = [
        {
            "entity_id": "IDLER_0",
            "combat_id": 1,
            "name": "Idler",
            "hp": 40,
            "max_hp": 40,
            "block": 0,
            "status": [],
            "intents": [{"type": "Buff", "label": "Buff", "title": "Buff", "description": ""}],
        }
    ]
    state = make_combat(
        hand=[
            card(0, "Production", 0, "Gain 2 Energy.", target="Self", ctype="Skill"),
            card(1, "Defend", 1, "Gain 5 Block.", target="Self", ctype="Skill"),
            card(2, "Strike", 1, "Deal 6 damage."),
        ],
        enemies=enemies,
        energy=3,
    )
    decision = router().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    assert "Defend" not in decision.rationale  # no block vs zero incoming
    assert decision.action.payload()["card_index"] == 2  # just hit it


def test_barricade_makes_block_stacking_worthwhile() -> None:
    """The nuance the owner flagged: with Barricade, block persists — stack away."""
    enemies = [
        {
            "entity_id": "IDLER_0",
            "combat_id": 1,
            "name": "Idler",
            "hp": 40,
            "max_hp": 40,
            "block": 0,
            "status": [],
            "intents": [{"type": "Buff", "label": "Buff", "title": "Buff", "description": ""}],
        }
    ]
    raw = make_combat(
        hand=[
            card(0, "Defend", 1, "Gain 5 Block.", target="Self", ctype="Skill"),
            card(1, "Strike", 1, "Deal 6 damage."),
        ],
        enemies=enemies,
        energy=3,
    ).model_dump(by_alias=True)
    raw["player"]["status"] = [
        {
            "id": "BARRICADE",
            "name": "Barricade",
            "amount": None,
            "type": "Buff",
            "description": "Block is not removed at the start of your turn.",
            "keywords": [],
        }
    ]
    from sts2bot.client.models import parse_state as ps

    decision = router().decide(ps(raw), LoopContext())
    assert isinstance(decision, Decision)
    assert "Defend" in decision.rationale  # block has future value now


def test_heal_potion_when_dire() -> None:
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("WURM_0", 40, intent_label="10")],
        hp=15,
        max_hp=80,
        potions=[
            {
                "id": "RADIANT",
                "name": "Healing Salve",
                "description": "Heal 20 HP.",
                "slot": 0,
                "can_use_in_combat": True,
                "target_type": "None",
                "keywords": [],
            }
        ],
    )
    decision = router().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    assert decision.action.payload()["action"] == "use_potion"
    assert "heal" in decision.rationale


def _insatiable_state(sandpit: int, escape_playable: bool = True):
    """Mirrors the logged Insatiable fight (run 2026-06-11-235641)."""
    enemies = [
        {
            "entity_id": "THE_INSATIABLE_0",
            "combat_id": 9,
            "name": "The Insatiable",
            "hp": 180,
            "max_hp": 300,
            "block": 0,
            "status": [
                {
                    "id": "SANDPIT",
                    "name": "Sandpit",
                    "amount": sandpit,
                    "type": "Buff",
                    "description": "When The Insatiable takes its turn, you will be "
                    "eaten and die.",
                    "keywords": [],
                }
            ],
            "intents": [{"type": "Attack", "label": "14", "title": "Attack", "description": ""}],
        }
    ]
    hand = [
        card(0, "Strike", 1, "Deal 6 damage."),
        {
            "index": 1,
            "id": "FRANTIC_ESCAPE",
            "name": "Frantic Escape",
            "type": "Status",
            "cost": "1",
            "star_cost": None,
            "description": "Get farther away. Increase Sandpit by 1. Increase the "
            "cost of this card by 1.",
            "target_type": "Self",
            "can_play": escape_playable,
            "unplayable_reason": None,
            "is_upgraded": False,
            "keywords": [],
        },
    ]
    return make_combat(hand=hand, enemies=enemies, energy=3, hp=50, state_type="boss")


def test_survival_card_played_when_countdown_low() -> None:
    """The Insatiable ate the bot at Sandpit 1 while Frantic Escape sat in hand."""
    decision = router().decide(_insatiable_state(sandpit=1), LoopContext())
    assert isinstance(decision, Decision)
    assert decision.action.payload()["card_index"] == 1
    assert "survival" in decision.rationale


def test_survival_card_ignored_when_countdown_safe() -> None:
    decision = router().decide(_insatiable_state(sandpit=5), LoopContext())
    assert isinstance(decision, Decision)
    payload = decision.action.payload()
    # normal planning: hit the boss instead of wasting energy on escape
    assert payload["action"] == "play_card" and payload["card_index"] == 0


def test_lethal_in_hand_skips_hail_mary() -> None:
    """Owner observation: hail-mary fired alongside lethal vs the Act 1 boss.
    If the planned line clears the board, don't waste potions surviving a turn
    that will never come."""
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage."), card(1, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("BOSS_0", 10, intent_label="20")],  # 12 damage available, 10 hp
        hp=3,
        max_hp=80,
        energy=2,
        state_type="boss",
        potions=[
            {
                "id": "FYSH_OIL",
                "name": "Fysh Oil",
                "description": "Gain 1 Strength and 1 Dexterity.",
                "slot": 0,
                "can_use_in_combat": True,
                "target_type": "None",
                "keywords": [],
            }
        ],
    )
    decision = router().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    assert decision.action.payload()["action"] == "play_card"
    assert "LETHAL" in decision.rationale


def test_hail_mary_drinks_unparseable_potion() -> None:
    """Run 10 died at 3 HP holding Fysh Oil + Radiant Tincture (buff/icon-markup
    descriptions the parser can't read). Lethal incoming -> drink anything."""
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("BYGONE_EFFIGY_0", 60, intent_label="13")],
        hp=3,
        max_hp=80,
        potions=[
            {
                "id": "FYSH_OIL",
                "name": "Fysh Oil",
                "description": "Gain 1 Strength and 1 Dexterity.",
                "slot": 0,
                "can_use_in_combat": True,
                "target_type": "None",
                "keywords": [],
            }
        ],
    )
    decision = router().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    assert decision.action.payload()["action"] == "use_potion"
    assert "hail mary" in decision.rationale


def test_event_refuses_hp_cost_when_low() -> None:
    state = parse_state(
        {
            "state_type": "event",
            "event": {
                "event_id": "DENSE_VEGETATION",
                "event_name": "Dense Vegetation",
                "is_ancient": False,
                "in_dialogue": False,
                "body": "Thick vines block the path.",
                "options": [
                    {
                        "index": 0,
                        "title": "Trudge On",
                        "description": "Take 8 damage.",
                        "is_locked": False,
                        "is_proceed": False,
                        "was_chosen": False,
                        "keywords": [],
                    },
                    {
                        "index": 1,
                        "title": "Go Around",
                        "description": "Lose all your gold... just kidding. Leave.",
                        "is_locked": False,
                        "is_proceed": True,
                        "was_chosen": False,
                        "keywords": [],
                    },
                ],
            },
            "run": {"act": 1, "floor": 6, "ascension": 0},
            "player": {
                "character": "The Necrobinder",
                "hp": 12,
                "max_hp": 66,
                "status": [],
                "relics": [],
                "potions": [],
                "max_potion_slots": 3,
            },
        }
    )
    decision = router().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    assert decision.action.payload() == {"action": "choose_event_option", "index": 1}


def test_map_avoids_elites_and_rests_when_hurt() -> None:
    payload = json.loads(json.dumps(FIXTURES["map"]))  # deep copy
    payload["map"]["next_options"] = [
        {"index": 0, "col": 1, "row": 3, "type": "Elite", "leads_to": []},
        {"index": 1, "col": 2, "row": 3, "type": "Monster", "leads_to": []},
        {"index": 2, "col": 3, "row": 3, "type": "RestSite", "leads_to": []},
    ]
    payload["player"]["hp"] = 20
    payload["player"]["max_hp"] = 80
    state = parse_state(payload)
    decision = router().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    # 75% missing HP makes the rest site dominate; elite must never win
    assert decision.action.payload() == {"action": "choose_map_node", "index": 2}

    payload["player"]["hp"] = 80
    state = parse_state(payload)
    decision = router().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    assert decision.action.payload()["index"] == 1  # healthy: fight the monster


def test_map_path_planning_avoids_forced_elite_lane() -> None:
    """Runs 10/15 died in lanes whose elite was committed floors earlier. Two lanes
    with identical immediate nodes: the one whose future forces an elite must lose."""
    payload = {
        "state_type": "map",
        "map": {
            "current_position": {"col": 2, "row": 0, "type": "Start"},
            "visited": [],
            "next_options": [
                {
                    "index": 0,
                    "col": 1,
                    "row": 1,
                    "type": "Monster",
                    "leads_to": [{"col": 1, "row": 2, "type": "Elite"}],
                },
                {
                    "index": 1,
                    "col": 3,
                    "row": 1,
                    "type": "Monster",
                    "leads_to": [{"col": 3, "row": 2, "type": "Event"}],
                },
            ],
            "nodes": [
                {"col": 2, "row": 0, "type": "Start", "children": [[1, 1], [3, 1]]},
                {"col": 1, "row": 1, "type": "Monster", "children": [[1, 2]]},
                {"col": 3, "row": 1, "type": "Monster", "children": [[3, 2]]},
                {"col": 1, "row": 2, "type": "Elite", "children": [[2, 3]]},
                {"col": 3, "row": 2, "type": "Event", "children": [[2, 3]]},
                {"col": 2, "row": 3, "type": "Monster", "children": []},
            ],
            "boss": {"col": 2, "row": 4, "id": "B", "name": "Boss"},
            "bosses": [],
        },
        "run": {"act": 1, "floor": 1, "ascension": 0},
        "player": {
            "character": "The Ironclad",
            "hp": 70,
            "max_hp": 80,
            "gold": 50,
            "status": [],
            "relics": [],
            "potions": [],
            "max_potion_slots": 3,
        },
    }
    decision = router().decide(parse_state(payload), LoopContext())
    assert isinstance(decision, Decision)
    assert decision.action.payload()["index"] == 1  # the lane without the forced elite
    assert decision.scores["1:Monster"] > decision.scores["0:Monster"]


def test_card_reward_takes_good_skips_bad() -> None:
    payload = json.loads(json.dumps(FIXTURES["card_reward"]))
    state = parse_state(payload)
    decision = router().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    # Uppercut (uncommon, vuln+weak) and Shrug It Off (block+draw) both clear threshold
    assert decision.action.payload()["action"] == "select_card_reward"

    payload["card_reward"]["cards"] = [
        {
            "index": 0,
            "id": "CLASH",
            "name": "Clunker",
            "type": "Attack",
            "cost": "3",
            "star_cost": None,
            "description": "A conditional nothing.",
            "rarity": "Common",
            "is_upgraded": False,
            "keywords": [],
        }
    ]
    state = parse_state(payload)
    decision = router().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    assert decision.action.payload() == {"action": "skip_card_reward"}


def test_priors_loaded_and_shaped() -> None:
    from sts2bot.kb.priors import CardPriors

    priors = CardPriors.load()
    assert priors is not None, "data/priors_cards.json should be committed"
    # accepts both display names and ids; ADRENALINE is the community's top pick
    adrenaline = priors.score("ADRENALINE", "The Ironclad")
    assert adrenaline is not None and adrenaline > 4.0
    assert priors.score("ADRENALINE", "IRONCLAD") == adrenaline
    assert priors.score("NO_SUCH_CARD", "IRONCLAD") is None


def test_priors_act_tilt_loads_and_directional() -> None:
    from sts2bot.kb.priors import CardPriors

    p = CardPriors.load()
    assert p is not None
    # Offering is act-1-favored (early tempo): act-1 tilt above act-3 tilt
    assert p.act_tilt("OFFERING", "The Ironclad", 1) > p.act_tilt("OFFERING", "The Ironclad", 3)
    assert p.act_tilt("NO_SUCH_CARD", "IRONCLAD", 2) == 0.0
    # a bare-float (test/legacy) entry has a score but no act tilt
    legacy = CardPriors(by_character={"IRONCLAD": {"X": 6.0}})
    assert legacy.score("X", "IRONCLAD") == 6.0
    assert legacy.act_tilt("X", "IRONCLAD", 1) == 0.0


def test_act_tilt_flips_act_appropriate_pick() -> None:
    """Two equally-rated cards; the act tilt should pick the act-appropriate one."""
    from sts2bot.kb.priors import CardPriors

    priors = CardPriors(
        by_character={
            "IRONCLAD": {
                "EARLY": {"s": 5.0, "a": [1.0, 0.0, -1.0]},
                "LATE": {"s": 5.0, "a": [-1.0, 0.0, 1.0]},
            }
        }
    )
    r = StandardRouter(priors=priors)

    def offered(act):
        cards = [
            {
                "index": 0,
                "id": "EARLY",
                "name": "Early",
                "type": "Attack",
                "cost": "1",
                "rarity": "Uncommon",
                "description": "Deal 6 damage.",
                "is_upgraded": False,
                "keywords": [],
            },
            {
                "index": 1,
                "id": "LATE",
                "name": "Late",
                "type": "Attack",
                "cost": "1",
                "rarity": "Uncommon",
                "description": "Deal 6 damage.",
                "is_upgraded": False,
                "keywords": [],
            },
        ]
        return parse_state(
            {
                "state_type": "card_reward",
                "card_reward": {"cards": cards, "can_skip": True},
                "run": {"act": act, "floor": 3, "ascension": 0},
                "player": {
                    "character": "The Ironclad",
                    "hp": 70,
                    "max_hp": 80,
                    "status": [],
                    "relics": [],
                    "potions": [],
                    "max_potion_slots": 3,
                },
            }
        )

    d1 = r.decide(offered(1), LoopContext())
    assert isinstance(d1, Decision) and d1.action.payload()["card_index"] == 0  # EARLY in act 1
    d3 = r.decide(offered(3), LoopContext())
    assert isinstance(d3, Decision) and d3.action.payload()["card_index"] == 1  # LATE in act 3


def test_card_reward_prior_overrides_heuristics() -> None:
    """A community-loved card must beat a heuristically-flashy but bad card."""
    from sts2bot.kb.priors import CardPriors

    priors = CardPriors(by_character={"IRONCLAD": {"COMMUNITY_GEM": 6.0, "TRAP_CARD": -6.0}})
    r = StandardRouter(priors=priors)
    payload = {
        "state_type": "card_reward",
        "card_reward": {
            "cards": [
                {
                    "index": 0,
                    "id": "TRAP_CARD",
                    "name": "Trap Card",
                    "type": "Power",
                    "cost": "1",
                    "rarity": "Rare",
                    "description": "Gain 1 Energy. Draw 2 cards. Gain 8 Block.",
                    "is_upgraded": False,
                    "keywords": [],
                },
                {
                    "index": 1,
                    "id": "COMMUNITY_GEM",
                    "name": "Community Gem",
                    "type": "Skill",
                    "cost": "1",
                    "rarity": "Common",
                    "description": "Does something subtle the regex cannot price.",
                    "is_upgraded": False,
                    "keywords": [],
                },
            ],
            "can_skip": True,
        },
        "run": {"act": 1, "floor": 4, "ascension": 0},
        "player": {
            "character": "The Ironclad",
            "hp": 70,
            "max_hp": 80,
            "status": [],
            "relics": [],
            "potions": [],
            "max_potion_slots": 3,
        },
    }
    decision = r.decide(parse_state(payload), LoopContext())
    assert isinstance(decision, Decision)
    assert decision.action.payload() == {"action": "select_card_reward", "card_index": 1}
    assert decision.scores["Community Gem"] > decision.scores["Trap Card"]


def test_pilotability_discounts_unplayable_upside() -> None:
    """Owner insight: priors price cards for skilled pilots. A simple solid card
    must beat an equal-prior card whose value lives in text we can't evaluate."""
    from sts2bot.kb.priors import CardPriors

    priors = CardPriors(by_character={"IRONCLAD": {"SIMPLE": 5.0, "ENGINE": 5.0}})
    r = StandardRouter(priors=priors)

    def offer(idx, cid, name, desc, ctype="Skill", rarity="Uncommon"):
        return {
            "index": idx,
            "id": cid,
            "name": name,
            "type": ctype,
            "cost": "1",
            "rarity": rarity,
            "description": desc,
            "is_upgraded": False,
            "keywords": [],
        }

    payload = {
        "state_type": "card_reward",
        "card_reward": {
            "cards": [
                offer(0, "ENGINE", "Engine", "Whenever a card is Exhausted, draw 1 card."),
                offer(1, "SIMPLE", "Simple", "Gain 8 Block."),
            ],
            "can_skip": True,
        },
        "run": {"act": 1, "floor": 4, "ascension": 0},
        "player": {
            "character": "The Ironclad",
            "hp": 70,
            "max_hp": 80,
            "status": [],
            "relics": [],
            "potions": [],
            "max_potion_slots": 3,
        },
    }
    decision = r.decide(parse_state(payload), LoopContext())
    assert isinstance(decision, Decision)
    assert decision.action.payload()["card_index"] == 1
    assert decision.scores["Simple"] > decision.scores["Engine"]


def test_event_refuses_max_hp_drain() -> None:
    """The vampire event: default option drains 1 Max HP per click; leave instead."""
    payload = {
        "state_type": "event",
        "event": {
            "event_id": "VAMPIRE_THING",
            "event_name": "Hungry Shrine",
            "is_ancient": False,
            "in_dialogue": False,
            "body": "It asks for more.",
            "options": [
                {
                    "index": 0,
                    "title": "Continue",
                    "description": "Lose 1 Max HP.",
                    "is_locked": False,
                    "is_proceed": False,
                    "was_chosen": False,
                    "keywords": [],
                },
                {
                    "index": 1,
                    "title": "Leave",
                    "description": "",
                    "is_locked": False,
                    "is_proceed": True,
                    "was_chosen": False,
                    "keywords": [],
                },
            ],
        },
        "run": {"act": 1, "floor": 5, "ascension": 0},
        "player": {
            "character": "The Ironclad",
            "hp": 80,
            "max_hp": 80,
            "status": [],
            "relics": [],
            "potions": [],
            "max_potion_slots": 3,
        },
    }
    decision = router().decide(parse_state(payload), LoopContext())
    assert isinstance(decision, Decision)
    assert decision.action.payload() == {"action": "choose_event_option", "index": 1}


def test_rest_threshold() -> None:
    payload = json.loads(json.dumps(FIXTURES["rest_site"]))
    payload["player"]["hp"] = 30  # 37.5% of 80
    state = parse_state(payload)
    decision = router().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    assert decision.action.payload()["index"] == 0  # rest

    payload["player"]["hp"] = 70
    state = parse_state(payload)
    decision = router().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    assert decision.action.payload()["index"] == 1  # smith


def _router_with_boss_loss(p75_loss):
    from sts2bot.kb.combat_stats import CombatStats
    from sts2bot.policy.standard import StandardRouter

    stats = CombatStats(by_type={"boss": {"mean": p75_loss * 0.6, "p75": p75_loss, "n": 10}})
    return StandardRouter(combat_stats=stats)


def test_rest_before_boss_survival_estimate() -> None:
    """Pre-boss: rest only if HP can't cover the boss's likely damage (p75 x safety),
    else smith to gear up. With boss p75=60, safety 1.1 -> need ~66 HP."""
    payload = json.loads(json.dumps(FIXTURES["rest_site"]))
    r = _router_with_boss_loss(60)

    payload["player"]["hp"] = 50  # < 66 needed -> rest
    ctx = LoopContext()
    ctx.screen_mem["pre_boss"] = True
    d = r.decide(parse_state(payload), ctx)
    assert isinstance(d, Decision) and d.action.payload()["index"] == 0  # rest
    assert "boss" in d.rationale

    payload["player"]["hp"] = 72  # >= 66 needed -> can survive the boss, so smith
    ctx = LoopContext()
    ctx.screen_mem["pre_boss"] = True
    d = r.decide(parse_state(payload), ctx)
    assert isinstance(d, Decision) and d.action.payload()["index"] == 1  # smith


def test_full_belt_discards_for_potion_reward() -> None:
    payload = json.loads(json.dumps(FIXTURES["rewards"]))
    payload["player"]["potions"] = [
        {"id": "BLOCK_POTION", "name": "Block Potion", "slot": 0},
        {"id": "DEX_POTION", "name": "Dexterity Potion", "slot": 1},
        {"id": "FLEX_POTION", "name": "Flex Potion", "slot": 2},
    ]
    payload["player"]["max_potion_slots"] = 3
    state = parse_state(payload)
    decision = router().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    assert decision.action.payload() == {"action": "discard_potion", "slot": 0}


def _sc_card(index, name, ctype="Attack", rarity="Common", upgraded=False, cid=None):
    return {
        "index": index,
        "id": cid or name.upper().replace(" ", "_"),
        "name": name,
        "type": ctype,
        "cost": "1",
        "star_cost": None,
        "description": "x",
        "rarity": rarity,
        "is_upgraded": upgraded,
        "keywords": [],
    }


def _card_select_state(screen_type, prompt, cards, can_confirm=False, can_cancel=True):
    return parse_state(
        {
            "state_type": "card_select",
            "card_select": {
                "screen_type": screen_type,
                "prompt": prompt,
                "cards": cards,
                "preview_showing": False,
                "can_confirm": can_confirm,
                "can_cancel": can_cancel,
            },
            "run": {"act": 1, "floor": 5, "ascension": 0},
            "player": {
                "character": "The Ironclad",
                "hp": 70,
                "max_hp": 80,
                "status": [],
                "relics": [],
                "potions": [],
                "max_potion_slots": 3,
            },
        }
    )


def test_removal_targets_basics_not_good_cards() -> None:
    """The boss-analysis ceiling: thinning never helped because removal hit arbitrary
    cards. Remove a basic, never Bash."""
    cards = [_sc_card(0, "Bash"), _sc_card(1, "Strike"), _sc_card(2, "Defend", "Skill")]
    d = router().decide(
        _card_select_state("select", "Choose a card to Remove.", cards), LoopContext()
    )
    assert isinstance(d, Decision)
    assert d.action.payload()["index"] in (1, 2)  # a basic, not Bash


def test_removal_prioritizes_curse() -> None:
    cards = [_sc_card(0, "Strike"), _sc_card(1, "Regret", "Curse", rarity="Curse")]
    d = router().decide(
        _card_select_state("select", "Choose a card to Remove.", cards), LoopContext()
    )
    assert isinstance(d, Decision) and d.action.payload()["index"] == 1


def test_upgrade_targets_best_unupgraded() -> None:
    cards = [
        _sc_card(0, "Strike"),
        _sc_card(1, "Inflame", "Power", rarity="Uncommon"),
        _sc_card(2, "Inflame", "Power", rarity="Uncommon", upgraded=True),
    ]
    d = router().decide(
        _card_select_state("upgrade", "Choose a card to Upgrade.", cards), LoopContext()
    )
    assert isinstance(d, Decision) and d.action.payload()["index"] == 1  # unupgraded Inflame


def test_upgrade_targets_highest_upgrade_value() -> None:
    """Owner tip: upgrade by upgraded-vs-base value, not base card quality. The card
    that GAINS the most from upgrading wins even if another card is better overall."""
    from sts2bot.kb.priors import CardPriors

    priors = CardPriors(
        by_character={
            "IRONCLAD": {
                "BIGGAIN": {"s": 3.0, "u": 4.5},
                "SMALLGAIN": {"s": 6.0, "u": 0.3},  # better card, barely improves
            }
        }
    )
    r = StandardRouter(priors=priors)
    cards = [
        _sc_card(0, "Small Gain", "Skill", cid="SMALLGAIN"),
        _sc_card(1, "Big Gain", "Attack", cid="BIGGAIN"),
    ]
    d = r.decide(_card_select_state("upgrade", "Choose a card to Upgrade.", cards), LoopContext())
    assert isinstance(d, Decision) and d.action.payload()["index"] == 1


def test_add_screen_targets_best() -> None:
    cards = [_sc_card(0, "Strike"), _sc_card(1, "Offering", "Skill", rarity="Rare")]
    d = router().decide(_card_select_state("choose", "Choose a card.", cards), LoopContext())
    assert isinstance(d, Decision) and d.action.payload()["index"] == 1  # the good card


def test_multi_remove_picks_two_worst_then_confirms() -> None:
    r = router()
    ctx = LoopContext()
    cards = [
        _sc_card(0, "Bash"),
        _sc_card(1, "Strike"),
        _sc_card(2, "Strike"),
        _sc_card(3, "Defend", "Skill"),
    ]
    state = _card_select_state("select", "Choose 2 cards to Remove.", cards)
    d1 = r.decide(state, ctx)
    d2 = r.decide(state, ctx)
    assert isinstance(d1, Decision) and isinstance(d2, Decision)
    picks = {d1.action.payload()["index"], d2.action.payload()["index"]}
    assert picks <= {1, 2, 3} and len(picks) == 2  # two distinct basics, never Bash(0)
    assert isinstance(r.decide(state, ctx), Wait)  # enough chosen; awaiting confirm
    confirm = r.decide(
        _card_select_state("select", "Choose 2 cards to Remove.", cards, can_confirm=True), ctx
    )
    assert isinstance(confirm, Decision)
    assert confirm.action.payload()["action"] == "confirm_selection"


def test_choose_screen_skips_when_stuck() -> None:
    """Run 2 stalled: a 'choose' screen returned ok but never resolved and the
    handler waited forever. Bounded retries, then skip — never an indefinite wait."""
    cards = [
        _sc_card(0, "Panic Button", "Skill"),
        _sc_card(1, "The Gambit", "Skill", rarity="Uncommon"),
        _sc_card(2, "Bolas", "Skill"),
    ]
    state = _card_select_state("choose", "Choose a card.", cards)
    r = router()
    ctx = LoopContext()
    for _ in range(3):  # re-presses the pick a few times
        d = r.decide(state, ctx)
        assert isinstance(d, Decision) and d.action.payload()["action"] == "select_card"
    final = r.decide(state, ctx)  # gives up -> skip, not a Wait
    assert isinstance(final, Decision)
    assert final.action.payload()["action"] == "cancel_selection"


def _shop_with_removal(price, gold=400, deck=None, full_belt=True):
    payload = json.loads(json.dumps(FIXTURES["shop"]))
    payload["player"]["gold"] = gold
    if deck is not None:
        payload["player"]["deck"] = deck
    if full_belt:  # fill the belt so potion buys don't pre-empt the removal check
        payload["player"]["potions"] = [
            {"id": f"P{i}", "name": f"P{i}", "slot": i} for i in range(3)
        ]
        payload["player"]["max_potion_slots"] = 3
    for it in payload["shop"]["items"]:
        if it["category"] == "card_removal":
            it["price"] = price
    return parse_state(payload)


def test_shop_removal_price_reluctance() -> None:
    deck = [_sc_card(0, "Strike")]  # a removable basic exists
    expensive = router().decide(_shop_with_removal(200, deck=deck), LoopContext())
    assert isinstance(expensive, Decision)
    p = expensive.action.payload()
    assert not (p["action"] == "shop_purchase" and p["index"] == 10)  # 200g removal skipped

    cheap = router().decide(_shop_with_removal(100, deck=deck), LoopContext())
    assert isinstance(cheap, Decision)
    assert cheap.action.payload() == {
        "action": "shop_purchase",
        "index": 10,
    }  # 100g removal bought


def test_shop_skips_removal_when_nothing_worth_removing() -> None:
    deck = [
        _sc_card(0, "Bash"),
        _sc_card(1, "Inflame", "Power", rarity="Uncommon"),
    ]  # no basics/curses
    d = router().decide(_shop_with_removal(100, deck=deck), LoopContext())
    assert isinstance(d, Decision)
    p = d.action.payload()
    assert not (p["action"] == "shop_purchase" and p["index"] == 10)


def test_standard_router_handles_every_fixture() -> None:
    """Replay-smoke over all committed fixtures: never raises, returns Decision|Wait."""
    r = router()
    states = {k: v for k, v in FIXTURES.items() if not k.startswith("_")}
    live_dir = Path(__file__).parent / "fixtures" / "live"
    payloads = list(states.values()) + [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(live_dir.glob("*.json"))
    ]
    ctx = LoopContext()
    for payload in payloads:
        decision = r.decide(parse_state(payload), ctx)
        assert isinstance(decision, Decision | Wait)
