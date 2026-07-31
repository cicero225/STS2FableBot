"""Policy configuration: TOML in, typed sections out, hash recorded per run (FR-3.4)."""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "policy.toml"


class _Section(BaseModel):
    model_config = ConfigDict(extra="allow")


class CombatWeights(_Section):
    w_damage: float = 1.0
    w_kill: float = 25.0
    # Feed-class "If Fatal" rider: extra credit when THAT card lands the kill, enough to
    # win sequencing ties (vs another killer) but not to delay a safe lethal.
    w_on_fatal_bonus: float = 8.0
    # Ramp-stall (owner 2026-07-16, Damp Cultist turtle-death): vs a strength-ramping
    # enemy, a zero-damage turn is a losing equilibrium the one-turn horizon can't see —
    # block caps, the ramp doesn't. Flat penalty on damageless plans while a living
    # ramper exists; a one-turn approximation of the multi-turn race until §5-C in-fight.
    w_ramp_stall: float = -8.0
    # Armaments-class "Upgrade card(s) in your Hand" rider, per card upgraded: enough to
    # beat play friction when targets exist, not enough to displace block/lethal needs.
    w_hand_upgrade: float = 2.5
    # Relic pass R2: next-turn value credits for end-of-turn conditional relics
    # (Pael's Tears banked energy, Pocketwatch's deferred draw, Art of War).
    w_next_turn_energy: float = 2.0
    w_next_turn_draw: float = 1.0
    # Prolong-class block carryover: next-turn block per point snapshotted, discounted
    # vs w_block_useful for the unknown next-turn incoming (live 2026-07-25)
    w_next_turn_block: float = 0.6
    w_focus: float = 9.0
    w_overkill: float = -0.3
    # Block is valued both directly here AND via the avoided hp_loss below, which double-counts it
    # and makes the one-turn planner fully block incoming every turn and barely attack — so normal
    # fights drag 15+ rounds and chip-bleed it out (live: a Beetle+Wurm pack took 64->7 HP). Trim
    # the direct reward, and flatten the always-on HP-loss penalty so a HEALTHY bot trades a little
    # damage to end fights faster (the steep `slope` still makes it block hard when low). Stopgap
    # until real multi-turn fight planning (§5-C) — keep modest.
    w_block_useful: float = 0.8
    w_block_excess: float = -0.15
    w_hp_loss: float = -2.0
    hp_scarcity_base: float = 0.3
    hp_scarcity_slope: float = 2.0
    w_vulnerable: float = 6.0
    w_weak: float = 5.0
    w_strength: float = 7.0
    w_draw: float = 3.0
    w_energy_waste: float = -0.5
    w_play_friction: float = -0.35
    w_power_played: float = 8.0  # per-turn value of a banked Power; scaled by remaining-turns
    w_power_horizon_cap: float = 6.0  # cap on the remaining-turns multiplier for power value
    power_self_damage_hp_safe: float = 0.5  # HP% above which self-damage powers may front-load
    # Card self-HP costs (Bloodletting, Offering) are a TEMPO trade, not chip damage (owner
    # 2026-07-09: "play Bloodletting+ as low as 15 hp... unless it led to death"). While the turn's
    # projected end HP stays above the floor, charge them flat-cheap instead of the scarcity curve;
    # below the floor the full curve returns, and a turn projecting to death gets a hard wall.
    self_hp_cheap_floor: int = 15
    self_hp_cheap_mult: float = 0.4  # x w_hp_loss, scarcity-free, while above the floor
    w_projected_death: float = -500.0  # non-lethal turn that projects you to <=0 HP: never
    # Spend-reluctance per damage potion drunk inside a plan: big enough that a potion only
    # joins a line when it flips something real (lethal's w_kill=25 + the damage clears it;
    # casual chip never does). Potions persist across fights -- hoard by default.
    w_potion_spend: float = -18.0
    w_rage_sequence: float = 0.3  # nudge Rage before attacks even when its block reads as excess
    w_ramp_damage: float = 1.5  # extra value for damaging strength-gaining enemies (race them)
    # Fight-open plan selection (Kin A/B 2026-07-30: owner's scaling deck killed
    # the Followers first and won where the bot's static race-the-leader lost;
    # owner: "no one strategy" — so pick per fight by rolling out both target
    # orders at round 1). The chosen plan biases the DFS via these terms:
    use_fight_plan: bool = True
    w_plan_focus_damage: float = 0.8  # "focus": per damage point on the biggest body
    w_plan_sweep_kill: float = 15.0   # "sweep": per body cleared (stacks with w_kill)
    # Extra value for damaging a debuff CARRIER (Shrinker Beetle) while other enemies
    # live — its death lifts the player-debuff for the rest of the fight (owner 2026-07-17)
    w_carrier_damage: float = 1.5
    # Keeper attack played while Primal Force is active = PERMANENT downgrade to a
    # 16-dmg Giant Rock (owner 2026-07-18: "upgrade your strikes, not the attacks you
    # want to keep"). The DFS discovers keeper-BEFORE-PF ordering from this penalty.
    w_primal_keeper: float = -6.0
    # Thrash-class growth: exhausted attack's damage banks into the next play, plus
    # the thinning — granted only when all other hand attacks are fodder (owner
    # 2026-07-20: strikes are GOOD Thrash food; keepers must never be risked).
    w_exhaust_growth: float = 5.0
    w_crab_rage_split: float = -20.0  # small penalty for a 1-claw-dead split (1-turn enrage stall)
    max_sequences: int = 4000
    survival_status_threshold: int = 2
    # transient 'BlockedByHook' hands (engine mid-resolution) report every card
    # unplayable; re-poll up to this many times before trusting it (cost a boss
    # fight: a planned triple-Defend collapsed to one, 14 HP -> 3, run 33)
    hook_retry_limit: int = 12


