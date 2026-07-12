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
import re
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


# Vulnerable is +50% damage, but it's not up every turn (a setup turn, reapplication gaps), so a
# deck that *can* apply it is credited an uptime-averaged multiplier rather than the full 1.5.
_VULN_DAMAGE_MULT = 1.3

# The Insatiable's Sandpit timer is *extendable*: it shuffles in 6 Frantic Escape cards, each of
# which raises the counter (at escalating cost). The one-turn planner plays them opportunistically
# (0-value cards go late in a sequence), so the real race window is ~6-8 turns, not the base ~4 —
# pad the parsed deadline by this much. (Optimal Frantic-Escape timing is a later refinement.)
_SANDPIT_SLACK = 3


@dataclass(frozen=True)
class DeckOutput:
    """What a deck can bring to bear per turn (estimated from the cards; see `deck_output`)."""

    burst_dmg: float  # best achievable single-turn damage to one target (close the leader fast)
    sustained_dmg: float  # damage/turn averaged over a deck cycle (long races)
    biggest_hit: float  # largest single attack — the part Slippery reduces to 1 each turn
    block_per_turn: float  # block/turn averaged over a cycle
    # in-fight scaling (estimated from the cards) — why a static burst/sustained under-rates
    # ramp/Vulnerable decks (the Matriarch-win pessimism, PLAN §8.4):
    str_per_turn: float = 0.0  # Strength the deck gains/turn -> adds to every hit as turns pass
    hits_per_turn: float = 0.0  # attack instances/turn (each one cashes in accumulated Strength)
    str_cap: float = 0.0  # total Strength the deck's cards can grant (plateaus the ramp)
    vuln_mult: float = 1.0  # damage multiplier when the deck reliably applies Vulnerable


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
    # damage-throttling (ENEMY_PASS Phase 0c) — detected from status text by detect_mechanics:
    dmg_cap_per_turn: int | None = None  # max HP it can lose/turn (Hardened Shell, Intangible)
    self_block: int = 0  # block it regenerates each turn (Plating); soaks that much of my damage
    death_damage: int = 0  # self-damage it deals me when I kill it (Steam Eruption)
    stun_threshold: int = 0  # HP at/below which it's Stunned once, skipping a turn (Plow, Shriek)
    thorns: int = 0  # damage it deals me each turn I attack it (Thorns)
    death_timer: int = 0  # Sandpit (The Insatiable): I die at this turn unless I've won — race it
    skittish: int = 0  # +Block on its first hit each turn (Skittish) — guts chip/multi-hit
    # player-stat drain (Lagavulin's Soul Siphon — live-traced 2026-07-09: -2 Str AND -2 Dex per
    # cast, every 4th round post-wake, permanent). A move/intent, not a status, so it can't be
    # text-detected; sourced from the _EMPIRICAL per-enemy table.
    drains_player: int = 0  # Str AND Dex the player permanently loses per cast
    drain_every: int = 0  # cast cadence in turns (0 = never)
    # death-damage that GROWS with fight length (Waterfall Giant: ~+3 Steam Eruption per move,
    # so the explosion at kill is the accumulated stack, not the flat 15 the status text shows)
    death_damage_growth: int = 0  # added to death_damage per elapsed turn
    # sustained self-healing (Knowledge Demon's Ponder: heal 30 every 4th turn ≈ 7.5/turn) —
    # the race must out-damage the regeneration, so it joins the kill math per turn
    heals_per_turn: int = 0
    # average per-turn blockable load its player-debuffs add (KD's escalating Disintegration:
    # 6+7+8 by round 9 ≈ +5/turn averaged over the fight) — folded into its dps for the race
    player_dot_avg: int = 0


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
    leaders = [e for e in enemies if e.counts_toward_kill]
    kill_hp = float(sum(e.hp for e in leaders))
    if kill_hp <= 0:
        return FightOutcome(win=True, exp_end_hp=my_hp, turns=0, enemy_hp_left=0)
    # Fight-level throttling, derived from the leaders (exact for a single-leader boss; an
    # approximation when several leaders carry kill-HP). All gate the damage I land each turn.
    slippery = any(e.slippery for e in leaders)
    self_block = sum(e.self_block for e in leaders)  # regenerating enemy block, absorbs my damage
    caps = [e.dmg_cap_per_turn for e in leaders if e.dmg_cap_per_turn is not None]
    cap = min(caps) if caps else None  # hard per-turn HP-loss cap (burst is wasted past it)
    death_damage = sum(e.death_damage for e in leaders)  # self-damage on the kill
    death_growth = sum(e.death_damage_growth for e in leaders)  # Waterfall: stack grows per turn
    heals = sum(e.heals_per_turn for e in leaders)  # KD's Ponder: the race must out-damage it
    stun_at = max((e.stun_threshold for e in leaders), default=0)  # crossing it skips a turn
    thorns = sum(e.thorns for e in leaders)
    drain_amt = max((e.drains_player for e in leaders), default=0)  # Soul Siphon, per cast
    drain_every = max((e.drain_every for e in leaders if e.drains_player), default=0)
    death_timer = min((e.death_timer for e in leaders if e.death_timer), default=0)  # race-or-die
    if death_timer:
        death_timer += _SANDPIT_SLACK  # extendable via Frantic Escape -> the real window is longer
    base_dps = sum(e.dps for e in enemies) + sum(e.player_dot_avg for e in enemies)
    n_attackers = sum(1 for e in enemies if e.dps > 0)
    hp = float(my_hp)
    extra_str = 0  # accumulated enemy ramp, added to every attacker's dps as turns pass
    my_str = 0.0  # my accumulated Strength (deck's Str-granters); plateaus at deck.str_cap
    drained = 0.0  # accumulated Soul-Siphon-style drain: subtracts from my Str AND my block/turn
    stunned_used = False
    for turn in range(1, max_turns + 1):
        if death_timer and turn > death_timer:  # Sandpit fired before I could close — I'm eaten
            return FightOutcome(False, round(hp), death_timer, round(kill_hp))
        # --- my turn: chip the leaders, throttled ---
        out = deck.burst_dmg if turn == 1 else deck.sustained_dmg
        # in-fight scaling: accumulated Strength adds to every hit, Vulnerable amplifies the lot.
        # Drained Strength (Soul Siphon) subtracts the same way — it can push net Str negative.
        out = max(0.0, (out + (my_str - drained) * deck.hits_per_turn) * deck.vuln_mult)
        if self_block:
            out = max(0.0, out - self_block)  # regenerating block soaks the first chunk
        if slippery:
            out = max(1.0, out - deck.biggest_hit + 1.0)  # largest hit drops to 1
        if cap is not None:
            out = min(out, float(cap))  # hard cap: never burst more than this into it
        kill_hp -= out
        if thorns and out > 0:
            hp -= thorns  # retaliation for attacking it
        if kill_hp <= 0:  # killed the leaders (thorns already paid); eat any death-damage
            # Waterfall: the kill explosion is the ACCUMULATED stack, growing each turn
            return FightOutcome(
                win=True, exp_end_hp=round(hp - death_damage - death_growth * turn),
                turns=turn, enemy_hp_left=0)
        # sustained self-healing (Ponder) regenerates AFTER a non-lethal turn, capped at start
        if heals:
            kill_hp = min(kill_hp + heals, float(sum(e.hp for e in leaders)))
        if hp <= 0:  # thorns killed me while it still stands
            return FightOutcome(False, round(hp), turn, round(kill_hp))
        # --- enemy turn: skipped the turn it's Stunned by crossing its threshold ---
        if stun_at and kill_hp <= stun_at and not stunned_used:
            stunned_used = True
            extra_str = 0  # Plow: the Beast loses ALL accumulated Strength when it stuns
        else:
            enemy_dps = base_dps + extra_str * n_attackers
            # Drained Dexterity thins my block; ~1 block-card/turn approximation (drained pts
            # subtract once per turn, not per card — conservative on multi-block decks).
            block_pt = max(0.0, deck.block_per_turn - drained)
            hp -= max(0.0, enemy_dps - block_pt)
        if drain_amt and drain_every and turn % drain_every == 0:
            drained += drain_amt  # Soul Siphon cast this cycle: permanent -Str -Dex
        extra_str += sum(e.str_ramp for e in enemies)
        my_str = min(deck.str_cap, my_str + deck.str_per_turn)  # one-time gains plateau at the cap
        if hp <= 0:  # died; remaining kill_hp = how close I got (progress signal for drafting)
            return FightOutcome(False, round(hp), turn, round(kill_hp))
    # couldn't close inside the horizon -> a grind it doesn't win (treadmill / wall)
    return FightOutcome(False, round(hp), max_turns, round(kill_hp))


