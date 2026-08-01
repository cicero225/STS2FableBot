"""Monte-Carlo fight rollouts — the forward model's estimator core (PLAN §5.2).

Replaces the closed-form HP race (`estimate_fight`) for strategic consumers: instead
of summarizing the deck as static output, PLAY the fight forward — shuffle a
simulated copy of the deck (our own RNG, never the game's), draw hands, pick plays,
apply enemy pressure, repeat to fight end. N rollouts give a distribution: win
rate, expected end HP, tail. Draw variance, dead curses, energy economy, exhaust
thinning, and strength accumulation price themselves because the simulation plays
them.

TWO turn policies drive ONE physics (`_RolloutSim`), so their estimates differ only
by decision quality, never by simulation drift:
- "greedy" (P1, calibrated on elites: act-1 93%/95%, act-2 86%/81%): fast heuristic
  picks, ~3ms per fight estimate — the map-time workhorse.
- "dfs" (P1.7): the REAL one-turn planner (`plan_combat_turn`) chooses each play via
  a synthesized CombatState — prices the long-fight sophistication (vuln farming,
  engine loops, sequencing) that the greedy can't, for BOSS estimates where the
  greedy's residual lives (bosses predicted ~20% vs 57% actual). Slower by design;
  timing is returned to the caller (owner 2026-07-29: log the time — the amount
  matters for iteration speed).

Design decisions (owner-reviewed): enemy model = bestiary dps/mechanics abstraction
(wiki-exact pass is the upgrade path); determinism via a content-derived seed so
identical inputs give identical estimates and replay determinism survives.

Pure functions; no I/O.
"""
from __future__ import annotations

import random
import re
import time as _time
import zlib
from dataclasses import dataclass

from sts2bot.policy.capability import FightEnemy
from sts2bot.policy.textparse import (
    HITS_EVERYONE,
    CardEffects,
    parse_card_description,
)

_UNPLAYABLE = re.compile(r"\bunplayable\b", re.IGNORECASE)
_ETHEREAL = re.compile(r"\bethereal\b", re.IGNORECASE)
_EXHAUST_SELF = re.compile(r"\bexhaust\.\s*$|\bexhaust\b(?!\s+(a|all|your|the|up))",
                           re.IGNORECASE)
_EOT_HAND_LOSS = re.compile(r"lose (\d+) hp", re.IGNORECASE)
_ADD_RANDOM_PER_EXHAUST = re.compile(r"add (\d+) random card", re.IGNORECASE)
_DEAL_N = re.compile(r"(?i)\b(deal )(\d+)( damage)")


def _rebake_strength(text: str, strength: int) -> str:
    """Synth-bridge v2: fold accumulated Strength into an attack's damage numbers so
    the one-turn planner prices the card the way the game's own UI would show it.
    Per-hit numbers get the full bonus ('Deal 6 damage 2 times' -> each hit +str).
    Non-numeric damage ('equal to your Block') is left alone."""
    if not strength:
        return text
    return _DEAL_N.sub(
        lambda m: f"{m.group(1)}{max(0, int(m.group(2)) + strength)}{m.group(3)}", text
    )


@dataclass
class _Card:
    name: str
    cost: int  # energy cost; unplayable cards never enter the playable pool
    fx: CardEffects
    is_attack: bool
    is_power: bool
    unplayable: bool
    exhausts: bool
    ethereal: bool
    eot_hand_loss: int  # Bad Luck-class: lose N HP if in hand at end of turn
    shreds_hand: bool = False  # Stoke-class: exhaust hand, add a card per exhausted
    text: str = ""  # original rules text (the DFS bridge synthesizes states from it)
    ctype: str = "Attack"
    cid: str = ""


