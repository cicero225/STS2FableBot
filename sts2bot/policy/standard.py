"""StandardRouter: the first real policy set (P1).

Smart handling for combat (one-turn planner), map routing, events, card rewards,
rest sites, shops, reward-screen potion management, and in-combat potions.
Everything else (menus/navigation, overlays, minigames) delegates to the
TrivialRouter, which is already battle-tested plumbing.
"""

from __future__ import annotations

from sts2bot.client import actions as act
from sts2bot.client.models import (
    CardRewardState,
    CombatState,
    EventState,
    GameState,
    MapState,
    Potion,
    RestSiteState,
    RewardsState,
    ShopState,
)
from sts2bot.kb.config import PolicyConfig, load_policy_config
from sts2bot.policy.base import Decision, LoopContext, Wait
from sts2bot.policy.combat import plan_combat_turn
from sts2bot.policy.textparse import parse_card_description, parse_hp_cost, parse_intent_damage
from sts2bot.policy.trivial import TrivialRouter


class StandardRouter:
    def __init__(self, config: PolicyConfig | None = None):
        self.config = config or load_policy_config()
        self._fallback = TrivialRouter()

    def decide(self, state: GameState, ctx: LoopContext) -> Decision | Wait:
        handler = getattr(self, f"_{state.state_type}", None)
        if handler is not None:
            return handler(state, ctx)
        return self._fallback.decide(state, ctx)

    # ------------------------------------------------------------------ combat

    def _combat(self, state: CombatState, ctx: LoopContext) -> Decision | Wait:
        potion_play = self._combat_potion(state)
        if potion_play is not None:
            return potion_play
        return plan_combat_turn(state, self.config.combat)

    _monster = _combat
    _elite = _combat
    _boss = _combat

    def _combat_potion(self, state: CombatState) -> Decision | None:
        """Drink a useful potion when the fight is dangerous (elite/boss) or HP is dire."""
        w = self.config.potions
        player = state.player
        if player is None or not player.in_combat or state.battle is None:
            return None
        if state.battle.turn != "player" or state.battle.is_play_phase is False:
            return None
        if state.battle.actions_disabled:
            return None
        hp_pct = player.hp / max(1, player.max_hp)
        dangerous = state.state_type in ("elite", "boss") and w.drink_in_elite_or_boss
        dire = hp_pct < w.drink_when_hp_pct_below
        if not (dangerous or dire):
            return None
        incoming = sum(
            parse_intent_damage(i.label)
            for e in state.battle.enemies
            if e.hp > 0
            for i in e.intents
            if i.type.lower() == "attack"
        )
        usable = [p for p in player.potions if p.can_use_in_combat is not False]
        for potion in usable:
            fx = parse_card_description(potion.description)
            if fx.total_damage > 0:
                alive = [e for e in state.battle.enemies if e.hp > 0]
                if not alive:
                    continue
                target = max(alive, key=lambda e: e.hp)
                needs_target = (potion.target_type or "").lower() not in ("none", "self")
                return Decision(
                    action=act.UsePotion(
                        slot=potion.slot, target=target.entity_id if needs_target else None
                    ),
                    rationale=f"drink {potion.name} ({'dire HP' if dire else 'hard fight'})",
                )
            if fx.block > 0 and incoming > player.block:
                return Decision(
                    action=act.UsePotion(slot=potion.slot),
                    rationale=f"drink {potion.name} to block {incoming} incoming",
                )
            if fx.heal > 0 and dire:
                return Decision(
                    action=act.UsePotion(slot=potion.slot),
                    rationale=f"drink {potion.name} to heal at {hp_pct:.0%} HP",
                )
        # Hail mary (learned from run 10: died at 3 HP holding two buff potions):
        # if this turn's unblocked incoming can kill us, drink anything usable.
        if w.hail_mary and dire and usable and incoming - player.block >= player.hp:
            potion = usable[0]
            needs_target = (potion.target_type or "").lower() not in ("none", "self")
            target = None
            if needs_target:
                alive = [e for e in state.battle.enemies if e.hp > 0]
                if alive:
                    target = max(alive, key=lambda e: e.hp).entity_id
            return Decision(
                action=act.UsePotion(slot=potion.slot, target=target),
                rationale=f"hail mary: drink {potion.name} (incoming {incoming} >= "
                f"{player.hp} HP)",
            )
        return None

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

        scored: dict[str, float] = {}
        best = None
        best_score = float("-inf")
        for opt in opts:
            score = type_score(opt.type)
            score += w.lookahead_discount * (
                max((type_score(child.type) for child in opt.leads_to), default=0.0)
            )
            scored[f"{opt.index}:{opt.type}"] = round(score, 2)
            if score > best_score:
                best_score, best = score, opt
        assert best is not None
        return Decision(
            action=act.ChooseMapNode(index=best.index),
            rationale=f"route to {best.type} at ({best.col},{best.row})",
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

        choices = []
        for option in unlocked:
            text = f"{option.title or ''} {option.description or ''}"
            hp_cost = parse_hp_cost(text)
            affordable = hp_cost == 0 or (hp - hp_cost > 0 and hp_pct >= w.hp_cost_refuse_below)
            gain = 1.0 if (option.relic_name or "card" in text.lower()) else 0.0
            choices.append((option, hp_cost, affordable, gain))

        # prefer affordable gainful options, then affordable non-proceed, then proceed
        affordable_gain = [c for c in choices if c[2] and c[3] > 0 and not c[0].is_proceed]
        if affordable_gain:
            option = min(affordable_gain, key=lambda c: c[1])[0]
            return Decision(
                action=act.ChooseEventOption(index=option.index),
                rationale=f"event gain option: {option.title}",
            )
        affordable_other = [c for c in choices if c[2] and not c[0].is_proceed and c[1] == 0]
        if affordable_other and hp_pct >= w.unknown_take_first_above:
            option = affordable_other[0][0]
            return Decision(
                action=act.ChooseEventOption(index=option.index),
                rationale=f"event option (HP comfortable): {option.title}",
            )
        proceed = next((o for o in unlocked if o.is_proceed), None)
        if proceed is not None:
            return Decision(
                action=act.ChooseEventOption(index=proceed.index),
                rationale="decline event (HP-risk or nothing worth taking)",
            )
        # no explicit proceed: take the cheapest affordable option
        fallback = min(choices, key=lambda c: (not c[2], c[1]))[0]
        return Decision(
            action=act.ChooseEventOption(index=fallback.index),
            rationale=f"least-cost event option: {fallback.title}",
        )

    # ------------------------------------------------------------------ card rewards

    def _card_score(self, card, deck_size: int) -> float:
        w = self.config.card_rewards
        fx = parse_card_description(card.description)
        score = {
            "Common": w.w_rarity_common,
            "Uncommon": w.w_rarity_uncommon,
            "Rare": w.w_rarity_rare,
        }.get(card.rarity or "", w.w_rarity_common)
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
        scored = [(self._card_score(c, deck_size), c) for c in cr.cards]
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

    # ------------------------------------------------------------------ rest sites

    def _rest_site(self, state: RestSiteState, ctx: LoopContext) -> Decision | Wait:
        w = self.config.rest
        rs = state.rest_site
        enabled = {o.id or (o.name or "").lower(): o for o in rs.options if o.is_enabled}
        player = state.player
        hp_pct = player.hp / max(1, player.max_hp) if player else 1.0
        if hp_pct < w.rest_below_hp_pct and "rest" in enabled:
            return Decision(
                action=act.ChooseRestOption(index=enabled["rest"].index),
                rationale=f"rest at {hp_pct:.0%} HP",
            )
        if "smith" in enabled:
            return Decision(
                action=act.ChooseRestOption(index=enabled["smith"].index),
                rationale=f"smith (HP {hp_pct:.0%} is comfortable)",
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
        bought = ctx.screen_mem.setdefault("shop_bought", [])
        for item in state.shop.items:
            if not item.is_stocked or item.index in bought:
                continue
            price = item.gold_price or 0
            if item.category == "card_removal" and gold - price >= w.removal_min_gold_reserve:
                bought.append(item.index)
                return Decision(
                    action=act.ShopPurchase(index=item.index),
                    rationale=f"buy card removal ({price}g, {gold}g held)",
                )
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

    def _worst_potion(self, potions: list[Potion]) -> Potion | None:
        if not potions:
            return None
        priority = [p.upper() for p in self.config.potions.discard_priority]
        for pid in priority:
            for potion in potions:
                if potion.id.upper() == pid:
                    return potion
        return potions[0]
