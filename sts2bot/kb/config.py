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
    w_block_useful: float = 1.2
    w_block_excess: float = -0.15
    w_hp_loss: float = -2.0
    hp_scarcity_base: float = 0.5
    hp_scarcity_slope: float = 2.0
    w_vulnerable: float = 6.0
    w_weak: float = 5.0
    w_strength: float = 7.0
    w_draw: float = 3.0
    w_energy_waste: float = -0.5
    w_play_friction: float = -0.35
    max_sequences: int = 4000
    survival_status_threshold: int = 2
    # transient 'BlockedByHook' hands (engine mid-resolution) report every card
    # unplayable; re-poll up to this many times before trusting it (cost a boss
    # fight: a planned triple-Defend collapsed to one, 14 HP -> 3, run 33)
    hook_retry_limit: int = 12


class EventWeights(_Section):
    hp_cost_refuse_below: float = 0.45
    unknown_take_first_above: float = 0.70


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


class CardRewardWeights(_Section):
    take_threshold: float = 4.0
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


class RestWeights(_Section):
    rest_below_hp_pct: float = 0.60  # general campfire: rest below this, else smith
    # pre-boss campfire: rest unless HP covers the upcoming boss's likely damage
    # (the bot's own p75 boss HP-loss) times a safety factor; else smith to gear up.
    boss_safety_factor: float = 1.1
    default_boss_loss: float = 60.0  # fallback when combat_stats has too few boss fights


class PotionWeights(_Section):
    drink_in_elite_or_boss: bool = True
    drink_when_hp_pct_below: float = 0.35
    hail_mary: bool = True
    discard_priority: list[str] = []


class ShopWeights(_Section):
    buy_card_removal_below_gold: int = 999
    removal_min_gold_reserve: int = 75
    # removal price escalates +50 per use (100, 150, 200…); efficiency drops sharply
    # past ~150g (owner), so don't pay more than this to remove a card.
    removal_max_price: int = 150
    buy_potion_min_gold: int = 120
    buy_relic_min_gold: int = 200


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