class EventWeights(_Section):
    hp_cost_refuse_below: float = 0.45
    unknown_take_first_above: float = 0.70
    take_min: float = 0.5  # heuristic net-value floor to engage an option vs proceeding
    # catalog v2 (2026-07-21): unknown options with NO parsed cost engage at this
    # floor instead of declining — the event pool is EV-positive (Spirebird's own
    # data), so free-value walk-aways were the residual decline driver
    unknown_costless_floor: float = 2.5
    spirebird_take_floor: float = -2.0  # take Spirebird's top option unless heuristically harmful
    min_hp_pct_after_cost: float = 0.20  # never pay an event HP cost that drops below this


class MapWeights(_Section):
    score_monster: float = 10.0
    score_unknown: float = 12.0
    score_event: float = 12.0
    score_rest_site: float = 6.0
    score_shop: float = 4.0
    score_treasure: float = 14.0
    score_elite: float = -20.0
    score_boss: float = 0.0
    rest_bonus_per_missing_hp_pct: float = 0.45
    shop_bonus_per_100_gold: float = 6.0
    # Shops are valued at PROJECTED gold-on-arrival (owner's late-shop loop practice,
    # A/B #3: 740g -> two Act-3 sprees -> 8 relics): expected income per map row
    # between the current position and the shop node, so late shops outscore early ones.
    shop_gold_income_per_row: float = 12.0
    lookahead_discount: float = 0.35
    path_step_discount: float = 0.80
    # §8.2 HP-aware routing (active only when combat_stats is loaded). The DP projects HP along
    # each route using the bot's own per-fight p75 loss; these tune how it reacts.
    survival_floor_hp_pct: float = 0.10  # route projected to drop to/below this HP frac = "lethal"
    route_death_penalty: float = 80.0  # ...and pays this; dominates a node's own type score
    # a *survivable* elite earns elite_relic_value (vs score_elite -20 -> net +22, well above
    # treasure): relics are deck power, so chase elites when the HP is there to spend.
    # 36 -> 42 (A/B #5, 2026-07-24): the owner traded ~30 HP for 2 elites -> 7 relics vs
    # our 3 -> 27 vs 16 dmg/round at the boss. HP preservation without power is a
    # losing trade; the whole retune is owner-blessed for batch validation.
    elite_relic_value: float = 42.0
    rest_heal_pct: float = 0.30  # HP fraction a rest site restores, for the projection
    # Winged Boots charges are INSURANCE (owner 2026-07-29: jump to a rest when
    # desperate, to a shop when rich — not casual path upgrades; live: 2 of 3
    # charges burned on marginal jumps). Off-path options pay this, so only a
    # clearly better line (death-floor dodge, big value gap) spends a charge.
    boots_jump_cost: float = 12.0
    # Sword of Stone at 4/5 elites: the next elite ALSO completes Sword of Jade
    # (+3 Str permanent) -- worth a real nudge on top of the relic value when the
    # gate already says the fight is winnable (owner 2026-07-29).
    sword_completion_bonus: float = 8.0
    # P2a (2026-07-29): the elite gate judges the pool with Monte-Carlo ROLLOUTS
    # (calibrated: act-1 93%/95%, act-2 86%/81%) instead of the closed-form race.
    # Tail-aware: a pool member is "won" at win_rate >= rollout_gate_win_rate AND
    # p25 end HP >= the existing elite_gate_min_end_hp_pct floor. Boss estimates
    # stay closed-form until P1.7 (DFS-policy boss rollouts). Flag reverts to the
    # closed form if the batch A/B goes wrong. Gate latency is logged per decision
    # in scores["gate_ms"] (owner: the amount matters for iteration time).
    use_rollout_gate: bool = True
    # 0.60 -> 0.55 (owner "push a little", 2026-07-29): the first rollout-gate
    # batch traded aggression for safety (elites 1.9 -> 1.6/run, deaths 2 -> 0,
    # relics@f17 6.0 -> 4.8); buy some aggression back with the tail floor
    # (p25 >= elite_gate_min_end_hp_pct) still standing guard.
    # KEPT at 0.55 (owner decision 2026-07-30): deep scan found 0.55 ~ 0.60 on
    # elite outcomes with zero attributable deaths; "I prefer slightly more
    # aggression if it has no discernable downside."
    rollout_gate_win_rate: float = 0.55
    # P1.7 (2026-07-30): KNOWN bosses are priced by DFS-policy rollouts (the real
    # one-turn planner drives each simulated turn) -- backtest: 52% predicted vs
    # greedy's 38% (actual 65%), bias +7. Median ~1.1s/estimate at n=8, so results
    # cache per (deck, boss, belt) in ctx.screen_mem; scores["boss_ms"] logs fresh
    # computations (owner: the amount matters). Generic/unknown bosses stay on the
    # closed form.
    use_dfs_boss_rollouts: bool = True
    dfs_boss_rollout_n: int = 8
    # §5-C elite gate: chase an elite only if the deck wins it (at full HP) with at least this HP
    # fraction left — a pyrrhic 2-HP win is a loss for the next node, so don't chase it.
    # 0.30 -> 0.20 (A/B #5): a 20%-HP win + relic beat our 90%-HP no-relic arrival.
    elite_gate_min_end_hp_pct: float = 0.20
    # The node's elite is a random draw from the act's bestiary pool: chase only if the deck
    # clears (win + HP floor) at least this fraction of the pool's real members (2026-07-09:
    # the generic 90-HP profile flattered Terror Eel & co -> 3 elite deaths in one batch).
    # 0.67 -> 0.50 (owner 2026-07-12, after three straight 0-elite batches: "we can
    # definitely fight more elites now" — the damage model gained Strength credit,
    # cross-turn Vulnerable, Cruelty, and coherent step-2 decks since 0.67 was set).
    # 0.50 -> 0.40 (A/B #5, 2026-07-24): same evidence as elite_relic_value above.
    elite_gate_pool_win_frac: float = 0.40


