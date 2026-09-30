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
from sts2bot.policy.textparse import (
    HITS_EVERYONE,
    CardEffects,
    parse_card_description,
    parse_intent_damage,
)

VULN_MULT = 1.5
WEAK_MULT = 0.75
FRAIL_MULT = 0.75  # Frail: block I gain from cards is reduced by 25%
_RAGE_BLOCK = re.compile(r"gain (\d+) block", re.IGNORECASE)
# "Exhaust your hand, deal N damage for each card exhausted" (Fiend Fire): damage
# scales with hand size, so the flat per-hit the text parser sees underprices it.
_HAND_EXHAUST_DMG = re.compile(r"(\d+) damage for each card", re.IGNORECASE)
# Exhaust COUNTING for Feel No Pain credit (owner check 2026-07-18: FNP block per
# exhaust event was entirely uncredited — Stoke's whole edge is exhaust synergies).
# Deliberately narrow: "when this card is Exhausted" (Drum) must NOT count as
# exhausting on play.
_EX_HAND = re.compile(r"exhaust (?:your hand|all)", re.IGNORECASE)
_EX_ONE = re.compile(r"exhaust (?:a|an|the top|1) ", re.IGNORECASE)
_EX_SELF = re.compile(r"(?:^|\.\s)Exhaust\.(?:\s|$)")
# Thrash-class growth (owner 2026-07-20): "add its damage to this card" = the
# exhausted attack's damage is banked into Thrash's NEXT play, plus the thinning.
# Both are future value the one-turn tally can't see, so the sim's correctly-priced
# per-hit costs (Skittish, thorns) made it look strictly worse than a Strike.
_GROWS_ON_EXHAUST = re.compile(r"add its damage to this card", re.IGNORECASE)
# Howl-from-Beyond class: replays itself from the Exhaust Pile (and reshuffles back),
# so exhausting it is SAFE -- even profitable (owner thought experiment 2026-07-30:
# Thrash eating Howl banks 25 dmg AND fires a free end-of-turn 25 AoE)
_SELF_REPLAYS = re.compile(r"in your Exhaust Pile, play it", re.IGNORECASE)
# Fiddle-class relic (owner 2026-07-31): 'draw 2 at the start of each turn; you may
# NOT draw cards during your turn' -- no player status is surfaced, so the Battle
# Trance NO_DRAW machinery never fires; the sim must start with draws dead.
_RELIC_BLOCKS_DRAW = re.compile(r"not draw (?:any )?cards? during your turn", re.IGNORECASE)
# Throwing Axe (Ancient, owner 2026-08-01): 'The first card you play each combat is
# played an extra time.' Armed-state approximated from piles/energy (no counter API).
_FIRST_CARD_TWICE = re.compile(r"first card you play each combat is played an extra time",
                               re.IGNORECASE)
_PRIMAL_ROCK_DAMAGE = 16  # Primal Force transforms Attacks into Giant Rock (16 damage, 1 cost)
# An enemy in its invincible/about-to-explode state (Waterfall Giant's Steam Eruption) is reported
# at a sentinel HP — damage into it is wasted (it dies on its own after the explosion), only block
# matters. Treat any absurd HP as invincible so the planner stops chipping it.
_INVINCIBLE_HP = 100_000_000
# The eruption's size is invisible (intent null in the invincible phase — live 2026-07-25);
# assume this much blockable incoming so the planner stacks block instead of coasting.
# Owner: entering the blast at 30 HP with 12 block died, so the real number is 42+.
_ERUPTION_ASSUMED_INCOMING = 50
_PEN_NIB_PERIOD = 10  # Pen Nib: every 10th attack deals double damage (counter persists per-run)
# Empirical guard pairs: single-target attacks aimed at the guarded enemy redirect to
# its guard while the guard lives; Skills/debuffs and AoE are NOT redirected. Keys and
# values match on entity_id prefix. VERDICT (2026-07-13 corpus forensics, owner
# skepticism confirmed): NO such mechanic exists — Nectar was hit normally dozens of
# times across 91 Bowlbug fights; the "redirect" appeared in 3/917 attack plays, all in
# the 4x-speed era — a stale-state/interleaving anomaly in the same family as the
# duplicate-submission race (see LoopConfig.duplicate_debounce_ticks). The table stays
# EMPTY; the machinery is kept tested-but-dormant in case a real guard enemy ships.
_GUARD_PAIRS: dict[str, str] = {}

# Kill-priority targets in multi-enemy fights, matched on entity_id substring — extra
# credit for damage into them while others live (the carrier_damage lane). Two cases:
# SHRINKER (owner 2026-07-17): its player-debuff dies with it. ROCKET (Kaiser Crab
# forensics 2026-07-18, 4 f33 deaths): the nuke claw escalates 27→33→49 single hits
# that landed on 0 block in every loss while the bot burst the tamer Crusher instead —
# removing Rocket removes the nukes.
_DEBUFF_CARRIERS = ("SHRINKER", "ROCKET")


@dataclass(frozen=True)
class RelicTrigger:
    """A relic's mid-turn trigger (relic pass R1, audit wf_d0019428-929). Per-turn
    counters fire on every `cadence`-th event this turn; lifetime counters (Nunchaku /
    Tuning Fork — Pen Nib's siblings) continue the live relic counter across combats."""
    kind: str  # attack | skill | power | kill | potion | exhaust
    #          | first_hp_loss_combat | first_self_hp_loss_turn
    cadence: int = 1
    per_turn: bool = True
    counter_start: int = 0  # live relic counter at plan start (lifetime kinds only)
    block: int = 0
    damage: int = 0  # single-target chip (random target -> applied to first living)
    aoe: bool = False  # damage hits ALL living enemies
    draw: int = 0
    energy: int = 0
    strength: int = 0
    dexterity: int = 0
    heal_eq_self_loss: bool = False  # Demon Tongue: heal = the HP just lost


# Trigger table keyed by relic id (live ids from data/relic_catalog.json). Class-B set
# plus the on-Power family and the two lifetime counters; first-per-combat latches
# (Vambrace, Unsettling Lamp, Permafrost, Ruined Helmet, Burning Sticks) are DEFERRED —
# the mod exposes no fired-flag, so they need a conservative arming heuristic first.
_RELIC_TRIGGERS: dict[str, RelicTrigger] = {
    "ORNAMENTAL_FAN": RelicTrigger(kind="attack", cadence=3, block=4),
    "SHURIKEN": RelicTrigger(kind="attack", cadence=3, strength=1),
    "KUNAI": RelicTrigger(kind="attack", cadence=3, dexterity=1),
    "KUSARIGAMA": RelicTrigger(kind="attack", cadence=3, damage=6),
    "DAUGHTER_OF_THE_WIND": RelicTrigger(kind="attack", cadence=1, block=1),
    "LETTER_OPENER": RelicTrigger(kind="skill", cadence=3, damage=5, aoe=True),
    "LOST_WISP": RelicTrigger(kind="power", cadence=1, damage=8, aoe=True),
    "GAME_PIECE": RelicTrigger(kind="power", cadence=1, draw=1),
    "GREMLIN_HORN": RelicTrigger(kind="kill", energy=1, draw=1),
    "REPTILE_TRINKET": RelicTrigger(kind="potion", strength=3),
    "FORGOTTEN_SOUL": RelicTrigger(kind="exhaust", damage=1),
    "CHARONS_ASHES": RelicTrigger(kind="exhaust", damage=3, aoe=True),
    "CENTENNIAL_PUZZLE": RelicTrigger(kind="first_hp_loss_combat", draw=3),
    "DEMON_TONGUE": RelicTrigger(kind="first_self_hp_loss_turn", heal_eq_self_loss=True),
    # Mummified Hand (owner check 2026-08-02): each Power played zeroes a RANDOM
    # hand card's cost FOR THE TURN (owner-confirmed: no cross-turn persistence).
    # +1 energy per Power is the tractable proxy -- EXACT in the deterministic
    # case the owner named (power + one other 1-cost card at 1 energy:
    # power-first now beats card-first in the DFS). Known edges, parked by owner
    # 2026-08-02: over-credits when the freed card goes unplayed or already cost
    # 0; UNDER-credits big discounts (owner's miss case: 3-cost power + 3-cost
    # card at 3 energy -- the real game plays both, the +1 proxy can't afford
    # the second). Exact fix would zero the lone other card's cost when hand
    # size makes the 'random' deterministic.
    "MUMMIFIED_HAND": RelicTrigger(kind="power", cadence=1, energy=1),
    "NUNCHAKU": RelicTrigger(kind="attack", cadence=10, per_turn=False, energy=1),
    "TUNING_FORK": RelicTrigger(kind="skill", cadence=10, per_turn=False, block=7),
}

# Relic pass R2: end-of-turn conditional relics — no mid-turn firing; _score evaluates
# them on the plan's END state (Orichalcum's free block, Cloak Clasp's per-retained-card
# block, Sturdy Clamp's persisting block, Ice Cream's banked energy, ...).
_EOT_RELICS = frozenset({
    "ORICHALCUM", "PARRYING_SHIELD", "CLOAK_CLASP", "SCREAMING_FLAGON", "PAELS_TEARS",
    "ART_OF_WAR", "POCKETWATCH", "SELF_FORMING_CLAY", "STURDY_CLAMP", "ICE_CREAM",
})


