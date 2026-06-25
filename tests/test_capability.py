"""Canonical race-model cases for the §5-C capability estimate (PLAN §5.1).

These encode the bestiary lessons the one-turn planner can't see (§8.4): Vantom's Slippery,
racing a leader past minions, Strength ramp out-scaling a slow deck. They are the spec — if the
model changes, change these with intent.
"""

from __future__ import annotations

from sts2bot.client.models import Card
from sts2bot.policy.capability import (
    DeckOutput,
    FightEnemy,
    FightOutcome,
    deck_output,
    detect_mechanics,
    estimate_fight,
)


def _st(name: str, desc: str) -> dict:
    return {"name": name, "description": desc}


def _card(name: str, type_: str, cost: int | str, desc: str) -> Card:
    return Card(index=0, name=name, type=type_, cost=str(cost), description=desc)


def _starter() -> list[Card]:
    return (
        [_card("Strike", "Attack", 1, "Deal 6 damage.") for _ in range(5)]
        + [_card("Defend", "Skill", 1, "Gain 5 Block.") for _ in range(4)]
        + [_card("Bash", "Attack", 2, "Deal 8 damage. Apply 2 Vulnerable.")]
    )


def _progress(o) -> float:
    return o.exp_end_hp - o.enemy_hp_left  # what §5-C drafting scores (progress even in a loss)


def test_strong_deck_clears_a_normal_with_hp_to_spare() -> None:
    deck = DeckOutput(burst_dmg=30, sustained_dmg=20, biggest_hit=15, block_per_turn=10)
    enemy = [FightEnemy(hp=46, dps=10)]
    out = estimate_fight(70, deck, enemy)
    assert out.win
    assert out.exp_end_hp >= 60  # a normal barely scratches a real deck


def test_weak_deck_cannot_close_vantom_slippery_and_loses() -> None:
    # Vantom (~173 HP) ramps Strength and is Slippery: the first hit each turn -> 1, so a
    # small-hit starter deck deals ~1/turn and never closes while Vantom out-paces it.
    vantom = [FightEnemy(hp=173, dps=28, str_ramp=4, slippery=True)]
    weak = DeckOutput(burst_dmg=10, sustained_dmg=8, biggest_hit=8, block_per_turn=5)
    out = estimate_fight(70, weak, vantom)
    assert not out.win


def test_slippery_guts_single_big_hit_but_not_multi_hit() -> None:
    # Same totals, opposite shape. Slippery drops the *largest* hit to 1, so a multi-hit deck
    # (small biggest_hit) gets most damage through; a one-big-swing deck is neutered.
    vantom = [FightEnemy(hp=173, dps=28, str_ramp=4, slippery=True)]
    multi = DeckOutput(burst_dmg=60, sustained_dmg=40, biggest_hit=12, block_per_turn=22)
    one_swing = DeckOutput(burst_dmg=60, sustained_dmg=40, biggest_hit=40, block_per_turn=22)
    assert estimate_fight(80, multi, vantom).win
    assert not estimate_fight(80, one_swing, vantom).win


def test_races_summoner_leader_past_its_minions() -> None:
    # Leader-kill ends the fight, so summoned minions add threat (dps) but not kill-HP. Racing
    # the 126-HP leader wins; if the minions *counted* toward the kill it would be unwinnable.
    deck = DeckOutput(burst_dmg=40, sustained_dmg=30, biggest_hit=18, block_per_turn=24)
    leader = FightEnemy(hp=126, dps=28, str_ramp=2)
    minions = [FightEnemy(hp=20, dps=4, counts_toward_kill=False) for _ in range(2)]
    raced = estimate_fight(80, deck, [leader, *minions])
    assert raced.win
    assert raced.exp_end_hp > 0

    # contrast: if every body counted toward the kill total, the same deck can't close in time
    minions_count = [FightEnemy(hp=20, dps=4, counts_toward_kill=True) for _ in range(2)]
    assert not estimate_fight(80, deck, [leader, *minions_count]).win