@dataclass
class _Foe:
    hp: int
    dps: int
    ramp: int
    counts: bool
    cap: int | None
    slippery: bool
    self_block: int
    thorns: int
    death_damage: int
    death_damage_growth: int
    heals: int
    dot: int
    death_timer: int
    str_gained: int = 0
    vuln: int = 0
    lost_this_turn: int = 0
    slipped_this_turn: bool = False
    wave: int = 0
    dormant: bool = False  # wave>0 body not yet spawned: untargetable, not attacking
    artifact: int = 0  # charges that eat incoming debuffs (Aeonglass opens with 3)
    sleep: int = 0  # Lagavulin-class: turns left asleep (no attacks); ANY damage wakes


@dataclass(frozen=True)
class RolloutResult:
    win_rate: float
    exp_end_hp: float  # mean end HP over all rollouts (losses count 0)
    p25_end_hp: float  # pessimistic tail — gate material
    mean_turns: float
    n: int = 0
    # mean kill-HP still standing at the end (0 on wins) — the loss GRADIENT draft
    # pricing needs: on an unwinnable boss every option scores end_hp 0, but a card
    # that gets 30 HP closer to the kill is still the right pick (§5-C, 2026-07-30)
    exp_enemy_hp_left: float = 0.0

    @property
    def win(self) -> bool:
        return self.win_rate >= 0.5


# persistent powers the loops honor beyond their one-shot fx
_FNP = ("FEEL_NO_PAIN",)
_DARK_EMBRACE = ("DARK_EMBRACE",)
_BARRICADE = ("BARRICADE",)


def _build_cards(deck, card_effects: dict | None) -> list[_Card]:
    out = []
    for c in deck or []:
        cid = (getattr(c, "id", "") or "").upper()
        up = 1 if getattr(c, "is_upgraded", False) else 0
        text = getattr(c, "description", None) or (
            (card_effects or {}).get(f"{cid}|{up}")
            or (card_effects or {}).get(f"{cid}|0") or ""
        )
        fx = parse_card_description(text)
        ctype = (getattr(c, "type", "") or "")
        raw_cost = getattr(c, "cost", None)
        try:
            cost = max(0, int(raw_cost))
        except (TypeError, ValueError):
            cost = 1  # X-cost: approximate as 1 (spend-all modeling is v2)
        unplayable = (ctype in ("Curse", "Status") and "playable" not in text.lower()
                      ) or bool(_UNPLAYABLE.search(text))
        m = _EOT_HAND_LOSS.search(text) if "end of" in text.lower() else None
        out.append(_Card(
            name=getattr(c, "name", "") or cid,
            cost=cost,
            fx=fx,
            is_attack=ctype == "Attack",
            is_power=ctype == "Power",
            unplayable=unplayable,
            exhausts=bool(_EXHAUST_SELF.search(text)),
            ethereal=bool(_ETHEREAL.search(text)),
            eot_hand_loss=int(m.group(1)) if m else 0,
            shreds_hand=("exhaust your hand" in text.lower()
                         and bool(_ADD_RANDOM_PER_EXHAUST.search(text))),
            text=text,
            ctype=ctype or "Attack",
            cid=cid,
        ))
    return out


def _hit(foe: _Foe, amount: int, vuln_mult: float = 1.5) -> int:
    """One damage instance into a foe, honoring Slippery / per-turn caps / self-block.
    Returns HP actually removed."""
    if foe.slippery and not foe.slipped_this_turn:
        foe.slipped_this_turn = True
        amount = min(amount, 1)
    amount = max(0, amount - foe.self_block)
    if foe.vuln > 0:
        amount = int(amount * vuln_mult)
    if foe.cap is not None:
        amount = min(amount, max(0, foe.cap - foe.lost_this_turn))
    amount = min(amount, foe.hp)
    foe.hp -= amount
    foe.lost_this_turn += amount
    return amount


