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
_BLOCK = re.compile(r"\bGain (\d+) (?:Block|Plating)", re.IGNORECASE)  # Plating ~ recurring block
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
_LOSE_HP = re.compile(r"\bLose (\d+) HP", re.IGNORECASE)
_LOSE_MAX_HP = re.compile(r"\bLose (\d+) Max(?:imum)? HP", re.IGNORECASE)
_TAKE_DAMAGE = re.compile(r"\b[Tt]ake (\d+) damage")
_HEAL = re.compile(r"\bHeal (\d+) HP", re.IGNORECASE)
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
    block: int = 0
    draw: int = 0
    energy_gain: int = 0
    vulnerable: int = 0
    weak: int = 0
    strength: int = 0
    self_hp_cost: int = 0
    max_hp_cost: int = 0
    heal: int = 0
    conditional: bool = False  # has synergy/conditional language the planner can't price
    # The Gambit-class: a rider that KILLS YOU under conditions no one-turn plan can certify
    # against ("If you take unblocked attack damage this combat, die.") — never play/draft.
    self_death_rider: bool = False
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
        fx.recognized.append("damage")
    elif _DISCOVER_CARD.search(text) and fx.damage == 0:  # Discovery: average-card EV
        fx.damage = _RANDOM_ATTACK_DMG
        fx.recognized.append("damage")
    if fx.damage and _ALL_ENEMIES.search(text):
        fx.aoe = True
    if m := _BLOCK.search(text):
        fx.block = int(m.group(1))
        fx.recognized.append("block")
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
    if m := _STRENGTH.search(text):
        fx.strength = int(m.group(1))
        fx.recognized.append("strength")
    if m := _LOSE_MAX_HP.search(text):
        fx.max_hp_cost = int(m.group(1))
        fx.recognized.append("max_hp_cost")
    elif m := _LOSE_HP.search(text):
        fx.self_hp_cost = int(m.group(1))
        fx.recognized.append("hp_cost")
    if m := _HEAL.search(text):
        fx.heal = int(m.group(1))
        fx.recognized.append("heal")
    if _BLOCK_EQ_DAMAGE.search(text) and fx.damage and not fx.block:
        fx.block = fx.damage * fx.hits  # Fisticuffs-class: ~95% of the value in one regex
        fx.recognized.append("block")
    if m := _SUMMON_N.search(text):
        fx.block += int(m.group(1))  # companion HP ~ block-equivalent protection (Bodyguard)
        if "block" not in fx.recognized:
            fx.recognized.append("block")
    fx.self_death_rider = bool(_SELF_DEATH_RIDER.search(full))
    fx.conditional = bool(_CONDITIONAL.search(full))  # flag reads the FULL text
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