# ENEMY_PASS Phase 0c: the mod ships enemy status text as rules descriptions, so the race-relevant
# mechanics parse straight out of it. Anchored tightly to avoid catching conditional one-offs
# (e.g. Crab Rage's "gains 99 Block on ally death" is NOT per-turn regen).
# caps -> Hardened Shell, Hard to Kill, Intangible; block -> Plating; stun -> Plow, Shriek
_CAP_RE = re.compile(r"cannot lose more than (\d+) HP", re.I)
_CAP_RE2 = re.compile(r"damage taken and HP los[ts][^.]*? to (\d+)", re.I)
_BLOCK_RE = re.compile(r"end of (?:your|its|each)?\s*turn,?\s*gain[s]? (\d+) Block", re.I)
_DEATH_RE = re.compile(r"when killed, deals (\d+) damage", re.I)  # Steam Eruption
_STUN_RE = re.compile(r"HP reaches (\d+) or below", re.I)
_THORNS_RE = re.compile(r"hit by an attack, deal (\d+) damage back", re.I)  # Thorns
_RAMP_RE = re.compile(r"end of (?:its|each|your)?\s*turn,?\s*gain[s]? (\d+) Strength", re.I)
_TIMER_RE = re.compile(r"in (\d+) turns?[^.]*?\bdie\b", re.I)  # Sandpit: "In N turns ... you die"
_SKITTISH_RE = re.compile(r"first time.*?hit each turn.*?gains? (\d+) block", re.I)  # Skittish