class CardRewardWeights(_Section):
    take_threshold: float = 4.0
    # 8.1d: a weak, starter-heavy deck should take cards readily (a Strike-tier card beats keeping
    # a basic). Drop the take threshold by this much times the fraction of the deck that's still
    # Basic Strikes/Defends — near-starter decks take almost anything; polished ones stay picky.
    take_weak_deck_discount: float = 4.0
    prior_weight: float = 1.8
    conditional_prior_mult: float = 0.7
    unparsed_prior_mult: float = 0.45
    # Flat dock for cards the planner can't use AT ALL (parsed effects empty, e.g. Cascade) —
    # self-removing once the card becomes parseable/pilotable (owner-approved 2026-07-09).
    penalty_planner_blind: float = -4.0
    prior_act_weight: float = 3.0  # per-act tilt (8.1b); bounded secondary nudge
    w_rarity_common: float = 2.0
    w_rarity_uncommon: float = 5.0
    w_rarity_rare: float = 8.0
    w_attack: float = 1.0
    w_skill: float = 1.5
    w_power: float = 3.0
    penalty_cost_3plus: float = -2.5
    penalty_deck_over_25: float = -3.0
    bonus_aoe: float = 3.0
    bonus_energy: float = 4.0
    # Owner model rework 2026-07-14 (StS2 economics: energy scarcer, less cycling
    # pressure than StS1). bonus_draw REMOVED — pure draw is a weak speculative draft;
    # instead draw is penalized when the deck has no energy_source to power it.
    # bonus_block replaced by an Act-1-scoped bonus, lesser than the damage one;
    # later acts price block via the §5-C capability delta.
    early_damage_bonus: float = 2.5  # Act 1: nudge toward damage to clear early fights (owner)
    # Damage saturation (owner, A/B #3 Sword Boomerang misdraft): the early-damage bonus
    # pays in full below this many non-basic damage picks, half AT it, zero beyond.
    early_damage_sat_start: int = 2
    early_block_bonus: float = 1.5  # Act 1: lesser nudge toward block (owner 2026-07-14)
    # Underdocks overrides (owner 2026-07-17, magnitudes provisional — "will require
    # tweaking"): the region rewards defense/scaling; the damage-first tilt fits only
    # the Overgrowth (arrival flip: OG 72→90%, UD 87→77% at the 07-14 rework).
    ud_early_damage_bonus: float = 1.0
    ud_early_block_bonus: float = 2.5
    penalty_draw_no_energy: float = -2.0  # draw without an energy_source in deck
    # Owner 2026-07-14 ("take SOMETHING with big damage"): one-time Act-1 switch — until
    # the deck holds any >=12-damage hit (or big_single_hit provider), offered big hits
    # get this bonus; self-extinguishes on the first one acquired.
    w_first_big_hit: float = 4.0
    # Owner 2026-07-15 (A/B #2, Whirlwind-early): X-cost spend-energy damage is an
    # inefficient early pick — its payoffs (card efficiency, surplus energy) are late-
    # game conditions. Act-1 dock; such cards also skip the flat bonus_aoe.
    penalty_xcost_damage_early: float = -2.5
    # capability-aware drafting (§5-C): value a card by how much it improves estimate_fight vs a
    # generic Act-1 boss in the *current deck's* context (a block-starved deck values block, a
    # damage-starved one values damage). Added on top of the Elo/heuristic score, not replacing it.
    capability_weight: float = 0.4  # score per +1 projected boss-survival HP the card adds
    capability_win_flip_bonus: float = 6.0  # extra if the card flips the boss estimate lose->win
    # §5-C v2 (2026-07-30, KD audit): deltas priced by rollout, not estimate_fight.
    # Rollouts per draft option; ~3ms each so a 4-card screen costs ~(4+1)*n*3ms.
    # 40 because one card in a ~15-card deck moves boss progress by only a few HP —
    # honest but small; at n=12 the delta sign flipped on rollout noise (probe
    # 2026-07-30: Bludgeon vs 170-HP boss read -0.4 at n=12, +0.6/+3.6 at 40/80).
    draft_rollout_n: int = 40
    # Card-pass step 2 (owner-reviewed 2026-07-12): deck-context tag machinery
    # (sts2bot/policy/drafttags.py + data/card_draft_tags.json). Bonus per met need
    # (x strength mult x met fraction); penalty ONLY for pure payoffs with zero
    # providers, discounted in Act 1 (the speculative window).
    w_tag_bonus: float = 2.0
    w_tag_penalty: float = -4.0
    tag_act1_penalty_mult: float = 0.4
    w_copy_cap: float = -8.0  # a second Barricade-class copy is dead weight
    w_controlled_exhaust: float = 1.5  # targeted exhaust = thinning value (x basics/6)
    w_upgrade_unlocks: float = 1.0  # upgrade crosses a class boundary (True Grit+)
    # Deficit feeding (owner shadow review #2, 2026-07-24, Uppercut+ over Colossus):
    # "the deck seemed to lack vulnerable appliers and defense. So I picked a card
    # that gave both." A candidate that PROVIDES a tag which cards already in the
    # deck need — and which the deck supplies at or below threshold+1 — earns a
    # redundancy bonus per starved needer (Molten Fist drew dead all act behind a
    # lone Bash: one source at exact threshold is fragile in the draw).
    w_deficit_feed: float = 1.5
    deficit_feed_cap: float = 3.0


