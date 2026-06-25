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
    w_rage_sequence: float = 0.3  # nudge Rage before attacks even when its block reads as excess
    w_ramp_damage: float = 1.5  # extra value for damaging strength-gaining enemies (race them)
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
    lookahead_discount: float = 0.35
    path_step_discount: float = 0.80
    # §8.2 HP-aware routing (active only when combat_stats is loaded). The DP projects HP along
    # each route using the bot's own per-fight p75 loss; these tune how it reacts.
    survival_floor_hp_pct: float = 0.10  # route projected to drop to/below this HP frac = "lethal"
    route_death_penalty: float = 80.0  # ...and pays this; dominates a node's own type score
    # a *survivable* elite earns elite_relic_value (vs score_elite -20 -> net +16, just above
    # treasure): relics are deck power, so chase elites when the HP is there to spend
    elite_relic_value: float = 36.0
    rest_heal_pct: float = 0.30  # HP fraction a rest site restores, for the projection
    # §5-C elite gate: chase an elite only if the deck wins it (at full HP) with at least this HP
    # fraction left — a pyrrhic 2-HP win is a loss for the next node, so don't chase it.
    elite_gate_min_end_hp_pct: float = 0.30


class CardRewardWeights(_Section):
    take_threshold: float = 4.0
    # 8.1d: a weak, starter-heavy deck should take cards readily (a Strike-tier card beats keeping
    # a basic). Drop the take threshold by this much times the fraction of the deck that's still
    # Basic Strikes/Defends — near-starter decks take almost anything; polished ones stay picky.
    take_weak_deck_discount: float = 4.0
    prior_weight: float = 1.8
    conditional_prior_mult: float = 0.7
    unparsed_prior_mult: float = 0.45
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
    bonus_block: float = 2.0
    bonus_draw: float = 2.0
    bonus_energy: float = 4.0
    early_damage_bonus: float = 2.5  # Act 1: nudge toward damage to clear early fights (owner)
    # capability-aware drafting (§5-C): value a card by how much it improves estimate_fight vs a
    # generic Act-1 boss in the *current deck's* context (a block-starved deck values block, a
    # damage-starved one values damage). Added on top of the Elo/heuristic score, not replacing it.
    capability_weight: float = 0.4  # score per +1 projected boss-survival HP the card adds
    capability_win_flip_bonus: float = 6.0  # extra if the card flips the boss estimate lose->win


class RestWeights(_Section):
    rest_below_hp_pct: float = 0.60  # general campfire: rest below this, else smith
    # pre-boss campfire: rest unless HP covers the upcoming boss's likely damage
    # (the bot's own p75 boss HP-loss) times a safety factor; else smith to gear up.
    boss_safety_factor: float = 1.1
    default_boss_loss: float = 60.0  # fallback when combat_stats has too few boss fights


class PotionWeights(_Section):
    drink_in_elite_or_boss: bool = True
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
