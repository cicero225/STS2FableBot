"""§5-C capability estimate (PLAN §5.1): a closed-form HP-race — "can I win this fight, and at
what HP cost?".

This is the root lever the one-turn planner can't reach: race-vs-turtle, minion-leader vs
chase-minions, elite/path appetite and rest timing all reduce to it (see memory
`combat-capability-estimate-is-the-root-lever`, PLAN §8.3/§8.4). It is *not* a stochastic
card-by-card simulator (that's P4, only where this mispredicts in logs — "measure don't simulate").
The owner's framing is literally a race: close the leader before the ramp out-scales you.

The model is an aggregate turn-by-turn race: my deck's output per turn (burst on turn 1, sustained
after) chips the leaders' HP; the enemies chip mine (their dps grows with Strength ramp, minus my
block). Whoever reaches zero first wins. Slippery (Vantom) reduces my *largest* single hit each
turn to 1, so it guts single-big-hit decks but barely touches multi-hit ones — which is why the
deck model carries a separate `biggest_hit`. Pure functions only (no I/O); consumers are routers.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeckOutput:
    """What a deck can bring to bear per turn (estimated from the cards; see `deck_output`)."""

    burst_dmg: float  # best achievable single-turn damage to one target (close the leader fast)
    sustained_dmg: float  # damage/turn averaged over a deck cycle (long races)
    biggest_hit: float  # largest single attack — the part Slippery reduces to 1 each turn
    block_per_turn: float  # block/turn averaged over a cycle


@dataclass(frozen=True)
class FightEnemy:
    """One enemy as the race sees it. `counts_toward_kill` is the minion distinction: a summoner's
    spawns and (by the owner's Kin call) ramping followers are *raced past* — leader-kill ends the
    fight — so they add threat (dps) but not kill-HP; only leaders carry kill-HP."""

    hp: int
    dps: int  # damage/turn it deals (current intent, or bestiary average)
    str_ramp: int = 0  # Strength gained per turn -> its dps grows (race it before it out-scales)
    slippery: bool = False  # first HP-loss/turn -> 1 (negates chip; only burst gets through)
    # False for summoned / raced-past minions: they add dps but not kill-HP (leader-kill ends it)
    counts_toward_kill: bool = True


@dataclass(frozen=True)
class FightOutcome:
    win: bool
    exp_end_hp: int  # projected HP when the leaders die (or <=0 if I lose the race)
    turns: int  # turns to close the leaders (or to die)


def estimate_fight(
    my_hp: int,
    deck: DeckOutput,
    enemies: list[FightEnemy],
    *,
    max_turns: int = 30,
) -> FightOutcome:
    """Race the deck against the enemies; -> who reaches zero first and at what HP."""
    kill_hp = float(sum(e.hp for e in enemies if e.counts_toward_kill))
    if kill_hp <= 0:
        return FightOutcome(win=True, exp_end_hp=my_hp, turns=0)
    # Slippery on any leader gates my whole turn (it's the leader I'm chipping).
    slippery = any(e.slippery for e in enemies if e.counts_toward_kill)
    hp = float(my_hp)
    extra_str = 0  # accumulated ramp, added to every attacker's dps as turns pass
    for turn in range(1, max_turns + 1):
        # --- my turn: chip the leaders ---
        out = deck.burst_dmg if turn == 1 else deck.sustained_dmg
        if slippery:
            out = max(1.0, out - deck.biggest_hit + 1.0)  # largest hit drops to 1
        kill_hp -= out
        if kill_hp <= 0:
            return FightOutcome(win=True, exp_end_hp=round(hp), turns=turn)
        # --- enemy turn: they chip me (ramp already in effect this turn), minus my block ---
        enemy_dps = sum(e.dps for e in enemies) + extra_str * sum(1 for e in enemies if e.dps > 0)
        hp -= max(0.0, enemy_dps - deck.block_per_turn)
        extra_str += sum(e.str_ramp for e in enemies)
        if hp <= 0:
            return FightOutcome(win=False, exp_end_hp=round(hp), turns=turn)
    # couldn't close inside the horizon -> a grind it doesn't win (treadmill / wall)
    return FightOutcome(win=False, exp_end_hp=round(hp), turns=max_turns)
