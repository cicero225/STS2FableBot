# Combat notes 2026-07-08 — the f44 Knights one-turn kill (owner's recorded win, seed `7Q4QCYQ09J`)

Owner-flagged as the run's proudest fight: the Act-3 elite pack just before the boss —
**Flail Knight 101 + Spectral Knight 93 + Magi Knight 82 = 276 HP — cleared entirely in
ROUND 1**, ending at 76/103 HP with 32 block up. Reconstructed from the state trace
(`logs/manual/runs/20260708-212420_the ironclad`, states ~1702–1790), then
**owner-corrected 2026-07-08** — the corrections themselves are instructive (see the
relic-attribution lesson at the bottom).

## The line (all one turn) — owner-corrected causality

Opening: 3 energy; hand after draw = Cascade+(X), Perfected Strike+, Burning Pact,
Entropy, Crimson Mantle, Bloodletting, Tremble. Potions: **Duplicator, Colorless Potion,
Skill Potion** (belt full — Delicate Frond refills it every combat, so spending all three
is ~free).

1. **Colorless Potion → chose Rolling Boulder** (a **Power**: "at the start of your turn,
   deal 5 damage to ALL enemies and increase this damage by 5"). **Owner's own verdict:
   a misplay *in the turn that resulted*** — it never ticked, because the fight ended this
   turn. But the pick was made *before* knowing the Cascade output, as setup damage for
   what could have been a hard multi-turn fight. Lesson: expert picks are EV bets under
   uncertainty, and even the "wasted" pick was principled — a planner evaluating this
   select needs the same expected-fight-length estimate (§5-C), not hindsight.
2. **Skill Potion → chose Forgotten Ritual** ("If you exhausted a card this turn, gain 3
   Energy. **Exhaust**.") — and the owner **checked the hand for an exhaust enabler
   *before* making this pick** (Burning Pact qualifies). Select-time cross-validation:
   the value of the picked card depended on the rest of the hand being able to switch it
   on. Both potion picks are 0-cost, fueling the same turn.
3. **Bloodletting** (−3 HP → +2 energy; 3→5). The HP loss tripped **Centennial Puzzle**
   ("the FIRST time you lose HP each combat, draw 3 cards") — that's what put Anger +
   Stampede+ (+1 more) in hand. A relic turning a card's *cost* into a *benefit*.
4. Free damage: **Rolling Boulder** (played as setup — see 1), **Anger** (Magi 82→72).
5. **Burning Pact** (exhaust Tremble, draw 2). **NOT deck-filtering for Cascade** (Tremble
   was in hand, not the draw pile) — it was **the exhaust trigger for Forgotten Ritual**,
   the enabler checked at step 2.
6. **Forgotten Ritual**: energy 4→**7** (its +3, trigger satisfied). The simultaneous ~5
   damage to ALL was **Letter Opener** ("every time you play 3 Skills in the same turn,
   deal 5 damage to all enemies") — a skill-count relic firing mid-combo, not part of the
   card's text.
7. **Crimson Mantle ×2** (powers down mid-combo), **Stampede+** (queues end-of-turn
   attack auto-plays — this matters at the end).
8. **Duplicator potion → Cascade+ at X=4** (energy 4→0): the next card plays twice, so
   Cascade resolves **twice — 8 deck cards auto-played**. The payoff avalanche: block
   4→9→12→16→21→26 (Colossus among the flips), the whole hand turning *upgraded*
   mid-fight (a Brand auto-play — "upgrade your hand"? verify), Letter Opener presumably
   still ticking on autoplayed Skills, and all three Knights melting: Magi →4→dead,
   Spectral 88→49, Flail 96→51.
9. Cascade's draws left **Bloodletting+ in hand → played it** (−3 HP, energy 0→**3**) — a
   second refuel *after* going to zero — then **Entropy+**, **Perfected Strike+**
   (Spectral dead), **Strike+** (Flail 51→23), **Burning Pact+**.
10. **End of turn: Stampede+'s queued auto-attacks finish Flail** (23→18→0). The
    "one-turn kill" completes in the end-of-turn phase — lethal math had to count the
    queued auto-plays.

## Why this is a useful canonical example (what the bot would need)

Every hard item from the owner's human-baseline list (PLAN §8.4) appears **in one turn,
composed** — plus a layer the first draft of these notes got wrong:

- **Relic triggers are load-bearing and invisible to the planner.** Three relics did real
  work: Centennial Puzzle (3 cards off the first HP loss — making Bloodletting's cost a
  draw engine), Letter Opener (repeated 5-AoE off skill counts), Delicate Frond (potion
  abundance). The first reconstruction mis-attributed both of the first two to cards —
  **exactly the mistake the bot would make**: state deltas without relic knowledge assign
  effects to the wrong causes. Owner: "may be worth parsing through the list of relics,
  which unfortunately adds a lot of complication." → filed as the relic pass (PLAN §8.5).
- **Potions as combo pieces, not emergency valves** — two of three potions *created
  cards*, with select-time cross-validation (Forgotten Ritual picked only after
  confirming an exhaust enabler in hand); Duplicator held to double the biggest X-play.
- **Enabler chains:** Burning Pact → (exhaust happened) → Forgotten Ritual's +3 energy.
  The planner has no concept of "play A to switch on B's conditional text."
- **Sequencing with dynamic resources:** two energy refuels (Bloodletting pre- and
  post-Cascade, Forgotten Ritual) interleaved so the turn never stalled at 0.
- **Cascade valuation requires draw-pile knowledge** (and Neow's-Fury-style tutoring —
  see PLAN §8.4 — requires **discard-pile** knowledge; both piles are player-visible).
  Luck helped the Cascade flips (owner's caveat), but it was a shaped bet.
- **Queued end-of-turn damage (Stampede) counted toward lethal** — ~23 HP of the kill
  arrived after the last card was played.
- The mid-fight **hand-wide upgrade** (Brand autoplay?) remains unrepresentable — cards
  changing identity mid-combat.

None of this is scheduled work; it's the §8.3 per-card pass + §5-C multi-turn layer +
the new relic pass seen end-to-end in one real example. When that work opens, this fight
is the acceptance test: *could the planner find (or even approximate) this line?*