def _classify_potions(potions) -> list[tuple[str, int]]:
    """(kind, amount) per usable potion: heal/block/damage/aoe/strength/energy.
    Downside/unknown potions never join (mirrors the live lanes)."""
    out = []
    for p in potions or []:
        nid = f"{getattr(p, 'id', '') or ''} {getattr(p, 'name', '') or ''}".upper()
        if ("FOUL" in nid or "GLOWWATER" in nid
                # drinker-in-the-blast by TEXT (names lie; a mutual kill is a loss)
                or HITS_EVERYONE.search(getattr(p, "description", None) or "")):
            continue
        fx = parse_card_description(getattr(p, "description", None) or "")
        if fx.heal > 0 or "BLOOD" in nid:
            out.append(("heal", fx.heal or 20))
        elif fx.block > 0:
            out.append(("block", fx.block))
        elif fx.total_damage > 0:
            out.append(("aoe" if fx.aoe else "damage", fx.total_damage))
        elif fx.strength > 0:
            out.append(("strength", fx.strength))
        elif fx.energy_gain > 0 or "ENERGY" in nid:
            out.append(("energy", fx.energy_gain or 2))
    return out


# High-impact combat relics the boss estimate must see (calibration 2026-07-29:
# bosses predicted 15-22% vs 55% actual -- the live bot wins them with potions
# and relics). Small table by design; unknowns are ignored.
_RELIC_FX = {
    "VAJRA": ("start_str", 1),
    "ODDLY_SMOOTH_STONE": ("start_block_per_turn", 1),  # +1 dex ~ +1 block/turn
    "ANCHOR": ("t1_block", 10),
    "HORN_CLEAT": ("t2_block", 14),
    "BAG_OF_MARBLES": ("t1_vuln", 1),
    "BAG_OF_PREPARATION": ("t1_draw", 2),
    "LANTERN": ("t1_energy", 1),
    "HAPPY_FLOWER": ("energy_every_3", 1),
    "PRISMATIC_GEM": ("energy_per_turn", 1),
    "ORICHALCUM": ("eot_block_if_none", 6),
    "BURNING_BLOOD": ("post_win_heal", 6),
    "BLACK_BLOOD": ("post_win_heal", 12),
    "MEAT_ON_THE_BONE": ("post_win_heal", 12),  # if below half; approximate
    "PAPER_PHROG": ("vuln_mult", 1),  # vulnerable hits harder
    # Fiddle (owner 2026-07-31): +2 cards at turn start, NO in-turn draws --
    # both halves matter or draw decks misprice badly
    "FIDDLE": ("fiddle", 2),
    # Whispering Earring (owner 2026-08-01): +1 energy/turn is the big upside;
    # the drawback (Vakuu autoplays turn 1 left-to-right) is modeled separately
    # via the auto_turn1 flag below.
    "WHISPERING_EARRING": ("energy_per_turn", 1),
}


