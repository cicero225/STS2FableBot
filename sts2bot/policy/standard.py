"""StandardRouter: the first real policy set (P1).

Smart handling for combat (one-turn planner), map routing, events, card rewards,
rest sites, shops, reward-screen potion management, and in-combat potions.
Everything else (menus/navigation, overlays, minigames) delegates to the
TrivialRouter, which is already battle-tested plumbing.
"""

from __future__ import annotations

import re
from typing import ClassVar

from sts2bot.client import actions as act
from sts2bot.client.models import (
    CardRewardState,
    CardSelectState,
    CombatState,
    EventState,
    GameState,
    HandSelectState,
    MapState,
    Potion,
    RestSiteState,
    RewardsState,
    ShopState,
)
from sts2bot.kb.combat_stats import CombatStats
from sts2bot.kb.config import PolicyConfig, load_policy_config
from sts2bot.kb.event_stats import EventStats
from sts2bot.kb.priors import CardPriors
from sts2bot.kb.shop_stats import ShopStats
from sts2bot.policy.base import Decision, LoopContext, Wait
from sts2bot.policy.combat import plan_combat_turn
from sts2bot.policy.textparse import parse_card_description, parse_hp_cost, parse_intent_damage
from sts2bot.policy.trivial import TrivialRouter

# Event-option value cues the card-text parser doesn't cover (gains the bot was blind to).
_EV_MAXHP_GAIN = re.compile(r"Gain (\d+) Max(?:imum)? HP", re.IGNORECASE)
_EV_GOLD_GAIN = re.compile(r"Gain (\d+) Gold", re.IGNORECASE)
_EV_GOLD_LOSS = re.compile(r"Lose (\d+) Gold", re.IGNORECASE)


