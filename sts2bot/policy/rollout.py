"""Monte-Carlo fight rollouts — the forward model's estimator core (PLAN §5.2).

Replaces the closed-form HP race (`estimate_fight`) for strategic consumers: instead
of summarizing the deck as static output, PLAY the fight forward — shuffle a
simulated copy of the deck (our own RNG, never the game's), draw hands, pick plays
with a fast greedy policy, apply enemy pressure, repeat to fight end. N rollouts
give a distribution: win rate, expected end HP, tail. Draw variance, dead curses,
energy economy, exhaust thinning, and strength accumulation price themselves
because the simulation plays them — the engine-blindness the calibration exposed
(0% predicted act-1 boss wins vs 55% actual) is structural to the summary, not to
simulation.

Design decisions (owner-reviewed 2026-07-25): greedy turn policy only (full-DFS
fidelity revisited if boss deaths persist); enemy model = bestiary dps/mechanics
abstraction (wiki-exact pattern pass is the upgrade path); determinism via a seed
derived from the (deck, enemies) content so identical inputs give identical
estimates and replay determinism survives.

Pure functions; no I/O.
"""
from __future__ import annotations

import random
import re
import zlib
from dataclasses import dataclass

from sts2bot.policy.capability import FightEnemy
from sts2bot.policy.textparse import CardEffects, parse_card_description

_UNPLAYABLE = re.compile(r"\bunplayable\b", re.IGNORECASE)
_ETHEREAL = re.compile(r"\bethereal\b", re.IGNORECASE)
_EXHAUST_SELF = re.compile(r"\bexhaust\.\s*$|\bexhaust\b(?!\s+(a|all|your|the|up))",
                           re.IGNORECASE)
_EOT_HAND_LOSS = re.compile(r"lose (\d+) hp", re.IGNORECASE)
_ADD_RANDOM_PER_EXHAUST = re.compile(r"add (\d+) random card", re.IGNORECASE)


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


@dataclass(frozen=True)
class RolloutResult:
    win_rate: float
    exp_end_hp: float  # mean end HP over all rollouts (losses count 0)
    p25_end_hp: float  # pessimistic tail — gate material
    mean_turns: float
    n: int = 0

    @property
    def win(self) -> bool:
        return self.win_rate >= 0.5


# persistent powers the greedy loop honors beyond their one-shot fx
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
        ))
    return out


def _hit(foe: _Foe, amount: int) -> int:
    """One damage instance into a foe, honoring Slippery / per-turn caps / self-block.
    Returns HP actually removed."""
    if foe.slippery and not foe.slipped_this_turn:
        foe.slipped_this_turn = True
        amount = min(amount, 1)
    amount = max(0, amount - foe.self_block)
    if foe.vuln > 0:
        amount = int(amount * 1.5)
    if foe.cap is not None:
        amount = min(amount, max(0, foe.cap - foe.lost_this_turn))
    amount = min(amount, foe.hp)
    foe.hp -= amount
    foe.lost_this_turn += amount
    return amount


