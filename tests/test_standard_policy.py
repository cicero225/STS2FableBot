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


def test_rest_tops_up_before_boss() -> None:
    """Entered Ceremonial Beast at 46/91 and lost with the boss at 32 HP. On the
    last row before the boss, rest unless nearly full."""
    payload = json.loads(json.dumps(FIXTURES["rest_site"]))
    payload["player"]["hp"] = 64  # 80% of 80 — would normally smith
    state = parse_state(payload)

    ctx = LoopContext()
    decision = router().decide(state, ctx)
    assert isinstance(decision, Decision)
    assert decision.action.payload()["index"] == 1  # smith normally

    ctx.screen_mem["pre_boss"] = True
    decision = router().decide(state, ctx)
    assert isinstance(decision, Decision)
    assert decision.action.payload()["index"] == 0  # rest before the boss
    assert "boss next" in decision.rationale


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
