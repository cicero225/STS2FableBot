"""One-turn combat planner (PLAN.md §5 phase B).

Enumerates energy-feasible card sequences for this turn (branching over targets
for single-target attacks), simulates a minimal effect model (damage, block,
vulnerable/weak/strength interactions), scores end states with configured
weights, and plays the first action of the best sequence. Re-plans after every
action, so simulation drift self-corrects against fresh state.

Deliberately NOT a full game simulator (C5: patch churn). Unrecognized card text
contributes nothing to the simulation; such cards are still playable late in a
sequence so 'mystery' cards get exercised rather than hoarded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from sts2bot.client import actions as act
from sts2bot.client.models import CombatState, Enemy
from sts2bot.kb.config import CombatWeights
from sts2bot.policy.base import Decision, Wait
from sts2bot.policy.textparse import CardEffects, parse_card_description, parse_intent_damage

VULN_MULT = 1.5
WEAK_MULT = 0.75
_RAGE_BLOCK = re.compile(r"gain (\d+) block", re.IGNORECASE)
# "Exhaust your hand, deal N damage for each card exhausted" (Fiend Fire): damage
# scales with hand size, so the flat per-hit the text parser sees underprices it.
_HAND_EXHAUST_DMG = re.compile(r"(\d+) damage for each card", re.IGNORECASE)


@dataclass(frozen=True)
class PlannedCard:
    index: int
    name: str
    cost: int  # X-cost resolved to current energy at plan time
    fx: CardEffects
    targets_enemy: bool
    is_attack: bool = False
    is_power: bool = False  # Power card: playing it banks a permanent buff (play eagerly)
    rage_block: int = 0  # Rage: block gained per Attack played after it this turn
    hand_exhaust_scale: int = 0  # Fiend Fire: damage per card exhausted from hand (0 = n/a)


@dataclass(frozen=True)
class EnemySim:
    entity_id: str
    hp: int
    max_hp: int
    block: int
    vulnerable: int
    incoming: int  # this enemy's attack damage this turn (0 if not attacking)
    is_minion: bool = False  # "Minion" status: flees when its leader dies, so ignorable
    gains_strength: bool = False  # ramping (Strength buff / Empower intent): race to kill it


@dataclass(frozen=True)
class SimState:
    energy: int
    enemies: tuple[EnemySim, ...]
    my_block: int
    my_strength: int
    barricade: bool = False  # block persists -> stacking it is never waste
    hand_size: int = 0  # full hand size at turn start (for hand-exhaust scaling)
    draws: int = 0
    weak_applied: int = 0
    vuln_applied: int = 0
    strength_gained: int = 0
    damage_dealt: int = 0
    kills: int = 0
    overkill: int = 0
    self_damage: int = 0
    rage_block_active: int = 0  # Rage in play: each later Attack grants this much Block
    rage_block_granted: int = 0  # total Block Rage has granted to attacks (sequencing nudge)
    powers_played: int = 0  # Power cards played this turn (banked permanent buffs)
    ramp_damage: int = 0  # damage dealt to strength-gaining enemies (rewarded: race them)
    played: tuple[tuple[int, str | None], ...] = ()  # (hand index, target entity_id)


def _to_planned(card, energy: int) -> PlannedCard | None:
    if not card.can_play:
        return None
    cost_str = card.cost or "0"
    if cost_str.upper() == "X":
        cost = energy
    else:
        try:
            cost = int(cost_str)
        except ValueError:
            return None
    fx = parse_card_description(card.description)
    # Rage special-case (owner): "Whenever you play an Attack this turn, gain N Block"
    # — so it must be sequenced BEFORE attacks. Encode it so the planner sees that.
    rage_block = 0
    if (card.id or card.name or "").upper().replace(" ", "_") == "RAGE":
        m = _RAGE_BLOCK.search(card.description or "")
        rage_block = int(m.group(1)) if m else 3
        fx.block = 0  # Rage's "gain N Block" is conditional (per Attack), not immediate
    # Fiend Fire & kin (owner special-case): damage scales with cards exhausted.
    desc = card.description or ""
    hand_exhaust_scale = 0
    if "exhaust" in desc.lower() and (m := _HAND_EXHAUST_DMG.search(desc)):
        hand_exhaust_scale = int(m.group(1))
    is_power = card.type == "Power"
    # Per-turn powers (Pyre "+1 Energy at the start of each turn", Demon Form "+Str at the
    # start of turn") don't fire the turn you play them; the text parser reads their numbers
    # as immediate, over-valuing them and mis-planning this turn's energy. Bank via w_power.
    if is_power and any(s in desc.lower() for s in ("start of", "each turn", "every turn")):
        fx.block = fx.energy_gain = fx.strength = 0
    return PlannedCard(
        index=card.index,
        name=card.name,
        cost=cost,
        fx=fx,
        targets_enemy=(card.target_type == "AnyEnemy"),
        is_attack=(card.type == "Attack"),
        is_power=is_power,
        rage_block=rage_block,
        hand_exhaust_scale=hand_exhaust_scale,
    )


def _enemy_sims(enemies: list[Enemy]) -> tuple[EnemySim, ...]:
    sims = []
    for e in enemies:
        if e.hp <= 0:
            continue
        vuln = 0
        is_minion = False
        gains_strength = False
        for p in e.status:
            if p.id.upper() == "VULNERABLE" and p.amount:
                vuln = p.amount
            if "MINION" in p.id.upper() or "abandon combat" in (p.description or "").lower():
                is_minion = True
            if "STRENGTH" in p.id.upper() and (p.amount or 0) > 0:
                gains_strength = True
        for i in e.intents:
            if (i.type or "").lower() == "buff" and (
                "empower" in (i.title or "").lower() or "strength" in (i.description or "").lower()
            ):
                gains_strength = True
        incoming = sum(
            parse_intent_damage(i.label) for i in e.intents if i.type.lower() == "attack"
        )
        sims.append(
            EnemySim(
                entity_id=e.entity_id,
                hp=e.hp,
                max_hp=max(e.max_hp, 1),
                block=e.block,
                vulnerable=vuln,
                incoming=incoming,
                is_minion=is_minion,
                gains_strength=gains_strength,
            )
        )
    return tuple(sims)


def _apply_attack(state: SimState, target_i: int, card: PlannedCard) -> SimState:
    enemies = list(state.enemies)
    e = enemies[target_i]
    dealt_total = 0
    hp, block = e.hp, e.block
    per_hit = card.fx.damage + state.my_strength
    if e.vulnerable > 0:
        per_hit = int(per_hit * VULN_MULT)
    for _ in range(card.fx.hits):
        if hp <= 0:
            break
        absorbed = min(block, per_hit)
        block -= absorbed
        dealt = per_hit - absorbed
        hp -= dealt
        dealt_total += dealt
    overkill_amt = -hp if hp < 0 else 0
    killed = hp <= 0 < e.hp
    hp = max(0, hp)
    enemies[target_i] = replace(
        e, hp=hp, block=block, vulnerable=e.vulnerable + card.fx.vulnerable
    )
    # Minions don't end the fight (it ends on the leader) and Illusion ones revive, so
    # damage/kills on them aren't progress — value them only for the incoming their death
    # removes (the score sees that via hp_loss). Offensive reward is for leaders only.
    if e.is_minion:
        return replace(state, enemies=tuple(enemies))
    return replace(
        state,
        enemies=tuple(enemies),
        damage_dealt=state.damage_dealt + dealt_total,
        kills=state.kills + (1 if killed else 0),
        overkill=state.overkill + overkill_amt,
        vuln_applied=state.vuln_applied + (card.fx.vulnerable if hp > 0 else 0),
        ramp_damage=state.ramp_damage + (dealt_total if e.gains_strength else 0),
    )


def _apply_card(state: SimState, card: PlannedCard, target_i: int | None) -> SimState:
    target_id = state.enemies[target_i].entity_id if target_i is not None else None
    # Rage: an Attack played while Rage is already active grants Block.
    rage_bonus = state.rage_block_active if (card.is_attack and state.rage_block_active) else 0
    s = replace(
        state,
        energy=state.energy - card.cost,
        rage_block_active=max(state.rage_block_active, card.rage_block),
        rage_block_granted=state.rage_block_granted + rage_bonus,
        powers_played=state.powers_played + (1 if card.is_power else 0),
        played=(*state.played, (card.index, target_id)),
    )
    atk = card
    if card.hand_exhaust_scale > 0:
        # Fiend Fire & kin: hits once per card still in hand when it resolves
        # (full hand, minus cards already played this turn, minus itself).
        exhausted = max(0, state.hand_size - len(state.played) - 1)
        atk = replace(card, fx=replace(card.fx, damage=card.hand_exhaust_scale, hits=exhausted))
    if atk.fx.total_damage > 0:
        if atk.fx.aoe:
            for i in range(len(s.enemies)):
                if s.enemies[i].hp > 0:
                    s = _apply_attack(s, i, atk)
        elif target_i is not None:
            s = _apply_attack(s, target_i, atk)
    elif card.fx.vulnerable and target_i is not None:
        enemies = list(s.enemies)
        e = enemies[target_i]
        if e.hp > 0:
            enemies[target_i] = replace(e, vulnerable=e.vulnerable + card.fx.vulnerable)
            s = replace(
                s, enemies=tuple(enemies), vuln_applied=s.vuln_applied + card.fx.vulnerable
            )
    if card.fx.weak:
        # apply to the biggest attacker still alive (approximation: weak is defensive)
        enemies = list(s.enemies)
        alive = [i for i, e in enumerate(enemies) if e.hp > 0 and e.incoming > 0]
        if alive:
            i = max(alive, key=lambda i: enemies[i].incoming)
            enemies[i] = replace(enemies[i], incoming=int(enemies[i].incoming * WEAK_MULT))
            s = replace(s, enemies=tuple(enemies), weak_applied=s.weak_applied + card.fx.weak)
    return replace(
        s,
        my_block=s.my_block + card.fx.block + rage_bonus,
        my_strength=s.my_strength + card.fx.strength,
        strength_gained=s.strength_gained + card.fx.strength,
        draws=s.draws + card.fx.draw,
        energy=s.energy + card.fx.energy_gain,
        self_damage=s.self_damage + card.fx.self_hp_cost,
    )


def _score(state: SimState, w: CombatWeights, hp_pct: float = 1.0) -> float:
    incoming = sum(e.incoming for e in state.enemies if e.hp > 0)
    if state.barricade:
        blocked = state.my_block  # persistent block is all future-useful
        excess = 0
    else:
        blocked = min(state.my_block, incoming)
        excess = max(0, state.my_block - incoming)
    hp_loss = incoming - min(state.my_block, incoming) + state.self_damage
    # HP is cheap when full, precious when low (owner: Offering should be played
    # freely when healthy, shelved when hurt)
    hp_weight = w.w_hp_loss * (w.hp_scarcity_base + w.hp_scarcity_slope * (1.0 - hp_pct))
    # quadratic focus-fire reward: concentrated damage beats spread damage, because
    # a finished enemy stops attacking (run 13: spread vs a 4-Nibbit pack = death)
    focus = sum(((e.max_hp - e.hp) / e.max_hp) ** 2 for e in state.enemies if not e.is_minion)
    return (
        w.w_focus * focus
        + w.w_damage * state.damage_dealt
        + w.w_kill * state.kills
        + w.w_overkill * state.overkill
        + w.w_block_useful * blocked
        + w.w_block_excess * excess
        + hp_weight * hp_loss
        + w.w_vulnerable * state.vuln_applied
        + w.w_weak * state.weak_applied
        + w.w_strength * state.strength_gained
        + w.w_draw * state.draws
        + w.w_energy_waste * max(0, state.energy)
        + w.w_play_friction * len(state.played)
        + w.w_power_played * state.powers_played
        + w.w_rage_sequence * state.rage_block_granted
        + w.w_ramp_damage * state.ramp_damage
    )


def plan_combat_turn(state: CombatState, weights: CombatWeights) -> Decision | Wait:
    """Pick the next combat action by searching this turn's play sequences."""
    if state.battle is None:
        return Wait(reason="combat still loading (no battle block yet)")
    player = state.player
    if player is None or not player.in_combat:
        return Wait(reason="combat state without combat player block")
    if state.battle.turn != "player" or state.battle.is_play_phase is False:
        return Wait(reason="not the player's play phase")
    if state.battle.actions_disabled:
        return Wait(reason="player actions disabled (scripted combat moment)")

    hand = player.hand or []
    energy = player.energy or 0
    my_strength = 0
    barricade = False
    for p in player.status:
        if p.id.upper() == "STRENGTH" and p.amount:
            my_strength = p.amount
        if p.id.upper() == "BARRICADE":
            barricade = True

    playable = [c for c in (_to_planned(card, energy) for card in hand) if c is not None]
    if not playable:
        return Decision(action=act.EndTurn(), rationale="no playable cards; end turn")

    start = SimState(
        energy=energy,
        enemies=_enemy_sims(state.battle.enemies),
        my_block=player.block,
        my_strength=my_strength,
        barricade=barricade,
        hand_size=len(hand),
    )
    if not start.enemies:
        return Decision(action=act.EndTurn(), rationale="no living enemies; end turn")

    hp_pct = player.hp / max(1, player.max_hp)
    best_state = start
    best_score = _score(start, weights, hp_pct)
    visited = 0

    def dfs(sim: SimState, remaining: list[PlannedCard]) -> None:
        nonlocal best_state, best_score, visited
        if visited >= weights.max_sequences:
            return
        for ci, card in enumerate(remaining):
            if card.cost > sim.energy:
                continue
            rest = remaining[:ci] + remaining[ci + 1 :]
            if card.targets_enemy and not card.fx.aoe:
                target_idx = [i for i, e in enumerate(sim.enemies) if e.hp > 0]
                # prefer distinct targets; cap target branching at 3 biggest threats
                target_idx.sort(key=lambda i: (-sim.enemies[i].incoming, sim.enemies[i].hp))
                for ti in target_idx[:3]:
                    visited += 1
                    nxt = _apply_card(sim, card, ti)
                    score = _score(nxt, weights, hp_pct)
                    if score > best_score:
                        best_score, best_state = score, nxt
                    dfs(nxt, rest)
            else:
                visited += 1
                nxt = _apply_card(sim, card, None)
                score = _score(nxt, weights, hp_pct)
                if score > best_score:
                    best_score, best_state = score, nxt
                dfs(nxt, rest)

    dfs(start, playable)

    if not best_state.played:
        return Decision(action=act.EndTurn(), rationale="no play improves the turn; end turn")

    first_index, first_target = best_state.played[0]
    chosen = next(c for c in playable if c.index == first_index)
    target = first_target if (chosen.targets_enemy and not chosen.fx.aoe) else None
    if chosen.targets_enemy and not chosen.fx.aoe and target is None:
        alive = [e for e in start.enemies if e.hp > 0]
        target = alive[0].entity_id if alive else None

    plan_names = []
    for idx, _tgt in best_state.played:
        match = next((c for c in playable if c.index == idx), None)
        plan_names.append(match.name if match else f"#{idx}")
    # Fight ends when the leaders die — Minion enemies flee, so they don't gate lethal.
    leaders = [e for e in best_state.enemies if not e.is_minion]
    lethal = all(e.hp <= 0 for e in (leaders or best_state.enemies))
    # Projected HP loss if we follow this line (post-block, post-kill incoming) — lets
    # callers tell "survivable with our own cards" from "actually facing death" so they
    # don't panic-drink a potion the planned block already covers.
    proj_incoming = sum(e.incoming for e in best_state.enemies if e.hp > 0)
    hp_loss = max(0, proj_incoming - best_state.my_block) + best_state.self_damage
    return Decision(
        action=act.PlayCard(card_index=chosen.index, target=target),
        rationale=f"plan [{' > '.join(plan_names)}] score {best_score:.1f}"
        + (" LETHAL" if lethal else "")
        + (f"; first: {chosen.name} -> {target}" if target else f"; first: {chosen.name}"),
        scores={
            "plan_score": round(best_score, 2),
            "explored": float(visited),
            "lethal": 1.0 if lethal else 0.0,
            "hp_loss": float(hp_loss),
        },
    )
