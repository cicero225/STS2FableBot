"""Prediction-fuzzing router (owner experiment design 2026-08-06, PLAN §7).

Off-policy model validation: in combat, play RANDOM legal cards while logging
the text-parse prediction for every play. The passive predict_audit only covers
states the policy chooses to visit; random play reaches the orderings and
combinations where conditional riders and sequencing bugs hide. Analysis pairs
each play's logged prediction against the next poll's actual state delta
(scripts/fuzz_audit.py).

Safety rail (the owner is the savescum operator -- attended sessions only):
before every fuzzed action, if OUR hp is under the floor or the fight is nearly
won, PAUSE with a MANUAL wait and never act. The owner savescums (force-close +
Continue restarts the fight); the restart is detected by hp/round recovery, the
fight is marked fuzz-done, and the run continues on the NORMAL policy until the
next fight arms the fuzzer again.

Determinism: the RNG seeds from (floor, round) so a savescummed replay of the
same fight fuzzes the same order -- controlled comparisons, not anecdotes.
"""

from __future__ import annotations

import random

from sts2bot.client import actions as act
from sts2bot.client.models import CombatState, GameState
from sts2bot.policy.base import Decision, LoopContext, Wait
from sts2bot.policy.standard import StandardRouter
from sts2bot.policy.textparse import parse_card_description

# rail thresholds (deliberately conservative: the whole point is not to lose the run)
HP_FLOOR = 25
ENEMY_NEARLY_DEAD_FRAC = 0.18


class FuzzRouter(StandardRouter):
    """StandardRouter everywhere, random-legal-play in combats not yet fuzz-done."""

    def decide(self, state: GameState, ctx: LoopContext) -> Decision | Wait:
        if isinstance(state, CombatState) and state.battle is not None:
            fuzzed = self._fuzz_combat(state, ctx)
            if fuzzed is not None:
                return fuzzed
        return super().decide(state, ctx)

    def _fuzz_combat(self, state: CombatState, ctx: LoopContext) -> Decision | Wait | None:
        player, battle = state.player, state.battle
        if player is None or not player.in_combat:
            return None
        floor = state.run.floor if state.run else -1
        done: set = ctx.screen_mem.setdefault("fuzz_done_floors", set())
        if floor in done:
            return None  # rail tripped here before: normal policy finishes the fight
        if battle.turn != "player" or battle.is_play_phase is False:
            return None  # waits/enemy turns run through the normal router (settle guard etc.)
        if battle.actions_disabled:
            return None

        # ---- safety rail: pause for the owner BEFORE any risky action
        nearly_won = all(
            (e.hp or 0) <= max(6, int((e.max_hp or 1) * ENEMY_NEARLY_DEAD_FRAC))
            for e in battle.enemies
            if (e.hp or 0) > 0
        )
        if player.hp <= HP_FLOOR or nearly_won:
            pause = ctx.screen_mem.get("fuzz_paused_at")
            if pause == (floor, battle.round):
                pass  # already announced this pause point; keep waiting
            else:
                ctx.screen_mem["fuzz_paused_at"] = (floor, battle.round)
            # a savescum restarts the fight: round drops / hp recovers -> the NEXT
            # poll sees a different (floor, round) with a healthy state, we mark the
            # floor done and the normal policy takes over
            if player.hp > HP_FLOOR and not nearly_won:
                done.add(floor)
                return None
            return Wait(
                reason=f"MANUAL: FUZZ-PAUSE at f{floor} r{battle.round} "
                f"(hp {player.hp}, nearly_won={nearly_won}) — savescum to keep the "
                "run; the fight resumes on normal policy after restart"
            )
        if ctx.screen_mem.get("fuzz_paused_at", (None, None))[0] == floor:
            # we paused earlier this fight and the state has recovered: the owner
            # savescummed. Hand the fight to the normal policy.
            done.add(floor)
            ctx.screen_mem.pop("fuzz_paused_at", None)
            return None

        # ---- random legal play, prediction logged in the rationale
        playable = [c for c in (player.hand or []) if c.can_play]
        rng = random.Random((floor << 8) ^ (battle.round or 0) ^ len(playable))
        affordable = [c for c in playable
                      if str(c.cost or "0").upper() == "X"
                      or (str(c.cost or "0").lstrip("-").isdigit()
                          and int(c.cost) <= (player.energy or 0))]
        if not affordable:
            return Decision(action=act.EndTurn(),
                            rationale="FUZZ: nothing affordable; end turn")
        card = rng.choice(affordable)
        fx = parse_card_description(card.description)
        target = None
        if (card.target_type or "").lower() == "anyenemy":
            alive = [e for e in battle.enemies if (e.hp or 0) > 0]
            if not alive:
                return Decision(action=act.EndTurn(), rationale="FUZZ: no targets; end turn")
            target = rng.choice(alive).entity_id
        pred = (f"dmg={fx.damage}x{max(1, fx.hits)} aoe={int(fx.aoe)} blk={fx.block} "
                f"draw={fx.draw} egain={fx.energy_gain} selfhp={fx.self_hp_cost} "
                f"vuln={fx.vulnerable} weak={fx.weak}")
        return Decision(
            action=act.PlayCard(card_index=card.index, target=target),
            rationale=f"FUZZ: {card.name} -> {target or 'self'} | PRED {pred}",
        )