class _RolloutSim:
    """One rollout's physics: deck piles, energy, block, foes, potions, relics.
    Turn policies only CHOOSE plays; all effects apply here, so greedy and DFS
    estimates differ by decision quality alone."""

    def __init__(self, cards, enemies, player_hp, max_hp, rng, pots, rfx):
        self.foes = [_Foe(hp=e.hp, dps=e.dps, ramp=e.str_ramp,
                          counts=e.counts_toward_kill, cap=e.dmg_cap_per_turn,
                          slippery=e.slippery, self_block=e.self_block,
                          thorns=e.thorns, death_damage=e.death_damage,
                          death_damage_growth=e.death_damage_growth,
                          heals=e.heals_per_turn, dot=e.player_dot_avg,
                          death_timer=e.death_timer, wave=e.wave,
                          dormant=e.wave > 0, artifact=e.artifact,
                          sleep=e.sleep_turns)
                     for e in enemies]
        self.rng = rng
        self.rfx = rfx or {}
        self.prefer_big = False  # set by rollout_fight(target_order="focus")
        self.n_exhausted = 0  # exhaust events this fight (Pact's End gate)
        self.belt = list(pots)
        self.draw = cards[:]
        rng.shuffle(self.draw)
        self.discard: list[_Card] = []
        self.hand: list[_Card] = []
        self.hp = int(player_hp)
        self.max_hp = int(max_hp)
        self.my_str = self.rfx.get("start_str", 0)
        self.vm = 1.75 if self.rfx.get("vuln_mult") else 1.5
        self.fnp = 0
        self.de_draw = 0
        self.barricade = False
        self.block = 0
        self.energy = 0
        self.turn = 0
        self.outcome: tuple[bool, int] | None = None  # (won, end_hp)

    # ---------------------------------------------------------------- plumbing
    def spend(self, kind: str) -> int:
        for i, (k, amt) in enumerate(self.belt):
            if k == kind:
                self.belt.pop(i)
                return amt
        return 0

    def alive_leaders(self):
        # win condition: dormant bodies still hold kill-HP (Phrog phase 2)
        return [f for f in self.foes if f.counts and f.hp > 0]

    def targets(self):
        # what's actually on the field: alive AND spawned
        return [f for f in self.foes if f.hp > 0 and not f.dormant]

    def best_target(self):
        # "sweep" (default): lowest-HP body first — clear the board, shed dps.
        # "focus": highest-HP leader first — race the big body (Kin-race style).
        # Fight-open plan selection compares both orders (owner 2026-07-30).
        on_field = self.targets()
        leaders = [f for f in on_field if f.counts]
        if self.prefer_big:
            return max(leaders or on_field, key=lambda f: f.hp, default=None)
        return min(leaders or on_field, key=lambda f: f.hp, default=None)

    def _advance_wave(self):
        if any(not f.dormant and f.hp > 0 for f in self.foes):
            return
        sleepers = [f for f in self.foes if f.dormant and f.hp > 0]
        if sleepers:
            nxt = min(f.wave for f in sleepers)
            for f in sleepers:
                if f.wave == nxt:
                    f.dormant = False

    def draw_one(self):
        if not self.draw:
            self.draw, self.discard = self.discard, []
            self.rng.shuffle(self.draw)
        if self.draw:
            self.hand.append(self.draw.pop())

    def exhaust_event(self):
        self.n_exhausted += 1
        self.block += self.fnp
        for _ in range(self.de_draw):
            self.draw_one()

    def _win(self):
        self.hp = min(self.max_hp, self.hp + self.rfx.get("post_win_heal", 0))
        self.outcome = (True, min(self.max_hp, self.hp))

    # ---------------------------------------------------------------- turn frame
    def start_turn(self):
        self.turn += 1
        rfx = self.rfx
        if not self.barricade:
            self.block = 0
        self.block += rfx.get("start_block_per_turn", 0)
        if self.turn == 1:
            self.block += rfx.get("t1_block", 0)
            self.my_str += self.spend("strength")  # fight-start buffs (live lane 4)
            for f in self.foes:
                if f.hp > 0 and not f.dormant:
                    if f.artifact > 0 and rfx.get("t1_vuln", 0):
                        f.artifact -= 1
                    else:
                        f.vuln += rfx.get("t1_vuln", 0)
        if self.turn == 2:
            self.block += rfx.get("t2_block", 0)
        for f in self.foes:
            f.lost_this_turn = 0
            f.slipped_this_turn = False
        self.hand = []
        for _ in range(5 + rfx.get("fiddle", 0)
                       + (rfx.get("t1_draw", 0) if self.turn == 1 else 0)):
            self.draw_one()
        self.energy = (3 + rfx.get("energy_per_turn", 0)
                       + (rfx.get("t1_energy", 0) if self.turn == 1 else 0)
                       + (rfx.get("energy_every_3", 0) if self.turn % 3 == 0 else 0))
        if self.turn == 1:
            self.energy += self.spend("energy")

    def playable(self):
        return [c for c in self.hand if not c.unplayable and c.cost <= self.energy]

    def apply_card(self, pick: _Card, target: _Foe | None):
        self.hand.remove(pick)
        self.energy -= pick.cost
        self.energy += pick.fx.energy_gain
        self.hp = max(0, self.hp - pick.fx.self_hp_cost)
        self.hp = min(self.max_hp, self.hp + pick.fx.heal)
        self.block += pick.fx.block
        self.my_str += pick.fx.strength
        if not self.rfx.get("fiddle"):  # Fiddle: in-turn draws are dead
            for _ in range(pick.fx.draw):
                self.draw_one()
        if pick.fx.total_damage > 0 or pick.fx.dmg_equals_block:
            tgts = (self.targets() if pick.fx.aoe
                    else ([target] if target is not None else []))
            # Body Slam-class: damage = CURRENT block (the Barricade finisher —
            # owner 2026-08-01; catalog preview numbers are stale, sim block isn't)
            per_hit = (self.block if pick.fx.dmg_equals_block
                       else pick.fx.damage + self.my_str)
            if (pick.fx.requires_exhaust_pile
                    and self.n_exhausted < pick.fx.requires_exhaust_pile):
                per_hit = 0  # Pact's End-class: condition unmet, damage is a mirage
            for f in tgts:
                if f is None or f.hp <= 0 or f.dormant:
                    continue
                f.sleep = 0  # any damage wakes a Lagavulin-class sleeper early
                for _h in range(max(1, pick.fx.hits)):
                    _hit(f, per_hit, self.vm)
                    if f.thorns:
                        self.hp -= f.thorns
                if pick.fx.vulnerable:
                    if f.artifact > 0:
                        f.artifact -= 1  # charge eats the debuff (Aeonglass tape)
                    else:
                        f.vuln += pick.fx.vulnerable
                if f.hp <= 0:
                    self.hp -= f.death_damage + f.death_damage_growth * self.turn
            self._advance_wave()  # Phrog: killing the leader spawns the next wave
        if pick.shreds_hand:
            # Stoke: exhaust hand, add a random card per exhausted — average-quality
            # replacements (owner: shredding basics is almost always a value upgrade)
            n_shredded = len(self.hand)
            for _c in list(self.hand):
                self.hand.remove(_c)
                self.exhaust_event()
            for _ in range(n_shredded):
                self.hand.append(_Card("random", 1,
                                       parse_card_description("Deal 8 damage."),
                                       True, False, False, True, False, 0,
                                       text="Deal 8 damage."))
        if pick.is_power:
            pid = pick.name.upper().replace(" ", "_").replace("!", "")
            if any(k in pid for k in _FNP):
                self.fnp += pick.fx.block or 4
                self.block -= pick.fx.block  # the parse read the trigger as flat block
            if any(k in pid for k in _DARK_EMBRACE):
                self.de_draw += 1
            if any(k in pid for k in _BARRICADE):
                self.barricade = True
        elif pick.exhausts:
            self.exhaust_event()
        else:
            self.discard.append(pick)
        if self.hp <= 0:
            self.outcome = (False, 0)
        elif not self.alive_leaders():
            self._win()

    def end_of_turn(self):
        # hand curses bite, ethereal exhausts, rest discards
        for c in self.hand:
            if c.eot_hand_loss:
                self.hp -= c.eot_hand_loss
            if c.ethereal:
                self.exhaust_event()
            else:
                self.discard.append(c)
        self.hand = []
        if self.hp <= 0:
            self.outcome = (False, 0)
            return
        # damage-potion finisher (live lane 5)
        for kind in ("damage", "aoe"):
            tgt = next((f for f in self.foes
                        if f.counts and f.hp > 0 and not f.dormant), None)
            if tgt is not None and any(k == kind and a >= tgt.hp for k, a in self.belt):
                tgt.hp = 0
                self.spend(kind)
                self._advance_wave()
                if not self.alive_leaders():
                    self._win()
                    return
        # enemy turn (block/heal potions as death-preventers — live lanes 1/5);
        # sleepers don't attack
        strike = sum(f.dps + f.str_gained + f.dot
                     for f in self.targets() if f.sleep <= 0)
        if self.hp - max(0, strike - self.block) <= 0:
            self.block += self.spend("block")
        if self.hp - max(0, strike - self.block) <= 0:
            self.hp = min(self.max_hp, self.hp + self.spend("heal"))
        self.hp -= max(0, strike - self.block)
        if self.hp <= 0:
            self.outcome = (False, 0)
            return
        if self.hp < 0.35 * self.max_hp and any(k == "heal" for k, _ in self.belt):
            self.hp = min(self.max_hp, self.hp + self.spend("heal"))
        if self.block == 0 and self.rfx.get("eot_block_if_none"):
            self.block += self.rfx["eot_block_if_none"]  # Orichalcum
        for f in self.foes:
            if f.hp <= 0 or f.dormant:
                continue
            if f.sleep > 0:
                f.sleep -= 1  # sleeping: no ramp/heal ticks, just the countdown
                continue
            f.str_gained += f.ramp
            if f.heals:
                f.hp += f.heals
            if f.vuln > 0:
                f.vuln -= 1
            if f.death_timer and self.turn >= f.death_timer:
                self.outcome = (False, 0)
                return


