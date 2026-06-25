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
from sts2bot.policy.capability import detect_mechanics
from sts2bot.policy.textparse import CardEffects, parse_card_description, parse_intent_damage

VULN_MULT = 1.5
WEAK_MULT = 0.75
_RAGE_BLOCK = re.compile(r"gain (\d+) block", re.IGNORECASE)
# "Exhaust your hand, deal N damage for each card exhausted" (Fiend Fire): damage
# scales with hand size, so the flat per-hit the text parser sees underprices it.
_HAND_EXHAUST_DMG = re.compile(r"(\d+) damage for each card", re.IGNORECASE)
_PRIMAL_ROCK_DAMAGE = 16  # Primal Force transforms Attacks into Giant Rock (16 damage, 1 cost)


@dataclass(frozen=True)
class PlannedCard:
    index: int
    name: str
    cost: int  # X-cost resolved to current energy at plan time
    fx: CardEffects
    targets_enemy: bool
    is_attack: bool = False
    is_power: bool = False  # Power card: playing it banks a permanent buff (play eagerly)
    self_damage_power: bool = False  # per-turn self-HP power (Inferno): no front-load at low HP
    primal_force: bool = False  # Primal Force: transforms later Attacks into 16-dmg Giant Rocks
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
    summons: bool = False  # has a Summon intent — its minions are replaceable, so race it
    illusion: bool = False  # "Illusion": revives at full HP when killed — grinding it is futile
    # damage-throttling (ENEMY_PASS): first HP-loss/turn -> 1 (Slippery); a hard per-turn HP-loss
    # cap (Hardened Shell, Intangible); thorns per hit. hp_lost_this_turn accrues so the planner
    # stops over-investing (don't dump a big hit into Slippery, don't burst past a cap).
    slippery: bool = False
    dmg_cap_per_turn: int | None = None
    thorns: int = 0
    hp_lost_this_turn: int = 0
    skittish: int = 0  # +Block on its FIRST hit each turn (Skittish); follow-ups get soaked


@dataclass(frozen=True)
class SimState:
    energy: int
    enemies: tuple[EnemySim, ...]
    my_block: int
    my_strength: int
    barricade: bool = False  # block persists -> stacking it is never waste
    has_summoner: bool = False  # an enemy summons minions: chasing the minions is a treadmill
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
    self_damage_powers_played: int = 0  # of those, per-turn self-HP-cost powers (Inferno)
    ramp_damage: int = 0  # damage dealt to strength-gaining enemies (rewarded: race them)
    primal_active: bool = False  # Primal Force played: later Attacks are 16-dmg Giant Rocks
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
    low = desc.lower()
    # Per-turn powers (Pyre "+1 Energy at the start of each turn", Demon Form "+Str at the
    # start of turn") don't fire the turn you play them; the text parser reads their numbers
    # as immediate, over-valuing them and mis-planning this turn's energy. Bank via w_power.
    per_turn_power = is_power and any(s in low for s in ("start of", "each turn", "every turn"))
    if per_turn_power:
        # also zero self_hp_cost: a per-turn power's "lose N HP" is a *next*-turn upkeep drain, not
        # damage you take the turn you play it (the parser reads it as immediate).
        fx.block = fx.energy_gain = fx.strength = fx.self_hp_cost = 0
    # Self-damage powers (Inferno, Crimson Mantle) drain HP at upkeep — strong, but front-loading
    # them at low HP is fatal (the drain lands next turn, which the one-turn tally can't see).
    self_damage_power = per_turn_power and "lose" in low and "hp" in low
    primal_force = "transform all attacks" in low
    return PlannedCard(
        index=card.index,
        name=card.name,
        cost=cost,
        fx=fx,
        targets_enemy=(card.target_type == "AnyEnemy"),
        is_attack=(card.type == "Attack"),
        is_power=is_power,
        self_damage_power=self_damage_power,
        primal_force=primal_force,
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
        summons = False
        illusion = False
        for p in e.status:
            if p.id.upper() == "VULNERABLE" and p.amount:
                vuln = p.amount
            if "MINION" in p.id.upper() or "abandon combat" in (p.description or "").lower():
                is_minion = True
            if "STRENGTH" in p.id.upper() and (p.amount or 0) > 0:
                gains_strength = True
            if "ILLUSION" in p.id.upper() or "revives" in (p.description or "").lower():
                illusion = True
        for i in e.intents:
            text = f"{i.type or ''} {i.title or ''} {i.description or ''}".lower()
            if (i.type or "").lower() == "buff" and (
                "empower" in (i.title or "").lower() or "strength" in (i.description or "").lower()
            ):
                gains_strength = True
            if "summon" in text:
                summons = True
        incoming = sum(
            parse_intent_damage(i.label) for i in e.intents if i.type.lower() == "attack"
        )
        # throttling parsed from the same status text the bestiary harvests (ENEMY_PASS)
        mech = detect_mechanics([{"description": p.description} for p in e.status])
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
                summons=summons,
                illusion=illusion,
                slippery=mech.get("slippery", False),
                dmg_cap_per_turn=mech.get("dmg_cap_per_turn"),
                thorns=mech.get("thorns", 0),
                skittish=mech.get("skittish", 0),
            )
        )
    return tuple(sims)


