"""StandardRouter: the first real policy set (P1).

Smart handling for combat (one-turn planner), map routing, events, card rewards,
rest sites, shops, reward-screen potion management, and in-combat potions.
Everything else (menus/navigation, overlays, minigames) delegates to the
TrivialRouter, which is already battle-tested plumbing.
"""

from __future__ import annotations

import dataclasses
import re
import time
import zlib
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
    _EMPIRICAL_MOVES,
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
from sts2bot.policy.forward import choose_mode, load_move_scripts
from sts2bot.policy.rollout import _EXHAUST_SELF, rollout_fight
from sts2bot.policy.textparse import (
    HITS_EVERYONE,
    parse_card_description,
    parse_hp_cost,
    parse_intent_damage,
)
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
# Summoner bosses: bodies the boss ADDS mid-fight, keyed by a substring of the boss
# name -> bestiary names of the summons. Consumed by _upcoming_boss (forecast side);
# the summons are minions in the Kin sense (threat, not kill-HP).
_BOSS_SUMMONS: dict[str, list[str]] = {"QUEEN": ["Torch Head Amalgam"]}
# Guarded summoner leaders (owner A/B 2026-08-02, both target orders taped on
# 373PFAE7EE): while her torch lives the Queen never attacks — she Buffs BOTH
# bodies and re-blocks ~20; the torch's death breaks the guard permanently (no
# resummon, block ends, she attacks at the dps her Buffs accumulated). Values:
# awakened base 18 + 2/turn of torch life ≈ the taped 35/19/Buff/50 pattern
# after a 7-turn phase 1. (self_block, awakened_dps, awakened_buff_per_turn)
_BOSS_GUARDED: dict[str, tuple[int, int, int]] = {"QUEEN": (20, 18, 2)}
# Relic -> card-type draft synergy: holding the relic makes that TYPE more
# favorable to draft (owner 2026-07-31, Mummified Hand). Values are nudges on
# the catalog scale (take threshold ~4), not mandates.
_RELIC_TYPE_DRAFT_BONUS: dict[str, tuple[str, float]] = {
    "MUMMIFIED_HAND": ("Power", 2.0),
}
# Stage bosses: (hp, dps) per sequential stage, owner-tape-observed (2026-07-30,
# Test Subject #C29 full fight): stage transitions FULL-HEAL to the next pool
# (100 -> 200 -> 300; his '#C__' suffix varies per run but every variant is ONE
# entity through all stages -- the bestiary's per-variant entries are run
# fragments, not stages). Stage 3 carries Nemesis (intangible every other turn,
# unmodeled -- the real fight is tougher than these numbers say) and dps 40 is
# the observed 12x3/45-single alternation.
_BOSS_STAGES: dict[str, list[tuple[int, int]]] = {
    "TEST SUBJECT": [(100, 19), (200, 36), (300, 40)],
}


def _draws_blocked(player) -> bool:
    """In-turn draws are dead: NO_DRAW status (Battle Trance) OR a Fiddle-class
    relic ('you may not draw cards during your turn' — no status is surfaced,
    owner 2026-07-31)."""
    if any("NO_DRAW" in (st_.id or "").upper() for st_ in (player.status or [])):
        return True
    return any(re.search(r"not draw (?:any )?cards? during your turn",
                         getattr(r_, "description", None) or "", re.IGNORECASE)
               for r_ in (player.relics or []))


def _desperation_active(w, cur_act: int, act_floor: int, elites_this_act: int,
                        dfs_boss_loss: float | None, max_hp: int) -> bool:
    """Owner rule 2026-08-02: a run with 0 elites late into the act is on the
    slow-loss track, and a DFS boss forecast reading near-unwinnable makes a
    risky elite strictly better than the certain boss loss. Either condition
    lowers the elite gate's bar."""
    zero_elite_late = (elites_this_act == 0
                       and act_floor >= w.desperation_zero_elite_floor)
    boss_doomed = (dfs_boss_loss is not None
                   and dfs_boss_loss >= w.desperation_boss_loss_pct * max_hp)
    return zero_elite_late or boss_doomed


def _boss_is_known(bestiary: dict, boss_name: str) -> bool:
    """A boss the forecast machinery can price: a direct bestiary entry, OR a stage
    boss whose suffix-stripped base is in the observed table (GLTQT0XBN7 2026-07-31:
    the run's 'Test Subject #C31' variant wasn't a bestiary key, so BOTH DFS gates
    fell back to history and the 600-HP stage model never got asked)."""
    if not boss_name:
        return False
    if bestiary.get(boss_name):
        return True
    return boss_name.split("#")[0].strip().upper() in _BOSS_STAGES
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
    # Aeonglass (owner full decode 2026-08-28; sketch in logs/reports/
    # aeonglass_draft_sketch.md, evidence n=194 era fights): mass-exhaust
    # decks survived her at 45% vs 18% with no tools — UNDER the old planner
    # that gave the clears zero credit — so the tool bonus rises and Stoke/
    # Second Wind are named tech. Big blocks premiumed (her damage scales
    # quadratically via Increasing Intensity; matches Vantom/Kaiser rows).
    # Powers get a mild bump: one PLAY for permanent value is the most
    # Withering-Presence-efficient card class, and her fights always run
    # long. Deliberately absent: vuln dock (survival was FLAT across vuln
    # package sizes, 31/28/29% — Artifact 3 delays, doesn't disable);
    # cheap_spam_dock (new knob, held for owner review with the setup arm).
    "AEONGLASS": {"exhaust_tool_bonus": 3.0,
                  "card_bonus": {"STOKE": 1.5, "SECOND_WIND": 1.5},
                  "min_block": 9, "block_bonus": 2.0,
                  "power_bonus": 1.25},
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


@dataclasses.dataclass(frozen=True)
class _EnemyView:
    """Lightweight live-enemy view for the multiturn oracle (choose_mode)."""

    name: str
    entity_id: str
    hp: int
    block: int
    asleep: bool = False
    intangible: bool = False  # live status read (Test Subject P3 Nemesis)
    # live intent damage THIS turn (player-visible ground truth) — the setup
    # gate must not trust script forecasts for the current turn (Queen f48
    # 2026-08-19: script blended unbuffed turns, read a 75-damage awakened
    # beat as safe at 58 hp -> 58->3 on a "setup" turn)
    incoming: int = 0


@dataclasses.dataclass(frozen=True)
class _ShopCardView:
    """ShopItem's card_* fields reshaped for the draft scorer (_card_score)."""

    id: str | None
    name: str | None
    type: str | None
    cost: str | None
    star_cost: str | None
    rarity: str | None
    description: str | None
    is_upgraded: bool = False