def detect_mechanics(statuses: list[dict]) -> dict[str, Any]:
    """Parse an enemy's statuses (each `{name, description, ...}`) into `FightEnemy` throttling
    kwargs. Unknown text contributes nothing (so a new status fails safe to 'generic enemy')."""
    cap: int | None = None
    block = death = stun = thorns = ramp = skittish = 0
    timer = 0  # soonest "you will die in N turns" deadline (Sandpit)
    slippery = False
    for s in statuses:
        d = s.get("description") or ""
        if m := (_CAP_RE.search(d) or _CAP_RE2.search(d)):
            v = int(m.group(1))
            cap = v if cap is None else min(cap, v)
        if m := _TIMER_RE.search(d):
            t = int(m.group(1))
            timer = t if not timer else min(timer, t)
        if m := _SKITTISH_RE.search(d):
            skittish = max(skittish, int(m.group(1)))
        if m := _BLOCK_RE.search(d):
            block += int(m.group(1))
        if m := _DEATH_RE.search(d):
            death += int(m.group(1))
        if (m := _STUN_RE.search(d)) and "stunned" in d.lower():
            stun = max(stun, int(m.group(1)))
        if m := _THORNS_RE.search(d):
            thorns += int(m.group(1))
        if m := _RAMP_RE.search(d):
            ramp += int(m.group(1))
        if "only loses 1 hp" in d.lower():
            slippery = True
    out: dict[str, Any] = {}
    if cap is not None:
        out["dmg_cap_per_turn"] = cap
    if block:
        out["self_block"] = block
    if death:
        out["death_damage"] = death
    if stun:
        out["stun_threshold"] = stun
    if thorns:
        out["thorns"] = thorns
    if ramp:
        out["str_ramp"] = ramp
    if slippery:
        out["slippery"] = True
    if timer:
        out["death_timer"] = timer
    if skittish:
        out["skittish"] = skittish
    return out


