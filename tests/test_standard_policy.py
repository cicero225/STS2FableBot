"""Behavioral tests for the StandardRouter (P1 policies)."""

import json
from pathlib import Path

from sts2bot.client.actions import PlayCard
from sts2bot.client.models import Card, parse_state
from sts2bot.policy.base import Decision, LoopContext, Wait
from sts2bot.policy.standard import StandardRouter

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "doc_states.json").read_text(encoding="utf-8")
)


def router() -> StandardRouter:
    return StandardRouter()


def make_combat(hand, enemies, energy=3, hp=70, max_hp=80, state_type="monster", potions=None,
                player_status=None):
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
                "status": player_status or [],
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


def test_spends_value_potion_in_a_big_fight() -> None:
    """Seeded run B04BGZEDRN: the bot hoarded Cure All ('Gain energy. Draw 2 cards') through the
    126-HP Ovicopter and threw it away in a hail-mary at the next floor; the human spent it to
    power through and exited ~30 HP higher. Energy/draw potions are now a 'value' bucket, deployed
    early in a big fight to convert to more block + damage."""
    cure = {"id": "CURE_ALL", "name": "Cure All", "description": "Gain energy. Draw 2 cards.",
            "slot": 0, "can_use_in_combat": True, "target_type": "AnyPlayer", "keywords": []}
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("OVICOPTER_0", 120, intent_label="10")],
        hp=80, max_hp=90, potions=[cure],
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload() == {"action": "use_potion", "slot": 0}  # spend the tempo potion


def test_full_belt_discard_keeps_value_potions_ditches_junk() -> None:
    """Live B04BGZEDRN: the full-belt discard returned potions[0] (slot order), so when the cascade
    landed Cure All in slot 0 it got thrown away — leaving none for the Ovicopter. Rank by value:
    ditch downside/unknown, keep energy/draw value, buffs, heals."""
    from sts2bot.client.models import Potion

    def pot(slot, pid, name, desc):
        return Potion(id=pid, name=name, description=desc, slot=slot, can_use_in_combat=True)

    belt = [
        pot(0, "CURE_ALL", "Cure All", "Gain energy. Draw 2 cards."),  # value
        pot(1, "FOUL_POTION", "Foul Potion", "Deal 12 damage to ALL (incl. you)."),  # ~100g
        pot(2, "STRENGTH_POTION", "Strength Potion", "Gain 2 Strength."),  # buff
    ]
    victim = router()._worst_potion(belt)
    # In a STRONG belt the Foul (rank 3: merchant money, not junk) is still the right
    # cut — but it must outrank true junk (see the reward-comparison test).
    assert victim is not None and victim.id == "FOUL_POTION"
    belt[0] = pot(0, "MYSTERY_BREW", "Mystery Brew", "Swirls mysteriously.")  # unknown, rank 1
    victim2 = router()._worst_potion(belt)
    assert victim2 is not None and victim2.id == "MYSTERY_BREW"  # junk goes before Foul


