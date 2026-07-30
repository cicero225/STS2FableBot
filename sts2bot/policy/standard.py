"""StandardRouter: the first real policy set (P1).

Smart handling for combat (one-turn planner), map routing, events, card rewards,
rest sites, shops, reward-screen potion management, and in-combat potions.
Everything else (menus/navigation, overlays, minigames) delegates to the
TrivialRouter, which is already battle-tested plumbing.
"""

from __future__ import annotations

import re
import time
from typing import ClassVar

from sts2bot.client import actions as act
from sts2bot.client.models import (
    BundleSelectState,
    CardRewardState,
    CardSelectState,
    CombatState,
    EventState,
    GameState,
    HandSelectState,
    MapState,
    Potion,
    RelicSelectState,
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
from sts2bot.policy.capability import (
    _ELITE_COMPOSITIONS,
    FightEnemy,
    bestiary_enemy,
    deck_output,
    elite_fight_members,
    estimate_fight,
    load_bestiary,
    load_card_descriptions,
    load_enemy_dps,
    realized_dps,
)
from sts2bot.policy.combat import plan_combat_turn
from sts2bot.policy.drafttags import (
    boon_relic_context,
    load_ancient_boons,
    load_draft_tags,
    load_event_choices,
    score_adjustment,
)
from sts2bot.policy.rollout import rollout_fight
from sts2bot.policy.textparse import parse_card_description, parse_hp_cost, parse_intent_damage
from sts2bot.policy.trivial import TrivialRouter

# Event-option value cues the card-text parser doesn't cover (gains the bot was blind to).
_EV_MAXHP_GAIN = re.compile(r"Gain (\d+) Max(?:imum)? HP", re.IGNORECASE)
_EV_GOLD_GAIN = re.compile(r"Gain (\d+) Gold", re.IGNORECASE)
_EV_GOLD_LOSS = re.compile(r"Lose (\d+) Gold", re.IGNORECASE)
# Relic grants the mod leaves with relic_name unset: text reads "Obtain the <Relic>"
# (e.g. The Chosen Cheese). Curse-guarded below; "card" is NOT excluded (relics like
# "Membership Card" contain the word).
_EV_OBTAIN_RELIC = re.compile(r"\bobtain (?:the|a|an) ", re.IGNORECASE)

# §5-C elite gate: a typical elite per act (hp, dps, Strength ramp) the deck must be able to *win*
# (not just survive) before the map scorer chases it for its relic. A conservative prior: the batch
# evidence is the bot *loses* Act-1 elites with starter-heavy decks, so err tough; the re-batch
# calibrates these (loosen if no elites taken, tighten if elite deaths persist). Tunable.
_GENERIC_ELITE = {
    1: (90, 17, 1),
    2: (140, 23, 2),
    3: (190, 29, 3),
}
# §5-C drafting target. Prefer the *real* upcoming boss (bestiary: real HP + detected mechanics
# like Slippery/Plating, name cached from map.boss); fall back to this generic profile for unknown
# or multi-creature bosses (e.g. The Kin). _ACT_BOSS supplies the per-act dps/ramp estimate (not
# harvested), paired with the bestiary's real HP + throttling.
_GENERIC_BOSS = (170, 24, 2)
_ACT_BOSS = {1: (24, 2), 2: (30, 2), 3: (36, 3)}  # (dps, str_ramp) estimate for the act's boss
_BIG_HIT_DAMAGE = 12  # "real hit" threshold for the first-big-hit draft switch (owner)
# Uncatalogued ancient boons compete at their generic-heuristic value clamped to this
# (catalog scale: relic ~ 6; the raw heuristic runs far hotter and must not hijack)
_UNKNOWN_BOON_CAP = 5.0
# Doll Room dolls (owner mechanics 2026-07-24, event-heuristic scale relic ~ 6):
# Daughter of the Wind = 1 Block whenever you play an Attack (scales with cheap
# attacks; pairs with Juggernaut) — base value assumes a middling deck, deck-fit
# adds +2.0. Mr. Struggles = end-of-turn AoE damage equal to the turn number
# (slow, consistent — the safe generic). Bing Bong = permanently-added cards
# arrive doubled — hardest to use, occasionally right, usually the prune target.
_DOLL_VALUES = {
    "Daughter of the Wind": 5.0,
    "Mr. Struggles": 5.5,
    "Bing Bong": 3.0,
}
# Act-1 region by boss (bosses are region-exclusive; co-occurrence clustering over 451
# logged runs split the enemy pools cleanly, 2026-07-17). Owner + community read:
# damage drafts play in the Overgrowth, defense/scaling in the Underdocks — and the
# 07-14 damage-first rework flipped our arrival rates (Overgrowth 72→90%, Underdocks
# 87→77%). The boss name is known from floor 1 (map cache), so drafting can condition.
_UNDERDOCKS_BOSSES = ("LAGAVULIN", "SOUL FYSH", "WATERFALL")
_OVERGROWTH_BOSSES = ("CEREMONIAL", "KIN", "VANTOM")

# Boss-specific draft premiums (owner 2026-07-17 — the FIRST boss-conditional drafting
# rule). Keyed by substring of the cached act-boss name; values are per-INSTANCE
# thresholds and bonuses. Lagavulin Matriarch: her Strategic cycle stacks -2 Str/-2 Dex
# on the player every 4 turns — a tax on instances, not totals. Forensics over the 4
# clean-build fights: a deck of 8-damage hits went 19 rounds and got zeroed at -8/-8;
# the one deck with 15/17-damage hits killed her before the second debuff even landed.
# Big blocks matter the same way (four 5-block Defends at -4 Dex block 4 total).
# Extensible: Colossus x Vulnerable and Dark Shackles multi-attack notes are filed as
# future entries.
_BOSS_DRAFT_RULES: dict[str, dict] = {
    # power_bonus (owner): her 3-turn sleep window is free setup time — Powers
    # (Rupture, Juggernaut...) get their cost amortized before she even wakes,
    # and even won fights run 7+ rounds, so the payoff horizon is guaranteed.
    # card_bonus: owner-named tech for this boss (A/B #4: Primal Force converts a chip
    # deck's 8s into 16-damage Giant Rocks — mass threshold-crossing; the sim already
    # models primal_active in-fight).
    "LAGAVULIN": {"min_hit": 12, "hit_bonus": 2.5, "min_block": 9, "block_bonus": 2.0,
                  "power_bonus": 1.5, "card_bonus": {"PRIMAL_FORCE": 2.5}},
    # Vantom (owner theory, forensics-confirmed on the 4 clean-build fights): Slippery 9
    # ate FIVE rounds of single-hit attacks (173→165 hp) in decks with zero multi-hits,
    # while his rigid cycle (small → x2 → 26/28/30+StatusCard → Empower) landed the big
    # hit on zero block every time (largest block instance in all four decks: 5).
    # Opposite attack profile from the Matriarch — which is why the table is boss-keyed.
    "VANTOM": {"min_block": 9, "block_bonus": 2.0, "min_hits": 2, "multihit_bonus": 2.0},
    # Knowledge Demon (f33 recheck 2026-07-18): the heal-race plays him RIGHT (33/turn
    # in one loss, +26 net through his heal) — the deaths were entries at 52-56 HP vs
    # 379 HP + the Disintegration clock (6→13→21/turn), which the generic Act-2 boss
    # dps estimate can't see. rest_loss_bonus lifts the pre-boss rest gate's demand.
    "KNOWLEDGE": {"rest_loss_bonus": 15.0},
    # Waterfall Giant (owner-confirmed 2026-07-18): dying, he ALWAYS erupts for his
    # Steam stack 1-2 turns later — telegraphed DeathBlow, blockable, surviving = the
    # win. The in-fight turn is priced by the existing DeathBlow-intent lane; the
    # levers are big block instances to absorb ~40 and entry HP to survive the ride
    # (both f17 deaths: all-5-block decks, killed him naked at ≤10 HP).
    "WATERFALL": {"min_block": 9, "block_bonus": 2.0, "rest_loss_bonus": 10.0},
    # Kaiser Crab (forensics 2026-07-18, 4 f33 deaths): Rocket's escalating 27/33/49
    # nukes landed on 0 block every time (all-small-block decks at f33), entries at
    # 54-65 HP all died. Big blocks at draft + a healthier entry; the focus-Rocket
    # targeting fix lives in combat.py's kill-priority lane.
    "KAISER": {"min_block": 9, "block_bonus": 2.0, "rest_loss_bonus": 10.0},
    # Soul Fysh (forensics 2026-07-18): Beckon-flood action tax + periodic Intangible
    # turns (now modeled in the sim) + escalating 24-hit turns on small blocks. Big
    # blocks premiumed; the Intangible/Beckon play fixes live in combat.py.
    # tag_bonus (owner, A/B #5): exhaust-enabler cards can DELETE his Beckons from
    # the deck — a small premium, especially with targeted control (True Grit+).
    "SOUL FYSH": {"min_block": 9, "block_bonus": 2.0,
                  "tag_bonus": {"exhaust_enabler": 1.5}},
    # The Kin (forensics 2026-07-18, ~5 lifetime): 2 Followers + a 190-HP Priest =
    # 307 aggregate HP with permanent Frail/Weak cycling. AoE is the axis (the one
    # deck with Conflagration cleared the Followers by r5 and nearly won from a
    # 52hp entry); entries at 38/52 both died — the fight costs ~55.
    "THE KIN": {"aoe_bonus": 2.0, "rest_loss_bonus": 10.0},
    # The Insatiable (3 lifetime; A/B #3's boss): pure escalating attrition — Empower
    # cycle with 6-status-card pollution, 8x2 → 28 → 12x2 → 30 output onto our small
    # blocks. The PROVEN human answer (A/B #3 win from a 51hp entry) was a Barricade
    # block engine banking 93 — so Barricade is named tech, big blocks premiumed,
    # and the rest gate demands a healthier entry (61 and 49 both died).
    "INSATIABLE": {"min_block": 9, "block_bonus": 2.0, "rest_loss_bonus": 10.0,
                   "card_bonus": {"BARRICADE": 2.5}},
}


def _boss_draft_rule(boss_name: str | None) -> dict | None:
    up = (boss_name or "").upper()
    for key, rule in _BOSS_DRAFT_RULES.items():
        if key in up:
            return rule
    return None


def _act1_region(boss_name: str | None) -> str | None:
    up = (boss_name or "").upper()
    if any(b in up for b in _UNDERDOCKS_BOSSES):
        return "underdocks"
    if any(b in up for b in _OVERGROWTH_BOSSES):
        return "overgrowth"
    return None
# Cards that WANT to be exhausted (owner 2026-07-14). Two families, one text rule —
# class-agnostic by design, so any future card with an on-exhaust payoff is covered:
#   * replay-from-exhaust: Howl from Beyond, Bombardment ("...if this is in your Exhaust
#     Pile, play it") — exhausting turns it into a free recurring attack;
#   * on-exhaust rider: Drum of Battle ("When this card is Exhausted, gain [E][E]") —
#     the payoff only fires BY exhausting it (and beats the draw it otherwise gives).
# (Silent's Sly — "played free when discarded" — is the same idea on the DISCARD axis;
# filed for the Silent pass, it needs discard-priority handling, not exhaust.)
_WANTS_EXHAUST_RE = re.compile(
    r"in your Exhaust Pile, play it|When this card is Exhausted", re.IGNORECASE)


class StandardRouter:
    def __init__(
        self,
        config: PolicyConfig | None = None,
        priors: CardPriors | None = None,
        combat_stats: CombatStats | None = None,
        shop_stats: ShopStats | None = None,
        event_stats: EventStats | None = None,
        bestiary: dict | None = None,
        enemy_dps: dict | None = None,
        draft_tags: dict | None = None,
        ancient_boons: dict | None = None,
    ):
        self.config = config or load_policy_config()
        self.priors = priors if priors is not None else CardPriors.load()
        self.combat_stats = combat_stats if combat_stats is not None else CombatStats.load()
        self.shop_stats = shop_stats if shop_stats is not None else ShopStats.load()
        self.event_stats = event_stats if event_stats is not None else EventStats.load()
        self.card_effects = load_card_descriptions()  # id|upgrade -> text, for §5-C deck pricing
        # enemy name -> HP + status text, for per-boss/elite estimates (injectable for tests)
        self.bestiary = bestiary if bestiary is not None else load_bestiary()
        # realized per-enemy dps (calibration 2026-07-25: the per-act priors ran ~2x
        # hot as sustained averages — Soul Fysh realized 8.4 vs the modeled 25)
        self.enemy_dps = enemy_dps if enemy_dps is not None else load_enemy_dps()
        # card-pass step 2: deck-context provides/needs table (injectable for tests)
        self.draft_tags = draft_tags if draft_tags is not None else load_draft_tags()
        # Ancients pass (§8.5.5a): boon catalog for is_ancient events + owned-boon
        # tag context in drafting (injectable for tests)
        self.ancient_boons = (
            ancient_boons if ancient_boons is not None else load_ancient_boons()
        )
        # events pass (EVENTS_PASS.md): option-title catalog for non-ancient events
        self.event_choices = load_event_choices()
        self._fallback = TrivialRouter()

    def decide(self, state: GameState, ctx: LoopContext) -> Decision | Wait:
        # Card-select retry counters live in screen_mem keyed by prompt, and were never
        # cleared when a screen RESOLVED — so they accumulated across the whole run: an
        # early Toolbox screen burned the budget, and the next "Choose a card." (Discovery!)
        # got one attempt before cancelling, silently forfeiting the card every time
        # (owner-caught 2026-07-14: Discovery failed 3/3 — a 0-cost exhaust for nothing).
        # Leaving the screen is the resolve signal: drop the counters here.
        if state.state_type != "card_select":
            for k in [k for k in ctx.screen_mem if k.startswith("cardsel:")]:
                ctx.screen_mem.pop(k, None)
        handler = getattr(self, f"_{state.state_type}", None)
        if handler is not None:
            if state.state_type == "elite" and getattr(state, "battle", None):
                seen = ctx.screen_mem.setdefault("elites_seen", set())
                for e in state.battle.enemies or []:
                    if e.name:
                        seen.add(e.name.upper())
            decision = handler(state, ctx)
            if state.state_type == "event":
                self._note_enchant_intent(state, decision, ctx)
            return decision
        return self._fallback.decide(state, ctx)

    # The mod's enchant target screen says only "Choose a card to Enchant." — the
    # enchant NAME lives one screen earlier, on the chosen event option (live
    # 2026-07-24: Slither landed on a 1-cost Taunt with Bash in the pool, because
    # the 'slither'-in-prompt rule could never fire on the generic prompt). Remember
    # the kind at event-choice time; _pick_target reads it on the next enchant
    # screen. Set on EVERY event choice (None when no enchant word) so a stale
    # intent from a declined event self-heals.
    _ENCHANT_KINDS = ("slither", "sharp", "nimble", "swift", "sown", "spiral")

    def _note_enchant_intent(self, state, decision, ctx: LoopContext) -> None:
        if not isinstance(decision, Decision) or not isinstance(
            decision.action, act.ChooseEventOption
        ):
            return
        ev = getattr(state, "event", None)
        opt = next((o for o in (ev.options if ev else []) or []
                    if o.index == decision.action.index), None)
        if opt is None:
            return
        text = f"{opt.title or ''} {opt.description or ''}".lower()
        ctx.screen_mem["pending_enchant"] = next(
            (k for k in self._ENCHANT_KINDS if k in text), None
        )

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

        # One-potion-per-round bookkeeping is shared with _combat_potion: the planner must not
        # re-drink a slot, and a plan that drinks records the slot the same way. state.battle
        # is None while combat is still loading (live-only transitional state — crashed batch
        # bpnsoql1j run 1); plan_combat_turn Waits on it, the bookkeeping must tolerate it.
        round_ = (state.battle.round if state.battle is not None
                  and state.battle.round is not None else -1)
        pused = ctx.screen_mem.get("potions_used")
        if not isinstance(pused, dict) or pused.get("round") != round_:
            pused = {"round": round_, "slots": []}
            ctx.screen_mem["potions_used"] = pused
        plan = plan_combat_turn(state, self.config.combat,
                                used_potion_slots=tuple(pused["slots"]),
                                hold_aoe_potions=self._aoe_hold(state, ctx))
        if (isinstance(plan, Decision) and isinstance(plan.action, act.UsePotion)
                and plan.action.slot not in pused["slots"]):
            pused["slots"].append(plan.action.slot)
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
        if any("NO_DRAW" in (st_.id or "").upper() for st_ in (player.status or [])):
            return None  # Battle Trance rider: the desperation draw would draw nothing
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
        # Under a 1-card cap (Ringing) the draw IS the whole turn — the drawn cards can never
        # be played, so digging is pure waste (f17 Beast death 2026-07-09: Battle Trance burned
        # the capped play; the drawn Flame Barrier sat unplayable). Let the planner's capped
        # search make the one allowed play count instead.
        for s in player.status:
            if (m := re.search(r"only play (\d+) card", s.description or "", re.IGNORECASE)) \
                    and int(m.group(1)) <= 1:
                return None
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

    @staticmethod
    def _aoe_hold(state, ctx: LoopContext) -> bool:
        """AoE damage potions held in acts 1-2 NORMAL fights while their premium
        targets are ahead: the Kin (spottable act-1 boss), Phrog Parasite p2,
        Phantasmal Gardeners, act-2 Decimillipede (owner 2026-07-29; Knight Gang
        excluded -- too much HP to dent). An elite already seen won't recur until
        3 elites are fought, so seen = the hold releases. Hail-mary overrides."""
        if state.state_type != "monster":
            return False
        cur_act = state.run.act if state.run else 1
        if cur_act > 2:
            return False
        seen = ctx.screen_mem.get("elites_seen") or set()
        swarms = {1: ("PHROG", "GARDENER"), 2: ("DECIMILLIPEDE",)}.get(cur_act, ())
        kin_boss = "KIN" in (ctx.screen_mem.get("act_boss_name") or "").upper()
        return ((cur_act == 1 and kin_boss)
                or any(not any(sw in name for name in seen) for sw in swarms))

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
            # Targeting is enforced HERE, off the potion's own target_type, not the caller's
            # category guess: a hail-mary Beetle Juice (enemy-debuff, category "other") was
            # drunk untargeted -> API error -> died with it in the belt (owner-caught, batch
            # b8oazdsui run 2 vs Kaiser Crab).
            if target is None and "enemy" in (potion.target_type or "").lower():
                target = biggest_threat()
            if potion.slot not in used_slots:
                used_slots.append(potion.slot)
            return Decision(action=act.UsePotion(slot=potion.slot, target=target), rationale=why)

        def biggest_threat() -> str | None:
            alive = [e for e in state.battle.enemies if e.hp > 0]
            return max(alive, key=lambda e: e.hp).entity_id if alive else None

        hp_pct = player.hp / max(1, player.max_hp)
        # Delicate Frond (owner A/B #4 + live 2026-07-22): empty slots REFILL at every
        # combat start, so the whole hoard-for-elites taxonomy inverts — spend potions
        # every fight ("just played most of my potions each fight" — the owner's Act-3
        # bonanza). Every fight becomes deploy-worthy and heals become topping-off.
        frond = any(
            "DELICATE" in f"{r.id or ''} {r.name or ''}".upper()
            and "FROND" in f"{r.id or ''} {r.name or ''}".upper()
            for r in (player.relics or [])
        )
        # Full belt raises the spend prior (owner, Ovicopter A/B 2026-07-25: "we're at
        # 3 of 3 potions, so my prior for playing one of them is higher" — and the
        # post-fight Explosive Ampule proved the overflow). A raised prior, not a
        # mandate: the value gates below still decide, same as the owner held both
        # budgeted potions once the exact math cleared without them.
        belt_full = (w.full_belt_deploys
                     and len(player.potions or []) >= (player.max_potion_slots or 3))
        dangerous = (state.state_type in ("elite", "boss")
                     and w.drink_in_elite_or_boss) or frond or belt_full
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
            # Foul-class guard (owner-caught 2026-07-20: hail-mary at 9 HP drank Foul
            # Potion, "Deal 10 damage to EVERYONE" — the drinker included — a certain
            # suicide traded for a merely-PROJECTED death; projections carry ~15%
            # error, so that margin is real). Never fall back to a self-lethal potion.
            def _self_lethal(p: Potion) -> bool:
                if re.search(r"\bEVERYONE\b", p.description or "", re.IGNORECASE):
                    return (parse_card_description(p.description).total_damage
                            >= player.hp)
                return False

            potion = first("block", "heal", "aoe_damage", "damage") or next(
                (p for p in available if not _self_lethal(p)), None)
            if potion is not None:
                tgt = (biggest_threat()
                       if cat[potion.slot] in ("damage", "aoe_damage") else None)
                return drink(
                    potion, tgt,
                    f"hail mary: drink {potion.name} "
                    f"(proj loss {proj_loss:.0f} >= {player.hp} HP)",
                )

        # 1b. Petrified Toad (owner A/B #5): the Rock potion (deal ~15) REGENERATES at
        #     every combat start — hoarding wastes the relic AND clogs the slot that
        #     would hold tomorrow's Rock. Throw it freely: finisher on sight, or at
        #     the biggest threat once the fight matures. (After hail-mary: a
        #     lifesaving block/heal still outranks a throw.)
        if any("PETRIFIED" in f"{r.id or ''} {r.name or ''}".upper()
               for r in (player.relics or [])):
            rock = next((p for p in available
                         if "ROCK" in f"{p.id or ''} {p.name or ''}".upper()), None)
            if rock is not None:
                rock_dmg = parse_card_description(rock.description).total_damage or 15
                finish = next((e for e in state.battle.enemies
                               if 0 < e.hp <= rock_dmg), None)
                if finish is not None:
                    return drink(rock, finish.entity_id,
                                 f"throw {rock.name} (finishes {finish.name})")
                if round_ >= 3:
                    return drink(rock, biggest_threat(),
                                 f"throw {rock.name} (free the Toad slot)")

        # 2. Fruit Juice (+max HP): pure upside, drink on sight.
        if juice := first("fruit_juice"):
            return drink(juice, None, f"drink {juice.name} (+max HP, free value)")

        # 3. Heal / Blood Potion when hurt. (Frond: heals are free refills — top off.)
        heal_bar = max(w.heal_below_pct, 0.8) if frond else w.heal_below_pct
        if hp_pct < heal_bar and (healp := first("heal")):
            return drink(healp, None, f"drink {healp.name} to heal at {hp_pct:.0%} HP")

        # 4a. Card-generating potions (Skill/Attack/Power/Colorless/Orobic): drop
        #     immediately at a BOSS or ELITE start (owner 2026-07-29: "obvious turn 1
        #     plays") — the generated cards compound over the fight's length, and held
        #     ones historically died in the belt or fired as pointless hail-maries
        #     (owner 2026-07-09). Window is two rounds so a buff (4b) also lands.
        if ((state.state_type in ("boss", "elite") or frond) and round_ <= 2
                and (cg := first("card_gen"))):
            return drink(cg, None,
                         f"drink {cg.name} ({state.state_type} start: bank cards early)")

        # 4. Proactive at an elite/boss start: deploy long-term buffs/debuffs early (the
        #    bot struggles with these fights, so bank the value rather than hoard it).
        if dangerous and round_ <= 1 and (buff := first("buff", "debuff")):
            tgt = biggest_threat() if cat[buff.slot] == "debuff" else None
            return drink(buff, tgt, f"drink {buff.name} (deploy at {state.state_type} start)")

        # 4a-2. Cost-zero potions (Touch of Insanity): deploy early at a boss,
        #     but ONLY when a worthy target (cost >= 2) is in hand — the owner nuance:
        #     turn 1 full of cheap cards -> WAIT for the turn the 3-cost shows up.
        if dangerous and round_ <= 4 and (cz := first("cost_zero")):
            hand_costs = [int(c.cost) for c in (player.hand or [])
                          if c.cost and str(c.cost).lstrip("-").isdigit()]
            if hand_costs and max(hand_costs) >= 2:
                ctx.screen_mem["pending_enchant"] = "cost_zero"  # target screen: max cost
                return drink(cz, None,
                             f"drink {cz.name} (cost-zero the {max(hand_costs)}-cost)")

        # 4b. Value/tempo potions (energy / draw): spend them early in a big fight so the extra
        #     energy + cards convert to more block and damage. Owner B04BGZEDRN: the bot hoarded
        #     Cure All (gain energy, draw 2) through the 126-HP Ovicopter and threw it away in a
        #     hail-mary at the next floor — the human spent it to power through and exited +30 HP.
        if vp := first("value"):
            enemy_hp = sum(e.hp for e in state.battle.enemies if e.hp > 0)
            if ((frond or enemy_hp >= w.value_drink_enemy_hp_min)
                    and round_ <= w.value_drink_by_round):
                return drink(
                    vp, None, f"drink {vp.name} (energy/draw for a {enemy_hp}-HP fight)"
                )

        # 5. Reactive, once the planned line has spent its cards (end of turn):
        if plan_ends_turn:
            # Swift-class draw potions (owner provisional 2026-07-29; full treatment
            # is the multiturn planner): out of playable cards with energy unspent
            # at a big fight or on a full belt -> the draw converts dead energy
            # into plays THIS turn.
            energy_left = player.energy or 0
            no_draw = any("NO_DRAW" in (st_.id or "").upper()
                          for st_ in (player.status or []))
            if (energy_left >= 1 and not no_draw and (dangerous or belt_full)
                    and (dp := first("draw"))):
                return drink(dp, None,
                             f"drink {dp.name} (out of cards, {energy_left} energy unspent)")
            if proj_loss >= w.block_reactive_min and (blockp := first("block")):
                return drink(
                    blockp, None, f"drink {blockp.name} end-of-turn (unblocked {proj_loss:.0f})"
                )
            # AoE-damage hold (owner 2026-07-29): Explosive-class potions are
            # PREMIUM against the multi-body fights ahead -- the Kin (spottable as
            # the act-1 boss), Phrog Parasite phase 2, Phantasmal Gardeners, act-2
            # Decimillipede (Knight Gang excluded: too much HP to dent). In acts
            # 1-2 NORMAL fights, hold the AoE while any of those is still ahead;
            # an elite already seen won't recur until 3 elites are fought (owner
            # recurrence rule), so seen = the hold releases. Hail-mary overrides.
            dmgp = first("damage") or (None if self._aoe_hold(state, ctx)
                                       else first("aoe_damage"))
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
        # Card-generating potions (Skill/Attack/Power/Colorless Potion: "choose a card, add it
        # to your hand"). Their text parses to no effect -> they fell to "other" and only ever
        # fired as the hail-mary fallback, way too late value-wise (owner 2026-07-09): the
        # earlier the card arrives, the longer it works. Deployed at boss start (rule 4a).
        if any(k in nid for k in ("SKILL", "ATTACK", "COLORLESS", "POWER POTION",
                                  "OROBIC")):
            # Orobic Acid: 3 random cards, free this turn — a turn-1 tempo bomb
            # (owner 2026-07-29: obvious turn-1 play at bosses/elites)
            return "card_gen"
        # "[Selected] card costs 0 for the rest of this fight" (owner 2026-07-29,
        # Touch of Insanity; matched by TEXT so the exact name doesn't matter):
        # a targeted cost-zero is a per-fight engine — deploy early in big fights,
        # but only when a WORTHY target is in hand (see the boss-deploy lane).
        if re.search(r"costs? 0.*rest of (this|the) (fight|combat)",
                     potion.description or "", re.IGNORECASE | re.DOTALL):
            return "cost_zero"
        fx = parse_card_description(potion.description)
        if fx.heal > 0:
            return "heal"
        if fx.block > 0:
            return "block"
        if fx.total_damage > 0:
            return "aoe_damage" if fx.aoe else "damage"
        if fx.vulnerable > 0 or fx.weak > 0 or any(
            k in nid for k in ("VULNER", "WEAK", "BINDING", "SHACKL")
        ) or re.search(r"deal \d+% less", potion.description or "", re.IGNORECASE):
            # the %-less phrasing: Beetle Juice "Enemy's attacks deal 30% less damage" — a
            # Weak-class debuff the Apply-N regexes miss (it sat as "other" until hail-mary)
            return "debuff"
        if fx.strength > 0 or any(
            k in nid for k in ("STRENGTH", "DEXTER", "FOCUS", "POWER", "BLESSING", "FYSH",
                               "FORGE", "THORNS")
        ) or re.search(r"gain \d+ (thorns|replay)", potion.description or "",
                       re.IGNORECASE):
            # THORNS/REPLAY by TEXT (names lie): Liquid Bronze "Gain 3 Thorns" sat
            # until hail-mary at a live KD fight; Soldier's Stew "All cards containing
            # Strike gain 1 Replay this combat" ditto at a live Aeonglass (owner
            # 2026-07-29: both are obvious turn-1 plays at bosses/elites).
            return "buff"
        if (fx.draw > 0 and fx.energy_gain == 0
                and "energy" not in (potion.description or "").lower()):
            # Swift-class PURE draw: its moment is OUT-OF-CARDS-WITH-ENERGY, not
            # turn 1 (owner provisional rule 2026-07-29; full treatment = §5-C).
            # The energy-text guard keeps Cure-All-likes ("Gain energy. Draw 2",
            # unnumbered energy parses 0) in the value bucket.
            return "draw"
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

        def setting_up(e) -> bool:
            # zero attack NOW but a buff/debuff/summon intent = danger next turn: worth killing
            return any((i.type or "").lower() in ("buff", "debuff", "summon", "carddebuff")
                       for i in e.intents)

        if cat == "aoe_damage":
            prevented = sum(threat(e) for e in kills)
            # Board-clear at ZERO threat wastes a potion that persists across fights (owner
            # 2026-07-09): hold unless something is actually incoming or setting up.
            worth = (len(kills) == len(alive)
                     and (prevented > 0 or any(setting_up(e) for e in kills))
                     ) or prevented >= w.damage_potion_prevents_min
            return None if worth else False
        if len(alive) == 1:
            # ends the fight — but at ZERO threat with no setup brewing, hold the potion for a
            # fight that needs it (it persists across combats; owner 2026-07-09)
            worth = [e for e in kills if threat(e) > 0 or setting_up(e)]
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
        # Phantom re-present guard (audit 2026-07-25): right after a travel is
        # ACCEPTED, the mod re-renders the map briefly with the consumed option
        # removed; deciding on that transient submitted a SECOND travel — "ok"-ed
        # but ignored by the game today (a swerve risk if it ever honors it), and
        # it poisoned route-intent analysis with best-of-the-leftovers values
        # (f42-44 forensics: Unknown 44.3 accepted, then 'Elite -151.5' phantoms).
        # Hold further map decisions from the SAME node, with a tick budget so a
        # genuinely failed submission still recovers.
        pos = state.map.current_position
        poskey = (state.run.floor if state.run else None,
                  (pos.col, pos.row) if pos else None)
        hold = ctx.screen_mem.get("map_travel_hold")
        if isinstance(hold, dict) and hold.get("key") == poskey:
            if hold.get("ticks", 0) < 8:
                hold["ticks"] = hold.get("ticks", 0) + 1
                return Wait(reason="travel already chosen from this node; holding")
            ctx.screen_mem.pop("map_travel_hold", None)  # budget spent: re-decide
        player = state.player
        hp_missing_pct = 0.0
        gold = 0
        if player is not None:
            hp_missing_pct = 100.0 * (1.0 - player.hp / max(1, player.max_hp))
            gold = player.gold
        # Sword of Stone one-from-Jade (owner 2026-07-29): at counter 4 the next
        # elite also completes the +3-Str transform -- nudge winnable elites.
        sword_bonus = w.sword_completion_bonus if any(
            "SWORD OF STONE" in f"{r.id or ''} {r.name or ''}".upper()
            and (r.counter or 0) == 4
            for r in ((player.relics if player else None) or [])
        ) else 0.0
        # Planisphere: +5 HP on entering a '?' room (owner nuance check 2026-07-29).
        # Margins only — but the DP's death-floor pockets flip on margins, and a
        # '?'-dense route with it held is a real trickle of sustain.
        held_relics = [f"{r.id or ''} {r.name or ''}".upper()
                       for r in ((player.relics if player else None) or [])]
        unknown_heal = 5.0 if any("PLANISPHERE" in n for n in held_relics) else 0.0
        # Meal Ticket: +15 HP on entering a shop (owner 2026-07-29) — same seam.
        shop_heal = 15.0 if any("MEAL_TICKET" in n or "MEAL TICKET" in n
                                for n in held_relics) else 0.0

        next_row = min(o.row for o in opts)

        def type_score(node_type: str | None, row: int | None = None) -> float:
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
                # Value a shop by the gold we'll HOLD on arrival, not today's wallet —
                # fights along the way keep paying. This is the owner's practice of
                # looping a LATE shop into the act (A/B #3: 740g -> two Act-3 sprees
                # -> 8 relics); with current-gold scoring, early and late shops tied.
                rows_ahead = max(0, (row - next_row)) if row is not None else 0
                projected = gold + w.shop_gold_income_per_row * rows_ahead
                base += w.shop_bonus_per_100_gold * (projected / 100.0)
            return base

        # Act-level path value: DP over the full map DAG so options are judged by the best
        # complete route to the boss, not just their own node type (1-ply lookahead committed
        # us to forced-elite lanes floors in advance). When the bot has HP data (combat_stats)
        # the DP also projects HP along each route (§8.2): routes it can't survive are penalised,
        # and a *survivable* elite is rewarded for its relic (deck power, the binding constraint),
        # flipping the flat elite-avoidance into elite-chasing whenever the HP is there to spend.
        node_by_pos = {(n.col, n.row): n for n in state.map.nodes}
        hp_aware = player is not None and self.combat_stats is not None
        cur_hp = float(player.hp) if player else 0.0
        max_hp = float(player.max_hp) if player else 1.0
        death_floor = max_hp * w.survival_floor_hp_pct
        EARLY_ROWS = 3  # first 3 rows of an act = the easy early normals (cf. build_combat_stats)
        _loss_default = {"monster_early": 5.0, "monster": 18.0, "elite": 32.0, "boss": 42.0}

        # §5-C capability gate: chase an elite only if the deck can actually *win* the elites of
        # this act (not merely survive — death_floor still handles survival). Judged at full HP,
        # so it's a pure deck-strength read; a starter-heavy deck fails it and stays elite-neutral.
        # 2026-07-09 (3 elite deaths in one batch, Terror Eel x2 + Phrog): the old generic
        # 90-HP/no-mechanics profile flattered every real elite (Terror Eel is 140 HP; Hardened
        # Shell / Skittish / Shriek all detected from the bestiary now). The node's elite is a
        # random draw from the act's pool, so gate on winning >= elite_gate_pool_win_frac of the
        # pool's real members. Known limitation: swarm elites (Phantasmal Gardeners) harvest as
        # one small body and fall below the pool's HP floor — the swarm is under-represented.
        can_win_elite = False
        gate_ms: float | None = None
        est_elite_loss: float | None = None
        est_boss_loss: float | None = None
        if hp_aware and player is not None and player.deck:
            cur_act = state.run.act if state.run else 1
            ehp, edps, eramp = _GENERIC_ELITE.get(cur_act, _GENERIC_ELITE[1])
            deck_out = deck_output(player.deck, descriptions=self.card_effects)
            floor_hp = max_hp * w.elite_gate_min_end_hp_pct
            pool = [
                (name, entry) for name, entry in self.bestiary.items()
                if "elite" in (entry.get("roles") or []) and cur_act in (entry.get("acts") or [])
                # drop minion-pollution entries UNLESS a composition rebuilds them as the real
                # multi-body fight (Gardener 31 HP alone is pollution; 3x with Skittish is real)
                and (((entry.get("hp") or [0, 0])[1] or 0) >= 50
                     or any(k in name.upper() for k in _ELITE_COMPOSITIONS))
            ]
            if pool:
                members_by_name = {
                    name: elite_fight_members(name, entry, self.bestiary,
                                              dps=realized_dps(self.enemy_dps, name, edps),
                                              str_ramp=eramp)
                    for name, entry in pool
                }
                if self.config.map.use_rollout_gate:
                    # P2a: calibrated Monte-Carlo distributions, tail-aware
                    t0 = time.perf_counter()
                    rolls = [
                        rollout_fight(player.deck, members, int(max_hp), int(max_hp),
                                      card_effects=self.card_effects,
                                      potions=player.potions, relics=player.relics)
                        for members in members_by_name.values()
                    ]
                    gate_ms = (time.perf_counter() - t0) * 1000.0
                    won_n = sum(
                        1 for r in rolls
                        if r.win_rate >= w.rollout_gate_win_rate
                        and r.p25_end_hp >= floor_hp
                    )
                    can_win_elite = won_n >= len(pool) * w.elite_gate_pool_win_frac
                    losses = sorted(max_hp - r.exp_end_hp for r in rolls)
                    est_elite_loss = losses[len(losses) // 2]
                else:
                    outcomes = [estimate_fight(int(max_hp), deck_out, members)
                                for members in members_by_name.values()]
                    won = [o for o in outcomes if o.win and o.exp_end_hp >= floor_hp]
                    can_win_elite = len(won) >= len(pool) * w.elite_gate_pool_win_frac
                    # median projected HP cost of THIS deck vs the act's real pool
                    losses = sorted((max_hp - o.exp_end_hp) if o.win else max_hp
                                    for o in outcomes)
                    est_elite_loss = losses[len(losses) // 2]
            else:  # bestiary empty for this act: fall back to the generic profile
                outcome = estimate_fight(
                    int(max_hp), deck_out, [FightEnemy(hp=ehp, dps=edps, str_ramp=eramp)]
                )
                can_win_elite = outcome.win and outcome.exp_end_hp >= floor_hp
                est_elite_loss = (max_hp - outcome.exp_end_hp) if outcome.win else max_hp
            boss_members = self._upcoming_boss(ctx, cur_act)
            if boss_members:
                bo = estimate_fight(int(max_hp), deck_out, boss_members)
                est_boss_loss = (max_hp - bo.exp_end_hp) if bo.win else max_hp

        def fight_loss(key: str) -> float:
            # Owner 2026-07-13 (route-then-swerve forensics): the p75-of-own-history
            # projection is poisoned by dying runs — a full act projected 120+ HP of
            # loss, so every path saturated at the death penalty and elite lanes
            # flipped on HP noise. Elite/boss nodes now project the CURRENT deck's
            # §5-C estimate ("can this deck beat it" made literal); monsters use the
            # mean (the p75 tail double-counts the same disasters).
            if key == "elite" and est_elite_loss is not None:
                return float(est_elite_loss)
            if key == "boss" and est_boss_loss is not None:
                return float(est_boss_loss)
            est = (self.combat_stats.expected_loss(key, stat="mean")
                   if self.combat_stats else None)
            return float(est) if est is not None else _loss_default[key]

        def project(node_type: str | None, row: int, hp: float) -> tuple[float, float]:
            """Project HP through one node -> (hp_after, score_adjustment). Combat subtracts the
            bot's own p75 loss for that fight type; a route that drops to/below the death floor is
            penalised; a survivable elite earns its relic bonus; a rest heals."""
            t = (node_type or "").lower()
            if t == "monster":
                hp_after = hp - fight_loss("monster_early" if row < EARLY_ROWS else "monster")
            elif t == "elite":
                hp_after = hp - fight_loss("elite")
            elif t == "boss":
                hp_after = hp - fight_loss("boss")
            elif t in ("restsite", "rest_site"):
                return min(max_hp, hp + w.rest_heal_pct * max_hp), 0.0
            elif t == "unknown" and unknown_heal:
                return min(max_hp, hp + unknown_heal), 0.0  # Planisphere trickle
            elif t == "shop" and shop_heal:
                return min(max_hp, hp + shop_heal), 0.0  # Meal Ticket
            else:
                return hp, 0.0
            if hp_after <= death_floor:
                return hp_after, -w.route_death_penalty  # route not survivable as projected
            # An elite the §5-C gate says the deck CANNOT WIN is a projected loss, not a missed
            # relic: price it death-class so the DP refuses lanes that END in forced elites at
            # commit time (batch bn4v9mf75 forensics: every remaining elite death was a forced
            # single-option lane the DP had committed into floors earlier, because the
            # unwinnable elite's only cost was its discounted HP projection). Matches the
            # owner's Phrog steer: "a death trap for a basic-heavy deck at ANY HP."
            if t == "elite" and not can_win_elite:
                return hp_after, -w.route_death_penalty
            # a survivable, winnable elite earns its relic bonus (§5-C gate)
            return hp_after, (w.elite_relic_value + sword_bonus
                              if t == "elite" else 0.0)

        memo: dict[tuple[int, int, int], float] = {}

        def path_value(col: int, row: int, hp: float) -> float:
            key = (col, row, int(hp) // 4)
            if key in memo:
                return memo[key]
            node = node_by_pos.get((col, row))
            if node is None:
                memo[key] = 0.0
                return 0.0
            memo[key] = 0.0  # cycle guard (map is a DAG, but be safe)
            hp_after, adj = project(node.type, row, hp) if hp_aware else (hp, 0.0)
            future = max(
                (path_value(c_col, c_row, hp_after) for c_col, c_row in node.children),
                default=0.0,
            )
            value = type_score(node.type, row) + adj + w.path_step_discount * future
            memo[key] = value
            return value

        # Winged Boots (owner 2026-07-29): with it held the mod offers OFF-PATH nodes
        # as extra next_options — identifiable as options absent from the current
        # node's graph children. Charges are insurance, not path upgrades (live:
        # 2 of 3 burned on marginal jumps), so jump options pay boots_jump_cost;
        # a death-floor dodge to a rest site still clears it easily.
        cur_node = node_by_pos.get((pos.col, pos.row)) if pos else None
        cur_kids = ({tuple(c) for c in cur_node.children} if cur_node else set())

        scored: dict[str, float] = {}
        best = None
        best_score = float("-inf")
        for opt in opts:
            hp_after, adj = project(opt.type, opt.row, cur_hp) if hp_aware else (cur_hp, 0.0)
            future = max(
                (path_value(c.col, c.row, hp_after) for c in opt.leads_to),
                default=0.0,
            )
            if not opt.leads_to and (node := node_by_pos.get((opt.col, opt.row))):
                future = max(
                    (path_value(c_col, c_row, hp_after) for c_col, c_row in node.children),
                    default=0.0,
                )
            score = type_score(opt.type, opt.row) + adj + w.path_step_discount * future
            if cur_kids and (opt.col, opt.row) not in cur_kids:
                score -= w.boots_jump_cost
            scored[f"{opt.index}:{opt.type}"] = round(score, 2)
            if score > best_score:
                best_score, best = score, opt
        assert best is not None
        if gate_ms is not None:
            scored["gate_ms"] = round(gate_ms, 1)  # owner: latency data matters
        if state.map.boss and state.map.boss.name:
            # cache the act's boss name (known after Neow) so post-combat drafting, where the map
            # isn't in state, can price cards against the *real* boss (§5-C / ENEMY_PASS).
            ctx.screen_mem["act_boss_name"] = state.map.boss.name
        boss_row = state.map.boss.row if state.map.boss else None
        if boss_row is not None and best.row == boss_row - 1:
            ctx.screen_mem["pre_boss"] = True  # arriving on the last row before the boss
        else:
            ctx.screen_mem.pop("pre_boss", None)
        ctx.screen_mem["map_travel_hold"] = {"key": poskey, "ticks": 0}
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
            # An event option that IS a fight carries an implicit HP cost the text
            # never states (Lantern Key death 2026-07-22: 'Fight to obtain the Key'
            # read as a free relic at 25/85 HP — chose combat at 29% over 100 gold).
            # Price it as an expected monster loss so the hp-cost gates apply.
            if hp_cost == 0 and re.search(r"\bfight\b", text, re.IGNORECASE):
                est_fight = (self.combat_stats.expected_loss("monster", stat="mean")
                             if self.combat_stats else None)
                hp_cost = int(est_fight if est_fight is not None else 15)
            if hp_cost:
                after_pct = (hp - hp_cost) / max(1, max_hp)
                # Refuse if already too hurt to pay, or if paying drops us into the danger
                # zone — a choice can be great on Spirebird yet suicidal in the current state.
                if hp_pct < w.hp_cost_refuse_below or after_pct < w.min_hp_pct_after_cost:
                    continue
            heur = self._event_option_value(o, hp, max_hp)
            vs = self.event_stats.option_vs(eid, o.title) if self.event_stats else None
            scored.append((o, heur, vs))

        # Ancients pass (§8.5.5a): boon offers get catalog values instead of the generic
        # gains/costs heuristic, which is actively baited by boon text (A/B #3: "Pael's
        # Tooth: REMOVE 5 cards..." earned +5 while the run-winning Legion parsed to ~0).
        # Uncatalogued options (new epochs) stay in the ranking at their heuristic value
        # CLAMPED into catalog scale — raw heuristics run hot (a "+31 Max HP" parse hits
        # 46) and an inflated unknown must not hijack the screen (live 2026-07-16: the
        # new-epoch Silken Tress fell the whole screen back to the generic path, which
        # took Scroll Boxes at a baited 7.0 over Lava Rock).
        if ev.is_ancient and self.ancient_boons and scored:
            deck = player.deck if (player and player.deck) else []
            known_any = any(self.ancient_boons.get(o.title or "") for o, _h, _v in scored)
            if known_any:
                vals = {}
                for o, heur, _vs in scored:
                    entry = self.ancient_boons.get(o.title or "")
                    if entry:
                        vals[o.index] = (float(entry.get("value", 0.0))
                                         + self._boon_deck_fit(entry, deck))
                    else:
                        vals[o.index] = min(heur, _UNKNOWN_BOON_CAP)
                best_o = max(scored, key=lambda s: vals[s[0].index])[0]
                known = bool(self.ancient_boons.get(best_o.title or ""))
                return Decision(
                    action=act.ChooseEventOption(index=best_o.index),
                    rationale=(f"ancient boon: '{best_o.title}' "
                               f"({'catalog' if known else 'unknown, heur-capped'} "
                               f"{vals[best_o.index]:.1f})"),
                    scores={(o.title or "?"): round(vals[o.index], 2)
                            for o, _h, _v in scored},
                )

        # Slippery Bridge gamble (owner mechanics + screenshot 2026-07-22): the
        # sub-screen reads [Overcome] "<Card> is removed from your Deck" /
        # [Hold On] "Lose X HP. The card in the above option is randomized." The
        # sub-screen title COLLIDES with the stage-1 'Overcome' catalog entry, so the
        # bot removed whatever card was shown first. Description-matched rule: junk
        # shown (curse/status/basic) -> accept the removal (free thinning!); keeper or
        # Quest card shown -> pay X and reroll while X is cheap and HP allows.
        removal_o = reroll_o = None
        removed_name = None
        reroll_x = 0
        for o in ev.options or []:
            d_ = o.description or ""
            if m := re.search(r"^(.+?) is removed from your Deck", d_):
                removal_o, removed_name = o, m.group(1).strip()
            elif "card in the above option is randomized" in d_:
                reroll_o = o
                if m2 := re.search(r"Lose (\d+) HP", d_):
                    reroll_x = int(m2.group(1))
        if removal_o is not None and reroll_o is not None and removed_name:
            deck = player.deck if (player and player.deck) else []
            shown = next((c for c in deck
                          if (c.name or "").rstrip("+") == removed_name.rstrip("+")),
                         None)
            is_quest = shown is not None and (shown.type or "") == "Quest"
            junk = False
            if shown is not None and not is_quest:
                cid = (shown.id or "").upper()
                junk = ((shown.type or "") in ("Curse", "Status")
                        or (cid.startswith(("STRIKE_", "DEFEND_"))
                            and not shown.is_upgraded))
            can_pay = hp > reroll_x + 10 and reroll_x <= 7
            if junk or not can_pay:
                why = ("free thinning" if junk
                       else f"X={reroll_x} too steep at {hp} HP")
                return Decision(
                    action=act.ChooseEventOption(index=removal_o.index),
                    rationale=f"bridge: remove {removed_name} ({why})",
                )
            return Decision(
                action=act.ChooseEventOption(index=reroll_o.index),
                rationale=f"bridge: keep {removed_name}, pay {reroll_x} HP to reroll",
            )

        # Doll Room (owner mechanics 2026-07-24): the text parser took 'Pick at
        # Random' every run ("Obtain a random Doll Relic" = free relic 6.0) — and
        # Random is Spirebird's WORST option here (vs 5.8 vs 14.3/22.5). Owner:
        # 'Take Some Time' (5 HP, 1 of 2) is the default because it always lets you
        # prune Bing Bong and assures at least an okay choice; with a real Daughter
        # deck (Juggernaut, or attack-spam) pay the 15 HP to Examine and make sure
        # you get her. Description-matched (stage-1 titles are collision-prone).
        doll_random = doll_pick = None
        doll_pick_n = 0
        for o in unlocked:
            d_ = o.description or ""
            if "random Doll Relic" in d_:
                doll_random = o
            elif m := re.search(r"Choose 1 of (\d+) Doll Relics", d_):
                n = int(m.group(1))
                if n > doll_pick_n:
                    doll_pick, doll_pick_n = o, n
        if doll_random is not None and doll_pick is not None:
            deck = player.deck if (player and player.deck) else []
            fit = self._daughter_deck_fit(deck)
            choose2 = next((o for o in unlocked
                            if "Choose 1 of 2 Doll Relics" in (o.description or "")),
                           None)

            def _payable(cost: int) -> bool:
                return (hp_pct >= w.hp_cost_refuse_below
                        and (hp - cost) / max(1, max_hp) >= w.min_hp_pct_after_cost)

            if doll_pick_n >= 3 and fit and _payable(15):
                pick, why = doll_pick, "Examine (Daughter deck, guarantee her)"
            elif choose2 is not None and _payable(5):
                pick, why = choose2, "Take Some Time (always prunes Bing Bong)"
            else:
                pick, why = doll_random, "too hurt to pay for selection"
            return Decision(
                action=act.ChooseEventOption(index=pick.index),
                rationale=f"doll room: {why}",
            )

        # Doll Room sub-screen: rank the offered dolls with the owner's deck-fit
        # nuance (Spirebird's Daughter 19 > Struggles 16.9 > Bing Bong 11.5 is
        # selection-biased — Daughter is only that good when the deck feeds her).
        doll_opts = [(o, _DOLL_VALUES[o.title or ""]) for o in unlocked
                     if (o.title or "") in _DOLL_VALUES]
        if len(doll_opts) >= 2:
            deck = player.deck if (player and player.deck) else []
            fit = self._daughter_deck_fit(deck)
            vals = {o.index: v + (2.0 if fit and "Daughter" in (o.title or "") else 0.0)
                    for o, v in doll_opts}
            best_o = max(doll_opts, key=lambda s: vals[s[0].index])[0]
            return Decision(
                action=act.ChooseEventOption(index=best_o.index),
                rationale=f"doll room: {best_o.title} ({vals[best_o.index]:.1f})",
                scores={(o.title or "?"): round(vals[o.index], 2)
                        for o, _v in doll_opts},
            )

        # Events pass (EVENTS_PASS.md): the decline-by-default fix. When the option
        # catalog knows any option on a NON-ancient screen, rank catalogued options by
        # value (unknowns ride the clamped heuristic, same lesson as Silken Tress) and
        # engage if the best clears take_min — Spirebird still outranks the catalog
        # when it has confident data (it sees outcomes; the catalog sees text).
        if not ev.is_ancient and self.event_choices and scored:
            rated_sb = [s for s in scored if s[2] is not None]
            # Catalog-first exceptions: events where the owner's ranking OVERRIDES
            # confident Spirebird data (Tinker Time 2026-07-29: SB slightly prefers
            # Skill over Power, 14.0 vs 13.8; owner: Power > Skill > Attack).
            catalog_first = (ev.event_id or "").upper() in ("TINKER_TIME",)
            if len(rated_sb) < 2 or catalog_first:  # catalog leads
                vals = {}
                for o, heur, _vs in scored:
                    entry = self.event_choices.get(o.title or "")
                    if entry:
                        vals[o.index] = float(entry.get("value", 0.0))
                    else:
                        # Costless-unknown floor (catalog v2, 2026-07-21): the
                        # residual declines were unparseable-but-costless options
                        # (enchants, flows), and Spirebird's own data says the event
                        # pool is overwhelmingly EV-positive — walking away from an
                        # option with NO parsed cost is the provably wrong default.
                        # Anything with a parsed cost keeps the clamped heuristic.
                        text = f"{o.title or ''} {o.description or ''}"
                        costless = (parse_hp_cost(text) == 0
                                    and "curse" not in text.lower()
                                    and "lose" not in text.lower()
                                    and "fight" not in text.lower())
                        vals[o.index] = (max(heur, w.unknown_costless_floor)
                                         if costless else min(heur, _UNKNOWN_BOON_CAP))
                best_o = max(scored, key=lambda s: vals[s[0].index])[0]
                if vals[best_o.index] >= w.take_min:
                    return Decision(
                        action=act.ChooseEventOption(index=best_o.index),
                        rationale=(f"event catalog: '{best_o.title}' "
                                   f"({vals[best_o.index]:.1f})"),
                        scores={(o.title or "?"): round(vals[o.index], 2)
                                for o, _h, _v in scored},
                    )

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

    @staticmethod
    def _daughter_deck_fit(deck) -> bool:
        """Does the deck feed Daughter of the Wind (Block per Attack played)?
        Juggernaut turns her into a damage engine outright; otherwise she needs
        attack density — ≥7 cheap (cost ≤ 1) attacks means she triggers most plays."""
        if not deck:
            return False
        cheap_attacks = 0
        for c in deck:
            if "JUGGERNAUT" in (c.id or "").upper():
                return True
            if (c.type or "") == "Attack" and (c.cost or "").isdigit() \
                    and int(c.cost) <= 1:
                cheap_attacks += 1
        return cheap_attacks >= 7

    def _boon_deck_fit(self, entry: dict, deck) -> float:
        """Choice-time deck-fit for a boon: + per weighted provider of each deck_bonus
        tag, capped (Pael's Legion is worth more to a deck that already generates
        block; Throwing Axe to one with a big opener)."""
        if not deck or not self.draft_tags:
            return 0.0
        from sts2bot.policy.drafttags import _providers, deck_tag_weights
        counts = deck_tag_weights(deck)
        fit = 0.0
        for db in entry.get("deck_bonus") or []:
            have = _providers(db.get("tag", ""), counts, deck, self.draft_tags)
            fit += min(float(db.get("cap", 0.0)), have * float(db.get("per", 0.0)))
        return fit

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
        if option.relic_name or (_EV_OBTAIN_RELIC.search(text) and "curse" not in low):
            val += 6.0  # mod often omits relic_name; "Obtain the <Relic>" text catches it
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

    def _deck_damage_picks(self, deck) -> int:
        """Non-basic cards that deal damage (by KB text or big-hit tag) — the owner's
        damage-saturation principle (A/B #3 Sword Boomerang misdraft): once a couple of
        real damage picks are in, the Act-1 damage-first bias should stop paying."""
        n = 0
        for c in deck:
            cid = (getattr(c, "id", "") or "").upper()
            if cid.startswith(("STRIKE_", "DEFEND_", "BASH")):
                continue
            desc = self.card_effects.get(
                f"{cid}|{1 if getattr(c, 'is_upgraded', False) else 0}")
            if desc and parse_card_description(desc).total_damage > 0:
                n += 1
        return n

    def _deck_has_big_hit(self, deck) -> bool:
        """True once the deck holds any >=12-damage card (by the card-effects KB text —
        deck payloads carry no descriptions) or a tagged big_single_hit provider. Turns
        the first-big-hit draft switch off."""
        for c in deck:
            cid = (getattr(c, "id", "") or "").upper()
            entry = self.draft_tags.get(cid) or {}
            if (entry.get("provides") or {}).get("big_single_hit"):
                return True
            desc = self.card_effects.get(
                f"{cid}|{1 if getattr(c, 'is_upgraded', False) else 0}")
            if desc and parse_card_description(desc).total_damage >= _BIG_HIT_DAMAGE:
                return True
        return False

    def _card_score(
        self, card, deck_size: int, character: str | None = None, act: int = 1,
        deck: list | None = None, relics: list | None = None,
        region: str | None = None, boss_rule: dict | None = None,
    ) -> float:
        w = self.config.card_rewards
        fx = parse_card_description(card.description)
        # Self-death-rider cards (The Gambit) are gated to never-play in the planner, so
        # drafting one buys a permanent dead card — worse than skipping, below any threshold.
        if fx.self_death_rider:
            return -100.0
        score = {
            "Common": w.w_rarity_common,
            "Uncommon": w.w_rarity_uncommon,
            "Rare": w.w_rarity_rare,
            # audit find (step 2): these fell through to the COMMON base. Ancient at
            # UNCOMMON tier (owner 2026-07-13, after a double Relax draft at rare-tier
            # 8.0): the trio varies too much for a flat premium — Apotheosis earns its
            # real value through the __unupgraded tag bonus + upgrade-awareness instead.
            "Ancient": w.w_rarity_uncommon,
            "Event": w.w_rarity_uncommon,
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
        # X-cost "spend-energy" damage (Whirlwind/Volley class) — owner 2026-07-15:
        # Whirlwind IS AoE but INEFFICIENT AoE (every dedicated AoE does more dmg/energy
        # — the tell that AoE alone doesn't redeem it). Its real payoffs are card
        # efficiency (one slot dumping the whole energy bar) and spending SURPLUS energy
        # at high X — both LATE-game conditions, rarely true early. So: no flat AoE
        # bonus (it isn't efficient AoE), and an Act-1 dock. energy_source in deck stays
        # a positive modifier via the tag table, not the hinge.
        is_xcost_damage = (card.cost or "").upper() == "X" and fx.total_damage > 0
        if fx.aoe and not is_xcost_damage:
            score += w.bonus_aoe
        if is_xcost_damage and act <= 1:
            score += w.penalty_xcost_damage_early
        # Owner model rework (2026-07-14): the flat draw bonus is GONE — StS2 energy is
        # scarcer and deck-cycling pressure lower, so pure draw / strike+draw is a weak
        # speculative draft (Pommel Strike "nowhere near as good as the last game").
        # Draw is instead PENALIZED when the deck has no energy source to spend it with;
        # Spirebird stays authoritative otherwise (deliberately NOT overridden).
        # Owned boons/relics count as tag providers (Ancients pass): an energy boon
        # (Pael's Flesh, Very Hot Cocoa...) lifts the draw penalty like a drafted
        # energy card would, and engine boons steer offers via draft_bonus below.
        relic_provides, relic_draft_bonus = (
            boon_relic_context(relics, self.ancient_boons)
            if relics and self.ancient_boons else ({}, {})
        )
        if fx.draw and deck is not None and self.draft_tags:
            from sts2bot.policy.drafttags import _providers, deck_tag_weights
            energy_sources = _providers("energy_source", deck_tag_weights(deck), deck,
                                        self.draft_tags, relic_provides)
            if energy_sources <= 0:
                score += w.penalty_draw_no_energy
        # Block earns its bonus in ACT 1 only (lesser than the damage bonus below —
        # owner 2026-07-14); later acts price block via the §5-C capability delta.
        # Region-conditional (owner 2026-07-17, magnitudes provisional): the Underdocks
        # rewards defense/scaling over damage, and the post-rework arrival flip
        # (Overgrowth 72→90%, Underdocks 87→77%) says our damage-first tilt fits only
        # the Overgrowth. Underdocks swaps the bonus magnitudes.
        ud = region == "underdocks"
        eff_block_bonus = w.ud_early_block_bonus if ud else w.early_block_bonus
        eff_damage_bonus = w.ud_early_damage_bonus if ud else w.early_damage_bonus
        if fx.block and act <= 1:
            score += eff_block_bonus
        # Boss-specific per-instance premium (_BOSS_DRAFT_RULES): vs a Str/Dex-taxing
        # boss (Lagavulin Matriarch) big single instances hold value; chip does not.
        if boss_rule:
            if fx.damage >= boss_rule.get("min_hit", 10**6) and not is_xcost_damage:
                score += boss_rule["hit_bonus"]
            if fx.block >= boss_rule.get("min_block", 10**6):
                score += boss_rule["block_bonus"]
            if (card.type or "") == "Power":
                score += boss_rule.get("power_bonus", 0.0)
            if fx.hits >= boss_rule.get("min_hits", 10**6) and not is_xcost_damage:
                score += boss_rule["multihit_bonus"]
            if fx.aoe and not is_xcost_damage:  # multi-body boss (The Kin)
                score += boss_rule.get("aoe_bonus", 0.0)
            score += (boss_rule.get("card_bonus") or {}).get((card.id or "").upper(), 0.0)
            # tag_bonus: premium for cards PROVIDING a tag this boss values
            # (Soul Fysh: exhaust_enabler deletes his Beckons from the deck)
            if self.draft_tags:
                provides = ((self.draft_tags.get((card.id or "").upper()) or {})
                            .get("provides") or {})
                for tag_, b_ in (boss_rule.get("tag_bonus") or {}).items():
                    if provides.get(tag_):
                        score += b_
        if fx.energy_gain:
            score += w.bonus_energy
        # Early-damage bias (owner, Run-2/3): Act 1 favors cards that deliver damage, to get
        # through early fights. Includes attack-*generators* like Infernal Blade — a Skill the
        # text parser reads no damage on, but it adds a free Attack, so it plays like one.
        # (Deck-aware drafting, e.g. Vulnerable only once Vicious is drafted, is deferred.)
        desc_l = (card.description or "").lower()
        generates_attack = "random attack" in desc_l or ("add" in desc_l and "attack" in desc_l)
        # ...but X-cost spend-energy damage is NOT effective early damage (the whole
        # point of the owner's Whirlwind read), so it earns neither this bonus nor AoE's.
        # ...tapered by damage saturation (owner, A/B #3: Sword Boomerang over Armaments
        # with Bully+Taunt already in deck was a "desperation damage pick" — an average
        # attack shouldn't keep earning the early bonus once real damage picks are in).
        if act <= 1 and (fx.total_damage > 0 or generates_attack) and not is_xcost_damage:
            n_dmg = self._deck_damage_picks(deck) if deck is not None else 0
            sat = w.early_damage_sat_start
            factor = 1.0 if n_dmg < sat else (0.5 if n_dmg == sat else 0.0)
            score += eff_damage_bonus * factor
        # One-time "take SOMETHING with big damage" switch (owner 2026-07-14, from the
        # CJN9M609YW A/B: Pommel over Hemokinesis was the community-prior pick, but a
        # starter deck's first job is acquiring a real hit). Until the deck holds any
        # >=12-damage card, offered big hits earn a strong bonus; self-extinguishing.
        if (act <= 1 and deck is not None
                and fx.total_damage >= _BIG_HIT_DAMAGE
                and not self._deck_has_big_hit(deck)):
            score += w.w_first_big_hit
        # Planner-blind penalty (owner-approved 2026-07-09, after two Cascade draft-and-upgrades):
        # a card whose parsed effects are EMPTY is one the combat planner literally cannot use
        # yet, so the community prior prices a pilot we aren't — flat dock on top of the upside
        # discount. Self-removing by design: the moment textparse/planner learn the card,
        # `recognized` fills and the penalty vanishes (Cascade is a fine card in general —
        # owner). Attack-generators (Infernal Blade) are exempt: their output is playable.
        if not fx.has_any_effect and not generates_attack:
            score += w.penalty_planner_blind
        try:
            if card.cost is not None and card.cost.upper() != "X" and int(card.cost) >= 3:
                score += w.penalty_cost_3plus
        except ValueError:
            pass
        if deck_size > 25:
            score += w.penalty_deck_over_25
        # card-pass step 2: deck-context tag adjustment (enabler/density/anti/copy-cap),
        # additive on top of everything above (owner-reviewed 2026-07-12)
        if deck is not None and self.draft_tags:
            score += score_adjustment(
                card.id or "", deck, self.draft_tags, w, act,
                is_upgraded=bool(getattr(card, "is_upgraded", False)),
                relic_provides=relic_provides,
                relic_draft_bonus=relic_draft_bonus,
            )
        return score

    def _upcoming_boss(self, ctx: LoopContext, act: int) -> list[FightEnemy]:
        """The act's boss as a FightEnemy: real HP + mechanics from the bestiary (name cached from
        the map) with a per-act dps/ramp estimate; the generic profile for unknown / multi-creature
        bosses (e.g. The Kin, whose bestiary entries are its components)."""
        boss_name = ctx.screen_mem.get("act_boss_name", "")
        entry = self.bestiary.get(boss_name)
        if entry:
            dps, ramp = _ACT_BOSS.get(act, _ACT_BOSS[1])
            dps = realized_dps(self.enemy_dps, boss_name, dps)
            return [bestiary_enemy(entry, dps=dps, name=boss_name, str_ramp=ramp)]
        return [FightEnemy(*_GENERIC_BOSS)]

    def _capability_deltas(
        self, deck, cards, max_hp: int, boss: list[FightEnemy]
    ) -> dict[int, float]:
        """§5-C drafting: per card index, how much it improves estimate_fight vs the upcoming boss
        in the *current deck's* context (deck-aware: a block-starved deck values block, a
        damage-starved one values damage). Needs the deck + harvested card text to price it; if
        either is missing the term is skipped (empty) and drafting falls back to Elo/heuristics.
        Note: deck_output now also prices Strength-ramp + Vulnerable from card text (approx; it
        still misses relic Strength e.g. Vajra and true per-turn rampers like Demon Form, which
        the Elo prior / w_power carry)."""
        if not deck or not self.card_effects:
            return {}
        w = self.config.card_rewards

        def progress(o) -> float:
            # HP I'd retain minus the boss HP still standing: rewards getting *closer* to the kill
            # even in a loss (the usual Act-1-boss case), where raw end-HP alone is misleading.
            return o.exp_end_hp - o.enemy_hp_left

        base_out = estimate_fight(max_hp, deck_output(deck, descriptions=self.card_effects), boss)
        base = progress(base_out)
        deltas: dict[int, float] = {}
        for c in cards:
            out = estimate_fight(
                max_hp, deck_output([*deck, c], descriptions=self.card_effects), boss
            )
            delta = w.capability_weight * (progress(out) - base)
            if out.win and not base_out.win:
                delta += w.capability_win_flip_bonus  # flips the boss lose->win: prize it
            deltas[c.index] = delta
        return deltas

    def _card_reward(self, state: CardRewardState, ctx: LoopContext) -> Decision | Wait:
        w = self.config.card_rewards
        cr = state.card_reward
        if not cr.cards:
            if cr.can_skip:
                return Decision(action=act.SkipCardReward(), rationale="no cards offered; skip")
            return Wait(reason="card reward with no cards and no skip")
        deck = state.player.deck if (state.player and state.player.deck) else []
        deck_size = len(deck) if deck else 15
        character = state.player.character if state.player else None
        run_act = state.run.act if state.run else 1
        max_hp = state.player.max_hp if (state.player and state.player.max_hp) else 80
        # §5-C: value each card by how much it improves the estimate vs the *real* upcoming boss
        cap = self._capability_deltas(deck, cr.cards, max_hp, self._upcoming_boss(ctx, run_act))
        relics = state.player.relics if (state.player and state.player.relics) else None
        region = _act1_region(ctx.screen_mem.get("act_boss_name")) if run_act <= 1 else None
        boss_rule = _boss_draft_rule(ctx.screen_mem.get("act_boss_name"))
        scored = [
            (self._card_score(c, deck_size, character, run_act, deck=deck, relics=relics,
                              region=region, boss_rule=boss_rule)
             + cap.get(c.index, 0.0), c)
            for c in cr.cards
        ]
        scored.sort(key=lambda sc: -sc[0])
        best_score, best = scored[0]
        score_map = {c.name: round(s, 2) for s, c in scored}
        region_tag = f", {region}" if region else ""
        # 8.1d: lower the take bar for an unrefined deck (lots of basic Strikes/Defends) — a weak
        # deck profits from almost any real card, and top players rarely skip early picks.
        basics = sum(1 for c in deck if (c.id or "").upper().startswith(("STRIKE_", "DEFEND_")))
        weak_frac = basics / max(1, deck_size)
        threshold = w.take_threshold - w.take_weak_deck_discount * weak_frac
        if best_score >= threshold or not cr.can_skip:
            return Decision(
                action=act.SelectCardReward(card_index=best.index),
                rationale=f"take {best.name} (score {best_score:.1f} >= thr {threshold:.1f}, "
                f"{weak_frac:.0%} basic{region_tag})",
                scores=score_map,
            )
        return Decision(
            action=act.SkipCardReward(),
            rationale=f"skip: best {best.name} scored {best_score:.1f} < thr "
            f"{threshold:.1f}{region_tag}",
            scores=score_map,
        )

    # ------------------------------------------------------------ bundle selection

    def _bundle_select(self, state: BundleSelectState, ctx: LoopContext) -> Decision | Wait:
        """Score bundles by their contents instead of taking the first blind (run 1
        2026-07-16: an unscored Neow pack delivered Havoc — a planner-dead card the
        reward scorer docks to -9.8). Each bundle = sum of _card_score over its cards
        with full deck/relic context; select best, then confirm."""
        bs = state.bundle_select
        if bs.preview_showing:
            if ctx.screen_mem.get("bundle_picked") is not None or not bs.can_cancel:
                ctx.screen_mem.pop("bundle_picked", None)
                return Decision(
                    action=act.ConfirmBundleSelection(),
                    rationale="confirm bundle selection",
                )
            # a preview we didn't open (screen defaults) — back out and score first
            return Decision(
                action=act.CancelBundleSelection(),
                rationale="cancel default bundle preview to score options",
            )
        if not bs.bundles:
            return Wait(reason="bundle select pending preview/confirm availability")
        deck = state.player.deck if (state.player and state.player.deck) else []
        relics = state.player.relics if (state.player and state.player.relics) else None
        character = state.player.character if state.player else None
        run_act = state.run.act if state.run else 1
        best, best_score = None, float("-inf")
        score_map = {}
        for b in bs.bundles:
            if not b.cards:  # contents hidden: neutral, only beats a negative bundle
                total = 0.0
            else:
                total = sum(
                    self._card_score(c, len(deck), character, run_act,
                                     deck=deck, relics=relics)
                    for c in b.cards
                )
            label = ", ".join(c.name or "?" for c in b.cards) or f"bundle {b.index}"
            score_map[label[:60]] = round(total, 2)
            if total > best_score:
                best, best_score = b, total
        ctx.screen_mem["bundle_picked"] = best.index
        return Decision(
            action=act.SelectBundle(index=best.index),
            rationale=f"select bundle {best.index} (score {best_score:.1f})",
            scores=score_map,
        )

    # -------------------------------------------------------- card selection overlay

    def _card_quality(self, card, character: str | None, deck: list | None = None) -> float:
        """Higher = better card to KEEP; lower = better to remove. Curses sink below
        un-upgraded basics, which sink below everything else; Spirebird prior on top."""
        w = self.config.deck
        base = (card.name or "").rstrip("+")
        quality = 0.0
        if (card.type or "") in ("Curse", "Status"):
            quality += w.curse_penalty
            # Self-expiring curses (Guilty: auto-removes after 5 combats) are NOT worth a paid
            # removal — the clock removes them free, so a basic beats them as the target (owner
            # 2026-07-09; the end-of-Act-3 "clock won't finish" nuance is deliberately skipped).
            # Deck-view cards carry no rules text, so match by name/id with a text fallback.
            nid = f"{card.id or ''} {card.name or ''}".upper()
            if "GUILTY" in nid or "removed from your deck" in (card.description or "").lower():
                quality -= w.curse_penalty * 0.8  # mostly neutralize: above basics, below keepers
        if base in ("Strike", "Defend") and not card.is_upgraded:
            quality += w.basic_penalty
            # Step-2 review (#16/#17): a drafted payoff keyed on basics flips them from
            # removal fodder to enablers — Fasten wants Defends kept; Perfected Strike /
            # Hellraiser want Strike-named cards. Mostly neutralize the basic penalty
            # while such a payoff is in deck (its tag-table needs reference the pseudo-tag).
            if deck and self.draft_tags:
                pseudo = "__defends" if base == "Defend" else "__strike_named"
                for c in deck:
                    entry = self.draft_tags.get((c.id or "").upper()) or {}
                    if any(n.get("tag") == pseudo for n in entry.get("needs") or []):
                        quality -= w.basic_penalty * 0.8
                        break
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
                if "GUILTY" in f"{c.id or ''} {c.name or ''}".upper():
                    continue  # self-expiring: not worth PAYING to remove (see _card_quality)
                return True
            if (c.name or "").rstrip("+") in ("Strike", "Defend") and not c.is_upgraded:
                return True
        return False

    @staticmethod
    def _select_count(prompt: str) -> int:
        m = re.search(r"choose (\d+)", prompt)
        return int(m.group(1)) if m else 1

    # Forced debuff choice (Knowledge Demon's Curse of Knowledge, captured 2026-07-09: an
    # ordinary card_select offering Status debuffs — Disintegration vs Mind Rot, later Sloth /
    # Waste Away). Owner strategy: take Disintegration every round (end-of-turn BLOCKABLE
    # damage beats permanent draw/energy/card-cap losses). Preference order, least-bad first;
    # unknown debuffs sort last so a new one is never accidentally preferred.
    _DEBUFF_PREFERENCE = ("DISINTEGRATION", "MIND_ROT", "SLOTH", "WASTE_AWAY")

    def _pick_target(self, cs, prefer_worst: bool, character, exclude=(),
                     free_this_turn: bool = False, deck: list | None = None,
                     boss_rule: dict | None = None, enchant_kind: str | None = None):
        prompt = (cs.prompt or "").lower()
        # the generic "Choose a card to Enchant." prompt carries no enchant name;
        # enchant_kind is the intent remembered from the event choice one screen back
        if enchant_kind and "enchant" in prompt:
            prompt = f"{prompt} {enchant_kind}"
        candidates = [c for c in cs.cards if c.index not in exclude]
        # All options are Status-type = a forced pick-your-poison, not a reward: choose the
        # least-bad by the owner's table, NOT by card quality (they're all "worthless").
        if candidates and all((c.type or "") == "Status" for c in candidates):
            def poison_rank(c):
                nid = (c.id or c.name or "").upper().replace(" ", "_")
                for i, key in enumerate(self._DEBUFF_PREFERENCE):
                    if key in nid:
                        return i
                return len(self._DEBUFF_PREFERENCE)
            return min(candidates, key=poison_rank)
        is_upgrade = "upgrade" in prompt or "enchant" in prompt
        if is_upgrade:
            unupgraded = [c for c in candidates if not c.is_upgraded]
            if unupgraded:
                candidates = unupgraded
        if not candidates:
            return None
        if is_upgrade:
            # Slither enchant (owner 2026-07-20, reversing the old 'trap' anchor):
            # random 0-3 cost on draw = positive EV stapled to any cost>=2 card, and
            # Ironclad always has Bash. Target the HIGHEST-cost card — the original
            # sin was Slither on a cost-1 Strike.
            if "slither" in prompt or "cost_zero" in prompt:
                def slither_cost(c):
                    try:
                        return int(c.cost or 0)
                    except ValueError:
                        return 0  # X-cost: don't randomize an X card
                return max(candidates,
                           key=lambda c: (slither_cost(c),
                                          self._card_quality(c, character)))
            # Upgrade the card that GAINS the most (Spirebird upgraded-vs-base delta),
            # tie-broken by base quality; missing deltas default to a typical gain.
            # Boss-aware Smith (owner lever 2026-07-17): an upgrade that pushes an
            # instance ACROSS the act boss's threshold (Headbutt 6→12 vs the
            # Matriarch's Str/Dex clock) is worth more than its generic delta says —
            # the offer stream is the binding constraint; Smithing widens it.
            def upgrade_key(c):
                uv = self.priors.upgrade_value(c.id, character) if self.priors else None
                uv = uv if uv is not None else 1.5
                # Mad Science upgrade = Innate (owner 2026-07-29): premium on the
                # POWER variants (an Innate Curious/Expertise fires turn 1 every
                # fight), minor otherwise. One id, many designs -> detect by text.
                if (c.id or "").upper() == "MAD_SCIENCE":
                    d_ = (c.description or "").lower()
                    if "cost 1 less" in d_ or "dexterity" in d_:
                        uv += 2.5
                # Sharp enchant multiplies per-HIT: prefer multi-hit attacks (owner:
                # a 3x+ target beats even Swift-on-Power)
                if "sharp" in prompt:
                    fxc = parse_card_description(c.description)
                    if fxc.hits >= 2:
                        uv += 1.5 + (1.0 if fxc.hits >= 3 else 0.0)
                if boss_rule and self.card_effects:
                    cid = (c.id or "").upper()
                    base_fx = parse_card_description(
                        self.card_effects.get(f"{cid}|0") or "")
                    up_fx = parse_card_description(
                        self.card_effects.get(f"{cid}|1") or "")
                    mh = boss_rule.get("min_hit")
                    if mh and base_fx.damage < mh <= up_fx.damage:
                        uv += 2.0
                    mb = boss_rule.get("min_block")
                    if mb and base_fx.block < mb <= up_fx.block:
                        uv += 1.5
                return (uv, self._card_quality(c, character))

            return max(candidates, key=upgrade_key)
        # Cards that WANT to be exhausted (owner 2026-07-14): Howl/Bombardment replay from
        # the exhaust pile; Drum of Battle pays energy ON exhaust. Exhausting one is a GAIN,
        # not a loss — but they ranked at -3 (below basics at -50), so the bot burned Strikes
        # and never fed the engine. Strictly scoped to true EXHAUST prompts: on a REMOVE
        # screen (permanent) or an upgrade screen this must not fire, or the bot would delete
        # its own engine. Curses still go first (owner).
        is_exhaust_prompt = "exhaust" in prompt and not any(
            v in prompt for v in ("remove", "destroy", "transform")
        )

        def quality(c):
            q = self._card_quality(c, character, deck=deck)
            if (is_exhaust_prompt and prefer_worst
                    and _WANTS_EXHAUST_RE.search(c.description or "")):
                q -= 60.0  # below basics (-50), above curses (-100)
            # Quest pseudo-curses (Spoils Map, owner 2026-07-17): unplayable dead weight
            # in combat, so prime exhaust/discard fodder — exhaust is per-fight and the
            # card returns for its Act-3 redemption (600g at the main chest). But on
            # PERMANENT screens (remove/transform/destroy) it must be protected:
            # deleting it deletes the payoff. (Type "Quest", no description — type is
            # the only hook the payload gives us.)
            if (c.type or "") == "Quest" and prefer_worst:
                if is_exhaust_prompt or "discard" in prompt:
                    q -= 58.0  # after curses (-100) and Howl-class engines (~-63),
                    #            before basics (-50)
                elif any(v in prompt for v in ("remove", "destroy", "transform")):
                    q += 150.0  # never delete the coupon
            # Curse-transform is curse ROULETTE (owner 2026-07-25, LKG20K3FBE forensics:
            # 'select worst' transformed Writhe at f3 and rolled Bad Luck — Eternal,
            # unplayable, 13 HP per end-of-turn-in-hand, un-removable — which bled the
            # run dead by f21): transforming a curse rerolls WITHIN THE CURSE POOL, so
            # the downside dwarfs the upside. Transform targets basics; curses only if
            # literally nothing else is offered.
            if (c.type or "") == "Curse" and "transform" in prompt:
                q += 250.0  # from -100 to above everything: never the transform pick
            # Retain curses (Poor Sleep) are better PARKED in hand than discarded back into
            # the deck cycle — but the parking is worth roughly one junk-tier, not immunity
            # (owner refinement 2026-07-09): if the rest of the hand would actually be PLAYED,
            # the retain curse IS the right discard. So it ranks above normal curses/statuses
            # (ditch those first) but below basics/playables. Exhaust/remove still take it.
            if (prefer_worst and "discard" in prompt and (c.type or "") == "Curse"
                    and "retain" in (c.description or "").lower()):
                q += 30.0  # curse -100 -> -70: after junk, before anything playable
            return q

        chooser = min if prefer_worst else max
        if free_this_turn and not prefer_worst:
            # Card-gen potion / discovery picks show FULL printed cost but play free this turn
            # (owner 2026-07-09: the bot passed on Pyre from a Power Potion — sensible only at
            # its printed 2 cost). The community prior prices a card as if its cost is paid
            # every play, so subsidize by printed cost: a Power's one-time cost barrier is
            # wiped entirely (x2.0); repeatable cards get a one-time tempo credit (x0.5).
            # Caveat: an in-combat TUTOR (fetch-from-pile) also lands here and gets a mild
            # expensive-card bias — acceptable until tutors are context-aware (PLAN §8.4).
            def free_key(c):
                try:
                    cost = int(c.cost) if c.cost and c.cost.upper() != "X" else 0
                except ValueError:
                    cost = 0
                mult = 2.0 if (c.type or "") == "Power" else 0.5
                return self._card_quality(c, character) + cost * mult
            return max(candidates, key=free_key)
        return chooser(candidates, key=quality)

    # Bounds so a non-progressing screen can never rail a run (run 2: a 'choose'
    # screen returned 'ok' but never resolved; the old await-confirm Wait stalled).
    # Raised 3 -> 8 (owner-caught 2026-07-14, Toolbox): the mod ACCEPTS the pick
    # ("Choosing card: Forgotten Ritual") but the overlay takes several polls to close,
    # so 3 tries expired and the handler CANCELLED — forfeiting the relic's free card
    # every combat. Selection is idempotent (re-picking the same index is harmless), so
    # patience is cheap; the loop's 60-tick stall rail remains the real backstop.
    _CHOOSE_RETRIES = 8
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

        # `needed` distinct cards to pick: 1 for "Choose a card to Remove/Upgrade", 3 for the
        # Gnarled Axe "Choose 3 cards to Enchant". Key the pick-tracking on the selection's
        # identity (screen + prompt) so it survives the cards list changing under us; it's cleared
        # on confirm/bail, so a later same-prompt event starts fresh.
        needed = self._select_count(prompt)
        mem_key = f"cardsel:{cs.screen_type}:{cs.prompt}"
        mem: dict = ctx.screen_mem.setdefault(mem_key, {"picked": [], "tries": 0})
        picked: list[int] = mem["picked"]

        # Single-pick screens that resolve on select_card alone: the "choose" type, and any 1-pick
        # screen with no confirm/cancel/skip (e.g. Headbutt's NCombatPileCardSelectScreen — "put a
        # card on top of your Draw Pile"). No confirm step, so (re)select until it closes, not
        # stranding in await-confirm (the live hang: first select hit a not-yet-settled overlay and
        # no-op'd). The `needed == 1` guard is essential: a FORCED multi-remove (Pael's Tooth's
        # "Choose 5 cards to Remove" — no cancel, can_confirm False until 5 picked) must NOT come
        # here (it would re-click the same worst card forever); it needs the pick-N-distinct path.
        resolves_on_select = (cs.screen_type or "") == "choose" or (
            needed == 1 and not (cs.can_confirm or cs.can_cancel or cs.can_skip)
        )
        # In-combat add/choose screens (card-gen potions, discoveries) play the pick FREE this
        # turn despite showing full cost — the pick scorer subsidizes printed cost there.
        in_combat = state.player is not None and bool(state.player.in_combat)
        if resolves_on_select:
            target = self._pick_target(cs, prefer_worst, character, free_this_turn=in_combat,
                                       deck=state.player.deck if state.player else None,
                                       boss_rule=_boss_draft_rule(
                                           ctx.screen_mem.get("act_boss_name")),
                                       enchant_kind=ctx.screen_mem.get("pending_enchant"))
            if mem["tries"] < self._CHOOSE_RETRIES and target is not None:
                mem["tries"] += 1
                return Decision(
                    action=act.SelectCard(index=target.index),
                    rationale=f"choose {target.name} for: {cs.prompt}",
                )
            ctx.screen_mem.pop(mem_key, None)
            # Cancelling FORFEITS the card (Toolbox: a free colorless card every combat),
            # so it stays the LAST resort — but it stays: a screen that never resolves
            # would otherwise hang the run (the original run-2 stall). The fix for the
            # Toolbox loss is patience (_CHOOSE_RETRIES 3 -> 8), not removing the valve.
            if cs.can_skip or cs.can_cancel:
                return Decision(
                    action=act.CancelSelection(), rationale="choose not resolving; skip"
                )
            return Wait(reason="choose-a-card stuck")

        # Pick the required N DISTINCT cards FIRST. The enchant screen lets you confirm with fewer
        # than N selected, which strands you on a dead sub-screen (live f27 hang). So don't confirm
        # until `needed` are picked — even though can_confirm goes True after the first pick.
        if cs.cards and len(picked) < needed:
            target = self._pick_target(cs, prefer_worst, character, exclude=picked,
                                       free_this_turn=in_combat,
                                       deck=state.player.deck if state.player else None,
                                       enchant_kind=ctx.screen_mem.get("pending_enchant"),
                                       boss_rule=_boss_draft_rule(
                                           ctx.screen_mem.get("act_boss_name")))
            if target is not None:
                picked.append(target.index)
                kind = "worst" if prefer_worst else "best"
                return Decision(
                    action=act.SelectCard(index=target.index),
                    rationale=f"select {kind} {target.name} ({len(picked)}/{needed}): {cs.prompt}",
                )
            # fewer distinct candidates than asked — confirm/skip with what we have
            ctx.screen_mem.pop(mem_key, None)
            if cs.can_confirm:
                return Decision(
                    action=act.ConfirmSelection(), rationale="no more candidates; confirm"
                )
            if cs.can_skip or cs.can_cancel:
                return Decision(action=act.CancelSelection(), rationale="no target; skip")
            return Wait(reason="card select: no remaining candidates")

        # Enough picked (or a previewed single pick): confirm. Clear pick-tracking ONLY once the
        # game raises its preview (preview_showing) -- the honest "selection registered" signal. If
        # cleared before that, a confirm that no-ops (picks not yet registered at 4x) would leave
        # `picked` empty and we'd re-select, toggling cards back off (the f27 enchant over-toggle).
        # Keeping `picked` means we just re-confirm next poll until it resolves. (Enchant/upgrade/
        # remove screens all raise a preview.)
        if cs.can_confirm:
            if cs.preview_showing:
                ctx.screen_mem.pop(mem_key, None)
            return Decision(
                action=act.ConfirmSelection(), rationale=f"confirm {len(picked)}/{needed} selected"
            )
        if not cs.cards:
            ctx.screen_mem.pop(mem_key, None)
            if cs.can_skip or cs.can_cancel:
                return Decision(action=act.CancelSelection(), rationale="nothing selectable; skip")
            return Wait(reason="card select with no cards or confirm")

        # Picked enough but confirm not offered yet: wait briefly, then bail safely.
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
        target = self._pick_target(hs, prefer_worst, character,
                                   deck=state.player.deck if state.player else None)
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
            # Clock bosses (Knowledge Demon's Disintegration) cost more than the
            # aggregate boss history says — per-boss bump via _BOSS_DRAFT_RULES.
            rule = _boss_draft_rule(ctx.screen_mem.get("act_boss_name"))
            if rule:
                est += rule.get("rest_loss_bonus", 0.0)
            # Act-3 bosses cost more than the act-1-dominated aggregate says
            if (state.run.act if state.run else 1) >= 3:
                est += w.act3_boss_loss_bonus
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
        # Non-standard campfire actions (§8.4 class, 4 known members): relic/quest-added
        # options the fixed Rest/Smith menu was blind to — the Byrdonis Egg rode along
        # as a dead curse past 3 rest sites, Girya's Lift never fired, and two Ancient
        # boons (Pael's Growth / Meat Cleaver) were priced near-zero because their
        # actions were unreachable. Priority (owner guidance, Girya note 2026-06-25):
        # Hatch always (it's why the egg was taken) > Lift while healthy (permanent
        # +1 Str, <=3 uses) > Cook when thinnables exist (remove 2, +9 max HP) >
        # Clone only if a Clone-enchanted card exists. Rest already won above if needed.
        def _deck_has_clone_enchant() -> bool:
            for c in (player.deck if player else None) or []:
                for k in getattr(c, "keywords", None) or []:
                    if (getattr(k, "name", "") or "").lower() == "clone":
                        return True
            return False

        specials = []  # (priority, option, why)
        for key, o in enabled.items():
            if key in ("rest", "smith"):
                continue
            nm = f"{o.id or ''} {o.name or ''}".lower()
            if "hatch" in nm:
                specials.append((0, o, f"hatch the egg ({o.name})"))
            elif "lift" in nm:
                specials.append((1, o, f"lift: permanent +1 Strength ({o.name})"))
            elif "cook" in nm and self._has_removable_card(player):
                specials.append((2, o, f"cook: remove 2 + max HP ({o.name})"))
            elif "clone" in nm and _deck_has_clone_enchant():
                specials.append((3, o, f"clone the enchanted card ({o.name})"))
        if specials:
            _, o, why = min(specials)
            return Decision(action=act.ChooseRestOption(index=o.index), rationale=why)
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

        # (Foul throws moved to the orchestrator, 2026-07-25: probe-proven that the
        # throw only works on the SHOPKEEPER screen, which our own /state polling
        # auto-advances past — so the loop fires them blind between the accepted
        # shop travel and the next poll. Attempting here always errored
        # "cannot be used right now": the shop UI is already open by the time this
        # handler runs.)

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

        # 1. Card removal — high, safe value when there's a junk card to cut. A starter-heavy deck
        #    spends down to a smaller cushion for it (cutting a basic is worth dipping into gold);
        #    still capped at removal_max_price (owner: efficiency dies past ~150g).
        deck = (player.deck if player else None) or []
        basics = sum(
            1 for c in deck
            if (c.name or "").rstrip("+") in ("Strike", "Defend") and not c.is_upgraded
        )
        weak_frac = basics / len(deck) if deck else 0.5
        removal_reserve = int(reserve * (1 - w.removal_weak_reserve_cut * weak_frac))
        for item in avail:
            price = item.gold_price or 0
            if (
                item.category == "card_removal"
                and price <= w.removal_max_price
                and gold - price >= removal_reserve
                and self._has_removable_card(player)
            ):
                bought.append(item.index)
                return Decision(
                    action=act.ShopPurchase(index=item.index),
                    rationale=f"buy card removal ({price}g; reserve {removal_reserve}, "
                    f"{weak_frac:.0%} basic)",
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

        # 4. Last-shop spend-down (owner 2026-07-12, caught during the FIRST-WIN run: the
        #    bot left an Act-3 shop with ~500 gold and no shop ahead). Gold has zero
        #    terminal value, so at the run's likely-last shop the reserve/value gates drop:
        #    buy affordable relics (skipping known-negative WAR and downside-text relics
        #    until the relic pass can price them) and fill the potion belt. Cards are
        #    deliberately NOT bought here — a random card can dilute the boss deck.
        #    Act>=3 approximates "last shop"; intended-path tracking is the filed upgrade.
        act_now = state.run.act if state.run else 1
        if act_now >= 3:
            downside_markers = ("curse", "lose ", "can no longer", "cannot ", "no longer",
                                "take 1 damage", "receive ")
            spend_relics = []
            for item in avail:
                if item.category != "relic" or not item.can_afford:
                    continue
                v = self.shop_stats.relic_value(item.relic_id) if self.shop_stats else None
                if v is not None and v < 0:
                    continue  # known dud stays a dud even free
                desc = (item.relic_description or "").lower()
                if any(m in desc for m in downside_markers):
                    continue
                spend_relics.append(item)
            if spend_relics:
                item = min(spend_relics, key=lambda i: i.gold_price or 0)  # most items per gold
                bought.append(item.index)
                return Decision(
                    action=act.ShopPurchase(index=item.index),
                    rationale=f"last-shop spend-down: relic {item.relic_name} "
                    f"({item.gold_price}g; gold is worthless past here)",
                )
            for item in avail:
                if (
                    item.category == "potion" and item.can_afford
                    and player is not None
                    and len(player.potions) < player.max_potion_slots
                ):
                    bought.append(item.index)
                    return Decision(
                        action=act.ShopPurchase(index=item.index),
                        rationale=f"last-shop spend-down: potion {item.potion_name} "
                        f"({item.gold_price}g)",
                    )
        return Decision(action=act.Proceed(), rationale="done shopping")

    # ------------------------------------------------------------------ rewards (potion-aware)

    def _rewards(self, state: RewardsState, ctx: LoopContext) -> Decision | Wait:
        player = state.player
        # Downside potions (Foul/Glowwater) are merchant ammo (100g thrown at a shop),
        # NOT combat resources — so past the point where a merchant is plausibly still
        # reachable, claiming one just wastes a slot (owner catch 2026-07-25: the WIN
        # run banked two Fouls it could never sell). Late-act-3 proxy until routing
        # can answer "is a shop still reachable" properly.
        run = state.run
        if (self.config.potions.skip_late_downside_claims
                and run and (run.act or 0) >= 3 and (run.floor or 0) >= 40
                and player is not None and player.potions):
            for item in state.rewards.items:
                nid = f"{item.potion_id or ''} {item.potion_name or ''}".upper()
                if item.type == "potion" and ("FOUL" in nid or "GLOWWATER" in nid):
                    marker = item.potion_id or item.gold_amount or item.description or ""
                    ctx.screen_mem.setdefault("reward_attempts", {})[
                        f"{run.floor}:{item.index}:{item.type}:{marker}"
                    ] = 99  # mark exhausted: the fallback claims everything else
        if player is not None and len(player.potions) >= player.max_potion_slots:
            potion_items = [i for i in state.rewards.items if i.type == "potion"]
            if potion_items and not ctx.screen_mem.get("discarded_for_reward"):
                victim = self._worst_potion(player.potions)
                # Discard only for a genuine upgrade (owner 2026-07-13: the belt's Foul
                # — 100g at the next merchant — was ditched for an ordinary reward).
                # Rank the incoming reward potion by the same keep-value scale.
                class _RewardPotion:
                    id = potion_items[0].potion_id
                    name = potion_items[0].potion_name
                    description = potion_items[0].potion_description
                reward_rank = self._potion_rank(_RewardPotion())
                if victim is not None and reward_rank > self._potion_rank(victim):
                    ctx.screen_mem["discarded_for_reward"] = True
                    return Decision(
                        action=act.DiscardPotion(slot=victim.slot),
                        rationale=f"discard {victim.name} (rank "
                        f"{self._potion_rank(victim)}) for better reward potion "
                        f"(rank {reward_rank})",
                    )
        decision = self._fallback.decide(state, ctx)
        if isinstance(decision, Decision) and decision.action.payload().get("action") == "proceed":
            ctx.screen_mem.pop("discarded_for_reward", None)
        return decision

    def _relic_select(self, state: RelicSelectState, ctx: LoopContext) -> Decision | Wait:
        """Ancient / elite / treasure relic choice: take the highest-value relic by Spirebird raw
        WAR, not the first offered (the trivial fallback took relics[0] -> effectively random).
        Unknown relics get a neutral 0 (taken over a known-bad, not over a known-good relic)."""
        rs = state.relic_select
        if rs.relics:
            def war(relic) -> float:
                v = self.shop_stats.relic_war(relic.id) if self.shop_stats else None
                return v if v is not None else 0.0
            best = max(rs.relics, key=war)
            return Decision(
                action=act.SelectRelic(index=best.index or 0),
                rationale=f"take {best.name} (relic WAR {war(best):.0f})",
            )
        if rs.can_skip:
            return Decision(action=act.SkipRelicSelection(), rationale="no relics; skip")
        return Wait(reason="relic select with nothing to do")

    # Keep-value by category for the full-belt discard: ditch junk (downside / unknown),
    # keep the good stuff (heals, buffs, energy/draw value, damage). Tie-break by slot.
    _DISCARD_RANK: ClassVar[dict[str, int]] = {
        "downside": 0, "other": 1, "debuff": 3, "block": 3, "value": 4, "draw": 4,
        "damage": 4, "aoe_damage": 4, "card_gen": 4, "buff": 5, "heal": 6, "fruit_juice": 7,
    }

    def _potion_rank(self, potion) -> int:
        """Keep-value rank for belt decisions. Foul is NOT its combat category: it is
        100 gold at the next merchant (the shop-throw feature), so it ranks like a
        strong potion instead of auto-discard fodder (live 2026-07-13: a Foul was
        discarded for a reward potion before ever meeting a shop)."""
        nid = f"{potion.id or ''} {potion.name or ''}".upper()
        if "FOUL" in nid:
            # ~100g via the merchant throw — WORKING again (2026-07-25 probe: the
            # window is the shopkeeper screen; the orchestrator now fires the throw
            # blind between shop travel and the next poll). Above junk, below real
            # combat potions.
            return 3
        return self._DISCARD_RANK.get(self._potion_category(potion), 2)

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
        return min(potions, key=lambda p: (self._potion_rank(p), p.slot))