class RestWeights(_Section):
    rest_below_hp_pct: float = 0.60  # general campfire: rest below this, else smith
    # pre-boss campfire: rest unless HP covers the upcoming boss's likely damage
    # (the bot's own p75 boss HP-loss) times a safety factor; else smith to gear up.
    boss_safety_factor: float = 1.1
    # The aggregate boss-loss stat is dominated by Act-1 samples (est 41 vs a Queen
    # that costs 60+): Act-3 bosses demand more in the tank (owner-questioned entry
    # at 25/53, 2026-07-22). Applied on top of any per-boss rest_loss_bonus.
    act3_boss_loss_bonus: float = 15.0
    default_boss_loss: float = 60.0  # fallback when combat_stats has too few boss fights


class PotionWeights(_Section):
    drink_in_elite_or_boss: bool = True
    # Late-act-3 downside-potion claims (Foul/Glowwater) are skipped — merchant ammo
    # with no merchant left (owner catch 2026-07-25). Config-gated so diagnostics
    # (e.g. the foul-throw probe replay) can re-enable claiming.
    skip_late_downside_claims: bool = True
    # Full belt = every reward potion overflows, so a held potion's option value is
    # gone; treat any fight as deploy-worthy (value gates still decide WHICH/WHETHER).
    # Owner, Ovicopter A/B 2026-07-25: "3 of 3 potions, so my prior for playing one
    # of them is higher" — confirmed by the overflowing Explosive Ampule same fight.
    full_belt_deploys: bool = True
    drink_when_hp_pct_below: float = 0.35  # hail-mary HP gate
    hail_mary: bool = True
    heal_below_pct: float = 0.80  # drink a heal/Blood potion below this HP fraction
    block_reactive_min: int = 10  # end-of-turn: drink a Block potion to stop >= this unblocked
    damage_potion_prevents_min: int = 10  # finisher: kill an attacker doing >= this much
    value_drink_enemy_hp_min: int = 90  # spend an energy/draw potion when the fight has >= this HP
    value_drink_by_round: int = 3  # ...and only in the first few rounds (front-load the tempo)
    discard_priority: list[str] = []