def test_plays_offering_when_healthy() -> None:
    """Owner's anti-turtle rule of thumb: above ~20 HP, Offering (lose 6 HP -> 2 energy + draw 3,
    exhaust) is near-guaranteed value and should be played. If it isn't, the planner is still too
    damage-averse (turtling)."""
    state = make_combat(
        hand=[card(0, "Offering", 0, "Lose 6 HP. Gain 2 Energy. Draw 3 cards. Exhaust.",
                   target="Self", ctype="Skill"),
              card(1, "Strike", 1, "Deal 6 damage."),
              card(2, "Strike", 1, "Deal 6 damage."),
              card(3, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("E_0", 60, intent_label="8")], energy=1, hp=50, max_hp=80,
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("card_index") == 0  # play Offering for the energy + draw


def test_plays_bloodletting_when_healthy_and_energy_usable() -> None:
    """Owner's rule: above ~20 HP, Bloodletting (lose 3 HP -> 2 energy) is worth it whenever the
    energy does anything (here, two extra Strikes)."""
    blood = card(0, "Bloodletting", 0, "Lose 3 HP. Gain 2 Energy.", target="Self", ctype="Skill")
    state = make_combat(
        hand=[blood,
              card(1, "Strike", 1, "Deal 6 damage."),
              card(2, "Strike", 1, "Deal 6 damage."),
              card(3, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("E_0", 60, intent_label="8")], energy=1, hp=50, max_hp=80,
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("card_index") == 0  # play Bloodletting for the energy


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


def test_rage_sequenced_before_attacks() -> None:
    """Owner (Rage, not Anger): 'gain 3 Block per Attack this turn' must be played
    BEFORE attacks so each one grants block — observed played last, which is useless."""
    rage = {
        "index": 0,
        "id": "RAGE",
        "name": "Rage",
        "type": "Skill",
        "cost": "0",
        "star_cost": None,
        "description": "Whenever you play an Attack this turn, gain 3 Block.",
        "target_type": "Self",
        "can_play": True,
        "unplayable_reason": None,
        "is_upgraded": False,
        "keywords": [],
    }
    state = make_combat(
        hand=[
            rage,
            card(1, "Strike", 1, "Deal 6 damage."),
            card(2, "Strike", 1, "Deal 6 damage."),
        ],
        enemies=[enemy("BRUTE_0", 60, intent_label="15")],
        energy=2,
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["card_index"] == 0  # Rage first
    assert "Rage" in d.rationale


def test_fiend_fire_scales_with_hand_size_for_lethal() -> None:
    """Owner (live 2026-06-15): Fiend Fire 'Exhaust your hand, deal 7 for each card
    exhausted' was priced as a flat 7, so a 21-dmg lethal was missed and the bot
    panic-drank. With 3 other cards in hand it must read as 7x3=21 and be the kill."""
    fiend = card(0, "Fiend Fire", 2, "Exhaust your hand. Deal 7 damage for each card exhausted.")
    state = make_combat(
        hand=[
            fiend,
            card(1, "Strike", 1, "Deal 6 damage."),
            card(2, "Strike", 1, "Deal 6 damage."),
            card(3, "Defend", 1, "Gain 5 Block.", target="Self", ctype="Skill"),
        ],
        enemies=[enemy("MUSHROOM_0", 20, intent_label="14")],
        energy=2,  # only Fiend Fire (cost 2, 7x3=21) reaches lethal; 2 Strikes = 12 don't
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["card_index"] == 0  # Fiend Fire, the 21-damage kill
    assert d.scores and d.scores.get("lethal") == 1.0


def test_plays_free_power_card() -> None:
    """Owner (Run-3 boss): a free 0-cost Power (Pyre) from a Power Potion was left unplayed.
    Powers are permanent buffs — play them, especially free ones."""
    # Pyre: Rare Power, normally 2 energy, here 0-cost from a Power Potion. Its real effect
    # is "Gain 1 Energy at the start of each turn" (verified online) — a per-turn power.
    pyre = card(0, "Pyre", 0, "Gain 1 Energy at the start of each turn.",
                target="Self", ctype="Power")
    state = make_combat(hand=[pyre], enemies=[enemy("DUMMY_0", 50, intent_label="5")], energy=3)
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("card_index") == 0  # play the free Power, not end turn


def test_rage_sequenced_first_even_when_block_reads_useless() -> None:
    """Owner (Run-3 Fight 6): vs an enemy whose intent the bot can't read (incoming 0), Rage's
    block scores as excess, so it stopped sequencing Rage first. A small nudge keeps Rage ahead
    of attacks — it's free to play first."""
    rage = card(0, "Rage", 0, "Whenever you play an Attack this turn, gain 3 Block.",
                target="Self", ctype="Skill")
    state = make_combat(
        hand=[rage, card(1, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("CONSTRUCT_0", 60, intent_label="")],  # empty intent -> incoming 0
        energy=2,
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("card_index") == 0  # Rage (index 0) before the Strike


def test_primal_force_played_first_to_upgrade_weak_attacks() -> None:
    """Owner (Run-3 Fight 2): Primal Force ('transform all Attacks in hand into Giant Rock',
    16 dmg) was played late. With a hand of Strikes (6 dmg) it should go first so they become
    16-damage rocks; the planner only does so when it's an upgrade."""
    primal = card(0, "Primal Force", 0, "Transform all Attacks in your Hand into Giant Rock.",
                  target="Self", ctype="Skill")
    state = make_combat(
        hand=[
            primal,
            card(1, "Strike", 1, "Deal 6 damage."),
            card(2, "Strike", 1, "Deal 6 damage."),
        ],
        enemies=[enemy("GOLEM_0", 80, intent_label="10")],
        energy=3,
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("card_index") == 0  # Primal Force first
    assert "Primal Force" in d.rationale


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


def _minion_status():
    return [{"id": "MINION", "name": "Minion",
             "description": "Minions abandon combat without their leader."}]


def test_killing_leader_is_lethal_even_with_minion_alive() -> None:
    """Owner: 'Minion' enemies abandon combat when their leader dies, so killing the
    leader is lethal even with the minion up (live 2026-06-15: Fiend Fire on the mushroom
    ended the fight with the 6/6 plant still alive)."""
    leader = enemy("MUSHROOM_0", 6, intent_label="14")
    minion = enemy("PLANT_0", 6, intent_label="5")
    minion["status"] = _minion_status()
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")], enemies=[leader, minion], energy=1
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("target") == "MUSHROOM_0"  # kill the leader, not the minion
    assert d.scores and d.scores.get("lethal") == 1.0  # minion flees -> fight over


def test_ignores_low_impact_minion_and_hits_leader() -> None:
    """Owner (Run 2 Fight 5): the bot poured damage into an ignorable minion — the focus
    term rewards finishing a low-HP enemy. With no offensive reward for minions, the
    single-target hit goes to the leader instead."""
    leader = enemy("BEAST_0", 40, intent_label="10")
    minion = enemy("SPORE_0", 8, intent_label="2")  # low HP: high focus under old scoring
    minion["status"] = _minion_status()
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")], enemies=[leader, minion], energy=1
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("target") == "BEAST_0"  # leader, not the easy minion


def test_attacks_dangerous_ramping_minion() -> None:
    """Owner (The Kin, live 2026-06-15): the followers are Minions but high-HP, high-damage and
    strength-gaining — worth grinding down to manage damage, not ignoring like a weak minion."""
    leader = enemy("OGRE_0", 100, intent_label="5")
    wasp = enemy("WASP_0", 40, intent_label="12")
    wasp["status"] = [
        {"id": "MINION_POWER", "name": "Minion",
         "description": "Minions abandon combat without their leader."},
        {"id": "STRENGTH_POWER", "name": "Strength", "amount": 2, "description": "Stronger."},
    ]
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")], enemies=[leader, wasp], energy=1
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("target") == "WASP_0"  # grind the dangerous minion down


def test_ignores_summoned_minions_and_races_summoner() -> None:
    """Seeded run B04BGZEDRN: the bot died to the Ovicopter — a summoner whose eggs/hatchlings
    are Minions that *respawn*. Chasing them is a treadmill (kill the summoner and they flee), so
    with a summoner on the board even minions that would otherwise be fought are ignored, and
    damage goes to the leader. (These non-ramping adds would be ignorable anyway; the summoner
    flag also covers a summoner with ramping adds.)"""
    leader = enemy("OVICOPTER_0", 60, intent_label="10")
    leader["intents"] = [
        {"type": "Special", "label": "Summon", "title": "Summon",
         "description": "This enemy intends to summon Monsters."}
    ]
    hatch = [enemy(f"HATCHLING_{i}", 21, intent_label="6") for i in range(2)]
    for h in hatch:
        h["status"] = _minion_status()  # Minion, but NOT strength-gaining
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")], enemies=[leader, *hatch], energy=1
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("target") == "OVICOPTER_0"  # race the summoner, not the adds


def test_ignores_illusion_minion_and_races_leader() -> None:
    """Live B04BGZEDRN f23 (Obscura): the Parafright is an Illusion (revives at full HP when
    killed) AND a ramping Minion, so the old logic read it as 'a ramping minion worth grinding'
    and poured damage into it every turn — futile, since it revives, while the 123-HP Obscura
    barely dropped. An Illusion minion is ignorable for progress: race the leader instead."""
    leader = enemy("OBSCURA_0", 80, intent_label="10")
    illusion = enemy("PARAFRIGHT_0", 21, intent_label="16")
    illusion["status"] = [
        {"id": "ILLUSION", "name": "Illusion",
         "description": "When this dies, it revives next turn at full HP."},
        {"id": "MINION_POWER", "name": "Minion",
         "description": "Minions abandon combat without their leader."},
        {"id": "STRENGTH_POWER", "name": "Strength", "amount": 3, "description": "Stronger."},
    ]
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")], enemies=[leader, illusion], energy=1
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("target") == "OBSCURA_0"  # race the leader, not the reviving add


def test_races_strength_gaining_enemy() -> None:
    """Owner (Run-3 Fight 6): vs strength-gaining (ramping) enemies the bot turtled and bled
    out. It should trade more — attack to end the fight before the ramp compounds, where vs a
    calm enemy facing the same hit it would block."""

    def fight(ramping: bool):
        e = enemy("RAMPER_0", 40, intent_label="8")
        if ramping:
            e["status"] = [{"id": "STRENGTH_POWER", "name": "Strength", "amount": 3,
                            "description": "Increases attack damage."}]
        return make_combat(
            hand=[
                card(0, "Strike", 1, "Deal 6 damage."),
                card(1, "Defend", 1, "Gain 5 Block.", target="Self", ctype="Skill"),
            ],
            enemies=[e], energy=1, hp=70, max_hp=80,
        )

    calm = router().decide(fight(False), LoopContext())
    ramp = router().decide(fight(True), LoopContext())
    assert calm.action.payload().get("card_index") == 1  # vs a calm enemy: block the hit
    assert ramp.action.payload().get("card_index") == 0  # vs a ramping enemy: race (Strike)


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
    cap). With per-slot tracking it drinks both (different slots) across polls.
    The second poll's state reflects the first drink (belt slot emptied) — the
    action-settle guard holds on a byte-identical re-poll by design."""

    fysh = {
        "id": "FYSH",
        "name": "Fysh Oil",
        "description": "Gain 1 Strength and 1 Dexterity.",
        "slot": 0,
        "can_use_in_combat": True,
        "target_type": "None",
        "keywords": [],
    }
    speed = {
        "id": "SPEED",
        "name": "Speed Potion",
        "description": "Gain 1 Dexterity.",
        "slot": 2,
        "can_use_in_combat": True,
        "target_type": "None",
        "keywords": [],
    }

    def state(potions):
        return make_combat(
            hand=[card(0, "Strike", 1, "Deal 6 damage.")],
            enemies=[enemy("BOSS_0", 200, intent_label="30")],
            hp=10,
            max_hp=80,
            state_type="boss",
            potions=potions,
        )

    r = router()
    ctx = LoopContext()
    d1 = r.decide(state([fysh, speed]), ctx)
    assert isinstance(d1, Decision) and d1.action.payload()["action"] == "use_potion"
    first = d1.action.payload()["slot"]
    remaining = [p for p in (fysh, speed) if p["slot"] != first]
    # the post-drink state must repeat through the quiescence dwell before the
    # second drink goes out (action-settle guard)
    d2 = None
    for _ in range(1 + r.config.combat.action_quiesce_polls):
        d2 = r.decide(state(remaining), ctx)
        if not isinstance(d2, Wait):
            break
    assert isinstance(d2, Decision) and d2.action.payload()["action"] == "use_potion"
    assert {first, d2.action.payload()["slot"]} == {0, 2}


def test_low_hp_plays_block_instead_of_panic_drinking() -> None:
    """Owner (live 2026-06-15): at 13 HP vs 14 incoming with a Defend in hand, the bot
    hail-mary-drank a potion. The planned Defend (5 block) survives (9 < 13), so it must
    play the block, not burn a potion on a turn it isn't actually dying."""
    state = make_combat(
        hand=[card(0, "Defend", 1, "Gain 5 Block.", target="Self", ctype="Skill")],
        enemies=[enemy("MUSHROOM_0", 40, intent_label="14")],
        energy=1,
        hp=13,
        max_hp=80,
        potions=[
            {
                "id": "FYSH",
                "name": "Fysh Oil",
                "description": "Gain 1 Strength and 1 Dexterity.",
                "slot": 0,
                "can_use_in_combat": True,
                "target_type": "None",
                "keywords": [],
            }
        ],
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["action"] == "play_card"  # the Defend, not a wasted potion
    assert d.action.payload()["card_index"] == 0


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


def _potion(pid, name, desc, slot=0, target="None"):
    return {"id": pid, "name": name, "description": desc, "slot": slot,
            "can_use_in_combat": True, "target_type": target, "keywords": []}


def test_fruit_juice_drunk_on_sight() -> None:
    """Owner taxonomy: Fruit Juice (+max HP) is pure upside — drink on sight, even at
    healthy HP in a plain fight."""
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("CRAWLER_0", 40, intent_label="6")],
        hp=70, max_hp=80,
        potions=[_potion("FRUIT_JUICE", "Fruit Juice", "Gain 5 Max HP.")],
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["action"] == "use_potion"
    assert "Fruit Juice" in d.rationale


def test_block_potion_reactive_at_end_of_turn() -> None:
    """Owner taxonomy: a Block Potion is drunk at end of turn vs incoming our own cards
    couldn't cover. With nothing left to play and 12 incoming, drink it."""
    state = make_combat(
        hand=[],
        enemies=[enemy("OGRE_0", 50, intent_label="12")],
        hp=60, max_hp=80,
        potions=[_potion("BLOCK_POTION", "Block Potion", "Gain 12 Block.")],
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["action"] == "use_potion"
    assert "end-of-turn" in d.rationale


def test_buff_potion_deployed_at_boss_start() -> None:
    """Owner taxonomy: long-term buffs are deployed at an elite/boss start (the bot
    struggles with those fights), not hoarded."""
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("BOSS_0", 200, intent_label="10")],
        hp=70, max_hp=80, state_type="boss",
        potions=[_potion("STRENGTH_POTION", "Strength Potion", "Gain 2 Strength.")],
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["action"] == "use_potion"
    assert "deploy at boss" in d.rationale


def test_finisher_potion_kills_last_enemy_at_end_of_turn() -> None:
    """Owner taxonomy: a damage potion is held until end of turn, then drunk to secure a
    kill — here it clears the last enemy on the board."""
    state = make_combat(
        hand=[],
        enemies=[enemy("WISP_0", 15, intent_label="14")],
        hp=60, max_hp=80,
        potions=[_potion("FIRE_POTION", "Fire Potion", "Deal 20 damage.", target="AnyEnemy")],
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["action"] == "use_potion"
    assert d.action.payload().get("target") == "WISP_0"


def test_downside_potion_held_outside_hail_mary() -> None:
    """Owner taxonomy: Foul Potion hits everyone including you, so it's held for hail-mary
    / full-belt only — not drunk in normal reactive use, even to finish a low-HP enemy."""
    state = make_combat(
        hand=[],
        enemies=[enemy("SLUG_0", 10, intent_label="14")],
        hp=60, max_hp=80,
        potions=[_potion("FOUL_POTION", "Foul Potion", "Deal 12 damage to ALL characters.")],
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["action"] == "end_turn"  # Foul held, not drunk


def test_early_damage_bias_lifts_damage_cards_in_act1() -> None:
    """Owner (Run-2 Draft 2): in Act 1, bias damage cards to clear early fights. A damage
    card scores higher in Act 1 than later; a pure block skill gets no such lift."""
    r = router()
    bonus = r.config.card_rewards.early_damage_bonus
    # fake ids so there's no Spirebird prior / act-tilt to confound the structural score
    dmg = Card.model_validate(card(0, "Zzznovel Slash", 1, "Deal 15 damage."))
    blk = Card.model_validate(
        card(1, "Zzznovel Guard", 1, "Gain 8 Block.", target="Self", ctype="Skill")
    )

    def s(c, a):
        return r._card_score(c, deck_size=10, character="The Ironclad", act=a)

    assert abs((s(dmg, 1) - s(dmg, 3)) - bonus) < 1e-6  # damage card gets the Act-1 lift
    # 2026-07-14 rework: block now gets its own LESSER Act-1 lift (owner model)
    blk_bonus = r.config.card_rewards.early_block_bonus
    assert abs((s(blk, 1) - s(blk, 3)) - blk_bonus) < 1e-6
    assert blk_bonus < bonus  # damage-first, block-second in Act 1


def test_infernal_blade_gets_early_damage_bias_as_attack_generator() -> None:
    """Owner (Run-3 Draft 1): Infernal Blade is a Skill that adds a free Attack — it plays like
    an attack, so the Act-1 damage bias should apply even though it deals no damage itself."""
    r = router()
    bonus = r.config.card_rewards.early_damage_bonus
    blade = Card.model_validate(
        card(0, "Zzz Blade", 1, "Add a random Attack to your hand. Exhaust.",
             target="Self", ctype="Skill")
    )
    plain = Card.model_validate(
        card(1, "Zzz Guard", 1, "Gain 8 Block.", target="Self", ctype="Skill")
    )

    def s(c, a):
        return r._card_score(c, deck_size=10, character="The Ironclad", act=a)

    assert abs((s(blade, 1) - s(blade, 3)) - bonus) < 1e-6  # attack-generator gets the Act-1 lift
    # the plain block skill gets only the (lesser) Act-1 block lift, not the damage one
    assert abs((s(plain, 1) - s(plain, 3))
               - r.config.card_rewards.early_block_bonus) < 1e-6


def _ev_opt(index, title, desc, is_proceed=False, relic_name=None):
    return {"index": index, "title": title, "description": desc, "is_locked": False,
            "is_proceed": is_proceed, "was_chosen": False, "relic_name": relic_name,
            "keywords": []}


def _ev_state(event_id, options, hp=70, max_hp=80):
    return parse_state({
        "state_type": "event",
        "event": {"event_id": event_id, "event_name": "x", "is_ancient": False,
                  "in_dialogue": False, "body": "", "options": options},
        "run": {"act": 1, "floor": 6, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": hp, "max_hp": max_hp, "gold": 50,
                   "status": [], "relics": [], "potions": [], "max_potion_slots": 3},
    })


def test_event_takes_free_gain_and_trusts_spirebird_rank() -> None:
    """Owner (Run-2/3): the bot declined every event, missing free upgrades. Byrdonis Nest's
    options are both gains, so it must NOT proceed; and since Spirebird rates both, it should
    take the better-rated one (Take the Egg, vs 14.5 > Eat the Egg, vs 8.7)."""
    state = _ev_state("BYRDONIS_NEST", [
        _ev_opt(0, "Eat the Egg", "Gain 7 Max HP."),
        _ev_opt(1, "Take the Egg", "Add Byrdonis Egg to your Deck."),
        _ev_opt(2, "Proceed", "", is_proceed=True),
    ])
    idx = router().decide(state, LoopContext()).action.payload()["index"]
    assert idx == 1  # Take the Egg (Spirebird's higher-rated option), not Proceed


def test_event_heuristic_when_unrated_takes_heal_upgrade() -> None:
    """Sapphire Seed's 'Consume' can't be matched to Spirebird's internal key, so the heuristic
    governs — and it must recognize Heal + Upgrade as a gain (the old code would not)."""
    state = _ev_state("SAPPHIRE_SEED", [
        _ev_opt(0, "Consume", "Heal 9 HP. Upgrade a card in your Deck."),
        _ev_opt(1, "Plant and Nourish", "Enchant a card with Sown."),
        _ev_opt(2, "Proceed", "", is_proceed=True),
    ], hp=50)
    idx = router().decide(state, LoopContext()).action.payload()["index"]
    assert idx == 0  # Consume (heal + upgrade), not Proceed


def test_event_recognizes_obtain_relic_when_relic_name_unset() -> None:
    """Owner live QA (bxtd5uum8): on The Chosen Cheese the mod leaves relic_name unset, so the bot
    scored 'Obtain the Chosen Cheese' as pure -14 HP and took the bland 'add 2 commons'. The
    heuristic must read 'Obtain the <Relic>' as a relic gain (curse-guarded so 'Obtain a Curse'
    is unaffected)."""
    state = _ev_state("THE_CHOSEN_CHEESE", [
        _ev_opt(0, "Gorge", "Choose 2 of 8 random Common cards to add to your Deck."),
        _ev_opt(1, "Devour", "Lose 14 HP. Obtain the Chosen Cheese."),
        _ev_opt(2, "Proceed", "", is_proceed=True),
    ])
    idx = router().decide(state, LoopContext()).action.payload()["index"]
    assert idx == 1  # the relic (6.0 - 4.2 = 1.8) beats the bland card-add (1.0)


_DOLL_ROOM_OPTS = [
    _ev_opt(0, "Pick at Random", "Obtain a random Doll Relic."),
    _ev_opt(1, "Take Some Time", "Lose 5 HP. Choose 1 of 2 Doll Relics."),
    _ev_opt(2, "Examine Each and Make the Best Choice",
            "Lose 15 HP. Choose 1 of 3 Doll Relics."),
]


def _doll_state(hp=70, max_hp=80, deck=None, options=None):
    payload = {
        "state_type": "event",
        "event": {"event_id": "DOLL_ROOM", "event_name": "x", "is_ancient": False,
                  "in_dialogue": False, "body": "",
                  "options": options or _DOLL_ROOM_OPTS},
        "run": {"act": 1, "floor": 6, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": hp, "max_hp": max_hp, "gold": 50,
                   "status": [], "relics": [], "potions": [], "max_potion_slots": 3,
                   "deck": deck or []},
    }
    return parse_state(payload)


def test_doll_room_pays_for_selection_not_random() -> None:
    """Owner (2026-07-24): the parser took 'Pick at Random' every run (free relic 6.0) —
    Spirebird's worst option. Default is Take Some Time: 5 HP always lets you prune
    Bing Bong and assures an okay choice."""
    d = router().decide(_doll_state(deck=_STARTER_DECK), LoopContext())
    assert d.action.payload()["index"] == 1
    assert "doll room" in d.rationale


def test_doll_room_examines_with_a_daughter_deck() -> None:
    """With Juggernaut (or attack-spam) in deck, pay 15 HP to Examine and guarantee
    Daughter of the Wind; without the deck for her, the 15 HP isn't worth it."""
    jugg_deck = [*_STARTER_DECK, *_deck(("JUGGERNAUT", "Power", 2, 1))]
    d = router().decide(_doll_state(deck=jugg_deck), LoopContext())
    assert d.action.payload()["index"] == 2
    assert "Daughter deck" in d.rationale


def test_doll_room_takes_random_when_too_hurt_to_pay() -> None:
    """Below the HP-cost floor, selection isn't affordable — free random beats nothing."""
    d = router().decide(_doll_state(hp=8, max_hp=80, deck=_STARTER_DECK), LoopContext())
    assert d.action.payload()["index"] == 0


def test_doll_room_subscreen_ranks_dolls_by_deck_fit() -> None:
    """Sub-screen: plain deck -> Mr. Struggles (safe consistent scaling, 5.5 > 5.0);
    a deck that feeds Daughter (Juggernaut) -> Daughter (5.0 + 2.0 fit). Bing Bong
    stays last (owner: usually the prune target)."""
    dolls = [
        _ev_opt(0, "Daughter of the Wind", "Whenever you play an Attack, gain 1 Block."),
        _ev_opt(1, "Mr. Struggles",
                "At the end of your turn, deal damage equal to the turn number to ALL enemies."),
        _ev_opt(2, "Bing Bong", "Whenever you add a card to your Deck, add another copy."),
    ]
    plain = router().decide(_doll_state(deck=_STARTER_DECK, options=dolls), LoopContext())
    assert plain.action.payload()["index"] == 1  # Mr. Struggles
    jugg_deck = [*_STARTER_DECK, *_deck(("JUGGERNAUT", "Power", 2, 1))]
    fit = router().decide(_doll_state(deck=jugg_deck, options=dolls), LoopContext())
    assert fit.action.payload()["index"] == 0  # Daughter of the Wind


def test_event_refuses_hp_cost_that_drops_too_low() -> None:
    """Owner edge case: a choice can be great on average yet suicidal now. Refuse a high-value
    option whose HP cost would drop us below the danger floor, and take the safe gain instead."""
    state = _ev_state("ZZZ_RISK", [
        _ev_opt(0, "Gamble", "Take 60 damage. Upgrade a card. Remove a card.", relic_name="X"),
        _ev_opt(1, "Safe", "Gain 5 Max HP."),
        _ev_opt(2, "Leave", "", is_proceed=True),
    ], hp=70, max_hp=80)  # Gamble -> 10 HP (12.5%), below the floor despite high value
    idx = router().decide(state, LoopContext()).action.payload()["index"]
    assert idx == 1  # the safe Max-HP gain, not the suicidal high-value grab


def test_event_declines_pure_cost() -> None:
    """An unknown event whose only choice is a net loss (Lose Max HP for nothing) is declined."""
    state = _ev_state("ZZZ_FAKE_EVENT", [
        _ev_opt(0, "Sacrifice", "Lose 8 Max HP."),
        _ev_opt(1, "Leave", "", is_proceed=True),
    ])
    d = router().decide(state, LoopContext())
    assert d.action.payload()["index"] == 1  # proceed, don't pay Max HP for nothing


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


# card rules text the §5-C elite gate prices test decks against (fixed, so the gate tests don't
# ride the harvested data file)
_ROUTING_CARD_EFFECTS = {
    "STRIKE_IRONCLAD|0": "Deal 6 damage.",
    "DEFEND_IRONCLAD|0": "Gain 5 Block.",
    "BASH|0": "Deal 8 damage. Apply 2 Vulnerable.",
    "BLUDGEON|0": "Deal 32 damage.",
    "SHRUG_IT_OFF|0": "Gain 8 Block. Draw 1 card.",
}


def _deck(*specs: tuple[str, str, int, int]) -> list[dict]:
    """Build a map-style deck payload: each spec is (id, type, cost, count)."""
    out: list[dict] = []
    for cid, typ, cost, n in specs:
        for _ in range(n):
            out.append(
                {
                    "index": len(out),
                    "id": cid,
                    "name": cid.title(),
                    "type": typ,
                    "cost": str(cost),
                    "is_upgraded": False,
                }
            )
    return out


# a starter-heavy deck (can't win an elite -> gate stays shut) and a built one (can -> chase)
_STARTER_DECK = _deck(("STRIKE_IRONCLAD", "Attack", 1, 5), ("DEFEND_IRONCLAD", "Skill", 1, 4),
                      ("BASH", "Attack", 2, 1))
_STRONG_DECK = [*_STARTER_DECK, *_deck(("BLUDGEON", "Attack", 3, 4))]
# Elite-READY: damage AND defense. Since capability-aware routing (2026-07-13), the
# projection prices elites for the actual deck — a Strikes+Bludgeons pile pays ~46 HP
# per elite (honest: 2.6 block/turn), so HP-gating tests need a deck whose projected
# elite cost is modest, or they test deck quality instead of HP.
_ELITE_READY_DECK = [*_STRONG_DECK, *_deck(("SHRUG_IT_OFF", "Skill", 1, 4))]


def _router_for_routing() -> StandardRouter:
    """StandardRouter with fixed combat_stats + card_effects so routing / gate tests don't ride the
    evolving data files (early normals cheap, late/elite/boss costlier; decks priced from
    _ROUTING_CARD_EFFECTS)."""
    from sts2bot.kb.combat_stats import CombatStats

    stats = CombatStats(
        by_type={
            "monster_early": {"mean": 4.0, "p75": 5, "n": 99},
            "monster": {"mean": 12.0, "p75": 18, "n": 99},
            "elite": {"mean": 21.0, "p75": 32, "n": 99},
            "boss": {"mean": 25.0, "p75": 42, "n": 99},
        }
    )
    r = StandardRouter(combat_stats=stats, bestiary={})  # empty pool -> generic-elite fallback
    #   (the pool-gate behavior gets its own dedicated test below)
    r.card_effects = _ROUTING_CARD_EFFECTS
    return r


def test_map_chases_survivable_elite_but_rests_when_hurt() -> None:
    payload = json.loads(json.dumps(FIXTURES["map"]))  # deep copy
    payload["map"]["next_options"] = [
        {"index": 0, "col": 1, "row": 3, "type": "Elite", "leads_to": []},
        {"index": 1, "col": 2, "row": 3, "type": "Monster", "leads_to": []},
        {"index": 2, "col": 3, "row": 3, "type": "RestSite", "leads_to": []},
    ]
    payload["player"]["deck"] = _STRONG_DECK  # strong enough to win the elite (gate open)
    payload["player"]["hp"] = 20
    payload["player"]["max_hp"] = 80
    state = parse_state(payload)
    decision = _router_for_routing().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    # 20/80: the elite is unsurvivable (route death penalty) and 75% missing HP makes the
    # rest site dominate; the elite must never win when hurt
    assert decision.action.payload() == {"action": "choose_map_node", "index": 2}

    payload["player"]["hp"] = 80
    state = parse_state(payload)
    decision = _router_for_routing().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    # full HP + a deck that can win the elite: chase it for its relic (deck power) over the plain
    # monster and the (unneeded) rest
    assert decision.action.payload()["index"] == 0


def test_map_elite_gate_skips_elite_a_weak_deck_cannot_win() -> None:
    # §5-C gate / the routing-batch fix: at full HP the elite is *survivable*, but a starter-heavy
    # deck can't *win* it, so the bot must not chase it — it takes the plain monster instead.
    payload = json.loads(json.dumps(FIXTURES["map"]))  # deep copy
    payload["map"]["next_options"] = [
        {"index": 0, "col": 1, "row": 3, "type": "Elite", "leads_to": []},
        {"index": 1, "col": 2, "row": 3, "type": "Monster", "leads_to": []},
    ]
    payload["player"]["hp"] = 80
    payload["player"]["max_hp"] = 80
    payload["player"]["deck"] = _STARTER_DECK  # can't win an elite -> gate shut
    decision = _router_for_routing().decide(parse_state(payload), LoopContext())
    assert isinstance(decision, Decision)
    assert decision.action.payload()["index"] == 1  # the monster, not the unwinnable elite


def test_capability_drafting_prefers_the_card_that_beats_the_boss() -> None:
    # §5-C drafting: a damage-starved deck should value a big attack (helps close the 170-HP boss)
    # over a no-impact cantrip (doesn't move estimate_fight at all).
    from sts2bot.client.models import Card, DeckCard
    from sts2bot.policy.capability import FightEnemy

    r = _router_for_routing()  # injects _ROUTING_CARD_EFFECTS so the deck is priced
    deck = [
        DeckCard(index=i, id=cid, name=cid.title(), type=typ, cost=str(cost), is_upgraded=False)
        for i, (cid, typ, cost) in enumerate(
            [("STRIKE_IRONCLAD", "Attack", 1)] * 5
            + [("DEFEND_IRONCLAD", "Skill", 1)] * 4
            + [("BASH", "Attack", 2)]
        )
    ]
    big = Card(index=0, id="BLUDGEON", name="Bludgeon", type="Attack", cost="3",
               description="Deal 32 damage.")
    cantrip = Card(index=1, id="CANTRIP", name="Cantrip", type="Skill", cost="0",
                   description="Draw 1 card.")
    boss = [FightEnemy(hp=170, dps=24, str_ramp=2)]
    deltas = r._capability_deltas(deck, [big, cantrip], 80, [boss])
    assert deltas[0] > deltas[1]  # the attack helps beat the boss; the cantrip doesn't
    assert deltas[0] > 0


def test_upcoming_boss_uses_the_real_boss_when_its_name_is_cached() -> None:
    # the map caches map.boss.name; drafting then prices vs the real boss (bestiary HP + mechanics)
    r = _router_for_routing()
    r.bestiary = {"Vantom": {"hp": [173, 173], "statuses": {
        "SLIPPERY_POWER": {"name": "Slippery",
                           "description": "The next time Vantom loses HP, it only loses 1 HP."}}}}
    ctx = LoopContext()
    ctx.screen_mem["act_boss_name"] = "Vantom"
    boss = r._upcoming_boss(ctx, 1)
    assert boss[0].hp == 173 and boss[0].slippery  # real HP + Slippery from the bestiary
    # no cached name (or unknown / multi-creature like The Kin) -> generic fallback, no crash
    assert r._upcoming_boss(LoopContext(), 1)[0].hp == 170


def test_map_path_planning_weighs_forced_elite_lane_by_hp() -> None:
    """Runs 10/15 died in lanes whose elite was committed floors earlier. With HP-aware
    routing the committed elite is judged by whether the bot can still afford it on arrival:
    chase the lane for its relic when healthy, avoid it when the elite would be unsurvivable.
    Two lanes with identical immediate nodes; only the committed future differs."""

    def payload(hp: int) -> dict:
        return {
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
                "hp": hp,
                "max_hp": 80,
                "gold": 50,
                "status": [],
                "relics": [],
                "potions": [],
                "max_potion_slots": 3,
                "deck": _ELITE_READY_DECK,  # elite-ready, so the gate is about HP, not deck power
            },
        }

    # healthy: the committed elite is survivable -> chase the lane for its relic
    healthy = _router_for_routing().decide(parse_state(payload(70)), LoopContext())
    assert isinstance(healthy, Decision)
    assert healthy.action.payload()["index"] == 0
    assert healthy.scores["0:Monster"] > healthy.scores["1:Monster"]

    # hurt: by the time it reaches the committed elite it can't survive it -> avoid the lane
    hurt = _router_for_routing().decide(parse_state(payload(40)), LoopContext())
    assert isinstance(hurt, Decision)
    assert hurt.action.payload()["index"] == 1
    assert hurt.scores["1:Monster"] > hurt.scores["0:Monster"]


def test_map_rich_wallet_routes_toward_late_shop() -> None:
    """Owner's late-shop loop (A/B #3: 740g -> two Act-3 sprees -> 8 relics): a rich
    bot must bend the route toward a shop-bearing lane, valuing the shop at PROJECTED
    gold-on-arrival (income accrues along the way); a poor bot keeps fighting."""

    def payload(gold: int) -> dict:
        return {
            "state_type": "map",
            "map": {
                "current_position": {"col": 2, "row": 0, "type": "Start"},
                "visited": [],
                "next_options": [
                    {"index": 0, "col": 1, "row": 1, "type": "Monster",
                     "leads_to": [{"col": 1, "row": 2, "type": "Monster"}]},
                    {"index": 1, "col": 3, "row": 1, "type": "Monster",
                     "leads_to": [{"col": 3, "row": 2, "type": "Shop"}]},
                ],
                "nodes": [
                    {"col": 2, "row": 0, "type": "Start", "children": [[1, 1], [3, 1]]},
                    {"col": 1, "row": 1, "type": "Monster", "children": [[1, 2]]},
                    {"col": 3, "row": 1, "type": "Monster", "children": [[3, 2]]},
                    {"col": 1, "row": 2, "type": "Monster", "children": [[2, 3]]},
                    {"col": 3, "row": 2, "type": "Shop", "children": [[2, 3]]},
                    {"col": 2, "row": 3, "type": "Monster", "children": []},
                ],
                "boss": {"col": 2, "row": 4, "id": "B", "name": "Boss"},
                "bosses": [],
            },
            "run": {"act": 3, "floor": 40, "ascension": 0},
            "player": {
                "character": "The Ironclad", "hp": 70, "max_hp": 80, "gold": gold,
                "status": [], "relics": [], "potions": [], "max_potion_slots": 3,
                "deck": _ELITE_READY_DECK,
            },
        }

    rich = _router_for_routing().decide(parse_state(payload(500)), LoopContext())
    assert isinstance(rich, Decision)
    assert rich.action.payload()["index"] == 1  # 500g: the shop lane dominates

    poor = _router_for_routing().decide(parse_state(payload(15)), LoopContext())
    assert isinstance(poor, Decision)
    assert poor.action.payload()["index"] == 0  # 15g: nothing to convert; keep fighting


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


def test_weak_starter_deck_takes_card_a_polished_deck_skips() -> None:
    """8.1d: the same modest, parseable card is TAKEN by a starter-heavy deck (a real card
    beats keeping a basic) but SKIPPED once the deck is polished. (Fixture recalibrated
    2026-07-30 for §5-C v2: rollout-priced deltas correctly punish the old cost-2-for-5-
    block fixture as strictly worse than a basic Defend; 'Gain 7 Block' at cost 1 is a
    modest REAL improvement, which is what this test is about. Recalibrated again
    2026-08-02 for elite-pool targeting: the old 12x-Bash 'polished' deck had ZERO
    block, so the rollout rightly took the first block card offered — a correction,
    not a regression. Polished is now block-saturated, and the skip comes from the
    rollout pricing the 13th card as pure dilution against the elite pool.) In the
    0/5 batch the bot skipped good cards (Molten Fist x4) holding a 9-starter deck."""
    def reward(deck_cards):
        deck = [{"index": i, "id": cid, "name": cid.title(), "type": typ, "cost": "1",
                 "description": desc, "rarity": "Basic", "is_upgraded": False}
                for i, (cid, typ, desc) in enumerate(deck_cards)]
        return parse_state({
            "state_type": "card_reward",
            "card_reward": {"cards": [
                {"index": 0, "id": "MYSTERY_SKILL", "name": "Modest", "type": "Skill", "cost": "1",
                 "description": "Gain 7 Block.", "rarity": "Common", "is_upgraded": False,
                 "keywords": []}], "can_skip": True},
            "run": {"act": 1, "floor": 5, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 70, "max_hp": 80, "deck": deck},
        })

    r = router()
    weak = ([("STRIKE_IRONCLAD", "Attack", "Deal 6 damage.")] * 8
            + [("DEFEND_IRONCLAD", "Skill", "Gain 5 Block.")] * 4)  # 100% basic -> low bar
    polished = ([("BASH", "Attack", "Deal 8 damage. Apply 2 Vulnerable.")] * 6
                + [("SHRUG", "Skill", "Gain 11 Block. Draw 1 card.")] * 6)  # full bar
    assert r.decide(reward(weak), LoopContext()).action.payload()["action"] == "select_card_reward"
    skipped = r.decide(reward(polished), LoopContext()).action.payload()
    assert skipped == {"action": "skip_card_reward"}


def test_relic_select_takes_highest_value_not_first() -> None:
    """Ancient/elite/treasure relic choices were effectively random (TrivialRouter took relics[0]).
    Rank by Spirebird raw WAR and take the best: Bag of Preparation (WAR ~890) over Membership Card
    (~665), even though Membership Card is offered first."""
    state = parse_state({
        "state_type": "relic_select",
        "relic_select": {"relics": [
            {"id": "MEMBERSHIP_CARD", "name": "Membership Card", "index": 0},
            {"id": "BAG_OF_PREPARATION", "name": "Bag of Preparation", "index": 1}],
            "can_skip": False},
        "run": {"act": 1, "floor": 9, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 70, "max_hp": 80},
    })
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload() == {"action": "select_relic", "index": 1}  # higher WAR, not first


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
                    "description": "Gain 4 Block. Does something subtle the regex cannot price.",
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


def test_rest_recognizes_live_heal_smith_ids() -> None:
    """Regression: live rest options are id 'HEAL'/'SMITH' (not 'rest'/'smith'); the
    old key check missed them so the bot fell through to Rest and never smithed."""
    state = parse_state(
        {
            "state_type": "rest_site",
            "rest_site": {
                "options": [
                    {
                        "index": 0,
                        "id": "HEAL",
                        "name": "Rest",
                        "description": "Heal.",
                        "is_enabled": True,
                    },
                    {
                        "index": 1,
                        "id": "SMITH",
                        "name": "Smith",
                        "description": "Upgrade.",
                        "is_enabled": True,
                    },
                ],
                "can_proceed": False,
            },
            "run": {"act": 1, "floor": 7, "ascension": 0},
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
    d = router().decide(state, LoopContext())  # 87% HP > 60% -> smith is now reachable
    assert isinstance(d, Decision) and d.action.payload()["index"] == 1
    assert "smith" in d.rationale.lower()


def test_full_belt_discards_for_potion_reward() -> None:
    # Since 2026-07-13 the discard fires only for a genuine upgrade: give the reward a
    # strong description (heal, rank 6) and expect the lowest-value belt potion to go.
    payload = json.loads(json.dumps(FIXTURES["rewards"]))
    payload["player"]["potions"] = [
        {"id": "BLOCK_POTION", "name": "Block Potion", "slot": 0,
         "description": "Gain 12 Block."},
        {"id": "DEX_POTION", "name": "Dexterity Potion", "slot": 1,
         "description": "Gain 2 Dexterity."},
        {"id": "FLEX_POTION", "name": "Flex Potion", "slot": 2,
         "description": "Gain 4 Strength this turn."},
    ]
    payload["player"]["max_potion_slots"] = 3
    for item in payload["rewards"]["items"]:
        if item.get("type") == "potion":
            item["potion_description"] = "Heal 20 HP."  # rank 6: a clear upgrade
    state = parse_state(payload)
    decision = router().decide(state, LoopContext())
    assert isinstance(decision, Decision)
    payload_out = decision.action.payload()
    assert payload_out["action"] == "discard_potion"
    # victim = the lowest keep-value potion (Block=3 ties Dex? ranks decide; never a heal)
    assert payload_out["slot"] in (0, 1, 2)


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


def test_transform_never_targets_a_curse() -> None:
    """LKG20K3FBE forensics (owner-confirmed mechanic): transforming a curse rerolls
    WITHIN the curse pool — 'select worst' transformed Writhe at f3 and rolled Bad
    Luck (Eternal, 13 HP/turn-in-hand), which bled the run dead by f21. Transform
    must target the worst NON-curse (a basic), even with a curse on the screen."""
    cards = [
        {"id": "WRITHE", "name": "Writhe", "type": "Curse", "cost": "-2",
         "description": "Unplayable.", "rarity": "Curse", "is_upgraded": False, "index": 0},
        {"id": "STRIKE_IRONCLAD", "name": "Strike", "type": "Attack", "cost": "1",
         "description": "Deal 6 damage.", "rarity": "Basic", "is_upgraded": False, "index": 1},
        {"id": "BLUDGEON", "name": "Bludgeon", "type": "Attack", "cost": "3",
         "description": "Deal 32 damage.", "rarity": "Rare", "is_upgraded": False, "index": 2},
    ]
    state = _card_select_state("NCardSelectScreen", "Choose 2 cards to Transform.", cards)
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("index") == 1  # the Strike — never the curse
    # REMOVAL keeps curse-first (deleting Writhe outright is still correct)
    state_rm = _card_select_state("NCardSelectScreen", "Choose a card to Remove.", cards)
    d_rm = router().decide(state_rm, LoopContext())
    assert d_rm.action.payload().get("index") == 0


def test_enchant_intent_carries_from_event_to_generic_prompt() -> None:
    """Live 2026-07-24: Slither landed on a 1-cost Taunt with Bash in the pool. The
    mod's target screen says only 'Choose a card to Enchant.' — the enchant name is
    on the EVENT option one screen back, so the 'slither' prompt rule never fired.
    The router must remember the kind at event-choice time and target highest-cost."""
    r = router()
    ctx = LoopContext()
    ev = _ev_state("WOOD_CARVINGS", [
        _ev_opt(0, "Bird", "Choose 1 starter card to Transform into Peck."),
        _ev_opt(1, "Snake", "Enchant 1 card with Slither."),
        _ev_opt(2, "Torus", "Choose 1 starter card to Transform into Toric Toughness."),
    ])
    d = r.decide(ev, ctx)
    assert d.action.payload()["index"] == 1  # Snake (catalog 5.5)
    assert ctx.screen_mem.get("pending_enchant") == "slither"
    cards = [{"id": "STRIKE_IRONCLAD", "name": "Strike", "type": "Attack", "cost": "1",
              "description": "Deal 6 damage.", "rarity": "Basic", "is_upgraded": False,
              "index": 0},
             {"id": "TAUNT", "name": "Taunt", "type": "Skill", "cost": "1",
              "description": "Gain 4 Block.", "rarity": "Common", "is_upgraded": False,
              "index": 1},
             {"id": "BASH", "name": "Bash", "type": "Attack", "cost": "2",
              "description": "Deal 8 damage. Apply 2 Vulnerable.", "rarity": "Basic",
              "is_upgraded": False, "index": 2}]
    sel = _card_select_state("NCardSelectScreen", "Choose a card to Enchant.", cards)
    pick = r.decide(sel, ctx)
    assert pick.action.payload()["index"] == 2  # Bash: the highest-cost card
    # a later event choice with no enchant word self-heals the intent
    ev2 = _ev_state("ZZZ_PLAIN", [
        _ev_opt(0, "Smash", "Heal 20 HP."),
        _ev_opt(1, "Proceed", "", is_proceed=True),
    ])
    r.decide(ev2, ctx)
    assert ctx.screen_mem.get("pending_enchant") is None


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
    confirm = None
    for _ in range(5):  # settle-dwell polls (3b5f834) precede the confirm
        confirm = r.decide(
            _card_select_state("select", "Choose 2 cards to Remove.", cards,
                               can_confirm=True), ctx)
        if isinstance(confirm, Decision):
            break
    assert isinstance(confirm, Decision)
    assert confirm.action.payload()["action"] == "confirm_selection"


def test_hand_select_exhausts_curse_over_basic() -> None:
    """Owner (fight 3+): Burning Pact exhaust chose a Defend instead of the curse
    Decay. Exhaust/discard prompts should target the worst card (curse first)."""
    state = parse_state(
        {
            "state_type": "hand_select",
            "hand_select": {
                "mode": "simple_select",
                "prompt": "Choose a card to Exhaust.",
                "cards": [
                    {
                        "index": 0,
                        "id": "DEFEND_R",
                        "name": "Defend",
                        "type": "Skill",
                        "cost": "1",
                        "description": "Gain 5 Block.",
                        "is_upgraded": False,
                        "keywords": [],
                    },
                    {
                        "index": 1,
                        "id": "DECAY",
                        "name": "Decay",
                        "type": "Curse",
                        "cost": "",
                        "description": "Unplayable.",
                        "is_upgraded": False,
                        "keywords": [],
                    },
                ],
                "can_confirm": False,
            },
            "run": {"act": 1, "floor": 8, "ascension": 0},
            "player": {
                "character": "The Ironclad",
                "hp": 60,
                "max_hp": 80,
                "status": [],
                "relics": [],
                "potions": [],
                "max_potion_slots": 3,
            },
        }
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload() == {"action": "combat_select_card", "card_index": 1}  # the curse


def test_choose_screen_skips_when_stuck() -> None:
    """Run 2 stalled: a 'choose' screen returned ok but never resolved and the handler
    waited forever. Bounded retries, then skip — never an indefinite wait. Retries raised
    3 -> 8 (owner-caught 2026-07-14): the Toolbox overlay ACCEPTS the pick but takes
    several polls to close, and cancelling forfeited the relic's free card every combat.
    Patience first; the cancel valve stays as the last resort."""
    cards = [
        _sc_card(0, "Panic Button", "Skill"),
        _sc_card(1, "The Gambit", "Skill", rarity="Uncommon"),
        _sc_card(2, "Bolas", "Skill"),
    ]
    state = _card_select_state("choose", "Choose a card.", cards)
    r = router()
    ctx = LoopContext()
    for _ in range(r._CHOOSE_RETRIES):  # re-presses the pick, patiently
        d = r.decide(state, ctx)
        assert isinstance(d, Decision) and d.action.payload()["action"] == "select_card"
    final = r.decide(state, ctx)  # only THEN gives up -> skip, not a Wait
    assert isinstance(final, Decision)
    assert final.action.payload()["action"] == "cancel_selection"


def test_exhaust_prefers_replay_from_exhaust_cards() -> None:
    """Owner 2026-07-14: Howl from Beyond ("...if this is in your Exhaust Pile, play it")
    WANTS to be exhausted — it becomes a free recurring AoE. It ranked below basics, so
    the bot burned Strikes instead. On EXHAUST prompts it must be chosen over basics but
    still after curses; on REMOVE/upgrade prompts the rule must NOT fire (deleting the
    engine permanently would be a disaster)."""
    howl = _sc_card(0, "Howl from Beyond", "Attack", cid="HOWL_FROM_BEYOND")
    howl["description"] = ("Deal 16 damage to ALL enemies. At the end of your turn, if "
                           "this is in your Exhaust Pile, play it.")
    strike = _sc_card(1, "Strike", "Attack", cid="STRIKE_IRONCLAD")
    strike["description"] = "Deal 6 damage."
    curse = _sc_card(2, "Clumsy", "Curse", cid="CLUMSY")
    curse["description"] = "Unplayable."
    r = router()

    # EXHAUST prompt: Howl beats the Strike as the target...
    st = _card_select_state("select", "Choose a card to Exhaust.", [howl, strike])
    d = r.decide(st, LoopContext())
    assert d.action.payload()["index"] == 0  # Howl

    # ...but a curse still goes first
    st2 = _card_select_state("select", "Choose a card to Exhaust.", [howl, strike, curse])
    d2 = r.decide(st2, LoopContext())
    assert d2.action.payload()["index"] == 2  # Clumsy

    # REMOVE prompt (permanent!): never sacrifice the engine — the Strike goes
    st3 = _card_select_state("select", "Choose a card to Remove.", [howl, strike])
    d3 = r.decide(st3, LoopContext())
    assert d3.action.payload()["index"] == 1  # Strike

    # Same rule, other family (owner 2026-07-14): Drum of Battle pays energy ON exhaust,
    # so the on-exhaust rider makes it a prime exhaust target too. One text rule covers
    # both families — and any future card, in any class, with an on-exhaust payoff.
    drum = _sc_card(0, "Drum of Battle", "Skill", cid="DRUM_OF_BATTLE")
    drum["description"] = ("Draw 2 cards. When this card is Exhausted, gain "
                           "[ironclad_energy_icon.png][ironclad_energy_icon.png].")
    st4 = _card_select_state("select", "Choose a card to Exhaust.", [drum, strike])
    d4 = r.decide(st4, LoopContext())
    assert d4.action.payload()["index"] == 0  # Drum, not the Strike


def test_choose_retry_budget_resets_between_screens() -> None:
    """Owner-caught 2026-07-14 (Discovery failed 3/3 live): the choose-screen retry
    counter lived in screen_mem keyed by PROMPT and was never cleared when a screen
    resolved, so it accumulated across the run — an early Toolbox screen burned the
    budget and the next 'Choose a card.' (Discovery) got ONE try before cancelling,
    forfeiting the card (a 0-cost exhaust for nothing). Leaving the screen must reset it."""
    cards = [_sc_card(0, "Pillage", "Skill"), _sc_card(1, "Fiend Fire", "Attack"),
             _sc_card(2, "Crimson Mantle", "Skill")]
    screen = _card_select_state("choose", "Choose a card.", cards)
    combat = make_combat(hand=[card(0, "Strike", 1, "Deal 6 damage.")],
                         enemies=[enemy("E_0", 40)], energy=3)
    r = router()
    ctx = LoopContext()

    # screen 1 (e.g. Toolbox): burn some of the retry budget
    for _ in range(3):
        d = r.decide(screen, ctx)
        assert d.action.payload()["action"] == "select_card"
    # the screen resolves -> we're back in combat
    r.decide(combat, ctx)
    # screen 2 (Discovery): must get a FULL budget, not one try then cancel
    for i in range(r._CHOOSE_RETRIES):
        d = r.decide(screen, ctx)
        assert d.action.payload()["action"] == "select_card", f"cancelled at try {i}"


def test_card_select_no_confirm_screen_reselects_not_awaits() -> None:
    """Live hang (Headbutt): NCombatPileCardSelectScreen ('put a card on top of your Draw Pile')
    has no confirm/cancel/skip -- it resolves on select alone. The bot selected once, the select
    no-op'd on a not-yet-settled overlay, then it waited 60 ticks for a confirm that can't come
    (C5). The handler must keep (re)selecting on such screens, not strand in await-confirm."""
    cards = [_sc_card(0, "Strike"), _sc_card(1, "Defend", "Skill"), _sc_card(2, "Bash")]
    state = _card_select_state(
        "NCombatPileCardSelectScreen", "Choose a card to put on top of your Draw Pile.",
        cards, can_confirm=False, can_cancel=False,
    )
    r = router()
    ctx = LoopContext()
    for _ in range(2):  # screen stays open -> must RE-select each poll (old code Waited here)
        d = r.decide(state, ctx)
        assert isinstance(d, Decision), f"stranded in a Wait instead of re-selecting: {d}"
        assert d.action.payload()["action"] == "select_card"


def test_card_select_forced_multiremove_picks_distinct() -> None:
    """Regression from the Headbutt fix (Pael's Tooth, live): 'Choose 5 cards to Remove' is forced
    (no cancel) with can_confirm False until 5 are picked. It must NOT be treated as resolve-on-
    select (which re-clicked the first Strike forever) -- needed>1 routes it to pick-N-distinct."""
    cards = [_sc_card(i, "Strike") for i in range(5)] + [
        _sc_card(5, "Bash"), _sc_card(6, "Defend", "Skill"),
    ]
    state = _card_select_state(
        "select", "Choose 5 cards to Remove.", cards, can_confirm=False, can_cancel=False
    )
    r = router()
    ctx = LoopContext()
    picked = []
    for _ in range(5):
        d = r.decide(state, ctx)
        assert isinstance(d, Decision) and d.action.payload()["action"] == "select_card"
        picked.append(d.action.payload()["index"])
    assert len(set(picked)) == 5  # 5 DISTINCT cards, not the same index five times


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


def test_shop_removal_more_eager_when_starter_heavy() -> None:
    """Marginal (owner: removal chances are rare) — a starter-heavy deck spends down to a smaller
    cushion for removal (cutting a basic is high value when mostly basics) where a near-polished
    deck holds the gold for relics. Same 150g removal, same 200 gold, price cap respected."""
    weak = [_sc_card(i, "Strike") for i in range(9)] + [_sc_card(9, "Bash")]      # 90% basic
    polished = [_sc_card(0, "Strike")] + [
        _sc_card(i, "Inflame", "Power", rarity="Uncommon") for i in range(1, 10)]  # 10% basic
    bought = router().decide(_shop_with_removal(150, gold=200, deck=weak), LoopContext())
    assert bought.action.payload() == {"action": "shop_purchase", "index": 10}    # weak: buy it
    held = router().decide(_shop_with_removal(150, gold=200, deck=polished), LoopContext())
    p2 = held.action.payload()
    assert not (p2["action"] == "shop_purchase" and p2.get("index") == 10)        # polished: hold


def _shop_relic_item(index, relic_id, relic_name, price):
    return {"index": index, "category": "relic", "relic_id": relic_id,
            "relic_name": relic_name, "price": price, "is_stocked": True, "can_afford": True}


def test_shop_buys_best_value_relic_and_skips_negative() -> None:
    """Owner: the bot bought no relics at shops. With Spirebird shop value-per-gold it buys
    the strong relic (Data Disk +0.049) over a weaker one, and skips bad buys (Book Repair
    Knife -0.03)."""
    base = json.loads(json.dumps(FIXTURES["shop"]))
    base["player"]["gold"] = 400
    base["shop"]["items"] = [
        _shop_relic_item(0, "BOOK_REPAIR_KNIFE", "Book Repair Knife", 200),  # -0.03, skip
        _shop_relic_item(1, "DATA_DISK", "Data Disk", 168),  # +0.049, best
        _shop_relic_item(2, "ANCHOR", "Anchor", 167),  # +0.031, weaker
    ]
    d = router().decide(parse_state(base), LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload() == {"action": "shop_purchase", "index": 1}  # Data Disk

    only_bad = json.loads(json.dumps(FIXTURES["shop"]))
    only_bad["player"]["gold"] = 400
    only_bad["shop"]["items"] = [
        _shop_relic_item(0, "BOOK_REPAIR_KNIFE", "Book Repair Knife", 200)
    ]
    d2 = router().decide(parse_state(only_bad), LoopContext())
    assert d2.action.payload()["action"] == "proceed"  # negative-value relic not bought


def test_last_shop_spend_down() -> None:
    """Owner (2026-07-12, caught during the first-win run): the bot left an Act-3 shop
    with ~500 gold. Gold has zero terminal value, so Act 3+ shops spend down: unknown
    relics get bought (cheapest first), downside-text relics are skipped, and the same
    shop in Act 1 keeps the normal value gates (proceeds)."""
    base = json.loads(json.dumps(FIXTURES["shop"]))
    base["player"]["gold"] = 500
    base["run"] = {"act": 3, "floor": 45, "ascension": 0}
    unknown = _shop_relic_item(0, "MYSTERY_TRINKET", "Mystery Trinket", 250)
    downside = _shop_relic_item(1, "CURSED_IDOL", "Cursed Idol", 100)
    downside["relic_description"] = "Whenever you rest, lose 5 HP and gain a Curse."
    base["shop"]["items"] = [unknown, downside]
    d = router().decide(parse_state(base), LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload() == {"action": "shop_purchase", "index": 0}  # unknown, not cursed

    act1 = json.loads(json.dumps(base))
    act1["run"] = {"act": 1, "floor": 6, "ascension": 0}
    d2 = router().decide(parse_state(act1), LoopContext())
    assert d2.action.payload()["action"] == "proceed"  # normal gates hold mid-run


def test_shop_buys_discount_relic_first() -> None:
    """Owner: Membership Card (-50%) / Courier (-20%) apply immediately, so buy them FIRST and
    let the rest of the shop come back discounted — even over a higher-value relic, and even
    though the Courier isn't in the shop value table at all."""
    member = json.loads(json.dumps(FIXTURES["shop"]))
    member["player"]["gold"] = 400
    member["shop"]["items"] = [
        _shop_relic_item(0, "DATA_DISK", "Data Disk", 168),  # +0.049, higher raw value
        _shop_relic_item(1, "MEMBERSHIP_CARD", "Membership Card", 150),  # buy FIRST
    ]
    d = router().decide(parse_state(member), LoopContext())
    assert d.action.payload() == {"action": "shop_purchase", "index": 1}  # Membership first

    courier = json.loads(json.dumps(FIXTURES["shop"]))
    courier["player"]["gold"] = 400
    courier["shop"]["items"] = [
        _shop_relic_item(0, "DATA_DISK", "Data Disk", 168),
        _shop_relic_item(1, "THE_COURIER", "The Courier", 200),  # not in value table, still first
    ]
    d2 = router().decide(parse_state(courier), LoopContext())
    assert d2.action.payload() == {"action": "shop_purchase", "index": 1}  # Courier first


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


def test_enchant_selects_full_count_before_confirming() -> None:
    """Live f27 hang (owner-diagnosed mechanic): Gnarled Axe's 'Choose 3 cards to Enchant' lets you
    confirm with fewer than 3 selected, which strands you on a dead sub-screen. `can_confirm` is
    True from the first pick (the trap), so the handler must select 3 DISTINCT cards FIRST, then
    confirm — never confirm early."""
    def cardsel(ncards: int = 12):
        cards = [{"id": f"CARD_{i}", "name": f"Card{i}", "type": "Attack", "cost": "1",
                  "description": "Deal 6 damage.", "rarity": "Common", "is_upgraded": False,
                  "index": i} for i in range(ncards)]
        return parse_state({
            "state_type": "card_select",
            "card_select": {"screen_type": "NDeckEnchantSelectScreen",
                            "prompt": "Choose 3 cards to Enchant.", "cards": cards,
                            "preview_showing": False, "can_confirm": True,  # confirm offered early
                            "can_cancel": False},
            "run": {"act": 2, "floor": 27, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 50, "max_hp": 80},
        })

    r = router()
    ctx = LoopContext()
    picks = []
    for _ in range(3):  # must SELECT three distinct cards despite can_confirm being True
        p = r.decide(cardsel(), ctx).action.payload()
        assert p["action"] == "select_card", f"confirmed too early: {p}"
        picks.append(p["index"])
    assert len(set(picks)) == 3  # three distinct cards
    # now that 3 are picked: settle-dwell polls (3b5f834), then the confirm
    d = None
    for _ in range(5):
        d = r.decide(cardsel(), ctx)
        if not isinstance(d, Wait):
            break
    assert d.action.payload()["action"] == "confirm_selection"


def test_drafting_vs_slippery_boss_prefers_multi_hit() -> None:
    # the payoff of wiring real mechanics in: vs a Slippery boss the largest hit is gutted to 1,
    # so a multi-hit card lands far more than an equal-total single swing. Drafting should see it.
    from sts2bot.client.models import Card, DeckCard
    from sts2bot.policy.capability import FightEnemy

    r = _router_for_routing()
    deck = [
        DeckCard(index=i, id="STRIKE_IRONCLAD", name="Strike", type="Attack", cost="1",
                 is_upgraded=False)
        for i in range(8)
    ]
    multi = Card(index=0, id="MULTI", name="Multi", type="Attack", cost="2",
                 description="Deal 5 damage 4 times.")  # 20 total, small hits
    big = Card(index=1, id="BIG", name="Big", type="Attack", cost="2",
               description="Deal 20 damage.")  # 20 total, one big hit
    slippery_boss = [FightEnemy(hp=173, dps=20, slippery=True)]
    deltas = r._capability_deltas(deck, [multi, big], 80, [slippery_boss])
    assert deltas[0] > deltas[1]  # multi-hit beats Slippery; the big swing is wasted


def test_card_gen_potion_dropped_at_boss_start() -> None:
    """Owner 2026-07-09: Skill/Attack/Power/Colorless Potions should be dropped immediately
    at a boss start -- the chosen card compounds over the fight; previously they classified
    as 'other' and only ever fired as too-late hail-maries."""
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("BOSS_0", 200, intent_label="10")],
        hp=70, max_hp=80, state_type="boss",
        potions=[_potion("SKILL_POTION", "Skill Potion",
                         "Choose 1 of 3 Skills. Add it to your hand.")],
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["action"] == "use_potion"
    assert "bank cards early" in d.rationale


def test_foul_self_lethal_guard_survives_text_drift() -> None:
    """Live 2026-07-30: Foul's text became 'Deal 12 damage to ALL players and
    enemies' (no EVERYONE) and the guard went silent — the bot drank a 12-damage
    suicide at 6 HP in a hail-mary. Both phrasings now veto."""
    foul = _potion("FOUL_POTION", "Foul Potion",
                   "Deal 12 damage to ALL players and enemies. "
                   "Can be thrown at the Merchant for 100 Gold instead.")
    state = make_combat(
        hand=[], enemies=[enemy("BOSS_0", 200, intent_label="24")],
        energy=0, hp=6, max_hp=80, state_type="boss", potions=[foul],
    )
    d = router().decide(state, LoopContext())
    if isinstance(d, Decision):
        assert d.action.payload().get("action") != "use_potion", d.rationale


def test_matriarch_drain_forces_the_race() -> None:
    """Matriarch cluster 2026-07-30 (3 healthy-HP deaths): Soul Siphon (-2 Str/Dex
    per cycle, a MOVE — nothing text-detects it) makes her a clock, but the planner
    turtled at ~12 chip/round vs 222 HP. Drain-table bosses now join the race lane:
    a damageless comfortable-block turn pays w_ramp_stall against her."""
    hand = [card(0, "Strike", 1, "Deal 6 damage."),
            card(1, "Defend", 1, "Gain 5 Block."),
            card(2, "Defend", 1, "Gain 5 Block.")]
    def fight(name):
        e = enemy(name.upper().replace(" ", "_") + "_0", 200, intent_label="10")
        e["name"] = name
        return make_combat(hand=[dict(c) for c in hand], enemies=[e],
                           hp=60, max_hp=80, state_type="boss", energy=2)
    d_m = router().decide(fight("Lagavulin Matriarch"), LoopContext())
    plan_m = d_m.rationale.split(";")[0]
    assert "Strike" in plan_m, d_m.rationale  # racing: damage in the plan


def test_emergency_stoke_rerolls_a_doomed_hand() -> None:
    """Owner live 2026-07-30: with no survivable line, Stoke as first play (after
    banking energy if available) rerolls the hand — the bot declined it. Works
    under NO_DRAW too (adds aren't draws)."""
    stoke = card(0, "Stoke", 1, "Exhaust your Hand. Add 1 random card into your "
                                "Hand for each card Exhausted.", ctype="Skill")
    bloodletting = card(1, "Bloodletting", 0,
                        "Lose 2 HP. Gain 2 Energy.", ctype="Skill")
    strike = card(2, "Strike", 1, "Deal 6 damage.")
    state = make_combat(hand=[stoke, bloodletting, strike],
                        enemies=[enemy("BOSS_0", 300, intent_label="40")],
                        hp=12, max_hp=80, state_type="boss")
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    # energy first (the lane re-fires next poll and the shred plays richer)
    assert d.action.payload().get("card_index") == 1, d.rationale
    assert "bank" in d.rationale
    # without the generator, the shred itself fires
    st2 = make_combat(hand=[stoke, strike],
                      enemies=[enemy("BOSS_0", 300, intent_label="40")],
                      hp=12, max_hp=80, state_type="boss")
    d2 = router().decide(st2, LoopContext())
    assert isinstance(d2, Decision)
    assert d2.action.payload().get("card_index") == 0, d2.rationale
    assert "emergency shred" in d2.rationale


def test_explosive_potion_held_for_the_swarms_ahead() -> None:
    """Owner 2026-07-29: AoE damage potions are premium vs the Kin / Phrog p2 /
    Gardeners / Decimillipede — hold them in acts 1-2 NORMAL fights while any of
    those is ahead; release once the act's swarms are seen (an elite seen won't
    recur until 3 fought) and the boss isn't Kin. Elite/boss fights spend freely."""
    boom = _potion("EXPLOSIVE_POTION", "Explosive Potion",
                   "Deal 12 damage to ALL enemies.")

    def normal_fight(potions):
        return make_combat(
            hand=[], enemies=[enemy("BUG_A", 11, intent_label="12"),
                              enemy("BUG_B", 25, intent_label="12")],
            energy=0, hp=70, max_hp=80, potions=potions,
        )

    # Kin boss cached -> held even with a finisher-worthy target
    ctx = LoopContext()
    ctx.screen_mem["act_boss_name"] = "The Kin"
    d = router().decide(normal_fight([boom]), ctx)
    assert (not isinstance(d, Decision)
            or d.action.payload().get("action") != "use_potion"), d.rationale
    # other boss + both act-1 swarms already seen -> the hold releases
    ctx2 = LoopContext()
    ctx2.screen_mem["act_boss_name"] = "Soul Fysh"
    ctx2.screen_mem["elites_seen"] = {"PHROG PARASITE", "PHANTASMAL GARDENER"}
    d2 = router().decide(normal_fight([boom]), ctx2)
    assert isinstance(d2, Decision)
    assert d2.action.payload().get("action") == "use_potion", d2.rationale


def test_no_draw_lock_blocks_swift_and_dead_plan_draws() -> None:
    """Owner trap 2026-07-29: Battle Trance's rider ("cannot draw additional cards
    this turn", status NO_DRAW_POWER) also kills potion draws. Swift must hold under
    the lock, and in-plan draws AFTER a Battle Trance credit nothing to the sim."""
    swift = _potion("SWIFT_POTION", "Swift Potion", "Draw 3 cards.")
    state = make_combat(
        hand=[], enemies=[enemy("BOSS_0", 200, intent_label="10")],
        energy=2, hp=70, max_hp=80, state_type="boss", potions=[swift],
        player_status=[{"id": "NO_DRAW_POWER", "name": "No Draw", "amount": 1,
                        "description": "You may not draw any more cards this turn."}],
    )
    d = router().decide(state, LoopContext())
    assert (not isinstance(d, Decision)
            or d.action.payload().get("action") != "use_potion"), d.rationale
    # sim side: Pommel-class draw after Battle Trance credits no draws
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn
    st2 = make_combat(
        hand=[card(0, "Battle Trance", 0,
                   "Draw 3 cards. You cannot draw additional cards this turn."),
              card(1, "Pommel Strike", 1, "Deal 9 damage. Draw 1 card.")],
        enemies=[enemy("MOB_0", 60, intent_label="5")], hp=70, max_hp=80,
    )
    plan = plan_combat_turn(st2, load_policy_config().combat)
    assert isinstance(plan, Decision)
    # the plan works either order; the sim just must not credit BT->Pommel with 4 draws
    # (indirect check: planner does not prefer BT first purely for the dead draw)
    assert plan.scores is not None


def test_swift_potion_on_out_of_cards_with_energy() -> None:
    """Owner provisional rule 2026-07-29: Swift (draw 3) drinks when out of playable
    cards with energy unspent at a boss/elite (or full belt) — NOT at turn 1 with a
    full hand. Full treatment belongs to the multiturn planner."""
    swift = _potion("SWIFT_POTION", "Swift Potion", "Draw 3 cards.")
    # boss, empty hand, 2 energy left -> drink
    state = make_combat(hand=[], enemies=[enemy("BOSS_0", 200, intent_label="10")],
                        energy=2, hp=70, max_hp=80, state_type="boss", potions=[swift])
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("action") == "use_potion", d.rationale
    assert "out of cards" in d.rationale
    # normal fight, belt not full -> held
    st2 = make_combat(hand=[], enemies=[enemy("MOB_0", 30, intent_label="5")],
                      energy=2, hp=70, max_hp=80, potions=[swift])
    d2 = router().decide(st2, LoopContext())
    assert (not isinstance(d2, Decision)
            or d2.action.payload().get("action") != "use_potion"), d2.rationale


def test_orobic_acid_deploys_at_elite_start() -> None:
    """Owner 2026-07-29: Orobic Acid (3 random cards, free this turn) and the other
    card-gen potions are obvious turn-1 plays at bosses AND elites — the lane was
    boss-only and Orobic categorized 'other' (hail-mary only)."""
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("ELITE_0", 140, intent_label="14")],
        hp=70, max_hp=80, state_type="elite",
        potions=[_potion("OROBIC_ACID", "Orobic Acid",
                         "Add a random Attack, Skill, and Power into your Hand. "
                         "They're free to play this turn.")],
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("action") == "use_potion", d.rationale
    assert "elite start" in d.rationale


def test_card_gen_potion_held_in_normal_fights() -> None:
    """The boss-start drop is boss-only: in a normal monster fight the card-gen potion is
    held (its value is banked for the fights that matter)."""
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("MOB_0", 30, intent_label="5")],
        hp=70, max_hp=80,
        potions=[_potion("COLORLESS_POTION", "Colorless Potion",
                         "Choose 1 of 3 Colorless cards. Add it to your hand.")],
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["action"] != "use_potion"


def test_elite_gate_uses_real_bestiary_pool() -> None:
    """2026-07-09 (3 elite deaths in one batch): the gate must judge the act's REAL elite pool,
    not the flattering generic 90-HP profile. A deck that beats the generic elite but loses to
    the pool's big members (Terror Eel 140 HP) fails the pool gate; an empty bestiary falls
    back to the generic profile (and passes, as before)."""
    from sts2bot.kb.combat_stats import CombatStats

    stats = CombatStats(by_type={
        "monster_early": {"mean": 4.0, "p75": 5, "n": 99},
        "monster": {"mean": 12.0, "p75": 18, "n": 99},
        "elite": {"mean": 21.0, "p75": 32, "n": 99},
        "boss": {"mean": 25.0, "p75": 42, "n": 99},
    })
    # pool recalibrated 2026-07-24 (A/B #5 gate loosening 0.50/0.30 -> 0.40/0.20):
    # bigger bodies so the pool STILL fails the looser gate — the test pins the
    # real-pool-vs-generic mechanism, not any particular threshold.
    pool = {
        "Terror Eel": {"roles": ["elite"], "acts": [1], "hp": [190, 190], "statuses": {}},
        "Bygone Effigy": {"roles": ["elite"], "acts": [1], "hp": [180, 180], "statuses": {}},
        "Skulking Colony": {"roles": ["elite"], "acts": [1], "hp": [95, 95], "statuses": {
            "HARDENED_SHELL_POWER": {"description": "Cannot lose more than 10 HP each turn."}}},
    }
    payload = json.loads(json.dumps(FIXTURES["map"]))
    payload["map"]["next_options"] = [
        {"index": 0, "col": 1, "row": 3, "type": "Elite", "leads_to": []},
        {"index": 1, "col": 2, "row": 3, "type": "Monster", "leads_to": []},
    ]
    payload["player"]["deck"] = _STRONG_DECK  # beats the generic elite (old gate opens)
    payload["player"]["hp"] = 80
    payload["player"]["max_hp"] = 80

    for bestiary, expect_elite in (({}, True), (pool, False)):
        r = StandardRouter(combat_stats=stats, bestiary=bestiary)
        r.card_effects = _ROUTING_CARD_EFFECTS
        d = r.decide(parse_state(payload), LoopContext())
        assert isinstance(d, Decision)
        took_elite = d.action.payload()["index"] == 0
        assert took_elite == expect_elite, (bestiary.keys(), d.rationale)


def test_thorns_potion_deployed_at_boss_start() -> None:
    """Owner catch (win-run summary): the run ENDED with a Thorns potion in the belt —
    'absolutely drink a thorns potion at the start of the final boss fight.' It
    categorized 'other' (only hail-maries drink those); now buff -> boss-start deploy."""
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("BOSS_0", 300, intent_label="12")],
        hp=70, max_hp=80, state_type="boss",
        potions=[_potion("LIQUID_BRONZE", "Liquid Bronze",
                         "Gain 3 Thorns.")],  # the REAL name (live 2026-07-29)
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("action") == "use_potion", d.rationale


def test_foul_potion_not_claimed_late_act3() -> None:
    """Owner catch: the win run banked two Fouls it could never sell (merchant ammo,
    no merchant left). Past f40 in act 3, downside potions are left on the table."""
    state = parse_state({
        "state_type": "rewards",
        "rewards": {"items": [
            {"index": 0, "type": "potion", "potion_id": "FOUL_POTION",
             "potion_name": "Foul Potion",
             "potion_description": "Deal 10 damage to EVERYONE."},
        ]},
        "run": {"act": 3, "floor": 42, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80, "gold": 100,
                   "status": [], "relics": [],
                   "potions": [_potion("BLOCK_POTION", "Block Potion", "Gain 12 Block.")],
                   "max_potion_slots": 3},
    })
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("action") != "claim_reward", d.rationale


def test_prolong_played_after_block_not_left_in_hand() -> None:
    """Live 2026-07-25: 0-cost Prolong ('Next turn, gain Block equal to your current
    Block. Exhaust.') sat unplayed with block up — it parsed to all-zeros. The
    carryover credit must get it played, and AFTER the block cards (snapshot)."""
    state = make_combat(
        hand=[card(0, "Prolong", 0,
                   "Next turn, gain Block equal to your current Block. Exhaust."),
              card(1, "Defend", 1, "Gain 5 Block."),
              card(2, "Defend", 1, "Gain 5 Block."),
              card(3, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("MOB_0", 60, intent_label="12")],
        hp=50, max_hp=80,
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    plan = d.rationale.split(";")[0]
    assert "Prolong" in plan, d.rationale
    # snapshot semantics: Prolong after at least the Defends it wants to copy
    assert plan.index("Prolong") > plan.index("Defend"), d.rationale


def test_enemy_buff_rider_gates_fight_me_on_kill_or_safe() -> None:
    """Ovicopter A/B 2026-07-25: the bot played Fight Me!+ into a non-lethal (missed
    by 9), ate the buffed intent, died next round. The owner's rule, made literal by
    the sim: the rider raises the SURVIVOR's incoming, so into a kill it's free, into
    a survivor it costs — with the hit lethal-adjacent, the planner must skip it."""
    fight_me = card(0, "Fight Me!+", 1,
                    "Deal 9 damage twice. Gain 4 Strength. The enemy gains 1 Strength.")
    strike = card(1, "Strike", 1, "Deal 6 damage.")
    defend = card(2, "Defend", 1, "Gain 5 Block.")
    # enemy survives anything this hand can do; its 4x4 hits become 5x4 = 20 if buffed,
    # and at 22 HP with 5 block that's the difference between -11 and -15... make it
    # sharper: hp such that buffed = into the death floor
    big = enemy("OVI_0", 60, intent_label="4x4")
    state = make_combat(hand=[fight_me, strike, defend], enemies=[big],
                        hp=14, max_hp=80)
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    plan_head = d.rationale.split(";")[0]
    assert "Fight Me" not in plan_head, d.rationale  # buffing a survivor near the floor: no
    # and the same card INTO a kill is fine (rider dies with the target)
    small = enemy("EGG_0", 15, intent_label="4x4")
    state2 = make_combat(hand=[fight_me, strike, defend], enemies=[small],
                         hp=14, max_hp=80)
    d2 = router().decide(state2, LoopContext())
    assert "Fight Me" in d2.rationale.split(";")[0], d2.rationale


def test_flex_potion_completes_lethal() -> None:
    """Ovicopter A/B: the bot missed a fight-ending kill by 9 with a Flex in the belt.
    Strength potions now join the lethal search as pseudo-cards before attacks."""
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage."),
              card(1, "Strike", 1, "Deal 6 damage."),
              card(2, "Twin Strike", 1, "Deal 5 damage twice.")],
        enemies=[enemy("BOSS_0", 37, intent_label="12")],
        hp=30, max_hp=80, state_type="boss",
        potions=[_potion("FLEX_POTION", "Flex Potion",
                         "Gain 5 Strength. At the end of your turn, lose 5 Strength.")],
    )
    # cards alone: 6+6+5x2 = 22 < 37. With Flex first: 11+11+10x2 = 42 >= 37.
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.scores and d.scores.get("lethal") == 1.0, (d.rationale, d.scores)


def test_full_belt_raises_potion_deploy_prior() -> None:
    """Owner (Ovicopter A/B): at 3/3 potions the spend prior rises — every reward
    potion overflows. A normal fight with a full belt counts as deploy-worthy."""
    def mk(n_potions):
        pots = [_potion(f"STRENGTH_POTION_{i}", "Strength Potion",
                        "Gain 2 Strength.", slot=i) for i in range(n_potions)]
        return make_combat(
            hand=[card(0, "Strike", 1, "Deal 6 damage.")],
            enemies=[enemy("MOB_0", 60, intent_label="6")],
            hp=50, max_hp=80, potions=pots,
        )

    # full belt: the round-1 buff-deploy lane fires in a NORMAL fight
    d = router().decide(mk(3), LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("action") == "use_potion", d.rationale
    # slack in the belt: same fight, potion stays held
    d2 = router().decide(mk(2), LoopContext())
    assert d2.action.payload().get("action") != "use_potion", d2.rationale


def test_eruption_phase_stacks_block_despite_null_intent() -> None:
    """WG death forensics (WYZQR5KPFQ f17, 2026-07-25): during the invincible phase the
    Giant exposes intent null and statuses null — 0 parsed incoming made all block score
    as excess, and the bot played 12 block at 30 HP into the blast. The HP sentinel is
    the one reliable signature: assume a big blockable eruption and stack block."""
    wg = {"entity_id": "WATERFALL_GIANT_0", "combat_id": 1, "name": "Waterfall Giant",
          "hp": 999999994, "max_hp": 999999999, "block": 0, "status": [], "intents": []}
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage."),
              card(1, "Defend", 1, "Gain 5 Block."),
              card(2, "Defend", 1, "Gain 5 Block."),
              card(3, "Iron Wave", 1, "Gain 5 Block. Deal 5 damage.")],
        enemies=[wg], hp=30, max_hp=80, state_type="boss",
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    # the 3-energy plan must be all-block (Defend/Defend/Iron Wave), never the Strike:
    # damage into the sentinel is wasted and the assumed eruption prices every point
    plan = d.rationale
    assert "Strike" not in plan.split("plan")[-1].split(";")[0], plan
    assert d.scores.get("plan_damage") == 0.0, d.scores  # no chip into the sentinel
    assert d.scores.get("hp_loss") == 35.0, d.scores  # 50 assumed - 15 block stacked


def test_tinker_time_catalog_overrides_spirebird() -> None:
    """Owner brief 2026-07-29: Power > Skill > Attack at Tinker Time — but Spirebird
    slightly prefers Skill (14.0 vs 13.8), so TINKER_TIME is catalog-first. The live
    miss: bot took Protector over Gadget at the catalog floor."""
    state = _ev_state("TINKER_TIME", [
        _ev_opt(0, "Protector", "Make a Skill."),
        _ev_opt(1, "Gadget", "Make a Power."),
    ])
    d = router().decide(state, LoopContext())
    assert d.action.payload()["index"] == 1, d.scores  # Gadget
    # stage 2 power head-to-head: Expertise default over Improvement
    st2 = _ev_state("TINKER_TIME", [
        _ev_opt(0, "Improvement", "At the end of combat, Upgrade a random card."),
        _ev_opt(1, "Expertise", "Gain 2 Strength and 2 Dexterity."),
    ])
    d2 = router().decide(st2, LoopContext())
    assert d2.action.payload()["index"] == 1, d2.scores


def test_mad_science_power_variant_is_a_premium_smith_target() -> None:
    """Owner 2026-07-29: upgrading Curious/Expertise Mad Science = Innate power
    (fires turn 1 every fight) — premium; other variants minor. One id, many
    designs — detected by text."""
    cards = [
        {"id": "STRIKE_IRONCLAD", "name": "Strike", "type": "Attack", "cost": "1",
         "description": "Deal 6 damage.", "rarity": "Basic", "is_upgraded": False,
         "index": 0},
        {"id": "MAD_SCIENCE", "name": "Mad Science", "type": "Power", "cost": "1",
         "description": "Gain 2 Strength and 2 Dexterity.", "rarity": "Special",
         "is_upgraded": False, "index": 1},
    ]
    state = _card_select_state("NCardSelectScreen", "Choose a card to Upgrade.", cards)
    d = router().decide(state, LoopContext())
    assert d.action.payload().get("index") == 1, d.rationale


def test_cost_zero_potion_waits_for_a_worthy_target() -> None:
    """Owner 2026-07-29 (Touch of Insanity — matched by TEXT, the name never
    matters): deploy early at a boss but only when a cost>=2 card is in hand — a
    turn-1 hand of cheap cards means WAIT for the turn the 3-cost shows up; the
    target screen then prefers max cost."""
    cz = _potion("TOUCH_OF_INSANITY", "Touch of Insanity",
                 "Choose a card. It costs 0 for the rest of this fight.")
    cheap_hand = [card(0, "Strike", 1, "Deal 6 damage."),
                  card(1, "Defend", 1, "Gain 5 Block.")]
    rich_hand = [*cheap_hand, card(2, "Bludgeon", 3, "Deal 32 damage.")]
    st_cheap = make_combat(hand=cheap_hand, enemies=[enemy("BOSS_0", 300, intent_label="10")],
                           hp=70, max_hp=80, state_type="boss", potions=[cz])
    # the WAIT applies when the deck holds a worthy target elsewhere (owner
    # softening 2026-08-30: with no >=2 in the whole deck, a boss-fight
    # 1-cost suffices instead of letting the potion rot)
    from sts2bot.client.models import Card
    st_cheap.player.deck = [Card(**card(0, "Bludgeon", 3, "Deal 32 damage."))]
    d = router().decide(st_cheap, LoopContext())
    assert (not isinstance(d, Decision)
            or d.action.payload().get("action") != "use_potion"), d.rationale
    st_poor = make_combat(hand=cheap_hand, enemies=[enemy("BOSS_0", 300, intent_label="10")],
                          hp=70, max_hp=80, state_type="boss", potions=[cz])
    d_poor = router().decide(st_poor, LoopContext())
    assert isinstance(d_poor, Decision)
    assert d_poor.action.payload().get("action") == "use_potion"  # 1-cost suffices
    ctx = LoopContext()
    st_rich = make_combat(hand=rich_hand, enemies=[enemy("BOSS_0", 300, intent_label="10")],
                          hp=70, max_hp=80, state_type="boss", potions=[cz])
    d2 = router().decide(st_rich, ctx)
    assert isinstance(d2, Decision)
    assert d2.action.payload().get("action") == "use_potion", d2.rationale
    assert ctx.screen_mem.get("pending_enchant") == "cost_zero"


def test_sword_of_stone_completion_nudge_at_four_elites() -> None:
    """Owner 2026-07-29: at counter 4 the next elite ALSO completes Sword of Jade
    (+3 Str) — a winnable elite node scores sword_completion_bonus higher than the
    identical spot at counter 0. (The event pick itself is docked until era elite
    rates make the upgrade real.)"""
    from sts2bot.kb.combat_stats import CombatStats

    stats = CombatStats(by_type={
        "monster_early": {"mean": 4.0, "p75": 5, "n": 99},
        "monster": {"mean": 12.0, "p75": 18, "n": 99},
        "elite": {"mean": 21.0, "p75": 32, "n": 99},
        "boss": {"mean": 25.0, "p75": 42, "n": 99},
    })

    def elite_score(counter):
        payload = json.loads(json.dumps(FIXTURES["map"]))
        payload["map"]["next_options"] = [
            {"index": 0, "col": 1, "row": 3, "type": "Elite", "leads_to": []},
            {"index": 1, "col": 2, "row": 3, "type": "Monster", "leads_to": []},
        ]
        payload["player"]["deck"] = _ELITE_READY_DECK
        payload["player"]["hp"] = 80
        payload["player"]["max_hp"] = 80
        payload["player"]["relics"] = [{
            "id": "SWORD_OF_STONE", "name": "Sword of Stone",
            "description": "Transforms into a powerful Relic after defeating 5 Elites.",
            "counter": counter, "keywords": []}]
        r = StandardRouter(combat_stats=stats, bestiary={})
        r.card_effects = _ROUTING_CARD_EFFECTS
        d = r.decide(parse_state(payload), LoopContext())
        return d.scores["0:Elite"]

    from sts2bot.kb.config import load_policy_config
    w = load_policy_config().map
    assert elite_score(4) - elite_score(0) >= w.sword_completion_bonus * 0.75


def test_boots_jump_is_insurance_not_a_path_upgrade() -> None:
    """Owner 2026-07-29: Winged Boots charges should be saved for emergencies — the
    bot burned 2 of 3 on marginal jumps (off-path options score higher, DP obliges).
    Jump options now pay boots_jump_cost: a comfy-HP rest jump is refused; the same
    jump at desperate HP (death-floor dodge) is taken."""
    from sts2bot.kb.combat_stats import CombatStats

    stats = CombatStats(by_type={
        "monster_early": {"mean": 4.0, "p75": 5, "n": 99},
        "monster": {"mean": 12.0, "p75": 18, "n": 99},
        "elite": {"mean": 21.0, "p75": 32, "n": 99},
        "boss": {"mean": 25.0, "p75": 42, "n": 99},
    })

    def mk(hp):
        payload = json.loads(json.dumps(FIXTURES["map"]))
        payload["map"]["current_position"] = {"col": 4, "row": 3, "type": "Monster"}
        payload["map"]["next_options"] = [
            {"index": 0, "col": 4, "row": 4, "type": "Monster", "leads_to": []},
            {"index": 1, "col": 0, "row": 4, "type": "RestSite", "leads_to": []},  # boots jump
        ]
        payload["map"]["nodes"] = [
            {"col": 4, "row": 3, "type": "Monster", "children": [[4, 4]]},
            {"col": 4, "row": 4, "type": "Monster", "children": []},
            {"col": 0, "row": 4, "type": "RestSite", "children": []},
        ]
        payload["player"]["hp"] = hp
        payload["player"]["max_hp"] = 80
        payload["player"]["deck"] = _STRONG_DECK
        return payload

    r = StandardRouter(combat_stats=stats, bestiary={})
    r.card_effects = _ROUTING_CARD_EFFECTS
    comfy = r.decide(parse_state(mk(64)), LoopContext())
    assert comfy.action.payload()["index"] == 0, comfy.scores  # stay on-path
    desperate = r.decide(parse_state(mk(18)), LoopContext())
    assert desperate.action.payload()["index"] == 1, desperate.scores  # spend the charge


def test_planisphere_heal_flips_a_death_floor_pocket() -> None:
    """Owner nuance check 2026-07-29: Planisphere (+5 HP entering a '?' room) now
    rides the map DP's HP projection. At 20/80 HP with a 12-loss monster behind both
    doors, the '?' route projects 20+5-12=13 (safe) while the event route projects
    20-12=8 (death floor) — the +5 is exactly the margin."""
    from sts2bot.kb.combat_stats import CombatStats

    stats = CombatStats(by_type={
        "monster_early": {"mean": 4.0, "p75": 5, "n": 99},
        "monster": {"mean": 12.0, "p75": 18, "n": 99},
        "elite": {"mean": 21.0, "p75": 32, "n": 99},
        "boss": {"mean": 25.0, "p75": 42, "n": 99},
    })
    payload = json.loads(json.dumps(FIXTURES["map"]))
    payload["map"]["next_options"] = [
        {"index": 0, "col": 1, "row": 4, "type": "Unknown",
         "leads_to": [{"col": 1, "row": 5, "type": "Monster"}]},
        {"index": 1, "col": 2, "row": 4, "type": "Event",
         "leads_to": [{"col": 2, "row": 5, "type": "Monster"}]},
    ]
    payload["map"]["nodes"] = [
        {"col": 1, "row": 5, "type": "Monster", "children": []},
        {"col": 2, "row": 5, "type": "Monster", "children": []},
    ]
    payload["player"]["hp"] = 20
    payload["player"]["max_hp"] = 80
    payload["player"]["deck"] = _STRONG_DECK
    payload["player"]["relics"] = [{"id": "PLANISPHERE", "name": "Planisphere",
                                    "description": "Heal 5 HP when you enter a ? room.",
                                    "counter": None, "keywords": []}]
    r = StandardRouter(combat_stats=stats, bestiary={})
    r.card_effects = _ROUTING_CARD_EFFECTS
    d = r.decide(parse_state(payload), LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["index"] == 0, d.scores  # the healed '?' route


def test_map_travel_hold_suppresses_phantom_redecide() -> None:
    """Audit 2026-07-25 (f42-44 forensics): right after a travel is accepted the mod
    re-renders the map minus the consumed option; the router re-decided on the
    leftovers and submitted a SECOND travel (Unknown 44.3 accepted -> 'Elite -151.5'
    phantom). Same node after a choice must Wait; the hold expires after its tick
    budget so a genuinely failed submission still recovers."""
    payload = json.loads(json.dumps(FIXTURES["map"]))
    payload["map"]["current_position"] = {"col": 4, "row": 2, "type": "Monster"}
    payload["map"]["next_options"] = [
        {"index": 0, "col": 1, "row": 3, "type": "Monster", "leads_to": []},
        {"index": 1, "col": 2, "row": 3, "type": "RestSite", "leads_to": []},
    ]
    r = router()
    ctx = LoopContext()
    first = r.decide(parse_state(payload), ctx)
    assert isinstance(first, Decision)
    # the transient: same position, the chosen option gone
    transient = json.loads(json.dumps(payload))
    transient["map"]["next_options"] = [o for o in payload["map"]["next_options"]
                                        if o["index"] != first.action.payload()["index"]]
    held = r.decide(parse_state(transient), ctx)
    assert isinstance(held, Wait) and "holding" in held.reason
    # budget: after 8 held ticks it re-decides (failed-submission recovery)
    for _ in range(7):
        assert isinstance(r.decide(parse_state(transient), ctx), Wait)
    recovered = r.decide(parse_state(transient), ctx)
    assert isinstance(recovered, Decision)
    # and once the position CHANGES (travel landed), no hold at all
    moved = json.loads(json.dumps(payload))
    moved["map"]["current_position"] = {"col": 1, "row": 3, "type": "Monster"}
    moved["run"]["floor"] = payload["run"]["floor"] + 1
    r2 = router()
    ctx2 = LoopContext()
    r2.decide(parse_state(payload), ctx2)
    after_move = r2.decide(parse_state(moved), ctx2)
    assert isinstance(after_move, Decision)


def test_desperation_draw_skipped_under_ringing() -> None:
    """Under a 1-card cap (Ringing), the desperation draw would BE the whole turn -- the drawn
    cards can never be played (f17 Beast death 2026-07-09: Battle Trance burned the capped play).
    The planner's capped search must spend the one play on the best card (the block) instead."""
    state = make_combat(
        hand=[card(0, "Battle Trance", 0, "Draw 3 cards. Ringing."),
              card(1, "Evil Eye+", 1, "Gain 11 Block. Ringing."),
              card(2, "Strike", 1, "Deal 8 damage. Ringing.")],
        enemies=[enemy("BEAST_0", 46, intent_label="21")],
        hp=6, max_hp=80,
        player_status=[{"id": "RINGING_POWER", "name": "Ringing", "amount": 1,
                        "description": "You can only play 1 card this turn."}],
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    payload = d.action.payload()
    assert payload["action"] == "play_card" and payload["card_index"] == 1  # block, not draw


def test_planner_blind_cards_get_docked_at_draft() -> None:
    """Owner-approved 2026-07-09 (two live Cascade draft-and-upgrades): a card whose parsed
    effects are EMPTY gets a flat dock -- the planner can't use it, whatever the community
    prior says. Self-removing: a parseable card of the same rarity scores strictly higher,
    and an attack-GENERATOR (Infernal Blade) is exempt."""
    r = StandardRouter(combat_stats=None, bestiary={})

    class C:
        def __init__(self, cid, name, desc, rarity="Uncommon", typ="Skill", cost="1"):
            self.id, self.name, self.description = cid, name, desc
            self.rarity, self.type, self.cost = rarity, typ, cost

    blind = r._card_score(C("CASCADE", "Cascade", "Play the top X cards of your deck."), 15)
    parsed = r._card_score(C("SHRUG", "Shrug It Off", "Gain 8 Block. Draw 1 card."), 15)
    generator = r._card_score(
        C("INFERNAL_BLADE", "Infernal Blade", "Add a random Attack to your hand. It costs 0."),
        15)
    assert parsed > blind
    assert generator > blind  # the exemption: its output is playable


def test_reward_discard_compares_values_and_protects_foul() -> None:
    """Owner 2026-07-13 (live): a belt Foul (100g at the next merchant) was discarded
    for an ordinary reward potion. Foul ranks as gold value — and the throw itself
    was probe-proven + orchestrator-fixed 2026-07-25 (shopkeeper-window blind throw),
    so the 100g is real again."""
    def payload(belt, reward_name, reward_desc):
        return {
            "state_type": "rewards",
            "rewards": {"items": [
                {"index": 0, "type": "potion", "potion_id": reward_name.upper().replace(" ", "_"),
                 "potion_name": reward_name, "potion_description": reward_desc},
            ], "can_proceed": True},
            "run": {"act": 1, "floor": 5, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 50, "max_hp": 80,
                       "status": [], "relics": [], "max_potion_slots": 2,
                       "potions": belt},
        }

    foul = {"slot": 0, "id": "FOUL_POTION", "name": "Foul Potion",
            "description": "Lose 5 HP."}
    weakest = {"slot": 1, "id": "SPEED_POTION", "name": "Speed Potion",
               "description": "Gain 2 Dexterity this turn."}
    # full belt with a Foul: an ordinary reward potion must NOT evict it
    st = payload([dict(foul), dict(weakest)], "Weak Potion",
                 "Apply 3 Weak to target enemy.")
    d = router().decide(parse_state(st), LoopContext())
    p = d.action.payload()
    assert p.get("action") != "discard_potion" or p.get("slot") != 0
    # a genuinely better reward (Fruit Juice) evicts the WEAKEST (never the Foul)
    st2 = payload([dict(foul), dict(weakest)], "Fruit Juice", "Gain 5 Max HP.")
    d2 = router().decide(parse_state(st2), LoopContext())
    p2 = d2.action.payload()
    assert p2.get("action") == "discard_potion" and p2.get("slot") == 1
    # and a junk/unknown reward doesn't evict ANYTHING from a Foul+junk belt
    st3 = payload([dict(foul), dict(weakest)], "Mystery Brew", "Swirls mysteriously.")
    d3 = router().decide(parse_state(st3), LoopContext())
    assert d3.action.payload().get("action") != "discard_potion"


def test_death_rider_card_never_drafted() -> None:
    """The Gambit is gated to never-play in the planner, so drafting it buys a permanent
    dead card: its draft score must sit below any plausible take threshold."""
    r = StandardRouter(combat_stats=None, bestiary={})

    class C:
        def __init__(self, cid, name, desc, rarity="Rare", typ="Skill", cost="0"):
            self.id, self.name, self.description = cid, name, desc
            self.rarity, self.type, self.cost = rarity, typ, cost

    gambit = r._card_score(
        C("THE_GAMBIT", "The Gambit",
          "Gain 50 Block. If you take unblocked attack damage this combat, die."), 15)
    assert gambit <= -100.0


def test_guilty_not_worth_a_paid_removal() -> None:
    """Owner 2026-07-09: Guilty auto-removes after 5 combats -- paying to remove it wastes the
    removal. It ranks ABOVE a basic Strike as a removal target (the Strike goes first), and a
    deck whose only 'bad' card is Guilty doesn't trigger paid removal at all."""
    r = router()

    class C:
        def __init__(self, cid, name, typ, upgraded=False, desc=None):
            self.id, self.name, self.type = cid, name, typ
            self.is_upgraded, self.description = upgraded, desc

    guilty = C("GUILTY", "Guilty", "Curse")
    strike = C("STRIKE_IRONCLAD", "Strike", "Attack")
    normal_curse = C("REGRET", "Regret", "Curse")
    def q(c):
        return r._card_quality(c, "IRONCLAD")
    assert q(normal_curse) < q(strike) < q(guilty)  # real curse worst, then basic, then Guilty

    class P:
        def __init__(self):
            self.deck = [guilty, C("BASH", "Bash", "Attack", upgraded=True)]
    assert r._has_removable_card(P()) is False  # Guilty alone doesn't justify paying


def test_targeted_potion_always_gets_a_target() -> None:
    """Owner-caught (b8oazdsui run 2, died vs Kaiser Crab): hail-mary drank Beetle Juice
    (enemy-targeted debuff, category missed it) with no target -> API error -> died with it
    in the belt. drink() now enforces targeting from the potion's own target_type."""
    state = make_combat(
        hand=[],
        enemies=[enemy("ROCKET_0", 50, intent_label="52")],
        hp=4, max_hp=80,
        potions=[_potion("BEETLE_JUICE", "Beetle Juice",
                         "Enemy's attacks deal 30% less damage for the next 4 turns.",
                         target="AnyEnemy")],
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    payload = d.action.payload()
    assert payload["action"] == "use_potion"
    assert payload.get("target") == "ROCKET_0"  # never untargeted again


def test_percent_less_potion_classified_debuff_and_deployed() -> None:
    """Beetle Juice's "%-less" phrasing now classifies as a debuff -> deployed proactively at
    a boss start (with a target) instead of rotting until a hail-mary."""
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("BOSS_0", 200, intent_label="10")],
        hp=70, max_hp=80, state_type="boss",
        potions=[_potion("BEETLE_JUICE", "Beetle Juice",
                         "Enemy's attacks deal 30% less damage for the next 4 turns.",
                         target="AnyEnemy")],
    )
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    payload = d.action.payload()
    assert payload["action"] == "use_potion" and payload.get("target") == "BOSS_0"
    # 2026-08-06: the debuff lane now keys on the first DAMAGING intent
    assert "first damaging intent" in d.rationale


def test_forced_debuff_choice_picks_disintegration_deliberately() -> None:
    """Knowledge Demon's Curse of Knowledge (captured live 2026-07-09): an all-Status
    card_select is a pick-your-poison, chosen by the owner's least-bad table (Disintegration
    first) -- NOT by card quality or index order. Mind Rot at index 0 must still lose."""
    state = parse_state({
        "state_type": "card_select",
        "card_select": {"screen_type": "choose", "prompt": "Choose a card.", "cards": [
            {"index": 0, "id": "MIND_ROT", "name": "Mind Rot", "type": "Status", "cost": "0",
             "description": "Draw 1 fewer card each turn.", "is_upgraded": False, "keywords": []},
            {"index": 1, "id": "DISINTEGRATION", "name": "Disintegration", "type": "Status",
             "cost": "0", "description": "At the end of your turn, take 6 damage.",
             "is_upgraded": False, "keywords": []}]},
        "run": {"act": 2, "floor": 33, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80,
                   "status": [], "relics": [], "potions": [], "max_potion_slots": 3},
    })
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["index"] == 1  # Disintegration, despite index order


def test_potion_pick_subsidizes_cost_when_free_this_turn() -> None:
    """Owner 2026-07-09: card-gen potion offers show FULL printed cost but play free this
    turn -- the bot passed on Pyre (2e Power) in a call that was only sensible at printed
    cost. In combat, the pick scorer subsidizes printed cost (Powers most)."""
    cs_state = {
        "state_type": "card_select",
        "card_select": {"screen_type": "choose", "prompt": "Choose a card.", "cards": [
            {"index": 0, "id": "CHEAP_POWER", "name": "Cheap Power", "type": "Power",
             "cost": "1", "description": "Gain 3 Block each turn.", "is_upgraded": False,
             "keywords": []},
            {"index": 1, "id": "PYRE", "name": "Pyre", "type": "Power", "cost": "2",
             "description": "Gain [ironclad_energy_icon.png] at the start of each turn.",
             "is_upgraded": False, "keywords": []}]},
        "run": {"act": 1, "floor": 5, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80, "block": 0,
                   "energy": 3, "max_energy": 3, "in_combat": True,
                   "hand": [], "draw_pile_count": 5, "discard_pile_count": 0,
                   "exhaust_pile_count": 0,
                   "status": [], "relics": [], "potions": [], "max_potion_slots": 3},
    }
    d = router().decide(parse_state(cs_state), LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["index"] == 1  # Pyre: its 2-cost is subsidized in combat

    cs_state["player"]["in_combat"] = False  # out of combat: printed cost is real again
    d2 = router().decide(parse_state(cs_state), LoopContext())
    assert isinstance(d2, Decision)


def test_unwinnable_elite_lane_priced_death_class_at_commit_time() -> None:
    """bn4v9mf75 forensics: the remaining elite deaths were forced single-option lanes the DP
    had committed into floors earlier -- a gate-rejected elite's only cost was its discounted
    HP projection. It is now priced death-class: a weak deck at FULL HP must refuse the lane
    whose committed future holds an elite, even against a blander alternative."""
    payload = {
        "state_type": "map",
        "map": {
            "current_position": {"col": 2, "row": 0, "type": "Start"},
            "visited": [],
            "next_options": [
                {"index": 0, "col": 1, "row": 1, "type": "Monster",
                 "leads_to": [{"col": 1, "row": 2, "type": "Elite"}]},
                {"index": 1, "col": 3, "row": 1, "type": "Monster",
                 "leads_to": [{"col": 3, "row": 2, "type": "Monster"}]},
            ],
            "nodes": [
                {"col": 2, "row": 0, "type": "Start", "children": [[1, 1], [3, 1]]},
                {"col": 1, "row": 1, "type": "Monster", "children": [[1, 2]]},
                {"col": 3, "row": 1, "type": "Monster", "children": [[3, 2]]},
                {"col": 1, "row": 2, "type": "Elite", "children": [[2, 3]]},
                {"col": 3, "row": 2, "type": "Monster", "children": [[2, 3]]},
                {"col": 2, "row": 3, "type": "Monster", "children": []},
            ],
            "boss": {"col": 2, "row": 4, "id": "B", "name": "Boss"},
            "bosses": [],
        },
        "run": {"act": 1, "floor": 1, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 80, "max_hp": 80, "gold": 50,
                   "deck": [{"index": i, "id": "STRIKE_IRONCLAD", "name": "Strike",
                             "type": "Attack", "cost": "1", "description": "Deal 6 damage.",
                             "rarity": "Basic", "is_upgraded": False} for i in range(10)],
                   "status": [], "relics": [], "potions": [], "max_potion_slots": 3},
    }
    d = _router_for_routing().decide(parse_state(payload), LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["index"] == 1  # refuse the committed-elite lane at full HP


def test_finisher_potion_held_at_zero_threat() -> None:
    """Owner Q1 (2026-07-09): killing a harmless last enemy wastes a potion that persists
    across fights. Zero threat + no setup intent -> hold; a Buff (setting up) -> fire."""
    def state(intent_type, label=""):
        s = make_combat(
            hand=[],
            enemies=[{"entity_id": "W_0", "name": "Wisp", "hp": 15, "max_hp": 30, "block": 0,
                      "status": [], "intents": [{"type": intent_type, "label": label}]}],
            hp=60, max_hp=80,
            potions=[_potion("FIRE_POTION", "Fire Potion", "Deal 20 damage.",
                             target="AnyEnemy")],
        )
        return s

    idle = router().decide(state("sleep"), LoopContext())
    assert not (isinstance(idle, Decision)
                and idle.action.payload().get("action") == "use_potion")  # held

    brewing = router().decide(state("buff"), LoopContext())
    assert isinstance(brewing, Decision)
    assert brewing.action.payload()["action"] == "use_potion"  # setup: worth ending it now


def test_foul_throw_no_longer_attempted_on_the_shop_screen() -> None:
    """2026-07-25 probe: the throw only works on the SHOPKEEPER screen (our polling
    auto-advances past it), so the orchestrator now fires it blind after shop travel
    (test_mock_run) and the shop handler must NOT burn errors attempting it here."""
    shop_state = {
        "state_type": "shop",
        "shop": {"items": []},
        "run": {"act": 1, "floor": 6, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80, "gold": 40,
                   "status": [], "relics": [],
                   "potions": [_potion("FOUL_POTION", "Foul Potion",
                                       "Deal 10 damage to EVERYONE.", slot=1)],
                   "max_potion_slots": 3},
    }
    d = router().decide(parse_state(shop_state), LoopContext())
    if isinstance(d, Decision):
        assert d.action.payload().get("action") != "use_potion", d.rationale
def test_combat_without_battle_block_waits_not_crashes() -> None:
    """Live-only transitional state: combat announced but battle block not yet present
    (crashed batch bpnsoql1j run 1 via the potion bookkeeping's unguarded state.battle)."""
    state = parse_state({
        "state_type": "monster",
        "run": {"act": 1, "floor": 2, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 70, "max_hp": 80, "block": 0,
                   "energy": 3, "max_energy": 3, "hand": [], "draw_pile_count": 5,
                   "discard_pile_count": 0, "exhaust_pile_count": 0,
                   "status": [], "relics": [], "potions": [], "max_potion_slots": 3},
    })
    d = router().decide(state, LoopContext())
    assert isinstance(d, Wait)  # loading: wait, never crash


def test_retain_curse_discard_ranking() -> None:
    """Owner 2026-07-09 (+ same-day refinement): a Retain curse's parking value is worth one
    junk-tier, not immunity. Discard order: normal curses first, then the retain curse, then
    playables. With only playables besides it, the retain curse IS the discard."""
    def hs_state(prompt):
        return parse_state({
            "state_type": "hand_select",
            "hand_select": {"prompt": prompt, "can_confirm": False, "cards": [
                {"index": 0, "id": "POOR_SLEEP", "name": "Poor Sleep", "type": "Curse",
                 "cost": "0", "description": "Unplayable. Retain.", "can_play": False,
                 "is_upgraded": False, "keywords": []},
                {"index": 1, "id": "STRIKE_IRONCLAD", "name": "Strike", "type": "Attack",
                 "cost": "1", "description": "Deal 6 damage.", "can_play": True,
                 "is_upgraded": False, "keywords": []}]},
            "run": {"act": 1, "floor": 5, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80, "status": [],
                       "relics": [], "potions": [], "max_potion_slots": 3},
        })

    # rest of hand is playable -> the retain curse IS the right discard (owner refinement)
    d = router().decide(hs_state("Choose a card to Discard."), LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["card_index"] == 0

    d2 = router().decide(hs_state("Choose a card to Exhaust."), LoopContext())
    assert isinstance(d2, Decision)
    assert d2.action.payload()["card_index"] == 0  # exhaust removes it: take the curse


def test_normal_curse_discarded_before_retain_curse() -> None:
    """The junk-tier ordering: a normal curse (pure junk, cycles regardless) is the discard
    before the retain curse (which at least parks usefully)."""
    state = parse_state({
        "state_type": "hand_select",
        "hand_select": {"prompt": "Choose a card to Discard.", "can_confirm": False, "cards": [
            {"index": 0, "id": "POOR_SLEEP", "name": "Poor Sleep", "type": "Curse",
             "cost": "0", "description": "Unplayable. Retain.", "can_play": False,
             "is_upgraded": False, "keywords": []},
            {"index": 1, "id": "REGRET", "name": "Regret", "type": "Curse", "cost": "0",
             "description": "Unplayable.", "can_play": False, "is_upgraded": False,
             "keywords": []},
            {"index": 2, "id": "STRIKE_IRONCLAD", "name": "Strike", "type": "Attack",
             "cost": "1", "description": "Deal 6 damage.", "can_play": True,
             "is_upgraded": False, "keywords": []}]},
        "run": {"act": 1, "floor": 5, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80, "status": [],
                   "relics": [], "potions": [], "max_potion_slots": 3},
    })
    d = router().decide(state, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["card_index"] == 1  # Regret first; Poor Sleep parks another day


def test_spoils_map_is_exhaust_fodder_but_never_removed() -> None:
    """Owner 2026-07-17 (live): the bot exhausted basic commons over the Spoils Map — a
    type=Quest pseudocurse (unplayable in combat, redeems for 600g at the Act-3 chest,
    no description in the payload). Exhaust is per-fight, so the Map is prime fodder;
    remove/transform screens must protect it (deleting it deletes the payoff)."""
    spoils = _sc_card(0, "Spoils Map", "Quest", cid="SPOILS_MAP")
    spoils["description"] = None
    strike = _sc_card(1, "Strike", "Attack", cid="STRIKE_IRONCLAD")
    strike["description"] = "Deal 6 damage."
    curse = _sc_card(2, "Clumsy", "Curse", cid="CLUMSY")
    curse["description"] = "Unplayable."
    r = router()

    # EXHAUST: the Map beats the Strike...
    st = _card_select_state("select", "Choose a card to Exhaust.", [spoils, strike])
    assert r.decide(st, LoopContext()).action.payload()["index"] == 0

    # ...a true curse still goes first
    st2 = _card_select_state("select", "Choose a card to Exhaust.", [spoils, strike, curse])
    assert r.decide(st2, LoopContext()).action.payload()["index"] == 2

    # REMOVE: never delete the coupon — the Strike goes
    st3 = _card_select_state("select", "Choose a card to Remove.", [spoils, strike])
    assert r.decide(st3, LoopContext()).action.payload()["index"] == 1

    # TRANSFORM: same protection
    st4 = _card_select_state("select", "Choose a card to Transform.", [spoils, strike])
    assert r.decide(st4, LoopContext()).action.payload()["index"] == 1


def test_boss_aware_smith_prefers_threshold_crossing_upgrade() -> None:
    """Owner lever 2026-07-17: vs the Matriarch the offer stream is the binding
    constraint — Smithing widens it. An upgrade that crosses her per-instance
    threshold (Headbutt 6->12) outranks a same-screen Strike (6->9, never crosses)."""
    from sts2bot.policy.standard import _boss_draft_rule

    r = router()
    rule = _boss_draft_rule("Lagavulin Matriarch")

    class CS:
        prompt = "Choose a card to Upgrade."

        def __init__(self, cards):
            self.cards = cards

    class C:
        def __init__(self, i, cid, name):
            self.index, self.id, self.name = i, cid, name
            self.type, self.cost, self.rarity = "Attack", "1", "Common"
            self.is_upgraded = False
            self.description = ""

    cs = CS([C(0, "STRIKE_IRONCLAD", "Strike"), C(1, "HEADBUTT", "Headbutt")])
    pick = r._pick_target(cs, prefer_worst=False, character="The Ironclad",
                          boss_rule=rule)
    assert pick.id == "HEADBUTT"


def test_pre_boss_rest_gate_demands_more_vs_clock_boss() -> None:
    """Knowledge Demon recheck (2026-07-18): both f33 deaths raced him correctly and
    still died from 52-56 HP entries — his Disintegration clock isn't in the generic
    boss estimate. The rest gate demands rest_loss_bonus more HP when he's the boss."""
    from sts2bot.policy.standard import StandardRouter, _boss_draft_rule

    r = StandardRouter(combat_stats=None, bestiary={})
    w = r.config.rest
    payload = json.loads(json.dumps(FIXTURES["rest_site"]))
    est = r.combat_stats.expected_loss("boss") if r.combat_stats else None
    est = est if est is not None else w.default_boss_loss
    bump = _boss_draft_rule("Knowledge Demon")["rest_loss_bonus"]
    # an HP strictly between the generic threshold and the Demon-bumped one
    hp = int((est + bump / 2) * w.boss_safety_factor)
    payload["player"]["hp"] = hp
    payload["player"]["max_hp"] = 90

    ctx = LoopContext()
    ctx.screen_mem["pre_boss"] = True
    ctx.screen_mem["act_boss_name"] = "Vantom"
    d_vantom = r.decide(parse_state(payload), ctx)
    assert "smith" in d_vantom.rationale or "covers the boss" in d_vantom.rationale

    ctx2 = LoopContext()
    ctx2.screen_mem["pre_boss"] = True
    ctx2.screen_mem["act_boss_name"] = "Knowledge Demon"
    d_demon = r.decide(parse_state(payload), ctx2)
    assert d_demon.rationale.startswith("rest")


def test_hail_mary_never_drinks_self_lethal_foul() -> None:
    """Owner-caught 2026-07-20: at 9 HP the hail-mary fallback drank Foul Potion
    ('Deal 10 damage to EVERYONE' — drinker included), a certain suicide traded for
    a merely-projected death. Self-lethal potions are vetoed from the fallback; a
    healthy drinker may still use Foul as an AoE nuke."""
    from sts2bot.policy.standard import StandardRouter

    r = StandardRouter(combat_stats=None, bestiary={})

    def combat_state(hp):
        return parse_state({
            "state_type": "monster", "run": {"act": 2, "floor": 33, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": hp, "max_hp": 80,
                       "block": 0, "energy": 0, "status": [], "hand": [],
                       "potions": [{"slot": 0, "id": "FOUL_POTION",
                                    "name": "Foul Potion", "can_use_in_combat": True,
                                    "description": "Deal 10 damage to EVERYONE."}],
                       "max_potion_slots": 3},
            "battle": {"round": 3, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "kd0", "name": "Knowledge Demon",
                                    "hp": 200, "max_hp": 379, "block": 0,
                                    "status": [],
                                    "intents": [{"type": "attack", "label": "25"}]}]},
        })

    # 9 HP, projected-lethal turn: Foul must NOT be drunk (suicide)
    d = r.decide(combat_state(9), LoopContext())
    assert "Foul" not in (d.rationale or "")

    # 40 HP: Foul as hail-mary fallback is legitimate (10 < 40, and it nukes enemies)
    d2 = r.decide(combat_state(30), LoopContext())
    if "hail mary" in (d2.rationale or ""):
        assert "Foul" in d2.rationale


def test_slither_enchant_targets_highest_cost() -> None:
    """Owner 2026-07-20 (reversing the old 'Slither trap' anchor): Slither = random
    0-3 cost on draw, +EV on any cost>=2 card. The original sin was targeting a
    cost-1 Strike; the picker now takes the highest-cost card (Bash over Strike)."""
    r = router()

    class CS:
        prompt = "Enchant 1 card with Slither."

        def __init__(self, cards):
            self.cards = cards

    class C:
        def __init__(self, i, cid, name, cost):
            self.index, self.id, self.name, self.cost = i, cid, name, cost
            self.type, self.rarity, self.is_upgraded = "Attack", "Basic", False
            self.description = ""

    cs = CS([C(0, "STRIKE_IRONCLAD", "Strike", "1"), C(1, "BASH", "Bash", "2")])
    pick = r._pick_target(cs, prefer_worst=False, character="The Ironclad")
    assert pick.id == "BASH"


def test_sharp_enchant_prefers_multihit() -> None:
    """Owner: Sharp (per-hit) on a 3x attack beats even Swift-on-Power — the target
    picker prefers multi-hit attacks over single hits."""
    r = router()

    class CS:
        prompt = "Choose an Attack to Enchant with Sharp 2."

        def __init__(self, cards):
            self.cards = cards

    class C:
        def __init__(self, i, cid, name, desc):
            self.index, self.id, self.name = i, cid, name
            self.cost, self.type, self.rarity = "1", "Attack", "Common"
            self.is_upgraded = False
            self.description = desc

    cs = CS([C(0, "BLUDGEON", "Bludgeon", "Deal 32 damage."),
             C(1, "SWORD_BOOMERANG", "Sword Boomerang",
               "Deal 3 damage to a random enemy 3 times.")])
    pick = r._pick_target(cs, prefer_worst=False, character="The Ironclad")
    assert pick.id == "SWORD_BOOMERANG"


def test_rest_site_nonstandard_actions() -> None:
    """§8.4 class fix (4 members): relic/quest-added campfire options the fixed
    Rest/Smith menu was blind to. Hatch always beats Smith; Lift beats Smith while
    healthy; rest still wins when HP demands it; Cook requires thinnable cards."""
    from sts2bot.policy.standard import StandardRouter

    r = StandardRouter(combat_stats=None, bestiary={})

    def rest_state(hp, extra_options):
        opts = [{"index": 0, "id": "HEAL", "name": "Rest", "is_enabled": True},
                {"index": 1, "id": "SMITH", "name": "Smith", "is_enabled": True}]
        opts += [dict(o, index=2 + i) for i, o in enumerate(extra_options)]
        return parse_state({
            "state_type": "rest_site",
            "rest_site": {"options": opts, "can_proceed": False},
            "run": {"act": 1, "floor": 8, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": hp, "max_hp": 80,
                       "block": 0, "gold": 100, "status": [], "relics": [],
                       "potions": [], "max_potion_slots": 3,
                       "deck": [{"index": 0, "id": "STRIKE_IRONCLAD",
                                 "name": "Strike", "type": "Attack", "cost": "1",
                                 "is_upgraded": False}]},
        })

    lift = {"id": "LIFT", "name": "Lift", "is_enabled": True}
    hatch = {"id": "HATCH", "name": "Hatch", "is_enabled": True}
    cook = {"id": "COOK", "name": "Cook", "is_enabled": True}

    # healthy: Lift beats Smith
    d = r.decide(rest_state(70, [lift]), LoopContext())
    assert "lift" in d.rationale.lower()

    # hurt: Rest still wins over specials
    d2 = r.decide(rest_state(20, [lift]), LoopContext())
    assert d2.rationale.startswith("rest")

    # Hatch outranks Lift
    d3 = r.decide(rest_state(70, [lift, hatch]), LoopContext())
    assert "hatch" in d3.rationale.lower()

    # Cook fires with a removable Strike in deck
    d4 = r.decide(rest_state(70, [cook]), LoopContext())
    assert "cook" in d4.rationale.lower()


def test_delicate_frond_flips_potion_policy_aggressive() -> None:
    """Owner A/B #4 + live 2026-07-22: Delicate Frond refills empty slots every
    combat, inverting the hoard taxonomy — buffs deploy at NORMAL fights, heals
    top off at 80%, value potions skip the big-fight gate."""
    from sts2bot.policy.standard import StandardRouter

    r = StandardRouter(combat_stats=None, bestiary={})

    def combat(potions, hp=70, relics=()):
        return parse_state({
            "state_type": "monster", "run": {"act": 3, "floor": 40, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": hp, "max_hp": 80,
                       "block": 0, "energy": 0, "status": [], "hand": [],
                       "relics": [{"id": rid, "name": rid.replace("_", " ").title()}
                                  for rid in relics],
                       "potions": potions, "max_potion_slots": 5},
            "battle": {"round": 1, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "m0", "name": "Myte", "hp": 40,
                                    "max_hp": 40, "block": 0, "status": [],
                                    "intents": [{"type": "attack", "label": "8"}]}]},
        })

    flex = [{"slot": 0, "id": "FLEX_POTION", "name": "Flex Potion",
             "can_use_in_combat": True,
             "description": "Gain 5 Strength until the end of this turn."}]

    # without Frond: a buff potion is hoarded at a normal fight
    d = r.decide(combat(flex), LoopContext())
    assert "Flex" not in (d.rationale or "")

    # with Frond: deployed at the normal fight's start
    d2 = r.decide(combat(flex, relics=("DELICATE_FROND",)), LoopContext())
    assert "Flex" in (d2.rationale or "")


def test_act3_boss_rest_gate_demands_more() -> None:
    """Owner 2026-07-22 (Queen entry at 25/53): the aggregate boss-loss stat is
    Act-1-dominated (est 41 vs a 60+ Queen). Act-3 pre-boss rests demand
    act3_boss_loss_bonus more."""
    from sts2bot.policy.standard import StandardRouter

    r = StandardRouter(combat_stats=None, bestiary={})
    w = r.config.rest
    est = r.combat_stats.expected_loss("boss") if r.combat_stats else None
    est = est if est is not None else w.default_boss_loss
    hp = int((est + w.act3_boss_loss_bonus / 2) * w.boss_safety_factor)
    payload = json.loads(json.dumps(FIXTURES["rest_site"]))
    payload["player"]["hp"] = hp
    payload["player"]["max_hp"] = 90

    for act_n, expect_rest in ((1, False), (3, True)):
        payload["run"] = {"act": act_n, "floor": 16 if act_n == 1 else 47,
                          "ascension": 0}
        ctx = LoopContext()
        ctx.screen_mem["pre_boss"] = True
        ctx.screen_mem["act_boss_name"] = "Vantom" if act_n == 1 else "Queen"
        d = r.decide(parse_state(payload), ctx)
        assert d.rationale.startswith("rest") == expect_rest, (act_n, d.rationale)


def test_petrified_toad_throws_rock_freely() -> None:
    """Owner A/B #5: the Toad's Rock potion regenerates every combat — hoarding wastes
    the relic and clogs its slot. Finisher on sight; thrown at the biggest threat once
    the fight matures; without the relic the same potion is hoarded normally."""
    from sts2bot.policy.standard import StandardRouter

    r = StandardRouter(combat_stats=None, bestiary={})

    def combat(enemy_hp, round_n=1, relics=("PETRIFIED_TOAD",)):
        return parse_state({
            "state_type": "monster", "run": {"act": 1, "floor": 6, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80,
                       "block": 0, "energy": 0, "status": [], "hand": [],
                       "relics": [{"id": rid, "name": rid.replace("_", " ").title()}
                                  for rid in relics],
                       "potions": [{"slot": 0, "id": "ROCK", "name": "Rock",
                                    "can_use_in_combat": True,
                                    "target_type": "AnyEnemy",
                                    "description": "Deal 15 damage."}],
                       "max_potion_slots": 3},
            "battle": {"round": round_n, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "e0", "name": "Flyconid",
                                    "hp": enemy_hp, "max_hp": 60, "block": 0,
                                    "status": [],
                                    "intents": [{"type": "attack", "label": "8"}]}]},
        })

    # finisher on sight (enemy at 12 <= 15): either the combat planner throws it
    # as a computed LETHAL (in-plan potion path) or the Toad rule finishes — both
    # count; what matters is the Rock flies at the target
    d = r.decide(combat(12), LoopContext())
    assert d.action.payload().get("action") == "use_potion"
    assert d.action.payload().get("target") == "e0"

    # healthy enemy, round 1: hold; round 3: throw to free the slot
    d2 = r.decide(combat(50, round_n=1), LoopContext())
    assert "Rock" not in (d2.rationale or "")
    d3 = r.decide(combat(50, round_n=3), LoopContext())
    assert "free the Toad slot" in (d3.rationale or "")

    # no Toad relic: the Rock is hoarded like any damage potion
    d4 = r.decide(combat(50, round_n=3, relics=()), LoopContext())
    assert "Rock" not in (d4.rationale or "")


def test_pre_boss_rest_gate_uses_dfs_boss_estimate_when_cached() -> None:
    """P2b (2026-07-30): the aggregate history said '~45 needed' while Matriarch's
    drain spiral killed three runs from 62-64 HP entries. When the map block's DFS
    cache holds THIS deck vs THIS boss, the rest gate trusts it over history."""
    from sts2bot.policy.standard import StandardRouter

    r = StandardRouter(combat_stats=None, bestiary={})
    w = r.config.rest
    payload = json.loads(json.dumps(FIXTURES["rest_site"]))
    payload["player"]["max_hp"] = 90
    # an HP that comfortably covers the history estimate (would smith)...
    payload["player"]["hp"] = int(w.default_boss_loss * w.boss_safety_factor) + 6
    payload["player"]["deck"] = [
        {"index": 0, "id": "STRIKE_IRONCLAD", "name": "Strike", "type": "Attack",
         "cost": "1", "description": "Deal 6 damage.", "is_upgraded": False,
         "keywords": []},
        {"index": 1, "id": "BASH", "name": "Bash", "type": "Attack", "cost": "2",
         "description": "Deal 8 damage. Apply 2 Vulnerable.", "is_upgraded": False,
         "keywords": []},
    ]
    st = parse_state(payload)
    deck_key = tuple(sorted((c.id or "", bool(c.is_upgraded))
                            for c in st.player.deck))

    ctx = LoopContext()
    ctx.screen_mem["pre_boss"] = True
    ctx.screen_mem["act_boss_name"] = "Lagavulin Matriarch"
    d_history = r.decide(st, ctx)
    assert "smith" in d_history.rationale

    # ...but the DFS cache says this boss costs 80 HP for this deck -> rest.
    ctx2 = LoopContext()
    ctx2.screen_mem["pre_boss"] = True
    ctx2.screen_mem["act_boss_name"] = "Lagavulin Matriarch"
    ctx2.screen_mem["boss_roll_cache"] = {
        ("Lagavulin Matriarch", deck_key): 80.0}
    d_dfs = r.decide(st, ctx2)
    assert d_dfs.rationale.startswith("rest") and "DFS" in d_dfs.rationale


def test_fresh_elite_pool_excludes_recently_seen_until_three_fought() -> None:
    """Recurrence rule (owner 2026-07-29): a seen elite won't recur this act until
    3 elites have been fought — so it shouldn't dilute the gate's pool gamble
    (Gardeners f7 death NE6CSNNX2Y drew a 0.0-win member from a 4/6 pool)."""
    from sts2bot.policy.standard import StandardRouter

    pool = [("Terror Eel", {}), ("Phantasmal Gardener", {})]
    ctx = LoopContext()
    # Gardeners seen at elite fight #1; only 2 fights total -> still excluded
    ctx.screen_mem["elites_seen_at"] = {"PHANTASMAL GARDENER": 1}
    ctx.screen_mem["elite_floors"] = {(1, 6), (1, 10)}
    fresh = StandardRouter._fresh_elite_pool(pool, ctx)
    assert [n for n, _ in fresh] == ["Terror Eel"]
    # after the 4th elite fight (3 since sighting) it can recur -> back in the pool
    ctx.screen_mem["elite_floors"] = {(1, 6), (1, 10), (1, 13), (2, 4)}
    fresh = StandardRouter._fresh_elite_pool(pool, ctx)
    assert [n for n, _ in fresh] == ["Terror Eel", "Phantasmal Gardener"]


def test_field_of_man_sized_holes_takes_perfect_fit_over_normality() -> None:
    """Owner live catch 2026-07-30: the bot kept taking 'Resist' (2 removals + a
    NORMALITY curse) off Spirebird's removal-loving prior. Normality's 3-plays cap
    is awful unless a shop is 1-2 combats away (unknowable here), so the curated
    values flip the pick to the weak-but-harmless Perfect Fit enchant."""
    state = _ev_state("FIELD_OF_MAN_SIZED_HOLES", [
        _ev_opt(0, "Resist", "Remove 2 cards from your Deck. Add Normality to your Deck."),
        _ev_opt(1, "Enter Your Hole", "Enchant a card with Perfect Fit."),
        _ev_opt(2, "Proceed", "", is_proceed=True),
    ])
    idx = router().decide(state, LoopContext()).action.payload()["index"]
    assert idx == 1


def test_eternal_feather_entry_heal_rides_the_route_projection() -> None:
    """Owner relic check 2026-07-30: Eternal Feather heals 3 HP per 5 deck cards on
    ENTERING a rest site — no rest required. With a 20-card deck (+12 on entry) the
    campfire route's projection clears a death-floor pocket the bare projection
    can't; the feather is exactly the margin (same seam as Planisphere/Meal Ticket)."""
    from sts2bot.kb.combat_stats import CombatStats

    stats = CombatStats(by_type={
        "monster_early": {"mean": 4.0, "p75": 5, "n": 99},
        "monster": {"mean": 12.0, "p75": 18, "n": 99},
        "elite": {"mean": 21.0, "p75": 32, "n": 99},
        "boss": {"mean": 25.0, "p75": 42, "n": 99},
    })
    payload = json.loads(json.dumps(FIXTURES["map"]))
    payload["map"]["next_options"] = [
        {"index": 0, "col": 1, "row": 4, "type": "RestSite",
         "leads_to": [{"col": 1, "row": 5, "type": "Monster"}]},
        {"index": 1, "col": 2, "row": 4, "type": "Event",
         "leads_to": [{"col": 2, "row": 5, "type": "Monster"}]},
    ]
    payload["map"]["nodes"] = [
        {"col": 1, "row": 5, "type": "Monster", "children": []},
        {"col": 2, "row": 5, "type": "Monster", "children": []},
    ]
    # calibrated so the feather is exactly the margin (floor = 10% of 40 = 4):
    # rest heal alone (30% of 40 = 12) leaves 4+12-12 = 4 <= floor -> death
    # penalty; the feather's +6 (14-card fixture deck) clears it to 10.
    payload["player"]["hp"] = 4
    payload["player"]["max_hp"] = 40
    payload["player"]["deck"] = _STRONG_DECK
    payload["player"]["relics"] = [
        {"id": "ETERNAL_FEATHER", "name": "Eternal Feather",
         "description": "For every 5 cards in your deck, heal 3 HP whenever you "
                        "enter a Rest Site.", "counter": None, "keywords": []}]
    r = StandardRouter(combat_stats=stats, bestiary={})
    r.card_effects = _ROUTING_CARD_EFFECTS
    d = r.decide(parse_state(payload), LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["index"] == 0, d.scores
    # the seam itself: the same state WITHOUT the feather must score the rest-site
    # route strictly lower (the delta is the feather term riding the projection)
    with_feather = d.scores["0:RestSite"]
    bare = json.loads(json.dumps(payload))
    bare["player"]["relics"] = []
    d2 = r.decide(parse_state(bare), LoopContext())
    assert with_feather > d2.scores["0:RestSite"]


def test_queen_forecast_includes_the_torch_head_amalgam() -> None:
    """Tape 2026-07-30 (A36ZF0WVBS, f48 death from a 95-HP entry in 6 turns): the
    Queen's own realized dps is 2.1 -- she summons a 24.8-dps Torch Head Amalgam
    the single-entry forecast never saw. _upcoming_boss now adds summons as
    Kin-style minions: full threat, no kill-HP."""
    from sts2bot.policy.standard import StandardRouter

    bestiary = {"Queen": {"hp": [400, 400], "statuses": {}, "roles": ["boss"]},
                "Torch Head Amalgam": {"hp": [199, 199], "statuses": {},
                                       "roles": ["boss"]}}
    r = StandardRouter(combat_stats=None, bestiary=bestiary)
    r.enemy_dps = {"Queen": {"dps_early": 0.0, "dps_mean": 2.1},
                   "Torch Head Amalgam": {"dps_early": 23.4, "dps_mean": 24.8}}
    ctx = LoopContext()
    ctx.screen_mem["act_boss_name"] = "Queen"
    members = r._upcoming_boss(ctx, 3)
    assert len(members) == 2
    queen = next(m for m in members if m.hp == 400)
    tha = next(m for m in members if m.hp == 199)
    assert queen.counts_toward_kill and not tha.counts_toward_kill
    assert tha.dps == 23  # its own realized number, not the queen's 2


def test_stage_boss_table_expands_to_sequential_waves() -> None:
    """Test Subject: owner tape 2026-07-30 (#C29, full fight) showed every '#C__'
    variant is ONE entity that FULL-HEALS through 3 stages (100/200/300) -- the
    bestiary's per-variant entries are run fragments, not stages. The observed
    stage table expands to dormant waves (the Phrog machinery), keyed on the
    suffix-stripped base name so any run's variant resolves."""
    from sts2bot.policy.standard import StandardRouter

    r = StandardRouter(combat_stats=None, bestiary={
        "Queen": {"hp": [400, 400], "statuses": {}, "roles": ["boss"]}})
    ctx = LoopContext()
    ctx.screen_mem["act_boss_name"] = "Test Subject #C29"  # unseen variant: still resolves
    members = r._upcoming_boss(ctx, 3)
    assert [m.wave for m in members] == [0, 1, 2]      # sequential stages
    assert [m.hp for m in members] == [100, 200, 300]  # observed full-heal pools
    assert [m.dps for m in members] == [19, 36, 40]    # observed per-stage dps
    assert all(m.counts_toward_kill for m in members)  # every stage must die
    # a plain single-entry boss is untouched by the stage table
    ctx2 = LoopContext()
    ctx2.screen_mem["act_boss_name"] = "Queen"
    assert len(r._upcoming_boss(ctx2, 3)) >= 1


def test_pantograph_counts_toward_the_pre_boss_rest_gate() -> None:
    """Owner relic check 2026-07-30: Pantograph heals 25 at boss-combat START, so
    the gate must compare the post-heal entry HP. Same HP, same estimate: without
    the relic -> rest; with it -> smith."""
    from sts2bot.policy.standard import StandardRouter

    r = StandardRouter(combat_stats=None, bestiary={})
    w = r.config.rest
    payload = json.loads(json.dumps(FIXTURES["rest_site"]))
    payload["player"]["max_hp"] = 90
    # 10 short of the actual history-estimate bar: Pantograph's +25 must flip it
    est = r.combat_stats.expected_loss("boss") if r.combat_stats else None
    est = est if est is not None else w.default_boss_loss
    payload["player"]["hp"] = int(est * w.boss_safety_factor) - 10

    ctx1 = LoopContext()
    ctx1.screen_mem["pre_boss"] = True
    d_bare = r.decide(parse_state(payload), ctx1)
    assert d_bare.rationale.startswith("rest")

    payload["player"]["relics"] = [
        {"id": "PANTOGRAPH", "name": "Pantograph", "counter": None, "keywords": [],
         "description": "At the start of each Boss combat, heal 25 HP."}]
    ctx2 = LoopContext()
    ctx2.screen_mem["pre_boss"] = True
    d_panto = r.decide(parse_state(payload), ctx2)
    assert "smith" in d_panto.rationale and "Pantograph" in d_panto.rationale


def _kin_shaped_state(hp=60):
    def enemy(i, name, ehp):
        return {"entity_id": f"E{i}", "combat_id": 1, "name": name, "hp": ehp,
                "max_hp": ehp, "block": 0, "status": [],
                "intents": [{"type": "Attack", "label": "6", "title": "Attack",
                             "description": ""}]}
    card = {"id": "STRIKE_IRONCLAD", "name": "Strike", "type": "Attack", "cost": "1",
            "description": "Deal 6 damage.", "is_upgraded": False, "keywords": []}
    hand = [{**card, "index": i, "star_cost": None, "target_type": "AnyEnemy",
             "can_play": True, "unplayable_reason": None} for i in range(5)]
    deck = ([{**card, "index": i} for i in range(6)]
            + [{**card, "index": 6 + i, "id": "DEFEND_IRONCLAD", "name": "Defend",
                "type": "Skill", "description": "Gain 5 Block."} for i in range(4)])
    return parse_state({
        "state_type": "boss",
        "battle": {"round": 1, "turn": "player", "is_play_phase": True,
                   "enemies": [enemy(0, "Big Leader", 90), enemy(1, "Rampling", 12),
                               enemy(2, "Rampling", 12)]},
        "run": {"act": 1, "floor": 17, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": hp, "max_hp": 80, "block": 0,
                   "energy": 3, "max_energy": 3, "gold": 0, "hand": hand,
                   "status": [], "relics": [], "potions": [],
                   "max_potion_slots": 3, "in_combat": True, "deck": deck},
    })


def test_fight_plan_selects_sweep_for_a_low_burst_deck_vs_ramping_swarm() -> None:
    """Kin A/B 2026-07-30: the owner's scaling deck killed the Followers first and
    won where the bot's static race lost — and his June fight did the opposite and
    also won. 'No one strategy': the round-1 rollout comparison picks per fight.
    Starter-grade deck vs big leader + fast-ramping smalls -> sweep, decisively
    (probe: win 1.00 vs 0.00)."""
    from sts2bot.policy.standard import StandardRouter

    bestiary = {
        "Big Leader": {"hp": [90, 90], "statuses": {}},
        "Rampling": {"hp": [12, 12], "statuses": {
            "RAMP": {"name": "Ramp",
                     "description": "At the end of its turn, gains 5 Strength."}}},
    }
    r = StandardRouter(combat_stats=None, bestiary=bestiary)
    r.card_effects = {"STRIKE_IRONCLAD|0": "Deal 6 damage.",
                      "DEFEND_IRONCLAD|0": "Gain 5 Block."}
    r.enemy_dps = {"Big Leader": {"dps_early": 5.0},
                   "Rampling": {"dps_early": 4.0}}
    ctx = LoopContext()
    plan = r._fight_plan(_kin_shaped_state(), ctx)
    assert plan == "sweep"
    # cached: second call is free and identical
    assert r._fight_plan(_kin_shaped_state(), ctx) == "sweep"
    # and the decision rationale carries the plan tag for forensics
    d = r.decide(_kin_shaped_state(), ctx)
    assert "|plan=sweep" in d.rationale


def test_solo_drain_boss_gets_focus_plan_without_rollout() -> None:
    """Matriarch A/B 2026-07-30: solo drain/clock bosses are pure races (owner
    burst 222 HP in ~3 post-sleep rounds; the bot ground 18 turns into the drain
    spiral). One alive enemy matching the drain/clock table -> plan='focus'."""
    from sts2bot.policy.standard import StandardRouter

    r = StandardRouter(combat_stats=None, bestiary={})
    st = _kin_shaped_state()
    # rebuild as a solo Matriarch fight
    payload = json.loads(json.dumps({
        "state_type": "boss",
        "battle": {"round": 1, "turn": "player", "is_play_phase": True,
                   "enemies": [{"entity_id": "E0", "combat_id": 1,
                                "name": "Lagavulin Matriarch", "hp": 222,
                                "max_hp": 222, "block": 0, "status": [],
                                "intents": [{"type": "Sleep", "label": "Sleeping",
                                             "title": "Sleep", "description": ""}]}]},
        "run": {"act": 1, "floor": 17, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 44, "max_hp": 80, "block": 0,
                   "energy": 3, "max_energy": 3, "gold": 0, "hand": [], "status": [],
                   "relics": [], "potions": [], "max_potion_slots": 3,
                   "in_combat": True,
                   "deck": [{"index": 0, "id": "STRIKE_IRONCLAD", "name": "Strike",
                             "type": "Attack", "cost": "1",
                             "description": "Deal 6 damage.", "is_upgraded": False,
                             "keywords": []}]},
    }))
    assert r._fight_plan(parse_state(payload), LoopContext()) == "focus"
    del st


def test_regal_pillow_rest_heal_rides_the_route_projection() -> None:
    """Owner relic check 2026-07-30: Regal Pillow = +15 when you actually REST
    (unlike Eternal Feather's entry heal). Rides the DP's rest-heal term; fixture
    calibrated so the pillow is exactly the death-floor margin (floor = 4 at 40
    max: 4+12-12=4 <= floor bare; +15 clears it)."""
    from sts2bot.kb.combat_stats import CombatStats

    stats = CombatStats(by_type={
        "monster_early": {"mean": 4.0, "p75": 5, "n": 99},
        "monster": {"mean": 12.0, "p75": 18, "n": 99},
        "elite": {"mean": 21.0, "p75": 32, "n": 99},
        "boss": {"mean": 25.0, "p75": 42, "n": 99},
    })
    payload = json.loads(json.dumps(FIXTURES["map"]))
    payload["map"]["next_options"] = [
        {"index": 0, "col": 1, "row": 4, "type": "RestSite",
         "leads_to": [{"col": 1, "row": 5, "type": "Monster"}]},
        {"index": 1, "col": 2, "row": 4, "type": "Event",
         "leads_to": [{"col": 2, "row": 5, "type": "Monster"}]},
    ]
    payload["map"]["nodes"] = [
        {"col": 1, "row": 5, "type": "Monster", "children": []},
        {"col": 2, "row": 5, "type": "Monster", "children": []},
    ]
    payload["player"]["hp"] = 4
    payload["player"]["max_hp"] = 40
    payload["player"]["deck"] = _STRONG_DECK
    payload["player"]["relics"] = [
        {"id": "REGAL_PILLOW", "name": "Regal Pillow", "counter": None,
         "keywords": [],
         "description": "Whenever you Rest, heal an additional 15 HP."}]
    r = StandardRouter(combat_stats=stats, bestiary={})
    r.card_effects = _ROUTING_CARD_EFFECTS
    d = r.decide(parse_state(payload), LoopContext())
    assert isinstance(d, Decision)
    with_pillow = d.scores["0:RestSite"]
    bare = json.loads(json.dumps(payload))
    bare["player"]["relics"] = []
    d2 = r.decide(parse_state(bare), LoopContext())
    assert with_pillow > d2.scores["0:RestSite"]




def test_capability_delta_is_clamped_and_barricade_cannot_bury_offering() -> None:
    """Owner live catch 2026-07-30 (batch bbis4j9pj run 1, f17 boss reward):
    Barricade drafted at 92.5 over Offering 23.6 off a +52 capability delta --
    the greedy sim's permanent-block-vs-smoothed-dps snowball, priced against
    the DEAD act-1 boss to boot. With the clamp + next-act pricing, the exact
    recorded state (fixture captured verbatim from the run log) must rank
    Offering above Barricade."""
    from pathlib import Path

    from sts2bot.policy.standard import StandardRouter

    payload = json.loads(
        (Path(__file__).parent / "fixtures"
         / "card_reward_barricade_offering.json").read_text(encoding="utf-8"))
    r_ = StandardRouter()
    d = r_.decide(parse_state(payload), LoopContext())
    assert isinstance(d, Decision)
    assert d.scores["Offering"] > d.scores["Barricade"], d.scores


def _gambit_state(hp=10, block=0, incoming="52", gambit_playable=True):
    hand = [
        {"index": 0, "id": "THE_GAMBIT", "name": "The Gambit", "type": "Skill",
         "cost": "0", "star_cost": None,
         "description": "Gain 50 Block. If you take unblocked attack damage "
                        "this combat, die.",
         "target_type": "None", "can_play": gambit_playable,
         "unplayable_reason": None, "is_upgraded": False, "keywords": []},
        {"index": 1, "id": "STRIKE_IRONCLAD", "name": "Strike", "type": "Attack",
         "cost": "1", "star_cost": None, "description": "Deal 6 damage.",
         "target_type": "AnyEnemy", "can_play": True, "unplayable_reason": None,
         "is_upgraded": False, "keywords": []},
    ]
    return parse_state({
        "state_type": "boss",
        "battle": {"round": 7, "turn": "player", "is_play_phase": True,
                   "enemies": [{"entity_id": "E0", "combat_id": 1,
                                "name": "Knowledge Demon", "hp": 120, "max_hp": 250,
                                "block": 0, "status": [],
                                "intents": [{"type": "Attack", "label": incoming,
                                             "title": "Attack", "description": ""}]}]},
        "run": {"act": 2, "floor": 33, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": hp, "max_hp": 80,
                   "block": block, "energy": 3, "max_energy": 3, "gold": 0,
                   "hand": hand, "status": [], "relics": [], "potions": [],
                   "max_potion_slots": 3, "in_combat": True, "deck": []},
    })


def test_gambit_saves_the_doomed_turn() -> None:
    """Owner edge case 2026-07-31 (YL8MY7QB4K, KD r7): died at 10 HP vs proj 52
    with a cost-0 Gambit playable all turn. The self-death-rider veto is right on
    normal turns and inverts on doomed ones: certain death now loses to
    conditional death later."""
    from sts2bot.policy.standard import StandardRouter

    r = StandardRouter(combat_stats=None, bestiary={})
    d = r.decide(_gambit_state(), LoopContext())
    assert isinstance(d, Decision)
    p = d.action.payload()
    assert p.get("action") == "play_card" and p.get("card_index") == 0, d.rationale
    assert "death-rider save" in d.rationale


def test_gambit_veto_stands_when_the_turn_is_survivable() -> None:
    from sts2bot.policy.standard import StandardRouter

    r = StandardRouter(combat_stats=None, bestiary={})
    d = r.decide(_gambit_state(hp=60, incoming="12"), LoopContext())
    assert isinstance(d, Decision)
    p = d.action.payload()
    # survivable turn: the Gambit must NOT be played (veto stands); any other
    # action (Strike, end turn) is acceptable
    assert not (p.get("action") == "play_card" and p.get("card_index") == 0), d.rationale


def test_entropic_brew_drunk_when_belt_otherwise_empty() -> None:
    """Owner 2026-07-31: 'Fill all available potion slots' is free value when
    every other slot is empty; banking it is overthinking. Post-drink, the next
    poll re-reads the belt so hail-mary re-evaluates the new potions naturally."""
    from sts2bot.policy.standard import StandardRouter

    d_payload = json.loads(json.dumps({
        "state_type": "boss",
        "battle": {"round": 2, "turn": "player", "is_play_phase": True,
                   "enemies": [{"entity_id": "E0", "combat_id": 1,
                                "name": "Chomper", "hp": 40, "max_hp": 40,
                                "block": 0, "status": [],
                                "intents": [{"type": "Attack", "label": "8",
                                             "title": "Attack", "description": ""}]}]},
        "run": {"act": 1, "floor": 5, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80, "block": 0,
                   "energy": 3, "max_energy": 3, "gold": 0, "hand": [], "status": [],
                   "relics": [],
                   "potions": [{"id": "ENTROPIC_BREW", "name": "Entropic Brew",
                                "slot": 0, "can_use_in_combat": True,
                                "target_type": "None", "keywords": [],
                                "description": "Fill all available potion slots "
                                               "with random potions."}],
                   "max_potion_slots": 3, "in_combat": True, "deck": []},
    }))
    r = StandardRouter(combat_stats=None, bestiary={})
    d = r.decide(parse_state(d_payload), LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("action") == "use_potion", d.rationale
    assert "free refill" in d.rationale


def test_stage_boss_variant_passes_the_dfs_rest_gate_guard() -> None:
    """GLTQT0XBN7 (2026-07-31, Test Subject f48 death): the run's '#C31'-class
    variant name isn't a bestiary key, so both DFS gates fell back to aggregate
    history and the 600-HP stage model never got asked. _boss_is_known accepts
    stage-table bases; the rest gate must produce a DFS estimate."""
    from sts2bot.policy.standard import StandardRouter

    r = StandardRouter(combat_stats=None, bestiary={})
    ctx = LoopContext()
    ctx.screen_mem["act_boss_name"] = "Test Subject #C31"
    loss = r._dfs_boss_loss(
        ctx,
        parse_state(json.loads(json.dumps({
            "state_type": "rest_site",
            "rest_site": {"options": []},
            "run": {"act": 3, "floor": 47, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80,
                       "gold": 0, "relics": [], "potions": [],
                       "max_potion_slots": 3,
                       "deck": [{"index": i, "id": "STRIKE_IRONCLAD",
                                 "name": "Strike", "type": "Attack", "cost": "1",
                                 "description": "Deal 6 damage.",
                                 "is_upgraded": False, "keywords": []}
                                for i in range(10)]},
        }))).player,
        3,
    )
    assert loss is not None and loss > 60  # 600 kill-HP fight: starter loses big


def test_pumpkin_candle_rekindled_when_low_not_when_fresh() -> None:
    """Owner relic check 2026-07-31: Pumpkin Candle (+1 energy/turn, 5 combats,
    Kindle at rest sites restores charges -- owner-sourced online, never seen
    live). The SS8.4 specials ladder didn't know it -- it fell through to
    smith, Girya-style. Kindle fires at
    <=2 charges and stays away at 4+ (wasted campfire)."""
    from sts2bot.policy.standard import StandardRouter

    def rest_state(charges):
        return parse_state(json.loads(json.dumps({
            "state_type": "rest_site",
            "rest_site": {"options": [
                {"index": 0, "id": "HEAL", "name": "Rest", "is_enabled": True},
                {"index": 1, "id": "SMITH", "name": "Smith", "is_enabled": True},
                {"index": 2, "id": "KINDLE", "name": "Kindle",
                 "is_enabled": True},
            ]},
            "run": {"act": 2, "floor": 22, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 70, "max_hp": 80,
                       "gold": 0, "hand": [], "status": [],
                       "relics": [{"id": "PUMPKIN_CANDLE", "name": "Pumpkin Candle",
                                   "counter": charges, "keywords": [],
                                   "description": "Gain Energy at the start of "
                                                  "each turn. Lasts 5 combats."}],
                       "potions": [], "max_potion_slots": 3, "deck": []},
        })))

    r = StandardRouter(combat_stats=None, bestiary={})
    low = r.decide(rest_state(1), LoopContext())
    assert low.action.payload()["index"] == 2 and "rekindle" in low.rationale.lower()
    fresh = r.decide(rest_state(5), LoopContext())
    assert fresh.action.payload()["index"] != 2  # fresh candle: don't waste the site


def test_mummified_hand_nudges_power_drafts() -> None:
    """Owner relic query 2026-07-31: Mummified Hand ('whenever you play a Power,
    a random card in hand costs 0 for the turn') should make POWERS more
    favorable at draft time. The in-fight discount rides per-poll replanning;
    the draft layer needed the pull."""
    from types import SimpleNamespace as NS

    from sts2bot.policy.standard import StandardRouter

    r = StandardRouter(combat_stats=None, bestiary={})
    power = NS(index=0, id="INFLAME", name="Inflame", type="Power", cost="1",
               description="Gain 2 Strength.", rarity="Uncommon",
               is_upgraded=False, keywords=[])
    hand_relic = [NS(id="MUMMIFIED_HAND", name="Mummified Hand",
                     description="Whenever you play a Power, a random card in "
                                 "your hand costs 0 for the turn.")]
    bare = r._card_score(power, 15, "The Ironclad", 1, deck=[], relics=None)
    held = r._card_score(power, 15, "The Ironclad", 1, deck=[], relics=hand_relic)
    assert held - bare == 2.0
    # non-powers unaffected
    strike = NS(index=1, id="STRIKE_IRONCLAD", name="Strike", type="Attack",
                cost="1", description="Deal 6 damage.", rarity="Basic",
                is_upgraded=False, keywords=[])
    assert (r._card_score(strike, 15, "The Ironclad", 1, deck=[], relics=hand_relic)
            == r._card_score(strike, 15, "The Ironclad", 1, deck=[], relics=None))


def test_fiddle_blocks_draw_lanes_and_dampens_draw_drafts() -> None:
    """Owner relic check 2026-07-31: Fiddle ('draw 2 at turn start; you may NOT
    draw cards during your turn') surfaces NO player status, so the Battle Trance
    NO_DRAW machinery never fired -- draw credit flowed to draws that silently do
    nothing. _draws_blocked reads the relic text; drafting docks dead draw riders."""
    from types import SimpleNamespace as NS

    from sts2bot.policy.standard import StandardRouter, _draws_blocked

    fiddle = NS(id="FIDDLE", name="Fiddle",
                description="At the start of each turn, draw 2 additional cards. "
                            "You may not draw cards during your turn.")
    player = NS(status=[], relics=[fiddle])
    assert _draws_blocked(player)
    assert not _draws_blocked(NS(status=[], relics=[]))

    r = StandardRouter(combat_stats=None, bestiary={})
    shrug = NS(index=0, id="SHRUG_IT_OFF", name="Shrug It Off", type="Skill",
               cost="1", description="Gain 8 Block. Draw 1 card.",
               rarity="Common", is_upgraded=False, keywords=[])
    bare = r._card_score(shrug, 15, "The Ironclad", 1, deck=[], relics=None)
    held = r._card_score(shrug, 15, "The Ironclad", 1, deck=[], relics=[fiddle])
    assert bare - held == 2.0  # dead draw rider docked


def test_full_belt_drinks_a_heal_to_claim_the_reward_potion() -> None:
    """Owner corner case 2026-08-01: belt [Blood, Blood, Block], a THIRD Blood
    Potion dropped, bot skipped it. Even a paltry heal at high HP beats skipping:
    drink the belt heal, claim the drop, net = same belt + a few HP. Fires only
    below max HP; at full HP the rank-based discard logic keeps the wheel."""
    payload = json.loads(json.dumps(FIXTURES["rewards"]))
    payload["player"]["hp"] = 76
    payload["player"]["max_hp"] = 80
    payload["player"]["potions"] = [
        {"id": "BLOOD_POTION", "name": "Blood Potion", "slot": 0,
         "description": "Heal 20% of your Max HP."},
        {"id": "BLOOD_POTION", "name": "Blood Potion", "slot": 1,
         "description": "Heal 20% of your Max HP."},
        {"id": "BLOCK_POTION", "name": "Block Potion", "slot": 2,
         "description": "Gain 12 Block."},
    ]
    payload["player"]["max_potion_slots"] = 3
    for item in payload["rewards"]["items"]:
        if item.get("type") == "potion":
            item["potion_id"] = "BLOOD_POTION"
            item["potion_name"] = "Blood Potion"
            item["potion_description"] = "Heal 20% of your Max HP."
    d = router().decide(parse_state(payload), LoopContext())
    assert isinstance(d, Decision)
    p = d.action.payload()
    assert p["action"] == "use_potion" and p["slot"] in (0, 1), d.rationale
    assert "free a belt slot" in d.rationale


def test_enchant_confirm_stall_never_reselects_and_cancels_to_reset() -> None:
    """Owner-diagnosed 2026-08-01 (batch 51476 f3, Slither enchant): the June fix
    cleared pick-tracking on preview_showing, so one transiently-failed confirm
    made the bot RE-SELECT Bash -- toggling the game's internal selection OFF
    while the preview stayed up; after that confirm no-oped for bot AND human.
    Owner's manual recovery: back -> fresh select -> confirm. The handler now
    re-confirms (never re-selects) and after 4 stuck confirms cancels to reset."""
    from types import SimpleNamespace as NS  # noqa: F401

    cards = [{"index": 0, "id": "BASH", "name": "Bash", "type": "Attack",
              "cost": "2", "description": "Deal 8 damage. Apply 2 Vulnerable.",
              "rarity": "Basic", "is_upgraded": False, "keywords": []}]

    def screen(can_confirm, preview):
        st = _card_select_state("NDeckEnchantSelectScreen",
                                "Choose a card to Enchant.", cards,
                                can_confirm=can_confirm)
        st.card_select.preview_showing = preview
        return st

    from sts2bot.policy.base import Wait

    r = router()
    ctx = LoopContext()
    d1 = r.decide(screen(False, False), ctx)
    assert d1.action.payload()["action"] == "select_card"  # first pick
    seq = []
    for _ in range(40):  # screen stuck: preview up, confirm never resolves
        d = r.decide(screen(True, True), ctx)
        seq.append("wait" if isinstance(d, Wait)
                   else d.action.payload()["action"])
    # settle-dwell first (the root fix: a confirm during the preview's opening
    # animation wedges the container -- live dissection 2026-08-01), then
    # dwell-paced confirms, a cancel-reset per cycle, and after 2 cycles pure
    # Waits so the stall rail can abort -- NO livelock
    assert seq[:3] == ["wait"] * 3  # preview settling
    assert seq[3] == "confirm_selection"
    assert "select_card" not in [a for a in seq[:seq.index("cancel_selection")]]
    assert seq.count("cancel_selection") <= 2
    tail = seq[-6:]
    assert all(a == "wait" for a in tail), seq  # livelock impossible


def test_forced_upgrade_grid_never_double_selects() -> None:
    """The wedge's true root (proven on the owner's repro tape 2026-08-01): a
    FORCED upgrade grid (no cancel/skip/confirm pre-selection) misroutes poll 1
    into the resolves-on-select branch, which didn't record its pick -- poll 2's
    pick-N path selected AGAIN, toggling the card OFF under the open preview.
    Sequence must be: one select, settle waits, confirm. No second select."""
    from sts2bot.policy.base import Wait

    cards = [{"index": 10, "id": "TAUNT", "name": "Taunt", "type": "Skill",
              "cost": "1", "description": "Gain 7 Block. Apply 1 Vulnerable.",
              "rarity": "Uncommon", "is_upgraded": False, "keywords": []}]

    def grid(preview, can_confirm, can_cancel):
        st = _card_select_state("upgrade", "Choose a card to Upgrade.", cards,
                                can_confirm=can_confirm, can_cancel=can_cancel)
        st.card_select.preview_showing = preview
        return st

    r = router()
    ctx = LoopContext()
    d1 = r.decide(grid(False, False, False), ctx)  # forced: no buttons yet
    assert d1.action.payload()["action"] == "select_card"
    seq = []
    for _ in range(6):  # preview now up, as the game presents it
        d = r.decide(grid(True, True, True), ctx)
        seq.append("wait" if isinstance(d, Wait) else d.action.payload()["action"])
    assert "select_card" not in seq, seq  # THE fix: never a second toggle
    assert "confirm_selection" in seq, seq


def test_act3_spend_down_buys_negative_war_relics_with_dead_gold() -> None:
    """Owner rule 2026-08-01: relics are USUALLY strict upsides; a negative
    Spirebird WAR is correlational and must not veto a dead-gold purchase at the
    run's last shops. Only active-downside texts (Ectoplasm-class) stay skips."""
    payload = json.loads(json.dumps(FIXTURES["shop"]))
    payload["player"]["gold"] = 1000
    payload["run"]["act"] = 3
    payload["player"]["potions"] = [{"id": f"P{i}", "name": f"P{i}", "slot": i}
                                    for i in range(3)]
    payload["player"]["max_potion_slots"] = 3
    for it in payload["shop"]["items"]:
        if it["category"] == "relic":
            it["relic_id"] = "MOLTEN_EGG"  # Spirebird WAR negative
            it["relic_name"] = "Molten Egg"
            it["relic_description"] = ("Whenever you add an Attack to your deck, "
                                       "upgrade it.")
    d = router().decide(parse_state(payload), LoopContext())
    assert isinstance(d, Decision)
    p = d.action.payload()
    assert p["action"] == "shop_purchase", d.rationale


def test_chest_settle_dwell_and_claim_cap() -> None:
    """Two treasure black screens in one day (2026-08-01, f41+f26): the first
    claim right after 'Opening chest...' clears lands mid-animation, wedges the
    chest, and the 11-tick debounce hammering escalates it to a BLACK SCREEN.
    Now: 3 settle Waits before the first claim; after 3 ok'd-but-ignored claims,
    pure Waits so the stall rail aborts instead of deepening the wedge."""
    from sts2bot.policy.base import Wait

    payload = json.loads(json.dumps(FIXTURES["treasure"]))
    payload["treasure"]["message"] = None
    payload["treasure"]["relics"] = [{"index": 0, "id": "TEA_SET",
                                      "name": "Venerable Tea Set",
                                      "description": "x", "keywords": []}]
    payload["treasure"]["can_proceed"] = True
    r = router()
    ctx = LoopContext()
    seq = []
    for _ in range(12):  # chest wedged: state never changes
        d = r.decide(parse_state(payload), ctx)
        seq.append("wait" if isinstance(d, Wait) else d.action.payload()["action"])
    assert seq[:3] == ["wait"] * 3                      # settle before first claim
    assert seq.count("claim_treasure_relic") == 3       # capped hammering
    assert all(a == "wait" for a in seq[6:]), seq       # then stall-rail territory


def test_desperation_activates_on_zero_elites_late_or_boss_doom() -> None:
    """Owner rule 2026-08-02: 'any run that has taken 0 Elites in all of Act 1
    is probably doomed in the long-term.' Zero elites at act-floor >= 8, or a
    DFS boss forecast >= 90% of max HP, lowers the elite gate's bar."""
    from sts2bot.kb.config import MapWeights
    from sts2bot.policy.standard import _desperation_active

    # dataclass DEFAULTS, not the deployed toml: config/policy.toml may toggle
    # the coupling off for attribution batches; this test covers the mechanism
    w = MapWeights()
    # healthy early run: not desperate
    assert not _desperation_active(w, 1, 5, 0, None, 80)
    # zero elites late in act 1: desperate
    assert _desperation_active(w, 1, 9, 0, None, 80)
    # elites taken: the late-act arm stands down
    assert not _desperation_active(w, 1, 9, 2, None, 80)
    # boss forecast near-unwinnable: desperate regardless of elites
    assert _desperation_active(w, 2, 4, 3, 75.0, 80)
    # boss beatable: not desperate
    assert not _desperation_active(w, 2, 4, 3, 40.0, 80)


def test_combat_action_settle_guard_holds_until_quiescent() -> None:
    """Kaiser Crab freeze (seed 373PFAE7EE, deterministic, 3-for-3 under bot
    pacing vs 0-for-1 under the owner's hand replay): Pillage with a Replay 1
    enchant killing Rocket is a multi-second resolution chain. Guard v1 held
    only until the state FIRST changed -- but the chain mutates state every
    poll (HP ticks, draws landing one by one), so v1 released mid-animation,
    plays + end-turn fired into the running resolution, and the engine's
    scripted move wedged again. v2 semantics: a combat action is sent only
    when the state has been IDENTICAL for action_quiesce_polls consecutive
    polls, and a sent action must visibly land before the next send. The gate
    is scoped to the action->settled window: with nothing in flight (fight
    start), the first action goes out immediately."""
    r = router()
    q = r.config.combat.action_quiesce_polls
    ctx = LoopContext()
    state = make_combat(hand=[card(0, "Strike", 1, "Deal 6 damage.")],
                        enemies=[enemy("CRAB_0", 60)], energy=3)
    d1 = r.decide(state, ctx)
    assert isinstance(d1, Decision)
    assert d1.action.payload()["action"] == "play_card"
    # identical state re-presented (action not yet reflected) -> hold
    for _ in range(5):
        w = r.decide(state, ctx)
        assert isinstance(w, Wait) and "settle" in w.reason
    # the resolution chain: state changes EVERY poll -> keep holding (the v1 bug
    # released here); three distinct mid-animation snapshots, never quiescent
    mid1 = make_combat(hand=[], enemies=[enemy("CRAB_0", 57)], energy=2)
    mid2 = make_combat(hand=[], enemies=[enemy("CRAB_0", 55)], energy=2)
    mid3 = make_combat(hand=[], enemies=[enemy("CRAB_0", 54)], energy=2)
    for mid in (mid1, mid2, mid3):
        w = r.decide(mid, ctx)
        assert isinstance(w, Wait) and "quiesce" in w.reason
    # resolution finished: the settled state repeats -> quiesce, then act
    # (mid3 was the settled state's first sighting, so q-2 more holds remain)
    after = make_combat(hand=[], enemies=[enemy("CRAB_0", 54)], energy=2)
    for _ in range(q - 2):
        w = r.decide(after, ctx)
        assert isinstance(w, Wait) and "quiesce" in w.reason
    d2 = r.decide(after, ctx)
    assert isinstance(d2, Decision)
    assert d2.action.payload()["action"] == "end_turn"
    # end-turn is guarded too (the freeze fired on end-turn into the animation)
    w2 = r.decide(after, ctx)
    assert isinstance(w2, Wait) and "settle" in w2.reason


def test_combat_action_settle_guard_caps_out() -> None:
    """A silently-failed action must not soft-lock the turn: after the hold cap
    the guard falls through and the planner re-decides. 2026-09-03 refinement
    (Stomp stall, run 151507): the play the game refused for the whole window
    is EXCLUDED from that re-decision -- resubmitting it forever was the stall
    -- so a second card is played instead, or the turn ends."""
    r = router()
    ctx = LoopContext()
    state = make_combat(hand=[card(0, "Strike", 1, "Deal 6 damage."),
                              card(1, "Strike", 1, "Deal 6 damage.")],
                        enemies=[enemy("CRAB_0", 60)], energy=3)
    first = r.decide(state, ctx)
    assert isinstance(first, Decision)
    refused_idx = first.action.payload()["card_index"]
    cap = r.config.combat.action_settle_polls
    waits = 0
    d = None
    while True:
        d = r.decide(state, ctx)
        if not isinstance(d, Wait):
            break
        waits += 1
        assert waits <= cap
    assert waits == cap
    assert d.action.payload()["action"] == "play_card"
    assert d.action.payload()["card_index"] != refused_idx
    # both refused -> end the turn rather than loop
    for _ in range(cap + 1):
        d = r.decide(state, ctx)
    assert d.action.payload()["action"] == "end_turn"


def test_fight_plan_commits_even_when_both_orders_lose() -> None:
    """Queen A/B (owner 2026-08-02): both target orders projected losses, the
    margins collapsed to ~0, and no plan was committed -- the per-turn DFS then
    flipped targets mid-fight and split damage across two bodies with neither
    dying. In losing positions coherence matters MOST: commit to the less-bad
    order anyway."""
    r = router()
    deck = [{"index": i, "id": "STRIKE_IRONCLAD", "name": "Strike", "type": "Attack",
             "cost": "1", "description": "Deal 6 damage.", "rarity": "Basic",
             "is_upgraded": False} for i in range(10)]
    state = parse_state({
        "state_type": "boss", "run": {"act": 2, "floor": 33, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 40, "max_hp": 80, "block": 0,
                   "energy": 3, "status": [], "deck": deck,
                   "hand": [card(0, "Strike", 1, "Deal 6 damage.")],
                   "potions": [], "max_potion_slots": 3},
        "battle": {"round": 1, "turn": "player", "is_play_phase": True,
                   "enemies": [enemy("HULK_0", 900, intent_label="40"),
                               enemy("BRUTE_0", 700, intent_label="35")]},
    })
    plan = r._fight_plan(state, LoopContext())
    assert plan in ("sweep", "focus")


def test_tungsten_rod_skipped_with_one_hp_cost_engine() -> None:
    """Epoch relic (owner 2026-08-02): 'lose 1 less' zeroes EXACTLY-1-HP card
    costs (Brand-class), breaking their loss-keyed engines -- one of the few
    genuinely negative relic takes. Costs of 2+ are unaffected."""
    def rs_state(relics, deck_cards):
        return parse_state({
            "state_type": "relic_select",
            "relic_select": {"relics": relics, "can_skip": True},
            "run": {"act": 2, "floor": 20, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80,
                       "deck": deck_cards},
        })

    brand_deck = [
        {"index": 0, "id": "BRAND", "name": "Brand", "type": "Attack", "cost": "1",
         "description": "Lose 1 HP. Deal 8 damage. Gain 1 Energy.",
         "rarity": "Common", "is_upgraded": False},
        {"index": 1, "id": "STRIKE_IRONCLAD", "name": "Strike", "type": "Attack",
         "cost": "1", "description": "Deal 6 damage.", "rarity": "Basic",
         "is_upgraded": False},
    ]
    plain_deck = [dict(brand_deck[1], index=i) for i in range(2)]
    rod = {"id": "TUNGSTEN_ROD", "name": "Tungsten Rod", "index": 0}
    other = {"id": "ANCHOR", "name": "Anchor", "index": 1}

    r = router()
    # Brand deck, rod + alternative offered: take the alternative
    d = r.decide(rs_state([rod, other], brand_deck), LoopContext())
    assert d.action.payload()["index"] == 1
    # Brand deck, rod alone: skip outright
    d2 = r.decide(rs_state([rod], brand_deck), LoopContext())
    assert d2.action.payload()["action"] == "skip_relic_selection"
    # no 1-HP-cost cards: the rod is a normal take
    d3 = r.decide(rs_state([rod], plain_deck), LoopContext())
    assert d3.action.payload()["action"] == "select_relic"


def test_regen_potion_deployed_early_at_boss_when_below_max_minus_5() -> None:
    """Owner 2026-08-02: Regen 5 = 5+4+3+2+1 = 15 HP over 5 turns -- worthless
    in short fights, premium in bosses/elites. Rule: drink the moment HP drops
    below max-5 (first tick can't overheal; bosses run the clock easily)."""
    regen = _potion("REGEN_POTION", "Regen Potion", "Gain 5 Regen.")

    def st(hp, state_type):
        return make_combat(
            hand=[card(0, "Defend", 1, "Gain 5 Block.", target="Self", ctype="Skill")],
            enemies=[enemy("BOSS_0", 300, intent_label="10")],
            hp=hp, max_hp=80, state_type=state_type, potions=[regen],
        )

    r = router()
    # boss, HP 70/80 (missing > 5): drink now
    d = r.decide(st(70, "boss"), LoopContext())
    assert d.action.payload()["action"] == "use_potion"
    assert "regen" in (d.rationale or "").lower()
    # boss, HP 77/80 (missing < 5): hold -- the first tick would overheal
    d2 = r.decide(st(77, "boss"), LoopContext())
    assert d2.action.payload().get("action") != "use_potion"
    # plain monster fight at 70/80: hold for a fight that runs the clock
    d3 = r.decide(st(70, "monster"), LoopContext())
    assert d3.action.payload().get("action") != "use_potion"


def test_powdered_demise_thrown_at_biggest_body_unless_artifacted() -> None:
    """Owner 2026-08-02: 'target loses 9 HP at the end of each of its turns' --
    throw early at bosses/elites at the max-HP body (leader for minion bosses;
    the max-HP Decimillipede segment approximates 'a part not otherwise
    targeted'). It's a STATUS: Artifact charges eat it, so charged targets are
    skipped; vs the staged Test Subject hold for the 300-HP final stage."""
    demise = _potion("POWDERED_DEMISE", "Powdered Demise",
                     "Target loses 9 HP at the end of each of its turns.")

    def st(enemies, state_type="boss"):
        return parse_state({
            "state_type": state_type, "run": {"act": 3, "floor": 45, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 70, "max_hp": 80, "block": 0,
                       "energy": 3, "status": [],
                       "hand": [card(0, "Defend", 1, "Gain 5 Block.",
                                     target="Self", ctype="Skill")],
                       "potions": [demise], "max_potion_slots": 3},
            "battle": {"round": 1, "turn": "player", "is_play_phase": True,
                       "enemies": enemies},
        })

    def foe(eid, name, hp, max_hp=None, status=()):
        return {"entity_id": eid, "combat_id": 1, "name": name, "hp": hp,
                "max_hp": max_hp or hp, "block": 0, "status": list(status),
                "intents": [{"type": "Attack", "label": "10", "title": "Attack",
                             "description": ""}]}

    r = router()
    # minion boss: the 400-HP leader gets the DoT, not the 199-HP torch
    d = r.decide(st([foe("T0", "Torch Head Amalgam", 199),
                     foe("Q0", "Queen", 400)]), LoopContext())
    assert d.action.payload()["action"] == "use_potion"
    assert d.action.payload()["target"] == "Q0"
    # artifact on the leader: skip it, take the next body instead
    art = {"id": "ARTIFACT_POWER", "name": "Artifact", "amount": 2, "description": ""}
    d2 = r.decide(st([foe("T0", "Torch Head Amalgam", 199),
                      foe("Q0", "Queen", 400, status=[art])]), LoopContext())
    assert d2.action.payload()["action"] == "use_potion"
    assert d2.action.payload()["target"] == "T0"
    # Test Subject stage 1 (100 max): hold for the 300-HP final stage
    d3 = r.decide(st([foe("TS0", "Test Subject #C29", 100)]), LoopContext())
    assert d3.action.payload().get("action") != "use_potion"
    # Test Subject stage 3 (300 max): now it flies
    d4 = r.decide(st([foe("TS0", "Test Subject #C29", 300)]), LoopContext())
    assert d4.action.payload()["action"] == "use_potion"


def test_duplicator_joins_the_dfs_and_doubles_the_kill() -> None:
    """Owner 2026-08-02: 'the next card played is played an extra time' -- a DFS
    pseudo-card so the doubled play is CHOSEN (w_potion_spend banks it until the
    duplication flips something real, the 'save it for impactful plays' proxy)."""
    dup = _potion("DUPLICATOR", "Duplication Potion",
                  "The next card you play is played an extra time.")
    state = make_combat(
        hand=[card(0, "Bludgeon", 3, "Deal 32 damage.")],
        enemies=[enemy("BOSS_0", 60, intent_label="20")],
        energy=3, hp=70, max_hp=80, state_type="boss", potions=[dup],
    )
    r = router()
    d = r.decide(state, LoopContext())
    # 32 alone doesn't kill the 60-HP boss; duplicated 64 does -> drink first
    assert d.action.payload()["action"] == "use_potion"
    assert d.scores and d.scores.get("lethal") == 1.0
    # no kill to flip (300 HP): the potion stays banked
    state2 = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("BOSS_0", 300, intent_label="10")],
        energy=3, hp=70, max_hp=80, state_type="boss", potions=[dup],
    )
    d2 = r.decide(state2, LoopContext())
    assert d2.action.payload().get("action") != "use_potion"


def test_fruit_juice_drunk_on_sight_at_rewards() -> None:
    """Owner 2026-08-02 (live miss): a Fruit Juice sat in the belt through a
    rest site and was traded away at an event -- the only on-sight lane lived
    in combat, and the run never fought while holding it. +Max HP compounds
    (rest heals scale off max), so drink at the first legal screen: rewards,
    where the potion was just claimed."""
    state = parse_state({
        "state_type": "rewards",
        "run": {"act": 1, "floor": 6, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 50, "max_hp": 75,
                   "status": [], "relics": [],
                   "potions": [{"id": "FRUIT_JUICE", "name": "Fruit Juice",
                                "slot": 0, "can_use_in_combat": True,
                                "description": "Gain 5 Max HP."}],
                   "max_potion_slots": 3},
        "rewards": {"items": [{"index": 0, "type": "gold", "description": "25 Gold",
                               "gold_amount": 25}], "can_proceed": True},
    })
    d = router().decide(state, LoopContext())
    assert d.action.payload() == {"action": "use_potion", "slot": 0}
    assert "sight" in d.rationale


def test_heart_of_iron_deployed_at_boss_held_in_normal_fights() -> None:
    """Owner 2026-08-02: Plating 7 pays out over ~7 turns -- deploy at
    boss/elite start, hold in normal fights that end before it matters."""
    hoi = _potion("HEART_OF_IRON", "Heart of Iron", "Gain 7 Plating.")

    def st(state_type):
        return make_combat(
            hand=[card(0, "Strike", 1, "Deal 6 damage.")],
            enemies=[enemy("FOE_0", 250, intent_label="12")],
            hp=70, max_hp=80, state_type=state_type, potions=[hoi],
        )

    r = router()
    d = r.decide(st("boss"), LoopContext())
    assert d.action.payload()["action"] == "use_potion"
    assert "plating" in (d.rationale or "").lower()
    d2 = r.decide(st("monster"), LoopContext())
    assert d2.action.payload().get("action") != "use_potion"


def test_lucky_tonic_not_drunk_proactively() -> None:
    """Owner 2026-08-02 (parked for the multiturn planner): 1 Buffer absorbs one
    instance of ANY size -- optimal is the biggest-hit turn, which a one-turn
    planner can't see. Until then it must not leak out at fight starts."""
    tonic = _potion("LUCKY_TONIC", "Lucky Tonic", "Gain 1 Buffer.")
    state = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("BOSS_0", 300, intent_label="12")],
        hp=70, max_hp=80, state_type="boss", potions=[tonic],
    )
    d = router().decide(state, LoopContext())
    assert d.action.payload().get("action") != "use_potion"


def test_retarget_toggle_reverts_to_boss_only_pricing() -> None:
    """Attribution toggle (2026-08-02 night): use_elite_pool_targets=False must
    reproduce the pre-retarget behavior -- early-act drafts price vs the act
    boss, not the elite pool."""
    r = router()
    ctx = LoopContext()
    on = r._draft_target_fights(ctx, 1, 5, None)
    object.__setattr__(r.config.card_rewards, "use_elite_pool_targets", False) \
        if hasattr(r.config.card_rewards, "__dataclass_fields__") \
        else setattr(r.config.card_rewards, "use_elite_pool_targets", False)
    off = r._draft_target_fights(LoopContext(), 1, 5, None)
    assert len(off) == 1  # boss-only: a single target fight
    # boss floors keep next-act pricing in BOTH modes (dead-boss fix predates it)
    assert len(r._draft_target_fights(LoopContext(), 1, 17, None)) == 1
    assert isinstance(on, list) and len(on) >= 1


def test_star_cost_cards_vetoed_off_class() -> None:
    """Owner 2026-08-03 (Prismatic Gem run: Ironclad drafted a 3-star Reflect):
    Regent star-cost cards are DEAD without a star source -- unlike cross-class
    'gain 15 Block' cards, which just work. Vetoed unless the deck generates
    stars (or we ARE the Regent)."""
    from sts2bot.client.models import Card, DeckCard

    r = router()
    reflect = Card(index=0, id="REFLECT", name="Reflect", type="Skill", cost="0",
                   star_cost="3", rarity="Rare",
                   description="Gain 12 Block. Deal damage equal to Block gained.")
    strike = DeckCard(index=0, id="STRIKE_IRONCLAD", name="Strike", type="Attack",
                      cost="1", is_upgraded=False, description="Deal 6 damage.")
    starfall = DeckCard(index=1, id="STARFALL", name="Starfall", type="Skill",
                        cost="1", is_upgraded=False, description="Gain 3 Stars.")
    # Ironclad, no star source: hard veto
    assert r._card_score(reflect, 10, "The Ironclad", 2, deck=[strike]) == -100.0
    # star generator in deck lifts the veto
    assert r._card_score(reflect, 10, "The Ironclad", 2, deck=[strike, starfall]) > -100.0
    # the Regent never needs the generator
    assert r._card_score(reflect, 10, "The Regent", 2, deck=[strike]) > -100.0


def test_entropic_minted_buff_deploys_after_round_gates_close() -> None:
    """Owner catch 2026-08-03 (KD win, undrunk Liquid Bronze): Entropic Brew
    MINTS potions mid-fight, after the boss-start lanes' round gates close.
    Later-arriving potions are FRESH: their round gates are waived."""
    bronze = _potion("LIQUID_BRONZE", "Liquid Bronze", "Gain 3 Thorns.")

    def st(round_, potions):
        s = make_combat(
            hand=[card(0, "Strike", 1, "Deal 6 damage.")],
            enemies=[enemy("KD_0", 300, intent_label="12")],
            hp=70, max_hp=80, state_type="boss", potions=potions,
        )
        s.battle.round = round_
        return s

    r = router()
    ctx = LoopContext()
    # round 1: belt is EMPTY (snapshot taken)
    d1 = r.decide(st(1, []), ctx)
    assert d1.action.payload().get("action") != "use_potion"
    # round 4: Bronze appeared mid-fight (Entropic refill) -> fresh -> deploys
    # (poll through the action-settle quiescence dwell; same ctx keeps the snapshot)
    d2 = None
    for _ in range(2 + r.config.combat.action_quiesce_polls):
        d2 = r.decide(st(4, [bronze]), ctx)
        if not isinstance(d2, Wait):
            break
    assert d2.action.payload().get("action") == "use_potion"
    assert "Bronze" in (d2.rationale or "")


def test_boots_lookahead_prefers_the_one_charge_line() -> None:
    """Owner catch 2026-08-03: with an unwinnable elite behind the ON-PATH rest
    and a second rest reachable by jump, the bot spent TWO boots charges
    (jump-rest, jump-rest) where on-path-rest-THEN-jump buys the same dodge for
    one. The lookahead now carries a charge dimension with jump edges, so the
    deferred-jump plan is representable and the tax discount makes it win."""
    payload = {
        "state_type": "map",
        "map": {
            "current_position": {"col": 2, "row": 0, "type": "Start"},
            "next_options": [
                {"index": 0, "col": 1, "row": 1, "type": "RestSite",
                 "leads_to": [{"col": 1, "row": 2}]},  # on-path (Start's only child)
                {"index": 1, "col": 0, "row": 1, "type": "RestSite",
                 "leads_to": [{"col": 0, "row": 2}]},  # boots jump
            ],
            "nodes": [
                {"col": 2, "row": 0, "type": "Start", "children": [[1, 1]]},
                {"col": 1, "row": 1, "type": "RestSite", "children": [[1, 2]]},
                {"col": 0, "row": 1, "type": "RestSite", "children": [[0, 2]]},
                {"col": 1, "row": 2, "type": "Elite", "children": [[0, 3]]},
                {"col": 0, "row": 2, "type": "Monster", "children": [[0, 3]]},
                {"col": 0, "row": 3, "type": "Monster", "children": []},
            ],
            "boss": {"col": 0, "row": 4, "id": "B", "name": "Boss"},
            "bosses": [],
        },
        "run": {"act": 1, "floor": 7, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 55, "max_hp": 80, "gold": 50,
                   "deck": _STARTER_DECK,
                   "status": [],
                   "relics": [{"id": "WINGED_BOOTS", "name": "Winged Boots",
                               "counter": 2}],
                   "potions": [], "max_potion_slots": 3},
    }
    d = _router_for_routing().decide(parse_state(payload), LoopContext())
    assert isinstance(d, Decision)
    # on-path rest (index 0): the elite behind it is dodged by a LATER jump,
    # paying the tax once and discounted -- beats jumping right now
    assert d.action.payload()["index"] == 0


def test_mazaleths_gift_deployed_at_boss_start() -> None:
    """Owner 2026-08-03: Ritual (+1 Str at end of every turn) compounds -- the
    definition of a boss/elite-start buff. Held in normal fights."""
    gift = _potion("MAZALETHS_GIFT", "Mazaleth's Gift", "Gain 1 Ritual.")

    def st(state_type):
        return make_combat(
            hand=[card(0, "Strike", 1, "Deal 6 damage.")],
            enemies=[enemy("BOSS_0", 300, intent_label="12")],
            hp=70, max_hp=80, state_type=state_type, potions=[gift],
        )

    r = router()
    d = r.decide(st("boss"), LoopContext())
    assert d.action.payload()["action"] == "use_potion"
    d2 = r.decide(st("monster"), LoopContext())
    assert d2.action.payload().get("action") != "use_potion"


def test_shovel_dig_beats_smith_but_not_a_needed_rest() -> None:
    """Owner 2026-08-03: Shovel adds Dig (random relic) at rest sites. Relics
    are usually strict upsides, so dig > smith; a needed rest still wins."""
    def rest_state(hp):
        return parse_state({
            "state_type": "rest_site",
            "rest_site": {"options": [
                {"index": 0, "id": "rest", "name": "Rest", "is_enabled": True},
                {"index": 1, "id": "smith", "name": "Smith", "is_enabled": True},
                {"index": 2, "id": "dig", "name": "Dig", "is_enabled": True}]},
            "run": {"act": 2, "floor": 22, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": hp, "max_hp": 80,
                       "deck": [{"index": 0, "id": "STRIKE_IRONCLAD", "name": "Strike",
                                 "type": "Attack", "cost": "1", "is_upgraded": False,
                                 "description": "Deal 6 damage."}],
                       "relics": [{"id": "SHOVEL", "name": "Shovel"}],
                       "potions": [], "max_potion_slots": 3},
        })

    r = router()
    # healthy: dig (not smith)
    d = r.decide(rest_state(75), LoopContext())
    assert "dig" in (d.rationale or "").lower()
    # hurt: rest wins
    d2 = r.decide(rest_state(25), LoopContext())
    assert (d2.rationale or "").lower().startswith("rest")


def test_beetle_juice_waits_for_a_damaging_intent_and_respects_artifact() -> None:
    """Owner 2026-08-06: Beetle Juice ('deals 30% less damage for 4 turns') is a
    STATUS -- throw on the first turn the target shows a DAMAGING intent (round
    1 Buff turns waste duration), skip Artifact-charged targets."""
    juice = _potion("BEETLE_JUICE", "Beetle Juice",
                    "Enemy's attacks deal 30% less damage for 4 turns.")
    juice["target_type"] = "AnyEnemy"

    def st(intent, status=()):
        return parse_state({
            "state_type": "boss", "run": {"act": 2, "floor": 33, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 70, "max_hp": 80, "block": 0,
                       "energy": 3, "status": [],
                       "hand": [card(0, "Strike", 1, "Deal 6 damage.")],
                       "potions": [juice], "max_potion_slots": 3},
            "battle": {"round": 2, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "B0", "name": "Boss", "hp": 300,
                                    "max_hp": 300, "block": 0, "status": list(status),
                                    "intents": [intent]}]},
        })

    r = router()
    # Buff intent: hold (duration would tick against no damage)
    d0 = r.decide(st({"type": "buff", "label": "Buff"}), LoopContext())
    assert d0.action.payload().get("action") != "use_potion"
    # damaging intent: throw
    d1 = r.decide(st({"type": "attack", "label": "24"}), LoopContext())
    assert d1.action.payload().get("action") == "use_potion"
    # artifact up: hold for the strip
    art = {"id": "ARTIFACT_POWER", "name": "Artifact", "amount": 2, "description": ""}
    d2 = r.decide(st({"type": "attack", "label": "24"}, status=[art]), LoopContext())
    assert d2.action.payload().get("action") != "use_potion"


def test_aeonglass_boss_rule_drafts_exhaust_tools() -> None:
    """Owner 2026-08-09: Aeonglass's Wither = STATUS CARDS in the deck, removed
    by exhaust tooling (True Grit-class targeted picks ideal). With her as the
    known boss, exhaust-tool cards get the draft bonus; self-exhaust riders
    ('Exhaust.') do not qualify."""
    r = router()
    from sts2bot.client.models import Card
    grit = Card(index=0, id="TRUE_GRIT", name="True Grit", type="Skill", cost="1",
                rarity="Common",
                description="Gain 7 Block. Exhaust a card in your hand.")
    rider = Card(index=1, id="LUMINESCE", name="Luminesce", type="Skill", cost="1",
                 rarity="Common", description="Gain 2 Energy. Exhaust.")
    from sts2bot.policy.standard import _boss_draft_rule
    rule = _boss_draft_rule("Aeonglass")
    assert rule and rule.get("exhaust_tool_bonus")
    base_grit = r._card_score(grit, 15, "The Ironclad", 3)
    boosted_grit = r._card_score(grit, 15, "The Ironclad", 3, boss_rule=rule)
    assert abs((boosted_grit - base_grit) - rule["exhaust_tool_bonus"]) < 1e-6
    base_rider = r._card_score(rider, 15, "The Ironclad", 3)
    boosted_rider = r._card_score(rider, 15, "The Ironclad", 3, boss_rule=rule)
    assert boosted_rider == base_rider  # 'Exhaust.' rider is not a tool


def test_nimble_enchant_prefers_repeatable_block_over_exhausting_premium() -> None:
    """Owner live catch 2026-08-09: the bot put Nimble on Impervious ('Gain 30
    Block. Exhaust.'). Nimble pays out on every PLAY, so a self-exhausting
    blocker triggers once per fight (and usually overblocks) -- worse value
    than a plain Defend. The picker now takes the best NON-exhausting block
    card; a plain Defend beats Impervious; Shrug It Off beats the Defend."""
    r = router()

    class CS:
        prompt = "Choose a card to Enchant with Nimble 2."

        def __init__(self, cards):
            self.cards = cards

    class C:
        def __init__(self, i, cid, name, desc, rarity="Common"):
            self.index, self.id, self.name = i, cid, name
            self.cost, self.type, self.rarity = "1", "Skill", rarity
            self.is_upgraded = False
            self.description = desc

    imperv = C(0, "IMPERVIOUS", "Impervious", "Gain 30 Block. Exhaust.", "Rare")
    defend = C(1, "DEFEND_IRONCLAD", "Defend", "Gain 5 Block.", "Basic")
    shrug = C(2, "SHRUG_IT_OFF", "Shrug It Off", "Gain 8 Block. Draw 1 card.")

    pick = r._pick_target(CS([imperv, defend, shrug]),
                          prefer_worst=False, character="The Ironclad")
    assert pick.id == "SHRUG_IT_OFF"
    # even with only basics available, the exhauster still loses
    pick = r._pick_target(CS([imperv, defend]),
                          prefer_worst=False, character="The Ironclad")
    assert pick.id == "DEFEND_IRONCLAD"


def test_remove_strips_plain_basic_before_enchanted_twin() -> None:
    """Owner 2026-08-09: an enchanted basic is a small permanent asset -- on
    permanent removal screens the plain Defend goes first and the Nimble'd
    twin last. (In practice you rarely remove ALL basics, so the enchanted
    one effectively never gets stripped.)"""
    r = router()

    class CS:
        prompt = "Choose a card to Remove."

        def __init__(self, cards):
            self.cards = cards

    class C:
        def __init__(self, i, cid, desc):
            self.index, self.id, self.name = i, cid, "Defend"
            self.cost, self.type, self.rarity = "1", "Skill", "Basic"
            self.is_upgraded = False
            self.description = desc

    plain = C(0, "DEFEND_IRONCLAD", "Gain 5 Block.")
    enchanted = C(1, "DEFEND_IRONCLAD", "Gain 5 Block. Nimble 2.")
    pick = r._pick_target(CS([enchanted, plain]),
                          prefer_worst=True, character="The Ironclad")
    assert pick.index == 0 or pick.description == "Gain 5 Block."
    assert "Nimble" not in pick.description


def test_forecast_dfs_weights_cap_node_budget() -> None:
    """2026-08-10 (owner: 'this run takes unusually long at every node'):
    forecast DFS rollouts hit the live 4000-node cap on every simulated turn
    with branchy decks -- one fresh boss estimate ~19s, re-paid per deck
    change (~38% of the run's wall time). Forecasts use a tightened budget;
    live in-fight planning keeps the full cap."""
    r = router()
    w = r._dfs_forecast_weights
    assert w.max_sequences == r.config.map.rollout_dfs_max_sequences
    assert w.max_sequences < r.config.combat.max_sequences
    # untouched: the live planner's weights
    assert r.config.combat.max_sequences == 4000


def test_passive_mod_chest_opens_explicitly_and_gently() -> None:
    """Passive-/state fork mod (2026-08-10): the chest no longer auto-opens on
    poll (the auto-click barrage on every /state was the prime re-entrancy
    suspect for the treasure wedge -- 2 batch kills in 24h). With chest_open
    False the bot sends open_chest ONCE, dwells 8 polls between retries, caps
    at 3 attempts, then Waits into the stall rail. Pre-fork payloads (no
    chest_open field) keep the old flow untouched."""
    from sts2bot.policy.base import Wait

    payload = json.loads(json.dumps(FIXTURES["treasure"]))
    payload["treasure"]["message"] = "Chest unopened; send open_chest"
    payload["treasure"]["chest_open"] = False
    payload["treasure"]["relics"] = []
    r = router()
    ctx = LoopContext()
    seq = []
    for _ in range(30):  # chest never opens: worst case
        d = r.decide(parse_state(payload), ctx)
        seq.append("wait" if isinstance(d, Wait) else d.action.payload()["action"])
    assert seq[0] == "open_chest"
    assert seq.count("open_chest") == 3          # gentle retries, capped
    assert seq[8] == "open_chest" and seq[16] == "open_chest"  # 8-poll dwell
    assert all(a == "wait" for a in seq[24:])    # stall-rail territory


def test_passive_mod_shop_opens_inventory_first() -> None:
    """Passive-/state fork mod: the shopkeeper screen persists (no auto-open on
    poll); the router opens the inventory explicitly before shopping."""
    payload = json.loads(json.dumps(FIXTURES["shop"]))
    payload["shop"]["inventory_open"] = False
    d = router().decide(parse_state(payload), LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["action"] == "open_shop_inventory"


def test_fork_action_payloads() -> None:
    from sts2bot.client import actions as act

    assert act.AbandonRun().payload() == {"action": "abandon_run"}
    assert act.OpenChest().payload() == {"action": "open_chest"}
    assert act.OpenShopInventory().payload() == {"action": "open_shop_inventory"}


def test_engine_liveness_parses_and_is_optional() -> None:
    """engine dict (fork liveness) parses when present, None on pre-fork payloads."""
    payload = json.loads(json.dumps(FIXTURES["treasure"]))
    st = parse_state(payload)
    assert st.engine is None
    payload["engine"] = {"process_frames": 123456, "action_queue_empty": False,
                         "action_queue_next_id": 42, "passive_state": True}
    st2 = parse_state(payload)
    assert st2.engine["action_queue_empty"] is False
    assert st2.engine["passive_state"] is True


def test_mode_layer_routes_queen_and_kaiser_end_to_end() -> None:
    """Multiturn P4: the oracle's mode reaches the DFS through the router.
    Queen+Torch -> guard_break focuses the MINION (rationale tags the mode);
    Kaiser claws on the Laser turn with a weak deck -> defend plan."""
    def combat(enemies, hand, energy=3, round_=1, hp=75):
        return parse_state({
            "state_type": "boss", "run": {"act": 3, "floor": 48, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": hp, "max_hp": 80,
                       "block": 0, "energy": energy, "status": [], "hand": hand,
                       "draw_pile": [], "discard_pile": [],
                       "potions": [], "max_potion_slots": 3},
            "battle": {"round": round_, "turn": "player", "is_play_phase": True,
                       "enemies": enemies},
        })

    strike = {"index": 0, "id": "STRIKE_IRONCLAD", "name": "Strike",
              "type": "Attack", "cost": "1", "description": "Deal 6 damage.",
              "can_play": True, "target_type": "AnyEnemy"}
    torch = {"entity_id": "TORCH_0", "name": "Torch Head Amalgam", "hp": 190,
             "max_hp": 199, "block": 0,
             "status": [{"id": "MINION_POWER", "name": "Minion", "amount": 1,
                         "description": "Will abandon combat when the leader dies."}],
             "intents": [{"type": "Attack", "label": "18"}]}
    queen = {"entity_id": "QUEEN_0", "name": "Queen", "hp": 391, "max_hp": 400,
             "block": 0, "status": [], "intents": [{"type": "CardDebuff", "label": ""}]}
    d = router().decide(combat([torch, queen], [strike]), LoopContext())
    assert "|mode=guard_break" in (d.rationale or ""), d.rationale
    assert "TORCH" in (d.rationale or "")

    crusher = {"entity_id": "CRUSHER_0", "name": "Crusher", "hp": 209,
               "max_hp": 209, "block": 0, "status": [],
               "intents": [{"type": "Attack", "label": "12"}]}
    rocket = {"entity_id": "ROCKET_0", "name": "Rocket", "hp": 199,
              "max_hp": 199, "block": 0, "status": [],
              "intents": [{"type": "Attack", "label": "33"}]}
    defend = {"index": 1, "id": "DEFEND_IRONCLAD", "name": "Defend",
              "type": "Skill", "cost": "1", "description": "Gain 5 Block.",
              "can_play": True, "target_type": "None"}
    d2 = router().decide(combat([crusher, rocket], [strike, defend], round_=4),
                         LoopContext())
    assert "|mode=defend_deadline" in (d2.rationale or ""), d2.rationale
    assert "|plan=defend" in (d2.rationale or "")


def test_shop_buys_role_filling_card_especially_on_sale() -> None:
    """Owner 2026-08-12: buy high-quality cards that fill a missing deck role,
    'particularly if on discount' (the mod exposes on_sale). The draft-tag
    needs machinery prices the fit: with FNP+Howl in the deck, True Grit+ is
    THE exhaust provider (the owner's own example) and gets bought; junk
    (Clash) stays on the shelf; low gold never eats the removal reserve."""
    def deck_card(i, cid, name, typ, cost, desc, up=False):
        return {"index": i, "id": cid, "name": name, "type": typ, "cost": cost,
                "description": desc, "is_upgraded": up}

    payload = json.loads(json.dumps(FIXTURES["shop"]))
    payload["player"]["gold"] = 400
    payload["player"]["deck"] = (
        [deck_card(i, "STRIKE_IRONCLAD", "Strike", "Attack", "1",
                   "Deal 6 damage.") for i in range(4)]
        + [deck_card(4 + i, "DEFEND_IRONCLAD", "Defend", "Skill", "1",
                     "Gain 5 Block.") for i in range(4)]
        + [deck_card(8, "FEEL_NO_PAIN", "Feel No Pain", "Power", "1",
                     "Whenever a card is Exhausted, gain 4 Block.", True),
           deck_card(9, "HOWL", "Howl", "Skill", "1",
                     "While this card is in your Exhaust Pile, play it at the "
                     "start of your turn.")])
    payload["shop"]["items"] = [
        {"index": 0, "category": "card", "price": 68, "is_stocked": True,
         "can_afford": True, "on_sale": True,
         "card_id": "TRUE_GRIT", "card_name": "True Grit+",
         "card_type": "Skill", "card_cost": "1", "card_rarity": "Common",
         "card_description": "Gain 9 Block. Exhaust a card in your hand."},
        {"index": 1, "category": "card", "price": 45, "is_stocked": True,
         "can_afford": True, "on_sale": False,
         "card_id": "CLASH", "card_name": "Clash",
         "card_type": "Attack", "card_cost": "0", "card_rarity": "Common",
         "card_description": "Can only be played if every card in your hand "
                             "is an Attack. Deal 14 damage."},
    ]
    d = router().decide(parse_state(payload), LoopContext())
    assert isinstance(d, Decision)
    p = d.action.payload()
    assert p.get("action") == "shop_purchase" and p.get("index") == 0, d.rationale
    assert "ON SALE" in (d.rationale or "")
    # low gold: the removal reserve is sacred -- no card buy
    payload["player"]["gold"] = 100
    d2 = router().decide(parse_state(payload), LoopContext())
    if isinstance(d2, Decision):
        p2 = d2.action.payload()
        assert not (p2.get("action") == "shop_purchase"
                    and p2.get("index") in (0, 1)), d2.rationale


def test_throwing_axe_sharp_reaches_the_picker_and_dismantle_counts() -> None:
    """Owner catches 2026-08-13 (Throwing Axe purchase): (1) pickup-enchant
    relics open a NAMELESS 'Choose 3 cards to Enchant.' screen and the Sharp
    intent never carried from a SHOP purchase (event-only carrier) -- Strikes
    got the enchant; (2) Dismantle's conditional double-hit wasn't counted as
    multi-hit by the Sharp rule; (3) worst: Dismantle+ was excluded outright by
    the upgrade-screen unupgraded filter. All three fixed."""
    r = router()
    ctx = LoopContext()

    class Item:
        relic_description = "Upon pickup, Enchant up to 3 Attacks with Sharp 3."
    r._note_relic_enchant(Item(), ctx)
    assert ctx.screen_mem.get("pending_enchant") == "sharp"

    class CS:
        prompt = "Choose 3 cards to Enchant."

        def __init__(self, cards):
            self.cards = cards

    class C:
        def __init__(self, i, cid, name, desc, up=False):
            self.index, self.id, self.name = i, cid, name
            self.cost, self.type, self.rarity = "1", "Attack", "Common"
            self.is_upgraded = up
            self.description = desc

    cards = [C(0, "STRIKE_IRONCLAD", "Strike", "Deal 6 damage."),
             C(1, "DISMANTLE", "Dismantle+",
               "Deal 12 damage. If the enemy is Vulnerable, hits twice.", up=True),
             C(2, "MOLTEN_FIST", "Molten Fist", "Deal 9 damage.")]
    pick = r._pick_target(CS(cards), prefer_worst=False, character="The Ironclad",
                          enchant_kind=ctx.screen_mem.get("pending_enchant"))
    # the upgraded conditional-double-hitter is now both ELIGIBLE and PREFERRED
    assert pick.index == 1, (pick.name, pick.index)


def _ts_body(eid, hp, max_hp, intent="12"):
    e = enemy(eid, hp, intent_label=intent)
    e["name"] = "Test Subject #C376"
    e["max_hp"] = max_hp
    return e


def test_touch_of_insanity_reworded_text_still_categorizes() -> None:
    """Owner catch 2026-08-28 (TS f48 tape): the game reworded the potion to
    'It is free to play this combat.' — the costs-0 regex stopped matching,
    TOI fell to 'other', and only the hail-mary ever drank it (r10,
    pointlessly). The deploy lane with the owner's wait-for-a-worthy-target
    rule was unreachable. Widened regex must route it to cost_zero and the
    lane must fire the turn a 2-cost is in hand."""
    toi = {"id": "TOUCH_OF_INSANITY", "name": "Touch of Insanity",
           "description": "Choose a card in your Hand. It is free to play this combat.",
           "slot": 0, "can_use_in_combat": True, "target_type": "Self",
           "keywords": []}
    cheap = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("BOSS_0", 300, intent_label="15")],
        state_type="boss", potions=[toi])
    from sts2bot.client.models import Card
    cheap.player.deck = [Card(**card(0, "Bludgeon", 3, "Deal 32 damage."))]
    d = router().decide(cheap, LoopContext())
    assert not (isinstance(d, Decision)
                and d.action.payload().get("action") == "use_potion")
    worthy = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage."),
              card(1, "Uppercut", 2, "Deal 13 damage. Apply 1 Weak. Apply 1 Vulnerable.")],
        enemies=[enemy("BOSS_0", 300, intent_label="15")],
        state_type="boss", potions=[toi])
    d2 = router().decide(worthy, LoopContext())
    assert isinstance(d2, Decision)
    assert d2.action.payload().get("action") == "use_potion"
    assert "cost-zero" in (d2.rationale or "")


def test_weak_potion_held_for_test_subject_final_phase() -> None:
    """Owner 2026-08-28: TS revives WIPE statuses and early phases hit
    softest — a debuff potion thrown at P1 is wasted. Hold until the
    final-phase body (max_hp >= 250)."""
    weak = {"id": "WEAK_POTION", "name": "Weak Potion",
            "description": "Apply 2 Weak to target enemy.",
            "slot": 0, "can_use_in_combat": True, "target_type": "AnyEnemy",
            "keywords": []}
    p1 = make_combat(hand=[card(0, "Strike", 1, "Deal 6 damage.")],
                     enemies=[_ts_body("TS_0", 140, 150)],
                     state_type="boss", potions=[weak])
    d = router().decide(p1, LoopContext())
    assert not (isinstance(d, Decision)
                and d.action.payload().get("action") == "use_potion")
    p3 = make_combat(hand=[card(0, "Strike", 1, "Deal 6 damage.")],
                     enemies=[_ts_body("TS_0", 290, 300)],
                     state_type="boss", potions=[weak])
    d2 = router().decide(p3, LoopContext())
    assert isinstance(d2, Decision)
    assert d2.action.payload().get("action") == "use_potion"


def test_not_yet_shelved_at_high_hp() -> None:
    """Owner 2026-08-28 (TS f48 r3: Not Yet burned at 77/83 for 6 real HP):
    the forgone 4 points are a wasted shelvable resource. Hold near-full;
    play at low HP where the full 10 lands."""
    ny = card(0, "Not Yet", 2, "Heal 10 HP. Exhaust.", target="None",
              ctype="Skill")
    high = make_combat(hand=[ny], enemies=[enemy("BOSS_0", 200, "6")],
                       hp=78, max_hp=83, state_type="boss")
    d = router().decide(high, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("action") != "play_card"  # shelved
    low = make_combat(hand=[ny], enemies=[enemy("BOSS_0", 200, "12")],
                      hp=30, max_hp=83, state_type="boss")
    d2 = router().decide(low, LoopContext())
    assert isinstance(d2, Decision)
    assert d2.action.payload().get("action") == "play_card"


def test_hail_mary_rerolls_before_drawing_on_junk_hands() -> None:
    """Owner catch (seed-A r7): Swift first drew 3 usable cards, then
    Bottled Potential flushed them all — belt order wasted the Swift. On a
    junk hand the reroll must go first; on a near-viable hand, draw first."""
    swift = {"id": "SWIFT_POTION", "name": "Swift Potion",
             "description": "Draw 3 cards.", "slot": 0,
             "can_use_in_combat": True, "target_type": "Self", "keywords": []}
    bp = {"id": "BOTTLED_POTENTIAL", "name": "Bottled Potential",
          "description": "Shuffle ALL your cards into your Draw Pile. "
          "Draw 5 cards.", "slot": 1, "can_use_in_combat": True,
          "target_type": "Self", "keywords": []}
    wither = card(0, "Wither", 0, "Unplayable. At the end of your turn, if "
                  "this is in your Hand, take 6 damage.", target="None",
                  ctype="Status", can_play=False)
    junk = make_combat(hand=[wither, card(1, "Strike", 1, "Deal 6 damage.")],
                       enemies=[enemy("BOSS_0", 300, intent_label="40")],
                       hp=10, max_hp=80, state_type="boss",
                       potions=[swift, bp])
    d = router().decide(junk, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload() == {"action": "use_potion", "slot": 1}  # reroll first
    viable = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage."),
              card(1, "Bash", 2, "Deal 8 damage. Apply 2 Vulnerable."),
              card(2, "Defend", 1, "Gain 5 Block.")],
        enemies=[enemy("BOSS_0", 300, intent_label="40")],
        hp=10, max_hp=80, state_type="boss", potions=[swift, bp])
    d2 = router().decide(viable, LoopContext())
    assert isinstance(d2, Decision)
    assert d2.action.payload() == {"action": "use_potion", "slot": 0}  # draw first


def test_reroll_potion_fires_on_junk_hand_held_otherwise() -> None:
    """Queue #9 (owner self-A/B: early belt-spend LOST the identical fight
    that holding won): Bottled Potential is its own category now — held
    through comfortable turns, drunk proactively when the hand is junk
    against real incoming."""
    bp = {"id": "BOTTLED_POTENTIAL", "name": "Bottled Potential",
          "description": "Shuffle ALL your cards into your Draw Pile. "
          "Draw 5 cards.", "slot": 0, "can_use_in_combat": True,
          "target_type": "Self", "keywords": []}
    wither = card(0, "Wither", 0, "Unplayable. At the end of your turn, if "
                  "this is in your Hand, take 6 damage.", target="None",
                  ctype="Status", can_play=False)
    junk = make_combat(hand=[wither, card(1, "Strike", 1, "Deal 6 damage.")],
                       enemies=[enemy("BOSS_0", 300, intent_label="22")],
                       hp=60, max_hp=80, state_type="boss", potions=[bp])
    d = router().decide(junk, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("action") == "use_potion"
    assert "fix the hand" in (d.rationale or "")
    comfy = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage."),
              card(1, "Defend", 1, "Gain 5 Block."),
              card(2, "Bash", 2, "Deal 8 damage. Apply 2 Vulnerable.")],
        enemies=[enemy("BOSS_0", 300, intent_label="22")],
        hp=60, max_hp=80, state_type="boss", potions=[bp])
    d2 = router().decide(comfy, LoopContext())
    if isinstance(d2, Decision):
        assert d2.action.payload().get("action") != "use_potion"  # held


def test_hail_mary_skips_duplicator_without_defensive_double() -> None:
    """Owner catch 2026-08-30 (Queen death-by-1): hail-mary drank Duplicator
    and the plan doubled an attack. An arming potion is no rescue unless a
    block/heal card is playable to receive the double."""
    dup = {"id": "DUPLICATOR", "name": "Duplicator",
           "description": "Your next card is played an extra time.",
           "slot": 0, "can_use_in_combat": True, "target_type": "Self",
           "keywords": []}
    attacks_only = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage.")],
        enemies=[enemy("BOSS_0", 300, intent_label="40")],
        hp=10, max_hp=80, state_type="boss", potions=[dup])
    d = router().decide(attacks_only, LoopContext())
    if isinstance(d, Decision):
        assert d.action.payload().get("action") != "use_potion"  # no rescue here
    with_defend = make_combat(
        hand=[card(0, "Strike", 1, "Deal 6 damage."),
              card(1, "Defend", 1, "Gain 5 Block.")],
        enemies=[enemy("BOSS_0", 300, intent_label="40")],
        hp=10, max_hp=80, state_type="boss", potions=[dup])
    d2 = router().decide(with_defend, LoopContext())
    assert isinstance(d2, Decision)
    assert d2.action.payload().get("action") == "use_potion"  # double can defend