_BESTIARY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "bestiary.json"


def load_bestiary(path: Path | str | None = None) -> dict[str, dict]:
    """Enemy name -> harvested record (roles, acts, hp, statuses) from data/bestiary.json
    (scripts/build_bestiary.py). Empty if absent."""
    p = Path(path) if path else _BESTIARY_PATH
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("enemies", {})


# Move/intent mechanics that no status text carries — live-traced params, keyed by a substring of
# the bestiary entry name. (Soul Siphon: 2026-07-09 trace, -2 Str -2 Dex per cast, every 4th round
# post-wake; permanent. See PLAN §8.4-A.)
_EMPIRICAL_MOVES: dict[str, dict[str, int]] = {
    "MATRIARCH": {"drains_player": 2, "drain_every": 4},
    # Waterfall Giant: +3 Steam Eruption per move -> the kill explosion is the ACCUMULATED
    # stack (30-60+ in a real race), not the flat 15 in the status text (PLAN §8.4-A part a)
    "WATERFALL": {"death_damage_growth": 3},
    # Knowledge Demon (PLAN §8.4-B open (b)): Ponder heals 30 every 4th turn (~7.5/turn the
    # race must out-damage) and the forced Disintegration picks average ~+5/turn blockable
    # load on the player by mid-fight (6+7+8 escalation)
    "KNOWLEDGE DEMON": {"heals_per_turn": 7, "player_dot_avg": 5},
}

# Multi-body elites the harvest records as ONE body (PLAN §8.5.6 sub-item, 2026-07-09: the pool
# gate fixed single-body elites — Terror Eel deaths 2→0 — but Gardeners/Phrog kept killing runs
# because one 31-HP Gardener flatters a 3-body Skittish swarm, and Phrog's death spawns a
# Wriggler wave). Keyed by a substring of the elite name; members are (bestiary name, count).
_ELITE_COMPOSITIONS: dict[str, list[tuple[str, int]]] = {
    "PHANTASMAL GARDENER": [("Phantasmal Gardener", 3)],
    "PHROG PARASITE": [("Phrog Parasite", 1), ("Wriggler", 4)],
    # 3 segments live-counted (batch bn4v9mf75 run 3, a genuine gate-pass death: the Act-2 pool
    # held only Entomancer, so a 46-HP single segment flattered a 138-HP Reattach fight).
    # Reattach's revive (25 HP after 2 turns unless killed together) is NOT modeled — the body
    # count alone fixes the gross underestimate; revive-HP is the ENEMY_PASS (B) refinement.
    "DECIMILLIPEDE": [("Decimillipede", 3)],
    # The Act-3 Knights fight all three together (276 HP total; the owner's f44 one-turn-kill
    # pack, confirmed by the merged bestiary 2026-07-12). Full names as keys — a bare "KNIGHT"
    # would false-match Mecha Knight, a genuine 300-HP solo.
    "FLAIL KNIGHT": [("Flail Knight", 1), ("Spectral Knight", 1), ("Magi Knight", 1)],
    "SPECTRAL KNIGHT": [("Flail Knight", 1), ("Spectral Knight", 1), ("Magi Knight", 1)],
    "MAGI KNIGHT": [("Flail Knight", 1), ("Spectral Knight", 1), ("Magi Knight", 1)],
}