def _trigger_fires(trig: RelicTrigger, before: int, after: int) -> int:
    """How many times a cadence counter fires as its count moves before -> after."""
    if trig.per_turn:
        return after // trig.cadence - before // trig.cadence
    return ((trig.counter_start + after) // trig.cadence
            - (trig.counter_start + before) // trig.cadence)


def _apply_trigger_fx(s: SimState, trig: RelicTrigger, times: int,
                      self_loss: int = 0) -> SimState:
    """Apply a fired trigger's effects. Trigger damage is simple block-then-HP chip
    (no Slippery/cap nuance — bounded approximation); AoE hits all living enemies,
    single-target hits the first living one (the game rolls randomly)."""
    if times <= 0:
        return s
    heal = 0
    if trig.heal_eq_self_loss and self_loss > 0:
        heal = max(0, min(self_loss, s.heal_room - s.healing))
    s = replace(
        s,
        my_block=s.my_block + trig.block * times,
        draws=s.draws + (0 if s.no_draw else trig.draw * times),
        energy=s.energy + trig.energy * times,
        my_strength=s.my_strength + trig.strength * times,
        my_dex=s.my_dex + trig.dexterity * times,
        healing=s.healing + heal,
    )
    if trig.damage:
        enemies = list(s.enemies)
        dealt = 0
        kills = 0
        targets = (range(len(enemies)) if trig.aoe
                   else [next((i for i, e in enumerate(enemies) if e.hp > 0), None)])
        for i in targets:
            if i is None or enemies[i].hp <= 0 or enemies[i].invincible:
                continue
            e = enemies[i]
            total = trig.damage * times
            absorbed = min(e.block, total)
            hp_loss = total - absorbed
            new_hp = max(0, e.hp - hp_loss)
            if new_hp == 0 < e.hp:
                kills += 1
            dealt += min(hp_loss, e.hp)
            enemies[i] = replace(e, hp=new_hp, block=e.block - absorbed,
                                 hp_lost_this_turn=e.hp_lost_this_turn + hp_loss)
        s = replace(s, enemies=tuple(enemies), damage_dealt=s.damage_dealt + dealt,
                    kills=s.kills + kills)
    return s


def _fire_relic_triggers(pre: SimState, post: SimState, card: PlannedCard) -> SimState:
    """Run the relic trigger pass for one played card: update play-kind counters, then
    fire every armed trigger the play crossed. Strength/Dexterity gained here correctly
    affects LATER cards in the same plan (SimState carries it forward).

    NB the counters update even with NO trigger relics — Smoggy's one-Skill-per-turn
    cap reads n_skills_played, and the old early return silently froze it at 0 in
    relic-less fights (caught 2026-07-20 while wiring Smoggy)."""
    is_potion = card.potion_slot is not None
    is_attack = card.is_attack
    is_power = card.is_power
    is_skill = not (is_attack or is_power or is_potion)
    n_att = post.n_attacks_played + (1 if is_attack else 0)
    n_sk = post.n_skills_played + (1 if is_skill else 0)
    n_pow = post.n_powers_played + (1 if is_power else 0)
    kills_delta = post.kills - pre.kills
    self_loss = card.fx.self_hp_cost
    s = replace(post, n_attacks_played=n_att, n_skills_played=n_sk,
                n_powers_played=n_pow)
    if not s.relic_triggers:
        return s
    for trig in s.relic_triggers:
        times = 0
        if trig.kind == "attack":
            times = _trigger_fires(trig, n_att - (1 if is_attack else 0), n_att)
        elif trig.kind == "skill":
            times = _trigger_fires(trig, n_sk - (1 if is_skill else 0), n_sk)
        elif trig.kind == "power":
            times = _trigger_fires(trig, s.powers_played - (1 if is_power else 0),
                                   s.powers_played)
        elif trig.kind == "kill":
            times = kills_delta
        elif trig.kind == "potion":
            times = 1 if is_potion else 0
        elif trig.kind == "exhaust":
            times = 1 if card.exhausts_a_card else 0  # Fiend Fire multi-exhaust: 1 (floor)
        elif (trig.kind == "first_hp_loss_combat"
              and self_loss > 0 and s.cent_puzzle_armed):
            times = 1
            s = replace(s, cent_puzzle_armed=False)
        elif (trig.kind == "first_self_hp_loss_turn"
              and self_loss > 0 and s.demon_tongue_armed):
            times = 1
            s = replace(s, demon_tongue_armed=False)
        if times:
            s = _apply_trigger_fx(s, trig, times, self_loss)
    return s
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
    # Battle Trance rider: "cannot draw additional cards this turn" — later
    # in-plan draws are dead (owner trap 2026-07-29, hits Ironclad specifically)
    blocks_draw: bool = False
    # Damage potions ride the DFS as pseudo-cards (0 cost, don't consume the card cap, carry
    # w_potion_spend reluctance) so card+potion LETHALS are weighed against block patterns
    # (owner question 2026-07-09). None = a real hand card.
    potion_slot: int | None = None
    is_power: bool = False  # Power card: playing it banks a permanent buff (play eagerly)
    self_damage_power: bool = False  # per-turn self-HP power (Inferno): no front-load at low HP
    primal_force: bool = False  # Primal Force: transforms later Attacks into 16-dmg Giant Rocks
    # Safe to feed to an active Primal Force (owner 2026-07-18: the transform is a
    # PERMANENT deck rewrite — "upgrade your strikes, but not the attack cards you
    # actually want to keep around"). Strikes and rider-less small attacks are fodder;
    # anything with debuffs/draw/block riders or big base damage is a keeper.
    primal_fodder: bool = False
    self_replays: bool = False  # Howl class: returns from the Exhaust Pile on its own
    reveal_nudge: float = 0.0  # per-remaining-card credit for playing a gamble card early
    # Ashen Strike-class: +N damage per exhaust EVENT within this plan (the live
    # preview already carries the pre-plan pile)
    dmg_per_exhaust_event: int = 0
    # Second Wind (owner death 2026-08-12, run -141919 r11): 'Exhaust all
    # NON-ATTACK cards... Gain 5 Block for each' -- the remaining-hand count
    # included the 2 leftover Strikes, projecting ~49 block where the game
    # gave 27, so no death wall and no hail-mary fired while a tutor potion
    # sat on the belt. Whole-hand exhausters now get their CONCRETE count in
    # the DFS (where the remaining cards are known), non-attack-aware.
    exhaust_nonattack_only: bool = False
    # Thrash-class (owner catch 2026-08-27, Queen f48 tape): 'Exhaust a random
    # Attack in your Hand' — the DFS must drop an attack from the remaining
    # hand or it plans phantom follow-ups ([Thrash > Strike] with Strike the
    # only other attack = the Fiend Fire bug family)
    exhausts_random_attack: bool = False
    # True Grit / Cinder: 'Exhaust 1 card at random' -- ANY card in hand. Live
    # 2026-09-28 (seed NDW2DDX5LZ, Waterfall Giant eruption 39 vs 29 HP): plan
    # [True Grit > Defend] read 12 block; the random exhaust ate the Defend and
    # the bot died 3 HP short. Defend-first would have lived.
    exhausts_random_card: bool = False
    # Barricade-class (owner catch 2026-08-29, seed-B T1: the plan only
    # learned block-persistence from the live status on REPLAN — same-turn
    # block after the power got no credit at plan time)
    grants_barricade: bool = False
    # Unmovable (owner catch 2026-09-04, Infested Prism T1: the bot blocked
    # BEFORE playing it): 'The first time you gain Block from a card each
    # turn, double the amount gained' -- and it applies the turn it is played,
    # so it must be sequenced ahead of the first block card.
    grants_unmovable: bool = False
    # RandomEnemy target_type (Beat Down): the sim targets it so damage credit
    # lands, but the play is submitted without a click target
    random_target: bool = False
    # Chooser exhausts (True Grit+ 'Exhaust 1 card.', Purity 'up to 3'): the
    # live hand_select prefers statuses/curses, so the DFS credits clearing
    # the worst stranded penalties (Aeonglass Withers — owner 2026-08-28:
    # 'exhausting statuses starts to become very important')
    targeted_exhaust_n: int = 0
    block_per_exhaust: int = 0  # SW-class: Block for each card exhausted
    # Cruelty-class rider ON THE CARD: playing it amplifies vuln damage for the
    # REST of the plan (owner catch 2026-08-12: Cruelty ordered AFTER an attack
    # on a vulnerable enemy -- the bonus only seeded from the ACTIVE status, so
    # the DFS saw no ordering benefit)
    vuln_amp: float = 0.0
    rage_block: int = 0  # Rage: block gained per Attack played after it this turn
    exhaust_count: int = 0  # cards this play exhausts (-1 = remaining hand); FNP credit
    # Queen's Chains of Binding (owner 2026-07-18): first 3 draws each turn are Bound —
    # ONLY ONE Bound card is playable per turn (keyword on the hand card; un-Bound at
    # end of turn; transform strips it). Plans sequencing 2+ Bound cards fizzled at the
    # gate, Normality-style.
    bound: bool = False
    # Thrash-class: play bonus for growth+thinning, granted post-build only when
    # every OTHER attack in hand is fodder (owner's rule: never risk the random
    # exhaust eating a keeper; the DFS's natural ordering covers the played ones).
    grows_on_exhaust: bool = False
    growth_bonus: float = 0.0
    is_skill: bool = False  # card.type == "Skill" (for Smoggy's one-Skill-per-turn cap)
    # Duplicator Potion (owner 2026-08-02): drinking arms a one-shot 'next card
    # is played an extra time' -- a pseudo-card the DFS sequences before the play
    # worth doubling (toggle cards like Barricade replay for ~nothing naturally:
    # their parsed fx is empty, so the second application adds ~0)
    arms_duplicate: bool = False
    # Cascade/Havoc-class: 'play the top card(s) of your draw pile'. Those plays
    # COUNT AGAINST Ringing-class card caps (owner 2026-08-03), so under a cap
    # the card burns a slot for nothing and is vetoed from the pool. (Replay
    # enchant copies are cap-EXEMPT, owner-confirmed -- the sim's replay
    # bookkeeping already models them without consuming plays.) Cascade value
    # is otherwise unmodeled today; this veto future-proofs the cap interaction
    # for whenever it gets priced.
    plays_top_cards: bool = False
    # Play-from-pile count (Havoc 1; Cascade X+1 resolved at plan time).
    # Owner catch 2026-08-29 (seed-B T5): Cascade+ at 0 energy is a FREE
    # random card — an unplayable Wither cascaded simply discards ('free
    # real estate') — but the class parsed to zero effects and carried no
    # credit anywhere, so the bot never played it (and drafts it at 0%).
    plays_pile_n: int = 0
    # X-cost dynamic (owner 2026-08-29, seed-B: Rampage-then-Whirlwind was
    # undiscoverable — X baked to turn-start energy made pre-X plans read
    # unaffordable and X-first stranded the rest)
    is_x_cost: bool = False
    # Cascade-class 'Play the top X(+1) cards': the count scales with the
    # energy AT PLAY POSITION (owner catch 2026-09-11, Test Subject death
    # turn: Cascade+ at X=0 chosen over Bloodletting -> Cascade+ at X=3, because
    # the static parse read every X as one card)
    pile_plays_scale_x: bool = False
    pile_plays_bonus: int = 0
    # Stampede power (owner trap, noted long ago, implemented 2026-08-23):
    # its end-of-turn random attack hits a RANDOM enemy, flipping facing --
    # vs Kaiser back-attack claws that's a +50% incoming tax you no longer
    # control. Playing it there gets docked; often better held or exhausted.
    stampede_power: bool = False
    # Fortifier Potion (owner 2026-08-03): 'Triple your current Block' -- a DFS
    # pseudo-card whose value depends on in-plan block, so the planner SEQUENCES
    # it (Defend > Defend > Fortifier) instead of guessing a drink lane.
    triples_block: bool = False
    hand_exhaust_scale: int = 0  # Fiend Fire: damage per card exhausted from hand (0 = n/a)
    # debuff types this card applies to the *target* enemy, in card-TEXT order (Uppercut = Weak
    # then Vulnerable). Order matters for Artifact, which eats one debuff per unique status.
    debuff_order: tuple[str, ...] = ()
    # C tranche: per-target-Vulnerable scaling (Bully dmg / Dominate Str), Molten Fist's vuln
    # doubling, enemy Strength-down (Dark Shackles/Mangle -> incoming reduction), the
    # exhausted-this-turn conditional pair (Evil Eye block / Forgotten Ritual energy), whether
    # playing this card exhausts one (sets the flag), and Colossus' vuln-damage-reduction.
    dmg_per_target_vuln: int = 0
    dmg_per_unique_debuff: int = 0  # Rend (item 80): +N per unique debuff on target
    str_per_target_vuln: int = 0
    doubles_target_vuln: bool = False
    target_str_down: int = 0
    bonus_block_if_exhausted: int = 0
    energy_requires_exhausted: bool = False
    exhausts_a_card: bool = False
    grants_vuln_reduction: bool = False
    # Feed-class "If Fatal, ..." rider: landing the KILL with this card pays a permanent
    # bonus, so _score nudges sequencing toward it (step-1 audit, owner-confirmed 07-12)
    on_fatal_bonus: bool = False
    # Frantic Escape at current cost <=1 (owner rule: extend the Sandpit clock
    # every turn while cheap; the cost escalates +1 per play as the brake)
    frantic_escape: bool = False
    # The game's own target_type says a click-target is REQUIRED — independent of the
    # aoe damage model. Omnislice ("Damage ALL other enemies...") is aoe in the sim but
    # target_type=AnyEnemy in the game; submitting it targetless C5-halted a batch
    # (2026-07-13, Louse Progenitor f29).
    requires_target: bool = False
    # Armaments-class "Upgrade a card / ALL cards in your Hand": number of hand cards
    # this play would upgrade (computed at plan time) — otherwise the rider is invisible
    # and the card sits unplayed at friction cost (owner-caught 2026-07-13). The actual
    # upgraded effects materialize via replan; this credit just gets it PLAYED.
    upgrades_in_hand: int = 0


REATTACH_REVIVE_HP = 25  # Decimillipede segment revive HP (bestiary status text)


@dataclass(frozen=True)
class EnemySim:
    entity_id: str
    hp: int
    max_hp: int
    block: int
    vulnerable: int
    incoming: int  # this enemy's attack damage this turn (0 if not attacking)
    name: str = ""  # display name (guarded-leader table lookups)
    is_minion: bool = False  # "Minion" status: flees when its leader dies, so ignorable
    gains_strength: bool = False  # ramping (Strength buff / Empower intent): race to kill it
    is_big: bool = False  # the fight's largest max-HP body — the "focus" plan's target
    # Bygone Effigy's Slow (owner 2026-08-01): 'Whenever you play a card, this
    # enemy receives 10% more damage from Attacks this turn.' None = absent;
    # otherwise the stacks ALREADY accumulated this turn (status amount).
    # Direct attacks only; bonus floors (6 dmg needs 2 stacks to reach 7).
    slow_stacks: int | None = None
    # Its player-debuff dies with it (owner 2026-07-17: Shrinker Beetle's big damage
    # debuff lifts on its death) — racing it down pays while OTHER enemies still live.
    debuff_carrier: bool = False
    # Waterfall Giant death-eruption (owner-confirmed 2026-07-18): at 0 HP he always
    # erupts for his Steam stack — but 1-2 turns LATER, telegraphed as a DeathBlow
    # intent from the invincible phase, so the EXISTING DeathBlow-intent incoming lane
    # prices the block-up turn. Killing ASAP is correct (smaller stack); no same-turn
    # debt coupling (tried and reverted — it made the planner stall on kill turns).
    # The remaining levers are draft-side: WATERFALL boss rule + rest-gate bump.
    # Intangible: all damage instances into it become 1 (Soul Fysh's periodic shield
    # turns, 2026-07-18: two Strikes into it dealt 2 total while Beckons piled up —
    # the planner now spends those turns blocking/clearing instead of attacking).
    intangible: bool = False
    incoming_hits: int = 0  # number of attack instances aimed at us this turn (retaliation math)
    summons: bool = False  # has a Summon intent — its minions are replaceable, so race it
    illusion: bool = False  # "Illusion": revives at full HP when killed — grinding it is futile
    # Decimillipede 'Reattach' (bestiary text, 2026-09-03): 'If other segments
    # are still alive, revives in 2 turns with 25 HP.' A segment kill that
    # leaves other segments alive is futile (it comes back) -- the fight is won
    # by lowering every segment into range and killing them together.
    reattach: bool = False
    # damage-throttling (ENEMY_PASS): first HP-loss/turn -> 1 (Slippery); a hard per-turn HP-loss
    # cap (Hardened Shell, Intangible); thorns per hit. hp_lost_this_turn accrues so the planner
    # stops over-investing (don't dump a big hit into Slippery, don't burst past a cap).
    slippery_stacks: int = 0  # Slippery charges: each reduces the NEXT HP-loss to 1, then is spent
    # Flutter-class (Thieving Hopper, owner-audit find 2026-08-06): 'Receives 50%
    # less damage from Attacks' -- unparsed, it produced FALSE LETHALS (sim 36 vs
    # game ~17 vs 24 HP) that suppressed survival lanes two turns running
    attack_dmg_mult: float = 1.0
    dmg_cap_per_turn: int | None = None
    thorns: int = 0
    hp_lost_this_turn: int = 0
    skittish: int = 0  # +Block on its FIRST hit each turn (Skittish); follow-ups get soaked
    artifact: int = 0  # negates the next N debuffs (one per unique status type, magnitude-blind)
    # Rend (audit item 80, owner): count of UNIQUE debuffs on the enemy at
    # plan start (stacking more of one adds nothing). Known family per owner:
    # vulnerable, weak, poison, doom, shrunken, str-down. In-plan additions
    # are NOT counted (conservative).
    debuff_count: int = 0
    stun_threshold: int = 0  # crossing to/below this HP Stuns it ONCE, skipping its turn (Plow)
    stunned_this_turn: bool = False  # our damage crossed the stun threshold this turn -> it skips
    invincible: bool = False  # sentinel-HP invincible state (Waterfall Giant): damage is wasted
    # Asleep (Lagavulin): chipping it awake forfeits the remaining free setup turns AND sheds its
    # Plating for it (wake removes Plating) — so damage into a sleeper earns NO offensive credit
    # unless the sequence kills it outright (2026-07-09 trace: bot chipped her awake on round 1).
    # NB deliberately NOT applied to Slumber (Beetle) — that stack decrements on HP loss too, so
    # chipping a Slumberer is a different (sometimes correct) call; per-enemy nuance later.
    asleep: bool = False
    # Asleep stacks remaining (the status amount, 3..1): she wakes on her own once
    # they run out, so a waking hit on the LAST asleep turn forfeits nothing.
    asleep_left: int = 0
    # Personal Hive (Entomancer, decoded 2026-09-30): 'Whenever this enemy is hit
    # by an Attack, add 1 Dazed into your Draw Pile' -- per HIT, stacks with
    # Empower. Each landed hit pollutes the deck by `hive` Dazed.
    hive: int = 0
    # Infested (Phrog Parasite): "Upon dying, summons..." — killing it does NOT end the fight
    # (4 stunned Wrigglers spawn mid-turn). Suppresses the false LETHAL so survival checks and
    # stranded-card tallies stay live on the kill turn (owner question 2026-07-09).
    spawns_on_death: bool = False
    crab_rage: bool = False  # Kaiser Crab claw: when an ally dies, survivors get +6 Str +99 Block
    back_attack: bool = False  # Kaiser Crab: deals +50% from behind while you're Surrounded
    # Tunneler: "Block is not removed at the start of Tunneler's turn. Stunned if all
    # Block is removed." — stripping its block to 0 CANCELS its attack (harness-found
    # 2026-07-16: pred 23 -> actual 0 whenever the bot happened to break its block).
    burrowed: bool = False
    # Corpse Slug: "When an enemy dies, Corpse Slug immediately eats it, becoming
    # Stunned and gaining 4 Strength." — killing ONE slug cancels the surviving pack's
    # whole turn (at +4 Str each, priced via ramp next turn). Harness-found 2026-07-16.
    ravenous: bool = False


@dataclass(frozen=True)
class SimState:
    energy: int
    enemies: tuple[EnemySim, ...]
    my_block: int
    my_strength: int
    my_dex: int = 0  # Dexterity: +/- block per block card (Soul Siphon drives it NEGATIVE)
    # Aeonglass Withering Presence (owner decode 2026-08-28): live countdown
    # (the power's amount field) to the next manufactured Wither; 0 = absent.
    # tier_dmg = what a NEW Wither drains per end of turn (escalates with
    # Increasing Intensity casts). withers_incurred = Withers this plan makes.
    wither_countdown: int = 0
    wither_period: int = 0
    wither_tier_dmg: int = 0
    withers_incurred: int = 0
    # exhaust-clears-stranded (owner 2026-08-28: the DFS priced Withers via
    # the stranded class but never connected Stoke/TG+ to REMOVING them)
    hand_purged: bool = False
    # vuln-payoff riders fired on zero stacks (Dominate/Molten Fist class —
    # nearly all self-exhaust, so a dry firing loses the payoff forever)
    vuln_payoff_dry: int = 0
    # unplayable status/curse cards in hand at turn start: chooser/mass
    # exhausts earn w_status_purge per one they can eat (future-cycle value)
    purgeable_in_hand: int = 0
    # cards cascaded from the pile this plan (Havoc/Cascade): credited at
    # w_play_from_pile each; they also tick Withering Presence
    pile_plays: int = 0
    # Deck vuln-dependency multiplier on the artifact-strip credit (owner
    # 2026-08-29 seed-A T3: 'clear underrating of artifact strip... in a
    # deck with this much dependency on Vuln'). 1.0 = the flat baseline.
    artifact_strip_mult: float = 1.0
    targeted_exhausts: int = 0
    # PRE-BAKED MODIFIERS (2026-07-14, trace-verified — the Pen Nib lesson generalized):
    # the mod's card text is a fully-RESOLVED preview. At Str 1 a Strike reads "Deal 7
    # damage"; at Dex 2 a Defend reads "Gain 7 Block" (an Unmovable-doubled Defend+ read
    # 26 = (8+5)x2). So the turn-start Strength/Dex are ALREADY in fx.damage / fx.block:
    # adding my_strength/my_dex again double-counts. Only strength/dex gained DURING this
    # plan (Inflame, Dominate, Shuriken/Kunai triggers) is unbaked and must be applied.
    # These fields hold the baked-in turn-start values; the sim adds only (current - start).
    my_strength_start: int = 0
    my_dex_start: int = 0

    @property
    def str_unbaked(self) -> int:
        """Strength gained mid-plan (not yet in the card text preview)."""
        return self.my_strength - self.my_strength_start

    @property
    def dex_unbaked(self) -> int:
        return self.my_dex - self.my_dex_start
    # end-of-MY-turn blockable self-damage from player statuses (Knowledge Demon's
    # Disintegration: "At the end of your turn, take N damage") — joins the incoming pool
    # so the planner reserves block for it; skipped on lethal (fight ends first).
    self_end_damage: int = 0
    rupture_per_loss: int = 0  # Rupture: Str per self-HP-loss event on our turn
    barricade: bool = False  # block persists -> stacking it is never waste
    my_weak: bool = False  # I'm Weak: my Attacks deal 25% less (Kin Orb of Weakness, etc.)
    my_frail: bool = False  # I'm Frail: Block I gain from cards is 25% less (Kin Orb of Frailty)
    surrounded: bool = False  # Kaiser Crab: a claw behind me deals +50% (gone once one claw dies)
    has_summoner: bool = False  # an enemy summons minions: chasing the minions is a treadmill
    # a _GUARDED_LEADER_NAMES leader is alive with a live minion: the minion is
    # the fight's clock, never ignorable (Queen/Torch, owner catch 2026-08-11)
    guard_active: bool = False
    hand_size: int = 0  # full hand size at turn start (for hand-exhaust scaling)
    hand_attacks0: int = 0  # Attack-type cards in the opening hand (SW counting)
    draws: int = 0
    weak_applied: int = 0
    vuln_applied: int = 0
    # charges consumed — opening the debuff window has real value (Aeonglass A/B)
    artifact_stripped: int = 0
    strength_gained: int = 0
    potion_strength: int = 0  # Str from potion pseudo-cards: flat credit, no horizon
    max_hp_spent: int = 0  # Brightest Flame-class 'Lose N Max HP' -- permanent,
    #                        was completely unpriced (owner check 2026-08-23)
    stampede_played: bool = False  # the Stampede POWER entered play this plan
    damage_dealt: int = 0
    kills: int = 0
    reattach_kills: int = 0  # kills of Reattach segments (futile if any segment survives the plan)
    reattach_revive_waste: int = 0  # HP those kills hand back on revive (25 - hp at the kill)
    overkill: int = 0
    self_damage: int = 0
    rage_block_active: int = 0  # Rage in play: each later Attack grants this much Block
    # Unmovable state: active (in play at turn start OR played in this plan);
    # baked = it was up at turn start, so the mod's resolved previews ALREADY
    # show doubled block on every block card while the doubling is unspent
    # ((8+5)x2 = 26 trace); first_block_used = the turn's one doubling is spent
    unmovable_active: bool = False
    unmovable_baked: bool = False
    # previews read doubled at plan time (power up AND doubling unspent at plan start)
    unmovable_previews_doubled: bool = False
    first_block_used: bool = False
    rage_block_granted: int = 0  # total Block Rage has granted to attacks (sequencing nudge)
    powers_played: int = 0  # Power cards played this turn (banked permanent buffs)
    self_damage_powers_played: int = 0  # of those, per-turn self-HP-cost powers (Inferno)
    ramp_damage: int = 0  # damage dealt to strength-gaining enemies (rewarded: race them)
    focus_damage: int = 0  # damage dealt to the fight's biggest body (the 'focus' plan)
    carrier_damage: int = 0  # damage to debuff carriers while others live (their death lifts it)
    primal_active: bool = False  # Primal Force played: later Attacks are 16-dmg Giant Rocks
    keepers_rocked: int = 0  # keeper attacks fed to an active Primal Force (permanent downgrade)
    per_exhaust_block: int = 0  # Feel No Pain stacks: block gained per card Exhausted
    bound_played: bool = False  # a Bound card was played this turn (only one allowed)
    no_draw: bool = False  # Battle Trance rider active: further draws are dead
    retain_hand: bool = False  # Equilibrium played: the unplayed hand is kept for next turn
    flat_bonus: float = 0.0  # accumulated per-play bonuses (Thrash growth credit)
    carryover_block: int = 0  # Prolong-class: block snapshotted for next turn's start
    smoggy: bool = False  # Living Fog's Smoggy: only ONE Skill playable per turn
    heal_room: int = 0  # max_hp - hp at turn start; caps in-combat healing (no overheal credit)
    healing: int = 0  # capped HP healed this turn (Not Yet); credited via the HP-scarcity curve
    heal_wasted: int = 0  # heal points past heal_room: a shelvable resource burned (w_heal_waste)
    pen_nib_counter: int | None = None  # live Pen Nib attack counter (None = relic absent)
    # True when the TURN began on counter 9: the game pre-doubles every attack's text, so
    # attacks after the first must halve back to base (set once at plan start, never mutated)
    pen_turn_started_at_nine: bool = False
    exhausted_this_turn: bool = False  # a card was Exhausted this turn (Evil Eye/Ritual gates)
    exhaust_pile0: int = 0  # live Exhaust Pile count at plan start (Pact's End gate)
    n_exhaust_events: int = 0  # exhausting plays this plan (approx: 1 per such card)
    vuln_dmg_reduction: bool = False  # Colossus: 50% less damage from Vulnerable enemies
    potions_spent: int = 0  # pseudo-card potions drunk this plan (each pays w_potion_spend)
    fatal_bonuses: int = 0  # kills landed by "If Fatal, ..." cards (Feed) this plan
    fatal_wasted: int = 0  # Feed-class spent on a MINION kill: payoff forfeited
    frantic_played: int = 0  # cheap Frantic Escapes played (Sandpit clock +1 each)
    growth_banked: int = 0  # Rampage-class: +N future damage per play, this combat
    # Cruelty (power): "Vulnerable enemies take an additional 25% damage" — additive on
    # top of Vulnerable's 50% (owner-confirmed the game previews it; 1.5 -> 1.75)
    vuln_mult_bonus: float = 0.0
    hand_upgrades: int = 0  # cards upgraded in hand this plan (Armaments-class rider)
    # Plating (player status): end-of-turn block, lands before the enemy turn — soaks
    # incoming like played block (harness signature n=31, 2026-07-16)
    end_turn_block: int = 0
    # relic pass R1: the held relics' mid-turn triggers + this plan's play-kind counters
    relic_triggers: tuple = ()
    n_attacks_played: int = 0
    # plan-start values of the play-kind counters (router turn memory seeds).
    # "Costs 1 less per Attack played this turn" and Second Wind's remaining-
    # attacks count must use the plan's OWN plays (the game's displayed cost
    # already reflects earlier ones): batch stall 2026-09-03 run 151507 --
    # Stomp shown at 1 cost after 2 attacks, seeded sim priced it at -1 and
    # looped on an unplayable card at 0 energy.
    n_attacks_played0: int = 0
    n_skills_played: int = 0
    n_powers_played: int = 0
    rainbow_ring: bool = False  # trio (A+S+P in one turn) pays 1 Str + 1 Dex
    # Energy-surplus draw judgment (owner rule, KD A/B 2026-08-14): energy
    # left after the hand's non-basic value plays -- drawn cards are USABLE
    # when positive, so draw credit scales up and draws sequence early.
    energy_surplus: int = 0
    cent_puzzle_armed: bool = False  # Centennial Puzzle unfired (approx: entered at full HP)
    axe_armed: bool = False  # Throwing Axe: the first CARD this combat plays twice
    demon_tongue_armed: bool = False  # Demon Tongue: first self-HP-loss this turn heals it
    # relic pass R2: end-of-turn conditional relics held (ids), evaluated in _score on
    # the plan's END state (Orichalcum, Cloak Clasp, Sturdy Clamp, Ice Cream, ...)
    eot_relics: tuple = ()
    # Tungsten Rod: each HP-loss instance loses 1 less — approximated as -1 per
    # attacking enemy in the incoming pool (multi-hit intents under-counted)
    hp_loss_reduction: int = 0
    dup_armed: bool = False  # Duplicator drunk: the next card play applies twice
    sleepers_woken: int = 0  # paid sleeper wakes in the plan (non-kill, non-final-turn)
    # free setup turns the plan's wakes forfeit (Asleep stacks - 1 each); the
    # unit of w_wake_sleeper ("her per-turn threat")
    wake_turns_forfeit: int = 0
    # Dazed the plan's hits add to the draw pile (Personal Hive: hits x stacks)
    hive_dazed: int = 0
    # hand indices of Ethereal cards (Daze etc.): unplayed at end of turn they
    # EXHAUST -- with Feel No Pain up that's free end-of-turn block the
    # block/attack tradeoff must see (owner check 2026-08-03)
    ethereal_hand: tuple = ()
    # Stampede (owner check 2026-08-06): 'At the end of your turn, 1 random
    # Attack in your Hand is played against a random enemy.' A RETAINED attack
    # is a free EOT play -- (index, damage) pairs of hand attacks, credited at
    # mean damage x0.9 (random target discount). Targeted kills still price
    # higher (w_kill), so deliberately spending the attack on a lethal beats
    # the gamble -- the owner's multi-enemy nuance, preserved by the weights.
    stampede_hand: tuple = ()
    facing: str | None = None  # entity_id of last single-target click (Kaiser Crab back-attack)
    played: tuple[tuple[int, str | None], ...] = ()  # (hand index, target entity_id)


def _to_planned(card, energy: int, hand_attacks: int = 0,
                exhaust_pile: int = 0, unupgraded_in_hand: int = 0,
                discard_attack_dmgs: tuple[int, ...] = ()) -> PlannedCard | None:
    # 'EnergyCostTooHigh' only gates on CURRENT energy, which the DFS re-checks per
    # state — dropping the card here made energy-gain chains structurally
    # undiscoverable (owner live catch 2026-07-30: Production[0]+Stomp[2] at 0 energy
    # ended the turn as 'no play improves'; 7 stranded Productions in one run). Every
    # other reason (Unplayable keyword, hooks, star cost) stays a hard drop.
    if (not card.can_play
            and (getattr(card, "unplayable_reason", None) or "") != "EnergyCostTooHigh"):
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
    blocks_draw = bool(re.search(r"(cannot|may not) draw (any |additional )?(more )?cards?",
                                 card.description or "", re.IGNORECASE))
    # The Gambit: "Gain 50 Block. If you take unblocked attack damage this combat, die."
    # A one-turn planner can never certify combat-long perfect blocking, so a self-death
    # rider makes the card strictly unplayable for this pilot (delta audit).
    if fx.self_death_rider:
        return None
    # Whirlwind & kin: "Deal N damage to ALL enemies X times" — X-cost resolves to current
    # energy (above), and the hit count is that same X; the parser can't know it, so set it
    # here. Without this Whirlwind read as one hit (4x+ under-valued at high energy).
    is_x = cost_str.upper() == "X"
    if is_x and fx.damage and re.search(r"\bX times", card.description or ""):
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
    # Second Wind-class: 'Gain N Block for each card Exhausted' -- the flat
    # parse read N as immediate block; real value = N x exhausted count,
    # concretized in the DFS
    block_per_exhaust = 0
    if "exhaust" in desc.lower() and (m := re.search(
            r"(\d+) Block for each card", desc, re.IGNORECASE)):
        block_per_exhaust = int(m.group(1))
        fx.block = max(0, fx.block - block_per_exhaust)  # un-flat the misparse
    is_power = card.type == "Power"
    low = desc.lower()
    # Armaments-class hand-upgrade rider: 1 target (base) or the whole hand (+)
    upgrades_in_hand = 0
    if m := re.search(r"Upgrade (a card|ALL cards) in your Hand", desc, re.IGNORECASE):
        upgrades_in_hand = (min(1, unupgraded_in_hand) if m.group(1).lower() == "a card"
                            else unupgraded_in_hand)
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
    # Power-like Skills (Apotheosis "Upgrade ALL your cards for the rest of combat"): a one-shot
    # combat-long buff with no parseable this-turn effect scored strictly negative and was NEVER
    # played (delta audit 2026-07-12; filed since 2026-06-26). Flag it power-like so it rides
    # w_power x power_horizon and goes down early, exactly like a real Power.
    if not is_power and "upgrade all your cards" in low:
        is_power = True
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
    per_debuff_dmg = int(m.group(1)) if (m := re.search(
        r"deals? (\d+) additional damage for each unique debuff", desc,
        re.IGNORECASE)) else 0
    per_vuln_str = int(m.group(1)) if (m := _PER_VULN_STR.search(desc)) else 0
    if per_vuln_str:
        # 'Gain N Strength for each Vulnerable' ALSO matches the flat Gain-N-
        # Strength parse — the conditional Str was credited twice, once
        # unconditionally (surfaced by the payoff-dry test 2026-08-29:
        # Dominate scored +33 into Artifact 3 at zero vuln). The rider is the
        # whole sentence; zero the flat copy. (No known card has both.)
        fx.strength = 0
    target_str_down = int(m.group(1)) if (m := _TARGET_STR_DOWN.search(desc)) else 0
    block_if_exh = int(m.group(1)) if (m := _BLOCK_IF_EXHAUSTED.search(desc)) else 0
    energy_gated = bool(_IF_EXHAUSTED_GATE.search(desc)) and fx.energy_gain > 0
    if _PER_HAND_ATTACK.search(desc):  # Expect a Fight: energy per Attack in hand
        fx.energy_gain = hand_attacks
        if "energy" not in fx.recognized:
            fx.recognized.append("energy")
    # Ashen Strike '+N per exhaust-pile card': the LIVE preview already bakes
    # the pile-so-far into 'Deal X' (tape 2026-08-04: 22->26->30 as the pile
    # grew mid-turn) -- folding pile*N on top DOUBLE-COUNTED and produced a
    # false LETHAL at 2 HP (57-HP Obscura, sim 63, game 45; survival lanes
    # suppressed, died with Stoke in hand). Only IN-PLAN exhaust events add.
    dmg_per_exhaust_event = int(m.group(1)) if (m := _PER_EXHAUST_PILE.search(desc)) else 0
    _pp = re.search(r"play(?:s)? the (top|next) (?:(x\+1|x|\d+) )?cards?", low)
    # Beat Down-class 'Play N random Attacks from your Discard Pile' (owner
    # catch 2026-09-28, Bygone Effigy at 14 HP with Strike+ 10 and Perfected
    # Strike 20 in the discard: the parse read no damage, the bot played
    # Defend/Defend/Strike and took the hit). The discard is player-visible,
    # so credit the PESSIMISTIC floor -- the N smallest attack damages there --
    # which is exactly what a lethal certificate may rely on.
    if m := re.search(r"play (\d+) random attacks? from your discard pile", low):
        k = min(int(m.group(1)), len(discard_attack_dmgs))
        floor_dmg = sum(sorted(discard_attack_dmgs)[:k]) if k else 0
        if floor_dmg > 0:
            fx.damage, fx.hits = floor_dmg, 1
            if "damage" not in fx.recognized:
                fx.recognized.append("damage")

    return PlannedCard(
        index=card.index,
        name=card.name,
        cost=cost,
        fx=fx,
        # Synthetic generator damage (Shivs / Infernal Blade credit) must be targetable or
        # _apply_card drops it on the floor -- harness-confirmed the IB fix never landed
        # because a non-targeting Skill's damage applies only with a target or AoE (delta
        # audit 2026-07-12). Real target choice is irrelevant; the credit just needs to land.
        targets_enemy=(card.target_type == "AnyEnemy")
        or (fx.damage > 0 and not fx.aoe),
        dmg_per_exhaust_event=dmg_per_exhaust_event,
        is_attack=(card.type == "Attack"),
        is_skill=(card.type == "Skill"),
        is_power=is_power,
        self_damage_power=self_damage_power,
        primal_force=primal_force,
        blocks_draw=blocks_draw,
        # fodder = Strikes, or rider-less attacks a 16-dmg Rock strictly upgrades
        primal_fodder=(
            (card.id or "").upper().startswith("STRIKE_")
            or (card.type == "Attack"
                and fx.damage * max(1, fx.hits) <= _PRIMAL_ROCK_DAMAGE
                and not (fx.vulnerable or fx.weak or fx.block or fx.draw
                         or fx.strength or fx.energy_gain or per_vuln_dmg
                         or per_debuff_dmg
                         or per_vuln_str or target_str_down))
        ),
        rage_block=rage_block,
        self_replays=bool(_SELF_REPLAYS.search(card.description or "")),
        hand_exhaust_scale=hand_exhaust_scale,
        debuff_order=debuff_order,
        dmg_per_target_vuln=per_vuln_dmg,
        dmg_per_unique_debuff=per_debuff_dmg,
        str_per_target_vuln=per_vuln_str,
        doubles_target_vuln=bool(_DOUBLE_VULN.search(desc)),
        target_str_down=target_str_down,
        bonus_block_if_exhausted=block_if_exh,
        energy_requires_exhausted=energy_gated,
        exhausts_a_card="exhaust" in low,
        exhaust_nonattack_only=bool(re.search(r"non-attack", desc, re.IGNORECASE)),
        exhausts_random_attack=bool(re.search(
            r"Exhaust a random Attack in your Hand", desc, re.IGNORECASE)),
        exhausts_random_card=bool(re.search(
            r"Exhaust 1 card at random", desc, re.IGNORECASE)),
        grants_barricade=bool(re.search(
            r"block is (?:not|no longer) removed", desc, re.IGNORECASE)),
        grants_unmovable=bool(re.search(
            r"first time you gain block from a card each turn, double",
            card.description or "", re.IGNORECASE)),
        targeted_exhaust_n=(
            0 if "random" in low else
            (int(m_te.group(1)) if (m_te := re.search(
                r"exhaust up to (\d+) cards?", low)) else
             1 if re.search(r"exhaust (?:1|a) card\b", low) else 0)),
        block_per_exhaust=block_per_exhaust,
        exhaust_count=(
            -1 if _EX_HAND.search(desc)
            else (1 if _EX_ONE.search(desc) else 0) + (1 if _EX_SELF.search(desc) else 0)
        ),
        bound=(
            any((k.name or "") == "Bound" for k in getattr(card, "keywords", None) or [])
            or bool(re.search(r"\bBound\b", desc))
        ),
        plays_top_cards=bool(re.search(r"play(s)? the (top|next)", desc, re.IGNORECASE)),
        plays_pile_n=(
            (int(_pp.group(2)) if (_pp.group(2) or "").isdigit()
             else (0 if _pp.group(2) else 1))
            if _pp else 0),
        pile_plays_scale_x=bool(_pp and (_pp.group(2) or "").lower().startswith("x")),
        pile_plays_bonus=(1 if _pp and (_pp.group(2) or "").lower() == "x+1" else 0),
        stampede_power=bool(re.search(
            r"random attack in your hand is played", desc, re.IGNORECASE)),
        grows_on_exhaust=bool(_GROWS_ON_EXHAUST.search(desc)),
        grants_vuln_reduction=bool(_VULN_DMG_REDUCTION.search(desc)),
        on_fatal_bonus=bool(re.search(r"\bIf Fatal\b", desc, re.IGNORECASE)),
        frantic_escape=((card.id or "").upper() == "FRANTIC_ESCAPE" and cost <= 1),
        vuln_amp=(int(m.group(1)) / 100.0
                  if (m := re.search(r"Vulnerable enemies take an additional "
                                     r"(\d+)% damage", desc, re.IGNORECASE))
                  else 0.0),
        requires_target=(card.target_type == "AnyEnemy"),
        random_target=(card.target_type == "RandomEnemy"),
        upgrades_in_hand=upgrades_in_hand,
        is_x_cost=is_x,
    )


def _enemy_sims(enemies: list[Enemy], plays_this_turn: int = 0) -> tuple[EnemySim, ...]:
    sims = []
    for e in enemies:
        if e.hp <= 0:
            continue
        vuln = 0
        artifact = 0
        n_debuffs = 0  # Rend: unique debuffs at plan start
        slippery_stacks = 0
        attack_dmg_mult = 1.0
        crab_rage = False
        back_attack = False
        is_minion = False
        gains_strength = False
        summons = False
        illusion = False
        reattach = False
        asleep = False
        asleep_left = 0
        hive = 0
        slow_stacks = None
        spawns_on_death = False
        burrowed = False
        ravenous = False
        intangible = False
        for p in e.status:
            # live ids carry a _POWER suffix (VULNERABLE_POWER); startswith, not ==, or
            # pre-existing stacks are invisible (the owner-caught Colossus/Ringing miss —
            # exact match also kept the cross-turn 1.5x vuln credit dead since day one).
            # startswith stays safe against a hypothetical INVULNERABLE id.
            if p.id.upper().startswith("VULNERABLE") and p.amount:
                vuln = p.amount
            if "ARTIFACT" in p.id.upper() and p.amount:
                artifact = p.amount
            if (any(p.id.upper().startswith(d) for d in (
                    "VULNERABLE", "WEAK", "POISON", "DOOM", "SHRUNK"))
                    or ("STRENGTH" in p.id.upper() and (p.amount or 0) < 0)):
                n_debuffs += 1
            if "CRAB_RAGE" in p.id.upper() or "ally dies" in (p.description or "").lower():
                crab_rage = True
            if "BACK_ATTACK" in p.id.upper() or "from behind" in (p.description or "").lower():
                back_attack = True
            # Slippery carries a stack count (Inklet 1, Vantom 9): each charge drops one HP-loss
            # instance to 1, so multi-hit strips it cheaply and a big single hit is wasted.
            if "SLIPPERY" in p.id.upper():
                slippery_stacks = p.amount if p.amount else 1
            if m_ := re.search(r"receives? (\d+)% less damage from attacks",
                               (p.description or ""), re.IGNORECASE):
                attack_dmg_mult = 1.0 - int(m_.group(1)) / 100.0
            if "MINION" in p.id.upper() or "abandon combat" in (p.description or "").lower():
                is_minion = True
            if "STRENGTH" in p.id.upper() and (p.amount or 0) > 0:
                gains_strength = True
            if "ILLUSION" in p.id.upper() or "revives" in (p.description or "").lower():
                illusion = True
            if "REATTACH" in p.id.upper() or (
                    "revives in" in (p.description or "").lower()
                    and "segment" in (p.description or "").lower()):
                reattach = True
            if p.id.upper().startswith("ASLEEP"):  # Asleep only — Slumber wakes differently
                asleep = True
                asleep_left = int(p.amount or 0)
            if p.id.upper().startswith("PERSONAL_HIVE"):  # Entomancer: a Dazed per hit
                hive = max(1, int(p.amount or 1))
            if ("receives 10% more damage from attacks" in (p.description or "").lower()
                    or p.id.upper().startswith("SLOW")):
                # Slow's AMOUNT is a cumulative-combat display, but the effect
                # is per card played THIS TURN (owner spec 'this turn'; audit
                # 2026-08-07: display-seeding read every attack x2 by round 3 --
                # false lethal #6). The caller passes its own plays-this-turn
                # count (router-tracked across replans, exhaust-snapshot family).
                slow_stacks = plays_this_turn
            if p.id.upper().startswith("BURROWED"):  # Tunneler: block-strip = stun
                burrowed = True
            if p.id.upper().startswith("RAVENOUS"):  # Corpse Slug: ally-death = self-stun
                ravenous = True
            if p.id.upper().startswith("INTANGIBLE") and (p.amount or 0) > 0:
                intangible = True
            low_desc = (p.description or "").lower()
            if "INFESTED" in p.id.upper() or ("dying" in low_desc and "summon" in low_desc):
                spawns_on_death = True
            # Axebot's Stock (audit 2026-08-07, -25 damage overprediction):
            # 'When killed, a new Axebot is summoned in its place', amount =
            # respawns left. A kill with stock remaining is NOT fight progress
            # the way the sim thought -- _fight_over already refuses wins over
            # dead spawners, so the flag alone fixes false lethals too.
            # Owner (undocumented, 2026-08-07): the STOCK-spawned replacement
            # NEVER attacks -- it only buffs. So the kill still ends the
            # incoming threat (dead = no incoming is correct), the fight just
            # is not over; do not model phantom incoming for replacements.
            if ("when killed" in low_desc and "summoned" in low_desc
                    and (p.amount or 0) > 0):
                spawns_on_death = True
        for i in e.intents:
            text = f"{i.type or ''} {i.title or ''} {i.description or ''}".lower()
            if (i.type or "").lower() == "buff" and (
                "empower" in (i.title or "").lower() or "strength" in (i.description or "").lower()
            ):
                gains_strength = True
            # A healer is a racer: every slow turn refunds its HP (Knowledge Demon healed
            # ~30/cycle and out-healed a 29-damage plan, byupfrv22 f33 x2 — the race lane's
            # ramp_damage/ramp_stall incentives are exactly right for it too).
            if (i.type or "").lower() == "heal":
                gains_strength = True
        # A PLAYER-DRAINER is a racer in mirror image: the Matriarch's Soul Siphon
        # (-2 Str AND Dex, permanent, every 4th round) shifts the race against you
        # each cycle exactly like enemy ramp. The drain is a MOVE, not a status, so
        # nothing text-detects it — matched from the empirical table (Matriarch
        # cluster 2026-07-30: 3 healthy-HP deaths, chip ~12/round vs 222 HP while
        # Str/Dex bled -2 -> -6; the planner turtled with no clock pressure).
        from sts2bot.policy.capability import _EMPIRICAL_MOVES
        if any(key in (e.name or "").upper() and params.get("drains_player")
               for key, params in _EMPIRICAL_MOVES.items()):
            gains_strength = True
            if "summon" in text:
                summons = True
        # Count damage from Attack AND DeathBlow intents. (The DeathBlow lane was built on the
        # assumption the Waterfall Giant telegraphs its eruption as one — DISPROVEN live
        # 2026-07-25, WYZQR5KPFQ f17 r13: during the invincible phase the Giant exposes intent
        # null AND statuses null. Kept for any boss that does telegraph a DeathBlow.)
        incoming = sum(
            parse_intent_damage(i.label)
            for i in e.intents
            if (i.type or "").lower() in ("attack", "deathblow")
        )
        invincible = e.hp >= _INVINCIBLE_HP
        # Eruption pending with NOTHING telegraphed (intent/statuses null): the one reliable
        # signature is the HP sentinel itself. Assume a big blockable hit so the block machinery
        # stacks everything it can — the WG death above played 12 block at 30 HP into the blast
        # because 0 parsed incoming made all block score as excess. Steam-stack size is
        # unknowable from state; overblocking costs w_block_excess, dying costs the run.
        # STALENESS FIX (audit #1 bucket, 2026-08-13: knockdown turns pred~40-50
        # vs actual 0, n=24 avg 17.2 over): the 2026-07-25 blind phase no longer
        # exists — today's tape shows the PREPARING turn as an explicit Stun
        # intent with STEAM_ERUPTION_POWER stacks visible, and the eruption turn
        # as DeathBlow N (already priced by the intent lane). Blocking on the
        # preparing turn is a turn EARLY (block expires before the blast).
        # The assumption now fires only when the phase is genuinely blind.
        _telegraphed = (
            any((i.type or "").lower() in ("stun", "deathblow") for i in e.intents)
            or any("STEAM_ERUPTION" in (p.id or "").upper() for p in e.status)
        )
        if invincible and incoming == 0 and not _telegraphed:
            incoming = _ERUPTION_ASSUMED_INCOMING
        # attack INSTANCE count ("6x3" = 3 hits) for Flame Barrier-class retaliation
        incoming_hits = sum(
            int(m.group(1)) if (m := re.search(r"x(\d+)", i.label or "")) else 1
            for i in e.intents
            if (i.type or "").lower() in ("attack", "deathblow")
        )
        # throttling parsed from the same status text the bestiary harvests (ENEMY_PASS)
        mech = detect_mechanics([{"description": p.description} for p in e.status])
        sims.append(
            EnemySim(
                entity_id=e.entity_id,
                name=e.name or "",
                hp=e.hp,
                max_hp=max(e.max_hp, 1),
                block=e.block,
                vulnerable=vuln,
                incoming=incoming,
                is_minion=is_minion,
                gains_strength=gains_strength,
                debuff_carrier=any(
                    k in (e.entity_id or "").upper() for k in _DEBUFF_CARRIERS
                ),
                intangible=intangible,
                incoming_hits=incoming_hits,
                summons=summons,
                illusion=illusion,
                reattach=reattach,
                slippery_stacks=slippery_stacks,
                attack_dmg_mult=attack_dmg_mult,
                dmg_cap_per_turn=mech.get("dmg_cap_per_turn"),
                thorns=mech.get("thorns", 0),
                skittish=mech.get("skittish", 0),
                artifact=artifact,
                debuff_count=n_debuffs,
                stun_threshold=mech.get("stun_threshold", 0),
                invincible=invincible,
                crab_rage=crab_rage,
                back_attack=back_attack,
                asleep=asleep,
                asleep_left=asleep_left,
                hive=hive,
                slow_stacks=slow_stacks,
                spawns_on_death=spawns_on_death,
                burrowed=burrowed,
                ravenous=ravenous,
            )
        )
    # mark the fight's biggest alive body — the "focus" plan's damage target
    alive = [s for s in sims if s.hp > 0]
    if alive:
        big = max(alive, key=lambda s: s.max_hp)
        sims = [replace(s, is_big=s is big) for s in sims]
    return tuple(sims)


# Guarded leaders (see data/enemy_notes.json 'Queen'): while any minion lives
# the leader does NOT attack -- she buffs and re-blocks -- so the MINION is the
# fight's real clock and the flee-with-the-leader discount is exactly backwards.
# Owner live catch 2026-08-11 (run 20260810-235031 f48): the planner poured six
# rounds of damage into the guarded 391-HP Queen while the 190-HP Torch beat the
# run to death; owner's 2026-08-02 A/B taped Torch-first as the winning order.
_GUARDED_LEADER_NAMES = ("QUEEN",)


def _ignorable_minion(e: EnemySim, has_summoner: bool = False,
                      guard_active: bool = False) -> bool:
    """A Minion not worth grinding down: race the leader instead — killing the leader makes the
    minions flee. Diverting damage to a minion pays off only when it's a *fixed* escalating threat:
    it ramps (Strength, like the Kin's followers) and isn't re-summoned. Ignore it when anything on
    the board summons (the Ovicopter's eggs/hatchlings — every minion is then replaceable, so
    chasing them is a treadmill), or it's an **Illusion** (revives at full HP when killed, so
    grinding makes no progress). Killing an Illusion only to deny a turn's attack is the deferred
    capability-estimate layer. Minions never gate lethal regardless."""
    if not e.is_minion:
        return False
    if guard_active:
        return False  # the guard IS the fight: its minion is never ignorable
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
    state: SimState, target_i: int, card: PlannedCard, pen_double: bool = False,
    pen_halve: bool = False
) -> SimState:
    enemies = list(state.enemies)
    e = enemies[target_i]
    # Guard redirect (Bowlbug pair): a single-target attack into the guarded enemy hits
    # the living guard instead — the sim must price the redirect or it plans phantom
    # kills into an untouchable target (owner-caught death, 2026-07-13).
    if not card.fx.aoe:
        guard_prefix = next(
            (g for k, g in _GUARD_PAIRS.items() if e.entity_id.startswith(k)), None)
        if guard_prefix is not None:
            gi = next(
                (i for i, en in enumerate(enemies)
                 if en.entity_id.startswith(guard_prefix) and en.hp > 0), None)
            if gi is not None and gi != target_i:
                target_i = gi
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
    # text already carries turn-start Strength; Osty attacks (fx.companion)
    # ignore the owner's Str entirely (owner clarification 2026-08-20)
    per_hit = base_damage + (0 if card.fx.companion else state.str_unbaked)
    if card.fx.double_hits_if_vuln and e.vulnerable > 0:
        hits *= 2  # Dismantle-class: vs a Vulnerable target every hit doubles
    if e.attack_dmg_mult != 1.0 and card.is_attack:
        per_hit = int(per_hit * e.attack_dmg_mult)  # Flutter: attacks halved
    if card.dmg_per_exhaust_event:  # Ashen: in-plan exhausts beyond the preview
        per_hit += card.dmg_per_exhaust_event * state.n_exhaust_events
    if card.dmg_per_target_vuln:  # Bully: +N per Vulnerable already on the target
        per_hit += card.dmg_per_target_vuln * e.vulnerable
    if card.dmg_per_unique_debuff:  # Rend: +N per UNIQUE debuff (plan-start
        # count; in-plan vuln counted if it made the target newly vulnerable)
        n_d = e.debuff_count + (1 if e.vulnerable > 0 and e.debuff_count == 0
                                else 0)
        per_hit += card.dmg_per_unique_debuff * n_d
    if pen_halve:
        # Pen Nib preview: at counter 9 the text shows doubled damage on EVERY attack, but
        # only the first actually doubles — later attacks revert to base (text // 2).
        per_hit = ((base_damage + 1) // 2
                   + (0 if card.fx.companion else state.str_unbaked))
    if pen_double:
        per_hit *= 2  # (kept for tests/simulation without preview text; unused live)
    # NB: the player's own Weak is PRE-BAKED into the card text (a Strike under Weak
    # reads "Deal 4 damage", 6 x 0.75 — trace-verified 2026-07-14). Applying WEAK_MULT
    # here would double-apply it, so we do NOT. (Enemy Weak that WE apply mid-plan is a
    # different thing and is still modeled — see the landed_weak block in _apply_card.)
    if e.vulnerable > 0:
        per_hit = int(per_hit * (VULN_MULT + state.vuln_mult_bonus))
    # Pact's End-class: the damage exists only if the Exhaust Pile (live count +
    # in-plan exhausting plays) meets the threshold at play time — else it's 0
    # (phantom-lethal death 2026-08-01: pile 0, 17 AoE credited, bot died)
    if (card.fx.requires_exhaust_pile
            and state.exhaust_pile0 + state.n_exhaust_events
            < card.fx.requires_exhaust_pile):
        per_hit = 0
    # Slow: +10% per card played this turn BEFORE this one (the attack doesn't
    # count its own play — owner's example: 6-dmg Strike + 2 stacks = 7), direct
    # attacks only, floored. The DFS discovers attacks-last ordering from this.
    if e.slow_stacks is not None and card.is_attack:
        k = e.slow_stacks + sum(1 for i, _ in state.played if i >= 0)
        per_hit = int(per_hit * (1 + 0.10 * k))
    hive_hits = 0
    for _ in range(hits):
        if hp <= 0:
            break
        thorns_taken += e.thorns  # "when hit by an attack" retaliates, per hit landed
        hive_hits += 1  # Personal Hive: every landed hit (blocked or not) adds Dazed
        absorbed = min(block, per_hit)
        block -= absorbed
        dealt = per_hit - absorbed
        if dealt > 0:
            if e.intangible:  # Soul Fysh shield turn: every HP-loss instance becomes 1
                dealt = 1
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
    # Burrowed (Tunneler): "Stunned if all Block is removed" — stripping its block to 0
    # cancels its attack, a BLOCK-based stun the planner can aim for deliberately.
    if e.burrowed and e.block > 0 and block <= 0:
        stunned = True
    # Enemy-buff rider (Fight Me!: "The enemy gains N Strength") — the survivor hits
    # harder THIS turn, so bump its incoming per attack instance. Killing it same
    # turn erases the rider (dead enemies contribute no incoming) — which makes the
    # owner's rule literal: play Fight Me only into a kill, or pay the buffed hit
    # (Ovicopter A/B 2026-07-25: the bot buffed it, missed the kill by 9, died).
    inc = e.incoming
    if card.fx.enemy_strength and hp > 0:
        inc += card.fx.enemy_strength * max(1, e.incoming_hits)
    # Mirror rider (Piercing Wail/Crush Under, audit #2 item 25): ALL enemies
    # LOSE Str this turn -> softer remaining hits. Owner nuance 2026-08-20:
    # Str-DOWN is a debuff -- Artifact eats it (one charge); Str-UP (Fight
    # Me!) bypasses Artifact, hence no charge check above.
    art = e.artifact
    strdown_stripped = 0
    if card.fx.enemy_str_down and hp > 0:
        if art > 0:
            art -= 1  # a charge eats the Str-down (debuff); Str-UP bypasses
            strdown_stripped = 1
        else:
            inc -= card.fx.enemy_str_down * max(1, e.incoming_hits)
    enemies[target_i] = replace(
        e, hp=hp, block=block, vulnerable=e.vulnerable + card.fx.vulnerable,
        hp_lost_this_turn=lost, stunned_this_turn=stunned, slippery_stacks=slip,
        incoming=inc, artifact=art,
    )
    # Ignorable minions (weak, non-ramping) aren't progress — they flee with the leader and
    # Illusion ones revive — so deny offensive reward; their death's incoming drop is still
    # seen via hp_loss. Dangerous minions (Kin followers etc.) fall through to normal reward.
    if _ignorable_minion(e, state.has_summoner, state.guard_active):
        return replace(
            state, enemies=tuple(enemies),
            self_damage=state.self_damage + thorns_taken,
            # burning an If-Fatal Exhaust card (Feed) on an ignorable minion
            # forfeits its permanent payoff -- the minion kill pays nothing
            # (game keyword: non-minion) and the card is gone
            fatal_wasted=state.fatal_wasted + (
                1 if card.on_fatal_bonus and e.hp > 0 and hp <= 0 else 0),
        )
    # Chipping a sleeper awake forfeits its remaining free setup turns (and Lagavulin sheds her
    # Plating FOR you on wake) — the attack is a complete no-op in sim unless it kills outright:
    # the HP change is NOT applied (a partial deny leaked reward through _score's focus term —
    # live leak, batch bnyka47dn run 3: Volley/Tremble woke her on round 1), so the planner
    # spends sleep turns on powers/block/clears. Conservative side effect: multi-card lethals
    # THROUGH the sleep window must kill from full HP (acceptable — rare at boss HP).
    # Sleeper model v3 (owner 2026-08-06): damage COUNTS (she keeps the HP loss
    # -- the old restore-untouched hack denied real burst progress, so 'wake her
    # with the deck's best burst' was unrepresentable), and the WAKING hit pays
    # w_wake_sleeper once. Pokes lose (9 < 12), bursts clear the bar, kills were
    # always exempt. The R2 tape leak (energy-waste bribing score-negative pokes
    # into a sleeper) dies to the same penalty.
    # 2026-09-28 (A0 era: 9 of 11 Matriarch losses were poke-wakes on rounds 1-2):
    # she "Awakens upon losing HP" -- a hit her Plating block fully soaks does NOT
    # wake her, so it must not pay (or pre-pay) the penalty: the old any-hit rule
    # charged the blocked Headbutt+ and then let the real waking Strike land free
    # (seed HEKRVZMGUV round 1). And with 1 stack left she wakes on her own after
    # this turn, so that waking hit forfeits no setup turn and pays nothing.
    woke = 1 if (e.asleep and not killed and dealt_total > 0) else 0
    if woke:
        enemies[target_i] = replace(enemies[target_i], asleep=False)
    woke_paid = woke if e.asleep_left != 1 else 0
    # forfeited free turns: stacks 3 -> 2 turns, 2 -> 1, unknown -> 1 (the old flat bar)
    forfeit = woke_paid * max(1, e.asleep_left - 1)
    return replace(
        state,
        enemies=tuple(enemies),
        sleepers_woken=state.sleepers_woken + woke_paid,
        wake_turns_forfeit=state.wake_turns_forfeit + forfeit,
        hive_dazed=state.hive_dazed + hive_hits * e.hive,
        damage_dealt=state.damage_dealt + dealt_total,
        kills=state.kills + (1 if killed else 0),
        reattach_kills=state.reattach_kills + (1 if killed and e.reattach else 0),
        reattach_revive_waste=state.reattach_revive_waste + (
            max(0, REATTACH_REVIVE_HP - e.hp) if killed and e.reattach else 0),
        overkill=state.overkill + overkill_amt,
        vuln_applied=state.vuln_applied + (card.fx.vulnerable if hp > 0 else 0),
        artifact_stripped=state.artifact_stripped + strdown_stripped,
        # a sleeping 'ramper' isn't ramping: the waking hit earns plain damage
        # credit only (with focus_damage below, the third sleeper-bribe term)
        ramp_damage=state.ramp_damage + (
            dealt_total if e.gains_strength and not woke
            and not (state.sleepers_woken + woke_paid) else 0),
        # the fight-plan race bias must not bribe a WAKING hit (Matriarch is a
        # drain boss -> plan=focus, and its +0.8/dmg amplifier out-bid the wake
        # penalty): her clock isn't ticking while she sleeps, so sleep-phase
        # damage earns plain credit, not race credit
        # ...nor the follow-up hits of a paid wake turn: that turn's raw damage IS
        # the "burst" weighed against the forfeited setup turns (owner rule: wake
        # early only if burst-in-hand beats remaining setup value), so the +0.8
        # premium must not inflate it (seed HEKRVZMGUV: 19 raw read as 33, woke R1)
        focus_damage=state.focus_damage + (
            dealt_total if e.is_big and not woke and not (state.sleepers_woken + woke_paid)
            else 0),
        carrier_damage=state.carrier_damage + (
            dealt_total
            if e.debuff_carrier
            and any(x.hp > 0 for j, x in enumerate(enemies) if j != target_i)
            else 0
        ),
        self_damage=state.self_damage + thorns_taken,
        fatal_bonuses=state.fatal_bonuses + (
            # the game keyword: kills a NON-MINION enemy (owner check 2026-08-13:
            # Feeding a Torch/Follower pays nothing -- and guard_break steers
            # kills onto minions, so the phantom credit collided exactly there)
            1 if killed and card.on_fatal_bonus and not e.is_minion else 0),
        fatal_wasted=state.fatal_wasted + (
            1 if killed and card.on_fatal_bonus and e.is_minion else 0),
    )