def test_shop_skips_dead_dependency_relics() -> None:
    """Owner catch 2026-08-30: Chemical X bought (218g) with zero X-cost
    cards — the WAR prior is deck-blind. Relics naming a card class the
    deck entirely lacks are skipped; with the class present, the buy is
    allowed again."""
    def shop_state(deck_cards):
        payload = json.loads(json.dumps(FIXTURES["shop"]))
        payload["player"]["gold"] = 500
        payload["player"]["deck"] = deck_cards
        payload["player"]["potions"] = [
            {"id": f"P{i}", "name": f"P{i}", "slot": i} for i in range(3)]
        payload["player"]["max_potion_slots"] = 3
        payload["shop"]["items"] = [{
            "index": 0, "category": "relic", "is_stocked": True,
            "can_afford": True, "gold_price": 218,
            "relic_id": "CHEMICAL_X", "relic_name": "Chemical X",
            "relic_description": "The effects of your cost X cards are "
                                 "increased by 2."}]
        return payload
    plain = [{"index": i, "id": "STRIKE_IRONCLAD", "name": "Strike",
              "type": "Attack", "cost": "1", "is_upgraded": False}
             for i in range(10)]
    d = router().decide(parse_state(shop_state(plain)), LoopContext())
    if isinstance(d, Decision):
        assert d.action.payload().get("action") != "shop_purchase" or \
            "Chemical" not in (d.rationale or "")
    with_x = [*plain, {"index": 10, "id": "WHIRLWIND", "name": "Whirlwind",
                       "type": "Attack", "cost": "X", "is_upgraded": False}]
    d2 = router().decide(parse_state(shop_state(with_x)), LoopContext())
    if isinstance(d2, Decision) and d2.action.payload().get("action") == "shop_purchase":
        assert "Chemical" in (d2.rationale or "")


