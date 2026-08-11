"""Prediction-fuzzing router (owner experiment design 2026-08-06, PLAN §7).

Off-policy model validation: in combat, play RANDOM legal cards while logging
the text-parse prediction for every play. The passive predict_audit only covers
states the policy chooses to visit; random play reaches the orderings and
combinations where conditional riders and sequencing bugs hide. Analysis pairs
each play's logged prediction against the next poll's actual state delta
(scripts/fuzz_audit.py).

Safety rail (AUTOMATED 2026-08-10, owner design): before every fuzzed action, if
OUR hp is under the floor or the fight is nearly won, send the fork mod's
save_and_quit (run persists; Continue restores the fight to its start -- the
owner's manual savescum, mechanized). The orchestrator's menu handler Continues,
the restart is detected by hp/enemy recovery, the fight is marked fuzz-done, and
the run proceeds on the NORMAL policy until the next fight arms the fuzzer again.
Fuzz sessions are therefore self-sufficient; the owner may watch for fun.

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

        # ---- safety rail: auto-savescum BEFORE any risky action (owner design
        # 2026-08-10: save_and_quit -> menu -> Continue restores the fight to its
        # start, exactly the manual force-close savescum, automated). Send it
        # ONCE per pause point, then hold while the menu transition runs; after
        # the restart the healthy state routes through the recovery branch below
        # and the normal policy finishes the (fuzz-done) fight.
        nearly_won = all(
            (e.hp or 0) <= max(6, int((e.max_hp or 1) * ENEMY_NEARLY_DEAD_FRAC))
            for e in battle.enemies
            if (e.hp or 0) > 0
        )
        if player.hp <= HP_FLOOR or nearly_won:
            # Nothing to rewind, nothing to risk (live 2026-08-10, run
            # 20260810-201707: a bleeding run entered f37/f38 at 5-6 hp, the
            # rail tripped at r1 with ZERO fuzzed plays made, and the pointless
            # savescum's Continue hit a resume-load wedge that cost the run).
            # If this fight hasn't been fuzzed yet, just hand it to the normal
            # policy -- a savescum only pays when there are risky plays to undo.
            if ctx.screen_mem.get("fuzz_played_fight") != floor:
                done.add(floor)
                return None
            pause = ctx.screen_mem.get("fuzz_paused_at")
            if pause == (floor, battle.round):
                return Wait(
                    reason=f"FUZZ-RAIL: save_and_quit sent at f{floor} "
                    f"r{battle.round}; waiting for the menu transition"
                )
            ctx.screen_mem["fuzz_paused_at"] = (floor, battle.round)
            return Decision(
                action=act.SaveAndQuit(),
                rationale=f"FUZZ-RAIL: auto-savescum at f{floor} r{battle.round} "
                f"(hp {player.hp}, nearly_won={nearly_won}) — Continue restores "
                "the fight; normal policy finishes it",
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
        ctx.screen_mem["fuzz_played_fight"] = floor  # this fight HAS fuzzed plays
        fx = parse_card_description(card.description)
        target = None
        if (card.target_type or "").lower() == "anyenemy":
            alive = [e for e in battle.enemies if (e.hp or 0) > 0]
            if not alive:
                return Decision(action=act.EndTurn(), rationale="FUZZ: no targets; end turn")
            target = rng.choice(alive).entity_id
        pred = (f"dmg={fx.damage}x{max(1, fx.hits)} aoe={int(fx.aoe)} blk={fx.block} "
                f"draw={fx.draw} egain={fx.energy_gain} selfhp={fx.self_hp_cost} "
                f"vuln={fx.vulnerable} weak={fx.weak} plat={fx.plating} "
                f"cond={int(fx.conditional)}")
        return Decision(
            action=act.PlayCard(card_index=card.index, target=target),
            rationale=f"FUZZ: {card.name} -> {target or 'self'} | PRED {pred}",
        )
