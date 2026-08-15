"""Structured numbers out of card descriptions and intent labels.

The API gives rules text, not effect structs, so policies regex-extract the
common quantities. Anything unrecognized stays None/0 and policies treat the
card as 'unknown effects' rather than guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# "Deals" (third person) covers companion damage — Unleash/Snap "Osty deals 7 damage" parsed
# as 0 (card-pass audit, high impact). "(?! back)" excludes retaliation clauses (Flame Barrier
# "deal 4 damage back" is thorns, not on-play damage).
_DAMAGE = re.compile(r"\bDeals? (\d+) damage(?! back)", re.IGNORECASE)
# live text pre-resolves dynamic hit counts parenthetically: "... (Hits 6 times)"
_HITS_PAREN = re.compile(r"\(Hits (\d+) times\)", re.IGNORECASE)
# "N times" may sit after a target clause: Conflagration = "Deal 2 damage to ALL enemies 4
# times." parsed as 2 dmg x1 (a 4x under-value that cascaded: Bloodletting looked pointless
# because its payoff card looked worthless — owner-caught live 2026-07-09). Word numerals
# too: Twin Strike / Thrash / Fight Me / Astral Pulse all say "twice" (card-pass audit).
_DAMAGE_TIMES = re.compile(
    r"\bDeals? (\d+) damage(?: to (?:ALL enemies|a random enemy|an enemy))?"
    r" (?:(\d+) times|(twice)|(thrice))",
    re.IGNORECASE,
)
# "ALL other enemies" = splash (Omnislice); close enough to AoE for the planner
_ALL_ENEMIES = re.compile(r"\bALL (?:other )?enem", re.IGNORECASE)
# Body Slam-class: damage computed from CURRENT block (owner 2026-08-01: THE
# Barricade finisher). Harvested catalog texts carry a stale '(Deals N damage)'
# preview or none; the flag lets the rollout compute dynamically.
_DMG_EQ_BLOCK = re.compile(r"damage equal to your Block", re.IGNORECASE)
_REQ_EXHAUST_PILE = re.compile(
    r"If you have (\d+) or more cards? in your Exhaust Pile", re.IGNORECASE)
# Foul-class blast that includes the DRINKER (owner ruling 2026-07-30: a mutual kill
# is a loss). Single source — the guard text-drifted twice ('EVERYONE' -> 'ALL
# players and enemies'), so every consumer must share one pattern. Public: used by
# standard (hail-mary veto), combat (pseudo-card filter), rollout (belt filter).
HITS_EVERYONE = re.compile(r"\bEVERYONE\b|ALL (players|characters|creatures)",
                           re.IGNORECASE)
# Plating split out of Block (fuzz-harness find #1, 2026-08-10: Stone Armor+
# 'Ethereal. Gain 6 Plating.' logged blk=6 with 0% within +-1 -- Plating grants
# its block at END of turn, decaying 1/turn; as immediate block it phantom-fed
# Body Slam-class and triples_block effects). The one-turn sim routes plating
# into end_turn_block (same soak vs incoming); coarse sims re-merge it as block.
_BLOCK = re.compile(r"\bGain (\d+) Block", re.IGNORECASE)
_PLATING_GAIN = re.compile(r"\bGain (\d+) Plating", re.IGNORECASE)
_DRAW = re.compile(r"\bDraw (\d+) card", re.IGNORECASE)
# retrieval reads as draw: Dredge "Put 3 cards from your Discard Pile into your Hand"
_RETRIEVE = re.compile(r"\bPut (\d+) cards? from your Discard Pile into your Hand", re.IGNORECASE)
# Shivs are 0-cost 4-damage cards added to hand — approximate as immediate 4xN multi-hit
# (the loop replans per card, so the real Shivs are played right after; slight double-credit
# within one plan is bounded by the replan)
_SHIVS = re.compile(r"\bAdd (\d+|a) Shivs? (?:in)?to your Hand", re.IGNORECASE)
# Attack-generators: Infernal Blade "Add a random Attack into your Hand. It's free to play
# this turn." parsed to NOTHING, so 0-cost IB+ sat unplayed at pure friction cost (owner
# live-caught vs Waterfall Giant 2026-07-09). Credit an average random attack (~8); the
# replan sees the real generated card immediately after.
_RANDOM_ATTACK = re.compile(r"\bAdd (a|an|\d+) random Attacks? (?:in)?to your Hand", re.IGNORECASE)
_RANDOM_ATTACK_DMG = 8
# Discovery-class: "Choose 1 of 3 random cards to add into your Hand" — same
# sat-unplayed-at-friction failure mode as Infernal Blade (delta audit 2026-07-12)
_DISCOVER_CARD = re.compile(
    r"\bChoose \d+ of \d+ random cards? to add (?:in)?to your Hand", re.IGNORECASE)
# compound debuff: Shockwave "Apply 3 Weak and Vulnerable" — both get N
_COMPOUND_DEBUFF = re.compile(
    r"\bApply (\d+) (Weak and Vulnerable|Vulnerable and Weak)", re.IGNORECASE
)
# Trigger/deferred sentences must NOT parse as immediate effects (card-pass audit: Drum of
# Battle's "When this card is Exhausted, gain [energy]" credited the energy on play; Relax's
# "Next turn, draw 2..." credited the draw now; whenever-trigger Powers over-credited).
# Sentences starting with these are dropped before effect parsing; the conditional flag is
# still computed on the FULL text.
# "Every\b" not "Every \d": Panache's "Every time you play 5 cards..." slipped the strip and
# its 10 AoE credited as immediate — harness-confirmed FALSE LETHAL (delta audit 2026-07-12).
_TRIGGER_SENTENCE = re.compile(
    r"^\s*(When\b|Whenever\b|Every\b|Next turn\b|At the start\b|At the end\b)", re.IGNORECASE
)
_ENERGY = re.compile(r"\bGain (\d+) Energy", re.IGNORECASE)
# Some cards render gained energy as ICON tokens, not "N Energy" text (Luminesce: "Gain
# [ironclad_energy_icon.png][ironclad_energy_icon.png]. Exhaust."). Count the energy icons after
# "Gain" so iconized energy-gain isn't read as 0 (-> card left unplayed). Owner-caught 2026-06-26.
_ENERGY_ICON_RUN = re.compile(r"\bGain ((?:\s*\[[a-z_]*energy[a-z_]*\.png\])+)", re.IGNORECASE)
_ENERGY_ICON = re.compile(r"\[[a-z_]*energy[a-z_]*\.png\]", re.IGNORECASE)
_VULN = re.compile(r"\bApply (\d+) Vulnerable", re.IGNORECASE)
_WEAK = re.compile(r"\bApply (\d+) Weak", re.IGNORECASE)
_STRENGTH = re.compile(r"\bGain (\d+) Strength", re.IGNORECASE)
# Fight Me!-class: "The enemy gains 1 Strength." — an enemy-buff rider the survival
# math must see (the buffed intent hits THIS turn's incoming). No collision with
# _STRENGTH: "gains 1" never matches "\bGain (\d+)".
_ENEMY_STRENGTH = re.compile(r"\benem(?:y|ies) gains? (\d+) Strength", re.IGNORECASE)
_BLOCK_CARRYOVER = re.compile(
    r"next turn,? gain block equal to your current block", re.IGNORECASE)
_LOSE_HP = re.compile(r"\bLose (\d+) HP", re.IGNORECASE)
_LOSE_MAX_HP = re.compile(r"\bLose (\d+) Max(?:imum)? HP", re.IGNORECASE)
_TAKE_DAMAGE = re.compile(r"\b[Tt]ake (\d+) damage")
_HEAL = re.compile(r"\bHeal (\d+) HP", re.IGNORECASE)
# Flame Barrier-class thorns-for-a-turn (owner 2026-07-18): "Whenever you are attacked
# this turn, deal N damage back." Not CALLED Thorns, but that's what it does — the
# planner credits N per incoming hit this turn.
_RETALIATE = re.compile(r"attacked this turn, deal (\d+) damage back", re.IGNORECASE)
_FNP_GRANT = re.compile(r"[Ww]henever a card is Exhausted,? gain (\d+) Block")
_DOUBLE_IF_VULN = re.compile(r"[Ii]f the (?:enemy|target) is Vulnerable,? hits twice")
_COST_LESS_PER_ATTACK = re.compile(
    r"Costs? (\d+) less .{0,40}for each Attack played this turn", re.IGNORECASE)
# Fisticuffs: "Gain Block equal to damage dealt" — approximate block = damage (delta audit)
_BLOCK_EQ_DAMAGE = re.compile(r"Gain Block equal to (?:the )?damage dealt", re.IGNORECASE)
# The Gambit: "Gain 50 Block. If you take unblocked attack damage this combat, die." A
# self-death rider no one-turn horizon can certify against — the card must never be
# played or drafted by this pilot (delta audit, high impact).
_SELF_DEATH_RIDER = re.compile(r"\byou\b[^.]*\bdie\b|,\s*die\.", re.IGNORECASE)
# Bodyguard "Summon 5." / Pull Aggro "Summon 4. Gain 7 Block.": no companion state is
# exposed by the mod, so summoned companion HP is approximated as ADDED block-equivalent
# protection (it soaks hits like block; carryover between turns is upside we don't price).
_SUMMON_N = re.compile(r"\bSummon (\d+)")
# Replay N (Spiral/Glam enchants, Soldier's Stew): "Deal 6 damage. Replay 1." — the card
# is played N ADDITIONAL times for the same cost, so every effect scales by N+1. Live
# shape captured 2026-07-12 (enchants are appended as a trailing sentence).
_REPLAY = re.compile(r"\bReplay (\d+)\b")
_IF_HAND_EMPTY = re.compile(r"\bif your hand is empty\b", re.IGNORECASE)
# conditional/synergy language the one-turn planner cannot evaluate yet
_CONDITIONAL = re.compile(
    r"\b(if |when |whenever |after you|for each|next turn|at the start|at the end"
    r"|exhaust|top card|draw pile|discard pile)",
    re.IGNORECASE,
)
_INTENT_MULTI = re.compile(r"^(\d+)\s*[x×]\s*(\d+)$")
_INTENT_SINGLE = re.compile(r"^(\d+)$")


@dataclass
class CardEffects:
    damage: int = 0
    hits: int = 1
    aoe: bool = False
    # Infernal Blade-class gamble (owner 2026-08-03): generates a random card --
    # playing it EARLY reveals the option while the rest of the turn can still
    # use it (the per-poll replan sees the real card next poll)
    reveals_random: bool = False
    # Feel No Pain-class grant: playing this card makes every LATER exhaust
    # this combat yield N block (owner FNP->Infernal Blade+ case 2026-08-03)
    per_exhaust_block_grant: int = 0
    # Dismantle-class (owner 2026-08-04): 'If the enemy is Vulnerable, hits
    # twice' -- conditional hit-doubling the flat parse missed (8 read as 8,
    # real value vs a vuln target is 16, exactly the synergy line)
    double_hits_if_vuln: bool = False
    # Stomp-class (owner 2026-08-04): 'Costs 1 less energy for each Attack
    # played this turn' -- dynamic in-plan cost so attack->Stomp ordering is
    # discoverable inside ONE plan, not just across replans
    cost_less_per_attack: int = 0
    block: int = 0
    # Stone Armor-class "Gain N Plating": end-of-turn decaying block, NOT
    # immediate block (fuzz find #1 2026-08-10; see _PLATING_GAIN comment)
    plating: int = 0
    draw: int = 0
    energy_gain: int = 0
    vulnerable: int = 0
    weak: int = 0
    strength: int = 0
    enemy_strength: int = 0  # Fight Me!-class rider: "The enemy gains N Strength"
    self_hp_cost: int = 0
    max_hp_cost: int = 0
    heal: int = 0
    retaliate: int = 0  # Flame Barrier: damage dealt back per incoming hit this turn
    # Prolong: "Next turn, gain Block equal to your current Block." — value is a
    # snapshot of block AT PLAY TIME, delivered next turn (parsed to all-zeros
    # before; live 2026-07-25: 0-cost Prolong sat unplayed with block up)
    block_carryover: bool = False
    conditional: bool = False  # has synergy/conditional language the planner can't price
    # Rampage-class (owner audit 2026-08-15): 'Increase this card's damage by
    # N this combat.' The LIVE text bakes accumulated growth into 'Deal X'
    # (corpus: 9->14->19), so in-the-moment damage is always right; this field
    # carries the FUTURE +N/play value the one-turn tally can't see.
    grows_per_play: int = 0
    # Restlessness-class gate (owner 2026-08-10): "Retain. If your Hand is
    # empty, draw 2 cards and gain [energy][energy]." Effects parse flat here;
    # the combat sim fires them only on the play that EMPTIES the hand, and
    # the rollout zeroes them (its coarse deck cycle can't sequence the gate).
    requires_empty_hand: bool = False
    # The Gambit-class: a rider that KILLS YOU under conditions no one-turn plan can certify
    # against ("If you take unblocked attack damage this combat, die.") — never play/draft.
    self_death_rider: bool = False
    # Body Slam-class: 'Deal damage equal to your Block.' Live texts carry a
    # mod-baked preview number (parsed into `damage`, accurate per poll); harvested
    # catalog texts carry a STALE preview — the rollout computes from sim block.
    dmg_equals_block: bool = False
    # Pact's End-class threshold: 'If you have N or more cards in your Exhaust
    # Pile, deal X...' — the damage is REAL only when the pile (plus in-plan
    # exhausts) meets N. Ungated, the sim planned phantom lethals (f9 death
    # 2026-08-01: pile 0, 17 AoE credited, slugs survived, bot died believing
    # it had won).
    requires_exhaust_pile: int = 0
    recognized: list[str] = field(default_factory=list)

    @property
    def total_damage(self) -> int:
        return self.damage * self.hits

    @property
    def has_any_effect(self) -> bool:
        return bool(self.recognized)


def parse_card_description(text: str | None) -> CardEffects:
    fx = CardEffects()
    if not text:
        return fx
    full = text
    # drop trigger/deferred sentences ("When...", "Whenever...", "Next turn, ...") so their
    # effects aren't credited as immediate; the conditional flag still reads the full text
    text = ". ".join(
        s for s in full.split(". ") if not _TRIGGER_SENTENCE.match(s)
    )
    if _DMG_EQ_BLOCK.search(full):
        fx.dmg_equals_block = True
    if m := _REQ_EXHAUST_PILE.search(full):
        fx.requires_exhaust_pile = int(m.group(1))
    if m := _DAMAGE_TIMES.search(text):
        n = m.group(2)
        fx.damage = int(m.group(1))
        fx.hits = int(n) if n else (2 if m.group(3) else 3)  # "twice" / "thrice"
        fx.recognized.append("damage")
    elif m := _DAMAGE.search(text):
        fx.damage = int(m.group(1))
        fx.recognized.append("damage")
        if m2 := _HITS_PAREN.search(text):  # "(Hits 6 times)" — game-resolved dynamic count
            fx.hits = int(m2.group(1))
    if m := _SHIVS.search(text):  # approximate Shivs as immediate 4-damage hits
        n = 1 if m.group(1).lower() == "a" else int(m.group(1))
        if fx.damage == 0:
            fx.damage, fx.hits = 4, n
            fx.recognized.append("damage")
    if (m := _RANDOM_ATTACK.search(text)) and fx.damage == 0:  # Infernal Blade & kin
        n = 1 if m.group(1).lower() in ("a", "an") else int(m.group(1))
        fx.damage, fx.hits = _RANDOM_ATTACK_DMG, n
        fx.reveals_random = True
        fx.recognized.append("damage")
    elif _DISCOVER_CARD.search(text) and fx.damage == 0:  # Discovery: average-card EV
        fx.damage = _RANDOM_ATTACK_DMG
        fx.reveals_random = True
        fx.recognized.append("damage")
    if fx.damage and _ALL_ENEMIES.search(text):
        fx.aoe = True
    if m := _BLOCK.search(text):
        fx.block = int(m.group(1))
        fx.recognized.append("block")
    if m := _PLATING_GAIN.search(text):
        fx.plating = int(m.group(1))
        fx.recognized.append("plating")
    if (m := _DRAW.search(text)) or (m := _RETRIEVE.search(text)):
        fx.draw = int(m.group(1))
        fx.recognized.append("draw")
    if m := _ENERGY.search(text):
        fx.energy_gain = int(m.group(1))
        fx.recognized.append("energy")
    elif m := _ENERGY_ICON_RUN.search(text):  # iconized form: "Gain [energy][energy]"
        fx.energy_gain = len(_ENERGY_ICON.findall(m.group(1)))
        fx.recognized.append("energy")
    if m := _COMPOUND_DEBUFF.search(text):  # Shockwave: "Apply 3 Weak and Vulnerable"
        fx.weak = fx.vulnerable = int(m.group(1))
        fx.recognized += ["weak", "vulnerable"]
    if m := _VULN.search(text):
        fx.vulnerable = int(m.group(1))
        fx.recognized.append("vulnerable")
    if m := _WEAK.search(text):
        fx.weak = int(m.group(1))
        fx.recognized.append("weak")
    # Mass-debuff AoE (owner Shockwave check 2026-08-03): 'Apply 3 Weak and
    # Vulnerable to ALL enemies' carries no damage, so the damage-gated aoe
    # flag above missed it — both sims then debuffed ONE enemy, undercrediting
    # exactly the multi-enemy fights mass-debuffs are for.
    if (fx.vulnerable or fx.weak) and not fx.aoe and _ALL_ENEMIES.search(text):
        fx.aoe = True
    if m := _STRENGTH.search(text):
        fx.strength = int(m.group(1))
        fx.recognized.append("strength")
    if m := _ENEMY_STRENGTH.search(text):
        fx.enemy_strength = int(m.group(1))
        fx.recognized.append("enemy_strength")
    # NB search `full`: the "Next turn, ..." clause is exactly what the conditional-
    # sentence strip removes (same lesson as _RETALIATE below)
    if _BLOCK_CARRYOVER.search(full):
        fx.block_carryover = True
        fx.recognized.append("block_carryover")
    if m := _LOSE_MAX_HP.search(text):
        fx.max_hp_cost = int(m.group(1))
        fx.recognized.append("max_hp_cost")
    elif m := _LOSE_HP.search(text):
        fx.self_hp_cost = int(m.group(1))
        fx.recognized.append("hp_cost")
    if m := _HEAL.search(text):
        fx.heal = int(m.group(1))
        fx.recognized.append("heal")
    # searched in FULL text: the "Whenever you are attacked" trigger sentence is
    # stripped from `text`, but retaliation resolves THIS turn — it's the one
    # trigger whose expected value the one-turn planner can honestly price.
    if m := _RETALIATE.search(full):
        fx.retaliate = int(m.group(1))
        fx.recognized.append("retaliate")
    if _BLOCK_EQ_DAMAGE.search(text) and fx.damage and not fx.block:
        fx.block = fx.damage * fx.hits  # Fisticuffs-class: ~95% of the value in one regex
        fx.recognized.append("block")
    if m := _SUMMON_N.search(text):
        fx.block += int(m.group(1))  # companion HP ~ block-equivalent protection (Bodyguard)
        if "block" not in fx.recognized:
            fx.recognized.append("block")
    fx.self_death_rider = bool(_SELF_DEATH_RIDER.search(full))
    if m := _FNP_GRANT.search(full):  # trigger sentence: lives only in the FULL text
        fx.per_exhaust_block_grant = int(m.group(1))
    fx.double_hits_if_vuln = bool(_DOUBLE_IF_VULN.search(full))
    if m := _COST_LESS_PER_ATTACK.search(full):
        fx.cost_less_per_attack = int(m.group(1))
    # Replay N: the whole card resolves N+1 times — scale every effect, costs included
    # (self-HP riders repeat too). Damage scales via hits so multi-hit stays per-hit.
    if m := _REPLAY.search(text):
        n = 1 + int(m.group(1))
        fx.hits *= n
        fx.block *= n
        fx.draw *= n
        fx.energy_gain *= n
        fx.vulnerable *= n
        fx.weak *= n
        fx.strength *= n
        fx.heal *= n
        fx.self_hp_cost *= n
        if "replay" not in fx.recognized:
            fx.recognized.append("replay")
    fx.conditional = bool(_CONDITIONAL.search(full))  # flag reads the FULL text
    fx.requires_empty_hand = bool(_IF_HAND_EMPTY.search(full))
    if m := re.search(r"increase this card's damage by (\d+)", full, re.IGNORECASE):
        fx.grows_per_play = int(m.group(1))
    return fx


def parse_intent_damage(label: str | None) -> int:
    """Incoming damage from an Attack intent label ('11' or '3x4' styles)."""
    if not label:
        return 0
    label = label.strip()
    if m := _INTENT_MULTI.match(label):
        return int(m.group(1)) * int(m.group(2))
    if m := _INTENT_SINGLE.match(label):
        return int(m.group(1))
    return 0


def parse_hp_cost(text: str | None) -> int:
    """HP cost mentioned in an event option / card ('Lose N HP' / 'take N damage').
    Max-HP loss is permanent, so it counts several times over (the 'max HP vampire'
    event killed three runs while reading as free)."""
    if not text:
        return 0
    cost = 0
    if m := _LOSE_HP.search(text):
        cost = max(cost, int(m.group(1)))
    if m := _TAKE_DAMAGE.search(text):
        cost = max(cost, int(m.group(1)))
    if m := _LOSE_MAX_HP.search(text):
        cost = max(cost, int(m.group(1)) * 8)
    return cost