class StandardRouter:
    def __init__(
        self,
        config: PolicyConfig | None = None,
        priors: CardPriors | None = None,
        combat_stats: CombatStats | None = None,
        shop_stats: ShopStats | None = None,
        event_stats: EventStats | None = None,
    ):
        self.config = config or load_policy_config()
        self.priors = priors if priors is not None else CardPriors.load()
        self.combat_stats = combat_stats if combat_stats is not None else CombatStats.load()
        self.shop_stats = shop_stats if shop_stats is not None else ShopStats.load()
        self.event_stats = event_stats if event_stats is not None else EventStats.load()
        self._fallback = TrivialRouter()

    def decide(self, state: GameState, ctx: LoopContext) -> Decision | Wait:
        handler = getattr(self, f"_{state.state_type}", None)
        if handler is not None:
            return handler(state, ctx)
        return self._fallback.decide(state, ctx)

    # ------------------------------------------------------------------ combat

    def _combat(self, state: CombatState, ctx: LoopContext) -> Decision | Wait:
        # Transient 'BlockedByHook' hands report every card unplayable while the
        # engine resolves a hook; trusting that ends the turn early (run 33: a
        # planned triple-Defend became one, 14 HP -> 3). Re-poll, bounded.
        if self._hand_blocked_by_hook(state):
            n = ctx.screen_mem.get("hook_waits", 0)
            if n < self.config.combat.hook_retry_limit:
                ctx.screen_mem["hook_waits"] = n + 1
                return Wait(reason=f"hand blocked by transient hook (retry {n + 1}); re-polling")
            # cap hit: fall through and let the planner act on what it sees
        else:
            ctx.screen_mem.pop("hook_waits", None)

        plan = plan_combat_turn(state, self.config.combat)
        # If the planned line clears the board this turn, survival measures are a
        # waste (owner watched a hail-mary fire alongside lethal-in-hand vs the
        # Act 1 boss). Sim-lethal can be optimistic, but the wasted-potion case
        # is far more common than a misread lethal.
        if isinstance(plan, Decision) and plan.scores and plan.scores.get("lethal"):
            return plan
        survival = self._survival_card(state)
        if survival is not None:
            return survival
        potion_play = self._combat_potion(state, ctx, plan)
        if potion_play is not None:
            return potion_play
        desperation = self._desperation_draw(state, plan)
        if desperation is not None:
            return desperation
        return plan

    def _desperation_draw(self, state: CombatState, plan: Decision | Wait) -> Decision | None:
        """Owner case: lethal hit the bot's face with Offering in hand. If this
        turn's incoming kills us and the plan doesn't save us, a survivable draw
        card is worth trying — the draw might find blocks or answers."""
        player = state.player
        if player is None or not player.in_combat or state.battle is None:
            return None
        if state.battle.turn != "player" or state.battle.is_play_phase is False:
            return None
        if isinstance(plan, Decision) and plan.scores and plan.scores.get("lethal"):
            return None
        incoming = sum(
            parse_intent_damage(i.label)
            for e in state.battle.enemies
            if e.hp > 0
            for i in e.intents
            if i.type.lower() == "attack"
        )
        proj_loss = incoming - player.block
        if isinstance(plan, Decision) and plan.scores and "hp_loss" in plan.scores:
            proj_loss = plan.scores["hp_loss"]
        if proj_loss < player.hp:
            return None  # the planned line already survives this turn
        for card_ in player.hand or []:
            if not card_.can_play:
                continue
            fx = parse_card_description(card_.description)
            if fx.draw > 0 and fx.self_hp_cost < player.hp:
                target = self._target_for(card_, state)
                return Decision(
                    action=act.PlayCard(card_index=card_.index, target=target),
                    rationale=f"desperation draw: {card_.name} (incoming {incoming} vs "
                    f"{player.hp} HP — dig for answers)",
                )
        return None

    @staticmethod
    def _target_for(card_, state: CombatState) -> str | None:
        """Highest-HP living enemy for cards that need a target (Pommel Strike is
        an attack that draws — desperation once played it untargeted, 8 errors)."""
        if (card_.target_type or "").lower() != "anyenemy" or state.battle is None:
            return None
        alive = [e for e in state.battle.enemies if e.hp > 0]
        if not alive:
            return None
        return max(alive, key=lambda e: e.hp).entity_id

    @staticmethod
    def _hand_blocked_by_hook(state: CombatState) -> bool:
        """True when it's our play phase but every card is unplayable solely because
        the engine is mid-hook-resolution ('BlockedByHook' — a transient). Returns
        False the moment any card is playable, so it never delays a real end-of-turn."""
        player, battle = state.player, state.battle
        if player is None or battle is None or not player.in_combat:
            return False
        if battle.turn != "player" or battle.is_play_phase is False:
            return False
        hand = player.hand or []
        if not hand or any(c.can_play for c in hand):
            return False
        return any((c.unplayable_reason or "") == "BlockedByHook" for c in hand)

    def _survival_card(self, state: CombatState) -> Decision | None:
        """Death-countdown mechanics (The Insatiable's Sandpit): an enemy status
        whose text promises death, mitigated by playing an injected card whose
        text names that status. Generic over the text pattern, not the boss."""
        if state.battle is None or state.player is None:
            return None
        if state.battle.turn != "player" or state.battle.is_play_phase is False:
            return None
        if state.battle.actions_disabled:
            return None
        threshold = self.config.combat.survival_status_threshold
        hand = state.player.hand or []
        for enemy_ in state.battle.enemies:
            if enemy_.hp <= 0:
                continue
            for power in enemy_.status:
                desc = (power.description or "").lower()
                if "you" not in desc or not ("die" in desc or "eaten" in desc):
                    continue
                amount = power.amount if power.amount is not None else 0
                if amount > threshold:
                    continue
                name = power.name.lower()
                for card_ in hand:
                    if card_.can_play and name in (card_.description or "").lower():
                        return Decision(
                            action=act.PlayCard(
                                card_index=card_.index,
                                target=self._target_for(card_, state),
                            ),
                            rationale=f"survival: play {card_.name} ({power.name} at "
                            f"{amount} — '{power.description}')",
                        )
        return None

    _monster = _combat
    _elite = _combat
    _boss = _combat

    def _combat_potion(
        self, state: CombatState, ctx: LoopContext, plan: Decision | Wait | None = None
    ) -> Decision | None:
        """Drink a useful potion when the fight is dangerous (elite/boss) or HP is dire."""
        w = self.config.potions
        player = state.player
        if player is None or not player.in_combat or state.battle is None:
            return None
        if state.battle.turn != "player" or state.battle.is_play_phase is False:
            return None
        if state.battle.actions_disabled:
            return None
        # A used potion stays visibly in the belt while its effect is queued, so
        # re-drinking the SAME slot rails on "already queued" (run 28, The Kin). Track
        # used slots per round: regular use is one survival potion per round, but a
        # hail-mary may drink several DIFFERENT potions (owner: it only used one when
        # facing death on a boss with two in the belt).
        round_ = state.battle.round if state.battle.round is not None else -1
        used = ctx.screen_mem.get("potions_used")
        if not isinstance(used, dict) or used.get("round") != round_:
            used = {"round": round_, "slots": []}
            ctx.screen_mem["potions_used"] = used
        used_slots: list[int] = used["slots"]

        def drink(potion: Potion, target: str | None, why: str) -> Decision:
            if potion.slot not in used_slots:
                used_slots.append(potion.slot)
            return Decision(action=act.UsePotion(slot=potion.slot, target=target), rationale=why)

        def biggest_threat() -> str | None:
            alive = [e for e in state.battle.enemies if e.hp > 0]
            return max(alive, key=lambda e: e.hp).entity_id if alive else None

        hp_pct = player.hp / max(1, player.max_hp)
        dangerous = state.state_type in ("elite", "boss") and w.drink_in_elite_or_boss
        incoming = sum(
            parse_intent_damage(i.label)
            for e in state.battle.enemies
            if e.hp > 0
            for i in e.intents
            if i.type.lower() == "attack"
        )
        # projected HP loss after the planned line plays its cards (block/kills) — not
        # raw incoming, so we don't panic-drink a turn our own cards survive.
        proj_loss = incoming - player.block
        if isinstance(plan, Decision) and plan.scores and "hp_loss" in plan.scores:
            proj_loss = plan.scores["hp_loss"]
        plan_ends_turn = isinstance(plan, Decision) and isinstance(plan.action, act.EndTurn)
        available = [
            p
            for p in player.potions
            if p.can_use_in_combat is not False and p.slot not in used_slots
        ]
        if not available:
            return None
        cat = {p.slot: self._potion_category(p) for p in available}

        def first(*want: str) -> Potion | None:
            return next((p for p in available if cat[p.slot] in want), None)

        # 1. Hail-mary (run 10: died holding buff potions): dying even after our cards
        #    block — throw a potion, preferring one that can actually save us.
        if w.hail_mary and hp_pct < w.drink_when_hp_pct_below and proj_loss >= player.hp:
            potion = first("block", "heal", "aoe_damage", "damage") or available[0]
            tgt = biggest_threat() if cat[potion.slot] in ("damage", "aoe_damage") else None
            return drink(
                potion, tgt,
                f"hail mary: drink {potion.name} (proj loss {proj_loss:.0f} >= {player.hp} HP)",
            )

        # 2. Fruit Juice (+max HP): pure upside, drink on sight.
        if juice := first("fruit_juice"):
            return drink(juice, None, f"drink {juice.name} (+max HP, free value)")

        # 3. Heal / Blood Potion when hurt.
        if hp_pct < w.heal_below_pct and (healp := first("heal")):
            return drink(healp, None, f"drink {healp.name} to heal at {hp_pct:.0%} HP")

        # 4. Proactive at an elite/boss start: deploy long-term buffs/debuffs early (the
        #    bot struggles with these fights, so bank the value rather than hoard it).
        if dangerous and round_ <= 1 and (buff := first("buff", "debuff")):
            tgt = biggest_threat() if cat[buff.slot] == "debuff" else None
            return drink(buff, tgt, f"drink {buff.name} (deploy at {state.state_type} start)")

        # 4b. Value/tempo potions (energy / draw): spend them early in a big fight so the extra
        #     energy + cards convert to more block and damage. Owner B04BGZEDRN: the bot hoarded
        #     Cure All (gain energy, draw 2) through the 126-HP Ovicopter and threw it away in a
        #     hail-mary at the next floor — the human spent it to power through and exited +30 HP.
        if vp := first("value"):
            enemy_hp = sum(e.hp for e in state.battle.enemies if e.hp > 0)
            if enemy_hp >= w.value_drink_enemy_hp_min and round_ <= w.value_drink_by_round:
                return drink(
                    vp, None, f"drink {vp.name} (energy/draw for a {enemy_hp}-HP fight)"
                )

        # 5. Reactive, once the planned line has spent its cards (end of turn):
        if plan_ends_turn:
            if proj_loss >= w.block_reactive_min and (blockp := first("block")):
                return drink(
                    blockp, None, f"drink {blockp.name} end-of-turn (unblocked {proj_loss:.0f})"
                )
            dmgp = first("damage", "aoe_damage")
            if dmgp:
                tgt = self._finisher_potion_target(dmgp, state, cat[dmgp.slot], w)
                if tgt is not False:
                    return drink(dmgp, tgt, f"drink {dmgp.name} (secure a kill)")
        return None

    @staticmethod
    def _potion_category(potion: Potion) -> str:
        """Bucket a potion for the owner's taxonomy (id/name first, then parsed text)."""
        nid = f"{potion.id or ''} {potion.name or ''}".upper()
        if "FRUIT" in nid:  # Fruit Juice: +max HP, pure upside
            return "fruit_juice"
        if "FOUL" in nid or "GLOWWATER" in nid:  # self-damage / hand-loss downside
            return "downside"
        if "BLOOD" in nid:  # Blood Potion: % heal (markup the text parser can't read)
            return "heal"
        fx = parse_card_description(potion.description)
        if fx.heal > 0:
            return "heal"
        if fx.block > 0:
            return "block"
        if fx.total_damage > 0:
            return "aoe_damage" if fx.aoe else "damage"
        if fx.vulnerable > 0 or fx.weak > 0 or any(
            k in nid for k in ("VULNER", "WEAK", "BINDING", "SHACKL")
        ):
            return "debuff"
        if fx.strength > 0 or any(
            k in nid for k in ("STRENGTH", "DEXTER", "FOCUS", "POWER", "BLESSING", "FYSH", "FORGE")
        ):
            return "buff"
        if fx.draw > 0 or fx.energy_gain > 0 or "ENERGY" in nid:  # tempo: more energy / cards
            return "value"
        return "other"

    @staticmethod
    def _finisher_potion_target(potion: Potion, state: CombatState, cat: str, w):
        """End-of-turn damage potion: returns the entity_id to hit, None for AoE/self, or
        False when not worth it. Worth it when it clears the board (lethal) or kills an
        attacker doing >= prevents_min (owner: 'kills an enemy AND prevents >10 damage')."""
        dmg = parse_card_description(potion.description).total_damage
        if dmg <= 0:
            return False
        alive = [e for e in state.battle.enemies if e.hp > 0]
        kills = [e for e in alive if dmg >= e.hp + e.block]
        if not kills:
            return False

        def threat(e) -> int:
            return sum(
                parse_intent_damage(i.label) for i in e.intents if i.type.lower() == "attack"
            )

        if cat == "aoe_damage":
            prevented = sum(threat(e) for e in kills)
            worth = len(kills) == len(alive) or prevented >= w.damage_potion_prevents_min
            return None if worth else False
        if len(alive) == 1:
            worth = kills  # killing the last enemy on the board ends the fight
        else:
            worth = [e for e in kills if threat(e) >= w.damage_potion_prevents_min]
        if not worth:
            return False
        best = max(worth, key=threat)
        no_target = (potion.target_type or "").lower() in ("none", "self")
        return None if no_target else best.entity_id

    # ------------------------------------------------------------------ map

    def _map(self, state: MapState, ctx: LoopContext) -> Decision | Wait:
        w = self.config.map
        opts = state.map.next_options
        if not opts:
            return Wait(reason="map with no next options")
        player = state.player
        hp_missing_pct = 0.0
        gold = 0
        if player is not None:
            hp_missing_pct = 100.0 * (1.0 - player.hp / max(1, player.max_hp))
            gold = player.gold

        def type_score(node_type: str | None) -> float:
            t = (node_type or "unknown").lower()
            base = {
                "monster": w.score_monster,
                "unknown": w.score_unknown,
                "event": w.score_event,
                "restsite": w.score_rest_site,
                "rest_site": w.score_rest_site,
                "shop": w.score_shop,
                "treasure": w.score_treasure,
                "elite": w.score_elite,
                "boss": w.score_boss,
                "start": 0.0,
            }.get(t, w.score_unknown)
            if t in ("restsite", "rest_site"):
                base += w.rest_bonus_per_missing_hp_pct * hp_missing_pct
            if t == "shop":
                base += w.shop_bonus_per_100_gold * (gold / 100.0)
            return base

        # Act-level path value: DP over the full map DAG so options are judged by
        # the best complete route to the boss, not just their own node type
        # (1-ply lookahead committed us to forced-elite lanes floors in advance).
        node_by_pos = {(n.col, n.row): n for n in state.map.nodes}
        memo: dict[tuple[int, int], float] = {}

        def path_value(col: int, row: int) -> float:
            key = (col, row)
            if key in memo:
                return memo[key]
            node = node_by_pos.get(key)
            if node is None:
                memo[key] = 0.0
                return 0.0
            memo[key] = 0.0  # cycle guard (map is a DAG, but be safe)
            future = max(
                (path_value(c_col, c_row) for c_col, c_row in node.children),
                default=0.0,
            )
            value = type_score(node.type) + w.path_step_discount * future
            memo[key] = value
            return value

        scored: dict[str, float] = {}
        best = None
        best_score = float("-inf")
        for opt in opts:
            future = max(
                (path_value(c.col, c.row) for c in opt.leads_to),
                default=0.0,
            )
            if not opt.leads_to and (node := node_by_pos.get((opt.col, opt.row))):
                future = max(
                    (path_value(c_col, c_row) for c_col, c_row in node.children),
                    default=0.0,
                )
            score = type_score(opt.type) + w.path_step_discount * future
            scored[f"{opt.index}:{opt.type}"] = round(score, 2)
            if score > best_score:
                best_score, best = score, opt
        assert best is not None
        boss_row = state.map.boss.row if state.map.boss else None
        if boss_row is not None and best.row == boss_row - 1:
            ctx.screen_mem["pre_boss"] = True  # arriving on the last row before the boss
        else:
            ctx.screen_mem.pop("pre_boss", None)
        return Decision(
            action=act.ChooseMapNode(index=best.index),
            rationale=f"route to {best.type} at ({best.col},{best.row}) "
            f"(best path value {best_score:.1f})",
            scores=scored,
        )

    # ------------------------------------------------------------------ events

    def _event(self, state: EventState, ctx: LoopContext) -> Decision | Wait:
        w = self.config.events
        ev = state.event
        if ev.in_dialogue:
            return Decision(action=act.AdvanceDialogue(), rationale="advance event dialogue")
        unlocked = [o for o in ev.options if not o.is_locked]
        if not unlocked:
            return Wait(reason="event with no unlocked options")

        player = state.player
        hp, max_hp = (player.hp, player.max_hp) if player else (1, 1)
        hp_pct = hp / max(1, max_hp)
        eid = ev.event_id

        # Score affordable, non-proceed options: a gain/cost heuristic plus Spirebird's
        # per-option vsBaseline where it matches. The heuristic alone fixes the real bug (the
        # old code only saw relic/"card" as gain and declined free Max-HP / heal / upgrade
        # picks); when Spirebird confidently rates >=2 options we trust its ranking over the
        # heuristic, vetoing only clearly-harmful picks.
        scored = []  # (option, heuristic_value, spirebird_vs)
        for o in unlocked:
            if o.is_proceed:
                continue
            text = f"{o.title or ''} {o.description or ''}"
            hp_cost = parse_hp_cost(text)
            if hp_cost:
                after_pct = (hp - hp_cost) / max(1, max_hp)
                # Refuse if already too hurt to pay, or if paying drops us into the danger
                # zone — a choice can be great on Spirebird yet suicidal in the current state.
                if hp_pct < w.hp_cost_refuse_below or after_pct < w.min_hp_pct_after_cost:
                    continue
            heur = self._event_option_value(o, hp, max_hp)
            vs = self.event_stats.option_vs(eid, o.title) if self.event_stats else None
            scored.append((o, heur, vs))

        rated = [s for s in scored if s[2] is not None]
        if len(rated) >= 2:
            o, heur, vs = max(rated, key=lambda s: s[2])
            if heur > w.spirebird_take_floor:
                return Decision(
                    action=act.ChooseEventOption(index=o.index),
                    rationale=f"event: take '{o.title}' (Spirebird vs {vs:.1f})",
                )
        if scored:
            o, heur, vs = max(scored, key=lambda s: s[1])
            if heur >= w.take_min:
                return Decision(
                    action=act.ChooseEventOption(index=o.index),
                    rationale=f"event: take '{o.title}' (value {heur:.1f})",
                )

        proceed = next((o for o in unlocked if o.is_proceed), None)
        if proceed is not None:
            return Decision(
                action=act.ChooseEventOption(index=proceed.index),
                rationale="decline event (nothing worth the cost)",
            )
        if scored:  # no proceed option: take the best heuristic option
            o = max(scored, key=lambda s: s[1])[0]
            return Decision(
                action=act.ChooseEventOption(index=o.index), rationale=f"event: '{o.title}'"
            )
        cheapest = min(
            unlocked, key=lambda o: parse_hp_cost(f"{o.title or ''} {o.description or ''}")
        )
        return Decision(
            action=act.ChooseEventOption(index=cheapest.index),
            rationale=f"event: least-cost '{cheapest.title}'",
        )

    def _event_option_value(self, option, hp: int, max_hp: int) -> float:
        """Net value of an event option (gains - costs), recognizing the gains the card-text
        parser misses: Max HP, heal, upgrade, remove, relic, gold."""
        text = f"{option.title or ''} {option.description or ''}"
        low = text.lower()
        fx = parse_card_description(text)
        val = 0.0
        if m := _EV_MAXHP_GAIN.search(text):
            val += int(m.group(1)) * 1.5
        if fx.heal:
            val += min(fx.heal, max(0, max_hp - hp)) * 0.4
        if "upgrade" in low:
            val += 5.0
        if "remove" in low:
            val += 5.0
        if option.relic_name:
            val += 6.0
        if m := _EV_GOLD_GAIN.search(text):
            val += int(m.group(1)) * 0.03
        if "add " in low and "curse" not in low:
            val += 1.0  # a card into the deck — usually fine, occasionally a trap
        val -= fx.max_hp_cost * 1.5
        val -= fx.self_hp_cost * 0.3
        if "curse" in low:
            val -= 8.0
        if m := _EV_GOLD_LOSS.search(text):
            val -= int(m.group(1)) * 0.03
        return val

    # ------------------------------------------------------------------ card rewards

    def _card_score(
        self, card, deck_size: int, character: str | None = None, act: int = 1
    ) -> float:
        w = self.config.card_rewards
        fx = parse_card_description(card.description)
        score = {
            "Common": w.w_rarity_common,
            "Uncommon": w.w_rarity_uncommon,
            "Rare": w.w_rarity_rare,
        }.get(card.rarity or "", w.w_rarity_common)
        if self.priors is not None:
            prior = self.priors.score(card.id, character)
            if prior is not None:
                if prior > 0:
                    # discount upside the planner can't cash in (owner insight:
                    # Evil Eye / Dark Embrace / Cascade need a pilot we aren't yet)
                    if not fx.has_any_effect:
                        prior *= w.unparsed_prior_mult
                    elif fx.conditional:
                        prior *= w.conditional_prior_mult
                score += w.prior_weight * prior
            # act-appropriateness nudge (8.1b)
            score += w.prior_act_weight * self.priors.act_tilt(card.id, character, act)
        score += {
            "Attack": w.w_attack,
            "Skill": w.w_skill,
            "Power": w.w_power,
        }.get(card.type or "", 0.0)
        if fx.aoe:
            score += w.bonus_aoe
        if fx.block:
            score += w.bonus_block
        if fx.draw:
            score += w.bonus_draw
        if fx.energy_gain:
            score += w.bonus_energy
        # Early-damage bias (owner, Run-2/3): Act 1 favors cards that deliver damage, to get
        # through early fights. Includes attack-*generators* like Infernal Blade — a Skill the
        # text parser reads no damage on, but it adds a free Attack, so it plays like one.
        # (Deck-aware drafting, e.g. Vulnerable only once Vicious is drafted, is deferred.)
        desc_l = (card.description or "").lower()
        generates_attack = "random attack" in desc_l or ("add" in desc_l and "attack" in desc_l)
        if act <= 1 and (fx.total_damage > 0 or generates_attack):
            score += w.early_damage_bonus
        try:
            if card.cost is not None and card.cost.upper() != "X" and int(card.cost) >= 3:
                score += w.penalty_cost_3plus
        except ValueError:
            pass
        if deck_size > 25:
            score += w.penalty_deck_over_25
        return score

    def _card_reward(self, state: CardRewardState, ctx: LoopContext) -> Decision | Wait:
        w = self.config.card_rewards
        cr = state.card_reward
        if not cr.cards:
            if cr.can_skip:
                return Decision(action=act.SkipCardReward(), rationale="no cards offered; skip")
            return Wait(reason="card reward with no cards and no skip")
        deck_size = len(state.player.deck) if (state.player and state.player.deck) else 15
        character = state.player.character if state.player else None
        run_act = state.run.act if state.run else 1
        scored = [(self._card_score(c, deck_size, character, run_act), c) for c in cr.cards]
        scored.sort(key=lambda sc: -sc[0])
        best_score, best = scored[0]
        score_map = {c.name: round(s, 2) for s, c in scored}
        if best_score >= w.take_threshold or not cr.can_skip:
            return Decision(
                action=act.SelectCardReward(card_index=best.index),
                rationale=f"take {best.name} (score {best_score:.1f})",
                scores=score_map,
            )
        return Decision(
            action=act.SkipCardReward(),
            rationale=f"skip: best {best.name} scored {best_score:.1f} < "
            f"threshold {w.take_threshold}",
            scores=score_map,
        )

    # -------------------------------------------------------- card selection overlay

    def _card_quality(self, card, character: str | None) -> float:
        """Higher = better card to KEEP; lower = better to remove. Curses sink below
        un-upgraded basics, which sink below everything else; Spirebird prior on top."""
        w = self.config.deck
        base = (card.name or "").rstrip("+")
        quality = 0.0
        if (card.type or "") in ("Curse", "Status"):
            quality += w.curse_penalty
        if base in ("Strike", "Defend") and not card.is_upgraded:
            quality += w.basic_penalty
        if self.priors is not None:
            prior = self.priors.score(card.id, character)
            if prior is not None:
                quality += prior
        return quality

    def _has_removable_card(self, player) -> bool:
        """A basic or curse worth paying to remove. Unknown deck -> assume yes (the
        selection screen targets the worst card regardless)."""
        if player is None or player.deck is None:
            return True
        for c in player.deck:
            if (c.type or "") in ("Curse", "Status"):
                return True
            if (c.name or "").rstrip("+") in ("Strike", "Defend") and not c.is_upgraded:
                return True
        return False

    @staticmethod
    def _select_count(prompt: str) -> int:
        m = re.search(r"choose (\d+)", prompt)
        return int(m.group(1)) if m else 1

    def _pick_target(self, cs, prefer_worst: bool, character, exclude=()):
        prompt = (cs.prompt or "").lower()
        candidates = [c for c in cs.cards if c.index not in exclude]
        is_upgrade = "upgrade" in prompt or "enchant" in prompt
        if is_upgrade:
            unupgraded = [c for c in candidates if not c.is_upgraded]
            if unupgraded:
                candidates = unupgraded
        if not candidates:
            return None
        if is_upgrade:
            # Upgrade the card that GAINS the most (Spirebird upgraded-vs-base delta),
            # tie-broken by base quality; missing deltas default to a typical gain.
            def upgrade_key(c):
                uv = self.priors.upgrade_value(c.id, character) if self.priors else None
                return (uv if uv is not None else 1.5, self._card_quality(c, character))

            return max(candidates, key=upgrade_key)
        chooser = min if prefer_worst else max
        return chooser(candidates, key=lambda c: self._card_quality(c, character))

    # Bounds so a non-progressing screen can never rail a run (run 2: a 'choose'
    # screen returned 'ok' but never resolved; the old await-confirm Wait stalled).
    _CHOOSE_RETRIES = 3
    _AWAIT_CONFIRM_POLLS = 8

    def _card_select(self, state: CardSelectState, ctx: LoopContext) -> Decision | Wait:
        """Target removal/transform at the WORST cards (basics, curses), upgrade/
        enchant at the BEST un-upgraded, add/choose at the BEST. Every path is
        bounded — on a stuck screen we skip/cancel rather than wait forever."""
        cs = state.card_select
        prompt = (cs.prompt or "").lower()
        prefer_worst = any(
            v in prompt for v in ("remove", "transform", "exhaust", "destroy", "discard")
        )
        character = state.player.character if state.player else None

        # Preview-based per-card selection (Gnarled Axe enchant etc.): pick a card -> it previews
        # -> confirm to lock it in -> repeat until the screen closes. `can_confirm` stays True
        # *between* cards, so confirming while nothing is previewed is a no-op that hangs the loop
        # (live f27: select once, then confirm 61x). Drive it off preview_showing instead.
        preview_key = f"cardsel_preview:{cs.screen_type}:{cs.prompt}"
        if cs.preview_showing:
            ctx.screen_mem[preview_key] = True
            if cs.can_confirm:
                return Decision(action=act.ConfirmSelection(), rationale="lock in previewed card")
            return Wait(reason="preview showing; awaiting confirm")
        if ctx.screen_mem.get(preview_key):  # preview screen, between cards: pick the next one
            if cs.cards:
                target = self._pick_target(cs, prefer_worst, character) or cs.cards[0]
                return Decision(
                    action=act.SelectCard(index=target.index),
                    rationale=f"select {target.name} to enchant ({cs.prompt})",
                )
            ctx.screen_mem.pop(preview_key, None)
            if cs.can_confirm:
                return Decision(action=act.ConfirmSelection(), rationale="all picks made; confirm")
            if cs.can_skip or cs.can_cancel:
                return Decision(action=act.CancelSelection(), rationale="preview screen done")
            return Wait(reason="preview screen: awaiting close")

        # fingerprint the offered cards so a later same-prompt screen gets fresh
        # mem (retry counts / picks don't leak across distinct selection events).
        fp = ",".join(f"{c.index}:{c.id or c.name}" for c in cs.cards)
        mem_key = f"cardsel:{cs.screen_type}:{cs.prompt}:{fp}"
        if cs.can_confirm:
            ctx.screen_mem.pop(mem_key, None)
            return Decision(action=act.ConfirmSelection(), rationale="confirm card selection")
        if not cs.cards:
            ctx.screen_mem.pop(mem_key, None)
            if cs.can_skip or cs.can_cancel:
                return Decision(action=act.CancelSelection(), rationale="nothing selectable; skip")
            return Wait(reason="card select with no cards, confirm, or cancel")

        mem: dict = ctx.screen_mem.setdefault(mem_key, {"picked": [], "tries": 0})

        # choose-a-card: select_card picks immediately (no confirm). Re-press a few
        # times if it doesn't resolve, then skip rather than stall.
        if (cs.screen_type or "") == "choose":
            target = self._pick_target(cs, prefer_worst, character)
            if mem["tries"] < self._CHOOSE_RETRIES and target is not None:
                mem["tries"] += 1
                return Decision(
                    action=act.SelectCard(index=target.index),
                    rationale=f"choose {target.name} for: {cs.prompt}",
                )
            ctx.screen_mem.pop(mem_key, None)
            if cs.can_skip or cs.can_cancel:
                return Decision(
                    action=act.CancelSelection(), rationale="choose not resolving; skip"
                )
            return Wait(reason="choose-a-card stuck")

        # grid: select the right N distinct cards, then confirm when offered.
        needed = self._select_count(prompt)
        picked: list[int] = mem["picked"]
        if len(picked) < needed:
            target = self._pick_target(cs, prefer_worst, character, exclude=picked)
            if target is None:
                ctx.screen_mem.pop(mem_key, None)
                if cs.can_skip or cs.can_cancel:
                    return Decision(action=act.CancelSelection(), rationale="no target; skip")
                return Wait(reason="card select: no remaining candidates")
            picked.append(target.index)
            kind = "worst" if prefer_worst else "best"
            return Decision(
                action=act.SelectCard(index=target.index),
                rationale=f"select {kind} {target.name} for: {cs.prompt}",
            )
        # enough chosen — wait briefly for confirm to enable, then bail safely.
        mem["tries"] += 1
        if mem["tries"] > self._AWAIT_CONFIRM_POLLS and (cs.can_skip or cs.can_cancel):
            ctx.screen_mem.pop(mem_key, None)
            return Decision(
                action=act.CancelSelection(), rationale="selection not confirming; skip"
            )
        return Wait(reason=f"selected {len(picked)}/{needed}; awaiting confirm")

    def _hand_select(self, state: HandSelectState, ctx: LoopContext) -> Decision | Wait:
        """In-combat 'choose a card to exhaust/discard/upgrade'. Target the WORST card
        for exhaust/discard (curses, basics), the BEST for upgrade — the trivial
        fallback picked arbitrarily (observed: exhausted a Defend over the curse Decay).
        Selected cards leave `cards`, so we just pick from what remains until confirm."""
        hs = state.hand_select
        if hs.can_confirm:
            return Decision(
                action=act.CombatConfirmSelection(), rationale="confirm hand selection"
            )
        if not hs.cards:
            return Wait(reason="hand_select with no cards and no confirm")
        prompt = (hs.prompt or "").lower()
        prefer_worst = any(v in prompt for v in ("exhaust", "discard", "remove", "destroy"))
        character = state.player.character if state.player else None
        target = self._pick_target(hs, prefer_worst, character)
        if target is None:
            return Wait(reason="hand_select: no candidates")
        kind = "worst" if prefer_worst else "best"
        return Decision(
            action=act.CombatSelectCard(card_index=target.index),
            rationale=f"hand-select {kind} {target.name}: {hs.prompt}",
        )

    # ------------------------------------------------------------------ rest sites

    @staticmethod
    def _rest_option_key(option) -> str:
        """Canonical key for a rest option. Live IDs are 'HEAL'/'SMITH' (not
        'rest'/'smith') — this bug silently disabled rest-vs-smith since session 3."""
        s = (option.id or option.name or "").lower()
        if "heal" in s or "rest" in s:
            return "rest"
        if "smith" in s or "upgrade" in s:
            return "smith"
        return s

    def _rest_site(self, state: RestSiteState, ctx: LoopContext) -> Decision | Wait:
        w = self.config.rest
        rs = state.rest_site
        enabled = {self._rest_option_key(o): o for o in rs.options if o.is_enabled}
        player = state.player
        hp = player.hp if player else 1
        hp_pct = hp / max(1, player.max_hp) if player else 1.0
        pre_boss = bool(ctx.screen_mem.get("pre_boss"))

        # Rest only when we might not survive to the next heal, else smith to gear up.
        if pre_boss:
            # next "fight" is the boss: estimate its likely HP cost from our own history.
            est = self.combat_stats.expected_loss("boss") if self.combat_stats else None
            if est is None:
                est = w.default_boss_loss
            needed = est * w.boss_safety_factor
            should_rest = hp < needed
            rest_why = f"rest: {hp} HP < ~{needed:.0f} needed for boss (est loss {est:.0f})"
            smith_why = f"smith: {hp} HP covers the boss (~{needed:.0f} needed)"
        else:
            should_rest = hp_pct < w.rest_below_hp_pct
            rest_why = f"rest at {hp_pct:.0%} HP"
            smith_why = f"smith (HP {hp_pct:.0%} is comfortable)"

        if should_rest and "rest" in enabled:
            return Decision(
                action=act.ChooseRestOption(index=enabled["rest"].index), rationale=rest_why
            )
        if "smith" in enabled:
            return Decision(
                action=act.ChooseRestOption(index=enabled["smith"].index), rationale=smith_why
            )
        if "rest" in enabled:
            return Decision(
                action=act.ChooseRestOption(index=enabled["rest"].index),
                rationale="rest (no smith available)",
            )
        if enabled:
            first = next(iter(enabled.values()))
            return Decision(
                action=act.ChooseRestOption(index=first.index),
                rationale=f"rest-site option {first.name}",
            )
        if rs.can_proceed:
            return Decision(action=act.Proceed(), rationale="rest done; proceed")
        return Wait(reason="rest site with nothing enabled and no proceed")

    # ------------------------------------------------------------------ shop

    def _shop(self, state: ShopState, ctx: LoopContext) -> Decision | Wait:
        w = self.config.shop
        if state.shop.error:
            return Wait(reason=f"shop inventory not ready: {state.shop.error}")
        player = state.player
        gold = player.gold if player else 0
        reserve = w.removal_min_gold_reserve
        bought = ctx.screen_mem.setdefault("shop_bought", [])
        avail = [i for i in state.shop.items if i.is_stocked and i.index not in bought]

        # 0. Discount relics (Membership Card -50% / Courier -20%, applied immediately) — buy
        #    FIRST so the rest of the shop is cheaper; once owned, the live shop returns
        #    discounted prices, and the Courier's restock is exploited by the one-buy-per-poll
        #    re-poll. Bought even if the value table can't rate them (Courier isn't in it),
        #    as long as there's other stock the discount will help with. (TODO: don't buy in
        #    isolation at the known last shop of the run — needs intended-path tracking.)
        discount_relics = {"MEMBERSHIP_CARD", "THE_COURIER", "COURIER"}
        for item in avail:
            price = item.gold_price or 0
            if (
                item.category == "relic"
                and (item.relic_id or "").upper() in discount_relics
                and item.can_afford
                and gold - price >= reserve
            ):
                v = self.shop_stats.relic_value(item.relic_id) if self.shop_stats else None
                worth_on_own = v is not None and v >= w.relic_war_per_100g_min
                if worth_on_own or len(avail) > 1:
                    bought.append(item.index)
                    return Decision(
                        action=act.ShopPurchase(index=item.index),
                        rationale=f"buy {item.relic_name} FIRST ({price}g; discounts the shop)",
                    )

        # 1. Card removal — high, safe value when there's a junk card to cut.
        for item in avail:
            price = item.gold_price or 0
            if (
                item.category == "card_removal"
                and price <= w.removal_max_price
                and gold - price >= reserve
                and self._has_removable_card(player)
            ):
                bought.append(item.index)
                return Decision(
                    action=act.ShopPurchase(index=item.index),
                    rationale=f"buy card removal ({price}g <= cap {w.removal_max_price})",
                )

        # 2. Best-value relic by Spirebird WAR/100g — buy the strongest affordable one and
        #    skip the duds (negative value-per-gold) and unknowns the data can't vouch for.
        relic_buys = []
        for item in avail:
            price = item.gold_price or 0
            if item.category == "relic" and item.can_afford and gold - price >= reserve:
                v = self.shop_stats.relic_value(item.relic_id) if self.shop_stats else None
                if v is not None and v >= w.relic_war_per_100g_min:
                    relic_buys.append((v, price, item))
        if relic_buys:
            v, price, item = max(relic_buys, key=lambda x: x[0])
            bought.append(item.index)
            return Decision(
                action=act.ShopPurchase(index=item.index),
                rationale=f"buy relic {item.relic_name} ({price}g, WAR/100g {v:+.3f})",
            )

        # 3. Potions (utility, when the belt has room).
        for item in avail:
            price = item.gold_price or 0
            if (
                item.category == "potion"
                and gold >= w.buy_potion_min_gold
                and player is not None
                and len(player.potions) < player.max_potion_slots
                and item.can_afford
            ):
                bought.append(item.index)
                return Decision(
                    action=act.ShopPurchase(index=item.index),
                    rationale=f"buy {item.potion_name} ({price}g)",
                )
        return Decision(action=act.Proceed(), rationale="done shopping")

    # ------------------------------------------------------------------ rewards (potion-aware)

    def _rewards(self, state: RewardsState, ctx: LoopContext) -> Decision | Wait:
        player = state.player
        if player is not None and len(player.potions) >= player.max_potion_slots:
            potion_items = [i for i in state.rewards.items if i.type == "potion"]
            if potion_items and not ctx.screen_mem.get("discarded_for_reward"):
                victim = self._worst_potion(player.potions)
                if victim is not None:
                    ctx.screen_mem["discarded_for_reward"] = True
                    return Decision(
                        action=act.DiscardPotion(slot=victim.slot),
                        rationale=f"discard {victim.name} to make room for reward potion",
                    )
        decision = self._fallback.decide(state, ctx)
        if isinstance(decision, Decision) and decision.action.payload().get("action") == "proceed":
            ctx.screen_mem.pop("discarded_for_reward", None)
        return decision

    # Keep-value by category for the full-belt discard: ditch junk (downside / unknown),
    # keep the good stuff (heals, buffs, energy/draw value, damage). Tie-break by slot.
    _DISCARD_RANK: ClassVar[dict[str, int]] = {
        "downside": 0, "other": 1, "debuff": 3, "block": 3, "value": 4,
        "damage": 4, "aoe_damage": 4, "buff": 5, "heal": 6, "fruit_juice": 7,
    }

    def _worst_potion(self, potions: list[Potion]) -> Potion | None:
        if not potions:
            return None
        priority = [p.upper() for p in self.config.potions.discard_priority]
        for pid in priority:  # explicit config override wins
            for potion in potions:
                if potion.id.upper() == pid:
                    return potion
        # else discard the lowest-value potion by category — was arbitrarily potions[0],
        # which threw away a Cure All when the cascade landed it in slot 0 (live B04BGZEDRN).
        return min(potions, key=lambda p: (self._DISCARD_RANK.get(self._potion_category(p), 2),
                                           p.slot))