# Enchant riders as they render appended to card text (Spiral shows as
# "Replay N" -- live shape 2026-07-12). Used only to tell an enchanted basic
# from its plain twin on permanent-removal screens.
_ENCHANT_TEXT_RE = re.compile(
    r"\b(nimble|sharp|slither|swift|sown|adroit|momentum|imbued"
    r"|perfect fit|replay \d)\b", re.IGNORECASE)


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
        # multiturn P4: harvested + wiki-verified turn scripts for the oracle
        self.move_scripts = load_move_scripts()
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
                # fight count by (act, floor) — decide() polls many times per fight,
                # so a bare counter would run hot; seen_at records the count when an
                # elite FIRST appeared (recurrence rule, owner 2026-07-29: a seen
                # elite won't recur until 3 elites have been fought)
                floors = ctx.screen_mem.setdefault("elite_floors", set())
                if state.run:
                    floors.add((state.run.act, state.run.floor))
                seen_at = ctx.screen_mem.setdefault("elites_seen_at", {})
                for e in state.battle.enemies or []:
                    if e.name:
                        seen.add(e.name.upper())
                        seen_at.setdefault(e.name.upper(), len(floors))
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

    def _note_relic_enchant(self, item, ctx: LoopContext) -> None:
        """A purchased/picked relic whose pickup enchants ('Enchant up to 3
        Attacks with Sharp 3') opens a NAMELESS target screen next -- carry the
        kind exactly like event-choice enchants (owner catch 2026-08-13:
        Throwing Axe's Sharp never reached the picker; Strikes got the enchant
        while Dismantle+ sat filtered out)."""
        desc = getattr(item, "relic_description", None) or ""
        if m := re.search(r"enchant[^.]*?with (\w+)", desc, re.IGNORECASE):
            kind = m.group(1).lower()
            if kind in self._ENCHANT_KINDS:
                ctx.screen_mem["pending_enchant"] = kind

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

    def _fight_plan(self, state: CombatState, ctx: LoopContext) -> str | None:
        """Fight-open plan selection (Kin A/B 2026-07-30): the owner's scaling deck
        killed the Followers first and won where the bot's static race lost; his June
        fight raced the same boss and won — "no one strategy... it requires a fine
        judgment of your bursting ability". So judge per fight: roll out both target
        orders ("sweep" low-HP-first vs "focus" big-body-first) with THIS deck at
        round 1 and commit to a clear winner; ties -> None (no bias). Cached per
        fight signature; ~100ms once per multi-enemy fight."""
        w = self.config.combat
        player = state.player
        if not w.use_fight_plan or player is None or not player.deck:
            return None
        b = state.battle
        if b is None:
            return None
        alive = [e for e in b.enemies or [] if (e.hp or 0) > 0]
        if len(alive) == 1:
            # Solo drain/clock boss (Matriarch A/B 2026-07-30: owner burst 222 HP
            # in ~3 post-sleep rounds and won taking 25, where the bot ground 18
            # turns into the drain spiral): time pressure makes the fight a pure
            # race — bias damage-forward, no rollout comparison needed.
            name = (alive[0].name or "").upper()
            drainer = any(k in name and (p.get("drains_player") or p.get("death_timer"))
                          for k, p in _EMPIRICAL_MOVES.items())
            return "focus" if drainer else None
        if len(alive) < 2:
            return None
        if any("REATTACH" in (st_.id or "").upper()
               for e in alive for st_ in (e.status or [])):
            # Reattach segments: the planner's futile-kill rule governs, not sweep/focus
            return None
        sig = ((state.run.floor if state.run else 0),
               tuple(sorted((e.name or "") for e in alive)))
        cache = ctx.screen_mem.setdefault("fight_plans", {})
        if sig in cache:
            return cache[sig]
        cur_act = min(int(state.run.act or 1) if state.run else 1, 3)
        ehp, edps, eramp = _GENERIC_ELITE.get(cur_act, _GENERIC_ELITE[1])
        members = []
        for e in alive:
            dps = realized_dps(self.enemy_dps, e.name or "", edps)
            entry = self.bestiary.get(e.name or "")
            if entry:
                m = bestiary_enemy(entry, dps=dps, name=e.name or "")
                m = FightEnemy(**{**m.__dict__, "hp": e.hp or m.hp})
            else:
                m = FightEnemy(hp=e.hp or ehp, dps=dps, str_ramp=eramp)
            members.append(m)
        rolls = {
            order: rollout_fight(player.deck, members, int(player.hp),
                                 int(player.max_hp),
                                 card_effects=self.card_effects,
                                 potions=player.potions, relics=player.relics,
                                 n=16, target_order=order)
            for order in ("sweep", "focus")
        }
        s, f = rolls["sweep"], rolls["focus"]
        plan = None
        if f.win_rate - s.win_rate > 0.10:
            plan = "focus"
        elif s.win_rate - f.win_rate > 0.10:
            plan = "sweep"
        elif f.p25_end_hp - s.p25_end_hp > 5:
            plan = "focus"
        elif s.p25_end_hp - f.p25_end_hp > 5:
            plan = "sweep"
        # Queen A/B 2026-08-02: when BOTH orders project a loss the margins
        # collapse to ~0 and no plan was committed — the per-turn DFS then
        # flipped targets mid-fight (Queen 4 rounds, torch 2) and split 203
        # damage across two bodies with neither dying. In losing positions
        # coherence matters MOST: commit to the less-bad order anyway.
        # Tie-break: pessimistic tail, then kill progress, then sweep (killing
        # the dps source first is the safer human default vs summoners).
        if plan is None and max(s.win_rate, f.win_rate) < 0.15:
            if abs(f.p25_end_hp - s.p25_end_hp) > 1:
                plan = "focus" if f.p25_end_hp > s.p25_end_hp else "sweep"
            elif abs(f.exp_enemy_hp_left - s.exp_enemy_hp_left) > 1:
                plan = ("focus" if f.exp_enemy_hp_left < s.exp_enemy_hp_left
                        else "sweep")
            else:
                plan = "sweep"
        cache[sig] = plan
        return plan

    @staticmethod
    def _combat_sig(state: CombatState) -> tuple | None:
        """Everything a resolved combat action would visibly change. None while
        the battle block is missing (mid-load) — the guard never holds on it."""
        player, battle = state.player, state.battle
        if player is None or battle is None:
            return None
        return (
            battle.round, battle.turn, battle.is_play_phase, battle.actions_disabled,
            player.energy, player.block, player.hp,
            tuple((c.name, c.index) for c in (player.hand or [])),
            tuple((e.entity_id, e.hp) for e in battle.enemies),
            tuple(p.slot for p in (player.potions or [])),
        )

    def _combat(self, state: CombatState, ctx: LoopContext) -> Decision | Wait:
        # Kaiser Crab freeze (373PFAE7EE): long resolution chains (Pillage with a
        # Replay enchant + a death animation) run for seconds while the bot's
        # 0.15s polls replan and fire more plays + end-turn into the animation —
        # the engine's scripted move wedges (the owner's hand replay of the exact
        # same sequence is clean; guard-v1's release-on-first-change re-froze it
        # because the chain mutates state EVERY poll). v2: an action is sent only
        # when the state has been QUIESCENT (signature identical) for the last N
        # polls, and a sent action must visibly land before the next one.
        sig = self._combat_sig(state)
        limit = self.config.combat.action_settle_polls
        quiesce = self.config.combat.action_quiesce_polls
        holds = ctx.screen_mem.get("settle_holds", 0)
        pending = ctx.screen_mem.get("action_settle")
        if sig is not None and pending is not None and holds < limit:
            if sig == pending.get("sig"):
                ctx.screen_mem["settle_holds"] = holds + 1
                return Wait(reason="last combat action not yet reflected "
                            f"(settle {holds + 1}/{limit})")
            stable = ctx.screen_mem.get("sig_stable")
            if not isinstance(stable, dict) or stable.get("sig") != sig:
                stable = {"sig": sig, "n": 0}
            stable["n"] += 1
            ctx.screen_mem["sig_stable"] = stable
            if stable["n"] < quiesce:
                ctx.screen_mem["settle_holds"] = holds + 1
                return Wait(reason="combat action resolving (quiesce "
                            f"{stable['n']}/{quiesce}, hold {holds + 1}/{limit})")
        if (sig is not None and pending is not None and holds >= limit
                and sig == pending.get("sig") and pending.get("card_index") is not None):
            # the settle window expired with the state UNCHANGED after a play:
            # the game refused it (batch stall 2026-09-03: Stomp resubmitted at
            # 0 energy until the stall rail). Exclude that card for the rest of
            # the turn so the replan finds something else or ends the turn.
            key = (state.run.floor if state.run else -1,
                   state.battle.round if state.battle else -1)
            ref = ctx.screen_mem.get("refused_cards")
            if not isinstance(ref, dict) or ref.get("key") != key:
                ref = {"key": key, "idx": []}
            if pending["card_index"] not in ref["idx"]:
                ref["idx"].append(pending["card_index"])
            ctx.screen_mem["refused_cards"] = ref
        ctx.screen_mem.pop("action_settle", None)
        ctx.screen_mem.pop("sig_stable", None)
        ctx.screen_mem["settle_holds"] = 0  # gate passed (or capped): fresh budget
        decision = self._combat_inner(state, ctx)
        if (sig is not None and isinstance(decision, Decision) and isinstance(
                decision.action, (act.PlayCard, act.UsePotion, act.EndTurn))):
            ctx.screen_mem["action_settle"] = {
                "sig": sig,
                "card_index": (decision.action.card_index
                               if isinstance(decision.action, act.PlayCard) else None)}
            # plays-this-turn counter (Slow seeding; exhaust-snapshot family)
            if isinstance(decision.action, act.PlayCard) and state.battle is not None:
                tp = ctx.screen_mem.get("turn_plays")
                key = (state.run.floor if state.run else -1, state.battle.round)
                if not isinstance(tp, dict) or tp.get("key") != key:
                    tp = {"key": key, "n": 0, "attacks": 0, "skills": 0, "powers": 0}
                tp["n"] += 1
                # play-KIND counts too: per-turn relic cadences must survive a
                # mid-turn replan (Kusarigama lethal missed, arm v3 run 4)
                played = next((c for c in (state.player.hand if state.player else [])
                               if c.index == decision.action.card_index), None)
                ptype = (getattr(played, "type", "") or "").lower()
                kind = ("attacks" if ptype == "attack" else
                        "powers" if ptype == "power" else "skills")
                tp[kind] = tp.get(kind, 0) + 1
                # Unmovable seeding: the turn's one block-doubling is spent by
                # the first card that grants Block (owner 2026-09-04)
                if re.search(r"gain \d+ block", getattr(played, "description", "") or "",
                             re.IGNORECASE):
                    tp["blocked"] = True
                ctx.screen_mem["turn_plays"] = tp
        return decision

    def _combat_inner(self, state: CombatState, ctx: LoopContext) -> Decision | Wait:
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
        fp = self._fight_plan(state, ctx)
        # Multiturn P4 (owner-reviewed table only): the oracle's mode takes
        # precedence over the sweep/focus rollout comparison for table fights.
        # Mode -> planner: race/guard_break = focus bias on the PLAN's target
        # ("race" also devalues small blocks per the Matriarch review);
        # defend_deadline = "defend" on recurring deadline turns (Kaiser Laser
        # T4/T9/...), race toward the target otherwise; setup_window = hands
        # off (the sleeper machinery already governs).
        mode_target: str | None = None
        mplan = None
        if state.battle is not None and state.player is not None:
            views = [
                _EnemyView(
                    name=e.name or "", entity_id=e.entity_id or "",
                    hp=e.hp or 0, block=e.block or 0,
                    asleep=any((s.id or "").upper().startswith("ASLEEP")
                               for s in (e.status or [])),
                    intangible=any((s.id or "").upper().startswith("INTANGIBLE")
                                   for s in (e.status or [])),
                    incoming=sum(parse_intent_damage(i.label)
                                 for i in (e.intents or [])
                                 if (i.type or "").lower() == "attack"),
                )
                for e in (state.battle.enemies or []) if (e.hp or 0) > 0
            ]
            mplan = choose_mode(views, state.player, self.move_scripts,
                                card_effects=self.card_effects,
                                current_round=state.battle.round or 1,
                                experimental_setup=tuple(
                                    self.config.combat.setup_burst_experimental))
            if mplan.mode == "race":
                fp = "race"
                mode_target = mplan.target
            elif mplan.mode == "guard_break":
                # NOT a race (Queen forensics 2026-08-13, 15 fights: 4 died
                # in-guard, the rest 1-3 rounds post-break -- and the owner's
                # tracker note says humans beat the Queen MOST OFTEN, so the
                # losses are bot-specific). The guard phase is PAID SETUP
                # time: only the minion attacks (~25/turn rent), so small
                # blocks stay fully valued (race's devaluation was stripping
                # defense against the rent) and the long 400-hp fight ahead
                # keeps powers front-loaded via the normal focus economics.
                fp = "focus"
                mode_target = mplan.target
            elif mplan.mode == "defend_deadline":
                cycle = int(mplan.detail.get("cycle") or 0)
                rnd = state.battle.round or 1
                dl = mplan.deadline_turn or 0
                on_deadline = (rnd == dl or
                               (cycle > 0 and rnd > dl and (rnd - dl) % cycle == 0))
                fp = "defend" if on_deadline else "race"
                mode_target = mplan.target
            elif mplan.mode == "burst_window":
                # Test Subject P3 (owner green-lit 2026-08-18): the boss's LIVE
                # Intangible caps attacks at 1 dmg/hit, so intangible turns are
                # block/setup turns ("defend") and open turns unload ("race").
                # P1/P2 never show Intangible -> always "race" (status quo).
                fp = "race" if mplan.detail.get("attack_now") else "defend"
                mode_target = mplan.target
            elif mplan.mode == "setup_turn":
                # Setup-then-burst (owner answers 2026-08-18): a cheap boss turn
                # banks powers/draws/scaling; the burst-flip in choose_mode
                # returns "race" instead once the kill is within reach.
                fp = "setup"
                mode_target = mplan.target
        # turn-start exhaust-pile snapshot (owner 2026-08-03): lets the planner
        # know a card was ALREADY exhausted this turn across replans, so
        # Forgotten Ritual / Evil Eye-class conditionals stay live mid-turn
        pile_now = getattr(state.player, "exhaust_pile_count", None) or 0
        exmem = ctx.screen_mem.get("turn_exhaust0")
        floor_now = state.run.floor if state.run else -1
        if (not isinstance(exmem, dict) or exmem.get("round") != round_
                or exmem.get("floor") != floor_now):
            exmem = {"round": round_, "floor": floor_now, "pile": pile_now}
            ctx.screen_mem["turn_exhaust0"] = exmem
        tp = ctx.screen_mem.get("turn_plays")
        tp_live = (tp if isinstance(tp, dict)
                   and tp.get("key") == (floor_now, round_) else {})
        plays_now = tp_live.get("n", 0)
        kinds_now = (tp_live.get("attacks", 0), tp_live.get("skills", 0),
                     tp_live.get("powers", 0))
        ref = ctx.screen_mem.get("refused_cards")
        refused = (frozenset(ref["idx"])
                   if isinstance(ref, dict) and ref.get("key") == (floor_now, round_)
                   else frozenset())
        # Vuln-dependency scaling for the strip credit (owner 2026-08-29):
        # payoff providers in the DECK (tag lens) raise the value of eating
        # Artifact charges — a Dominate/Bully package starves behind charges.
        vuln_dep = 0.0
        for c in (state.player.deck if state.player else None) or []:
            entry = self.draft_tags.get((c.id or "").upper()) or {}
            vuln_dep += float((entry.get("provides") or {}).get(
                "vulnerable_payoff", 0.0))
        w_ = self.config.combat
        strip_mult = 1.0 + w_.artifact_strip_payoff_mult * min(
            vuln_dep, w_.artifact_strip_payoff_cap)
        plan = plan_combat_turn(state, self.config.combat,
                                artifact_strip_mult=strip_mult,
                                used_potion_slots=tuple(pused["slots"]),
                                hold_aoe_potions=self._aoe_hold(state, ctx),
                                fight_plan=fp,
                                focus_target=mode_target,
                                exhausted_this_turn=pile_now > exmem["pile"],
                                plays_this_turn=plays_now,
                                kinds_this_turn=kinds_now,
                                excluded_indices=refused,
                                block_used_this_turn=bool(tp_live.get("blocked")),
                                debuff_wipe_hp=(
                                    int(mplan.detail.get("wipe_hp") or 0)
                                    if mplan is not None
                                    and mplan.detail.get("staged") else 0))
        if fp and isinstance(plan, Decision) and plan.rationale:
            plan.rationale += f" |plan={fp}"
            if mplan is not None and mplan.mode:
                plan.rationale += f" |mode={mplan.mode}"
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
        # death-rider save BEFORE hail-mary potions: if The Gambit fully saves the
        # turn, the belt stays banked for the fight it just bought us
        rider_save = self._death_rider_save(state, plan)
        if rider_save is not None:
            return rider_save
        potion_play = self._combat_potion(state, ctx, plan,
                                          mode_target=mode_target)
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
        no_draw = _draws_blocked(player)
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
        shredder = None
        energy_gen = None
        for card_ in player.hand or []:
            if not card_.can_play:
                continue
            fx = parse_card_description(card_.description)
            if fx.draw > 0 and fx.self_hp_cost < player.hp and not no_draw:
                target = self._target_for(card_, state)
                return Decision(
                    action=act.PlayCard(card_index=card_.index, target=target),
                    rationale=f"desperation draw: {card_.name} (incoming {incoming} vs "
                    f"{player.hp} HP — dig for answers)",
                )
            d_ = (card_.description or "").lower()
            if "exhaust your hand" in d_ and "random card" in d_:
                shredder = card_  # Stoke-class: reroll the whole hand
            elif fx.energy_gain > 0 and fx.self_hp_cost < player.hp:
                energy_gen = card_
        # Emergency Stoke (owner live 2026-07-30): no survivable line -> shredding
        # the hand IS a reroll, and it works under NO_DRAW (adds aren't draws).
        # Bank energy first if a generator is playable — the lane re-fires next
        # poll and the shred then plays with more energy for whatever it finds.
        if shredder is not None:
            if energy_gen is not None:
                return Decision(
                    action=act.PlayCard(card_index=energy_gen.index,
                                        target=self._target_for(energy_gen, state)),
                    rationale=f"bank {energy_gen.name} before the emergency shred "
                    f"(incoming {incoming} vs {player.hp} HP)",
                )
            return Decision(
                action=act.PlayCard(card_index=shredder.index,
                                    target=self._target_for(shredder, state)),
                rationale=f"emergency shred: {shredder.name} rerolls the hand "
                f"(incoming {incoming} vs {player.hp} HP)",
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

    def _death_rider_save(self, state: CombatState, plan) -> Decision | None:
        """The Gambit ('Gain 50 Block. If you take unblocked attack damage this
        combat, die.') is vetoed from every normal plan — a one-turn planner can't
        certify combat-long perfect blocking (delta audit). Owner edge case
        2026-07-31 (KD r7: 10 HP, proj loss 52, cost-0 Gambit playable through the
        whole doomed turn): when THIS turn already kills us, the veto inverts —
        certain death now loses to conditional death later, and the save carried
        real kill equity next turn."""
        battle, player = state.battle, state.player
        if battle is None or player is None:
            return None
        if battle.turn != "player" or battle.is_play_phase is False:
            return None
        if battle.actions_disabled:
            return None
        incoming = sum(
            parse_intent_damage(i.label)
            for e in battle.enemies if e.hp > 0
            for i in e.intents if i.type.lower() == "attack"
        )
        proj_loss = incoming - (player.block or 0)
        if isinstance(plan, Decision) and plan.scores and "hp_loss" in plan.scores:
            proj_loss = plan.scores["hp_loss"]
        if proj_loss < player.hp:
            return None  # not doomed: the veto stands
        for card_ in player.hand or []:
            if not card_.can_play:
                continue
            fx = parse_card_description(card_.description)
            if not fx.self_death_rider or fx.block <= 0:
                continue
            if incoming - (player.block or 0) - fx.block < player.hp:
                return Decision(
                    action=act.PlayCard(card_index=card_.index, target=None),
                    rationale=(f"death-rider save: {card_.name} blocks {fx.block} "
                               f"(proj loss {proj_loss:.0f} >= {player.hp} HP) — "
                               "certain death now loses to conditional death later"),
                )
        return None

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
        self, state: CombatState, ctx: LoopContext, plan: Decision | Wait | None = None,
        mode_target: str | None = None,
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

        # Entropic-refill visibility (owner catch 2026-08-03, KD win with an
        # undrunk Liquid Bronze): the Brew MINTS potions mid-fight, after the
        # boss-start deploy lanes' round gates have closed. Snapshot the belt
        # when the fight is FIRST seen (even if empty -- the early-outs below
        # must not skip this); later arrivals are FRESH and the deploy lanes
        # waive their round gates for them.
        floor_now = state.run.floor if state.run else -1
        belt_mem = ctx.screen_mem.get("fight_belt_r1")
        if not isinstance(belt_mem, dict) or belt_mem.get("floor") != floor_now:
            belt_mem = {"floor": floor_now,
                        "ids": {f"{p.slot}:{p.id}" for p in player.potions or []}}
            ctx.screen_mem["fight_belt_r1"] = belt_mem

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

        def fresh(p: Potion) -> bool:
            return f"{p.slot}:{p.id}" not in belt_mem["ids"]

        def first(*want: str) -> Potion | None:
            return next((p for p in available if cat[p.slot] in want), None)

        # 0. Entropic Brew-class (owner 2026-07-31): 'Fill all available potion
        #    slots' is free value whenever every OTHER slot is empty — banking it
        #    as a future potion bank is overthinking. After it resolves, the next
        #    poll re-reads the belt, so the hail-mary lane naturally re-evaluates
        #    the new potions (stateless per-poll re-decision).
        if len(player.potions) == 1:
            lone = player.potions[0]
            if (lone.slot not in used_slots
                    and re.search(r"fill all .*potion slots",
                                  lone.description or "", re.IGNORECASE)):
                return drink(lone, None, f"drink {lone.name} (belt otherwise "
                                         "empty: free refill)")

        # 1. Hail-mary (run 10: died holding buff potions): dying even after our cards
        #    block — throw a potion, preferring one that can actually save us.
        if w.hail_mary and hp_pct < w.drink_when_hp_pct_below and proj_loss >= player.hp:
            # Foul-class guard (owner-caught 2026-07-20: hail-mary at 9 HP drank Foul
            # Potion, "Deal 10 damage to EVERYONE" — the drinker included — a certain
            # suicide traded for a merely-PROJECTED death; projections carry ~15%
            # error, so that margin is real). Never fall back to a self-lethal potion.
            def _self_lethal(p: Potion) -> bool:
                # Text drift bit this guard (live 2026-07-30: Foul's text became
                # "Deal 12 damage to ALL players and enemies" — no EVERYONE — and
                # the bot drank a 12-damage suicide at 6 HP). HITS_EVERYONE is the
                # shared single-source pattern for drinker-in-the-blast texts.
                if HITS_EVERYONE.search(p.description or ""):
                    return (parse_card_description(p.description).total_damage
                            >= player.hp)
                return False

            # Fallback ordering (owner catch 2026-08-29, seed-A r7: Swift
            # drunk first drew 3 usable cards, then Bottled Potential FLUSHED
            # all of them — belt-slot order wasted the Swift 100%). Junk hand
            # -> reroll-class first (draws stack ON a reroll, never the
            # reverse); near-viable hand -> draw first (maybe save the reroll).
            live = sum(1 for c in (player.hand or [])
                       if c.can_play and (c.type or "") not in ("Status", "Curse"))
            def _arming_only(p: Potion) -> bool:
                # Duplicator-class (owner catch 2026-08-30, Queen death-by-1:
                # hail-mary drank it, the plan doubled an ATTACK, the planned
                # Defend evaporated to a mid-plan lane): an arming potion is
                # no rescue unless the double CAN be defensive. Skip it when
                # no block/heal card is playable this turn.
                if not re.search(r"(played? |plays? it )?an extra time|played twice",
                                 p.description or "", re.IGNORECASE):
                    return False
                for c in player.hand or []:
                    if not c.can_play:
                        continue
                    fxc = parse_card_description(c.description)
                    if fxc.block > 0 or fxc.heal > 0:
                        return False  # a defensive double exists: drinkable
                return True

            def _fallback_rank(p: Potion) -> int:
                desc = (p.description or "").lower()
                reroll = "shuffle" in desc and "draw pile" in desc
                draws = parse_card_description(p.description).draw > 0
                if live <= 2:  # junk hand
                    return 0 if reroll else (1 if draws else 2)
                return 0 if draws else (1 if reroll else 2)
            potion = first("block", "heal", "aoe_damage", "damage") or next(
                iter(sorted((p for p in available
                             if not _self_lethal(p) and not _arming_only(p)),
                            key=_fallback_rank)), None)
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

        # 3b. Regen Potion (owner 2026-08-02): 'Gain 5 Regen' = 5+4+3+2+1 = 15 HP
        #     streamed over 5 turns -- worthless in short fights, premium in long
        #     ones. Boss/elite rule: drink the moment HP drops below max-5 (the
        #     first tick can't overheal, and bosses easily run the 5-turn clock).
        #     Overheal edges (post-boss ancient heal, A3+ 80%% boss heal) waved off
        #     by the owner as overthinking.
        if dangerous and player.hp < player.max_hp - 5 and (rg := first("regen")):
            return drink(rg, None,
                         f"drink {rg.name} (start the regen clock at "
                         f"{player.hp}/{player.max_hp})")

        # 3c. Heart of Iron-class Plating (owner 2026-08-02): ~28 block streamed
        #     over 7 turns -- a long-fight clock. Deploy at boss/elite start;
        #     normal fights end before it pays out, so hold it there.
        if (dangerous and (pl_ := first("plating")) is not None
                and (round_ <= 2 or fresh(pl_))):
            return drink(pl_, None,
                         f"drink {pl_.name} ({state.state_type}: plating clock)")

        # 4a. Card-generating potions (Skill/Attack/Power/Colorless/Orobic): drop
        #     immediately at a BOSS or ELITE start (owner 2026-07-29: "obvious turn 1
        #     plays") — the generated cards compound over the fight's length, and held
        #     ones historically died in the belt or fired as pointless hail-maries
        #     (owner 2026-07-09). Window is two rounds so a buff (4b) also lands.
        if ((state.state_type in ("boss", "elite") or frond)
                and (cg := first("card_gen")) is not None
                and (round_ <= 2 or fresh(cg))):
            return drink(cg, None,
                         f"drink {cg.name} ({state.state_type} start: bank cards early)")

        # 4a-3. Powdered Demise-class DoT throw (owner 2026-08-02): 'target loses
        #     9 HP at the end of each of its turns' -- premium at bosses/elites,
        #     thrown at the biggest body (the leader for minion bosses; on the
        #     Decimillipede the max-HP segment approximates the owner's 'a part
        #     not otherwise targeted', since kill lines chew from the low end).
        #     Caveats (owner): it's a STATUS -- Artifact charges eat it, so skip
        #     charged targets (a later poll rethrows once charges are stripped);
        #     vs the staged Test Subject hold for the 300-HP final stage.
        if dangerous and (dot := first("dot_throw")):
            alive = [e for e in state.battle.enemies if e.hp > 0]

            def _artifacted(e) -> bool:
                return any("ARTIFACT" in f"{s.id or ''} {s.name or ''}".upper()
                           and (s.amount or 0) > 0 for s in e.status)

            staged = any("TEST SUBJECT" in (e.name or "").upper() for e in alive)
            if not (staged and not any((e.max_hp or 0) >= 300 for e in alive)):
                dot_tgts = [e for e in alive if not _artifacted(e)]
                if dot_tgts:
                    dt = max(dot_tgts, key=lambda e: e.hp)
                    return drink(dot, dt.entity_id,
                                 f"throw {dot.name} at {dt.name} (DoT clock on "
                                 f"{dt.hp} HP)")

        # 4. Proactive at an elite/boss start: deploy long-term buffs/debuffs early (the
        #    bot struggles with these fights, so bank the value rather than hoard it).
        if (dangerous and (buff := first("buff")) is not None
                and (round_ <= 1 or fresh(buff))):
            return drink(buff, None, f"drink {buff.name} (deploy at {state.state_type} start)")

        # 4-d. Enemy-debuff potions (Beetle Juice 'deals 30% less damage for 4
        #     turns' -- owner 2026-08-06): throw on the FIRST turn the target
        #     shows a DAMAGING intent (round 1 is often a Buff turn; a blind
        #     early throw wastes duration). It's a STATUS: Artifact eats it, so
        #     charged targets are skipped and a later poll rethrows post-strip.
        #     Reapplication extends duration (not stacking) and it's independent
        #     of Weak -- both fine to layer, no special casing needed.
        # Staged-boss hold (owner 2026-08-28, TS f48: Weak Potion thrown r1 at
        # phase 1): Test Subject's revive WIPES statuses, and early phases hit
        # softest — hold debuff potions until the final-phase body (max_hp
        # >= 250; P3 is 300). The card-side debuff-waste guard knew this; the
        # potion lane didn't.
        ts_early_phase = any(
            "TEST SUBJECT" in (e.name or "").upper()
            and (e.hp or 0) > 0 and (e.max_hp or 0) < 250
            for e in state.battle.enemies)
        if dangerous and not ts_early_phase and (db := first("debuff")) is not None:
            unshielded = [e for e in state.battle.enemies
                          if (e.hp or 0) > 0
                          and not any("ARTIFACT" in f"{s.id or ''} {s.name or ''}".upper()
                                      and (s.amount or 0) > 0 for s in e.status)]
            # Vulnerable is an OFFENSIVE debuff -- it amplifies damage WE deal
            # INTO the target, so it goes on the fight plan's KILL target, not
            # the biggest attacker (owner catch 2026-08-23: Vuln Potion thrown
            # at Crusher while every attack went to the mode target Rocket;
            # 'first damaging intent' is Beetle Juice/Weak defensive logic).
            if "vulnerab" in (db.description or "").lower():
                dt = next((e for e in unshielded
                           if (e.entity_id or "") == (mode_target or "")), None)
                why = "the fight-plan target"
                if dt is None and unshielded:
                    dt = max(unshielded, key=lambda e: e.hp or 0)
                    why = "biggest HP"
                if dt is not None:
                    return drink(db, dt.entity_id,
                                 f"throw {db.name} at {dt.name} ({why})")
            atkers = [e for e in unshielded
                      if any((i.type or "").lower() == "attack" for i in e.intents)]
            if atkers:
                dt = max(atkers, key=lambda e: e.hp or 0)
                return drink(db, dt.entity_id,
                             f"throw {db.name} at {dt.name} (first damaging intent)")

        # 4a-2. Cost-zero potions (Touch of Insanity): deploy early at a boss,
        #     but ONLY when a worthy target (cost >= 2) is in hand — the owner nuance:
        #     turn 1 full of cheap cards -> WAIT for the turn the 3-cost shows up.
        if dangerous and (cz := first("cost_zero")) is not None:
            # Round gate REMOVED 2026-08-30: it contradicted the lane's own
            # wait-for-a-worthy-target design (a 3-cost first appearing r5+
            # found the window already shut). Worthy targets come from the
            # HAND (TOI-class) or the DISCARD (Liquid Memories-class).
            src = ((player.discard_pile or [])
                   if "discard pile" in (cz.description or "").lower()
                   else (player.hand or []))
            costs = [int(c.cost) for c in src
                     if c.cost and str(c.cost).lstrip("-").isdigit()]
            # Worthy = cost>=2; owner softening 2026-08-30: if the DECK holds
            # no >=2 at all, a boss-fight free-play on a 1-cost beats letting
            # the potion rot.
            deck_has_2 = any(
                c.cost and str(c.cost).lstrip("-").isdigit() and int(c.cost) >= 2
                for c in (player.deck or []))
            bar = 2 if deck_has_2 else 1
            if costs and max(costs) >= bar:
                ctx.screen_mem["pending_enchant"] = "cost_zero"  # target screen: max cost
                return drink(cz, None,
                             f"drink {cz.name} (cost-zero the {max(costs)}-cost)")

        # 4a-4. Fix-the-hand (owner rule 2026-08-29, queue #9): a junk hand
        #     facing real damage is the reroll's moment — 'the turn was going
        #     to be awful unless I did this.' Junk = <=2 live non-status
        #     cards. (Ordering vs draw potions: #12's rule in the hail-mary;
        #     here the reroll IS the trigger's answer.)
        if dangerous and (rr := first("hand_reroll")) is not None:
            live_n = sum(1 for c in (player.hand or [])
                         if c.can_play and (c.type or "") not in ("Status", "Curse"))
            incoming_now = sum(
                parse_intent_damage(i.label)
                for e in state.battle.enemies if (e.hp or 0) > 0
                for i in (e.intents or []) if (i.type or "").lower() == "attack")
            if live_n <= 2 and incoming_now >= 10:
                return drink(rr, None,
                             f"fix the hand: {rr.name} ({live_n} live cards vs "
                             f"{incoming_now} incoming)")

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
            no_draw = _draws_blocked(player)
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
        if re.search(r"loses? \d+ hp at the end of each", potion.description or "",
                     re.IGNORECASE):
            # Powdered Demise-class enemy DoT (owner 2026-08-02) -- own throw lane
            return "dot_throw"
        if re.search(r"gain \d+ plating", potion.description or "", re.IGNORECASE):
            # Heart of Iron-class (owner 2026-08-02): Plating N = decaying
            # end-of-turn block, ~N(N+1)/2 over N turns -- a long-fight clock
            # like Regen; own boss/elite deploy lane, held in normal fights
            return "plating"
        if re.search(r"gain \d+ buffer", potion.description or "", re.IGNORECASE):
            # Lucky Tonic-class (owner 2026-08-02): 1 Buffer absorbs ONE damage
            # instance of any size. Optimal use = the enemy's biggest single-hit
            # turn, which needs the multiturn planner -- PARKED by owner. Until
            # then: high keep-value, no proactive lane (hail-mary fallback may
            # still drink it facing death, where absorbing an instance is right).
            return "buffer"
        if re.search(r"gain \d+ ritual", potion.description or "", re.IGNORECASE):
            # Mazaleth's Gift (owner 2026-08-03): Ritual = +1 Str at end of EVERY
            # turn -- compounding, i.e. the definition of a boss/elite-start
            # buff. Rides deploy lane 4 (round 1 + Entropic-fresh waiver).
            return "buff"
        if ("REGEN" in nid
                or re.search(r"gain \d+ regen", potion.description or "", re.IGNORECASE)):
            # Regen Potion (owner 2026-08-02): heal streamed over 5 turns; its own
            # boss/elite deploy lane drinks it -- categorized so it ranks like a
            # heal for keep-value and never falls to the 'other' bucket
            return "regen"
        if any(k in nid for k in ("SKILL", "ATTACK", "COLORLESS", "POWER POTION",
                                  "OROBIC")):
            # Orobic Acid: 3 random cards, free this turn — a turn-1 tempo bomb
            # (owner 2026-07-29: obvious turn-1 play at bosses/elites)
            return "card_gen"
        # "[Selected] card costs 0 for the rest of this fight" (owner 2026-07-29,
        # Touch of Insanity; matched by TEXT so the exact name doesn't matter):
        # a targeted cost-zero is a per-fight engine — deploy early in big fights,
        # but only when a WORTHY target is in hand (see the boss-deploy lane).
        # Text drift (owner catch 2026-08-28, TS f48 tape): the live wording is
        # now "It is free to play this combat" — the old costs-0 phrasing
        # stopped matching, TOI fell to "other", and the hail-mary drank it
        # pointlessly at r10 while its deploy lane sat unreachable.
        if re.search(r"(costs? 0|free to play).*(rest of )?(this|the) (fight|combat|turn)",
                     potion.description or "", re.IGNORECASE | re.DOTALL):
            # 'this turn' variant added 2026-08-30 (owner catch: Liquid
            # Memories — 'Put a card from your Discard Pile into your Hand.
            # It's free to play this turn.' — sat as 'other' through a won
            # Queen fight, hail-mary-only; the TOI text-drift bug's sibling)
            return "cost_zero"
        low_d = (potion.description or "").lower()
        if "shuffle" in low_d and "draw pile" in low_d:
            # Bottled Potential-class full reroll: held for the moment the
            # hand is junk (owner self-A/B 2026-08-29: spending the belt
            # early on the identical fight LOST where holding won)
            return "hand_reroll"
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
        # White Star (epoch relic, owner 2026-08-02): elites drop an extra RARE
        # card reward — a flat sweetener on every winnable elite while held.
        sword_bonus += w.white_star_elite_bonus if any(
            "WHITE_STAR" in (r.id or "").upper() or "WHITE STAR" in (r.name or "").upper()
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
        # Juzu Bracelet (owner 2026-07-30): '?' rooms never roll normal fights.
        # NB the HP projection never charged '?' nodes for potential combat, so
        # there is no penalty to remove — this is the upside-only score bump
        # (guaranteed event/treasure/shop EV beats the fight-diluted pool).
        juzu_bonus = 2.0 if any("JUZU" in n for n in held_relics) else 0.0
        # Eternal Feather (owner relic check 2026-07-30): heal 3 per 5 deck cards on
        # ENTERING a rest site — no rest required, so it stacks on top of whatever
        # the campfire is spent on and rewards rest-dense routes even when smithing.
        feather_heal = (3.0 * (len((player.deck if player else None) or []) // 5)
                        if any("ETERNAL" in n and "FEATHER" in n
                               for n in held_relics) else 0.0)
        # Pantograph (owner relic check 2026-07-30): +25 at boss-combat start — the
        # projection heals BEFORE charging the boss loss.
        boss_entry_heal = 25.0 if any("PANTOGRAPH" in n for n in held_relics) else 0.0
        # Regal Pillow (owner relic check 2026-07-30): +15 when you actually REST —
        # unlike the feather it rides the rest heal itself, which is what the DP's
        # rest-site step already assumes the campfire is spent on.
        pillow_heal = 15.0 if any("REGAL" in n and "PILLOW" in n
                                  for n in held_relics) else 0.0

        # Relic-conditional node bonuses (owner GO 2026-08-20; act-3 A/B
        # Decision 3: they diverted LEFT for a double-shop line BECAUSE Music
        # Box rewards optionality -- path_value had no relic term). Curated
        # phase-1 table; texts verified against relic_catalog/relic_notes.
        _relic_node = {
            "MUSIC_BOX": ("shop", 5.0),       # optionality: more shopping = more combo pieces
            "SHOVEL": ("rest_site", 5.0),     # dig: a free relic per rest site
            "DREAM_CATCHER": ("rest_site", 3.0),  # rest offers a card draft
            # (Meal Ticket deliberately absent: its 15-heal already rides the
            # HP projection via shop_heal above -- a flat bonus would double-count)
            "COURIER": ("shop", 4.0),         # -20% + endless stock: each visit worth more
            "MEMBERSHIP_CARD": ("shop", 4.0),  # -50%: ditto
        }
        relic_node_bonus: dict[str, float] = {}
        for rid, (ntype, amt) in _relic_node.items():
            if any(rid in n for n in held_relics):
                relic_node_bonus[ntype] = relic_node_bonus.get(ntype, 0.0) + amt

        next_row = min(o.row for o in opts)

        def type_score(node_type: str | None, row: int | None = None) -> float:
            t = (node_type or "unknown").lower()
            base = {
                "monster": w.score_monster,
                "unknown": w.score_unknown + juzu_bonus,
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
                base += relic_node_bonus.get("rest_site", 0.0)
            if t == "shop":
                base += relic_node_bonus.get("shop", 0.0)
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
        act_now = min(int(state.run.act or 1), 3) if state.run else 1
        elite_entry_pct = ({2: w.elite_entry_min_hp_pct_act2,
                            3: w.elite_entry_min_hp_pct_act3}.get(act_now)
                           or w.elite_entry_min_hp_pct)
        deck_too_small = bool(
            w.elite_min_deck_cards
            and len((player.deck if player else None) or []) < w.elite_min_deck_cards)
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
        gate_detail: dict[str, float] | None = None  # pass-side evidence (Phrog audit
        # 2026-07-30: a passing gate logged NOTHING, so a bad pass left no numbers)
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
            # Recurrence sharpening (owner rule 2026-07-29; Gardeners f7 death NE6CSNNX2Y
            # was a 4/6 pool gamble that drew a 0.0-win member): an elite seen this act
            # can't recur until 3 elites have been fought, so it shouldn't dilute the
            # pool the gate gambles on. Keep the full pool if everything is excluded.
            fresh = self._fresh_elite_pool(pool, ctx)
            pool = fresh or pool
            if pool:
                members_by_name = {
                    name: elite_fight_members(name, entry, self.bestiary,
                                              dps=realized_dps(self.enemy_dps, name, edps),
                                              str_ramp=eramp, dps_table=self.enemy_dps)
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
                    # Desperation coupling (owner rule 2026-08-02): zero elites
                    # late in the act, or a near-unwinnable DFS boss forecast,
                    # lowers the bar -- a risky elite beats a certain slow loss.
                    floor_now = state.run.floor if state.run else 0
                    act_floor = floor_now - {1: 0, 2: 17, 3: 34}.get(cur_act, 0)
                    elites_this_act = sum(
                        1 for (a, _f) in (ctx.screen_mem.get("elite_floors") or ())
                        if a == cur_act)
                    desperate = _desperation_active(
                        w, cur_act, act_floor, elites_this_act,
                        self._dfs_boss_loss(ctx, player, cur_act), int(max_hp))
                    eff_bar = (w.rollout_gate_win_rate
                               - (w.desperation_gate_discount if desperate else 0.0))
                    eff_floor = floor_hp * (0.5 if desperate else 1.0)
                    won_n = sum(
                        1 for r in rolls
                        if r.win_rate >= eff_bar
                        and r.p25_end_hp >= eff_floor
                    )
                    can_win_elite = won_n >= len(pool) * w.elite_gate_pool_win_frac
                    losses = sorted(max_hp - r.exp_end_hp for r in rolls)
                    est_elite_loss = losses[len(losses) // 2]
                    gate_detail = {
                        "gate_desperate": 1.0 if desperate else 0.0,
                        "gate_won_n": float(won_n),
                        "gate_pool_n": float(len(pool)),
                        "gate_min_win": round(min(r.win_rate for r in rolls), 2),
                        "gate_min_p25": round(min(r.p25_end_hp for r in rolls), 1),
                    }
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
            # Calibration arm (2026-09-03): the rollout's pool-median loss and
            # win verdicts are era-miscalibrated (config.py elite_loss_source);
            # observed mode prices the elite from the bot's own history and
            # leaves survivability to the HP projection (+ entry floor).
            if w.elite_loss_source == "observed" and self.combat_stats is not None:
                obs = self.combat_stats.expected_loss("elite", stat=w.elite_loss_stat)
                if obs is not None:
                    est_elite_loss = float(obs)
                    can_win_elite = True
            boss_members = self._upcoming_boss(ctx, cur_act)
            if boss_members:
                boss_name = ctx.screen_mem.get("act_boss_name", "")
                obs_boss = (self.combat_stats.expected_loss("boss")
                            if (w.boss_loss_source == "observed"
                                and self.combat_stats is not None) else None)
                if obs_boss is not None:
                    # observed history (p75) + the act-3 bump the rest gate uses
                    est_boss_loss = float(obs_boss) + (
                        self.config.rest.act3_boss_loss_bonus if cur_act >= 3 else 0.0)
                    use_dfs = False
                else:
                    use_dfs = (self.config.map.use_dfs_boss_rollouts
                               and _boss_is_known(self.bestiary, boss_name))
                if use_dfs:
                    # P1.7: DFS-policy rollout for the KNOWN boss, cached per
                    # (deck, boss, belt) -- ~1.1s fresh, free on cache hits
                    # cache key: deck + boss only (2026-07-30: keying on the belt
                    # too busted the cache ~14x/run for ~10s max stalls; potions
                    # rarely flip a boss estimate materially)
                    key = (boss_name,
                           tuple(sorted((c.id or "", bool(c.is_upgraded))
                                        for c in player.deck)))
                    cache = ctx.screen_mem.setdefault("boss_roll_cache", {})
                    if key in cache:
                        est_boss_loss = cache[key]
                    else:
                        t0 = time.perf_counter()
                        timing: dict = {}
                        roll = rollout_fight(
                            player.deck, boss_members, int(max_hp), int(max_hp),
                            card_effects=self.card_effects,
                            potions=player.potions, relics=player.relics,
                            n=self.config.map.dfs_boss_rollout_n,
                            policy="dfs",
                            combat_weights=self._dfs_forecast_weights,
                            timing_out=timing,
                        )
                        est_boss_loss = max_hp - roll.exp_end_hp
                        cache[key] = est_boss_loss
                        boss_ms = timing.get("ms", (time.perf_counter() - t0) * 1e3)
                        ctx.screen_mem["last_boss_ms"] = round(boss_ms, 1)
                elif est_boss_loss is None:
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
                # entry floor (calibration arm): never route INTO an elite below
                # this HP fraction -- era elite deaths entered at ~63% HP
                if elite_entry_pct and hp < max_hp * elite_entry_pct:
                    return hp_after, -w.route_death_penalty
                if deck_too_small:  # near-starter deck: no elite yet (arm v4)
                    return hp_after, -w.route_death_penalty
            elif t == "boss":
                hp_after = min(max_hp, hp + boss_entry_heal) - fight_loss("boss")
            elif t in ("restsite", "rest_site"):
                # feather_heal fires on ENTRY (before the rest/smith choice);
                # pillow_heal only when resting, which this step assumes
                return (min(max_hp, hp + feather_heal + pillow_heal
                            + w.rest_heal_pct * max_hp), 0.0)
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

        # Winged Boots charge-aware lookahead (owner catch 2026-08-03: the bot
        # spent TWO jumps -- rest, jump, rest -- where on-path-rest-THEN-jump
        # buys the same line for one; the old lookahead walked only graph
        # children, so plan-a-jump-later was unrepresentable). Jump edges: from
        # any node, any next-row node is reachable at boots_jump_cost with one
        # fewer charge; memo carries the charge dimension.
        boots_charges = 0
        for r_ in ((player.relics if player else None) or []):
            if "WINGED" in f"{r_.id or ''} {r_.name or ''}".upper():
                boots_charges = min(3, r_.counter if r_.counter is not None else 3)
        nodes_by_row: dict[int, list] = {}
        for n_ in state.map.nodes:
            nodes_by_row.setdefault(n_.row, []).append(n_)

        memo: dict[tuple[int, int, int, int], float] = {}

        def path_value(col: int, row: int, hp: float, charges: int = 0) -> float:
            key = (col, row, int(hp) // 4, charges)
            if key in memo:
                return memo[key]
            node = node_by_pos.get((col, row))
            if node is None:
                memo[key] = 0.0
                return 0.0
            memo[key] = 0.0  # cycle guard (map is a DAG, but be safe)
            hp_after, adj = project(node.type, row, hp) if hp_aware else (hp, 0.0)
            future = max(
                (path_value(c_col, c_row, hp_after, charges)
                 for c_col, c_row in node.children),
                default=0.0,
            )
            if charges > 0:
                kid_set = {tuple(c) for c in node.children}
                jump_future = max(
                    (path_value(j.col, j.row, hp_after, charges - 1)
                     - w.boots_jump_cost
                     for j in nodes_by_row.get(row + 1, [])
                     if (j.col, j.row) not in kid_set),
                    default=float("-inf"),
                )
                future = max(future, jump_future)
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
            is_jump = bool(cur_kids and (opt.col, opt.row) not in cur_kids)
            charges_after = max(0, boots_charges - (1 if is_jump else 0))
            kid_pairs = ([(c.col, c.row) for c in opt.leads_to]
                         or [(c_col, c_row) for c_col, c_row in (
                             node_by_pos.get((opt.col, opt.row)).children
                             if node_by_pos.get((opt.col, opt.row)) else [])])
            future = max(
                (path_value(c_col, c_row, hp_after, charges_after)
                 for c_col, c_row in kid_pairs),
                default=0.0,
            )
            # a remaining charge can also jump FROM this option's node next floor
            # (the owner's one-charge line: on-path rest, THEN jump past its elite)
            if charges_after > 0:
                jump_future = max(
                    (path_value(j.col, j.row, hp_after, charges_after - 1)
                     - w.boots_jump_cost
                     for j in nodes_by_row.get(opt.row + 1, [])
                     if (j.col, j.row) not in set(kid_pairs)),
                    default=float("-inf"),
                )
                future = max(future, jump_future)
            score = type_score(opt.type, opt.row) + adj + w.path_step_discount * future
            if is_jump:
                score -= w.boots_jump_cost
            scored[f"{opt.index}:{opt.type}"] = round(score, 2)
            if score > best_score:
                best_score, best = score, opt
        assert best is not None
        if gate_ms is not None:
            scored["gate_ms"] = round(gate_ms, 1)  # owner: latency data matters
        if gate_detail:
            scored.update(gate_detail)
        if ctx.screen_mem.get("last_boss_ms") is not None:
            scored["boss_ms"] = ctx.screen_mem.pop("last_boss_ms")
        if state.map.boss and state.map.boss.name:
            # cache the act's boss name (known after Neow) so post-combat drafting, where the map
            # isn't in state, can price cards against the *real* boss (§5-C / ENEMY_PASS).
            ctx.screen_mem["act_boss_name"] = state.map.boss.name
        boss_row = state.map.boss.row if state.map.boss else None
        if boss_row is not None and best.row == boss_row - 1:
            ctx.screen_mem["pre_boss"] = True  # arriving on the last row before the boss
        else:
            ctx.screen_mem.pop("pre_boss", None)
        # Pre-elite campfire flag (config.rest.rest_before_elite_hp_pct): the DP
        # priced this campfire as a heal; tell _rest_site when its best
        # continuation is an elite so the heal actually happens.
        pre_elite = False
        if hp_aware and (best.type or "").lower() in ("restsite", "rest_site"):
            hp_rest, _adj = project(best.type, best.row, cur_hp)
            kids = [(c.col, c.row) for c in best.leads_to] or [
                tuple(c) for c in (node_by_pos[(best.col, best.row)].children
                                   if (best.col, best.row) in node_by_pos else [])]
            if kids:
                nxt = max(kids, key=lambda k: path_value(k[0], k[1], hp_rest, boots_charges))
                nxt_node = node_by_pos.get(nxt)
                nxt_type = (nxt_node.type if nxt_node else next(
                    (c.type for c in best.leads_to if (c.col, c.row) == nxt), None)) or ""
                pre_elite = nxt_type.lower() == "elite"
        if pre_elite:
            ctx.screen_mem["pre_elite"] = True
        else:
            ctx.screen_mem.pop("pre_elite", None)
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
                esat = {}
                for o, heur, _vs in scored:
                    entry = self.ancient_boons.get(o.title or "")
                    if entry:
                        esat[o.index] = self._boon_energy_sat(entry, deck, player)
                        vals[o.index] = (float(entry.get("value", 0.0))
                                         + self._boon_deck_fit(entry, deck)
                                         - esat[o.index])
                    else:
                        vals[o.index] = min(heur, _UNKNOWN_BOON_CAP)
                best_o = max(scored, key=lambda s: vals[s[0].index])[0]
                known = bool(self.ancient_boons.get(best_o.title or ""))
                sat_note = "".join(
                    f" |esat[{o.title}] -{esat[o.index]:.1f}"
                    for o, _h, _v in scored if esat.get(o.index, 0.0) > 0
                )
                return Decision(
                    action=act.ChooseEventOption(index=best_o.index),
                    rationale=(f"ancient boon: '{best_o.title}' "
                               f"({'catalog' if known else 'unknown, heur-capped'} "
                               f"{vals[best_o.index]:.1f})" + sat_note),
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
            # Skill over Power, 14.0 vs 13.8; owner: Power > Skill > Attack.
            # Man-Sized Holes 2026-07-30: SB's removal-loving 10.6 for 'Resist' is
            # blind to the Normality rider — owner: awful without a shop 1-2
            # combats away).
            catalog_first = (ev.event_id or "").upper() in (
                "TINKER_TIME", "FIELD_OF_MAN_SIZED_HOLES")
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

    def _boon_energy_sat(self, entry: dict, deck, player) -> float:
        """Energy-curve saturation discount (owner, act-3 A/B rep 1 2026-08-15): an
        energy boon is worth LESS to a deck already rich in energy sources — Earring's
        +1/turn is marginal next to Pyre. Weighted energy_source providers (deck cards
        plus owned boons) over the free allowance pay per-source, capped."""
        w = self.config.events
        esrc = float((entry.get("provides") or {}).get("energy_source", 0.0))
        if esrc <= 0 or not deck or not self.draft_tags:
            return 0.0
        from sts2bot.policy.drafttags import _providers, deck_tag_weights
        relics = getattr(player, "relics", None) if player else None
        relic_provides, _ = (
            boon_relic_context(relics, self.ancient_boons)
            if relics and self.ancient_boons else ({}, {})
        )
        have = _providers("energy_source", deck_tag_weights(deck), deck,
                          self.draft_tags, relic_provides)
        over = max(0.0, have - w.energy_sat_free_sources)
        return min(w.energy_sat_cap, w.energy_sat_per_source * esrc * over)

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
        # Star-cost trap (owner 2026-08-03, Prismatic Gem run: Ironclad drafted a
        # 3-star Reflect): Regent star-cost cards are DEAD in hand without a star
        # source — unlike cross-class 'gain 15 Block' cards, which just work.
        # Veto unless we're the Regent or the deck already generates stars.
        if getattr(card, "star_cost", None) not in (None, "", "0", 0):
            generates = character == "The Regent" or any(
                re.search(r"\bgain(s)? \d+ star|\bgenerate(s)? \d+ star",
                          getattr(c_, "description", None) or "", re.IGNORECASE)
                for c_ in (deck or []))
            if not generates:
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
        # Rainbow Ring (owner 2026-08-13; PER-TURN trigger, so every played
        # power is a potential trio turn): declining draft schedule -- full
        # bonus for the first Power, half while under ~1 power per 8 deck
        # cards, nothing beyond (owner: 'definitely possible to add too
        # many powers'; the cap encodes that without pretending precision).
        if relics and (card.type or "") == "Power" and any(
                "RAINBOW" in ((getattr(r, "id", "")
                               or getattr(r, "name", "") or "").upper())
                for r in relics):
            n_powers = sum(1 for c_ in (deck or [])
                           if (getattr(c_, "type", "") or "") == "Power")
            if n_powers == 0:
                score += w.rainbow_first_power_bonus
            elif n_powers < max(2, deck_size // 8):
                score += w.rainbow_first_power_bonus / 2
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
        # Fiddle-class (owner 2026-07-31): in-turn draws are DEAD while held, so a
        # draw rider is dead weight at draft time (the +2/turn is already banked).
        # EXEMPT (owner decode 2026-08-22, verified online): ALL start-of-turn
        # draw effects ignore Fiddle -- Predator's 'Next turn, draw 2',
        # Pael's Blood, Glow. Only in-turn draws are dead.
        if (fx.draw
                and not re.search(
                    r"next turn[^.]*draw|at the start of (?:your|each) turn"
                    r"[^.]*draw", card.description or "", re.IGNORECASE)
                and any(
                    re.search(r"not draw (?:any )?cards? during your turn",
                              getattr(r_, "description", None) or "",
                              re.IGNORECASE)
                    for r_ in relics or [])):
            score -= 2.0
        # Plain-relic -> card-TYPE draft synergies (owner 2026-07-31: Mummified Hand
        # — 'whenever you play a Power, a random card in hand costs 0' — makes
        # powers more favorable to draft; the in-fight discount rides per-poll
        # replanning for free, but the draft layer must see the pull).
        for r_ in relics or []:
            rid = f"{getattr(r_, 'id', '') or ''} {getattr(r_, 'name', '') or ''}".upper()
            for key, (syn_type, syn_bonus) in _RELIC_TYPE_DRAFT_BONUS.items():
                if key in rid and (card.type or "") == syn_type:
                    score += syn_bonus
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
            # exhaust TOOLING (Aeonglass Wither-removal): cards that exhaust
            # OTHER cards -- 'Exhaust a/your/all...' -- not the self-exhaust rider
            if boss_rule.get("exhaust_tool_bonus") and re.search(
                    r"exhaust (a|an|any|all|your|up to)",
                    card.description or "", re.IGNORECASE):
                score += boss_rule["exhaust_tool_bonus"]
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
        dps_prior, ramp = _ACT_BOSS.get(act, _ACT_BOSS[1])
        # Stage bosses: owner tape 2026-07-30 corrected the family-variant model —
        # every '#C__' Test Subject is ONE entity that full-heals through 3 stages
        # (100/200/300), so the stages come from the observed table, keyed on the
        # suffix-stripped base name. Same dormant-wave machinery as Phrog phase 2.
        base = boss_name.split("#")[0].strip().upper()
        if base in _BOSS_STAGES:
            return [
                FightEnemy(hp=hp_s, dps=dps_s, wave=wave)
                for wave, (hp_s, dps_s) in enumerate(_BOSS_STAGES[base])
            ]
        entry = self.bestiary.get(boss_name)
        if entry:
            dps = realized_dps(self.enemy_dps, boss_name, dps_prior)
            members = [bestiary_enemy(entry, dps=dps, name=boss_name, str_ramp=ramp)]
            # Summoner bosses (tape 2026-07-30, A36ZF0WVBS): the single-entry
            # forecast read the Queen as harmless (2.1 realized dps) while her
            # summoned Torch Head Amalgam swings 24.8 — a 95-HP entry died in 6
            # turns to a "2-dps" boss. Leader carries the kill-HP; summons add
            # dps but not kill-HP (counts_toward_kill=False — the Kin rule).
            for key, minions in _BOSS_SUMMONS.items():
                if key in boss_name.upper():
                    for mname in minions:
                        m_entry = self.bestiary.get(mname)
                        if m_entry:
                            members.append(bestiary_enemy(
                                m_entry,
                                dps=realized_dps(self.enemy_dps, mname, dps),
                                name=mname, counts_toward_kill=False))
                    # guarded leader (Queen): only meaningful once the minion
                    # actually joined the forecast — a lone guarded foe would
                    # read as a 0-dps fight
                    guard = _BOSS_GUARDED.get(key)
                    if guard and len(members) > 1:
                        blk, awd, buff = guard
                        members[0] = dataclasses.replace(
                            members[0], guarded_by_minions=True, self_block=blk,
                            awakened_dps=awd, awakened_buff_per_turn=buff)
            return members
        return [FightEnemy(*_GENERIC_BOSS)]

    @staticmethod
    def _fresh_elite_pool(pool: list, ctx: LoopContext) -> list:
        """Pool members that can actually appear behind the next elite node: a seen
        elite won't recur until 3 elite fights after its appearance (owner recurrence
        rule). seen_at holds the elite-fight count at first sighting; matching is by
        body name against the pool's bestiary key."""
        seen_at = ctx.screen_mem.get("elites_seen_at") or {}
        n_fought = len(ctx.screen_mem.get("elite_floors") or ())
        return [
            (name, entry) for name, entry in pool
            if (seen_at.get(name.upper()) is None
                or n_fought - seen_at[name.upper()] >= 3)
        ]

    @property
    def _dfs_forecast_weights(self):
        """Combat weights for FORECAST DFS rollouts (boss pricing): the live
        max_sequences cap, tightened to map.rollout_dfs_max_sequences. See the
        config comment -- forecast turns hit the full cap on branchy decks and
        one boss refresh cost ~19s of map-decision stall."""
        w = getattr(self, "_dfs_forecast_weights_cache", None)
        if w is None:
            w = self.config.combat.model_copy(update={"max_sequences": min(
                self.config.combat.max_sequences,
                self.config.map.rollout_dfs_max_sequences)})
            self._dfs_forecast_weights_cache = w
        return w

    def _dfs_boss_loss(self, ctx: LoopContext, player, cur_act: int) -> float | None:
        """P2b: THIS deck vs THIS boss loss estimate for the pre-boss rest gate,
        sharing the map block's cache (warm in practice — a map screen precedes every
        rest node with the same deck). None -> caller falls back to aggregate history.
        The Matriarch cluster (3 deaths from 62-64 HP) was the aggregate saying '~45
        needed' for a boss whose drain spiral the DFS sim actually models."""
        if self.config.map.boss_loss_source == "observed":
            return None  # calibration arm: callers fall back to observed history
        if not (self.config.map.use_dfs_boss_rollouts and player and player.deck):
            return None
        boss_name = ctx.screen_mem.get("act_boss_name") or ""
        if not boss_name:
            return None
        key = (boss_name,
               tuple(sorted((c.id or "", bool(c.is_upgraded)) for c in player.deck)))
        cache = ctx.screen_mem.setdefault("boss_roll_cache", {})
        if key in cache:
            return cache[key]
        if not _boss_is_known(self.bestiary, boss_name):
            return None  # unknown boss: nothing real to roll out against
        boss_members = self._upcoming_boss(ctx, cur_act)
        if not boss_members:
            return None
        max_hp = int(player.max_hp)
        roll = rollout_fight(player.deck, boss_members, max_hp, max_hp,
                             card_effects=self.card_effects, potions=player.potions,
                             relics=player.relics,
                             n=self.config.map.dfs_boss_rollout_n,
                             policy="dfs",
                             combat_weights=self._dfs_forecast_weights)
        loss = max_hp - roll.exp_end_hp
        cache[key] = loss
        return loss

    def _capability_deltas(
        self, deck, cards, max_hp: int, fights: list[list[FightEnemy]], relics=None
    ) -> dict[int, float]:
        """§5-C drafting: per card index, how much it improves the boss forecast in the
        *current deck's* context (deck-aware: a block-starved deck values block, a
        damage-starved one values damage). 2026-07-30 (KD audit: all 5 deaths were
        correctly forecast losses — the forecast was wasted because nothing upstream
        consumed it): priced by ROLLOUT delta, not estimate_fight — the static estimate
        is the calibration table's known-blind spot (engines, draw variance), and the
        rollout's exp_enemy_hp_left keeps the loss gradient the old progress() had.
        Needs the deck + harvested card text; if either is missing the term is skipped
        and drafting falls back to Elo/heuristics."""
        if not deck or not self.card_effects:
            return {}
        w = self.config.card_rewards

        def progress(r) -> float:
            # HP I'd retain minus the boss HP still standing: rewards getting *closer*
            # to the kill even in a loss (the usual boss case at draft time).
            return r.exp_end_hp - r.exp_enemy_hp_left

        # common random numbers: one seed from the BASE deck for every candidate, so
        # deltas compare like against like instead of re-seeding per candidate (a
        # per-candidate content seed made deltas a difference of two independent
        # noisy estimates — sigma comparable to the take threshold)
        seed = zlib.crc32(",".join(sorted(
            (getattr(c, "id", "") or "") for c in deck)).encode()) & 0x7FFFFFFF

        def roll(d, members):
            return rollout_fight(d, members, max_hp, max_hp,
                                 card_effects=self.card_effects,
                                 relics=relics, n=w.draft_rollout_n, rng_seed=seed)

        # Elite-pool retarget (owner 2026-08-02): early-act drafts price against
        # MULTIPLE target fights (the act's elite pool -- our best-calibrated
        # estimator, 3 floors away) and average; boss-targeting passes a single
        # fight as before. Chip-loss on normals remains unmodeled (owner note).
        bases = [roll(deck, m) for m in fights]
        base = sum(progress(b) for b in bases) / max(1, len(bases))
        deltas: dict[int, float] = {}
        clamp = w.capability_delta_clamp
        for c in cards:
            outs = [roll([*deck, c], m) for m in fights]
            prog = sum(progress(o) for o in outs) / max(1, len(outs))
            delta = w.capability_weight * (prog - base)
            delta = max(-clamp, min(clamp, delta))  # sim artifacts stay ordinal
            if (sum(o.win for o in outs) > len(outs) / 2
                    and not sum(b.win for b in bases) > len(bases) / 2):
                delta += w.capability_win_flip_bonus  # flips lose->win: prize it
            deltas[c.index] = delta
        return deltas

    def _draft_target_fights(self, ctx: LoopContext, cur_act: int, floor_now: int,
                             player) -> list[list[FightEnemy]]:
        """What the draft rollout prices against (owner 2026-08-02): EARLY in the
        act, the ELITE POOL (our best-calibrated estimator, 3 floors away -- the
        human 'pick something that beats act elites' proxy, measured); late-act
        and boss-floor rewards, the boss as before. Up to 3 pool fights spanning
        the kill-HP range, deltas averaged."""
        act_floor = floor_now - {1: 0, 2: 17, 3: 34}.get(cur_act, 0)
        if act_floor in (17, 33) or act_floor == 0:
            nxt = min(cur_act + 1, 3)
            dps, ramp = _ACT_BOSS.get(nxt, _ACT_BOSS[1])
            return [[FightEnemy(hp=_GENERIC_BOSS[0], dps=dps, str_ramp=ramp)]]
        if not self.config.card_rewards.use_elite_pool_targets:
            return [self._upcoming_boss(ctx, cur_act)]  # attribution arm: boss-only
        if act_floor >= 12:
            return [self._upcoming_boss(ctx, cur_act)]
        _ehp, edps, eramp = _GENERIC_ELITE.get(cur_act, _GENERIC_ELITE[1])
        pool = [
            (name, entry) for name, entry in self.bestiary.items()
            if "elite" in (entry.get("roles") or [])
            and cur_act in (entry.get("acts") or [])
            and (((entry.get("hp") or [0, 0])[1] or 0) >= 50
                 or any(k in name.upper() for k in _ELITE_COMPOSITIONS))
        ]
        pool = self._fresh_elite_pool(pool, ctx) or pool
        if not pool:
            return [self._upcoming_boss(ctx, cur_act)]
        fights = [
            elite_fight_members(name, entry, self.bestiary,
                                dps=realized_dps(self.enemy_dps, name, edps),
                                str_ramp=eramp, dps_table=self.enemy_dps)
            for name, entry in pool
        ]
        fights.sort(key=lambda ms: sum(m.hp for m in ms if m.counts_toward_kill))
        if len(fights) <= 3:
            return fights
        return [fights[0], fights[len(fights) // 2], fights[-1]]

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
        relics = state.player.relics if (state.player and state.player.relics) else None
        # Target selection (owner 2026-08-02): elite pool early in the act, the
        # boss late; boss-floor rewards price vs the NEXT act (the 2026-07-30
        # dead-boss catch lives inside _draft_target_fights now).
        floor_now = state.run.floor if state.run else 0
        cap = self._capability_deltas(
            deck, cr.cards, max_hp,
            self._draft_target_fights(ctx, run_act, floor_now, state.player),
            relics=relics)
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
        if "upgrade" in prompt:
            # true UPGRADE screens only: enchants target upgraded keepers too
            # (owner catch 2026-08-13: Dismantle+ was filtered out of a Sharp
            # pickup entirely -- the premium targets are exactly the + cards)
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
            # Nimble enchant (owner live catch 2026-08-09: the bot Nimble'd
            # Impervious 'Gain 30 Block. Exhaust.'): the rider pays out every
            # PLAY, so play-frequency across the run beats card quality. A
            # self-exhausting blocker fires once per fight and usually
            # overblocks -- worse value than a plain Defend. Prefer block
            # cards; among those, sticking around beats premium-but-
            # exhausting. (True multi-block cards would be the dream target;
            # Ironclad has none today, so there's nothing to detect.)
            if "nimble" in prompt:
                def nimble_key(c):
                    fxc = parse_card_description(c.description)
                    blocky = 1 if fxc.block > 0 else 0
                    sticky = int(bool(blocky) and not
                                 _EXHAUST_SELF.search(c.description or ""))
                    return (blocky, sticky, self._card_quality(c, character))
                return max(candidates, key=nimble_key)
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
                    # Dismantle-class conditional double-hit counts as multi-hit
                    # (owner check 2026-08-13: 'could hit twice' is Sharp-fed)
                    if fxc.hits >= 2 or fxc.double_hits_if_vuln:
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
            # Enchanted basics go LAST among basics on permanent removal
            # (owner 2026-08-09: the enchant is a small permanent asset --
            # strip the plain Defends first; the Nimble'd twin stays until
            # it's the only basic left). Scoped to Basic rarity so it can
            # only reorder twins, never shield a bad card class.
            if (prefer_worst and (c.rarity or "") == "Basic"
                    and any(v in prompt for v in ("remove", "destroy", "transform"))
                    and _ENCHANT_TEXT_RE.search(c.description or "")):
                q += 5.0  # basics -50 -> -45: after plain basics, before keepers
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
                # Record the pick: FORCED grid screens (no cancel/skip/confirm at
                # the grid stage — this event upgrade, the June enchant) satisfy
                # the needed==1-no-buttons arm and land here, but they TOGGLE and
                # raise a preview. Without recording, the next poll's pick-N path
                # selected AGAIN — toggling the card OFF under the open preview,
                # after which every confirm clicked a dead container (the owner's
                # double-selection theory, proven on the 2026-08-01 repro tape:
                # 'choose Taunt' + 'select best Taunt' back to back). True
                # choose-screens resolve instantly, so the record is harmless.
                if target.index not in picked:
                    picked.append(target.index)
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

        # Enough picked (or a previewed single pick): confirm — and NEVER clear the
        # pick-tracking while still on this screen. The June fix cleared on
        # preview_showing, which enabled the exact hang it targeted (owner-diagnosed
        # 2026-08-01, batch 51476 f3): one transiently-failed confirm with the
        # preview up -> picked cleared -> next poll RE-SELECTS Bash -> the game's
        # selection toggles OFF internally while the preview still shows -> confirm
        # no-ops for bot AND human alike. The owner's manual recovery was
        # back -> fresh select -> confirm; mirror it: re-confirm a few times, then
        # CancelSelection to reset the screen state and re-pick cleanly.
        if cs.can_confirm:
            # Settle-dwell BEFORE the first confirm (live dissection 2026-08-01 on
            # the owner's deterministic repro): a confirm fired during the
            # preview's opening animation wedges the preview container — after
            # that NO confirm lands (bot or human) until a cancel rebuilds it.
            # The same select+confirm with a 1s gap resolved instantly. Engine
            # animations run faster at 4x, so 3 polls of settle is generous.
            if mem.get("settle", 0) < 3:
                mem["settle"] = mem.get("settle", 0) + 1
                return Wait(reason=f"preview settling ({mem['settle']}/3) "
                                   "before confirm")
            # Livelock guard (owner-caught 2026-08-01 #2, upgrade screen): the
            # confirm->cancel->reselect cycle keeps the STATE changing, so the
            # stall rail never trips. A cycle counter that survives the cancel
            # caps recovery at 2 resets; after that, stop acting — the stall
            # rail aborts the run cleanly instead of ping-ponging forever.
            cyc_key = f"cardsel:cycles:{state.run.floor if state.run else 0}:{cs.prompt}"
            if ctx.screen_mem.get(cyc_key, 0) >= 2:
                return Wait(reason="card select: confirm unresolvable after 2 "
                                   "reset cycles; letting the stall rail abort")
            mem["confirms"] = mem.get("confirms", 0) + 1
            # Dwell between confirms: the transient class looks like confirm
            # racing the resolve animation — hammering (or worse, cancelling
            # mid-resolve) can abort a confirm that was actually landing.
            if mem["confirms"] % 2 == 0:
                return Wait(reason="confirm sent; dwell for the resolve animation")
            if mem["confirms"] <= 7:
                return Decision(
                    action=act.ConfirmSelection(),
                    rationale=f"confirm {len(picked)}/{needed} selected",
                )
            # stuck: reset like the owner did — cancel, clear tracking, re-pick
            ctx.screen_mem.pop(mem_key, None)
            ctx.screen_mem[cyc_key] = ctx.screen_mem.get(cyc_key, 0) + 1
            if cs.can_cancel or cs.can_skip:
                return Decision(
                    action=act.CancelSelection(),
                    rationale="confirm not resolving; cancel to reset the "
                              "selection state (owner recovery 2026-08-01)",
                )
            return Wait(reason="card select: confirm not resolving, no cancel")
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
            cur_act = state.run.act if state.run else 1
            # P2b: per-boss DFS estimate first — it models the mechanics the per-boss
            # bumps below hand-patch (drain spirals, clocks), so it replaces them too.
            dfs_est = self._dfs_boss_loss(ctx, player, cur_act)
            if dfs_est is not None:
                est = dfs_est
                src = f"DFS vs {ctx.screen_mem.get('act_boss_name', 'boss')}"
            else:
                # fall back: estimate the boss's likely HP cost from our own history.
                est = self.combat_stats.expected_loss("boss") if self.combat_stats else None
                if est is None:
                    est = w.default_boss_loss
                # Clock bosses (Knowledge Demon's Disintegration) cost more than the
                # aggregate boss history says — per-boss bump via _BOSS_DRAFT_RULES.
                rule = _boss_draft_rule(ctx.screen_mem.get("act_boss_name"))
                if rule:
                    est += rule.get("rest_loss_bonus", 0.0)
                # Act-3 bosses cost more than the act-1-dominated aggregate says
                if cur_act >= 3:
                    est += w.act3_boss_loss_bonus
                src = "history"
            needed = est * w.boss_safety_factor
            # Pantograph (owner relic check 2026-07-30): +25 HP at boss-combat START,
            # so the gate compares the post-heal entry, not the campfire HP.
            pantograph = 25 if any(
                "PANTOGRAPH" in f"{r.id or ''} {r.name or ''}".upper()
                for r in ((player.relics if player else None) or [])) else 0
            hp_at_boss = min(player.max_hp if player else hp, hp + pantograph)
            should_rest = hp_at_boss < needed
            panto_tag = f" (+{pantograph} Pantograph)" if pantograph else ""
            rest_why = (f"rest: {hp} HP{panto_tag} < ~{needed:.0f} needed for boss "
                        f"({src} est loss {est:.0f})")
            smith_why = (f"smith: {hp} HP{panto_tag} covers the boss "
                         f"(~{needed:.0f} needed, {src})")
        elif ctx.screen_mem.get("pre_elite") and w.rest_before_elite_hp_pct > 0:
            # the map DP priced this campfire as a heal ahead of an elite
            should_rest = hp_pct < w.rest_before_elite_hp_pct
            rest_why = (f"rest: {hp_pct:.0%} HP < {w.rest_before_elite_hp_pct:.0%} "
                        f"before the committed elite")
            smith_why = (f"smith: {hp_pct:.0%} HP covers the committed elite "
                         f"(>= {w.rest_before_elite_hp_pct:.0%})")
        else:
            should_rest = hp_pct < w.rest_below_hp_pct
            rest_why = f"rest at {hp_pct:.0%} HP"
            smith_why = f"smith (HP {hp_pct:.0%} is comfortable)"

        if should_rest and "rest" in enabled:
            return Decision(
                action=act.ChooseRestOption(index=enabled["rest"].index), rationale=rest_why
            )
        # Non-standard campfire actions (§8.4 class, 5 known members): relic/quest-added
        # options the fixed Rest/Smith menu was blind to — the Byrdonis Egg rode along
        # as a dead curse past 3 rest sites, Girya's Lift never fired, and two Ancient
        # boons (Pael's Growth / Meat Cleaver) were priced near-zero because their
        # actions were unreachable. Priority (owner guidance, Girya note 2026-06-25):
        # Hatch always (it's why the egg was taken) > Lift while healthy (permanent
        # +1 Str, <=3 uses) > Rekindle when the Pumpkin Candle runs low (owner
        # 2026-07-31: +1 energy/turn for 5 combats — Happy-Flower-plus; wasted if
        # charges are still high) > Cook when thinnables exist (remove 2, +9 max HP)
        # > Clone only if a Clone-enchanted card exists. Rest already won above.
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
            elif "dig" in nm:
                # Shovel (owner 2026-08-03): Dig = retrieve a random relic.
                # Relics are usually strict upsides (owner rule), so a dig beats
                # a smith; needed rests still win (the rest lane returns before
                # specials). Priority between Lift and Rekindle.
                specials.append((1.5, o, f"dig: random relic ({o.name})"))
            elif "rekind" in nm or "kindle" in nm:  # owner: likely 'Kindle';
                # NEVER OBSERVED LIVE (online description only) — matcher kept
                # generous; verify the real option id/name on first sighting
                cndl = next((r_ for r_ in ((player.relics if player else None) or [])
                             if "PUMPKIN" in f"{r_.id or ''} {r_.name or ''}".upper()),
                            None)
                charges = (cndl.counter if cndl and cndl.counter is not None else 0)
                # threshold 2 = a guess pending owner calibration: rekindling at
                # 4-5 charges wastes the campfire; at 0-2 it beats a smith
                if charges <= 2:
                    specials.append((2, o, f"rekindle the Pumpkin Candle "
                                           f"({charges} combats left -> 5)"))
            elif "cook" in nm and self._has_removable_card(player):
                specials.append((3, o, f"cook: remove 2 + max HP ({o.name})"))
            elif "clone" in nm and _deck_has_clone_enchant():
                specials.append((4, o, f"clone the enchanted card ({o.name})"))
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
        # Passive-/state fork mod (2026-08-10): the shopkeeper screen now PERSISTS
        # until we open the inventory (the old auto-open on poll is gone). Open
        # explicitly; the stable shopkeeper window also obsoletes the blind Foul
        # throw timing dance eventually (orchestrator keeps the blind hook for
        # pre-fork builds; on the fork the throw can land aimed, later refinement).
        if state.shop.inventory_open is False:
            return Decision(action=act.OpenShopInventory(),
                            rationale="open shop inventory (passive mod)")
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
                    self._note_relic_enchant(item, ctx)
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
                    # Deck-dependency gate (owner catch 2026-08-30: Chemical X
                    # bought for 218g with ZERO X-cost cards in a 26-card deck
                    # — the WAR prior is global, blind to the deck). A relic
                    # whose text names a card class the deck entirely lacks is
                    # a dead purchase; extend the table as classes surface.
                    rdesc = (item.relic_description or "").lower()
                    if (("cost x" in rdesc or "x cost" in rdesc
                         or "x-cost" in rdesc)
                            and not any(str(c.cost or "").upper() == "X"
                                        for c in deck)):
                        continue
                    if "shiv" in rdesc and not any(
                            "shiv" in (c.name or "").lower() for c in deck):
                        continue
                    relic_buys.append((v, price, item))
        if relic_buys:
            v, price, item = max(relic_buys, key=lambda x: x[0])
            bought.append(item.index)
            self._note_relic_enchant(item, ctx)
            return Decision(
                action=act.ShopPurchase(index=item.index),
                rationale=f"buy relic {item.relic_name} ({price}g, WAR/100g {v:+.3f})",
            )

        # 2.5 Cards that fill a missing deck role (owner 2026-08-12): scored by
        #     the DRAFT scorer, so the draft-tag provides/needs machinery prices
        #     the role fit exactly as at card rewards ('the deck needs an
        #     exhaust provider and True Grit+ is available'). The shop's one
        #     on_sale card gets a lowered bar ('particularly if on discount').
        #     Gold discipline: never dips into the removal reserve, one card
        #     per shop, and the bar sits above the free-reward take threshold.
        floor_now_shop = state.run.floor if state.run else -1
        cbuy = ctx.screen_mem.get("shop_card_buy")
        n_cards_bought = (cbuy.get("n", 0) if isinstance(cbuy, dict)
                          and cbuy.get("floor") == floor_now_shop else 0)
        if deck and player is not None and n_cards_bought < w.max_card_buys_per_shop:
            run_act = state.run.act if state.run else 1
            character = player.character
            region = (_act1_region(ctx.screen_mem.get("act_boss_name"))
                      if run_act <= 1 else None)
            card_buys = []
            for item in avail:
                price = item.gold_price or 0
                if (item.category != "card" or not item.can_afford
                        or gold - price < reserve):
                    continue
                view = _ShopCardView(
                    id=item.card_id, name=item.card_name,
                    type=item.card_type, cost=item.card_cost,
                    star_cost=item.card_star_cost, rarity=item.card_rarity,
                    description=item.card_description,
                    is_upgraded=(item.card_name or "").endswith("+"),
                )
                s = self._card_score(view, len(deck), character, run_act,
                                     deck=deck, relics=player.relics,
                                     region=region)
                bar = (w.buy_card_sale_min_score if item.on_sale
                       else w.buy_card_min_score)
                if s >= bar:
                    card_buys.append((s, -price, item))
            if card_buys:
                s, negp, item = max(card_buys)
                ctx.screen_mem["shop_card_buy"] = {"floor": floor_now_shop,
                                                   "n": n_cards_bought + 1}
                bought.append(item.index)
                return Decision(
                    action=act.ShopPurchase(index=item.index),
                    rationale=f"buy card {item.card_name} ({-negp}g, draft score "
                    f"{s:.1f}{', ON SALE' if item.on_sale else ''})",
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
                # Owner rule 2026-08-01 (left a late-act-3 shop holding ~1000g):
                # relics are USUALLY strict upsides — a negative Spirebird WAR is
                # correlational and must not veto a purchase made with dead gold.
                # Only ACTIVE-downside texts remain legitimate skips.
                desc = (item.relic_description or "").lower()
                if any(m in desc for m in downside_markers):
                    continue
                # Tungsten Rod vs a ==1-HP-cost engine (owner 2026-08-02): an
                # actively negative take even with dead gold
                if ("TUNGSTEN" in f"{item.relic_name or ''}".upper()
                        and self._one_hp_cost_cards(
                            state.player.deck if (state.player and state.player.deck)
                            else [])):
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
        # Fruit Juice on sight, OUT of combat (owner 2026-08-02, live miss: one sat
        # in the belt through a rest site and got traded at an event — the only
        # on-sight lane lived in _combat_potion, and the run never fought while
        # holding it). +Max HP compounds from the moment it's drunk (rest heals
        # scale off max), so the first legal screen is the right screen; rewards
        # is where potions are claimed AND where out-of-combat UsePotion is
        # live-proven (the drink-to-claim lane). Event/shop-acquired juice still
        # waits for the next rewards/combat — rest-site use is unverified API.
        if player is not None:
            juice = next((p for p in player.potions or []
                          if self._potion_category(p) == "fruit_juice"), None)
            if juice is not None:
                return Decision(
                    action=act.UsePotion(slot=juice.slot),
                    rationale=f"drink {juice.name} on sight (+max HP compounds; "
                    "never hold through a rest)")
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
                    skip = ctx.screen_mem.setdefault("reward_skip", set())
                    skip.add((run.floor, item.type, str(marker)))  # fallback skips these
        if player is not None and len(player.potions) >= player.max_potion_slots:
            potion_items = [i for i in state.rewards.items if i.type == "potion"]
            if potion_items and not ctx.screen_mem.get("discarded_for_reward"):
                # Owner corner case 2026-08-01 (belt of 2 Blood Potions + 1, a 3rd
                # Blood dropped, bot skipped it): with a FULL belt at a potion
                # reward, DRINKING a belt heal dominates skipping OR discarding —
                # even a paltry 5 HP at 95% is free value, and the claimed reward
                # refills the slot. Only heals qualify (their out-of-combat use
                # has value whenever hp < max); at full HP fall through to the
                # rank-based discard.
                if player.hp < player.max_hp:
                    heal = next((p for p in player.potions
                                 if self._potion_category(p) == "heal"), None)
                    if heal is not None:
                        return Decision(
                            action=act.UsePotion(slot=heal.slot),
                            rationale=(f"drink {heal.name} to free a belt slot "
                                       f"for the reward potion (heal beats "
                                       f"discard/skip at {player.hp}/{player.max_hp})"),
                        )
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

    def _one_hp_cost_cards(self, deck) -> list[str]:
        """Names of deck cards whose self-HP cost is EXACTLY 1 (Brand-class).
        Tungsten Rod's 'lose 1 less' zeroes that loss, breaking the card's own
        loss-keyed engine (owner 2026-08-02: costs of 2+ are unaffected)."""
        hits = []
        for c in deck or []:
            cid = (c.id or "").upper()
            up = 1 if getattr(c, "is_upgraded", False) else 0
            text = getattr(c, "description", None) or (
                (self.card_effects or {}).get(f"{cid}|{up}")
                or (self.card_effects or {}).get(f"{cid}|0") or "")
            if parse_card_description(text).self_hp_cost == 1:
                hits.append(c.name or cid)
        return hits

    def _relic_select(self, state: RelicSelectState, ctx: LoopContext) -> Decision | Wait:
        """Ancient / elite / treasure relic choice: take the highest-value relic by Spirebird raw
        WAR, not the first offered (the trivial fallback took relics[0] -> effectively random).
        Unknown relics get a neutral 0 (taken over a known-bad, not over a known-good relic)."""
        rs = state.relic_select
        if rs.relics:
            deck = state.player.deck if (state.player and state.player.deck) else []
            rod_conflicts = self._one_hp_cost_cards(deck)

            def war(relic) -> float:
                v = self.shop_stats.relic_war(relic.id) if self.shop_stats else None
                v = v if v is not None else 0.0
                # Tungsten Rod countersynergy (owner 2026-08-02): with Brand-class
                # ==1-HP-cost cards in the deck, 'lose 1 less' nulls the loss the
                # engine keys off — one of the game's few genuinely negative takes.
                if "TUNGSTEN" in f"{relic.id or ''} {relic.name or ''}".upper() and rod_conflicts:
                    v -= 800.0
                return v

            best = max(rs.relics, key=war)
            if war(best) < -400.0 and rs.can_skip:
                return Decision(
                    action=act.SkipRelicSelection(),
                    rationale=f"skip: Tungsten Rod vs 1-HP-cost engine "
                    f"({', '.join(rod_conflicts[:3])})")
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
        "damage": 4, "aoe_damage": 4, "card_gen": 4, "dot_throw": 4, "buff": 5,
        "plating": 5, "buffer": 6, "heal": 6, "regen": 6, "fruit_juice": 7,
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
