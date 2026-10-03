"""Osty trap (owner catch 2026-10-02): a Kaleidoscope run let the Ironclad draft
High Five ('Osty deals 11 damage and applies 2 Vulnerable to ALL enemies.').
Osty is the Necrobinder's companion, so Osty-acting cards are dead in hand for
other characters -- vetoed like Regent star-cost cards without a star source."""

from sts2bot.policy.standard import StandardRouter


class C:
    def __init__(self, cid, name, description="", typ="Attack", rarity="Uncommon"):
        self.id = cid
        self.name = name
        self.type = typ
        self.cost = "2"
        self.is_upgraded = False
        self.description = description
        self.rarity = rarity
        self.star_cost = None


def _deck():
    deck = [C("STRIKE_IRONCLAD", "Strike", "Deal 6 damage.") for _ in range(5)]
    deck += [C("DEFEND_IRONCLAD", "Defend", "Gain 5 Block.", typ="Skill") for _ in range(4)]
    return deck


HIGH_FIVE = C("HIGH_FIVE", "High Five",
              "Osty deals 11 damage and applies 2 Vulnerable to ALL enemies.")


def test_osty_card_is_vetoed_for_non_necrobinder() -> None:
    r = StandardRouter()
    deck = _deck()
    assert r._card_score(HIGH_FIVE, len(deck), "The Ironclad", act=1, deck=deck) == -100.0


def test_osty_card_allowed_for_necrobinder_or_with_a_summon_source() -> None:
    r = StandardRouter()
    deck = _deck()
    assert r._card_score(HIGH_FIVE, len(deck), "The Necrobinder", act=1, deck=deck) > -100.0
    summon = C("BODYGUARD", "Bodyguard", "Summon 5.", typ="Skill")
    assert r._card_score(HIGH_FIVE, len(deck) + 1, "The Ironclad", act=1,
                         deck=[*deck, summon]) > -100.0


def test_ordinary_cards_unaffected() -> None:
    r = StandardRouter()
    deck = _deck()
    pommel = C("POMMEL_STRIKE", "Pommel Strike", "Deal 9 damage. Draw 1 card.",
               rarity="Common")
    assert r._card_score(pommel, len(deck), "The Ironclad", act=1, deck=deck) > -100.0
