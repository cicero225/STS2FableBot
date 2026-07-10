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
FRAIL_MULT = 0.75  # Frail: block I gain from cards is reduced by 25%
_RAGE_BLOCK = re.compile(r"gain (\d+) block", re.IGNORECASE)
# "Exhaust your hand, deal N damage for each card exhausted" (Fiend Fire): damage
# scales with hand size, so the flat per-hit the text parser sees underprices it.
_HAND_EXHAUST_DMG = re.compile(r"(\d+) damage for each card", re.IGNORECASE)
_PRIMAL_ROCK_DAMAGE = 16  # Primal Force transforms Attacks into Giant Rock (16 damage, 1 cost)
# An enemy in its invincible/about-to-explode state (Waterfall Giant's Steam Eruption) is reported
# at a sentinel HP — damage into it is wasted (it dies on its own after the explosion), only block
# matters. Treat any absurd HP as invincible so the planner stops chipping it.
_INVINCIBLE_HP = 100_000_000
_PEN_NIB_PERIOD = 10  # Pen Nib: every 10th attack deals double damage (counter persists per-run)
# Card-pass C tranche (2026-07-09): clustered planner mechanics from the 149-card audit.
_PER_VULN_DMG = re.compile(r"Deals? (\d+) additional damage for each Vulnerable", re.IGNORECASE)
_PER_VULN_STR = re.compile(r"Gain (\d+) Strength for each Vulnerable", re.IGNORECASE)
_DOUBLE_VULN = re.compile(r"Double the enemy's Vulnerable", re.IGNORECASE)
_TARGET_STR_DOWN = re.compile(r"Enemy loses (\d+) Strength this turn", re.IGNORECASE)
_BLOCK_IF_EXHAUSTED = re.compile(r"Gain another (\d+) Block if you have Exhausted", re.IGNORECASE)
_IF_EXHAUSTED_GATE = re.compile(r"If you (?:have )?Exhausted a card this turn", re.IGNORECASE)
_PER_HAND_ATTACK = re.compile(r"for each Attack in your Hand", re.IGNORECASE)
_PER_EXHAUST_PILE = re.compile(
    r"Deals? (\d+) additional damage for each card in your Exhaust Pile", re.IGNORECASE)
_VULN_DMG_REDUCTION = re.compile(r"receive 50% less damage from Vulnerable", re.IGNORECASE)


@dataclass(frozen=True)
class PlannedCard:
    index: int
    name: str
    cost: int  # X-cost resolved to current energy at plan time
    fx: CardEffects
    targets_enemy: bool
    is_attack: bool = False
    # Damage potions ride the DFS as pseudo-cards (0 cost, don't consume the card cap, carry
    # w_potion_spend reluctance) so card+potion LETHALS are weighed against block patterns
    # (owner question 2026-07-09). None = a real hand card.
    potion_slot: int | None = None
    is_power: bool = False  # Power card: playing it banks a permanent buff (play eagerly)
    self_damage_power: bool = False  # per-turn self-HP power (Inferno): no front-load at low HP
    primal_force: bool = False  # Primal Force: transforms later Attacks into 16-dmg Giant Rocks
    rage_block: int = 0  # Rage: block gained per Attack played after it this turn
    hand_exhaust_scale: int = 0  # Fiend Fire: damage per card exhausted from hand (0 = n/a)
    # debuff types this card applies to the *target* enemy, in card-TEXT order (Uppercut = Weak
    # then Vulnerable). Order matters for Artifact, which eats one debuff per unique status.
    debuff_order: tuple[str, ...] = ()
    # C tranche: per-target-Vulnerable scaling (Bully dmg / Dominate Str), Molten Fist's vuln
    # doubling, enemy Strength-down (Dark Shackles/Mangle -> incoming reduction), the
    # exhausted-this-turn conditional pair (Evil Eye block / Forgotten Ritual energy), whether
    # playing this card exhausts one (sets the flag), and Colossus' vuln-damage-reduction.
    dmg_per_target_vuln: int = 0
    str_per_target_vuln: int = 0
    doubles_target_vuln: bool = False
    target_str_down: int = 0
    bonus_block_if_exhausted: int = 0
    energy_requires_exhausted: bool = False
    exhausts_a_card: bool = False
    grants_vuln_reduction: bool = False


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
    slippery_stacks: int = 0  # Slippery charges: each reduces the NEXT HP-loss to 1, then is spent
    dmg_cap_per_turn: int | None = None
    thorns: int = 0
    hp_lost_this_turn: int = 0
    skittish: int = 0  # +Block on its FIRST hit each turn (Skittish); follow-ups get soaked
    artifact: int = 0  # negates the next N debuffs (one per unique status type, magnitude-blind)
    stun_threshold: int = 0  # crossing to/below this HP Stuns it ONCE, skipping its turn (Plow)
    stunned_this_turn: bool = False  # our damage crossed the stun threshold this turn -> it skips
    invincible: bool = False  # sentinel-HP invincible state (Waterfall Giant): damage is wasted
    # Asleep (Lagavulin): chipping it awake forfeits the remaining free setup turns AND sheds its
    # Plating for it (wake removes Plating) — so damage into a sleeper earns NO offensive credit
    # unless the sequence kills it outright (2026-07-09 trace: bot chipped her awake on round 1).
    # NB deliberately NOT applied to Slumber (Beetle) — that stack decrements on HP loss too, so
    # chipping a Slumberer is a different (sometimes correct) call; per-enemy nuance later.
    asleep: bool = False
    # Infested (Phrog Parasite): "Upon dying, summons..." — killing it does NOT end the fight
    # (4 stunned Wrigglers spawn mid-turn). Suppresses the false LETHAL so survival checks and
    # stranded-card tallies stay live on the kill turn (owner question 2026-07-09).
    spawns_on_death: bool = False
    crab_rage: bool = False  # Kaiser Crab claw: when an ally dies, survivors get +6 Str +99 Block
    back_attack: bool = False  # Kaiser Crab: deals +50% from behind while you're Surrounded