def _apply_card(state: SimState, card: PlannedCard, target_i: int | None) -> SimState:
    target_id = state.enemies[target_i].entity_id if target_i is not None else None
    # Rage: an Attack played while Rage is already active grants Block.
    rage_bonus = state.rage_block_active if (card.is_attack and state.rage_block_active) else 0
    # Flame Barrier-class retaliation (owner 2026-07-18): thorns-for-a-turn in all but
    # name — credit retaliate x every attack instance aimed at us this turn. Score
    # credit only (damage_dealt), no enemy-HP mutation: the hits land after end-turn,
    # so a false in-plan kill must not be claimable from it.
    retaliation = 0
    if card.fx.retaliate:
        retaliation = card.fx.retaliate * sum(
            e.incoming_hits for e in state.enemies if _enemy_attacking(e)
        )
    # Kaiser Crab facing: any single-target click turns you to face that enemy, so the OTHER claw
    # takes the +50% back-attack. AoE doesn't rotate. What matters is who you face LAST this turn
    # (owner), so just track the most recent single-target target through the sequence.
    facing = target_id if target_i is not None else state.facing
    eff_cost = card.cost
    if card.is_x_cost:
        # X-cost consumes whatever remains AT PLAY POSITION; the baked
        # turn-start hits are wrong mid-plan in both directions (owner
        # catch 2026-08-29: Rampage-then-Whirlwind undiscoverable)
        eff_cost = max(0, state.energy)
        if card.fx.damage and card.fx.hits:
            # X=0 -> ZERO hits (the old max(1, X) bake gave 0-energy
            # Whirlwind a phantom 6 damage -- owner T6 catch 2026-08-29)
            card = replace(card, fx=replace(card.fx, hits=eff_cost))
    if card.fx.cost_less_per_attack:  # Stomp-class: cheaper per Attack already played
        eff_cost = max(0, card.cost
                       - card.fx.cost_less_per_attack
                       * (state.n_attacks_played - state.n_attacks_played0))
    if card.pile_plays_scale_x:
        # Cascade-class: X resolves at play position for a live X-cost card; a
        # card the game already shows at a fixed cost (X resolved, e.g. 0)
        # plays that many (+1 for X+1)
        x_now = max(0, state.energy) if card.is_x_cost else card.cost
        card = replace(card, plays_pile_n=x_now + card.pile_plays_bonus)
    s = replace(
        state,
        energy=state.energy - eff_cost,
        damage_dealt=state.damage_dealt + retaliation,
        potions_spent=state.potions_spent + (1 if card.potion_slot is not None else 0),
        max_hp_spent=state.max_hp_spent + card.fx.max_hp_cost,
        # FNP played mid-plan: later exhausts in THIS plan earn its block
        # (owner 2026-08-03: FNP -> Infernal Blade+ ordering must be discoverable)
        per_exhaust_block=state.per_exhaust_block + card.fx.per_exhaust_block_grant,
        rage_block_active=max(state.rage_block_active, card.rage_block),
        rage_block_granted=state.rage_block_granted + rage_bonus,
        powers_played=state.powers_played + (1 if card.is_power else 0),
        stampede_played=state.stampede_played or card.stampede_power,
        self_damage_powers_played=(
            state.self_damage_powers_played + (1 if card.self_damage_power else 0)
        ),
        primal_active=state.primal_active or card.primal_force,
        keepers_rocked=state.keepers_rocked + (
            1 if (state.primal_active and card.is_attack and not card.primal_fodder)
            else 0
        ),
        bound_played=state.bound_played or card.bound,
        # reveal-early nudge (owner 2026-08-03): gamble cards (Infernal Blade+)
        # played sooner leave more of the turn able to use what they generate --
        # position-scaled tie-break, sized below any real effect
        flat_bonus=state.flat_bonus + card.growth_bonus
        # nudge accrues for ANY card it was deliberately set on (gambles,
        # 0-cost draws, surplus-energy draw sources) -- the old
        # reveals_random gate silently ignored the draw-opener nudges
        + card.reveal_nudge * max(0, state.hand_size - len(state.played) - 1),
        # Prolong-class: next-turn block equal to block AT PLAY TIME (snapshot —
        # review #13). Future value the one-turn tally can't see; the DFS discovers
        # on its own that it plays best AFTER the block cards (live 2026-07-25:
        # 0-cost Prolong sat unplayed with block up — it parsed to all-zeros).
        carryover_block=state.carryover_block + (
            state.my_block if card.fx.block_carryover else 0
        ),
        facing=facing,
        played=(*state.played, (card.index, target_id)),
    )
    # Pen Nib: count attack cards; the one whose counter rolls past a multiple of 10 doubles.
    # Pen Nib, LIVE-VALIDATED 2026-07-09 (owner's June gotcha confirmed): while the counter
    # sits on 9 the game PRE-DOUBLES every attack's rules text ("Deal 12" on a base-6 Strike),
    # but only the FIRST attack actually doubles. So at 9: the first attack keeps its parsed
    # (already-doubled) damage untouched, and every LATER attack in the same plan halves back
    # to base. Doubling per_hit ourselves on top of the doubled text was a 4x over-credit.
    pen_halve = False
    if card.is_attack and s.pen_nib_counter is not None:
        at_nine = (s.pen_nib_counter % _PEN_NIB_PERIOD) == _PEN_NIB_PERIOD - 1
        pen_halve = s.pen_turn_started_at_nine and not at_nine  # later attack: preview lies
        s = replace(s, pen_nib_counter=s.pen_nib_counter + 1)
    pen_double = False  # never our own doubling — the text already carries it at 9
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
            s = replace(s, enemies=tuple(enemies),
                        artifact_stripped=s.artifact_stripped + (e.artifact - art))
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
                    s = _apply_attack(s, i, atk, pen_double=pen_double,
                                      pen_halve=pen_halve)
        elif target_i is not None:
            s = _apply_attack(s, target_i, atk, pen_double=pen_double,
                              pen_halve=pen_halve)
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
    # Piercing Wail-class (audit #2 item 25, owner: -6 Str 'cannot be
    # ignored'): a damageless AoE Str-down softens EVERY attacker's remaining
    # hits this turn. (Damage cards with the rider -- Crush Under -- apply it
    # per target inside _apply_attack instead.)
    if atk.fx.enemy_str_down and atk.fx.total_damage == 0:
        enemies = list(s.enemies)
        hit_any = False
        stripped = 0
        for i, e in enumerate(enemies):
            if e.hp <= 0:
                continue
            if e.artifact > 0:  # owner 2026-08-20: Artifact eats Str-DOWN
                enemies[i] = replace(e, artifact=e.artifact - 1)
                stripped += 1
                hit_any = True
            elif e.incoming > 0:
                cut = atk.fx.enemy_str_down * max(1, e.incoming_hits)
                enemies[i] = replace(e, incoming=max(0, e.incoming - cut))
                hit_any = True
        if hit_any:
            s = replace(s, enemies=tuple(enemies),
                        artifact_stripped=s.artifact_stripped + stripped)
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
    # Ravenous (Corpse Slug): "When an enemy dies, Corpse Slug immediately eats it,
    # becoming Stunned and gaining 4 Strength." Any death this card stuns every living
    # ravenous ally — killing ONE slug cancels the surviving pack's whole turn. The +4
    # Str shows up in next turn's intent labels (pre-resolved), so no ramp bookkeeping.
    if any(e.ravenous for e in s.enemies):
        pre_r = {e.entity_id: e.hp for e in state.enemies}
        died_any = any(e.hp <= 0 < pre_r.get(e.entity_id, 0) for e in s.enemies)
        if died_any:
            enemies = [
                replace(e, stunned_this_turn=True) if (e.ravenous and e.hp > 0) else e
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
        # Payoff-dry dock (owner rule 2026-08-29, seed-A T2 + seed-B r4 tapes:
        # Dominate led plans as an artifact STRIPPER, Molten Fist+ exhausted
        # itself with vuln 0 under Artifact — 'you REALLY want to save these
        # until there is actual vuln'): a vuln-payoff rider firing on ZERO
        # stacks wastes the payoff; exhaust cards lose it forever.
        if ((card.str_per_target_vuln or card.doubles_target_vuln)
                and e.vulnerable <= 0):
            s = replace(s, vuln_payoff_dry=s.vuln_payoff_dry + 1)
        if card.doubles_target_vuln and e.vulnerable > 0 and e.hp > 0:  # Molten Fist
            enemies[target_i] = replace(e, vulnerable=e.vulnerable * 2)
            s = replace(s, enemies=tuple(enemies),
                        vuln_applied=s.vuln_applied + e.vulnerable)
            e = enemies[target_i]
        if card.target_str_down and e.incoming > 0:  # Dark Shackles/Mangle: -N Str this turn
            if e.artifact > 0:  # owner 2026-08-20: Artifact eats Str-DOWN too
                enemies[target_i] = replace(e, artifact=e.artifact - 1)
                s = replace(s, enemies=tuple(enemies),
                            artifact_stripped=s.artifact_stripped + 1)
            else:
                enemies[target_i] = replace(
                    e, incoming=max(0, e.incoming - card.target_str_down))
                s = replace(s, enemies=tuple(enemies))
    # In-combat healing (Not Yet), capped at the turn's damage taken — no overheal credit.
    heal_applied = max(0, min(card.fx.heal, s.heal_room - s.healing)) if card.fx.heal else 0
    # Forgone heal (owner catch 2026-08-28, TS f48: Not Yet burned at 77/83
    # for a 6-point heal): the overflow isn't just uncredited, it's a WASTED
    # future scarce-HP resource — the same 10 at 30 HP is worth triple on the
    # scarcity curve. Charged via w_heal_waste so the planner shelves heals
    # while healthy (mirror of the Offering play-freely-when-healthy rule).
    heal_forgone = (card.fx.heal - heal_applied) if card.fx.heal else 0
    # Dexterity adds/subtracts per block-granting card — Soul Siphon drives it NEGATIVE, so a
    # drained Defend really grants less (the planner over-blocked-on-paper vs Lagavulin without
    # this). Then Frail cuts the result by 25% — the floor matches the game.
    base_block = card.fx.block
    if card.bonus_block_if_exhausted and s.exhausted_this_turn:  # Evil Eye's second half
        base_block += card.bonus_block_if_exhausted
    if base_block and s.dex_unbaked:  # text already carries turn-start Dexterity
        base_block = max(0, base_block + s.dex_unbaked)
    # Feel No Pain (owner check 2026-07-18): block per exhaust EVENT — invisible to
    # the pre-bake (it fires on events, not card text). Whole-hand exhausters (Stoke,
    # Fiend Fire) count the remaining hand; no Dex/Frail on power-granted block.
    fnp_block = 0
    n_ex = 0
    if card.exhaust_count:
        n_ex = (max(0, state.hand_size - len(state.played) - 1)
                if card.exhaust_count == -1 else card.exhaust_count)
        if card.exhaust_count == -1 and card.exhaust_nonattack_only:
            # Second Wind exhausts NON-ATTACKS only (owner death 2026-08-12,
            # run -141919 r11: counting the leftover Strikes projected ~49
            # block vs the real 27 -- no death wall, no hail-mary, a tutor
            # potion died unused on the belt). Count includes unplayables
            # (Stoke+Wounds): hand arithmetic, minus attacks still unplayed.
            n_ex = max(0, n_ex - max(0, state.hand_attacks0
                                          - (state.n_attacks_played - state.n_attacks_played0)))
    if s.per_exhaust_block and n_ex:
        fnp_block = s.per_exhaust_block * n_ex
    sw_block = card.block_per_exhaust * n_ex if card.block_per_exhaust else 0
    block_gain = base_block + rage_bonus + fnp_block + sw_block
    # Unmovable: the turn's FIRST card-block doubles. Previews are resolved,
    # so if the power was up at turn start every block card in hand reads
    # doubled while the doubling is unspent -- the first play is as-read and
    # later ones must be halved; a power played inside this plan doubles the
    # (single-read) first block card after it. Block before the power (or a
    # second block card) spends nothing extra.
    first_block_used = s.first_block_used
    if base_block > 0 and card.potion_slot is None:
        if s.unmovable_active and not s.first_block_used and not s.unmovable_baked:
            block_gain += base_block
        elif s.unmovable_previews_doubled and s.first_block_used:
            block_gain -= base_block - base_block // 2  # spent inside this plan: halve the read
        first_block_used = True
    # Frail is likewise PRE-BAKED into the text (a Defend under Frail reads "Gain 3
    # Block", 5 x 0.75 — trace-verified 2026-07-14): do NOT re-apply FRAIL_MULT.
    # Forgotten Ritual: the energy fires only if a card was Exhausted this turn
    energy_gain = card.fx.energy_gain
    if card.energy_requires_exhausted and not s.exhausted_this_turn:
        energy_gain = 0
    # Restlessness (owner 2026-08-10): 'Retain. If your Hand is empty, draw 2
    # cards and gain [energy][energy].' The rider fires only on the play that
    # EMPTIES the hand; any earlier play is dead -- the flat parse credited it
    # as a free Adrenaline and the bot played it with the condition inactive.
    draw_gain = card.fx.draw
    if card.fx.requires_empty_hand and card.potion_slot is None:
        hand_left = state.hand_size - (len(state.played) - state.potions_spent) - 1
        if hand_left > 0:
            energy_gain = 0
            draw_gain = 0
    tripled = (s.my_block + block_gain) * 2 if card.triples_block else 0
    # HAND-LIMIT FIZZLE (owner catch 2026-08-29, seed-A T1: the bot burned ~2
    # draws into a full hand — Centennial's 3 landed as 1 — and reached
    # Pact's End+ a turn late; the whole seed-A draw divergence). Draws past
    # 10 cards do nothing in-game; cap the credit by live hand space so the
    # DFS discovers make-room-before-draw and late-Battle-Trance orderings.
    if draw_gain and not s.no_draw:
        # s.played already includes the current card here (unlike the
        # pre-play `state` snapshot used by the Fiend Fire count above)
        hand_now = s.hand_size - (len(s.played) - s.potions_spent) + s.draws
        draw_gain = max(0, min(draw_gain, 10 - hand_now))
    nxt = replace(
        s,
        my_block=s.my_block + block_gain + tripled,
        draws=s.draws + (0 if s.no_draw else draw_gain),
        no_draw=s.no_draw or card.blocks_draw,
        retain_hand=s.retain_hand or card.fx.retain_hand,
        energy=s.energy + energy_gain,
        self_damage=s.self_damage + card.fx.self_hp_cost,
        healing=s.healing + heal_applied,
        heal_wasted=s.heal_wasted + heal_forgone,
        # card-played Plating joins the end-of-turn pool (soaks incoming via the
        # tally at scoring; never feeds my_block/Body Slam/triples_block)
        end_turn_block=s.end_turn_block + card.fx.plating,
        frantic_played=s.frantic_played + (1 if card.frantic_escape else 0),
        growth_banked=s.growth_banked + card.fx.grows_per_play,
        # Cruelty played mid-plan: later attacks this turn ride the higher
        # multiplier -- the DFS discovers power-before-attack ordering from it
        vuln_mult_bonus=s.vuln_mult_bonus + card.vuln_amp,
        # Rupture: a self-HP-cost play is an on-your-turn HP loss -> Str
        my_strength=s.my_strength + card.fx.strength
        + card.fx.strength_temp  # Setup Strike-class: live for the plan...
        + (s.rupture_per_loss if card.fx.self_hp_cost > 0 else 0),
        # Potion-sourced Str is EXCLUDED from the horizon-scaled credit: the
        # owner's hoarding rule (Ovicopter A/B) gates potion spend on belt
        # pressure, and the 2x long-fight boost must not out-bid it.
        strength_gained=s.strength_gained + (
            0 if card.potion_slot is not None else card.fx.strength)
        + (s.rupture_per_loss if card.fx.self_hp_cost > 0 else 0),
        potion_strength=s.potion_strength + (
            card.fx.strength if card.potion_slot is not None else 0),
        exhausted_this_turn=s.exhausted_this_turn or card.exhausts_a_card,
        n_exhaust_events=s.n_exhaust_events + (1 if card.exhausts_a_card else 0),
        vuln_dmg_reduction=s.vuln_dmg_reduction or card.grants_vuln_reduction,
        hand_upgrades=s.hand_upgrades + card.upgrades_in_hand,
        # Aeonglass Withering Presence (owner decode 2026-08-28): every card
        # PLAY ticks the live countdown; crossing it manufactures an
        # escalating Wither. Potions aren't cards.
        wither_countdown=(
            (s.wither_period if s.wither_countdown == 1 else s.wither_countdown - 1)
            if s.wither_countdown and card.potion_slot is None
            else s.wither_countdown),
        # AMORTIZED (owner catch 2026-08-29, seed-B T3: Whirlwind played at 0
        # energy purely advancing the counter — crossing-only pricing made
        # advancement free): every card play pays tier/period in _score, so
        # withers_incurred now counts TICKING PLAYS, not crossings.
        withers_incurred=s.withers_incurred + (
            (1 + card.plays_pile_n)
            if (s.wither_countdown and card.potion_slot is None) else 0),
        pile_plays=s.pile_plays + card.plays_pile_n,
        # exhaust plays clear stranded statuses (Withers/Beckons): whole-hand
        # exhausters purge everything (Second Wind too — statuses aren't
        # attacks); chooser exhausts (TG+/Purity) eat the worst K in _score
        hand_purged=s.hand_purged or card.exhaust_count == -1,
        barricade=s.barricade or card.grants_barricade,
        unmovable_active=s.unmovable_active or card.grants_unmovable,
        first_block_used=first_block_used,
        targeted_exhausts=s.targeted_exhausts + card.targeted_exhaust_n,
    )
    # relic pass R1: fire mid-turn relic triggers this play crossed (counters, on-kill,
    # on-exhaust, on-potion, first-HP-loss). `state` is the pre-play snapshot.
    return _fire_relic_triggers(state, nxt, card)


def _fight_over(enemies) -> bool:
    """All leaders dead AND no dead enemy spawns on death (Infested): the fight truly ends.
    Minions flee with the leader; a dead spawner means a phase 2 is coming mid-turn."""
    leaders = [e for e in enemies if not e.is_minion]
    pool = leaders or list(enemies)
    if any(e.hp > 0 for e in pool):
        return False
    return not any(e.hp <= 0 and e.spawns_on_death for e in enemies)


def _hand_at_end(state: SimState) -> int:
    """Cards still in hand at end of turn: the turn-start hand minus plays
    (potions aren't hand cards), plus in-plan draws (10-card cap), minus
    chooser exhausts; a whole-hand exhaust leaves nothing. Cloak Clasp,
    Screaming Flagon, the retain credit and the hp_loss diagnostic read it
    (owner check 2026-09-11: draws were not counted, so a Pommel Strike's
    two drawn cards earned no Clasp block)."""
    if state.hand_purged:
        return 0
    n = max(0, state.hand_size - (len(state.played) - state.potions_spent))
    n = min(10, n + (0 if state.no_draw else state.draws))
    return max(0, n - state.targeted_exhausts)


def _score(
    state: SimState, w: CombatWeights, hp_pct: float = 1.0, power_horizon: float = 1.0,
    stranded_unblockable: dict[int, int] | None = None,
    stranded_blockable: dict[int, int] | None = None,
    my_hp: int = 999,
    fight_plan: str | None = None,
    debuff_wipe_hp: int = 0,
) -> float:
    # Lethal end-state (all leaders dead): stranded penalties and the death wall don't apply —
    # the fight ends before end of turn. A dead SPAWNER (Infested) means the fight continues.
    lethal_end = _fight_over(state.enemies)
    # A stunned enemy (dropped to/below its stun threshold this turn) skips its turn, so its
    # intent doesn't land — attacking down to the threshold can cancel an otherwise-lethal hit.
    incoming = sum(
        max(0, (e.incoming // 2 if state.vuln_dmg_reduction and e.vulnerable > 0
                else e.incoming) - state.hp_loss_reduction)
        for e in state.enemies if _enemy_attacking(e)
    )  # Colossus: 50% less dmg from Vulnerable enemies; Tungsten: -1 per attacker
    # Stranded status cards (Beckon "lose N HP" / Toxic "take N damage") bite at end of turn
    # UNLESS played — so the penalty must live in the scored objective, not just the post-hoc
    # hp_loss diagnostic, or the search can never prefer spending energy to clear one (the
    # bsmwhj26u Soul Fysh losses: 3 energy went into ~1-damage Intangible pokes while two
    # Beckons sat in hand for 12 unblockable). Keyed by hand index; a played card's penalty
    # vanishes. Skipped on a lethal end-state (the fight ends before end of turn).
    stranded_unb = stranded_blk = 0
    if ((stranded_unblockable or stranded_blockable) and not lethal_end
            and not state.hand_purged):  # whole-hand exhaust purged them all
        played_idx = {i for i, _ in state.played}
        vals = ([(v, True) for i, v in (stranded_unblockable or {}).items()
                 if i not in played_idx]
                + [(v, False) for i, v in (stranded_blockable or {}).items()
                   if i not in played_idx])
        if state.targeted_exhausts:
            # chooser exhausts (TG+/Purity) eat the worst stranded first —
            # the live hand_select prefers statuses/curses
            vals.sort(reverse=True)
            vals = vals[state.targeted_exhausts:]
        stranded_unb = sum(v for v, unb in vals if unb)
        stranded_blk = sum(v for v, unb in vals if not unb)
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
    # Relic pass R2: end-of-turn conditionals evaluate on the plan's END state.
    eot = state.eot_relics
    # hand size at end of turn (potions aren't hand cards): the turn-start hand
    # minus plays, plus in-plan draws (capped at the 10-card hand), minus
    # chooser exhausts; a whole-hand exhaust leaves nothing. Cloak Clasp and
    # Screaming Flagon read this (owner check 2026-09-11: draws were not
    # counted, so a Pommel Strike's two drawn cards earned no Clasp block).
    retained = _hand_at_end(state)
    # Retain-your-Hand credit (owner catch 2026-09-10, Insatiable r1: a 0-cost
    # Equilibrium went unplayed with block already up, and the Bloodletting it
    # would have kept was discarded): each retained playable card is next
    # turn's card in hand, priced as a draw-equivalent; statuses/curses earn
    # nothing (they would rather leave).
    retain_term = (w.w_retain_card * max(0, retained - state.purgeable_in_hand)
                   if state.retain_hand and not lethal_end else 0.0)
    my_block_eff = state.my_block
    if state.end_turn_block and not lethal_end:  # Plating lands before the enemy turn
        my_block_eff += state.end_turn_block
    # Ethereal x Feel No Pain (owner 2026-08-03): unplayed Ethereal cards (Daze)
    # exhaust at end of turn -- each one fires FNP before the enemy turn
    if state.per_exhaust_block and state.ethereal_hand and not lethal_end:
        _played_idx = {i for i, _ in state.played}
        my_block_eff += state.per_exhaust_block * sum(
            1 for i in state.ethereal_hand if i not in _played_idx)
    # Stampede: one RETAINED attack fires free at end of turn (random target)
    stampede_term = 0.0
    _back_attack_fight = any(e.back_attack and e.hp > 0 for e in state.enemies)
    if state.stampede_hand and not lethal_end:
        _sp_idx = {i for i, _ in state.played}
        _retained = [dmg for i, dmg in state.stampede_hand if i not in _sp_idx]
        if _retained:
            stampede_term = w.w_damage * (sum(_retained) / len(_retained)) * 0.9
            if _back_attack_fight:
                # Kaiser trap (owner): the free attack hits a RANDOM enemy,
                # flipping facing -- the +50% back-attack tax roughly eats
                # the free damage. Keep a sliver, not the full credit.
                stampede_term *= 0.2
    if state.stampede_played and _back_attack_fight and not lethal_end:
        # dock PLAYING the power into a back-attack fight (owner: often
        # better held or even exhausted vs Kaiser)
        stampede_term += w.w_stampede_backattack
    if eot and not lethal_end:
        if "CLOAK_CLASP" in eot:  # "gain 1 Block for each card in your Hand" at end of turn
            my_block_eff += retained
        if "ORICHALCUM" in eot and my_block_eff == 0:  # "end without Block -> gain 6"
            my_block_eff = 6
    if state.barricade:
        blocked = my_block_eff  # persistent block is all future-useful
        excess = 0
    else:
        blocked = min(my_block_eff, incoming)
        excess = max(0, my_block_eff - incoming)
        if "STURDY_CLAMP" in eot:  # "up to 10 Block persists" — that much is never waste
            excess = max(0, excess - 10)
    # Healing offsets HP lost (Not Yet); net it against the loss so both ride the same scarcity
    # curve — a heal is worth ~nothing at full HP and a lot when low, symmetric with Offering.
    # Stranded Beckon-type damage is unblockable: straight into the loss, past the block math.
    external_loss = (incoming - min(my_block_eff, incoming)
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
    if death_wall:
        # every branch that projects death pays the same wall; the self-HP
        # spent getting there is moot (the outright-suicide veto still holds
        # in _to_planned), so the tie breaks on what might still avert it --
        # pile plays, draws, damage -- not on Bloodletting's 3 HP (owner catch
        # 2026-09-11: Cascade+ at X=0 chosen over Bloodletting -> Cascade+ X=3)
        self_term = 0.0
    # quadratic focus-fire reward: concentrated damage beats spread damage, because
    # a finished enemy stops attacking (run 13: spread vs a 4-Nibbit pack = death)
    focus = sum(
        ((e.max_hp - e.hp) / e.max_hp) ** 2
        for e in state.enemies
        if not _ignorable_minion(e, state.has_summoner, state.guard_active)
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
    if fight_plan == "setup":  # setup-then-burst: banked turns are FOR powers
        power_term *= w.setup_power_mult
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
    # Relic pass R2: remaining end-of-turn conditional credits (small, next-turn value)
    eot_term = 0.0
    if eot and not lethal_end:
        if "PARRYING_SHIELD" in eot and my_block_eff >= 10:  # "end with >=10 Block: 6 dmg"
            eot_term += w.w_damage * 6
        if "SCREAMING_FLAGON" in eot and retained == 0:  # "empty hand: 20 dmg to ALL"
            eot_term += w.w_damage * 20
        if "PAELS_TEARS" in eot and state.energy > 0:  # unspent energy -> +2 next turn
            eot_term += w.w_next_turn_energy * 2
        if "ART_OF_WAR" in eot and state.n_attacks_played == 0:  # no attacks -> +1 energy
            eot_term += w.w_next_turn_energy
        if "POCKETWATCH" in eot and (len(state.played) - state.potions_spent) <= 3:
            eot_term += w.w_next_turn_draw * 3  # "<=3 cards played: draw 3 next turn"
        if "SELF_FORMING_CLAY" in eot and (state.self_damage > 0 or external_loss > 0):
            eot_term += w.w_next_turn_draw  # ~3 block next turn, tiny flat credit
    # Ice Cream: energy is conserved between turns — leftover energy is BANKED,
    # scored mildly positive so the planner will play generators for future turns
    # even with nothing to spend on now (owner 2026-07-31; must stay well below
    # w_damage-per-point so spending this turn always beats banking). Deliberate
    # underspend-toward-a-big-turn sequencing is multiturn-planner material.
    energy_waste_term = (w.w_banked_energy * max(0, state.energy) if "ICE_CREAM" in eot
                         else w.w_energy_waste * max(0, state.energy))
    if lethal_end:
        # the fight ends this turn: unspent energy is not waste and damage
        # past the kill is not progress (owner catch 2026-09-10: Brand -> Tear
        # Asunder+ 'lethal' on a 1-HP Exoskeleton, losing 1 HP, when a Strike
        # was lethal for free -- the extra damage and energy spend out-bid it)
        energy_waste_term = 0.0
    return (
        eot_term
        + stampede_term
        + crab_split
        + w.w_focus * focus
        # "setup" (setup-then-burst, owner 2026-08-18): a banked turn dampens
        # immediate-damage credit -- powers/draws/scaling outbid chip damage --
        # but a lethal end always keeps full value (never decline the kill)
        + w.w_damage * (max(0, state.damage_dealt - state.overkill) if lethal_end
                        else state.damage_dealt)
        * (w.setup_damage_mult if fight_plan == "setup" and not lethal_end else 1.0)
        + w.w_kill * state.kills
        # Reattach (Decimillipede): a segment kill with any segment left alive
        # at plan end is undone in 2 turns (revives at 25) -- cancel its kill
        # credit and charge the revive; the planner then lowers segments into
        # range and takes them together (arm v3 run 4: a 12-round grind died at
        # 74/80 entry, killing the same segment over and over)
        - ((w.w_kill + w.w_reattach_futile_kill) * state.reattach_kills
           + w.w_damage * state.reattach_revive_waste
           if state.reattach_kills and any(e.reattach and e.hp > 0 for e in state.enemies)
           else 0.0)
        + w.w_on_fatal_bonus * state.fatal_bonuses  # Feed lands the kill -> permanent payoff
        # Rainbow Ring (owner 2026-08-13; live text says EACH TURN, not once):
        # completing Attack+Skill+Power in one turn pays 1 Str + 1 Dex --
        # the DFS finds trio turns when the pieces are in hand
        + (w.w_rainbow_trio
           if state.rainbow_ring and state.n_attacks_played >= 1
           and state.n_skills_played >= 1 and state.n_powers_played >= 1
           else 0.0)
        # burning an If-Fatal Exhaust card on a MINION kill forfeits its future
        # payoff -- enough to lose the tie vs a plain finisher, never to block
        # a needed kill (the +8 bonus and w_kill dwarf it)
        - 0.25 * w.w_on_fatal_bonus * state.fatal_wasted
        # Sandpit clock (owner rule 2026-08-12): a cheap Frantic Escape per turn
        # buys +1 deadline turn -- worth more than a Strike, moot if this plan
        # already ends the fight ("unless sure of lethal in time")
        + (w.w_frantic_escape * state.frantic_played if not lethal_end else 0)
        # Rampage-class future growth: each play banks +N damage for the rest
        # of the combat -- worthless on the killing turn (no future)
        + (w.w_growth_future * state.growth_banked if not lethal_end else 0)
        + w.w_hand_upgrade * state.hand_upgrades  # Armaments-class rider (owner 07-13)
        + w.w_overkill * state.overkill
        # Multiturn P4 mode terms (owner review 2026-08-12): in "race" small
        # blocks never defer value ('blocking for 3 or 4 isn't worth deferring
        # bigger value' -- most-of-round mitigation keeps full credit); in
        # "defend" (a recurring deadline turn, e.g. Kaiser's Laser) block is
        # promoted -- the whole point of the mode is surviving THIS beat.
        + w.w_block_useful * blocked
        * (0.5 if fight_plan == "race" and blocked < 6 else
           w.defend_block_mult if fight_plan == "defend" else 1.0)
        + w.w_block_excess * excess
        + hp_weight * external_loss
        + self_term
        + death_wall
        # Staged-body debuff waste (Test Subject wiki pass 2026-08-15): an
        # Adaptable body wipes ALL statuses when it revives, so residual
        # vuln/weak credit dies once the body sits within one average turn of
        # the phase kill (debuff_wipe_hp = mean dmg/turn, from choose_mode).
        # In-plan amplification already paid through the damage terms.
        + (w.w_vulnerable * state.vuln_applied + w.w_weak * state.weak_applied)
        * (0.0 if debuff_wipe_hp > 0 and not any(
            e.hp > debuff_wipe_hp for e in state.enemies) else 1.0)
        # Artifact strips open the debuff window (owner's Aeonglass line: two cheap
        # debuffs eaten r2-r3, THEN Vulnerable landed and r4 dealt 250) — an eaten
        # debuff is a down payment, not pure waste
        + w.w_artifact_strip * state.artifact_strip_mult * state.artifact_stripped
        # Strength-horizon (backlog item, shipped 2026-08-19): Str's residual
        # value is future-turns x future-hits — in-plan contribution is already
        # realized through the damage terms, so a lethal end pays nothing
        # (Inflame on the killing turn loses to a plain finisher), and the
        # credit scales with the same remaining-turns estimate powers use.
        + w.w_strength * state.strength_gained
        * (0.0 if lethal_end else
           min(w.strength_horizon_max,
               max(w.strength_horizon_min,
                   power_horizon / w.strength_horizon_norm)))
        # potion Str keeps the OLD flat rate (still 0 on lethal): the horizon
        # boost must not out-bid the potion-hoarding discipline
        + w.w_strength * state.potion_strength * (0.0 if lethal_end else 1.0)
        + w.w_draw * state.draws
        + retain_term
        * (w.surplus_draw_mult if state.energy_surplus > 0 else 1.0)
        + energy_waste_term
        + w.w_play_friction * len(state.played)
        + power_term
        + w.w_rage_sequence * state.rage_block_granted
        + w.w_ramp_damage * state.ramp_damage
        + w.w_carrier_damage * state.carrier_damage
        + w.w_primal_keeper * state.keepers_rocked
        + state.flat_bonus
        + w.w_next_turn_block * state.carryover_block
        # turtling a ramper loses (Damp Cultist 2026-07-16: four all-block turns vs a
        # +5/turn Ritual, died at full-HP enemy) — damageless turns pay while one lives
        + (w.w_ramp_stall
           if (state.damage_dealt == 0 and not lethal_end
               and any(e.gains_strength and e.hp > 0 and not e.asleep
                       for e in state.enemies))
           else 0.0)
        + w.w_potion_spend * state.potions_spent
        + w.w_heal_waste * state.heal_wasted  # Not Yet burned at high HP
        + w.w_max_hp_cost * state.max_hp_spent  # permanent pool shrink
        # Withering Presence, AMORTIZED: every play advances the 6-count
        # clock, so each pays tier/period of the eventual Wither's drain
        # (total = one tier per cycle; crossing pays nothing extra). Kills
        # zero-value counter ticks (0-energy Whirlwind, seed-B T3) while
        # keeping early cheap-tier turns cheap — the owner's 'favorable
        # before it scales' shape falls out of tier escalation.
        + (w.w_wither_incurred * state.wither_tier_dmg * state.withers_incurred
           / max(1, state.wither_period)
           if not lethal_end else 0.0)
        + (w.w_vuln_payoff_dry * state.vuln_payoff_dry
           if not lethal_end else 0.0)
        + w.w_play_from_pile * state.pile_plays
        # deck-pollution purge: chooser exhausts (TG+/Purity) eat statuses
        # first; mass exhausts (Stoke/SW) eat them all. Credit the future
        # cycles the one-turn tally can't see.
        + w.w_status_purge * (
            state.purgeable_in_hand if state.hand_purged
            else min(state.targeted_exhausts, state.purgeable_in_hand))
        + w.w_wake_sleeper * state.wake_turns_forfeit
        # Entomancer's Personal Hive: each landed hit seeds Dazed (a dead future
        # draw each); nothing to pollute after the killing blow
        + (w.w_hive_dazed * state.hive_dazed if not lethal_end else 0.0)
        # Fight-open plan bias (Kin A/B 2026-07-30): the round-1 rollout comparison
        # picked a target order; these terms make the DFS serve it every turn.
        + (w.w_plan_focus_damage * state.focus_damage
           if fight_plan in ("focus", "race", "defend") else 0.0)
        + (w.w_plan_sweep_kill * state.kills if fight_plan == "sweep" else 0.0)
    )


# Status cards that bite if left in hand at end of turn — the incoming/block tally misses them. Two
# flavors, modeled DIFFERENTLY: Beckon "lose N HP" is unblockable (straight to HP); Toxic "take N
# damage" is blockable (leftover block soaks it). The caller keyword-gates on "in your hand" + "end
# of" (order/phrasing vary across cards), then these pull the number for the right pool.
_HAND_HP_LOSS_RE = re.compile(r"lose (\d+) hp", re.I)       # Beckon-type: unblockable
_HAND_TAKE_DMG_RE = re.compile(r"take (\d+) damage", re.I)  # Toxic-type: blockable


def plan_combat_turn(
    state: CombatState, weights: CombatWeights, used_potion_slots: tuple[int, ...] = (),
    hold_aoe_potions: bool = False, fight_plan: str | None = None,
    focus_target: str | None = None,
    exhausted_this_turn: bool = False, plays_this_turn: int = 0,
    debuff_wipe_hp: int = 0,
    artifact_strip_mult: float = 1.0,
    kinds_this_turn: tuple[int, int, int] = (0, 0, 0),
    excluded_indices: frozenset[int] = frozenset(),
    block_used_this_turn: bool = False,
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
    rupture_per_loss = 0
    vuln_mult_bonus = 0.0
    per_exhaust_block = 0  # Feel No Pain
    smoggy = False  # Living Fog: one Skill per turn
    end_turn_block = 0  # Plating: end-of-turn block that soaks this turn's incoming
    for p in player.status:
        pid = p.id.upper()
        # live id is STRENGTH_POWER — exact match silently zeroed player Strength in every
        # live plan (same _POWER-suffix bug family as the enemy VULNERABLE miss)
        if pid.startswith("STRENGTH") and p.amount:
            my_strength = p.amount
        if "DEXTER" in pid and p.amount:  # DEXTERITY_POWER; negative under Soul Siphon
            my_dex = p.amount
        if pid.startswith("FEEL_NO_PAIN") and p.amount:  # block per card Exhausted
            per_exhaust_block = p.amount
        # Living Fog's Smoggy (owner 2026-07-20): only one Skill per turn
        if pid.startswith("SMOGGY") or re.search(
                r"only (?:play )?(?:one|1) skill", p.description or "", re.I):
            smoggy = True
        # Knowledge Demon's Disintegration (and kin): end-of-turn blockable self-damage as a
        # PLAYER status. Parse the amount from the text so escalation (6->7->8) tracks live.
        if m := re.search(r"end of your turn, take (\d+) damage", p.description or "", re.I):
            self_end_damage += int(m.group(1))
        # Cruelty (power): "Vulnerable enemies take an additional 25% damage" — additive
        # with Vulnerable's own 50% (the game's hover preview confirms; owner 2026-07-12).
        # Text-parsed so any future +%-vs-Vulnerable power rides the same lane.
        if m := re.search(r"Vulnerable enemies take an additional (\d+)% damage",
                          p.description or "", re.I):
            vuln_mult_bonus += int(m.group(1)) / 100.0
        # Rupture (owner question 2026-08-12: 'did the planner even weigh the
        # 1 Str / 2 hp logic?' -- it didn't; the trigger sentence is stripped
        # and no seed existed): "Whenever you lose HP on your turn, gain N
        # Strength." Self-HP-cost plays (Bloodletting) now earn the strength,
        # so the trade is priced. Enemy-turn losses don't trigger (on YOUR turn).
        if m := re.search(r"whenever you lose hp on your turn, gain (\d+) strength",
                          p.description or "", re.I):
            rupture_per_loss += int(m.group(1))
        # Plating (Gorget / Stone Armor): "At the end of your turn, gain N Block" — that
        # block lands BEFORE the enemy turn, so it soaks incoming exactly like played
        # block. The harness's dominant clean signature (2026-07-16, n=31): hp_loss
        # over-predicted by ~Plating every turn it was up. Parse N from the text.
        if pid.startswith("PLATING") and (
                m := re.search(r"gain (\d+) Block", p.description or "", re.I)):
            end_turn_block += int(m.group(1))
        if pid.startswith("BARRICADE"):  # live id BARRICADE_POWER
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
    # 3 cards this turn. (N cards left)" — the STS2 text carries the LIVE remainder (the
    # pre-bake rule: displays are fully resolved), which covers the retroactive case too:
    # draw into Normality after 2 plays and "(1 card left)" is the truth, not the static 3.
    # Ignoring it planned a 3-card LETHAL with 1 play left — Bloodletting went through, the
    # gate ate Conflagration, run died (f45, batch b1i49b9k0, owner-caught live).
    for c in hand:
        if m := re.search(r"cannot play more than (\d+) cards", c.description or "",
                          re.IGNORECASE):
            cap = int(m.group(1))
            if m2 := re.search(r"\((\d+) cards? left\)", c.description or "", re.IGNORECASE):
                cap = min(cap, int(m2.group(1)))
            card_cap = cap if card_cap is None else min(card_cap, cap)

    hand_attacks = sum(1 for c in hand if (c.type or "") == "Attack")
    exhaust_pile = getattr(player, "exhaust_pile_count", None) or 0
    # upgrade targets for Armaments-class riders: unupgraded OTHERS (the played card
    # leaves the hand before the upgrade resolves)
    unupgraded_in_hand = sum(1 for c in hand if not getattr(c, "is_upgraded", False))
    # attack damages sitting in the (player-visible) discard pile, for the
    # Beat Down-class 'play N random Attacks from your Discard Pile' floor;
    # pile texts are resolved previews (Strength baked in), like hand texts
    discard_dmgs: list[int] = []
    for pc in (player.discard_pile or []):
        pdesc = pc.description or ""
        if re.search(r"random attacks? from your discard", pdesc, re.IGNORECASE):
            continue  # another Beat Down is not an attack
        pfx = parse_card_description(pdesc)
        if pfx.damage > 0:
            discard_dmgs.append(int(pfx.total_damage))
    discard_attack_dmgs = tuple(discard_dmgs)
    playable = [
        c for c in (
            _to_planned(card, energy, hand_attacks, exhaust_pile,
                        max(0, unupgraded_in_hand
                            - (0 if getattr(card, "is_upgraded", False) else 1)),
                        discard_attack_dmgs=discard_attack_dmgs)
            for card in hand
            # a play the game REFUSED through the whole settle window this turn
            # (router refused_cards): never resubmit it -- the Stomp stall loop
            if card.index not in excluded_indices
        )
        if c is not None
        # Absolute veto: a self-HP cost that kills us outright is never playable — at
        # death's-door the projected-death wall hits ALL branches equally, so the tie
        # broke on Bloodletting's energy bonus and the bot suicided (owner-caught
        # 2026-07-13). Certain self-death loses now; the enemy turn at least has variance.
        and not (c.fx.self_hp_cost > 0 and c.fx.self_hp_cost >= player.hp)
        # Cascade/Havoc under an active card cap: vetoed (see plays_top_cards)
        and not (card_cap is not None and c.plays_top_cards)
    ]
    # Mind Blast (item 112): damage = draw-pile size, resolved at plan time
    # (static within a turn to good approximation; each pc's fx is its own
    # instance, so the mutation is plan-local)
    _n_draw = len(player.draw_pile or [])
    for _pc in playable:
        if _pc.fx.dmg_equals_drawpile:
            _pc.fx.damage = _n_draw
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
            if ("FOUL" in nid or "GLOWWATER" in nid  # downside (cf. _potion_category)
                    # drinker-in-the-blast by TEXT (names lie): a Foul-class finisher
                    # at low HP is a mutual kill, and a mutual kill is a loss
                    # (owner ruling 2026-07-30)
                    or HITS_EVERYONE.search(potion.description or "")):
                continue
            pfx = parse_card_description(potion.description)
            if hold_aoe_potions and pfx.aoe and pfx.total_damage > 0:
                continue  # Explosive-class held for the swarms ahead (owner 2026-07-29)
            # Strength potions (Flex: "Gain 5 Strength... lose 5 at end of turn") join
            # too when the hand has attacks — str converts to damage per attack played
            # after it, and the DFS orders that correctly. Ovicopter A/B 2026-07-25:
            # the bot missed a fight-ending kill by 9 with a Flex in the belt; the
            # owner's read of the same hand: "very hard to get a Flex turn better
            # than this". w_potion_spend still keeps it out of non-lethal lines.
            str_pseudo = pfx.strength > 0 and any(
                pc.is_attack for pc in playable if pc.potion_slot is None)
            # Duplicator (owner 2026-08-02): joins the DFS so the DOUBLED play is
            # chosen, not guessed -- w_potion_spend keeps it banked until the
            # duplication flips something worth ~a potion (a lethal, an Offering),
            # which is the owner's 'save it for impactful plays' proxy.
            dup_pseudo = bool(re.search(
                r"next card (you )?play(ed)? .*(extra time|twice|additional time)",
                potion.description or "", re.IGNORECASE))
            # Fortifier (owner 2026-08-03): value = 2x in-plan block at drink
            # time; w_potion_spend banks it until the tripled block saves real
            # HP (a big-block turn against big incoming)
            fort_pseudo = bool(re.search(r"triple[^.]*block",
                                         potion.description or "", re.IGNORECASE))
            if (pfx.total_damage <= 0 and not str_pseudo and not dup_pseudo
                    and not fort_pseudo):
                continue
            playable.append(PlannedCard(
                index=-(potion.slot + 1), name=f"{potion.name} (potion)", cost=0, fx=pfx,
                targets_enemy=pfx.total_damage > 0 and not pfx.aoe,
                potion_slot=potion.slot,
                arms_duplicate=dup_pseudo,
                triples_block=fort_pseudo,
            ))
    # Thrash-class growth bonus: the exhausted attack's damage banks into the NEXT
    # play + thinning — future value the one-turn tally can't see. Granted only when
    # every OTHER attack in hand is fodder (owner: never risk eating a keeper).
    energy_surplus = energy - sum(
        pc.cost for pc in playable
        if pc.potion_slot is None
        and not (pc.name or "").rstrip("+").startswith(("Strike", "Defend"))
        and pc.fx.draw == 0
    )
    fiddle_no_draw = any(
        _RELIC_BLOCKS_DRAW.search(getattr(r_, "description", None) or "")
        for r_ in (player.relics or [])
    )
    for i, pc in enumerate(playable):
        if pc.fx.reveals_random:
            playable[i] = replace(pc, reveal_nudge=weights.w_reveal_early)
        elif (energy_surplus > 0
              and ((pc.fx.draw > 0 and not fiddle_no_draw) or pc.fx.tutors)
              and pc.cost <= energy_surplus and pc.potion_slot is None):
            # surplus energy: what draws/tutors fetch is USABLE -- surface
            # early (tutors added per audit item 71; under Fiddle the DRAW
            # half is dead so only tutors qualify -- owner check 2026-08-23)
            playable[i] = replace(pc, reveal_nudge=weights.w_reveal_early)
        elif (pc.cost <= 1
              and ((pc.fx.draw > 0 and not fiddle_no_draw) or pc.fx.tutors)
              and pc.potion_slot is None):
            # Owner rule (KD A/B 2026-08-14, WIDENED to cost<=1 per the
            # seed-A r5 catch 2026-08-29: the bot led Dominate over Pommel+
            # and never saw the draw's options): cheap draws open the turn —
            # drawn cards feed the replan loop, so surface them FIRST when
            # orderings are otherwise near-tied. The Battle Trance wrinkle
            # (suppresses further draw) is already priced: no_draw zeroes
            # later draws in-plan, keeping Pommel-before-Trance.
            playable[i] = replace(pc, reveal_nudge=weights.w_reveal_early)
    grow_attacks = [pc for pc in playable if pc.is_attack and pc.potion_slot is None]
    for i, pc in enumerate(playable):
        if pc.grows_on_exhaust:
            others = [a for a in grow_attacks if a.index != pc.index]
            # self-replayers are exhaust-SAFE (they come back), so they don't
            # veto the growth line -- eating one is the jackpot, not a loss
            if others and all(a.primal_fodder or a.self_replays for a in others):
                playable[i] = replace(pc, growth_bonus=weights.w_exhaust_growth)
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
    # Relic pass R1: build the held relics' mid-turn triggers; lifetime counters
    # (Nunchaku/Tuning Fork) continue from the live counter, Pen Nib-style.
    relic_triggers = []
    eot_relics = []
    cent_armed = demon_armed = axe_armed = False
    for r in player.relics:
        rid = (r.id or r.name or "").upper().replace(" ", "_")
        if rid in _EOT_RELICS:  # R2: end-of-turn conditionals, evaluated in _score
            eot_relics.append(rid)
        trig = _RELIC_TRIGGERS.get(rid)
        if trig is not None:
            if not trig.per_turn:
                trig = replace(trig, counter_start=r.counter or 0)
            relic_triggers.append(trig)
            if trig.kind == "first_hp_loss_combat":
                # armed only if provably unfired: entered THIS combat at full HP and
                # untouched so far (under-credits after any chip; never over-credits)
                cent_armed = player.hp == player.max_hp
            if trig.kind == "first_self_hp_loss_turn":
                demon_armed = True
        if _FIRST_CARD_TWICE.search(r.description or ""):
            # armed iff nothing has been played this combat yet: round 1, empty
            # discard/exhaust, full energy (approx — 0-cost first plays evade the
            # energy check, but piles catch non-power plays; documented tradeoff)
            axe_armed = (
                (state.battle.round or 1) == 1
                and not (getattr(player, "discard_pile_count", None) or 0)
                and not (getattr(player, "exhaust_pile_count", None) or 0)
                and player.energy == (player.max_energy or player.energy)
            )
        # Paper Phrog: "Enemies with Vulnerable take 75% more damage rather than 50%."
        # — rides the Cruelty vuln_mult_bonus lane (additive on VULN_MULT)
        if m := re.search(r"take (\d+)% more damage rather than 50%",
                          r.description or ""):
            vuln_mult_bonus += (int(m.group(1)) - 50) / 100.0
        # Velvet Choker-class: a play cap carried in RELIC text joins the card cap
        if m := re.search(r"cannot play more than (\d+) cards", r.description or "",
                          re.IGNORECASE):
            cap = int(m.group(1))
            card_cap = cap if card_cap is None else min(card_cap, cap)
    hp_loss_reduction = sum(
        1 for r in player.relics
        if "TUNGSTEN" in (r.id or r.name or "").upper())
    enemy_sims = _enemy_sims(state.battle.enemies, plays_this_turn)
    # Multiturn P4: the oracle's mode target overrides the biggest-body focus
    # (guard_break wants the MINION, Kaiser's race wants Rocket -- not the
    # largest max_hp). All focus machinery then serves the plan's target.
    if focus_target and any(e.entity_id == focus_target and e.hp > 0
                            for e in enemy_sims):
        enemy_sims = tuple(
            replace(e, is_big=(e.entity_id == focus_target)) for e in enemy_sims
        )
    # Purgeable junk in hand (owner catch 2026-08-31, Mecha Knight: TG+
    # unplayed at 4 energy with two Burns in hand — the stranded-clear
    # credit is this-turn-only, but exhausting a status removes it from the
    # DECK, saving its drain every future cycle): count unplayable
    # status/curse cards so exhaust plays earn the future-value purge.
    purgeable = sum(
        1 for c in hand
        if not c.can_play and (c.type or "") in ("Status", "Curse"))

    # Aeonglass Withering Presence (owner decode 2026-08-28): "Every 6 cards
    # you play, add a Wither to your Hand" — the power's amount is the LIVE
    # countdown (tape-verified 6→5→...→1, resets), so the DFS knows exactly
    # which planned play manufactures a Wither. Tier damage from a hand
    # Wither's live text when one exists; else 3+3X with X ≈ Increasing
    # Intensity casts (every 3rd turn from T3).
    wither_period = wither_countdown = wither_tier = 0
    for en in state.battle.enemies or []:
        for s_ in en.status or []:
            if m := re.search(r"every (\d+) cards you play.*add a wither",
                              s_.description or "", re.IGNORECASE):
                wither_period = int(m.group(1))
                wither_countdown = s_.amount or wither_period
    if wither_period:
        tiers = [int(m.group(1)) for c in hand
                 if "wither" in (c.name or "").lower()
                 and (m := _HAND_TAKE_DMG_RE.search((c.description or "").lower()))]
        rnd = state.battle.round or 1
        wither_tier = max(tiers) if tiers else 3 + 3 * (rnd // 3)

    unmovable_up = any(
        "UNMOVABLE" in (st_.id or "").upper()
        or re.search(r"first time you gain block from a card each turn, double",
                     st_.description or "", re.IGNORECASE) is not None
        for st_ in (player.status or []))
    start = SimState(
        energy=energy,
        # play-kind counts already made this turn (router turn memory): per-turn
        # relic cadences (Kusarigama/Shuriken/Kunai/Fan/Letter Opener) and the
        # Smoggy skill cap count from them. Arm v3 run 4 (2026-09-03): after
        # Break+ killed a Decimillipede segment, the replan forgot that attack,
        # saw Strike+Dismantle as 2 attacks (no Kusarigama 6), missed a real
        # lethal and blocked -- the segment revived and the fight was lost.
        n_attacks_played=kinds_this_turn[0],
        n_attacks_played0=kinds_this_turn[0],
        n_skills_played=kinds_this_turn[1],
        n_powers_played=kinds_this_turn[2],
        exhaust_pile0=exhaust_pile,
        wither_countdown=wither_countdown,
        wither_period=wither_period,
        wither_tier_dmg=wither_tier,
        artifact_strip_mult=artifact_strip_mult,
        purgeable_in_hand=purgeable,
        # Forgotten Ritual dead-in-hand (owner 2026-08-03): the API has no
        # 'exhausted this turn' field, so post-exhaust REPLANS priced the
        # conditional energy at zero and Ritual slid out of every plan. The
        # caller tracks the turn-start exhaust pile and seeds this flag.
        exhausted_this_turn=exhausted_this_turn,
        # Duplicator armed-state (audit find 2026-08-06): after the potion is
        # drunk the game exposes DUPLICATION_POWER ('your next card is played an
        # extra time') as a live status -- but a REPLAN between the drink and
        # the doubled play forgot the armed state entirely. Seed it.
        dup_armed=any(
            "DUPLICATION" in (s_.id or "").upper()
            or "played an extra time" in (s_.description or "").lower()
            for s_ in (player.status or [])),
        # no_draw must ALSO read the live NO_DRAW status (owner catch 2026-08-03:
        # a second Battle Trance was played under an active no-draw for phantom
        # +3-draw credit -- the seed only knew about Fiddle). The status IS in
        # the API; earlier-in-turn Trances set it.
        no_draw=fiddle_no_draw or any(
            "NO_DRAW" in (st_.id or "").upper()
            or re.search(r"(cannot|may not) draw", st_.description or "", re.IGNORECASE)
            is not None
            for st_ in (player.status or [])),
        unmovable_active=unmovable_up,
        unmovable_baked=unmovable_up,
        unmovable_previews_doubled=unmovable_up and not block_used_this_turn,
        first_block_used=block_used_this_turn,
        enemies=enemy_sims,
        my_block=player.block,
        my_strength=my_strength,
        my_dex=my_dex,
        # already baked into the card text preview — the sim adds only mid-plan gains
        my_strength_start=my_strength,
        my_dex_start=my_dex,
        self_end_damage=self_end_damage,
        rupture_per_loss=rupture_per_loss,
        vuln_mult_bonus=vuln_mult_bonus,
        per_exhaust_block=per_exhaust_block,
        smoggy=smoggy,
        end_turn_block=end_turn_block,
        barricade=barricade,
        my_weak=my_weak,
        my_frail=my_frail,
        surrounded=my_surrounded,
        hand_size=len(hand),
        hand_attacks0=sum(1 for c_ in hand if (c_.type or "") == "Attack"),
        # Owner rule (KD A/B 2026-08-14): 'is my hand good value for my
        # energy, or is it worth spending X to draw into my deck?' Surplus =
        # energy minus the cost of playable NON-BASIC, non-draw value cards
        # ('possible to spend all energy on non-strike/defends?'). Positive
        # surplus -> drawn cards are usable -> draw credit scales and draw
        # sources sequence early. At 3 energy with a good hand: no change.
        energy_surplus=energy_surplus,
        has_summoner=any(e.summons for e in enemy_sims),
        guard_active=(
            any(any(g in (e.name or "").upper() for g in _GUARDED_LEADER_NAMES)
                and e.hp > 0 for e in enemy_sims)
            and any(e.is_minion and e.hp > 0 for e in enemy_sims)
        ),
        heal_room=max(0, player.max_hp - player.hp),
        pen_nib_counter=pen_nib_counter,
        rainbow_ring=any("RAINBOW" in (r.id or r.name or "").upper()
                         for r in player.relics),
        pen_turn_started_at_nine=(pen_nib_counter is not None
                                  and pen_nib_counter % _PEN_NIB_PERIOD
                                  == _PEN_NIB_PERIOD - 1),
        relic_triggers=tuple(relic_triggers),
        cent_puzzle_armed=cent_armed,
        axe_armed=axe_armed,
        demon_tongue_armed=demon_armed,
        eot_relics=tuple(eot_relics),
        hp_loss_reduction=hp_loss_reduction,
        ethereal_hand=tuple(
            c.index for c in hand
            if re.search(r"ethereal", c.description or "", re.IGNORECASE)),
        stampede_hand=tuple(
            (pc.index, pc.fx.damage * max(1, pc.fx.hits))
            for pc in playable
            if pc.is_attack and pc.potion_slot is None and pc.fx.damage > 0
        ) if any(
            "STAMPEDE" in (s_.id or "").upper()
            or "random attack in your hand is played" in (s_.description or "").lower()
            for s_ in (player.status or [])) else (),
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
                      stranded_unblockable, stranded_blockable, my_hp=player.hp,
                      fight_plan=fight_plan, debuff_wipe_hp=debuff_wipe_hp)

    best_state = start
    best_score = scored(start)
    visited = 0
    # Ringing & kin cap cards/turn; default = hand size (search stays energy-bound). The cap stops
    # the planner *starting* a 2-card plan it can't finish (the live miss: blocked, then couldn't
    # hit); it commits to the single best card by the turn score (a lethal scores huge; a survival-
    # block dodges the death penalty). The fuller call — block now and hit on the clean turn the
    # Beast's Ringing/attack cycle guarantees, or read the draw pile — is deferred to §5-C.
    max_plays = card_cap if card_cap is not None else len(playable)

    def apply_play(sim: SimState, card: PlannedCard, ti: int | None) -> SimState:
        nxt = _apply_card(sim, card, ti)
        if card.arms_duplicate:
            return replace(nxt, dup_armed=True)
        # Duplicator armed: this card applies twice (free replay, one played entry)
        if sim.dup_armed and card.potion_slot is None:
            again = _apply_card(nxt, card, ti)
            nxt = replace(again, energy=again.energy + card.cost,
                          played=again.played[:-1], dup_armed=False)
        # Throwing Axe: the first CARD (not potion) of the combat replays free —
        # full effects, no energy, no extra play friction
        if (sim.axe_armed and card.potion_slot is None
                and not any(i >= 0 for i, _ in sim.played)):
            again = _apply_card(nxt, card, ti)
            nxt = replace(again, energy=again.energy + card.cost,
                          played=again.played[:-1], axe_armed=False)
        return nxt

    def after_random_exhaust(nxt: SimState, rest: list[PlannedCard]) -> list[PlannedCard]:
        # True Grit / Cinder pessimism (house rule, as Thrash): the random exhaust
        # eats the card the plan WANTS MOST next -- a one-step lookahead on the
        # post-play state over the affordable cards (potions and unaffordable
        # cards are harmless eats). The DFS then learns to play the needed card
        # BEFORE the exhauster (seed NDW2DDX5LZ: Defend before True Grit).
        cand = [i for i, c_ in enumerate(rest)
                if c_.potion_slot is None and (c_.is_x_cost or c_.cost <= nxt.energy)]
        if not cand:
            return rest
        alive = [k for k, e in enumerate(nxt.enemies) if e.hp > 0]

        def want(i: int) -> float:
            c_ = rest[i]
            if c_.targets_enemy and not c_.fx.aoe:
                if not alive:
                    return scored(nxt)
                return max(scored(apply_play(nxt, c_, k)) for k in alive[:3])
            return scored(apply_play(nxt, c_, None))

        eaten = max(cand, key=want)
        return rest[:eaten] + rest[eaten + 1:]

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
            # Normality "(0 cards left)": the DFS only checked the play budget when
            # RECURSING, so a 1-card plan was generable at zero budget (latent; found
            # by code-read during the 2026-07-22 owner stall report — no live firing
            # observed, but the class is real). Potions aren't cards: still legal.
            if plays_left <= 0 and card.potion_slot is None:
                continue
            eff_cost = sim.energy if card.is_x_cost else card.cost
            if card.fx.cost_less_per_attack:
                eff_cost = max(0, card.cost
                               - card.fx.cost_less_per_attack
                               * (sim.n_attacks_played - sim.n_attacks_played0))
            if eff_cost > sim.energy:
                continue
            if card.bound and sim.bound_played:  # Chains of Binding: one Bound play/turn
                continue
            # Forgotten Ritual-class (owner mystery T7, 2026-08-29): the
            # conditional energy is gated correctly, but the ENERGY-WASTE
            # term paid +0.15 net to burn a dead FR (spending on nothing
            # scored better than leftover energy). Unfulfilled, it is a
            # strictly-dead self-exhausting play -- veto, unless FNP is up
            # (the self-exhaust then buys real block).
            if (card.energy_requires_exhausted and not sim.exhausted_this_turn
                    and sim.per_exhaust_block <= 0):
                continue
            if sim.smoggy and card.is_skill and sim.n_skills_played >= 1:
                continue  # Smoggy: only one Skill per turn (Living Fog)
            # Restlessness-class 'if your Hand is empty' + Retain (owner
            # 2026-08-10): holding is free and a non-final play fizzles the
            # rider, so never play it while other cards remain in hand --
            # counting unplayables too (a Wither in hand keeps the condition
            # false in-game as well). As the true last card it fires and the
            # DFS can sequence it as a refuel finisher.
            # KNOWN GAP (owner, deferred 2026-08-10): under Runic Pyramid
            # ("no longer discard your Hand" -- IS in the pool: 32 logged
            # runs, held twice, relic_notes RUNIC_PYRAMID) the right move
            # flips to playing it as a hand-space clear. Needs hand-space
            # valuation (likely the multiturn planner); until then Pyramid
            # runs just hold it.
            if (card.fx.requires_empty_hand and card.potion_slot is None
                    and sim.hand_size - (len(sim.played) - sim.potions_spent) - 1 > 0):
                continue
            rest = remaining[:ci] + remaining[ci + 1 :]
            # Hand-exhausters (Fiend Fire, Stoke): the REST OF THE HAND is gone
            # (owner catch 2026-08-04: the plan read [Fiend Fire > Sword
            # Boomerang > Feel No Pain > Pyre] -- phantom post-exhaust plays
            # double-dipped the score, and the bot torched two potions' worth of
            # free Powers as 7-damage fodder). Potions survive; cards don't --
            # which also teaches the DFS to play free cards BEFORE the exhaust.
            if card.exhaust_count == -1:  # covers Stoke too (same text)
                if card.exhaust_nonattack_only:
                    # Second Wind: attacks SURVIVE and stay playable
                    rest = [c_ for c_ in rest
                            if c_.potion_slot is not None or c_.is_attack]
                else:
                    rest = [c_ for c_ in rest if c_.potion_slot is not None]
            elif card.exhausts_random_attack:
                # Thrash (owner catch 2026-08-27, Queen f48 r4: plan
                # [Thrash > Strike] with Strike the only other attack — the
                # follow-up was guaranteed torched; minion lived at 22 HP and
                # hit for its full intent). Pessimism per house rule: assume
                # it eats the attack the plan most WANTS (best damage), so
                # attack-first orderings surface naturally; potions survive;
                # the growth rider stays uncredited (conservative).
                atk_i = [i for i, c_ in enumerate(rest)
                         if c_.potion_slot is None and c_.is_attack]
                if atk_i:
                    eaten = max(atk_i, key=lambda i: rest[i].fx.total_damage)
                    rest = rest[:eaten] + rest[eaten + 1:]
            if card.targets_enemy and not card.fx.aoe:
                target_idx = [i for i, e in enumerate(sim.enemies) if e.hp > 0]
                # prefer distinct targets; cap target branching at 3 biggest threats
                target_idx.sort(key=lambda i: (-sim.enemies[i].incoming, sim.enemies[i].hp))
                for ti in target_idx[:3]:
                    visited += 1
                    nxt = apply_play(sim, card, ti)
                    score = scored(nxt)
                    if score > best_score:
                        best_score, best_state = score, nxt
                    nl = plays_left if card.potion_slot is not None else plays_left - 1
                    if nl > 0:
                        dfs(nxt, after_random_exhaust(nxt, rest)
                            if card.exhausts_random_card else rest, nl)
            else:
                visited += 1
                nxt = apply_play(sim, card, None)
                score = scored(nxt)
                if score > best_score:
                    best_score, best_state = score, nxt
                nl = plays_left if card.potion_slot is not None else plays_left - 1
                if nl > 0:
                    dfs(nxt, after_random_exhaust(nxt, rest)
                        if card.exhausts_random_card else rest, nl)

    dfs(start, playable, max_plays)

    if not best_state.played:
        return Decision(action=act.EndTurn(), rationale="no play improves the turn; end turn")

    first_index, first_target = best_state.played[0]
    chosen = next(c for c in playable if c.index == first_index)
    target = first_target if (chosen.targets_enemy and not chosen.fx.aoe) else None
    # Splash-AoE cards (Omnislice) are aoe in the sim but still need a click-target:
    # honor the game's target_type whenever the plan didn't produce one.
    if (chosen.requires_target or (chosen.targets_enemy and not chosen.fx.aoe)) \
            and target is None:
        alive = [e for e in start.enemies if e.hp > 0]
        target = alive[0].entity_id if alive else None
    if chosen.random_target:
        # RandomEnemy cards (Beat Down) take no click target; the sim targeted
        # them only so their damage credit could land
        target = None

    plan_names = []
    for idx, _tgt in best_state.played:
        match = next((c for c in playable if c.index == idx), None)
        plan_names.append(match.name if match else f"#{idx}")
    # Fight ends when the leaders die — Minion enemies flee, so they don't gate lethal.
    lethal = _fight_over(best_state.enemies)
    # Projected HP loss if we follow this line (post-block, post-kill incoming) — lets
    # callers tell "survivable with our own cards" from "actually facing death" so they
    # don't panic-drink a potion the planned block already covers.
    proj_incoming = sum(
        (e.incoming // 2 if best_state.vuln_dmg_reduction and e.vulnerable > 0
         else e.incoming)
        for e in best_state.enemies if _enemy_attacking(e)
    )  # mirror _score's Colossus halving — hail-mary callers read this number
    # Status cards stranded in hand hit you at end of turn; the incoming/block tally misses them.
    # Beckon "lose N HP" is unblockable (added straight to hp_loss); Toxic "take N damage" is
    # blockable (joins the incoming pool so leftover block soaks it). Count the *unplayed* ones so
    # hp_loss (and the hail-mary reading it) is honest. Skip on a lethal turn (fight ends first).
    extra_unblockable = 0
    extra_blockable = 0
    if not lethal and not best_state.hand_purged:  # whole-hand exhaust cleared them
        played_idx = {idx for idx, _ in best_state.played}
        dvals = ([(v, True) for i, v in stranded_unblockable.items()
                  if i not in played_idx]
                 + [(v, False) for i, v in stranded_blockable.items()
                    if i not in played_idx])
        if best_state.targeted_exhausts:  # TG+/Purity ate the worst ones
            dvals.sort(reverse=True)
            dvals = dvals[best_state.targeted_exhausts:]
        extra_unblockable = sum(v for v, unb in dvals if unb)
        extra_blockable = sum(v for v, unb in dvals if not unb)
    end_dmg = 0 if lethal else best_state.self_end_damage  # Disintegration, blockable
    # Plating's end-of-turn block joins the pool (mirrors _score; harness n=31)
    block_pool = best_state.my_block + (0 if lethal else best_state.end_turn_block)
    if not lethal:  # end-of-turn relic block joins the pool (mirrors _score)
        if "CLOAK_CLASP" in best_state.eot_relics:
            block_pool += _hand_at_end(best_state)
        if "ORICHALCUM" in best_state.eot_relics and block_pool == 0:
            block_pool = 6
    hp_loss = (max(0, proj_incoming + extra_blockable + end_dmg - block_pool)
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
            # Prediction-vs-reality harness (owner 2026-07-14): what this plan expects
            # to DEAL this turn. scripts/predict_audit.py diffs it against the enemy HP
            # actually lost — systematic gaps are unmodeled mechanics. (The Strength
            # double-count was exactly this class of error.) Diagnostic only.
            "plan_damage": float(best_state.damage_dealt),
        },
    )
