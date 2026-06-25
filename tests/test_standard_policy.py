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
        pot(1, "FOUL_POTION", "Foul Potion", "Deal 12 damage to ALL (incl. you)."),  # downside
        pot(2, "STRENGTH_POTION", "Strength Potion", "Gain 2 Strength."),  # buff
    ]
    victim = router()._worst_potion(belt)
    assert victim is not None and victim.id == "FOUL_POTION"  # ditch the junk, keep Cure All


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
    assert abs(s(blk, 1) - s(blk, 3)) < 1e-6  # block skill gets none


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
    assert abs(s(plain, 1) - s(plain, 3)) < 1e-6  # a plain block skill does not


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
    r = StandardRouter(combat_stats=stats)
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
    deltas = r._capability_deltas(deck, [big, cantrip], 80, boss)
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
                "deck": _STRONG_DECK,  # can win the elite, so the gate is about HP, not deck power
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
    """8.1d: the same modest card (Common Skill, score 3.5 < base take_threshold 4.0) is TAKEN by a
    starter-heavy deck (a real card beats keeping a basic) but SKIPPED once the deck is polished.
    In the 0/5 batch the bot skipped good cards (Molten Fist x4) holding a 9-starter deck."""
    def reward(deck_ids):
        deck = [{"index": i, "id": cid, "name": cid.title(), "type": "Attack", "cost": "1",
                 "description": "Deal 6 damage.", "rarity": "Basic", "is_upgraded": False}
                for i, cid in enumerate(deck_ids)]
        return parse_state({
            "state_type": "card_reward",
            "card_reward": {"cards": [
                {"index": 0, "id": "MYSTERY_SKILL", "name": "Modest", "type": "Skill", "cost": "1",
                 "description": "A modest effect.", "rarity": "Common", "is_upgraded": False,
                 "keywords": []}], "can_skip": True},
            "run": {"act": 1, "floor": 5, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 70, "max_hp": 80, "deck": deck},
        })

    r = router()
    weak = ["STRIKE_IRONCLAD"] * 8 + ["DEFEND_IRONCLAD"] * 4   # 100% basic -> low bar
    polished = ["BASH"] * 12                                   # 0% basic -> full bar
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
    # now that 3 are picked, confirm
    assert r.decide(cardsel(), ctx).action.payload()["action"] == "confirm_selection"


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
    deltas = r._capability_deltas(deck, [multi, big], 80, slippery_boss)
    assert deltas[0] > deltas[1]  # multi-hit beats Slippery; the big swing is wasted