@dataclass(frozen=True)
class SimState:
    energy: int
    enemies: tuple[EnemySim, ...]
    my_block: int
    my_strength: int
    my_dex: int = 0  # Dexterity: +/- block per block card (Soul Siphon drives it NEGATIVE)
    # end-of-MY-turn blockable self-damage from player statuses (Knowledge Demon's
    # Disintegration: "At the end of your turn, take N damage") — joins the incoming pool
    # so the planner reserves block for it; skipped on lethal (fight ends first).
    self_end_damage: int = 0
    barricade: bool = False  # block persists -> stacking it is never waste
    my_weak: bool = False  # I'm Weak: my Attacks deal 25% less (Kin Orb of Weakness, etc.)
    my_frail: bool = False  # I'm Frail: Block I gain from cards is 25% less (Kin Orb of Frailty)
    surrounded: bool = False  # Kaiser Crab: a claw behind me deals +50% (gone once one claw dies)
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
    heal_room: int = 0  # max_hp - hp at turn start; caps in-combat healing (no overheal credit)
    healing: int = 0  # capped HP healed this turn (Not Yet); credited via the HP-scarcity curve
    pen_nib_counter: int | None = None  # live Pen Nib attack counter (None = relic absent)
    exhausted_this_turn: bool = False  # a card was Exhausted this turn (Evil Eye/Ritual gates)
    vuln_dmg_reduction: bool = False  # Colossus: 50% less damage from Vulnerable enemies
    potions_spent: int = 0  # pseudo-card potions drunk this plan (each pays w_potion_spend)
    facing: str | None = None  # entity_id of last single-target click (Kaiser Crab back-attack)
    played: tuple[tuple[int, str | None], ...] = ()  # (hand index, target entity_id)


def _to_planned(card, energy: int, hand_attacks: int = 0,
                exhaust_pile: int = 0) -> PlannedCard | None:
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
    # Whirlwind & kin: "Deal N damage to ALL enemies X times" — X-cost resolves to current
    # energy (above), and the hit count is that same X; the parser can't know it, so set it
    # here. Without this Whirlwind read as one hit (4x+ under-valued at high energy).
    if cost_str.upper() == "X" and fx.damage and re.search(r"\bX times", card.description or ""):
        fx.hits = max(1, cost)
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
    # Stranded-status text ("End of your turn, if in your Hand, lose 6 HP" — Beckon/Toxic) is a
    # penalty for NOT playing the card; playing it just discards it. The parser reads the loss
    # as an immediate self-cost, which would exactly cancel the clearing credit in _score (the
    # planner then never clears — the bsmwhj26u Fysh losses). Zero the misread fx.
    if "in your hand" in low and "end of" in low:
        fx.self_hp_cost = 0
        fx.damage = 0
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
    # Debuffs this card lands on its target, in card-text order (for Artifact). Find each
    # status word's position in the description; a present-but-unfound status sorts last.
    debuff_spots = []
    if fx.vulnerable:
        pos = low.find("vulnerab")
        debuff_spots.append((pos if pos >= 0 else len(low), "vulnerable"))
    if fx.weak:
        pos = low.find("weak")
        debuff_spots.append((pos if pos >= 0 else len(low), "weak"))
    debuff_order = tuple(t for _, t in sorted(debuff_spots))
    # C tranche detections (against the audited real texts):
    per_vuln_dmg = int(m.group(1)) if (m := _PER_VULN_DMG.search(desc)) else 0
    per_vuln_str = int(m.group(1)) if (m := _PER_VULN_STR.search(desc)) else 0
    target_str_down = int(m.group(1)) if (m := _TARGET_STR_DOWN.search(desc)) else 0
    block_if_exh = int(m.group(1)) if (m := _BLOCK_IF_EXHAUSTED.search(desc)) else 0
    energy_gated = bool(_IF_EXHAUSTED_GATE.search(desc)) and fx.energy_gain > 0
    if _PER_HAND_ATTACK.search(desc):  # Expect a Fight: energy per Attack in hand
        fx.energy_gain = hand_attacks
        if "energy" not in fx.recognized:
            fx.recognized.append("energy")
    if m := _PER_EXHAUST_PILE.search(desc):  # Ashen Strike: +N per exhaust-pile card
        fx.damage += int(m.group(1)) * exhaust_pile
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
        debuff_order=debuff_order,
        dmg_per_target_vuln=per_vuln_dmg,
        str_per_target_vuln=per_vuln_str,
        doubles_target_vuln=bool(_DOUBLE_VULN.search(desc)),
        target_str_down=target_str_down,
        bonus_block_if_exhausted=block_if_exh,
        energy_requires_exhausted=energy_gated,
        exhausts_a_card="exhaust" in low,
        grants_vuln_reduction=bool(_VULN_DMG_REDUCTION.search(desc)),
    )


