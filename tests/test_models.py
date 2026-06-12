import json
from pathlib import Path

import pytest

from sts2bot.client import StateParseError, parse_state
from sts2bot.client.actions import EndTurn, MenuSelect, PlayCard
from sts2bot.client.models import (
    CardRewardState,
    CombatState,
    EventState,
    FakeMerchantState,
    GameOverState,
    MapState,
    MenuState,
    ShopState,
)

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "doc_states.json").read_text(encoding="utf-8")
)
STATES = {k: v for k, v in FIXTURES.items() if not k.startswith("_")}

EXPECTED_TYPE = {
    "menu_main": "menu",
    "menu_profile_select": "menu",
    "menu_character_select": "menu",
    "menu_popup": "menu",
    "menu_tutorial_prompt": "menu",
    "unknown": "unknown",
    "combat_monster": "monster",
    "combat_defect_orbs": "elite",
    "combat_necrobinder_pet": "boss",
    "hand_select": "hand_select",
    "rewards": "rewards",
    "card_reward": "card_reward",
    "map": "map",
    "event_neow": "event",
    "event_dialogue": "event",
    "rest_site": "rest_site",
    "shop": "shop",
    "fake_merchant": "fake_merchant",
    "treasure": "treasure",
    "card_select_transform": "card_select",
    "bundle_select": "bundle_select",
    "relic_select": "relic_select",
    "crystal_sphere": "crystal_sphere",
    "game_over": "game_over",
    "overlay": "overlay",
}


def test_fixture_coverage_matches_expectations() -> None:
    assert set(STATES) == set(EXPECTED_TYPE)


@pytest.mark.parametrize("name", sorted(STATES))
def test_parses_every_fixture(name: str) -> None:
    state = parse_state(STATES[name])
    assert state.state_type == EXPECTED_TYPE[name]


def test_menu_options_normalized() -> None:
    plain = parse_state(STATES["menu_main"])
    assert isinstance(plain, MenuState)
    assert "singleplayer" in plain.option_names()

    objects = parse_state(STATES["menu_character_select"])
    assert isinstance(objects, MenuState)
    assert objects.option_names()[:2] == ["IRONCLAD", "SILENT"]


def test_combat_state_details() -> None:
    state = parse_state(STATES["combat_monster"])
    assert isinstance(state, CombatState)
    enemy = state.battle.enemies[0]
    assert enemy.entity_id == "JAW_WORM_0"
    assert enemy.intents[0].type == "Attack"
    player = state.player
    assert player is not None and player.in_combat
    assert player.energy == 3
    hand = player.hand or []
    assert [c.can_play for c in hand] == [True, True, False]
    assert hand[2].unplayable_reason == "NotEnoughEnergy"
    assert player.status[0].amount == 3  # Strength


def test_character_mechanics_parse() -> None:
    defect = parse_state(STATES["combat_defect_orbs"])
    assert isinstance(defect, CombatState)
    assert defect.player is not None and defect.player.orbs is not None
    assert defect.player.orbs[0].id == "LIGHTNING"

    necro = parse_state(STATES["combat_necrobinder_pet"])
    assert isinstance(necro, CombatState)
    assert necro.player is not None and necro.player.pets is not None
    assert necro.player.pets[0].alive is True


def test_map_graph_shape() -> None:
    state = parse_state(STATES["map"])
    assert isinstance(state, MapState)
    assert state.map.next_options[0].leads_to[0].type == "Elite"
    assert state.map.nodes[0].children == [(2, 1), (3, 1), (4, 1)]
    assert state.map.boss is not None and state.map.boss.name == "Vantom"


def test_shop_prices_including_fake_merchant_cost_alias() -> None:
    shop = parse_state(STATES["shop"])
    assert isinstance(shop, ShopState)
    by_cat = {i.category: i for i in shop.shop.items}
    assert by_cat["card"].gold_price == 75
    assert by_cat["card_removal"].gold_price == 75

    fake = parse_state(STATES["fake_merchant"])
    assert isinstance(fake, FakeMerchantState)
    assert fake.fake_merchant.shop is not None
    assert fake.fake_merchant.shop.items[0].gold_price == 150  # "cost" alias


def test_event_options() -> None:
    state = parse_state(STATES["event_neow"])
    assert isinstance(state, EventState)
    assert state.event.options[2].relic_name == "Black Star"
    dialogue = parse_state(STATES["event_dialogue"])
    assert isinstance(dialogue, EventState)
    assert dialogue.event.in_dialogue is True


def test_card_reward_and_game_over() -> None:
    reward = parse_state(STATES["card_reward"])
    assert isinstance(reward, CardRewardState)
    assert reward.card_reward.can_skip is True
    over = parse_state(STATES["game_over"])
    assert isinstance(over, GameOverState)
    assert over.game_over.options == ["main_menu"]


def test_unknown_state_type_raises() -> None:
    with pytest.raises(StateParseError):
        parse_state({"state_type": "brand_new_screen", "stuff": 1})


def test_extra_fields_tolerated() -> None:
    payload = dict(STATES["menu_main"])
    payload["added_by_future_patch"] = {"x": 1}
    state = parse_state(payload)
    assert state.state_type == "menu"


def test_action_payloads() -> None:
    assert PlayCard(card_index=2, target="JAW_WORM_0").payload() == {
        "action": "play_card",
        "card_index": 2,
        "target": "JAW_WORM_0",
    }
    # exclude_none: optional target omitted entirely
    assert PlayCard(card_index=0).payload() == {"action": "play_card", "card_index": 0}
    assert EndTurn().payload() == {"action": "end_turn"}
    assert MenuSelect(option="singleplayer").payload() == {
        "action": "menu_select",
        "option": "singleplayer",
    }