def test_strength_ramp_out_scales_a_slow_deck_but_not_a_fast_one() -> None:
    # "Close the leader before the ramp out-scales you." Same heavily-ramping leader; only the
    # deck that closes fast survives.
    leader = [FightEnemy(hp=80, dps=12, str_ramp=6)]
    slow = DeckOutput(burst_dmg=15, sustained_dmg=10, biggest_hit=10, block_per_turn=8)
    fast = DeckOutput(burst_dmg=40, sustained_dmg=35, biggest_hit=12, block_per_turn=8)
    assert not estimate_fight(70, slow, leader).win
    assert estimate_fight(70, fast, leader).win


def test_outcome_is_frozen_and_reports_turns() -> None:
    out = estimate_fight(70, DeckOutput(30, 20, 15, 10), [FightEnemy(hp=46, dps=10)])
    assert isinstance(out, FightOutcome)
    assert out.turns >= 1


def test_deck_output_reads_a_starter_deck() -> None:
    out = deck_output(_starter())
    assert out.biggest_hit == 8  # Bash, the deck's largest single hit
    assert out.block_per_turn > 0  # the Defends
    assert out.burst_dmg >= out.sustained_dmg > 0  # a peak turn beats the cycle average
    assert out.burst_dmg < 25  # but a starter has no real burst


def test_deck_output_biggest_hit_tracks_the_largest_attack() -> None:
    deck = [*_starter(), _card("Bludgeon", "Attack", 3, "Deal 32 damage.")]
    assert deck_output(deck).biggest_hit == 32


def test_deck_output_scales_with_strength() -> None:
    base = deck_output(_starter())
    buffed = deck_output(_starter(), strength=3)
    assert buffed.biggest_hit == base.biggest_hit + 3
    assert buffed.sustained_dmg > base.sustained_dmg
    assert buffed.burst_dmg > base.burst_dmg


def test_deck_output_heavy_clog_dilutes_sustained() -> None:
    # A few curses in a small energy-bound deck don't dent damage (you still draw enough to spend
    # your energy); but heavy clog makes *draw* the binding constraint and thins the output.
    clogged = [*_starter(), *(_card("Regret", "Curse", 0, "Unplayable.") for _ in range(12))]
    assert deck_output(clogged).sustained_dmg < deck_output(_starter()).sustained_dmg


def test_deck_output_feeds_the_race_end_to_end() -> None:
    # starter deck can't close Vantom (Slippery + ramp); a built deck clears a normal comfortably
    vantom = [FightEnemy(hp=173, dps=28, str_ramp=4, slippery=True)]
    assert not estimate_fight(70, deck_output(_starter()), vantom).win

    strong = [
        *_starter(),
        _card("Bludgeon", "Attack", 3, "Deal 32 damage."),
        _card("Twin Strike", "Attack", 1, "Deal 5 damage 2 times."),
        _card("Pommel Strike", "Attack", 1, "Deal 9 damage. Draw 1 card."),
        _card("Iron Wave", "Attack", 1, "Deal 5 damage. Gain 5 Block."),
    ]
    won = estimate_fight(70, deck_output(strong), [FightEnemy(hp=46, dps=10)])
    assert won.win
    assert won.exp_end_hp >= 60


def test_deck_output_credits_strength_and_vulnerable_from_text() -> None:
    # In-fight scaling read straight from card text (the Matriarch-win pessimism fix, PLAN §8.4).
    plain = deck_output([_card("Strike", "Attack", 1, "Deal 6 damage.")])
    assert plain.vuln_mult == 1.0 and plain.str_cap == 0.0
    vuln = deck_output([_card("Bash", "Attack", 2, "Deal 8 damage. Apply 2 Vulnerable.")])
    assert vuln.vuln_mult > 1.0  # the deck can apply Vulnerable -> damage multiplier
    strong = deck_output([_card("Inflame", "Power", 1, "Gain 2 Strength."),
                          _card("Strike", "Attack", 1, "Deal 6 damage.")])
    assert strong.str_cap == 2 and strong.str_per_turn > 0 and strong.hits_per_turn > 0


