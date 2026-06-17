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

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sts2bot.policy.textparse import parse_card_description

_CARD_EFFECTS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "card_effects.json"


def load_card_descriptions(path: Path | str | None = None) -> dict[str, str]:
    """id|<0|1> -> rules text (from scripts/build_card_effects.py). Empty if absent — the map deck
    can then only price cards that still carry their own description (curses, statuses)."""
    p = Path(path) if path else _CARD_EFFECTS_PATH
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


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
    enemy_hp_left: int  # leaders' HP still standing when it ends (0 on a win) — progress in a loss


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
        return FightOutcome(win=True, exp_end_hp=my_hp, turns=0, enemy_hp_left=0)
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
            return FightOutcome(win=True, exp_end_hp=round(hp), turns=turn, enemy_hp_left=0)
        # --- enemy turn: they chip me (ramp already in effect this turn), minus my block ---
        enemy_dps = sum(e.dps for e in enemies) + extra_str * sum(1 for e in enemies if e.dps > 0)
        hp -= max(0.0, enemy_dps - deck.block_per_turn)
        extra_str += sum(e.str_ramp for e in enemies)
        if hp <= 0:  # died; remaining kill_hp = how close I got (progress signal for drafting)
            return FightOutcome(False, round(hp), turn, round(kill_hp))
    # couldn't close inside the horizon -> a grind it doesn't win (treadmill / wall)
    return FightOutcome(False, round(hp), max_turns, round(kill_hp))


def _resolve_cost(cost: str | None, energy: int) -> int:
    s = (cost or "0").strip().upper()
    if s == "X":  # X-cost dumps the turn's energy
        return energy
    try:
        return max(0, int(s))
    except ValueError:
        return 0  # unparsed cost (rare) -> don't let it inflate the energy denominator


def _best_burst(attacks: list[tuple[int, float]], energy: int) -> float:
    """Max single-target damage in one energy-limited turn: a 0/1 knapsack over the deck's best
    affordable attacks (the ideal-draw peak the race uses for 'can I one-shot the leader?')."""
    best = [0.0] * (energy + 1)
    for cost, dmg in attacks:
        cost = max(0, min(energy, cost))
        for e in range(energy, cost - 1, -1):
            best[e] = max(best[e], best[e - cost] + dmg)
    return best[energy]


def deck_output(
    cards: list[Any],
    *,
    strength: int = 0,
    energy_per_turn: int = 3,
    cards_per_turn: int = 5,
    descriptions: dict[str, str] | None = None,
) -> DeckOutput:
    """Estimate a deck's per-turn race inputs from its cards (reusing the CardEffects parser).

    Cards carrying their own `description` (combat-hand Cards) are parsed directly; map `DeckCard`s
    have none, so their rules text is looked up by id+upgrade in `descriptions` (the harvested
    table). sustained/block are the deck's totals spread over a full cycle, whose length is the
    binding of energy (total cost / energy) and draw (deck size / cards drawn), so an expensive
    deck and a curse-clogged one both read as slower. burst is the best energy-limited turn;
    biggest_hit is the deck's largest single hit (what Slippery drops to 1). Strength rides along.
    """
    attacks: list[tuple[int, float]] = []  # (cost, total damage incl. strength)
    total_attack_damage = total_block = total_cost = 0.0
    biggest_hit = 0.0
    deck_size = 0
    for c in cards:
        deck_size += 1  # curses/statuses still clog draws
        if (c.type or "").lower() in ("curse", "status"):
            continue
        cost = _resolve_cost(c.cost, energy_per_turn)
        total_cost += cost
        desc = getattr(c, "description", None)
        if not desc and descriptions is not None and c.id:
            up = 1 if getattr(c, "is_upgraded", False) else 0
            desc = descriptions.get(f"{c.id}|{up}") or descriptions.get(f"{c.id}|0")
        fx = parse_card_description(desc)
        if c.type == "Attack" and fx.damage:
            hit = fx.damage + strength  # one hit, with Strength
            dmg = hit * max(1, fx.hits)
            total_attack_damage += dmg
            attacks.append((cost, dmg))
            biggest_hit = max(biggest_hit, float(hit))
        if fx.block:
            total_block += fx.block
    cycle = max(1.0, deck_size / max(1, cards_per_turn), total_cost / max(1, energy_per_turn))
    return DeckOutput(
        burst_dmg=_best_burst(attacks, energy_per_turn),
        sustained_dmg=total_attack_damage / cycle,
        biggest_hit=biggest_hit,
        block_per_turn=total_block / cycle,
    )
