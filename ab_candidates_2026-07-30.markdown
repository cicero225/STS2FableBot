# Owner A/B candidates — boss fights worth replaying (2026-07-30 scan)

Scanned every boss death of 2026-07-30 (~25 fights) for decision-point density:
score flip-flops, potions dying in the belt, late hail-maries, winnable-looking
peaks. Each pick below has a specific falsifiable hypothesis — a rule we could
encode if the owner's line beats the bot's — not just "multiturn planner needed."

## A/B session prep (2026-07-30 evening — batching paused, seeds verified from tape)

**KIN — seed `9NUW6E6TGZ`** (Ironclad A0). Fight at f17. Bot's entry state, for
verifying the seed reproduces: 77/80 HP, 133g, belt [Radiant Tincture,
Gigantification, Entropic Brew, Speed], relics [Burning Blood, Phial Holster,
Whetstone, Tuning Fork, Centennial Puzzle, Pantograph, Ghost Seed], deck 19
(3x Battle Trance, Stoke, Bloodletting, Evil Eye, Bully, Spite, Dramatic
Entrance, Cruelty, Bash++, Strike++...). Fight opens: Kin Follower 59 + Kin
Follower 58 + Kin Priest 190. Bot lost in 15 turns, drinking 6 of 7 potions as
reactive hail-maries. WATCH FOR: when you commit potions (turn 1-2 all-in vs
staggered), and whether target discipline ever leaves the Priest.

**MATRIARCH — seed `R9NZLD49C1`** (Ironclad A0). Fight at f17. Entry: 62/80 HP,
179g, belt [Bottled Potential, Swift, Flex], relics [Burning Blood, Scroll
Boxes, Potion Belt, Anchor], deck 15 (Perfected Strike, Sword Boomerang++,
Dismantle, Uppercut, Tremble, True Grit, Spite + basics). Fight: Lagavulin
Matriarch 222 HP. Bot lost in 18 turns, zero hail-maries — the drain spiral
bled it out. WATCH FOR: your pacing — is there a turn-budget after which you
consider the fight lost regardless of HP (all-in before drain stack ~2)?

**Epoch caveat:** seeds are valid only if no unlock epoch advanced since the run
(wins #7/#8 happened today). Verify one seed in-game before scheduling a session.

## 1. `9NUW6E6TGZ` — The Kin, f17 — **PLAYED 2026-07-30, owner WON; fix shipped (62a6261)**
15 turns, peak +278, 7 potions drunk, 6 of them hail-maries. The bot entered at
~28 HP off a rest, spent potions REACTIVELY (one per near-death turn) in the
fight the owner's own rule says is a race-the-leader. 307-HP fight, Radiant
Tincture drunk for sustain mid-fight.
**Hypothesis:** §5.2 item 5's inversion — for a KNOWN-hard race, perfect play
front-loads the whole belt turn 1-2 (and target discipline never wavers off the
leader). If the owner wins this by committing everything early, the encodable
rule is: race fights extend the boss-start deploy lane to the FULL belt, not one
potion.

**RESULT:** owner won from 67/80 (ending 40) in 9 turns vs the bot's 15-turn loss
from 77/80. Belt front-load CONFIRMED (both potions by turn 2 — with the nuance
that one-turn debuff potions are TIMED for the best turn, not auto-T1). Targeting
HYPOTHESIS INVERTED: the owner killed the Followers first (scaling deck needs
time), the opposite of his June race with a burst deck — "no one strategy."
Encoded as fight-open plan selection: round-1 rollout of both target orders picks
per fight (62a6261). Belt-front-load + potion timing filed to the potion pass
(PLAN §5.2 item 14).

## 2. `A36ZF0WVBS` — Queen, f48 — **RESOLVED FROM TAPE, fix shipped (bb484dd)**
Entered at 95 HP, dead in 6 turns while the dps table called the Queen harmless
(2.1 mean). The fight window answered it without a replay: `TORCH_HEAD_AMALGAM_0`
(realized dps 24.8, hottest in the table) — she's a SUMMONER, and the forecast
priced her alone. `_upcoming_boss` now adds the Amalgam as a Kin-style minion
(full threat, no kill-HP). Residual owner question, lower priority: summon
cadence (does she re-summon after an Amalgam dies? kill-the-summon ever right?)
— worth asking next time one is on screen, not worth a dedicated session.

## 3. `XNTR7JTWGZ` — Aeonglass, f48 — **RESOLVED FROM TAPE, fix shipped (ea27f77)**
Four fight tapes named the whole kit: 3-turn cycle (26+Str single w/ Defend rider
-> 11x2+Str -> Empower +3-4 Str COMPOUNDING; single swing 26->40 by r10), opens
with Artifact 3 (early Vulnerable plans fizzle — the +581-peak-then-collapse
signature), and Withering Presence = "every 6 cards you play, add a Wither to
your Hand" (deck clog, not a stat drain). Artifact now modeled end-to-end
(detect_mechanics -> sim -> synth). Residual, lower priority: Wither/StatusCard
clog in the sim (ENEMY_PASS refinement); no dedicated owner session needed —
the remaining question is play style vs the compounding ramp (all-in early?),
which the Kin/Matriarch sessions already cover in spirit.

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

---

## Act-3 boss A/B slate (2026-08-01 night — post-epoch seeds, all f48 deaths)

**1. `E4ZW92AFP5` — Aeonglass (RECOMMENDED).** The purest "promising run died"
case on record: the DFS forecast read **est loss 38** vs a 38-42 HP rest-gate
margin — the closest-to-winnable read any act-3 death has produced — and the
run still lost in 8 turns. Entry 62/91, 17 relics (Whispering Earring, History
Course, Vajra, Happy Flower), 31-card deck with Barricade++/Dominate/Unmovable.
Fight opens: Aeonglass 448. THE question: is the residual a play-quality gap
(you win comfortably) or honest variance (you barely lose)? Highest information
per minute of any candidate.

**2. `U2T0A11MXZ` — Queen.** Peak +302 mid-fight = a winnable-looking position
lost late. Entry 54/70, 18 relics (Brimstone, Kunai, Spiked Gauntlets — an aggro
kit), 28 cards. Tape intel bonus: Torch Head Amalgam was ALREADY on field r1
(199 HP beside Queen 400) — concurrent, not summoned late; matches the forecast
model.

**3. `SBBZ075SQX` — Test Subject #C33.** Densest decision profile (9 turns, 6
potions, 4 hail-maries). Entry 73/78, Shuriken/Sai/White Beast Statue multi-
attack kit + 3x Bloodletting++ engine vs the 100/200/300 Nemesis staircase.
Best candidate for reading YOUR stage-transition pacing (when do you hold burst
for the next heal-wall?).

Caveat: a full act-3 A/B is a 48-floor climb (~45-90 min at 1x) — one seed is
a full evening activity. Fingerprints above are boss-ENTRY states; the f1-f17
segment should match the bot's route only loosely (your drafts will diverge).