def _ignorable_minion(e: EnemySim, has_summoner: bool = False) -> bool:
    """A Minion not worth grinding down: race the leader instead — killing the leader makes the
    minions flee. Diverting damage to a minion pays off only when it's a *fixed* escalating threat:
    it ramps (Strength, like the Kin's followers) and isn't re-summoned. Ignore it when anything on
    the board summons (the Ovicopter's eggs/hatchlings — every minion is then replaceable, so
    chasing them is a treadmill), or it's an **Illusion** (revives at full HP when killed, so
    grinding makes no progress). Killing an Illusion only to deny a turn's attack is the deferred
    capability-estimate layer. Minions never gate lethal regardless."""
    if not e.is_minion:
        return False
    if has_summoner or e.illusion:
        return True
    return not e.gains_strength


def _apply_attack(state: SimState, target_i: int, card: PlannedCard) -> SimState:
    enemies = list(state.enemies)
    e = enemies[target_i]
    dealt_total = 0
    hp, block = e.hp, e.block
    lost = e.hp_lost_this_turn  # HP it has already lost this turn (for the per-turn cap)
    slippery_pending = e.slippery and lost == 0  # first HP-loss this turn -> 1
    skittish_pending = e.skittish > 0 and lost == 0  # first hit this turn -> it gains Block
    thorns_taken = 0
    base_damage, hits = card.fx.damage, card.fx.hits
    if state.primal_active and card.is_attack:
        base_damage, hits = _PRIMAL_ROCK_DAMAGE, 1  # transformed into a Giant Rock
    per_hit = base_damage + state.my_strength
    if e.vulnerable > 0:
        per_hit = int(per_hit * VULN_MULT)
    for _ in range(hits):
        if hp <= 0:
            break
        thorns_taken += e.thorns  # "when hit by an attack" retaliates, per hit landed
        absorbed = min(block, per_hit)
        block -= absorbed
        dealt = per_hit - absorbed
        if dealt > 0:
            if slippery_pending:  # Slippery: the first HP-loss this turn drops to 1
                dealt = 1
                slippery_pending = False
            if e.dmg_cap_per_turn is not None:  # Hardened Shell / Intangible: cap HP lost per turn
                dealt = max(0, min(dealt, e.dmg_cap_per_turn - lost))
        hp -= dealt
        dealt_total += dealt
        lost += dealt
        if skittish_pending:  # Skittish: first hit lands, then it gains Block (soaks follow-ups)
            block += e.skittish
            skittish_pending = False
    overkill_amt = -hp if hp < 0 else 0
    killed = hp <= 0 < e.hp
    hp = max(0, hp)
    enemies[target_i] = replace(
        e, hp=hp, block=block, vulnerable=e.vulnerable + card.fx.vulnerable, hp_lost_this_turn=lost
    )
    # Ignorable minions (weak, non-ramping) aren't progress — they flee with the leader and
    # Illusion ones revive — so deny offensive reward; their death's incoming drop is still
    # seen via hp_loss. Dangerous minions (Kin followers etc.) fall through to normal reward.
    if _ignorable_minion(e, state.has_summoner):
        return replace(state, enemies=tuple(enemies), self_damage=state.self_damage + thorns_taken)
    return replace(
        state,
        enemies=tuple(enemies),
        damage_dealt=state.damage_dealt + dealt_total,
        kills=state.kills + (1 if killed else 0),
        overkill=state.overkill + overkill_amt,
        vuln_applied=state.vuln_applied + (card.fx.vulnerable if hp > 0 else 0),
        ramp_damage=state.ramp_damage + (dealt_total if e.gains_strength else 0),
        self_damage=state.self_damage + thorns_taken,
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
        self_damage_powers_played=(
            state.self_damage_powers_played + (1 if card.self_damage_power else 0)
        ),
        primal_active=state.primal_active or card.primal_force,
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


def _score(
    state: SimState, w: CombatWeights, hp_pct: float = 1.0, power_horizon: float = 1.0
) -> float:
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
    focus = sum(
        ((e.max_hp - e.hp) / e.max_hp) ** 2
        for e in state.enemies
        if not _ignorable_minion(e, state.has_summoner)
    )
    # Powers compound over the rest of the fight, so value them by per-turn buff × turns left
    # (power_horizon) — that front-loads them instead of deferring to "spare" energy that never
    # comes. Self-damage powers (Inferno) are the exception: only front-load them while healthy;
    # at low HP their upkeep drain makes eager play dangerous, so fall back to the flat value.
    safe_powers = state.powers_played - state.self_damage_powers_played
    sd_horizon = power_horizon if hp_pct >= w.power_self_damage_hp_safe else 1.0
    power_term = w.w_power_played * (
        safe_powers * power_horizon + state.self_damage_powers_played * sd_horizon
    )
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
        + power_term
        + w.w_rage_sequence * state.rage_block_granted
        + w.w_ramp_damage * state.ramp_damage
    )