# ---------------------------------------------------------------- turn policies

def _auto_turn(sim: _RolloutSim) -> None:
    """Whispering Earring turn 1: Vakuu plays cards left-to-right until no longer
    possible -- no prioritization, no target selection beyond the first body, and
    self-costed cards get dumped too. Deliberately dumber than the greedy."""
    for _ in range(24):
        if sim.outcome is not None:
            return
        pick = next((c for c in sim.hand
                     if not c.unplayable and c.cost <= sim.energy), None)
        if pick is None:
            return
        sim.apply_card(pick, next(iter(sim.targets()), None))


def _greedy_turn(sim: _RolloutSim) -> None:
    """The P1 heuristic: generators -> powers -> kills -> vuln uptime -> needed
    block -> best damage. Calibrated on elites; behavior unchanged by the P1.7
    refactor (same pick order, same physics)."""
    incoming = sum(f.dps + f.str_gained + f.dot for f in sim.targets())
    for _ in range(12):
        if sim.outcome is not None:
            return
        playable = sim.playable()
        if not playable:
            return
        target = sim.best_target()
        pick = None
        gens = [c for c in playable if c.fx.draw > 0 or c.fx.energy_gain > 0]
        if gens:
            pick = max(gens, key=lambda c: c.fx.draw + 2 * c.fx.energy_gain)
        elif (powers := [c for c in playable if c.is_power]):
            pick = powers[0]
        elif target is not None:
            atks = [c for c in playable
                    if c.fx.total_damage > 0 or c.fx.dmg_equals_block]

            def per_hit(c):
                return sim.block if c.fx.dmg_equals_block else c.fx.damage + sim.my_str

            kill = [c for c in atks if per_hit(c) * c.fx.hits >= target.hp]
            vulners = [c for c in atks if c.fx.vulnerable > 0]
            if kill:
                pick = min(kill, key=lambda c: c.cost)
            elif target.sleep > 0:
                # sleeping (Matriarch A/B 2026-07-30): damage wakes her early, so
                # the window is setup, not chip — bank block, let the turn end
                if (blocks := [c for c in playable if c.fx.block > 0]):
                    pick = max(blocks, key=lambda c: c.fx.block / max(1, c.cost))
            elif target.vuln <= 0 and vulners and target.hp > 25:
                # vulnerable uptime first in long fights: everything after multiplies
                pick = max(vulners, key=lambda c: c.fx.vulnerable)
            elif incoming > sim.block and (blocks := [c for c in playable
                                                      if c.fx.block > 0]):
                pick = max(blocks, key=lambda c: c.fx.block / max(1, c.cost))
            elif atks:
                pick = max(atks, key=lambda c: per_hit(c)
                           * c.fx.hits / max(1, c.cost))
        if pick is None and (blocks := [c for c in playable if c.fx.block > 0]):
            pick = max(blocks, key=lambda c: c.fx.block)
        if pick is None:
            return
        sim.apply_card(pick, sim.best_target())


