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

from dataclasses import dataclass, replace

from sts2bot.client import actions as act
from sts2bot.client.models import CombatState, Enemy
from sts2bot.kb.config import CombatWeights
from sts2bot.policy.base import Decision, Wait
from sts2bot.policy.textparse import CardEffects, parse_card_description, parse_intent_damage

VULN_MULT = 1.5
WEAK_MULT = 0.75


@dataclass(frozen=True)
class PlannedCard:
    index: int
    name: str
    cost: int  # X-cost resolved to current energy at plan time
    fx: CardEffects
    targets_enemy: bool


@dataclass(frozen=True)
class EnemySim:
    entity_id: str
    hp: int
    max_hp: int
    block: int
    vulnerable: int
    incoming: int  # this enemy's attack damage this turn (0 if not attacking)


@dataclass(frozen=True)
class SimState:
    energy: int
    enemies: tuple[EnemySim, ...]
    my_block: int
    my_strength: int
    draws: int = 0
    weak_applied: int = 0
    vuln_applied: int = 0
    strength_gained: int = 0
    damage_dealt: int = 0
    kills: int = 0
    overkill: int = 0
    self_damage: int = 0
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
    return PlannedCard(
        index=card.index,
        name=card.name,
        cost=cost,
        fx=fx,
        targets_enemy=(card.target_type == "AnyEnemy"),
    )


def _enemy_sims(enemies: list[Enemy]) -> tuple[EnemySim, ...]:
    sims = []
    for e in enemies:
        if e.hp <= 0:
            continue
        vuln = 0
        for p in e.status:
            if p.id.upper() == "VULNERABLE" and p.amount:
                vuln = p.amount
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
    kills = state.kills
    overkill = state.overkill
    if hp <= 0 < e.hp:
        kills += 1
        overkill += -hp
        hp = 0
    enemies[target_i] = replace(
        e,
        hp=hp,
        block=block,
        vulnerable=e.vulnerable + card.fx.vulnerable,
    )
    return replace(
        state,
        enemies=tuple(enemies),
        damage_dealt=state.damage_dealt + dealt_total,
        kills=kills,
        overkill=overkill,
        vuln_applied=state.vuln_applied + (card.fx.vulnerable if hp > 0 else 0),
    )


def _apply_card(state: SimState, card: PlannedCard, target_i: int | None) -> SimState:
    target_id = state.enemies[target_i].entity_id if target_i is not None else None
    s = replace(
        state,
        energy=state.energy - card.cost,
        played=(*state.played, (card.index, target_id)),
    )
    if card.fx.total_damage > 0:
        if card.fx.aoe:
            for i in range(len(s.enemies)):
                if s.enemies[i].hp > 0:
                    s = _apply_attack(s, i, card)
        elif target_i is not None:
            s = _apply_attack(s, target_i, card)
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
        my_block=s.my_block + card.fx.block,
        my_strength=s.my_strength + card.fx.strength,
        strength_gained=s.strength_gained + card.fx.strength,
        draws=s.draws + card.fx.draw,
        energy=s.energy + card.fx.energy_gain,
        self_damage=s.self_damage + card.fx.self_hp_cost,
    )


def _score(state: SimState, w: CombatWeights) -> float:
    incoming = sum(e.incoming for e in state.enemies if e.hp > 0)
    blocked = min(state.my_block, incoming)
    hp_loss = incoming - blocked + state.self_damage
    # quadratic focus-fire reward: concentrated damage beats spread damage, because
    # a finished enemy stops attacking (run 13: spread vs a 4-Nibbit pack = death)
    focus = sum(((e.max_hp - e.hp) / e.max_hp) ** 2 for e in state.enemies)
    return (
        w.w_focus * focus
        + w.w_damage * state.damage_dealt
        + w.w_kill * state.kills
        + w.w_overkill * state.overkill
        + w.w_block_useful * blocked
        + w.w_block_excess * max(0, state.my_block - incoming)
        + w.w_hp_loss * hp_loss
        + w.w_vulnerable * state.vuln_applied
        + w.w_weak * state.weak_applied
        + w.w_strength * state.strength_gained
        + w.w_draw * state.draws
        + w.w_energy_waste * max(0, state.energy)
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
    for p in player.status:
        if p.id.upper() == "STRENGTH" and p.amount:
            my_strength = p.amount

    playable = [c for c in (_to_planned(card, energy) for card in hand) if c is not None]
    if not playable:
        return Decision(action=act.EndTurn(), rationale="no playable cards; end turn")

    start = SimState(
        energy=energy,
        enemies=_enemy_sims(state.battle.enemies),
        my_block=player.block,
        my_strength=my_strength,
    )
    if not start.enemies:
        return Decision(action=act.EndTurn(), rationale="no living enemies; end turn")

    best_state = start
    best_score = _score(start, weights)
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
                    score = _score(nxt, weights)
                    if score > best_score:
                        best_score, best_state = score, nxt
                    dfs(nxt, rest)
            else:
                visited += 1
                nxt = _apply_card(sim, card, None)
                score = _score(nxt, weights)
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
    return Decision(
        action=act.PlayCard(card_index=chosen.index, target=target),
        rationale=f"plan [{' > '.join(plan_names)}] score {best_score:.1f}"
        + (f"; first: {chosen.name} -> {target}" if target else f"; first: {chosen.name}"),
        scores={"plan_score": round(best_score, 2), "explored": float(visited)},
    )
