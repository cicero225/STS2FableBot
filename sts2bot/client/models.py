"""Typed models for STS2MCP API state responses.

Source of truth: external/STS2MCP/docs/raw-full.md (mod v0.4.0, game v0.103.2).

Modeling policy (REQUIREMENTS C5): core fields the bot relies on are required and
fail loudly when missing; everything else is optional. Unknown extra fields are
*allowed* (game patches add fields) — drift detection logs them rather than crashing.
An unrecognized `state_type` raises StateParseError: the loop must halt/report, not flail.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------- shared objects


class Keyword(ApiModel):
    name: str
    description: str | None = None


class Power(ApiModel):
    """Status effect on a player, pet, or enemy."""

    id: str
    name: str
    amount: int | None = None
    type: Literal["Buff", "Debuff"] | str | None = None
    description: str | None = None
    keywords: list[Keyword] = Field(default_factory=list)


class Card(ApiModel):
    """A card in hand or offered in a choice (reward, select overlay, hand_select)."""

    index: int
    id: str | None = None
    name: str
    type: str | None = None  # Attack, Skill, Power, Status, Curse
    cost: str | None = None  # energy cost as string; "X" for X-cost
    star_cost: str | None = None  # Regent only
    description: str | None = None
    rarity: str | None = None  # present in reward/select contexts
    is_upgraded: bool | None = None
    # combat-hand-only fields:
    target_type: str | None = None  # None, Self, AnyEnemy, AllEnemies, ...
    can_play: bool | None = None
    unplayable_reason: str | None = None
    keywords: list[Keyword] = Field(default_factory=list)


class PileCard(ApiModel):
    """Card as listed in draw/discard/exhaust piles (reduced shape)."""

    name: str
    cost: str | None = None
    star_cost: str | None = None
    description: str | None = None


class Orb(ApiModel):
    id: str
    name: str
    description: str | None = None
    passive_val: int | None = None
    evoke_val: int | None = None
    keywords: list[Keyword] = Field(default_factory=list)


class Pet(ApiModel):
    """Necrobinder companion (e.g. Osty)."""

    id: str
    name: str
    alive: bool
    hp: int
    max_hp: int
    block: int = 0
    status: list[Power] = Field(default_factory=list)


class Relic(ApiModel):
    id: str
    name: str
    description: str | None = None
    counter: int | None = None
    rarity: str | None = None  # present in choice contexts
    index: int | None = None  # present in choice contexts
    keywords: list[Keyword] = Field(default_factory=list)


class Potion(ApiModel):
    id: str
    name: str
    description: str | None = None
    slot: int
    can_use_in_combat: bool | None = None
    target_type: str | None = None
    keywords: list[Keyword] = Field(default_factory=list)


class DeckCard(ApiModel):
    """Master-deck entry (fork field; run deck, not combat piles)."""

    index: int
    id: str | None = None
    name: str
    type: str | None = None
    cost: str | None = None
    star_cost: str | None = None
    rarity: str | None = None
    is_upgraded: bool | None = None


class Player(ApiModel):
    character: str
    hp: int
    max_hp: int
    block: int = 0
    gold: int = 0
    deck: list[DeckCard] | None = None  # fork (mod >= 0.4.0-fork.2)
    # combat-only:
    energy: int | None = None
    max_energy: int | None = None
    stars: int | None = None  # Regent
    hand: list[Card] | None = None
    draw_pile_count: int | None = None
    discard_pile_count: int | None = None
    exhaust_pile_count: int | None = None
    draw_pile: list[PileCard] | None = None
    discard_pile: list[PileCard] | None = None
    exhaust_pile: list[PileCard] | None = None
    orbs: list[Orb] | None = None  # Defect
    orb_slots: int | None = None
    orb_empty_slots: int | None = None
    pets: list[Pet] | None = None  # Necrobinder
    # always present:
    status: list[Power] = Field(default_factory=list)
    relics: list[Relic] = Field(default_factory=list)
    potions: list[Potion] = Field(default_factory=list)
    max_potion_slots: int = 3

    @property
    def in_combat(self) -> bool:
        return self.energy is not None


class RunInfo(ApiModel):
    act: int
    floor: int
    ascension: int


class Intent(ApiModel):
    type: str  # Attack, Defend, Buff, Debuff, Sleep, ...
    label: str | None = None
    title: str | None = None
    description: str | None = None


class Enemy(ApiModel):
    entity_id: str  # targeting ID, e.g. "JAW_WORM_0"
    combat_id: int | None = None
    name: str
    hp: int
    max_hp: int
    block: int = 0
    status: list[Power] = Field(default_factory=list)
    intents: list[Intent] = Field(default_factory=list)


class Battle(ApiModel):
    round: int | None = None
    turn: Literal["player", "enemy"] | str | None = None
    is_play_phase: bool | None = None
    enemies: list[Enemy] = Field(default_factory=list)


# ---------------------------------------------------------------- state variants


class BaseState(ApiModel):
    """Fields shared by every state response (run/player absent on menu/unknown)."""

    run: RunInfo | None = None
    player: Player | None = None

    @property
    def kind(self) -> str:
        return self.state_type  # type: ignore[attr-defined]


class MenuOption(ApiModel):
    name: str
    enabled: bool = True


class MenuState(BaseState):
    state_type: Literal["menu"]
    message: str | None = None
    menu_screen: str | None = None  # main, singleplayer, profile_select, character_select,
    # tutorial_prompt, popup, timeline, multiplayer*, ...
    # options are plain strings on most screens, {name, enabled} objects on some (MP join)
    options: list[str | MenuOption] = Field(default_factory=list)
    blocked_options: list[Any] | None = None
    characters: list[Any] | None = None  # character_select screen
    # fork additions (mod >= 0.4.0-fork.1): which character the lobby will actually
    # embark with, and whether the unlock animation may still overwrite selections
    selected_character: str | None = None
    selection_busy: bool | None = None
    # fork additions (mod >= 0.4.0-fork.2): ascension picker state on character_select
    ascension: int | None = None
    max_ascension: int | None = None
    lobby: dict[str, Any] | None = None  # MP only — out of scope

    def option_names(self) -> list[str]:
        return [o if isinstance(o, str) else o.name for o in self.options]

    def enabled_options(self) -> dict[str, bool]:
        return {
            (o if isinstance(o, str) else o.name).lower(): (
                True if isinstance(o, str) else o.enabled
            )
            for o in self.options
        }


class UnknownState(BaseState):
    state_type: Literal["unknown"]
    room_type: str | None = None


class CombatState(BaseState):
    state_type: Literal["monster", "elite", "boss"]
    # battle is briefly absent while the combat room is still loading (observed live;
    # not in the API docs) — treat None as "wait for combat to finish loading".
    battle: Battle | None = None


class HandSelect(ApiModel):
    mode: str | None = None  # simple_select | upgrade_select
    prompt: str | None = None
    cards: list[Card] = Field(default_factory=list)
    selected_cards: list[Any] | None = None
    can_confirm: bool = False


class HandSelectState(BaseState):
    state_type: Literal["hand_select"]
    hand_select: HandSelect
    battle: Battle | None = None


class RewardItem(ApiModel):
    index: int
    type: str  # gold, potion, relic, card, special_card, card_removal
    description: str | None = None
    gold_amount: int | None = None
    potion_id: str | None = None
    potion_name: str | None = None


class Rewards(ApiModel):
    items: list[RewardItem] = Field(default_factory=list)
    can_proceed: bool = True


class RewardsState(BaseState):
    state_type: Literal["rewards"]
    rewards: Rewards


class CardReward(ApiModel):
    cards: list[Card] = Field(default_factory=list)
    can_skip: bool = True


class CardRewardState(BaseState):
    state_type: Literal["card_reward"]
    card_reward: CardReward


class MapPosition(ApiModel):
    col: int
    row: int
    type: str | None = None


class MapNextOption(MapPosition):
    index: int
    leads_to: list[MapPosition] = Field(default_factory=list)


class MapNode(MapPosition):
    children: list[tuple[int, int]] = Field(default_factory=list)  # [col, row] pairs


class BossInfo(ApiModel):
    col: int | None = None
    row: int | None = None
    id: str | None = None
    name: str | None = None


class MapInfo(ApiModel):
    current_position: MapPosition | None = None
    visited: list[MapPosition] = Field(default_factory=list)
    next_options: list[MapNextOption] = Field(default_factory=list)
    nodes: list[MapNode] = Field(default_factory=list)
    boss: BossInfo | None = None
    bosses: list[BossInfo] = Field(default_factory=list)


class MapState(BaseState):
    state_type: Literal["map"]
    map: MapInfo


class EventOption(ApiModel):
    index: int
    title: str | None = None
    description: str | None = None
    is_locked: bool = False
    is_proceed: bool = False
    was_chosen: bool = False
    relic_name: str | None = None
    relic_description: str | None = None
    keywords: list[Keyword] = Field(default_factory=list)


class EventInfo(ApiModel):
    event_id: str | None = None
    event_name: str | None = None
    is_ancient: bool = False
    in_dialogue: bool = False
    body: str | None = None
    options: list[EventOption] = Field(default_factory=list)


class EventState(BaseState):
    state_type: Literal["event"]
    event: EventInfo


class RestOption(ApiModel):
    index: int
    id: str | None = None
    name: str | None = None
    description: str | None = None
    is_enabled: bool = True


class RestSite(ApiModel):
    options: list[RestOption] = Field(default_factory=list)
    can_proceed: bool = False


class RestSiteState(BaseState):
    state_type: Literal["rest_site"]
    rest_site: RestSite


class ShopItem(ApiModel):
    index: int
    category: str  # card, relic, potion, card_removal
    price: int | None = None
    cost: int | None = None  # fake_merchant uses "cost"
    is_stocked: bool = True
    can_afford: bool | None = None
    on_sale: bool = False
    card_id: str | None = None
    card_name: str | None = None
    card_type: str | None = None
    card_cost: str | None = None
    card_star_cost: str | None = None
    card_rarity: str | None = None
    card_description: str | None = None
    relic_id: str | None = None
    relic_name: str | None = None
    relic_description: str | None = None
    potion_id: str | None = None
    potion_name: str | None = None
    potion_description: str | None = None
    keywords: list[Keyword] = Field(default_factory=list)

    @property
    def gold_price(self) -> int | None:
        return self.price if self.price is not None else self.cost


class ShopInfo(ApiModel):
    items: list[ShopItem] = Field(default_factory=list)
    can_proceed: bool = True
    error: str | None = None  # inventory not ready; retry


class ShopState(BaseState):
    state_type: Literal["shop"]
    shop: ShopInfo


class FakeMerchantInfo(ApiModel):
    event_id: str | None = None
    event_name: str | None = None
    started_fight: bool = False
    shop: ShopInfo | None = None
    message: str | None = None


class FakeMerchantState(BaseState):
    state_type: Literal["fake_merchant"]
    fake_merchant: FakeMerchantInfo


class TreasureInfo(ApiModel):
    message: str | None = None  # transitional "Opening chest..." — re-query
    relics: list[Relic] = Field(default_factory=list)
    can_proceed: bool = True


class TreasureState(BaseState):
    state_type: Literal["treasure"]
    treasure: TreasureInfo


class CardSelect(ApiModel):
    screen_type: str | None = None  # transform, upgrade, select, simple_select, choose
    prompt: str | None = None
    cards: list[Card] = Field(default_factory=list)
    preview_showing: bool = False
    can_confirm: bool = False
    can_cancel: bool = False
    can_skip: bool | None = None  # "choose" screens


class CardSelectState(BaseState):
    state_type: Literal["card_select"]
    card_select: CardSelect


class Bundle(ApiModel):
    index: int
    card_count: int | None = None
    cards: list[Card] = Field(default_factory=list)


class BundleSelect(ApiModel):
    screen_type: str | None = None
    prompt: str | None = None
    bundles: list[Bundle] = Field(default_factory=list)
    preview_showing: bool = False
    preview_cards: list[Card] = Field(default_factory=list)
    can_confirm: bool = False
    can_cancel: bool = False


class BundleSelectState(BaseState):
    state_type: Literal["bundle_select"]
    bundle_select: BundleSelect


class RelicSelect(ApiModel):
    prompt: str | None = None
    relics: list[Relic] = Field(default_factory=list)
    can_skip: bool = True


class RelicSelectState(BaseState):
    state_type: Literal["relic_select"]
    relic_select: RelicSelect


class CrystalCell(ApiModel):
    x: int
    y: int
    is_hidden: bool = True
    is_clickable: bool = False
    is_highlighted: bool = False
    is_hovered: bool = False
    item_type: str | None = None
    is_good: bool | None = None


class CrystalCoord(ApiModel):
    x: int
    y: int


class RevealedItem(ApiModel):
    item_type: str | None = None
    x: int | None = None
    y: int | None = None
    width: int | None = None
    height: int | None = None
    is_good: bool | None = None


class CrystalSphere(ApiModel):
    instructions_title: str | None = None
    instructions_description: str | None = None
    grid_width: int | None = None
    grid_height: int | None = None
    cells: list[CrystalCell] = Field(default_factory=list)
    clickable_cells: list[CrystalCoord] = Field(default_factory=list)
    revealed_items: list[RevealedItem] = Field(default_factory=list)
    tool: str | None = None  # big, small, none
    can_use_big_tool: bool | None = None
    can_use_small_tool: bool | None = None
    divinations_left_text: str | None = None
    can_proceed: bool = False


class CrystalSphereState(BaseState):
    state_type: Literal["crystal_sphere"]
    crystal_sphere: CrystalSphere


class GameOverInfo(ApiModel):
    message: str | None = None
    options: list[str] = Field(default_factory=list)


class GameOverState(BaseState):
    state_type: Literal["game_over"]
    game_over: GameOverInfo


class OverlayInfo(ApiModel):
    screen_type: str | None = None
    message: str | None = None


class OverlayState(BaseState):
    state_type: Literal["overlay"]
    overlay: OverlayInfo


# ---------------------------------------------------------------- union + parsing

GameState = Annotated[
    MenuState
    | UnknownState
    | CombatState
    | HandSelectState
    | RewardsState
    | CardRewardState
    | MapState
    | EventState
    | RestSiteState
    | ShopState
    | FakeMerchantState
    | TreasureState
    | CardSelectState
    | BundleSelectState
    | RelicSelectState
    | CrystalSphereState
    | GameOverState
    | OverlayState,
    Field(discriminator="state_type"),
]

_state_adapter: TypeAdapter[GameState] = TypeAdapter(GameState)


class StateParseError(Exception):
    """State payload didn't match the known schema (game/mod drift — see C5)."""

    def __init__(self, message: str, raw: dict[str, Any] | None = None):
        super().__init__(message)
        self.raw = raw


def parse_state(raw: dict[str, Any]) -> GameState:
    """Parse a GET-state payload into a typed state, raising loudly on drift."""
    try:
        return _state_adapter.validate_python(raw)
    except ValidationError as e:
        raise StateParseError(
            f"Unrecognized or malformed game state (state_type={raw.get('state_type')!r}): {e}",
            raw=raw,
        ) from e
