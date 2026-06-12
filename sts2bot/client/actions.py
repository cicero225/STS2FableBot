"""Action types for POST /api/v1/singleplayer.

Each action serializes to the JSON body the mod expects. Typed objects (rather than
raw dicts) so decisions are loggable/replayable with their parameters (REQUIREMENTS C6).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class _ActionBase(BaseModel):
    def payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


# menus / popups / game over
class MenuSelect(_ActionBase):
    action: Literal["menu_select"] = "menu_select"
    option: str
    seed: str | None = None


# combat
class PlayCard(_ActionBase):
    action: Literal["play_card"] = "play_card"
    card_index: int
    target: str | None = None  # enemy entity_id


class UsePotion(_ActionBase):
    action: Literal["use_potion"] = "use_potion"
    slot: int
    target: str | None = None


class DiscardPotion(_ActionBase):
    action: Literal["discard_potion"] = "discard_potion"
    slot: int


class EndTurn(_ActionBase):
    action: Literal["end_turn"] = "end_turn"


class CombatSelectCard(_ActionBase):
    action: Literal["combat_select_card"] = "combat_select_card"
    card_index: int


class CombatConfirmSelection(_ActionBase):
    action: Literal["combat_confirm_selection"] = "combat_confirm_selection"


# rewards
class ClaimReward(_ActionBase):
    action: Literal["claim_reward"] = "claim_reward"
    index: int


class Proceed(_ActionBase):
    """Leave rewards / rest site / shop / treasure."""

    action: Literal["proceed"] = "proceed"


class SelectCardReward(_ActionBase):
    action: Literal["select_card_reward"] = "select_card_reward"
    card_index: int


class SkipCardReward(_ActionBase):
    action: Literal["skip_card_reward"] = "skip_card_reward"


# map
class ChooseMapNode(_ActionBase):
    action: Literal["choose_map_node"] = "choose_map_node"
    index: int


# events
class ChooseEventOption(_ActionBase):
    action: Literal["choose_event_option"] = "choose_event_option"
    index: int


class AdvanceDialogue(_ActionBase):
    action: Literal["advance_dialogue"] = "advance_dialogue"


# rest site
class ChooseRestOption(_ActionBase):
    action: Literal["choose_rest_option"] = "choose_rest_option"
    index: int


# shop (incl. fake merchant)
class ShopPurchase(_ActionBase):
    action: Literal["shop_purchase"] = "shop_purchase"
    index: int


# treasure
class ClaimTreasureRelic(_ActionBase):
    action: Literal["claim_treasure_relic"] = "claim_treasure_relic"
    index: int


# card selection overlay
class SelectCard(_ActionBase):
    action: Literal["select_card"] = "select_card"
    index: int


class ConfirmSelection(_ActionBase):
    action: Literal["confirm_selection"] = "confirm_selection"


class CancelSelection(_ActionBase):
    action: Literal["cancel_selection"] = "cancel_selection"


# bundle selection overlay
class SelectBundle(_ActionBase):
    action: Literal["select_bundle"] = "select_bundle"
    index: int


class ConfirmBundleSelection(_ActionBase):
    action: Literal["confirm_bundle_selection"] = "confirm_bundle_selection"


class CancelBundleSelection(_ActionBase):
    action: Literal["cancel_bundle_selection"] = "cancel_bundle_selection"


# relic selection overlay
class SelectRelic(_ActionBase):
    action: Literal["select_relic"] = "select_relic"
    index: int


class SkipRelicSelection(_ActionBase):
    action: Literal["skip_relic_selection"] = "skip_relic_selection"


# fork utilities (mod >= 0.4.0-fork.2)
class SetTimeScale(_ActionBase):
    """Engine animation/game speed. Valid any time; persists until game restart."""

    action: Literal["set_time_scale"] = "set_time_scale"
    scale: float


class SetAscension(_ActionBase):
    """Set run ascension on the open character-select screen (after selecting a
    character — the unlocked cap is per-character)."""

    action: Literal["set_ascension"] = "set_ascension"
    level: int


# crystal sphere minigame
class CrystalSphereSetTool(_ActionBase):
    action: Literal["crystal_sphere_set_tool"] = "crystal_sphere_set_tool"
    tool: Literal["big", "small"]


class CrystalSphereClickCell(_ActionBase):
    action: Literal["crystal_sphere_click_cell"] = "crystal_sphere_click_cell"
    x: int
    y: int


class CrystalSphereProceed(_ActionBase):
    action: Literal["crystal_sphere_proceed"] = "crystal_sphere_proceed"


Action = (
    MenuSelect
    | PlayCard
    | UsePotion
    | DiscardPotion
    | EndTurn
    | CombatSelectCard
    | CombatConfirmSelection
    | ClaimReward
    | Proceed
    | SelectCardReward
    | SkipCardReward
    | ChooseMapNode
    | ChooseEventOption
    | AdvanceDialogue
    | ChooseRestOption
    | ShopPurchase
    | ClaimTreasureRelic
    | SelectCard
    | ConfirmSelection
    | CancelSelection
    | SelectBundle
    | ConfirmBundleSelection
    | CancelBundleSelection
    | SelectRelic
    | SkipRelicSelection
    | SetTimeScale
    | SetAscension
    | CrystalSphereSetTool
    | CrystalSphereClickCell
    | CrystalSphereProceed
)