# Status cards that bite if left in hand at end of turn — the incoming/block tally misses them. Two
# flavors, modeled DIFFERENTLY: Beckon "lose N HP" is unblockable (straight to HP); Toxic "take N
# damage" is blockable (leftover block soaks it). The caller keyword-gates on "in your hand" + "end
# of" (order/phrasing vary across cards), then these pull the number for the right pool.
_HAND_HP_LOSS_RE = re.compile(r"lose (\d+) hp", re.I)       # Beckon-type: unblockable
_HAND_TAKE_DMG_RE = re.compile(r"take (\d+) damage", re.I)  # Toxic-type: blockable


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
    card_cap = None  # "You can only play N cards this turn" (Ringing): spend it on the best play
    for p in player.status:
        if p.id.upper() == "STRENGTH" and p.amount:
            my_strength = p.amount
        if p.id.upper() == "BARRICADE":
            barricade = True
        if m := re.search(r"only play (\d+) card", p.description or "", re.IGNORECASE):
            card_cap = int(m.group(1)) if card_cap is None else min(card_cap, int(m.group(1)))

    playable = [c for c in (_to_planned(card, energy) for card in hand) if c is not None]
    if not playable:
        return Decision(action=act.EndTurn(), rationale="no playable cards; end turn")

    enemy_sims = _enemy_sims(state.battle.enemies)
    start = SimState(
        energy=energy,
        enemies=enemy_sims,
        my_block=player.block,
        my_strength=my_strength,
        barricade=barricade,
        hand_size=len(hand),
        has_summoner=any(e.summons for e in enemy_sims),
    )
    if not start.enemies:
        return Decision(action=act.EndTurn(), rationale="no living enemies; end turn")

    hp_pct = player.hp / max(1, player.max_hp)
    # Power horizon: estimate turns left in the fight from enemy HP over a quick greedy read of
    # this turn's attack damage (powers excluded -> no circularity), capped. A power's worth scales
    # with it, so it goes down ASAP early and not bothered late. No attacks in hand -> assume long
    # fight (cap), i.e. the turn you can't attack is exactly when you should bank a power.
    enemy_total_hp = sum(e.hp for e in enemy_sims if e.hp > 0)
    budget, base_dmg = energy, 0
    for c in sorted(
        (c for c in playable if c.is_attack and c.fx.damage),
        key=lambda c: c.fx.damage * max(1, c.fx.hits),
        reverse=True,
    ):
        if c.cost <= budget:
            base_dmg += c.fx.damage * max(1, c.fx.hits)
            budget -= c.cost
    remaining_turns = enemy_total_hp / base_dmg if base_dmg else weights.w_power_horizon_cap
    power_horizon = min(weights.w_power_horizon_cap, max(1.0, remaining_turns))
    best_state = start
    best_score = _score(start, weights, hp_pct, power_horizon)
    visited = 0
    # Ringing & kin cap cards/turn; default = hand size (search stays energy-bound). The cap stops
    # the planner *starting* a 2-card plan it can't finish (the live miss: blocked, then couldn't
    # hit); it commits to the single best card by the turn score (a lethal scores huge; a survival-
    # block dodges the death penalty). The fuller call — block now and hit on the clean turn the
    # Beast's Ringing/attack cycle guarantees, or read the draw pile — is deferred to §5-C.
    max_plays = card_cap if card_cap is not None else len(playable)

    def dfs(sim: SimState, remaining: list[PlannedCard], plays_left: int) -> None:
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
                    score = _score(nxt, weights, hp_pct, power_horizon)
                    if score > best_score:
                        best_score, best_state = score, nxt
                    if plays_left > 1:
                        dfs(nxt, rest, plays_left - 1)
            else:
                visited += 1
                nxt = _apply_card(sim, card, None)
                score = _score(nxt, weights, hp_pct, power_horizon)
                if score > best_score:
                    best_score, best_state = score, nxt
                if plays_left > 1:
                    dfs(nxt, rest, plays_left - 1)

    dfs(start, playable, max_plays)

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
    # Status cards stranded in hand hit you at end of turn; the incoming/block tally misses them.
    # Beckon "lose N HP" is unblockable (added straight to hp_loss); Toxic "take N damage" is
    # blockable (joins the incoming pool so leftover block soaks it). Count the *unplayed* ones so
    # hp_loss (and the hail-mary reading it) is honest. Skip on a lethal turn (fight ends first).
    extra_unblockable = 0
    extra_blockable = 0
    if not lethal:
        played_idx = {idx for idx, _ in best_state.played}
        for c in hand:
            if c.index in played_idx:
                continue
            low = (c.description or "").lower()
            if "in your hand" not in low or "end of" not in low:
                continue
            if m := _HAND_HP_LOSS_RE.search(low):
                extra_unblockable += int(m.group(1))
            elif m := _HAND_TAKE_DMG_RE.search(low):
                extra_blockable += int(m.group(1))
    hp_loss = (max(0, proj_incoming + extra_blockable - best_state.my_block)
               + best_state.self_damage + extra_unblockable)
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