def _synth_state(sim: _RolloutSim):
    """Fabricate a CombatState for the real planner from sim state. Accumulated
    Strength IS re-baked into attack texts (v2, 2026-07-30 — the v1 gap made the
    planner under-rate late-fight attacks; physics stays on the base fx, so the
    bonus applies exactly once). Caps and Slippery ride synthesized status text
    the live detectors already parse."""
    from sts2bot.client.models import parse_state
    enemies = []
    for i, f in enumerate(sim.foes):
        if f.hp <= 0 or f.dormant:  # dormant wave: not on screen yet
            continue
        status = []
        if f.vuln > 0:
            status.append({"id": "VULNERABLE_POWER", "name": "Vulnerable",
                           "amount": f.vuln, "description": "", "keywords": []})
        if f.cap is not None:
            status.append({"id": "HARDENED_SHELL_POWER", "name": "Hardened Shell",
                           "amount": f.cap, "keywords": [],
                           "description": f"Cannot lose more than {f.cap} HP each turn."})
        if f.slippery:
            status.append({"id": "SLIPPERY_POWER", "name": "Slippery", "amount": 1,
                           "keywords": [],
                           "description": "The next time this loses HP, it only loses 1 HP."})
        if f.artifact > 0:
            # the real planner already prices debuffs-into-Artifact as waste
            status.append({"id": "ARTIFACT_POWER", "name": "Artifact",
                           "amount": f.artifact, "keywords": [],
                           "description": f"Negates {f.artifact} debuffs."})
        if f.sleep > 0:
            # the real planner's sleeper handling (damage-noop unless killed) applies
            status.append({"id": "ASLEEP_POWER", "name": "Asleep", "amount": f.sleep,
                           "keywords": [], "description": "Asleep."})
        enemies.append({
            "entity_id": f"SIM_{i}", "combat_id": 1, "name": f"Sim{i}",
            "hp": f.hp, "max_hp": max(f.hp, 1), "block": f.self_block,
            "status": status,
            "intents": ([{"type": "Sleep", "label": "Sleeping", "title": "Sleep",
                          "description": ""}] if f.sleep > 0 else
                        [{"type": "Attack",
                          "label": str(f.dps + f.str_gained + f.dot),
                          "title": "Attack", "description": ""}]),
        })
    hand = [{
        "index": i, "id": c.cid or c.name.upper().replace(" ", "_"), "name": c.name,
        "type": c.ctype, "cost": str(c.cost), "star_cost": None,
        "description": (
            # Body Slam-class: refresh the stale catalog preview with CURRENT sim
            # block — the live parser reads the '(Deals N damage)' preview, so the
            # DFS bridge prices the slam correctly as block accumulates
            f"Deal damage equal to your Block. (Deals {sim.block} damage)"
            if c.fx.dmg_equals_block
            else _rebake_strength(c.text, sim.my_str) if c.is_attack
            else c.text),
        "target_type": "AnyEnemy" if c.is_attack else "None",
        "can_play": not c.unplayable, "unplayable_reason": None,
        "is_upgraded": False, "keywords": [],
    } for i, c in enumerate(sim.hand)]
    return parse_state({
        "state_type": "boss",
        "battle": {"round": sim.turn, "turn": "player", "is_play_phase": True,
                   "enemies": enemies},
        "run": {"act": 1, "floor": 17, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": sim.hp, "max_hp": sim.max_hp,
                   "block": sim.block, "energy": sim.energy, "max_energy": sim.energy,
                   "gold": 0, "hand": hand, "status": [], "relics": [],
                   "potions": [], "max_potion_slots": 0, "in_combat": True},
    })