def test_vulnerable_multiplier_helps_close_the_race() -> None:
    # Same raw damage; the Vulnerable multiplier makes more progress (exp_end_hp - enemy_hp_left,
    # the metric drafting scores) — why the estimate stopped under-rating Bash decks.
    enemy = [FightEnemy(hp=90, dps=16)]
    base = DeckOutput(20, 15, 12, 8)
    vuln = DeckOutput(20, 15, 12, 8, vuln_mult=1.3)
    assert _progress(estimate_fight(70, vuln, enemy)) > _progress(estimate_fight(70, base, enemy))


def test_accumulating_strength_ramps_my_damage() -> None:
    # A Strength bonus that grows each turn adds to every hit -> a slow deck closes a long race
    # the flat sustained number says it can't (the Matriarch Str 3->8 ramp the estimate missed).
    enemy = [FightEnemy(hp=140, dps=16)]  # dps > block, so a slow close costs real HP
    flat = DeckOutput(14, 12, 8, 10)
    ramp = DeckOutput(14, 12, 8, 10, str_per_turn=1.0, hits_per_turn=2.0, str_cap=8)
    assert _progress(estimate_fight(70, ramp, enemy)) > _progress(estimate_fight(70, flat, enemy))


def test_detect_mechanics_from_real_status_text() -> None:
    # the descriptions are verbatim from data/bestiary.json (the mod's own rules text)
    assert detect_mechanics([_st("Hardened Shell", "Skulking Colony cannot lose more than 15 HP "
                                 "each turn.")]) == {"dmg_cap_per_turn": 15}
    assert detect_mechanics([_st("Hard to Kill", "Reduce all damage taken and HP lost by "
                                 "Exoskeleton to 9.")]) == {"dmg_cap_per_turn": 9}
    assert detect_mechanics([_st("Intangible", "Reduce all damage taken and HP loss to 1. Lasts "
                                 "for 1 turn.")]) == {"dmg_cap_per_turn": 1}
    assert detect_mechanics([_st("Plating", "At the end of your turn, gain 12 Block. Plating is "
                                 "reduced by 1 at the start of your turn.")]) == {"self_block": 12}
    assert detect_mechanics([_st("Steam Eruption", "When killed, deals 15 damage at the end of "
                                 "your next turn.")]) == {"death_damage": 15}
    assert detect_mechanics([_st("Plow", "The first time Ceremonial Beast's HP reaches 150 or "
                                 "below, it becomes Stunned and loses all its Strength.")]) == {
        "stun_threshold": 150}
    assert detect_mechanics([_st("Thorns", "When hit by an attack, deal 5 damage back.")]) == {
        "thorns": 5}
    assert detect_mechanics([_st("Ritual", "At the end of its turn, gains 2 Strength.")]) == {
        "str_ramp": 2}
    assert detect_mechanics([_st("Slippery", "The next time Inklet loses HP, it only loses 1 HP "
                                 "instead.")]) == {"slippery": True}


def test_detect_mechanics_ignores_conditional_one_offs_and_unknowns() -> None:
    # Crab Rage's Block/Strength are conditional on an *ally* dying, not per-turn -> not detected
    assert detect_mechanics([_st("Crab Rage", "When an ally dies, Crusher gains 6 Strength and 99 "
                                 "Block.")]) == {}
    assert detect_mechanics([_st("Surprise", "Something is off about this creature...")]) == {}
    assert detect_mechanics([]) == {}


def test_estimate_hard_cap_makes_a_winnable_fight_unwinnable() -> None:
    deck = DeckOutput(burst_dmg=40, sustained_dmg=30, biggest_hit=15, block_per_turn=5)
    assert estimate_fight(70, deck, [FightEnemy(hp=80, dps=14)]).win
    assert not estimate_fight(70, deck, [FightEnemy(hp=80, dps=14, dmg_cap_per_turn=8)]).win