def _enemy_sims(enemies: list[Enemy]) -> tuple[EnemySim, ...]:
    sims = []
    for e in enemies:
        if e.hp <= 0:
            continue
        vuln = 0
        artifact = 0
        slippery_stacks = 0
        crab_rage = False
        back_attack = False
        is_minion = False
        gains_strength = False
        summons = False
        illusion = False
        asleep = False
        spawns_on_death = False
        for p in e.status:
            if p.id.upper() == "VULNERABLE" and p.amount:
                vuln = p.amount
            if "ARTIFACT" in p.id.upper() and p.amount:
                artifact = p.amount
            if "CRAB_RAGE" in p.id.upper() or "ally dies" in (p.description or "").lower():
                crab_rage = True
            if "BACK_ATTACK" in p.id.upper() or "from behind" in (p.description or "").lower():
                back_attack = True
            # Slippery carries a stack count (Inklet 1, Vantom 9): each charge drops one HP-loss
            # instance to 1, so multi-hit strips it cheaply and a big single hit is wasted.
            if "SLIPPERY" in p.id.upper():
                slippery_stacks = p.amount if p.amount else 1
            if "MINION" in p.id.upper() or "abandon combat" in (p.description or "").lower():
                is_minion = True
            if "STRENGTH" in p.id.upper() and (p.amount or 0) > 0:
                gains_strength = True
            if "ILLUSION" in p.id.upper() or "revives" in (p.description or "").lower():
                illusion = True
            if p.id.upper().startswith("ASLEEP"):  # Asleep only — Slumber wakes differently
                asleep = True
            low_desc = (p.description or "").lower()
            if "INFESTED" in p.id.upper() or ("dying" in low_desc and "summon" in low_desc):
                spawns_on_death = True
        for i in e.intents:
            text = f"{i.type or ''} {i.title or ''} {i.description or ''}".lower()
            if (i.type or "").lower() == "buff" and (
                "empower" in (i.title or "").lower() or "strength" in (i.description or "").lower()
            ):
                gains_strength = True
            if "summon" in text:
                summons = True
        # Count damage from Attack AND DeathBlow intents. The Waterfall Giant's Steam-Eruption
        # explosion telegraphs as a "DeathBlow" (the boss goes invincible at an HP sentinel, then
        # hits for the whole stack), which the attack-only filter missed -> the bot saw 0 incoming
        # and neither blocked nor hail-mary'd a blatant lethal (owner). Extend the set if other
        # damage-intent types surface.
        incoming = sum(
            parse_intent_damage(i.label)
            for i in e.intents
            if (i.type or "").lower() in ("attack", "deathblow")
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
                slippery_stacks=slippery_stacks,
                dmg_cap_per_turn=mech.get("dmg_cap_per_turn"),
                thorns=mech.get("thorns", 0),
                skittish=mech.get("skittish", 0),
                artifact=artifact,
                stun_threshold=mech.get("stun_threshold", 0),
                invincible=e.hp >= _INVINCIBLE_HP,
                crab_rage=crab_rage,
                back_attack=back_attack,
                asleep=asleep,
                spawns_on_death=spawns_on_death,
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


def _enemy_attacking(e: EnemySim) -> bool:
    """Will this enemy's intent actually land this turn? No if dead, or if our damage crossed its
    stun threshold this turn (Ceremonial Beast's Plow / Terror Eel) — the planner can deliberately
    attack to the threshold to cancel an otherwise-lethal hit. The stun is ONE-TIME and crossing-
    based: an enemy that *began* the turn already below its threshold (it already used the stun and
    is now awake) attacks per its live intent, so we key off the crossing, not the HP level."""
    if e.hp <= 0:
        return False
    return not e.stunned_this_turn


def _apply_attack(
    state: SimState, target_i: int, card: PlannedCard, pen_double: bool = False
) -> SimState:
    enemies = list(state.enemies)
    e = enemies[target_i]
    # Invincible (Waterfall Giant mid-explosion): damage is wasted — it dies on its own after the
    # eruption. Charge the energy (already spent by the caller) but credit no progress so the
    # planner spends its cards on block/mitigation instead of chipping an unkillable wall.
    if e.invincible:
        return state
    dealt_total = 0
    hp, block = e.hp, e.block
    lost = e.hp_lost_this_turn  # HP it has already lost this turn (for the per-turn cap)
    slip = e.slippery_stacks  # Slippery charges left (each reduces one HP-loss instance to 1)
    skittish_pending = e.skittish > 0 and lost == 0  # first hit this turn -> it gains Block
    thorns_taken = 0
    base_damage, hits = card.fx.damage, card.fx.hits
    if state.primal_active and card.is_attack:
        base_damage, hits = _PRIMAL_ROCK_DAMAGE, 1  # transformed into a Giant Rock
    per_hit = base_damage + state.my_strength
    if card.dmg_per_target_vuln:  # Bully: +N per Vulnerable already on the target
        per_hit += card.dmg_per_target_vuln * e.vulnerable
    if pen_double:
        per_hit *= 2  # Pen Nib's 10th attack: double the (post-Strength) per-hit damage
    if state.my_weak:
        per_hit = int(per_hit * WEAK_MULT)  # I'm Weak: my Attacks deal 25% less
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
            if slip > 0:  # Slippery: this HP-loss instance drops to 1 and spends a charge
                dealt = 1
                slip -= 1
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
    # Plow stun: if this attack crossed the threshold (from above to at/below), it's stunned and
    # skips its next turn — one-time, so we key off the crossing (started above) not the HP level.
    stunned = e.stunned_this_turn or bool(
        e.stun_threshold and e.hp > e.stun_threshold and hp <= e.stun_threshold
    )
    enemies[target_i] = replace(
        e, hp=hp, block=block, vulnerable=e.vulnerable + card.fx.vulnerable,
        hp_lost_this_turn=lost, stunned_this_turn=stunned, slippery_stacks=slip,
    )
    # Ignorable minions (weak, non-ramping) aren't progress — they flee with the leader and
    # Illusion ones revive — so deny offensive reward; their death's incoming drop is still
    # seen via hp_loss. Dangerous minions (Kin followers etc.) fall through to normal reward.
    if _ignorable_minion(e, state.has_summoner):
        return replace(state, enemies=tuple(enemies), self_damage=state.self_damage + thorns_taken)
    # Chipping a sleeper awake forfeits its remaining free setup turns (and Lagavulin sheds her
    # Plating FOR you on wake) — the attack is a complete no-op in sim unless it kills outright:
    # the HP change is NOT applied (a partial deny leaked reward through _score's focus term —
    # live leak, batch bnyka47dn run 3: Volley/Tremble woke her on round 1), so the planner
    # spends sleep turns on powers/block/clears. Conservative side effect: multi-card lethals
    # THROUGH the sleep window must kill from full HP (acceptable — rare at boss HP).
    if e.asleep and not killed:
        enemies[target_i] = e  # restore untouched: no hp/block progress to leak anywhere
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
    # Kaiser Crab facing: any single-target click turns you to face that enemy, so the OTHER claw
    # takes the +50% back-attack. AoE doesn't rotate. What matters is who you face LAST this turn
    # (owner), so just track the most recent single-target target through the sequence.
    facing = target_id if target_i is not None else state.facing
    s = replace(
        state,
        energy=state.energy - card.cost,
        potions_spent=state.potions_spent + (1 if card.potion_slot is not None else 0),
        rage_block_active=max(state.rage_block_active, card.rage_block),
        rage_block_granted=state.rage_block_granted + rage_bonus,
        powers_played=state.powers_played + (1 if card.is_power else 0),
        self_damage_powers_played=(
            state.self_damage_powers_played + (1 if card.self_damage_power else 0)
        ),
        primal_active=state.primal_active or card.primal_force,
        facing=facing,
        played=(*state.played, (card.index, target_id)),
    )
    # Pen Nib: count attack cards; the one whose counter rolls past a multiple of 10 doubles.
    pen_double = False
    if card.is_attack and s.pen_nib_counter is not None:
        pen_double = (s.pen_nib_counter % _PEN_NIB_PERIOD) == _PEN_NIB_PERIOD - 1
        s = replace(s, pen_nib_counter=s.pen_nib_counter + 1)
    # Resolve this card's debuffs against the target's Artifact: card-text order, one strip per
    # unique status (magnitude-blind), eaten debuffs don't land. So a debuff dumped into Artifact
    # scores ~0 (Dominate into Artifact 2 = waste); a multi-status card (Uppercut) strips two.
    landed_vuln, landed_weak = card.fx.vulnerable, card.fx.weak
    if target_i is not None and card.debuff_order:
        e = s.enemies[target_i]
        art = e.artifact
        lv = lw = 0
        for typ in card.debuff_order:
            if art > 0:
                art -= 1
            elif typ == "vulnerable":
                lv = card.fx.vulnerable
            else:
                lw = card.fx.weak
        landed_vuln, landed_weak = lv, lw
        if art != e.artifact:
            enemies = list(s.enemies)
            enemies[target_i] = replace(e, artifact=art)
            s = replace(s, enemies=tuple(enemies))
    atk = card
    if card.hand_exhaust_scale > 0:
        # Fiend Fire & kin: hits once per card still in hand when it resolves
        # (full hand, minus cards already played this turn, minus itself).
        exhausted = max(0, state.hand_size - len(state.played) - 1)
        atk = replace(card, fx=replace(card.fx, damage=card.hand_exhaust_scale, hits=exhausted))
    # bake the post-Artifact Vulnerable into the attack so _apply_attack lands the right amount
    if atk.fx.vulnerable != landed_vuln:
        atk = replace(atk, fx=replace(atk.fx, vulnerable=landed_vuln))
    if atk.fx.total_damage > 0:
        if atk.fx.aoe:
            for i in range(len(s.enemies)):
                if s.enemies[i].hp > 0:
                    s = _apply_attack(s, i, atk, pen_double=pen_double)
        elif target_i is not None:
            s = _apply_attack(s, target_i, atk, pen_double=pen_double)
    elif landed_vuln and target_i is not None:
        enemies = list(s.enemies)
        e = enemies[target_i]
        if e.hp > 0:
            enemies[target_i] = replace(e, vulnerable=e.vulnerable + landed_vuln)
            s = replace(s, enemies=tuple(enemies), vuln_applied=s.vuln_applied + landed_vuln)
    if landed_weak:
        enemies = list(s.enemies)
        if target_i is not None and enemies[target_i].hp > 0:
            # Weak lands on the struck/targeted enemy (Uppercut), per Artifact resolution
            i = target_i
        else:
            # Untargeted Weak: approximate onto the biggest attacker still alive (defensive)
            alive = [i for i, e in enumerate(enemies) if e.hp > 0 and e.incoming > 0]
            i = max(alive, key=lambda i: enemies[i].incoming) if alive else None
        if i is not None:
            enemies[i] = replace(enemies[i], incoming=int(enemies[i].incoming * WEAK_MULT))
            s = replace(s, enemies=tuple(enemies), weak_applied=s.weak_applied + landed_weak)
    # Crab Rage (Kaiser Crab): when a claw dies, every still-living Crab-Rage ally gains +6 Str and
    # +99 Block (one-turn wall). Resolve at *card* granularity (this card's before/after) so an AoE
    # killing BOTH claws at once enrages no one, while a single-target kill buffs the survivor — so
    # the sim sees the survivor can't also be finished this turn (no over-credited double-kill).
    # The kill is still usually good (it ends Surrounded — see the back-attack term); this just
    # prices in the enrage so the planner doesn't *assume* it can punch through the fresh 99 Block.
    if any(e.crab_rage for e in s.enemies):
        pre = {e.entity_id: e.hp for e in state.enemies}
        died_crab = any(e.crab_rage and e.hp <= 0 < pre.get(e.entity_id, 0) for e in s.enemies)
        if died_crab:
            enemies = [
                replace(e, block=e.block + 99, incoming=e.incoming + 6)
                if (e.crab_rage and e.hp > 0)
                else e
                for e in s.enemies
            ]
            s = replace(s, enemies=tuple(enemies))
    # --- C-tranche target mechanics (after damage/debuffs have landed) ---
    if target_i is not None and (card.str_per_target_vuln or card.doubles_target_vuln
                                 or card.target_str_down):
        enemies = list(s.enemies)
        e = enemies[target_i]
        if card.str_per_target_vuln and e.vulnerable > 0:  # Dominate: Str per Vuln stack
            gained = card.str_per_target_vuln * e.vulnerable
            s = replace(s, my_strength=s.my_strength + gained,
                        strength_gained=s.strength_gained + gained)
        if card.doubles_target_vuln and e.vulnerable > 0 and e.hp > 0:  # Molten Fist
            enemies[target_i] = replace(e, vulnerable=e.vulnerable * 2)
            s = replace(s, enemies=tuple(enemies),
                        vuln_applied=s.vuln_applied + e.vulnerable)
            e = enemies[target_i]
        if card.target_str_down and e.incoming > 0:  # Dark Shackles/Mangle: -N Str this turn
            enemies[target_i] = replace(e, incoming=max(0, e.incoming - card.target_str_down))
            s = replace(s, enemies=tuple(enemies))
    # In-combat healing (Not Yet), capped at the turn's damage taken — no overheal credit.
    heal_applied = max(0, min(card.fx.heal, s.heal_room - s.healing)) if card.fx.heal else 0
    # Dexterity adds/subtracts per block-granting card — Soul Siphon drives it NEGATIVE, so a
    # drained Defend really grants less (the planner over-blocked-on-paper vs Lagavulin without
    # this). Then Frail cuts the result by 25% — the floor matches the game.
    base_block = card.fx.block
    if card.bonus_block_if_exhausted and s.exhausted_this_turn:  # Evil Eye's second half
        base_block += card.bonus_block_if_exhausted
    if base_block and s.my_dex:
        base_block = max(0, base_block + s.my_dex)
    block_gain = base_block + rage_bonus
    if s.my_frail and block_gain:
        block_gain = int(block_gain * FRAIL_MULT)
    # Forgotten Ritual: the energy fires only if a card was Exhausted this turn
    energy_gain = card.fx.energy_gain
    if card.energy_requires_exhausted and not s.exhausted_this_turn:
        energy_gain = 0
    return replace(
        s,
        my_block=s.my_block + block_gain,
        my_strength=s.my_strength + card.fx.strength,
        strength_gained=s.strength_gained + card.fx.strength,
        draws=s.draws + card.fx.draw,
        energy=s.energy + energy_gain,
        self_damage=s.self_damage + card.fx.self_hp_cost,
        healing=s.healing + heal_applied,
        exhausted_this_turn=s.exhausted_this_turn or card.exhausts_a_card,
        vuln_dmg_reduction=s.vuln_dmg_reduction or card.grants_vuln_reduction,
    )


def _fight_over(enemies) -> bool:
    """All leaders dead AND no dead enemy spawns on death (Infested): the fight truly ends.
    Minions flee with the leader; a dead spawner means a phase 2 is coming mid-turn."""
    leaders = [e for e in enemies if not e.is_minion]
    pool = leaders or list(enemies)
    if any(e.hp > 0 for e in pool):
        return False
    return not any(e.hp <= 0 and e.spawns_on_death for e in enemies)


def _score(
    state: SimState, w: CombatWeights, hp_pct: float = 1.0, power_horizon: float = 1.0,
    stranded_unblockable: dict[int, int] | None = None,
    stranded_blockable: dict[int, int] | None = None,
    my_hp: int = 999,
) -> float:
    # Lethal end-state (all leaders dead): stranded penalties and the death wall don't apply —
    # the fight ends before end of turn. A dead SPAWNER (Infested) means the fight continues.
    lethal_end = _fight_over(state.enemies)
    # A stunned enemy (dropped to/below its stun threshold this turn) skips its turn, so its
    # intent doesn't land — attacking down to the threshold can cancel an otherwise-lethal hit.
    incoming = sum(
        (e.incoming // 2 if state.vuln_dmg_reduction and e.vulnerable > 0 else e.incoming)
        for e in state.enemies if _enemy_attacking(e)
    )  # Colossus: 50% less damage from Vulnerable enemies this turn
    # Stranded status cards (Beckon "lose N HP" / Toxic "take N damage") bite at end of turn
    # UNLESS played — so the penalty must live in the scored objective, not just the post-hoc
    # hp_loss diagnostic, or the search can never prefer spending energy to clear one (the
    # bsmwhj26u Soul Fysh losses: 3 energy went into ~1-damage Intangible pokes while two
    # Beckons sat in hand for 12 unblockable). Keyed by hand index; a played card's penalty
    # vanishes. Skipped on a lethal end-state (the fight ends before end of turn).
    stranded_unb = stranded_blk = 0
    if (stranded_unblockable or stranded_blockable) and not lethal_end:
        played_idx = {i for i, _ in state.played}
        stranded_unb = sum(
            v for i, v in (stranded_unblockable or {}).items() if i not in played_idx
        )
        stranded_blk = sum(
            v for i, v in (stranded_blockable or {}).items() if i not in played_idx
        )
    incoming += stranded_blk  # Toxic-type is blockable: it joins the incoming pool
    if state.self_end_damage and not lethal_end:  # Disintegration: end-of-turn, blockable
        incoming += state.self_end_damage
    # Kaiser Crab back-attack: while Surrounded with 2+ claws alive, the claw you're NOT facing
    # hits for +50% (labels are base — verified live). You face whoever you single-target-clicked
    # LAST (state.facing); default to facing the biggest hitter (the optimal play, and what the
    # biggest-first targeting tends to do). Killing one claw drops to 1 -> permanently faced -> no
    # +50% (owner: that removal is why killing a claw is usually a boon despite the enrage).
    if state.surrounded:
        back = [e for e in state.enemies if e.back_attack and _enemy_attacking(e)]
        if len(back) >= 2:
            faced = next((e for e in back if e.entity_id == state.facing), None) or max(
                back, key=lambda e: e.incoming
            )
            incoming += int(0.5 * sum(e.incoming for e in back if e is not faced))
    if state.barricade:
        blocked = state.my_block  # persistent block is all future-useful
        excess = 0
    else:
        blocked = min(state.my_block, incoming)
        excess = max(0, state.my_block - incoming)
    # Healing offsets HP lost (Not Yet); net it against the loss so both ride the same scarcity
    # curve — a heal is worth ~nothing at full HP and a lot when low, symmetric with Offering.
    # Stranded Beckon-type damage is unblockable: straight into the loss, past the block math.
    external_loss = (incoming - min(state.my_block, incoming)
                     - state.healing + stranded_unb)
    # HP is cheap when full, precious when low (owner: Offering should be played
    # freely when healthy, shelved when hurt)
    hp_weight = w.w_hp_loss * (w.hp_scarcity_base + w.hp_scarcity_slope * (1.0 - hp_pct))
    # Self-HP costs (Bloodletting, Offering, thorns eaten) are a TEMPO trade, not chip damage
    # (owner 2026-07-09: "play Bloodletting+ as low as 15 hp... unless it led to death"). While
    # the turn's projected end HP stays above the floor they're charged flat-cheap; below it the
    # scarcity curve returns, and a non-lethal turn that projects to <=0 HP hits a hard wall.
    projected_hp = my_hp - external_loss - state.self_damage
    if projected_hp > w.self_hp_cheap_floor:
        self_term = w.w_hp_loss * w.self_hp_cheap_mult * state.self_damage
    else:
        self_term = hp_weight * state.self_damage
    death_wall = w.w_projected_death if (projected_hp <= 0 and not lethal_end) else 0.0
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
    # Crab Rage split: ending a turn with one claw dead and another alive left the survivor a fresh
    # 99 Block for a turn — a small future cost the one-turn tally misses. Only a gentle penalty:
    # killing a claw is usually a BOON (it ends Surrounded; the back-attack term carries that), so
    # this just nudges against a needless split when both could fall ~together (§8.4-B).
    crab = [e for e in state.enemies if e.crab_rage]
    crab_split = (
        w.w_crab_rage_split
        if crab and any(e.hp <= 0 for e in crab) and any(e.hp > 0 for e in crab)
        else 0.0
    )
    return (
        crab_split
        + w.w_focus * focus
        + w.w_damage * state.damage_dealt
        + w.w_kill * state.kills
        + w.w_overkill * state.overkill
        + w.w_block_useful * blocked
        + w.w_block_excess * excess
        + hp_weight * external_loss
        + self_term
        + death_wall
        + w.w_vulnerable * state.vuln_applied
        + w.w_weak * state.weak_applied
        + w.w_strength * state.strength_gained
        + w.w_draw * state.draws
        + w.w_energy_waste * max(0, state.energy)
        + w.w_play_friction * len(state.played)
        + power_term
        + w.w_rage_sequence * state.rage_block_granted
        + w.w_ramp_damage * state.ramp_damage
        + w.w_potion_spend * state.potions_spent
    )


# Status cards that bite if left in hand at end of turn — the incoming/block tally misses them. Two
# flavors, modeled DIFFERENTLY: Beckon "lose N HP" is unblockable (straight to HP); Toxic "take N
# damage" is blockable (leftover block soaks it). The caller keyword-gates on "in your hand" + "end
# of" (order/phrasing vary across cards), then these pull the number for the right pool.
_HAND_HP_LOSS_RE = re.compile(r"lose (\d+) hp", re.I)       # Beckon-type: unblockable
_HAND_TAKE_DMG_RE = re.compile(r"take (\d+) damage", re.I)  # Toxic-type: blockable


def plan_combat_turn(
    state: CombatState, weights: CombatWeights, used_potion_slots: tuple[int, ...] = ()
) -> Decision | Wait:
    """Pick the next combat action by searching this turn's play sequences. Damage potions
    (minus already-used slots) join the search as pseudo-cards so card+potion lethals are
    weighed against block patterns; w_potion_spend keeps them out of non-lethal lines."""
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
    my_weak = my_frail = my_surrounded = False
    card_cap = None  # "You can only play N cards this turn" (Ringing): spend it on the best play
    my_dex = 0
    self_end_damage = 0
    for p in player.status:
        pid = p.id.upper()
        if pid == "STRENGTH" and p.amount:
            my_strength = p.amount
        if "DEXTER" in pid and p.amount:  # DEXTERITY_POWER; negative under Soul Siphon
            my_dex = p.amount
        # Knowledge Demon's Disintegration (and kin): end-of-turn blockable self-damage as a
        # PLAYER status. Parse the amount from the text so escalation (6->7->8) tracks live.
        if m := re.search(r"end of your turn, take (\d+) damage", p.description or "", re.I):
            self_end_damage += int(m.group(1))
        if pid == "BARRICADE":
            barricade = True
        if "SURROUND" in pid:  # Kaiser Crab: a claw behind me deals +50% (back-attack)
            my_surrounded = True
        # My own Weak/Frail throttle this turn's output (the Kin applies both via Orbs); amount is
        # turns remaining, so any positive stack is live now.
        if "WEAK" in pid and (p.amount or 0) > 0:
            my_weak = True
        if "FRAIL" in pid and (p.amount or 0) > 0:
            my_frail = True
        if m := re.search(r"only play (\d+) card", p.description or "", re.IGNORECASE):
            card_cap = int(m.group(1)) if card_cap is None else min(card_cap, int(m.group(1)))
    # Normality (curse) caps from the HAND, not a player status: "You cannot play more than
    # 3 cards this turn." Conservative: we can't source cards-already-played, so the cap is
    # taken as-is (the game's own can_play gates enforce the true remainder on replan) —
    # the win is that the DFS stops planning 5-card lines it can never finish (curses pass).
    # NB (owner): Normality counts RETROACTIVELY — drawing into it mid-turn locks the turn at
    # 3 total plays including cards already played. Unforeseeable at plan time (draws are
    # random); the replan + can_play gates absorb it when it happens.
    for c in hand:
        if m := re.search(r"cannot play more than (\d+) cards", c.description or "",
                          re.IGNORECASE):
            card_cap = int(m.group(1)) if card_cap is None else min(card_cap, int(m.group(1)))

    hand_attacks = sum(1 for c in hand if (c.type or "") == "Attack")
    exhaust_pile = getattr(player, "exhaust_pile_count", None) or 0
    playable = [
        c for c in (_to_planned(card, energy, hand_attacks, exhaust_pile) for card in hand)
        if c is not None
    ]
    # Damage potions as pseudo-cards: 0-cost, exempt from the card cap (potions aren't card
    # plays), negative index -(slot+1) mapped back to UsePotion below. is_attack stays False
    # (no Rage/Pen Nib interaction). Gated on SOMETHING threatening or setting up: at zero
    # board threat the slow card-kill is free, so the potion stays in the belt (owner rule) —
    # reluctance alone can't encode "the fight is already won eventually" on a 1-turn horizon.
    threat_or_setup = any(
        (i.type or "").lower() in ("attack", "deathblow", "buff", "debuff", "summon",
                                   "carddebuff")
        for e in state.battle.enemies if e.hp > 0 for i in e.intents
    )
    if threat_or_setup:
        for potion in state.player.potions or []:
            if potion.can_use_in_combat is False or potion.slot in used_potion_slots:
                continue
            nid = f"{potion.id or ''} {potion.name or ''}".upper()
            if "FOUL" in nid or "GLOWWATER" in nid:  # downside potions (cf. _potion_category)
                continue
            pfx = parse_card_description(potion.description)
            if pfx.total_damage <= 0:
                continue
            playable.append(PlannedCard(
                index=-(potion.slot + 1), name=f"{potion.name} (potion)", cost=0, fx=pfx,
                targets_enemy=not pfx.aoe, potion_slot=potion.slot,
            ))
    if not playable:
        return Decision(action=act.EndTurn(), rationale="no playable cards; end turn")

    # Pen Nib (relic): live attack counter, persists between fights. On a multiple of 9 (i.e. the
    # next attack is the 10th) that attack doubles. Read the counter; absent relic -> None (no-op).
    pen_nib_counter = next(
        (r.counter for r in player.relics
         if r.counter is not None and "PEN" in (r.id or r.name or "").upper().replace(" ", "")
         and "NIB" in (r.id or r.name or "").upper().replace(" ", "")),
        None,
    )
    enemy_sims = _enemy_sims(state.battle.enemies)
    start = SimState(
        energy=energy,
        enemies=enemy_sims,
        my_block=player.block,
        my_strength=my_strength,
        my_dex=my_dex,
        self_end_damage=self_end_damage,
        barricade=barricade,
        my_weak=my_weak,
        my_frail=my_frail,
        surrounded=my_surrounded,
        hand_size=len(hand),
        has_summoner=any(e.summons for e in enemy_sims),
        heal_room=max(0, player.max_hp - player.hp),
        pen_nib_counter=pen_nib_counter,
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
    # Status cards that bite if stranded in hand at end of turn (Beckon unblockable / Toxic
    # blockable), keyed by hand index so the DFS credits a play that clears one. Computed once
    # here; _score drops a card's penalty when its index appears in sim.played.
    stranded_unblockable: dict[int, int] = {}
    stranded_blockable: dict[int, int] = {}
    for c in hand:
        low = (c.description or "").lower()
        if "in your hand" not in low or "end of" not in low:
            continue
        if m := _HAND_HP_LOSS_RE.search(low):
            stranded_unblockable[c.index] = int(m.group(1))
        elif m := _HAND_TAKE_DMG_RE.search(low):
            stranded_blockable[c.index] = int(m.group(1))

    def scored(sim: SimState) -> float:
        return _score(sim, weights, hp_pct, power_horizon,
                      stranded_unblockable, stranded_blockable, my_hp=player.hp)

    best_state = start
    best_score = scored(start)
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
        # Nothing resolves after the killing blow — the fight ends instantly. Without this cut
        # the order-indifferent score credited [kill > Not Yet] the same as [Not Yet > kill],
        # and the bot took lethal with 2 spare energy while a heal sat in hand (owner-caught
        # 2026-07-09). Heal/setup-before-kill lines keep their credit; post-kill lines can't.
        if _fight_over(sim.enemies):
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
                    score = scored(nxt)
                    if score > best_score:
                        best_score, best_state = score, nxt
                    nl = plays_left if card.potion_slot is not None else plays_left - 1
                    if nl > 0:
                        dfs(nxt, rest, nl)
            else:
                visited += 1
                nxt = _apply_card(sim, card, None)
                score = scored(nxt)
                if score > best_score:
                    best_score, best_state = score, nxt
                nl = plays_left if card.potion_slot is not None else plays_left - 1
                if nl > 0:
                    dfs(nxt, rest, nl)

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
    lethal = _fight_over(best_state.enemies)
    # Projected HP loss if we follow this line (post-block, post-kill incoming) — lets
    # callers tell "survivable with our own cards" from "actually facing death" so they
    # don't panic-drink a potion the planned block already covers.
    proj_incoming = sum(e.incoming for e in best_state.enemies if _enemy_attacking(e))
    # Status cards stranded in hand hit you at end of turn; the incoming/block tally misses them.
    # Beckon "lose N HP" is unblockable (added straight to hp_loss); Toxic "take N damage" is
    # blockable (joins the incoming pool so leftover block soaks it). Count the *unplayed* ones so
    # hp_loss (and the hail-mary reading it) is honest. Skip on a lethal turn (fight ends first).
    extra_unblockable = 0
    extra_blockable = 0
    if not lethal:
        played_idx = {idx for idx, _ in best_state.played}
        extra_unblockable = sum(
            v for i, v in stranded_unblockable.items() if i not in played_idx
        )
        extra_blockable = sum(
            v for i, v in stranded_blockable.items() if i not in played_idx
        )
    end_dmg = 0 if lethal else best_state.self_end_damage  # Disintegration, blockable
    hp_loss = (max(0, proj_incoming + extra_blockable + end_dmg - best_state.my_block)
               + best_state.self_damage + extra_unblockable - best_state.healing)
    first_action = (
        act.UsePotion(slot=chosen.potion_slot, target=target)
        if chosen.potion_slot is not None
        else act.PlayCard(card_index=chosen.index, target=target)
    )
    return Decision(
        action=first_action,
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