class ShopWeights(_Section):
    buy_card_removal_below_gold: int = 999
    removal_min_gold_reserve: int = 75
    # A starter-heavy deck spends down to a smaller gold cushion for removal (cutting a basic is
    # high value when the deck is mostly basics) — shrink the reserve by up to this fraction,
    # scaled by the fraction of the deck still Basic Strikes/Defends. Respects removal_max_price.
    removal_weak_reserve_cut: float = 0.5
    # removal price escalates +50 per use (100, 150, 200…); efficiency drops sharply
    # past ~150g (owner), so don't pay more than this to remove a card.
    removal_max_price: int = 150
    buy_potion_min_gold: int = 120
    buy_relic_min_gold: int = 200
    # Spirebird shop value-per-gold (WAR/100g) floor to buy a relic; negatives are bad
    # buys (e.g. Book Repair Knife -0.03), unknown relics are skipped.
    relic_war_per_100g_min: float = 0.01


class DeckWeights(_Section):
    """Card-quality penalties for removal/upgrade/transform targeting (higher
    quality = better card to KEEP). Prior (Spirebird) is added on top."""

    basic_penalty: float = -50.0  # un-upgraded Strike/Defend: prime removal targets
    curse_penalty: float = -100.0  # curses/statuses: remove first


class PolicyConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    combat: CombatWeights = CombatWeights()
    events: EventWeights = EventWeights()
    map: MapWeights = MapWeights()
    card_rewards: CardRewardWeights = CardRewardWeights()
    rest: RestWeights = RestWeights()
    potions: PotionWeights = PotionWeights()
    shop: ShopWeights = ShopWeights()
    deck: DeckWeights = DeckWeights()
    source_path: str | None = None
    config_hash: str | None = None


def load_policy_config(path: Path | str | None = None) -> PolicyConfig:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    raw_bytes = config_path.read_bytes()
    data: dict[str, Any] = tomllib.loads(raw_bytes.decode("utf-8"))
    config = PolicyConfig.model_validate(data)
    config.source_path = str(config_path)
    config.config_hash = hashlib.sha1(raw_bytes).hexdigest()[:12]
    return config
