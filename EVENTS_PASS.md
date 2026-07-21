# Events Pass (Lane 1, PLAN item 5)

*Discovery 2026-07-20 (session 9). Corpus: post-rework era (2026-07-14+), 52 distinct
non-ancient events. Companion docs: RELIC_PASS.md, CARD_PASS_STEP2_PROPOSAL.md; the
Ancients pass (PLAN §8.5.5a, shipped) is the playbook this follows.*

## Headline finding: decline-by-default

**"Proceed" is the modal pick on nearly every event** — decline rates ≈50%+ across
the board (SELF_HELP_BOOK 29/51, BRAIN_LEECH 26/49, THIS_OR_THAT 23/44, ...). The
decline path fires whenever Spirebird lacks confident option data AND the generic
gains/costs heuristic reads under take_min — so any event whose text the parser can't
price (transforms, enchants, map effects, multi-step flows) defaults to walking away
from an EV-positive room class (our own router prices event nodes 12 vs monster 10).

## Top events by frequency (post-rework corpus)

| event | seen | decline rate | notes |
|---|---|---|---|
| SELF_HELP_BOOK | 51 | 57% | two "read" options, Spirebird splits evenly |
| BRAIN_LEECH | 49 | 53% | owner took "Rip the Leech Off" in A/B; Spirebird agrees when it fires |
| ABYSSAL_BATHS | 45 | 38% | 3-way; "Immerse"/"Exit" split |
| THIS_OR_THAT | 44 | 52% | "That" via bare heuristic 21× — what are This/That? uncatalogued |
| ROOM_FULL_OF_CHEESE | 41 | 51% | "Gorge" almost never taken (2×) |
| THE_LEGENDS_WERE_TRUE | 38 | 53% | "Nab the Map" |
| SUNKEN_STATUE | 37 | 54% | "Grab the Sword" |
| SUNKEN_TREASURY | 37 | 51% | "Second Chest" |
| DROWNING_BEACON | 31 | 55% | "Bottle" picked via OTHER path (14×) — inspect |
| SPIRALING_WHIRLPOOL | 29 | 55% | "Observe" |

(12 more mid-frequency: ENDLESS_CONVEYOR, FUTURE_OF_POTIONS, DENSE_VEGETATION,
SLIPPERY_BRIDGE, TABLET_OF_TRUTH, WELLSPRING, JUNGLE_MAZE, LOST_WISP, WOOD_CARVINGS,
TEA_MASTER, SYMBIOTE, AROMA_OF_CHAOS; tail of 30 rare ones.)

## Known anchor cases (pre-filed)

- **Slither enchant** (PLAN item 5 anchor): the bot enchanted a Strike with Slither —
  enchant-target selection needs the keep-quality ranking, not first-card.
- **Byrdonis Egg** (§8.4): taken then never hatched (rest handler blind to the hatch
  action — same non-standard-campfire class as Girya/Lift/Clone/Cook; the class is now
  worth one shared fix given FOUR members).
- **Delicate Frond** potion-aggressiveness switch (relic-conditional; A/B #4 exhibit).

## Proposed approach (the Ancients playbook)

1. **Option catalog keyed by OPTION TITLE** (`data/event_choices.json`) — not by
   (event, option): the harvest showed the mod's event_id LAGS screen transitions
   (options bleed across ids in logs), and titles are stable and self-identifying
   ("Rip the Leech Off" means the same thing wherever filed). Same key design as the
   boon catalog. Harvested texts: session scratchpad event_texts.json (2026-07-20).
   Notable entries already visible: Second Chest = 300-360g + Greed curse; Nab the
   Map = Spoils Map (the 600g coupon we now protect); Snake = the Slither trap IN
   TEXT; Immerse/Linger = repeatable +2 max HP for small damage.
2. **Decline-rate correction**: where an option is strictly-positive (no HP/gold/curse
   cost parsed AND no unknown keyword), prefer it over Proceed even without Spirebird
   — walking away from free value is the one provably wrong move.
3. **Rest-handler action awareness** (shared fix): Girya Lift / Egg Hatch / Clone /
   Cook — parse non-standard rest options generically (name + description → category)
   instead of the fixed Rest/Smith menu. Unblocks two boon reprices too.
4. Defer: event-stats mining for per-option outcome deltas (needs more corpus).

## Owner review outcomes (2026-07-20)

- **Spirebird HAS event data** (owner recalled correctly; 62 events, e.g. 81k picks
  on Self-Help Book) and the word-subset matcher reaches most of it.
- **SLITHER REVERSED**: random 0-3 cost on draw = +EV on any cost>=2 card (SB 11.9
  agrees). The old "trap" anchor was a cost-1 Strike TARGETING mistake. Enchant
  picker now targets the highest-cost card (Bash always exists).
- Swift-on-Power tops Self-Help Book (SB 15.1) unless a 3x+ multi-hit Sharp target
  exists — Sharp target preference wired.
- Spiral = Replay 1 on a basic; planner verified to price the Replay text.
- **Future of Potions**: highest-rarity-first; PROTECTED potions never sacrificed
  (potion-pass item): Entropic Brew, Fairy in a Bottle, Gigantification Potion,
  Orobic Acid, Ambergris. Event itself is not declinable.
- Decider (not declinable): 2-relics > Shame-upgrade; Regret+300g > heal-10 (unless
  desperate / no shops remain); Doubt+2-rewards vs Double+Transform-2 by basics count.
- Peck vs Toric: Toric usually; Peck with Strength gain in deck OR Vantom as boss.

## Status

- [x] Discovery audit
- [x] Harvest option texts → catalog (53 options)
- [x] Owner review (0 uncertain remaining)
- [x] `_event` catalog-first wiring (37ef0e7) + review values (a26dd4a)
- [x] Slither/Sharp enchant target rules (a26dd4a)
- [ ] Rest-handler non-standard action awareness (Girya/Hatch/Clone/Cook)
- [ ] Potion-pass handoff: protected-potion veto for Future of Potions
