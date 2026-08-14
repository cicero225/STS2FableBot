"""Multiturn feasibility oracle (P3 of the multiturn planner, owner design
session 2026-08-11).

NOT a tree search: the owner's own play rule for the wall bosses is a
feasibility calculation ("can I kill Rocket by T4 without dropping below ~25
HP?"), so the oracle answers exactly those questions and a mode selector turns
the answers into a fight plan the one-turn planner consumes as biases.

Primitives (all pure; script data passed in):
  throughput(...)   -> per-turn damage/block distribution from hand + REAL
                       draw/discard pile composition (live payloads carry full
                       pile contents; order unknown -- same as the player).
                       Hybrid per owner: density over the actual pile, exact
                       when the pile is nearly empty.
  incoming_by_turn  -> enemy damage schedule from wiki-verified move scripts
                       (data/move_scripts.json), turn- or wake-anchored.
  hp_at(k)          -> projected player HP at future turn k.
  kill_eta(...)     -> expected turns to kill a target (mean and pessimistic).
  choose_mode(...)  -> race / defend_deadline / setup_window / guard_break
                       (+params) from the per-boss mode table (OWNER-REVIEWED
                       before the router consumes it).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from sts2bot.policy.textparse import parse_card_description

_SCRIPTS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "move_scripts.json"


def load_move_scripts(path: Path | str | None = None) -> dict[str, dict]:
    """Enemy name -> harvested turn script (scripts/build_move_scripts.py).
    Empty if absent."""
    p = Path(path) if path else _SCRIPTS_PATH
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

# pessimism: plan on drawing the weaker part of the pile (owner: density with a
# margin; calibrate against fuzz/audit corpora later)
P25_THROUGHPUT_FACTOR = 0.72
# the pile size at/below which next-hand composition is (partially) exact
EXACT_PILE_THRESHOLD = 6


@dataclass(frozen=True)
class Throughput:
    dmg_mean: float  # expected single-target damage per turn
    dmg_p25: float   # pessimistic damage per turn
    blk_mean: float  # expected block per turn (dedicating defense)
    exact_tail: bool = False  # pile small enough that draws are near-exact


@dataclass(frozen=True)
class FightPlan:
    mode: str  # race | defend_deadline | setup_window | guard_break
    # mode params (deadline turn, priority target entity_id, window turns left)
    deadline_turn: int | None = None
    target: str | None = None
    window_turns: int = 0
    rationale: str = ""
    detail: dict = field(default_factory=dict)


def _card_stats(card, card_effects: dict | None) -> tuple[int, float, float]:
    """(cost, damage, block) for one card, catalog fallback for missing text."""
    desc = card.description or ""
    if not desc and card_effects:
        cid = (card.id or "").upper()
        up = 1 if getattr(card, "is_upgraded", False) else 0
        desc = card_effects.get(f"{cid}|{up}") or card_effects.get(f"{cid}|0") or ""
    fx = parse_card_description(desc)
    try:
        cost = max(0, int(card.cost)) if str(card.cost).upper() != "X" else 1
    except (TypeError, ValueError):
        cost = 1
    dmg = float(fx.damage * max(1, fx.hits))
    blk = float(fx.block + fx.plating)
    return cost, dmg, blk


def throughput(player, card_effects: dict | None = None,
               strength: int = 0) -> Throughput:
    """Per-turn output from the REAL cycling pool: hand + draw + discard piles
    (exhaust excluded -- those cards are gone). Density model: the expected
    hand is 5 draws from the pool, energy allocates to the densest cards.
    v1 approximation is deliberately simple; the fuzz/audit corpora calibrate."""
    pool = list(player.hand or [])
    for pile in (player.draw_pile, player.discard_pile):
        pool.extend(pile or [])
    if not pool:
        return Throughput(0.0, 0.0, 0.0)
    energy = float(player.max_energy or player.energy or 3)
    stats = [_card_stats(c, card_effects) for c in pool]
    hand_frac = min(1.0, 5.0 / len(pool))  # fraction of the pool seen per turn

    def per_turn(select) -> float:
        # value available per turn: cards seen x their output, energy-capped by
        # efficiency ordering (spend energy on the densest cards first)
        seen = sorted(
            ((cost, val) for cost, val in select if val > 0),
            key=lambda cv: (cv[1] / max(1, cv[0])), reverse=True)
        budget, total = energy, 0.0
        for cost, val in seen:
            take = min(1.0, budget / max(1, cost)) * hand_frac
            total += val * take
            budget -= cost * hand_frac
            if budget <= 0:
                break
        return total

    dmg = per_turn([(c, d + strength * (1 if d > 0 else 0)) for c, d, _ in stats])
    blk = per_turn([(c, b) for c, _, b in stats])
    exact = (len(player.draw_pile or [])) <= EXACT_PILE_THRESHOLD
    return Throughput(
        dmg_mean=dmg, dmg_p25=dmg * P25_THROUGHPUT_FACTOR,
        blk_mean=blk, exact_tail=exact,
    )


def incoming_by_turn(script: dict | None, current_round: int, horizon: int,
                     fallback_dps: float = 12.0,
                     wake_offset: int | None = None) -> list[float]:
    """Enemy damage for the next `horizon` turns from a harvested move script.
    `script` = one enemy's entry from data/move_scripts.json. Wake-anchored
    scripts index from the wake turn; `wake_offset` = how many of THIS fight's
    turns since wake (0 = waking this turn), None = not asleep/not anchored."""
    out: list[float] = []
    if not script or not script.get("turns"):
        return [fallback_dps] * horizon
    turns = script["turns"]
    anchored = script.get("wake_anchored", False)
    for k in range(1, horizon + 1):
        if anchored:
            idx = (wake_offset or 0) + k
            key = f"W{idx}"
            # scripts cycle: wrap on the longest observed prefix
            if key not in turns:
                observed = [int(t[1:]) for t in turns if t.startswith("W")]
                if observed:
                    span = max(observed)
                    key = f"W{(idx - 1) % span + 1}"
        else:
            idx = current_round + k
            key = str(idx)
            if key not in turns:
                observed = [int(t) for t in turns if t.isdigit()]
                if observed:
                    span = max(observed)
                    key = str((idx - 1) % span + 1)
        rows = turns.get(key) or []
        dmg = 0.0
        best_n = 0
        for r in rows:
            if (r.get("intent") or "").lower() not in ("attack", "deathblow"):
                continue
            label = r.get("label") or ""
            try:
                if "x" in label:
                    a, b = label.split("x")
                    val = int(a) * int(b)
                else:
                    val = int(label)
            except ValueError:
                continue
            if r.get("n", 0) > best_n:
                best_n, dmg = r["n"], float(val)
        out.append(dmg if best_n else 0.0)
    return out


def hp_at(current_hp: int, current_block: int, incoming: list[float],
          block_per_turn: float, defend_frac: float = 0.5) -> list[float]:
    """Projected HP after each of the next turns, spending `defend_frac` of
    the block throughput on defense (0 = all-in race, 1 = full turtle)."""
    hp = float(current_hp)
    blk = float(current_block)
    traj = []
    for inc in incoming:
        soak = blk + block_per_turn * defend_frac
        hp -= max(0.0, inc - soak)
        blk = 0.0  # block does not carry (Barricade et al. are v2 refinements)
        traj.append(hp)
    return traj


def kill_eta(target_effective_hp: float, tp: Throughput,
             offense_frac: float = 1.0) -> tuple[float, float]:
    """(mean, pessimistic) turns to bring the target to 0, spending
    `offense_frac` of throughput on damage."""
    mean_dpt = tp.dmg_mean * offense_frac
    p25_dpt = tp.dmg_p25 * offense_frac
    eta_mean = target_effective_hp / mean_dpt if mean_dpt > 0 else float("inf")
    eta_p25 = target_effective_hp / p25_dpt if p25_dpt > 0 else float("inf")
    return eta_mean, eta_p25


# ---------------------------------------------------------------- mode table
# DRAFT -- OWNER REVIEW PENDING (their explicit ask at the design session).
# The router does not consume choose_mode until this table is signed off.
# Grounded rows cite wiki-verified scripts; TBD rows await their wiki pass.
FIGHT_MODE_TABLE: dict[str, dict] = {
    "LAGAVULIN MATRIARCH": {
        "asleep": "setup_window",  # 3 free turns max; Plating drops on wake
        "awake": "race",  # Soul Siphon every 4th beat: long fights strictly worsen
        "notes": "OWNER-REVIEWED 2026-08-12: 'not a pure race, but a lot of it is "
                 "racing' -- the fight is VALUE-driven: play big damage, impactful "
                 "powers, or big mitigation. Blocking 3-4 isn't worth deferring "
                 "value; blocking MOST of a round (Blood Wall) beats a mere Strike. "
                 "Deck-dependent: without impact cards neither plan saves it. Wake "
                 "early ONLY if burst-in-hand beats remaining setup value.",
    },
    "ROCKET": {  # the Kaiser Crab fight: no body is named 'Kaiser' live (wiki:
        # two claws only); ROCKET is corpus-unique to this fight (241/241 f33)
        "rule": "kill_by_deadline",
        "target": "Rocket", "deadline": 4, "hp_floor": 25,
        "notes": "Laser recurs T4/T9/T14; feasible p25-kill by T4 -> race "
                 "(block ~ waste, surround costs ~10/rd regardless); else "
                 "defend_deadline on Laser turns, kill T5-7. Post-kill: Crab "
                 "Rage turn (+6 Str, 99 Block) is quasi-dead offense -- "
                 "defend/setup that turn.",
    },
    "QUEEN": {
        "guarded": "guard_break",  # Torch is the clock; she buffs+re-blocks
        "awake": "race",  # she wakes buffed and growing: finish it
        "notes": "guard_break target = the minion (4642772 fixed ignorable); "
                 "her awakened dps grows per buff turn -- ETA matters.",
    },
    "WATERFALL GIANT": {
        "default": "race",
        "notes": "eruption finale is a blockable telegraphed beat after the "
                 "kill (knockdown decode) -- race, then defend the eruption "
                 "turn via its intent (already priced by the one-turn planner).",
    },
    "THE INSATIABLE": {
        "default": "race",
        "notes": "OWNER-REVIEWED 2026-08-12: race, but never so hard the escapes "
                 "go unplayed -- rule of thumb: play at least one Frantic Escape "
                 "per turn while it costs <=1, unless sure of lethal in time. "
                 "Encoded card-level: w_frantic_escape (combat.py), lethal-gated.",
    },
    # TBD pending wiki verification passes (do not ship without owner review):
    "KNOWLEDGE DEMON": {
        "default": "race",
        "notes": "WIKI-VERIFIED 2026-08-13: Ponder heals him 30/cycle + 2 Str "
                 "-- every uncompleted cycle costs 30 effective HP and ramps "
                 "both his damage and the Disintegration clock. Hard race; "
                 "kill by cycle 3 caps Disintegration at 21.",
    },
    "TEST SUBJECT": {"default": "race", "notes": "TBD: staged full-heal bodies"},
    "CEREMONIAL BEAST": {"default": "race", "notes": "TBD: single HP threshold"},
    "AEONGLASS": {
        "default": "race",
        "notes": "WIKI-VERIFIED 2026-08-13: 3-cycle Ebb 22+33Block / Eye Lasers "
                 "11x2 / Increasing Intensity (Wither+X, +2+X Str, upgrades all "
                 "Withers). Superlinear escalation -- hard race; exhaust tools "
                 "clear Withers (draft rule exists); Ebb turns are her block "
                 "turns (debuff there, burst elsewhere -- future nuance).",
    },
}


def choose_mode(enemies: list, player, scripts: dict,
                card_effects: dict | None = None,
                current_round: int = 1, hp_floor: int = 25) -> FightPlan:
    """Pick the fight plan from the mode table + feasibility math.
    `enemies` = live views with .name/.hp/.block/.asleep-ish signals."""
    tp = throughput(player, card_effects)
    alive = [e for e in enemies if (getattr(e, "hp", 0) or 0) > 0]
    names = {(getattr(e, "name", "") or "").upper() for e in alive}

    def find(key):
        return next((e for e in alive if key in (getattr(e, "name", "") or "").upper()), None)

    for key, rule in FIGHT_MODE_TABLE.items():
        if not any(key in n for n in names):
            continue
        boss = find(key)
        if rule.get("rule") == "kill_by_deadline":
            tgt = find((rule["target"] or "").upper()) or boss
            deadline = rule["deadline"]
            eff_hp = (getattr(tgt, "hp", 0) or 0) + (getattr(tgt, "block", 0) or 0)
            _eta_mean, eta_p25 = kill_eta(eff_hp, tp)
            # HP check over the RACE WINDOW, not the whole schedule: the target
            # attacks only until the kill lands (a dead claw fires no Laser --
            # first draft charged Rocket's T4 into a T3 kill), while the OTHER
            # bodies keep hitting through the kill turn.
            if not math.isfinite(eta_p25):
                # no measurable damage throughput (e.g. empty piles mid-parse):
                # the kill question is unanswerable -- defend the deadline
                return FightPlan(
                    mode="defend_deadline", target=getattr(tgt, "entity_id", None),
                    deadline_turn=deadline,
                    rationale="no damage throughput measurable; defend the deadline",
                    detail={"cycle": 0},
                )
            kill_turn = min(deadline, max(1, math.ceil(eta_p25)))
            tgt_inc = incoming_by_turn(
                scripts.get(getattr(tgt, "name", "") or ""),
                current_round, max(0, kill_turn - 1))
            other_inc = [0.0] * kill_turn
            for e in alive:
                if e is tgt:
                    continue
                for i, v in enumerate(incoming_by_turn(
                        scripts.get(getattr(e, "name", "") or ""),
                        current_round, kill_turn, fallback_dps=0.0)):
                    other_inc[i] += v
            merged = [
                (tgt_inc[i] if i < len(tgt_inc) else 0.0) + other_inc[i]
                for i in range(kill_turn)
            ]
            traj = hp_at(getattr(player, "hp", 0) or 0,
                         getattr(player, "block", 0) or 0, merged,
                         tp.blk_mean, defend_frac=0.0)
            feasible = (eta_p25 <= deadline
                        and (not traj or min(traj) >= rule.get("hp_floor", hp_floor)))
            if feasible:
                return FightPlan(
                    mode="race", target=getattr(tgt, "entity_id", None),
                    deadline_turn=deadline,
                    rationale=f"kill-by-T{deadline} feasible "
                              f"(eta_p25={eta_p25:.1f}, hp_min={min(traj) if traj else '?'})",
                )
            script = scripts.get(getattr(tgt, "name", "") or "") or {}
            # cycle length: wiki-verified field first (the harvest's raw turn
            # keys run PAST one cycle -- fights observed at T6-T12 are cycle-2
            # rows, so max-key is not the period)
            spans = [int(t) for t in (script.get("turns") or {}) if str(t).isdigit()]
            cycle = int(script.get("cycle") or 0) or (max(spans) if spans else 0)
            return FightPlan(
                mode="defend_deadline", target=getattr(tgt, "entity_id", None),
                deadline_turn=deadline,
                rationale=f"kill-by-T{deadline} infeasible (eta_p25={eta_p25:.1f}); "
                          f"defend the deadline, kill after",
                detail={"cycle": cycle},
            )
        if "asleep" in rule and boss is not None and getattr(boss, "asleep", False):
            return FightPlan(mode=rule["asleep"], target=getattr(boss, "entity_id", None),
                             window_turns=max(0, 3 - (current_round - 1)),
                             rationale=f"{key}: sleep window")
        if "guarded" in rule:
            minion = next((e for e in alive if e is not boss), None)
            if minion is not None:
                return FightPlan(mode=rule["guarded"],
                                 target=getattr(minion, "entity_id", None),
                                 rationale=f"{key}: break the guard (minion is the clock)")
        return FightPlan(mode=rule.get("awake") or rule.get("default", "race"),
                         target=getattr(boss, "entity_id", None),
                         rationale=f"{key}: table default")
    # unknown fight: no plan (one-turn planner's existing behavior stands)
    return FightPlan(mode="", rationale="no table entry")
