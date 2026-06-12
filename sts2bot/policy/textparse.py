"""Structured numbers out of card descriptions and intent labels.

The API gives rules text, not effect structs, so policies regex-extract the
common quantities. Anything unrecognized stays None/0 and policies treat the
card as 'unknown effects' rather than guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_DAMAGE = re.compile(r"\bDeal (\d+) damage", re.IGNORECASE)
_DAMAGE_TIMES = re.compile(r"\bDeal (\d+) damage (\d+) times", re.IGNORECASE)
_ALL_ENEMIES = re.compile(r"\bALL enem", re.IGNORECASE)
_BLOCK = re.compile(r"\bGain (\d+) Block", re.IGNORECASE)
_DRAW = re.compile(r"\bDraw (\d+) card", re.IGNORECASE)
_ENERGY = re.compile(r"\bGain (\d+) Energy", re.IGNORECASE)
_VULN = re.compile(r"\bApply (\d+) Vulnerable", re.IGNORECASE)
_WEAK = re.compile(r"\bApply (\d+) Weak", re.IGNORECASE)
_STRENGTH = re.compile(r"\bGain (\d+) Strength", re.IGNORECASE)
_LOSE_HP = re.compile(r"\bLose (\d+) HP", re.IGNORECASE)
_TAKE_DAMAGE = re.compile(r"\b[Tt]ake (\d+) damage")
_HEAL = re.compile(r"\bHeal (\d+) HP", re.IGNORECASE)
_INTENT_MULTI = re.compile(r"^(\d+)\s*[x×]\s*(\d+)$")  # noqa: RUF001 - real × appears in labels
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
    heal: int = 0
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
    if m := _DAMAGE_TIMES.search(text):
        fx.damage, fx.hits = int(m.group(1)), int(m.group(2))
        fx.recognized.append("damage")
    elif m := _DAMAGE.search(text):
        fx.damage = int(m.group(1))
        fx.recognized.append("damage")
    if fx.damage and _ALL_ENEMIES.search(text):
        fx.aoe = True
    if m := _BLOCK.search(text):
        fx.block = int(m.group(1))
        fx.recognized.append("block")
    if m := _DRAW.search(text):
        fx.draw = int(m.group(1))
        fx.recognized.append("draw")
    if m := _ENERGY.search(text):
        fx.energy_gain = int(m.group(1))
        fx.recognized.append("energy")
    if m := _VULN.search(text):
        fx.vulnerable = int(m.group(1))
        fx.recognized.append("vulnerable")
    if m := _WEAK.search(text):
        fx.weak = int(m.group(1))
        fx.recognized.append("weak")
    if m := _STRENGTH.search(text):
        fx.strength = int(m.group(1))
        fx.recognized.append("strength")
    if m := _LOSE_HP.search(text):
        fx.self_hp_cost = int(m.group(1))
        fx.recognized.append("hp_cost")
    if m := _HEAL.search(text):
        fx.heal = int(m.group(1))
        fx.recognized.append("heal")
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
    """HP cost mentioned in an event option / card ('Lose N HP' / 'take N damage')."""
    if not text:
        return 0
    cost = 0
    if m := _LOSE_HP.search(text):
        cost = max(cost, int(m.group(1)))
    if m := _TAKE_DAMAGE.search(text):
        cost = max(cost, int(m.group(1)))
    return cost