def _dfs_turn(sim: _RolloutSim, weights, max_plans: int = 10) -> None:
    """P1.7: the REAL one-turn planner chooses each play through a synthesized
    state; effects apply through the shared sim physics. Potions stay sim-side
    (the synth belt is empty), so the planner only ever picks cards."""
    from sts2bot.client import actions as act
    from sts2bot.policy.base import Decision
    from sts2bot.policy.combat import plan_combat_turn
    for _ in range(max_plans):
        if sim.outcome is not None or not sim.playable():
            return
        try:
            decision = plan_combat_turn(_synth_state(sim), weights)
        except Exception:
            return  # synth gap: fall back to ending the turn (conservative)
        if not isinstance(decision, Decision):
            return
        a = decision.action
        if isinstance(a, act.PlayCard):
            idx = a.card_index
            if idx is None or not (0 <= idx < len(sim.hand)):
                return
            target = None
            tid = a.target or ""
            if tid.startswith("SIM_"):
                k = int(tid.split("_")[1])
                if (0 <= k < len(sim.foes) and sim.foes[k].hp > 0
                        and not sim.foes[k].dormant):
                    target = sim.foes[k]
            if target is None:
                target = sim.best_target()
            sim.apply_card(sim.hand[idx], target)
        else:
            return  # EndTurn / anything else: the turn is done