def test_estimate_sandpit_timer_loses_a_slow_race() -> None:
    # The Insatiable's Sandpit (race-or-die). detect_mechanics parses the deadline; the estimate
    # pads it (+_SANDPIT_SLACK) for the Frantic Escapes the planner extends with. A slow deck that
    # out-races the HP-loss but can't *close* inside the window gets eaten; a burst deck survives.
    assert detect_mechanics([{"description": "In 4 turns, you will be eaten and die."}]) == {
        "death_timer": 4}
    insat = FightEnemy(hp=321, dps=14, death_timer=4)
    slow = DeckOutput(burst_dmg=22, sustained_dmg=18, biggest_hit=12, block_per_turn=20)
    assert estimate_fight(80, slow, [FightEnemy(hp=321, dps=14)]).win  # no timer -> grinds it out
    assert not estimate_fight(80, slow, [insat]).win  # but the Sandpit eats it first
    fast = DeckOutput(burst_dmg=60, sustained_dmg=55, biggest_hit=30, block_per_turn=20)
    assert estimate_fight(80, fast, [insat]).win  # closes inside the (padded) window


def test_estimate_regenerating_block_slows_the_race() -> None:
    deck = DeckOutput(burst_dmg=40, sustained_dmg=30, biggest_hit=15, block_per_turn=5)
    assert estimate_fight(70, deck, [FightEnemy(hp=80, dps=14)]).win
    assert not estimate_fight(70, deck, [FightEnemy(hp=80, dps=14, self_block=25)]).win


def test_estimate_stun_threshold_saves_hp() -> None:
    deck = DeckOutput(burst_dmg=40, sustained_dmg=30, biggest_hit=15, block_per_turn=0)
    base = estimate_fight(70, deck, [FightEnemy(hp=80, dps=30)])
    stunned = estimate_fight(70, deck, [FightEnemy(hp=80, dps=30, stun_threshold=40)])
    assert base.win and stunned.win
    assert stunned.exp_end_hp > base.exp_end_hp  # skipping the stunned turn = less damage taken


def test_estimate_death_damage_costs_end_hp() -> None:
    deck = DeckOutput(burst_dmg=40, sustained_dmg=30, biggest_hit=15, block_per_turn=0)
    base = estimate_fight(70, deck, [FightEnemy(hp=40, dps=5)])
    boom = estimate_fight(70, deck, [FightEnemy(hp=40, dps=5, death_damage=20)])
    assert base.win and boom.win
    assert boom.exp_end_hp == base.exp_end_hp - 20


def test_estimate_thorns_costs_hp_per_attacking_turn() -> None:
    deck = DeckOutput(burst_dmg=20, sustained_dmg=20, biggest_hit=10, block_per_turn=0)
    base = estimate_fight(70, deck, [FightEnemy(hp=80, dps=0)])
    thorny = estimate_fight(70, deck, [FightEnemy(hp=80, dps=0, thorns=10)])
    assert base.win and thorny.win
    assert thorny.exp_end_hp < base.exp_end_hp


def test_bestiary_enemy_from_synthetic_entry() -> None:
    plating = {"name": "Plating", "description": "At the end of your turn, gain 12 Block."}
    entry = {"hp": [200, 222], "statuses": {"PLATING_POWER": plating}}
    from sts2bot.policy.capability import bestiary_enemy

    e = bestiary_enemy(entry, dps=20)
    assert e.hp == 222 and e.self_block == 12 and e.dps == 20  # max HP seen + Plating detected


def test_bestiary_enemy_from_real_bosses() -> None:
    from sts2bot.policy.capability import bestiary_enemy, load_bestiary

    best = load_bestiary()
    assert {"Lagavulin Matriarch", "Vantom"} <= set(best)  # the harvest is present
    lag = bestiary_enemy(best["Lagavulin Matriarch"], dps=20)
    assert lag.hp == 222 and lag.self_block == 12  # real HP + Plating regen
    vantom = bestiary_enemy(best["Vantom"], dps=28)
    assert vantom.hp == 173 and vantom.slippery  # real HP + Slippery