def elite_fight_members(
    name: str, entry: dict, bestiary: dict, *, dps: int, str_ramp: int = 0
) -> list[FightEnemy]:
    """The full body-list for an elite fight. Single-body elites -> [bestiary_enemy(entry)];
    composed ones (swarms, death-spawn waves) expand via _ELITE_COMPOSITIONS, splitting the
    per-act dps estimate across the bodies (HP totals and per-body mechanics like Skittish are
    the real correction; total threat stays the act estimate)."""
    comp = next(
        (m for key, m in _ELITE_COMPOSITIONS.items() if key in name.upper()), None
    )
    if not comp:
        return [bestiary_enemy(entry, dps=dps, name=name, str_ramp=str_ramp)]
    bodies = sum(n for _, n in comp)
    per_dps = max(1, dps // max(1, bodies))
    members: list[FightEnemy] = []
    for member_name, count in comp:
        m_entry = bestiary.get(member_name) or entry
        for _ in range(count):
            members.append(
                bestiary_enemy(m_entry, dps=per_dps, name=member_name, str_ramp=str_ramp)
            )
    return members


def bestiary_enemy(entry: dict, *, dps: int, name: str = "", **overrides: Any) -> FightEnemy:
    """Build a FightEnemy from a bestiary entry: its max HP seen + the mechanics detected from its
    status descriptions. dps isn't harvested reliably (intents vary), so the caller passes a
    per-act estimate; HP and the mechanics are the real, race-relevant parts. Entries carry no
    name (the bestiary is name-keyed), so callers pass it for the _EMPIRICAL_MOVES lookup.
    `overrides` win."""
    hp = (entry.get("hp") or [None, None])[1] or 1
    flags = detect_mechanics(list((entry.get("statuses") or {}).values()))
    for key, move_flags in _EMPIRICAL_MOVES.items():
        if key in name.upper():
            flags.update(move_flags)
    flags.update(overrides)
    return FightEnemy(hp=int(hp), dps=dps, **flags)


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
    total_hits = total_str_gain = 0.0  # hit instances / Strength granted (in-fight scaling)
    vuln_sources = 0  # cards that apply Vulnerable -> reliability of the damage multiplier
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
            hits = max(1, fx.hits)
            hit = fx.damage + strength  # one hit, with (starting) Strength
            total_attack_damage += hit * hits
            total_hits += hits
            attacks.append((cost, hit * hits))
            biggest_hit = max(biggest_hit, float(hit))
        if fx.block:
            total_block += fx.block
        total_str_gain += fx.strength  # Inflame/Spot Weakness/Limit Break... ramp my damage
        if fx.vulnerable:
            vuln_sources += 1
    cycle = max(1.0, deck_size / max(1, cards_per_turn), total_cost / max(1, energy_per_turn))
    # Vulnerable as *uptime*, not a binary flag: a lone source applies it only intermittently (you
    # draw it ~once per cycle), so the deck seldom has Vulnerable up every turn; each extra source
    # raises uptime with diminishing returns, capped at the reliable-application ceiling. apps/turn
    # = sources * cards_drawn / deck_size (owner lookthrough 2026-06-25: a lone Bash is a weak
    # Vulnerable source; a 2nd enabler matters — the binary flag over-credited the first).
    vuln_uptime = min(1.0, vuln_sources * cards_per_turn / max(1, deck_size))
    vuln_mult = 1.0 + (_VULN_DAMAGE_MULT - 1.0) * vuln_uptime
    return DeckOutput(
        burst_dmg=_best_burst(attacks, energy_per_turn),
        sustained_dmg=total_attack_damage / cycle,
        biggest_hit=biggest_hit,
        block_per_turn=total_block / cycle,
        str_per_turn=total_str_gain / cycle,
        hits_per_turn=total_hits / cycle,
        str_cap=total_str_gain,
        vuln_mult=vuln_mult,
    )
