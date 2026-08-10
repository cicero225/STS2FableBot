"""Trivial first-legal-choice policies for every state type (P0 / M0).

These exist to exercise plumbing, not to win. Real policies replace them per-domain
in P1 (see PLAN.md §4-5). The menu handler doubles as the navigator: it walks from
the main menu into a singleplayer run and dismisses popups/tutorials/game-over.
"""

from __future__ import annotations

from sts2bot.client import actions as act
from sts2bot.client.models import (
    BundleSelectState,
    CardRewardState,
    CardSelectState,
    CombatState,
    CrystalSphereState,
    EventState,
    FakeMerchantState,
    GameOverState,
    GameState,
    HandSelectState,
    MapState,
    MenuState,
    OverlayState,
    RestSiteState,
    RewardsState,
    ShopState,
    TreasureState,
    UnknownState,
)
from sts2bot.policy.base import Decision, LoopContext, Wait


class TrivialRouter:
    """First-legal-choice decisions for every state type."""

    def decide(self, state: GameState, ctx: LoopContext) -> Decision | Wait:
        handler = getattr(self, f"_{state.state_type}", None)
        if handler is None:
            return Wait(reason=f"no handler for state_type={state.state_type}")
        return handler(state, ctx)

    # ------------------------------------------------------------------ menus

    def _menu(self, state: MenuState, ctx: LoopContext) -> Decision | Wait:
        screen = state.menu_screen or "main"
        options = [o.lower() for o in state.option_names()]

        def pick(option: str, why: str) -> Decision:
            return Decision(action=act.MenuSelect(option=option), rationale=why)

        if screen == "popup":
            for preferred in ("ignore", "ok", "confirm", "back"):
                if preferred in options:
                    return pick(preferred, "dismiss blocking popup")
            if options:
                return pick(options[0], "dismiss blocking popup (first option)")
            return Wait(reason="popup with no options")

        if screen == "tutorial_prompt":
            return pick("no", "decline tutorial (bot does not need FTUE)")

        if screen == "timeline":
            # The mod refuses to open Timeline, so if it's open the OWNER opened it
            # (epoch reveal). Backing out would kick them off the screen (happened
            # live 2026-06-11) — hands off until they finish.
            return Wait(reason="MANUAL: Timeline is open — waiting for owner to finish the reveal")

        if screen == "profile_select":
            if ctx.profile_id is not None:
                return pick(f"profile_{ctx.profile_id}", f"select bot profile {ctx.profile_id}")
            return pick("back", "no profile configured; leave profile select")

        if ctx.goal != "start_run":
            if "back" in options:
                return pick("back", "retreat toward main menu")
            return Wait(reason=f"no path for goal={ctx.goal} on screen={screen}")

        if screen == "main":
            ctx.screen_mem.pop("character_sent", None)
            ctx.screen_mem.pop("embark_sent", None)
            if "continue" in options:
                return pick("continue", "resume saved run")
            if "singleplayer" in options:
                return pick("singleplayer", "start a new singleplayer run")
            blocked = state.blocked_options or []
            reveal = [
                b
                for b in blocked
                if isinstance(b, dict) and b.get("reason") == "manual_epoch_reveal_required"
            ]
            if reveal:
                epochs = [e for b in reveal for e in b.get("pending_epoch_ids", [])]
                return Wait(
                    reason="MANUAL: Timeline epoch reveal required "
                    f"({', '.join(epochs) or 'unknown epoch'}) — owner must open "
                    "Timeline in-game once (mod refuses to automate this safely)"
                )
            return Wait(reason="main menu without singleplayer/continue")

        if screen == "singleplayer":
            return pick("standard", "standard run mode")

        if screen == "character_select":
            return self._character_select(state, ctx, pick)

        if "back" in options:
            return pick("back", f"unhandled menu screen {screen}; retreating")
        return Wait(reason=f"unhandled menu screen {screen} with no back option")

    def _character_select(self, state: MenuState, ctx: LoopContext, pick) -> Decision | Wait:
        """Verify-before-confirm: the screen's unlock animation can overwrite picks
        (found live 2026-06-11), so with a forked mod we re-select until the state's
        selected_character matches, and only then embark. Falls back to fire-and-hope
        on the unforked mod (no selected_character field)."""
        wanted = ctx.character.lower()
        enabled = state.enabled_options()
        if state.selection_busy:
            return Wait(reason="character unlock animation playing; selection would be lost")

        if state.selected_character is not None:
            selected = state.selected_character.lower()
            if selected != wanted:
                ctx.screen_mem.pop("embark_sent", None)
                if enabled.get(wanted):
                    return pick(
                        ctx.character,
                        f"select {ctx.character} (screen has {state.selected_character})",
                    )
                return Wait(
                    reason=f"MANUAL: requested character {ctx.character} is not selectable "
                    f"(locked or absent); screen has {state.selected_character}"
                )
            if (
                ctx.ascension
                and state.ascension is not None
                and state.ascension != ctx.ascension
                and not ctx.screen_mem.get("embark_sent")
            ):
                if state.max_ascension is not None and ctx.ascension > state.max_ascension:
                    return Wait(
                        reason=f"MANUAL: ascension {ctx.ascension} not unlocked for "
                        f"{ctx.character} (max {state.max_ascension})"
                    )
                return Decision(
                    action=act.SetAscension(level=ctx.ascension),
                    rationale=f"set ascension {state.ascension} -> {ctx.ascension}",
                )
            if ctx.screen_mem.get("embark_sent"):
                return Wait(reason="embarked; waiting for run to start")
            for confirm in ("confirm", "embark"):
                if enabled.get(confirm):
                    ctx.screen_mem["embark_sent"] = True
                    asc = f" A{ctx.ascension}" if ctx.ascension else ""
                    return pick(confirm, f"selection verified ({ctx.character}{asc}); embark")
            return Wait(reason="selection verified; waiting for confirm to enable")

        # Legacy mod without selected_character: select once, confirm once, hope.
        options = [o.lower() for o in state.option_names()]
        if not ctx.screen_mem.get("character_sent") and wanted in options:
            ctx.screen_mem["character_sent"] = True
            return pick(ctx.character, f"select configured character {ctx.character}")
        if ctx.screen_mem.get("embark_sent"):
            return Wait(reason="embarked; waiting for run to start")
        for confirm in ("confirm", "embark"):
            if confirm in options:
                ctx.screen_mem["embark_sent"] = True
                return pick(confirm, "confirm character and embark")
        return Wait(reason="character select without confirm option")

    def _game_over(self, state: GameOverState, ctx: LoopContext) -> Decision | Wait:
        return Decision(
            action=act.MenuSelect(option="main_menu"),
            rationale="run ended; return to main menu",
        )

    # ------------------------------------------------------------------ combat

    def _combat(self, state: CombatState, ctx: LoopContext) -> Decision | Wait:
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
        playable = [c for c in hand if c.can_play]
        if not playable:
            return Decision(action=act.EndTurn(), rationale="no playable cards; end turn")
        card = playable[0]
        target = None
        if card.target_type == "AnyEnemy":
            alive = [e for e in state.battle.enemies if e.hp > 0]
            if not alive:
                return Decision(action=act.EndTurn(), rationale="no living targets; end turn")
            target = alive[0].entity_id
        return Decision(
            action=act.PlayCard(card_index=card.index, target=target),
            rationale=f"play first playable card {card.name}"
            + (f" at {target}" if target else ""),
        )

    _monster = _combat
    _elite = _combat
    _boss = _combat

    def _hand_select(self, state: HandSelectState, ctx: LoopContext) -> Decision | Wait:
        hs = state.hand_select
        if hs.can_confirm:
            return Decision(
                action=act.CombatConfirmSelection(), rationale="confirm hand selection"
            )
        if hs.cards:
            mem_key = f"hand_select:{hs.prompt}"
            i = ctx.screen_mem.get(mem_key, 0)
            ctx.screen_mem[mem_key] = i + 1
            card = hs.cards[i % len(hs.cards)]
            return Decision(
                action=act.CombatSelectCard(card_index=card.index),
                rationale=f"select {card.name} for prompt: {hs.prompt}",
            )
        return Wait(reason="hand_select with no cards and no confirm")

    # ------------------------------------------------------------------ rooms

    def _rewards(self, state: RewardsState, ctx: LoopContext) -> Decision | Wait:
        r = state.rewards
        # Some claims no-op with status "ok" (observed live: potion reward with a full
        # belt). Track attempts per item and abandon any that won't claim, else the
        # loop spins until the stall rail kills the run.
        floor = state.run.floor if state.run else -1
        attempts: dict[str, int] = ctx.screen_mem.setdefault("reward_attempts", {})
        # deliberate skips (late-act-3 Foul claims) live in their own set -- they
        # used to ride the attempts dict, which collided with the counter below
        skip_set = ctx.screen_mem.get("reward_skip") or set()
        for item in r.items:
            marker = item.potion_id or item.gold_amount or item.description or ""
            if (floor, item.type, str(marker)) in skip_set:
                continue
            # remaining-count in the key (owner catch 2026-08-03: THREE identical
            # Foul Potions -- index shifts to 0 as each claims, so all three hashed
            # to one key, two SUCCESSES counted as 'attempts', and the third was
            # abandoned as unclaimable). A successful claim shrinks the list ->
            # fresh key; a true no-op keeps the same count -> the cap still bites.
            key = f"{floor}:{item.index}:{item.type}:{marker}:{len(r.items)}"
            if attempts.get(key, 0) < 2:
                attempts[key] = attempts.get(key, 0) + 1
                label = item.potion_name or item.type
                return Decision(
                    action=act.ClaimReward(index=item.index),
                    rationale=f"claim reward {label} (attempt {attempts[key]})",
                )
        if r.can_proceed:
            why = (
                "leaving unclaimable rewards behind; proceed"
                if r.items
                else "rewards exhausted; proceed"
            )
            return Decision(action=act.Proceed(), rationale=why)
        return Wait(reason="rewards not claimable and cannot proceed")

    def _card_reward(self, state: CardRewardState, ctx: LoopContext) -> Decision | Wait:
        cr = state.card_reward
        if cr.cards:
            card = cr.cards[0]
            return Decision(
                action=act.SelectCardReward(card_index=card.index),
                rationale=f"take first card {card.name}",
            )
        if cr.can_skip:
            return Decision(action=act.SkipCardReward(), rationale="no cards offered; skip")
        return Wait(reason="card reward with no cards and no skip")

    def _map(self, state: MapState, ctx: LoopContext) -> Decision | Wait:
        opts = state.map.next_options
        if not opts:
            return Wait(reason="map with no next options")
        choice = opts[0]
        return Decision(
            action=act.ChooseMapNode(index=choice.index),
            rationale=f"first map option: {choice.type} at ({choice.col},{choice.row})",
        )

    def _event(self, state: EventState, ctx: LoopContext) -> Decision | Wait:
        ev = state.event
        if ev.in_dialogue:
            return Decision(action=act.AdvanceDialogue(), rationale="advance event dialogue")
        unlocked = [o for o in ev.options if not o.is_locked]
        if not unlocked:
            return Wait(reason="event with no unlocked options")
        choice = unlocked[0]
        return Decision(
            action=act.ChooseEventOption(index=choice.index),
            rationale=f"first unlocked event option: {choice.title}",
        )

    def _rest_site(self, state: RestSiteState, ctx: LoopContext) -> Decision | Wait:
        rs = state.rest_site
        enabled = [o for o in rs.options if o.is_enabled]
        if enabled:
            choice = enabled[0]
            return Decision(
                action=act.ChooseRestOption(index=choice.index),
                rationale=f"first rest option: {choice.name}",
            )
        if rs.can_proceed:
            return Decision(action=act.Proceed(), rationale="rest done; proceed")
        return Wait(reason="rest site with nothing enabled and no proceed")

    def _shop(self, state: ShopState, ctx: LoopContext) -> Decision | Wait:
        # passive-/state fork mod: shopkeeper screen persists until we open
        if state.shop.inventory_open is False:
            return Decision(action=act.OpenShopInventory(),
                            rationale="open shop inventory (passive mod)")
        if state.shop.error:
            return Wait(reason=f"shop inventory not ready: {state.shop.error}")
        return Decision(action=act.Proceed(), rationale="trivial policy buys nothing")

    def _fake_merchant(self, state: FakeMerchantState, ctx: LoopContext) -> Decision | Wait:
        return Decision(action=act.Proceed(), rationale="trivial policy ignores fake merchant")

    def _treasure(self, state: TreasureState, ctx: LoopContext) -> Decision | Wait:
        t = state.treasure
        # Passive-/state fork mod (2026-08-10): the chest no longer auto-opens on
        # every poll (the old auto-click barrage is the prime re-entrancy suspect
        # for the claim wedge that killed two batches). Open it EXPLICITLY, gently:
        # one click, an 8-poll dwell before any retry, 3 attempts max, then let
        # the stall rail abort. chest_open None = pre-fork mod, old flow below.
        if t.chest_open is False:
            tick = ctx.screen_mem.get("chest_open_tick", 0)
            ctx.screen_mem["chest_open_tick"] = tick + 1
            if tick // 8 >= 3:
                return Wait(reason="chest open unresolvable after 3 attempts; "
                                   "letting the stall rail abort")
            if tick % 8 == 0:
                return Decision(action=act.OpenChest(),
                                rationale=f"open chest (attempt {tick // 8 + 1}/3)")
            return Wait(reason="chest opening (passive mod)")
        # Wait through the chest's transitional "Opening chest..." state -- `can_proceed` defaults
        # True, so without this guard the bot fires a *premature* proceed before the relic even
        # appears, racing the open/upgrade animation and freezing the map node (esp. at high speed:
        # War Paint on a ?-node, seed ZWSK88UNQN, clean at 1x / frozen at 4x, 2026-06-25).
        if t.message:
            ctx.screen_mem["chest_settle"] = 0  # animation restarted: re-settle
            return Wait(reason=f"treasure opening: {t.message}")
        if t.relics:
            # Settle-dwell + claim cap (2 black screens on 2026-08-01, f41+f26,
            # same anatomy as the card-select wedge): the first claim right after
            # the message clears lands mid-animation and wedges the chest; the
            # 11-tick debounce hammering then escalates the wedge to a BLACK
            # SCREEN. Dwell before the first claim; after 3 ok'd-but-ignored
            # claims stop entirely and let the stall rail abort the run.
            settle = ctx.screen_mem.get("chest_settle", 0)
            if settle < 3:
                ctx.screen_mem["chest_settle"] = settle + 1
                return Wait(reason=f"chest settling ({settle + 1}/3) before claim")
            claims = ctx.screen_mem.get("chest_claims", 0)
            if claims >= 3:
                return Wait(reason="chest claim unresolvable after 3 attempts; "
                                   "letting the stall rail abort")
            ctx.screen_mem["chest_claims"] = claims + 1
            relic = t.relics[0]
            return Decision(
                action=act.ClaimTreasureRelic(index=relic.index or 0),
                rationale=f"claim treasure relic {relic.name}",
            )
        ctx.screen_mem.pop("chest_settle", None)
        ctx.screen_mem.pop("chest_claims", None)
        ctx.screen_mem.pop("chest_open_tick", None)
        if t.can_proceed:
            return Decision(action=act.Proceed(), rationale="treasure claimed; proceed")
        return Wait(reason="treasure chest still opening")

    # ------------------------------------------------------------------ overlays

    def _card_select(self, state: CardSelectState, ctx: LoopContext) -> Decision | Wait:
        cs = state.card_select
        if cs.can_confirm:
            return Decision(action=act.ConfirmSelection(), rationale="confirm card selection")
        if cs.cards:
            mem_key = f"card_select:{cs.prompt}"
            i = ctx.screen_mem.get(mem_key, 0)
            ctx.screen_mem[mem_key] = i + 1
            card = cs.cards[i % len(cs.cards)]
            return Decision(
                action=act.SelectCard(index=card.index),
                rationale=f"select {card.name} for: {cs.prompt}",
            )
        if cs.can_cancel:
            return Decision(action=act.CancelSelection(), rationale="nothing selectable; cancel")
        return Wait(reason="card select with no cards, confirm, or cancel")

    def _bundle_select(self, state: BundleSelectState, ctx: LoopContext) -> Decision | Wait:
        bs = state.bundle_select
        if bs.can_confirm:
            return Decision(
                action=act.ConfirmBundleSelection(), rationale="confirm bundle selection"
            )
        if bs.bundles and not bs.preview_showing:
            return Decision(
                action=act.SelectBundle(index=bs.bundles[0].index),
                rationale="preview first bundle",
            )
        return Wait(reason="bundle select pending preview/confirm availability")

    def _relic_select(self, state, ctx: LoopContext) -> Decision | Wait:
        rs = state.relic_select
        if rs.relics:
            relic = rs.relics[0]
            return Decision(
                action=act.SelectRelic(index=relic.index or 0),
                rationale=f"take first relic {relic.name}",
            )
        if rs.can_skip:
            return Decision(action=act.SkipRelicSelection(), rationale="no relics; skip")
        return Wait(reason="relic select with nothing to do")

    def _crystal_sphere(self, state: CrystalSphereState, ctx: LoopContext) -> Decision | Wait:
        sphere = state.crystal_sphere
        if sphere.can_proceed:
            return Decision(action=act.CrystalSphereProceed(), rationale="minigame done")
        if sphere.clickable_cells:
            cell = sphere.clickable_cells[0]
            return Decision(
                action=act.CrystalSphereClickCell(x=cell.x, y=cell.y),
                rationale=f"reveal first clickable cell ({cell.x},{cell.y})",
            )
        return Wait(reason="crystal sphere with no clickable cells and no proceed")

    # ------------------------------------------------------------------ stuck states

    def _unknown(self, state: UnknownState, ctx: LoopContext) -> Decision | Wait:
        return Wait(reason=f"unknown room type {state.room_type}")

    def _overlay(self, state: OverlayState, ctx: LoopContext) -> Decision | Wait:
        return Wait(reason=f"unhandled overlay {state.overlay.screen_type}")
