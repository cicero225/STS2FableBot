"""Canonical race-model cases for the §5-C capability estimate (PLAN §5.1).

These encode the bestiary lessons the one-turn planner can't see (§8.4): Vantom's Slippery,
racing a leader past minions, Strength ramp out-scaling a slow deck. They are the spec — if the
model changes, change these with intent.
"""

from __future__ import annotations

from sts2bot.policy.capability import DeckOutput, FightEnemy, FightOutcome, estimate_fight


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