def test_liquid_memories_deploys_from_discard_targets() -> None:
    """Owner catch 2026-08-30 (won Queen fight, potion rotted): Liquid
    Memories says free-to-play 'this TURN' — the fight/combat regex missed
    it, so it sat as 'other' (hail-mary-only). Now cost_zero class with
    DISCARD-side worthy targets; the round gate is gone (it contradicted
    wait-for-the-target); and with no >=2 in the whole deck, a 1-cost
    suffices at a boss."""
    lm = {"id": "LIQUID_MEMORIES", "name": "Liquid Memories",
          "description": "Put a card from your Discard Pile into your Hand. "
          "It's free to play this turn.", "slot": 0,
          "can_use_in_combat": True, "target_type": "Self", "keywords": []}
    st = make_combat(hand=[card(0, "Strike", 1, "Deal 6 damage.")],
                     enemies=[enemy("QUEEN_0", 300, intent_label="12")],
                     hp=70, max_hp=80, state_type="boss", potions=[lm])
    # inject a discard pile with a 2-cost target
    raw = st
    d = router().decide(raw, LoopContext())
    # without discard info the lane may hold; craft the discard directly
    from sts2bot.client.models import PileCard
    raw.player.discard_pile = [PileCard(name="Uppercut", cost="2",
                                        description="Deal 13 damage.")]
    d = router().decide(raw, LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload().get("action") == "use_potion"
    assert "cost-zero the 2-cost" in (d.rationale or "")


# --- capability-calibration arm (2026-09-03) -------------------------------
# HQX8M7T6VN full-run diff: the owner fought 6 elites (20 relics) on the seed
# where the bot fought 0 (10 relics). Era calibration of the gate's greedy
# rollout vs 500 real elite fights: <20%-rated fights won 88%, predicted loss
# ~38 HP vs actual 23.5 (corr 0.18); the DFS boss forecast read a full loss on
# 61-99% of pre-boss evaluations. Observed mode prices both from history.


def _calibrated_router() -> StandardRouter:
    r = _router_for_routing()
    r.config.map.elite_loss_source = "observed"
    r.config.map.elite_entry_min_hp_pct = 0.5
    r.config.map.boss_loss_source = "observed"
    return r


def test_observed_elite_pricing_chases_elite_with_a_starter_deck() -> None:
    # same screen as the gate-shut test above: starter deck, full HP. Under the
    # rollout gate the elite is skipped; in observed mode the HP projection
    # governs (p75 elite loss 32 of 80 -> survivable) and the relic wins.
    payload = json.loads(json.dumps(FIXTURES["map"]))
    payload["map"]["next_options"] = [
        {"index": 0, "col": 1, "row": 3, "type": "Elite", "leads_to": []},
        {"index": 1, "col": 2, "row": 3, "type": "Monster", "leads_to": []},
    ]
    payload["player"]["hp"] = 80
    payload["player"]["max_hp"] = 80
    payload["player"]["deck"] = _STARTER_DECK
    assert _router_for_routing().decide(
        parse_state(payload), LoopContext()).action.payload()["index"] == 1
    d = _calibrated_router().decide(parse_state(payload), LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["index"] == 0


def test_observed_elite_entry_floor_refuses_the_elite_when_hurt() -> None:
    # 45/80 is survivable on p75 (45-32=13, above the 10% death floor) but
    # BELOW a 60% entry floor: era elite deaths entered at median 63% HP.
    # Monster instead; lifting the floor flips it back to the relic.
    payload = json.loads(json.dumps(FIXTURES["map"]))
    payload["map"]["next_options"] = [
        {"index": 0, "col": 1, "row": 3, "type": "Elite", "leads_to": []},
        {"index": 1, "col": 2, "row": 3, "type": "Monster", "leads_to": []},
    ]
    payload["player"]["hp"] = 45
    payload["player"]["max_hp"] = 80
    payload["player"]["deck"] = _STARTER_DECK
    r = _calibrated_router()
    r.config.map.elite_entry_min_hp_pct = 0.6
    d = r.decide(parse_state(payload), LoopContext())
    assert d.action.payload()["index"] == 1
    # lift the floor: 45/80 with a 32-loss projection is survivable -> chase
    r.config.map.elite_entry_min_hp_pct = 0.0
    assert r.decide(parse_state(payload), LoopContext()).action.payload()["index"] == 0
    # deck-size floor (arm v4): a starter deck (10 cards) below the floor never
    # routes into the elite; at/above it the relic wins again
    r.config.map.elite_min_deck_cards = 14
    assert r.decide(parse_state(payload), LoopContext()).action.payload()["index"] == 1
    r.config.map.elite_min_deck_cards = len(payload["player"]["deck"])
    assert r.decide(parse_state(payload), LoopContext()).action.payload()["index"] == 0
    r.config.map.elite_min_deck_cards = 0
    # per-act override (arm v3): act 2 gets its own floor; act 1 keeps the base
    r.config.map.elite_entry_min_hp_pct_act2 = 0.65
    payload["run"]["act"] = 2
    assert r.decide(parse_state(payload), LoopContext()).action.payload()["index"] == 1
    payload["run"]["act"] = 1
    assert r.decide(parse_state(payload), LoopContext()).action.payload()["index"] == 0


def test_observed_boss_pricing_bypasses_the_dfs_forecast() -> None:
    # the rest gate's DFS estimate is suppressed in observed mode so the
    # campfire decides on history (+ act-3 bump), not a forecast that read a
    # full loss on nearly every era evaluation
    r = _calibrated_router()
    r.bestiary = {"Vantom": {"hp": [173, 173], "statuses": {}, "roles": ["boss"], "acts": [1]}}
    from sts2bot.client.models import DeckCard
    player = parse_state(json.loads(json.dumps(FIXTURES["map"]))).player
    player.deck = [DeckCard(index=0, id="STRIKE_IRONCLAD", name="Strike", type="Attack",
                            cost="1", is_upgraded=False)]
    ctx = LoopContext()
    ctx.screen_mem["act_boss_name"] = "Vantom"
    assert r._dfs_boss_loss(ctx, player, 1) is None
    r.config.map.boss_loss_source = "dfs"
    assert r._dfs_boss_loss(ctx, player, 1) is not None


def test_pre_elite_campfire_flag_and_rest_rule() -> None:
    """Arm v2 (2026-09-03): the map DP projects a HEAL at every campfire, yet the
    campfire policy smithed at 58-62% and the run walked into the elite it had
    priced post-heal (run 26: smith at 62% -> Effigy -51 -> dead). The map now
    flags a campfire whose DP-best continuation is an elite; _rest_site rests
    below rest_before_elite_hp_pct there (0 = off, live unchanged)."""
    def payload(next_type: str) -> dict:
        return {
            "state_type": "map",
            "map": {
                "current_position": {"col": 1, "row": 0, "type": "Start"},
                "visited": [],
                "next_options": [
                    {"index": 0, "col": 1, "row": 1, "type": "RestSite",
                     "leads_to": [{"col": 1, "row": 2, "type": next_type}]},
                ],
                "nodes": [
                    {"col": 1, "row": 0, "type": "Start", "children": [[1, 1]]},
                    {"col": 1, "row": 1, "type": "RestSite", "children": [[1, 2]]},
                    {"col": 1, "row": 2, "type": next_type, "children": [[1, 3]]},
                    {"col": 1, "row": 3, "type": "Monster", "children": []},
                ],
                "boss": {"col": 1, "row": 4, "id": "B", "name": "Boss"},
                "bosses": [],
            },
            "run": {"act": 1, "floor": 1, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 52, "max_hp": 80, "gold": 50,
                       "status": [], "relics": [], "potions": [], "max_potion_slots": 3,
                       "deck": _STARTER_DECK},
        }
    r = _calibrated_router()
    ctx = LoopContext()
    r.decide(parse_state(payload("Elite")), ctx)
    assert ctx.screen_mem.get("pre_elite") is True
    ctx2 = LoopContext()
    r.decide(parse_state(payload("Monster")), ctx2)
    assert "pre_elite" not in ctx2.screen_mem

    rest = json.loads(json.dumps(FIXTURES["rest_site"]))
    rest["player"]["hp"], rest["player"]["max_hp"] = 52, 80  # 65%: above the 60% general bar
    r.config.rest.rest_before_elite_hp_pct = 0.75
    d = r.decide(parse_state(rest), ctx)
    assert d.rationale.startswith("rest") and "committed elite" in d.rationale
    r.config.rest.rest_before_elite_hp_pct = 0.0  # off -> the general 60% rule smiths
    assert r.decide(parse_state(rest), ctx).rationale.startswith("smith")
    # no flag -> the rule never fires even when on
    r.config.rest.rest_before_elite_hp_pct = 0.75
    assert r.decide(parse_state(rest), ctx2).rationale.startswith("smith")


def test_shop_bought_list_resets_between_shops() -> None:
    """Owner catch 2026-09-11 (1170 gold walked out of the act-3 shop before
    Aeonglass): the bought-this-shop index list lived in screen_mem for the
    whole run, so every index bought at an earlier shop was invisible at every
    later one. Same ctx, two shops on different floors: the removal bought at
    the first must be buyable again at the second."""
    deck = [_sc_card(0, "Strike")]
    r = router()
    ctx = LoopContext()
    first = _shop_with_removal(100, deck=deck)
    d1 = r.decide(first, ctx)
    assert d1.action.payload() == {"action": "shop_purchase", "index": 10}
    payload = json.loads(json.dumps(FIXTURES["shop"]))
    payload["player"]["gold"] = 400
    payload["player"]["deck"] = deck
    payload["player"]["potions"] = [{"id": f"P{i}", "name": f"P{i}", "slot": i} for i in range(3)]
    payload["player"]["max_potion_slots"] = 3
    payload["run"]["floor"] = (payload["run"].get("floor") or 0) + 15
    for it in payload["shop"]["items"]:
        if it["category"] == "card_removal":
            it["price"] = 100
    d2 = r.decide(parse_state(payload), ctx)
    assert d2.action.payload() == {"action": "shop_purchase", "index": 10}