def rollout_fight(
    deck,
    enemies: list[FightEnemy],
    player_hp: int,
    max_hp: int,
    *,
    card_effects: dict | None = None,
    n: int = 20,
    rng_seed: int | None = None,
    max_turns: int = 30,
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

    end_hps: list[int] = []
    turns_out: list[int] = []
    wins = 0
    for i in range(n):
        rng = random.Random(rng_seed + i * 7919)
        won, end_hp, turns = _one_rollout(cards, enemies, player_hp, max_hp, rng,
                                          max_turns)
        wins += 1 if won else 0
        end_hps.append(end_hp if won else 0)
        turns_out.append(turns)
    end_hps.sort()
    return RolloutResult(
        win_rate=wins / n,
        exp_end_hp=sum(end_hps) / n,
        p25_end_hp=float(end_hps[n // 4]),
        mean_turns=sum(turns_out) / n,
        n=n,
    )


def _one_rollout(cards, enemies, player_hp, max_hp, rng, max_turns):
    foes = [_Foe(hp=e.hp, dps=e.dps, ramp=e.str_ramp, counts=e.counts_toward_kill,
                 cap=e.dmg_cap_per_turn, slippery=e.slippery, self_block=e.self_block,
                 thorns=e.thorns, death_damage=e.death_damage,
                 death_damage_growth=e.death_damage_growth, heals=e.heals_per_turn,
                 dot=e.player_dot_avg, death_timer=e.death_timer)
            for e in enemies]
    draw = cards[:]
    rng.shuffle(draw)
    discard: list[_Card] = []
    hp = int(player_hp)
    my_str = 0
    fnp = 0  # block per exhaust event
    de_draw = 0  # draw per exhaust event
    barricade = False
    block = 0

    def alive_leaders():
        return [f for f in foes if f.counts and f.hp > 0]

    def exhaust_event(hand):
        nonlocal block
        block += fnp
        for _ in range(de_draw):
            if draw or discard:
                _draw_one(hand)

    def _draw_one(hand):
        nonlocal draw, discard
        if not draw:
            draw, discard = discard, []
            rng.shuffle(draw)
        if draw:
            hand.append(draw.pop())

    for turn in range(1, max_turns + 1):
        if not barricade:
            block = 0
        for f in foes:
            f.lost_this_turn = 0
            f.slipped_this_turn = False
        hand: list[_Card] = []
        for _ in range(5):
            _draw_one(hand)
        energy = 3
        incoming = sum(f.dps + f.str_gained + f.dot for f in foes if f.hp > 0)

        # greedy loop: generators -> powers -> kills -> needed block -> best damage
        for _ in range(12):
            playable = [c for c in hand if not c.unplayable and c.cost <= energy]
            if not playable:
                break
            target = min(alive_leaders(), key=lambda f: f.hp, default=None)
            pick = None
            gens = [c for c in playable if c.fx.draw > 0 or c.fx.energy_gain > 0]
            if gens:
                pick = max(gens, key=lambda c: c.fx.draw + 2 * c.fx.energy_gain)
            elif (powers := [c for c in playable if c.is_power]):
                pick = powers[0]
            elif target is not None:
                atks = [c for c in playable if c.fx.total_damage > 0]
                kill = [c for c in atks
                        if (c.fx.damage + my_str) * c.fx.hits >= target.hp]
                if kill:
                    pick = min(kill, key=lambda c: c.cost)
                elif incoming > block and (blocks := [c for c in playable
                                                      if c.fx.block > 0]):
                    pick = max(blocks, key=lambda c: c.fx.block / max(1, c.cost))
                elif atks:
                    pick = max(atks, key=lambda c: (c.fx.damage + my_str)
                               * c.fx.hits / max(1, c.cost))
            if pick is None and (blocks := [c for c in playable if c.fx.block > 0]):
                pick = max(blocks, key=lambda c: c.fx.block)
            if pick is None:
                break
            hand.remove(pick)
            energy -= pick.cost
            energy += pick.fx.energy_gain
            hp = max(0, hp - pick.fx.self_hp_cost)
            hp = min(max_hp, hp + pick.fx.heal)
            block += pick.fx.block
            my_str += pick.fx.strength
            for _ in range(pick.fx.draw):
                _draw_one(hand)
            if pick.fx.total_damage > 0:
                tgts = ([f for f in foes if f.hp > 0] if pick.fx.aoe
                        else ([target] if target else []))
                for f in tgts:
                    if f is None or f.hp <= 0:
                        continue
                    for _h in range(max(1, pick.fx.hits)):
                        _hit(f, pick.fx.damage + my_str)
                        if f.thorns:
                            hp -= f.thorns
                    if pick.fx.vulnerable:
                        f.vuln += pick.fx.vulnerable
                    if f.hp <= 0:
                        hp -= f.death_damage + f.death_damage_growth * turn
            if pick.shreds_hand:
                # Stoke: exhaust hand, add a random card per exhausted — model the
                # adds as average-quality replacements (owner: shredding basics is
                # almost always a value upgrade; this also silences hand curses)
                n_shredded = len(hand)
                for _c in list(hand):
                    hand.remove(_c)
                    exhaust_event(hand)
                for _ in range(n_shredded):
                    hand.append(_Card("random", 1,
                                      parse_card_description("Deal 8 damage."),
                                      True, False, False, True, False, 0))
            if pick.is_power:
                pid = pick.name.upper().replace(" ", "_").replace("!", "")
                if any(k in pid for k in _FNP):
                    fnp += pick.fx.block or 4
                    block -= pick.fx.block  # the parse read the trigger as flat block
                if any(k in pid for k in _DARK_EMBRACE):
                    de_draw += 1
                if any(k in pid for k in _BARRICADE):
                    barricade = True
            elif pick.exhausts:
                exhaust_event(hand)
            else:
                discard.append(pick)
            if hp <= 0:
                return False, 0, turn
            if not alive_leaders():
                return True, min(max_hp, hp), turn

        # end of turn: hand curses bite, ethereal exhausts, rest discards
        for c in hand:
            if c.eot_hand_loss:
                hp -= c.eot_hand_loss
            if c.ethereal:
                exhaust_event(hand)
            else:
                discard.append(c)
        if hp <= 0:
            return False, 0, turn

        # enemy turn
        strike = sum(f.dps + f.str_gained + f.dot for f in foes if f.hp > 0)
        hp -= max(0, strike - block)
        if hp <= 0:
            return False, 0, turn
        for f in foes:
            if f.hp <= 0:
                continue
            f.str_gained += f.ramp
            if f.heals:
                f.hp += f.heals
            if f.vuln > 0:
                f.vuln -= 1
            if f.death_timer and turn >= f.death_timer:
                return False, 0, turn

    return False, 0, max_turns  # timed out: treat as a loss (stalemates lose races)
