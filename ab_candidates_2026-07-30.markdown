# Owner A/B candidates — boss fights worth replaying (2026-07-30 scan)

Scanned every boss death of 2026-07-30 (~25 fights) for decision-point density:
score flip-flops, potions dying in the belt, late hail-maries, winnable-looking
peaks. Each pick below has a specific falsifiable hypothesis — a rule we could
encode if the owner's line beats the bot's — not just "multiturn planner needed."

**Epoch caveat:** seeds are valid only if no unlock epoch advanced since the run
(wins #7/#8 happened today). Verify one seed in-game before scheduling a session.

## 1. `9NUW6E6TGZ` — The Kin, f17 (TOP PICK)
15 turns, peak +278, 7 potions drunk, 6 of them hail-maries. The bot entered at
~28 HP off a rest, spent potions REACTIVELY (one per near-death turn) in the
fight the owner's own rule says is a race-the-leader. 307-HP fight, Radiant
Tincture drunk for sustain mid-fight.
**Hypothesis:** §5.2 item 5's inversion — for a KNOWN-hard race, perfect play
front-loads the whole belt turn 1-2 (and target discipline never wavers off the
leader). If the owner wins this by committing everything early, the encodable
rule is: race fights extend the boss-start deploy lane to the FULL belt, not one
potion.

## 2. `A36ZF0WVBS` — Queen, f48 — **RESOLVED FROM TAPE, fix shipped (bb484dd)**
Entered at 95 HP, dead in 6 turns while the dps table called the Queen harmless
(2.1 mean). The fight window answered it without a replay: `TORCH_HEAD_AMALGAM_0`
(realized dps 24.8, hottest in the table) — she's a SUMMONER, and the forecast
priced her alone. `_upcoming_boss` now adds the Amalgam as a Kin-style minion
(full threat, no kill-HP). Residual owner question, lower priority: summon
cadence (does she re-summon after an Amalgam dies? kill-the-summon ever right?)
— worth asking next time one is on screen, not worth a dedicated session.

## 3. `XNTR7JTWGZ` — Aeonglass, f48
11 turns, peak +581 (!) — the planner believed it was decisively winning — then
collapse to death. Aeonglass realized dps 20.2 (n=6). Something turns this fight
that a one-turn planner cannot see coming (clock? stacking debuff? WG-style
accumulating payload).
**Hypothesis:** Aeonglass has a mechanic in the WG death-growth class that needs
an _EMPIRICAL_MOVES entry. One owner fight (or even a narrated loss) names it.

## 4. `R9NZLD49C1` — Lagavulin Matriarch, f17
18 turns (longest of the day), 17 score flips, and ZERO hail-maries — the bot
never acknowledged the endgame; the drain spiral (-2 Str/Dex per 4 rounds,
post-race-fix) bled it out slowly. First live observation of the race-lane fix:
it wasn't enough.
**Hypothesis:** correct Matriarch play is all-in before drain stack k (turn ~8?)
— after that, damage decays and the fight is unwinnable regardless of HP. If the
owner's line confirms, the encodable rule is a drain-aware race horizon (spend
potions/burst by a turn budget), which the rollout can also price.

## Not shortlisted (and why)
- KD deaths (7 today): every one a correctly-forecast deck-power loss (rest gate
  read est loss 80-98 pre-fight); fights lasted 5-8 turns with no winnable-looking
  peak. Conclusion already extracted: fix is upstream drafting (§5-C v2, live).
- Kaiser Crab x4, Insatiable x2: same stat-check shape.
- `6J4T046P13`/`F8ZVNDV045`/`KJPRHVQWU6` (f48): 5-7 turn overwhelm losses, no
  visible decision point; the Queen/Aeonglass picks above cover the same bosses
  with better tape.