# ---------------------------------------------------------------- entry point

def rollout_fight(
    deck,
    enemies: list[FightEnemy],
    player_hp: int,
    max_hp: int,
    *,
    card_effects: dict | None = None,
    potions=None,
    relics=None,
    n: int = 20,
    rng_seed: int | None = None,
    max_turns: int = 30,
    policy: str = "greedy",
    combat_weights=None,  # required for policy="dfs"
    timing_out: dict | None = None,  # filled with {"ms": ...} when provided
    target_order: str = "sweep",  # "sweep" (low-HP first) | "focus" (big body first)
) -> RolloutResult:
    cards = _build_cards(deck, card_effects)
    if not cards or not enemies:
        return RolloutResult(0.0, 0.0, 0.0, float(max_turns), n=0)
    if rng_seed is None:
        # content-derived: identical (deck, enemies) -> identical estimate (replay
        # determinism; crc32, not hash() — that one is randomized per process);
        # our own RNG, never the game's (C3)
        key = ",".join(sorted(c.name for c in cards)) + "|" + ",".join(
            f"{e.hp}:{e.dps}:{e.str_ramp}" for e in enemies)
        rng_seed = zlib.crc32(key.encode()) & 0x7FFFFFFF

    pots = _classify_potions(potions)
    rfx: dict[str, int] = {}
    for r in relics or []:
        rid = (getattr(r, "id", "") or getattr(r, "name", "") or "").upper().replace(" ", "_")
        for key2, (kind, amt) in _RELIC_FX.items():
            if key2 in rid:
                rfx[kind] = rfx.get(kind, 0) + amt
        if "WHISPERING_EARRING" in rid:
            rfx["auto_turn1"] = 1  # Vakuu plays turn 1 left-to-right

    t0 = _time.perf_counter()
    end_hps: list[int] = []
    turns_out: list[int] = []
    hp_left: list[int] = []
    wins = 0
    for i in range(n):
        rng = random.Random(rng_seed + i * 7919)
        sim = _RolloutSim(cards, enemies, player_hp, max_hp, rng, pots, rfx)
        sim.prefer_big = target_order == "focus"
        while sim.outcome is None and sim.turn < max_turns:
            sim.start_turn()
            if sim.turn == 1 and rfx.get("auto_turn1"):
                _auto_turn(sim)  # Whispering Earring: turn 1 is out of our hands
            elif policy == "dfs":
                _dfs_turn(sim, combat_weights)
            else:
                _greedy_turn(sim)
            if sim.outcome is None:
                sim.end_of_turn()
        won, end_hp = sim.outcome if sim.outcome is not None else (False, 0)
        wins += 1 if won else 0
        end_hps.append(end_hp if won else 0)
        turns_out.append(sim.turn)
        # loss gradient for draft pricing: how much kill-HP still stood at the end
        hp_left.append(0 if won else sum(f.hp for f in sim.foes
                                         if f.counts and f.hp > 0))
    if timing_out is not None:
        timing_out["ms"] = (_time.perf_counter() - t0) * 1000.0
    end_hps.sort()
    return RolloutResult(
        win_rate=wins / n,
        exp_end_hp=sum(end_hps) / n,
        p25_end_hp=float(end_hps[n // 4]),
        mean_turns=sum(turns_out) / n,
        n=n,
        exp_enemy_hp_left=sum(hp_left) / n,
    )
