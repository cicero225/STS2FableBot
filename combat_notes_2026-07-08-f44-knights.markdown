# Combat notes 2026-07-08 — the f44 Knights one-turn kill (owner's recorded win, seed `7Q4QCYQ09J`)

Owner-flagged as the run's proudest fight: the Act-3 elite pack just before the boss —
**Flail Knight 101 + Spectral Knight 93 + Magi Knight 82 = 276 HP — cleared entirely in
ROUND 1**, ending at 76/103 HP with 32 block up. Reconstructed from the state trace
(`logs/manual/runs/20260708-212420_the ironclad`, states ~1702–1790). The recorder logs
states, not actions, so per-card effects below are **inferred from state deltas** — the
sequence is solid; individual damage attributions are best-effort.

## The line (all one turn)

Opening: 3 energy; hand after draw = Cascade+(X), Perfected Strike+, Burning Pact,
Entropy, Crimson Mantle, Bloodletting, Tremble. Potions: **Duplicator, Colorless Potion,
Skill Potion** (belt full — Delicate Frond refills it every combat, so spending all three
is ~free).

1. **Colorless Potion → chose Rolling Boulder (0-cost)**; **Skill Potion → chose
   Forgotten Ritual (0-cost)**. Both potions used as *card generation*, and both picks are
   0-cost so they fuel the same turn.
2. **Bloodletting** (−3 HP → +2 energy; 3→5). Two free cards appeared in hand here
   (Anger, Stampede+) — likely a draw relic trigger (Pendulum / Prayer Wheel — verify).
3. Free damage: **Rolling Boulder**, **Anger** (Magi 82→72).
4. **Burning Pact** (exhausted Tremble — deck *filtering* ahead of the Cascade payoff —
   drew Strike + 2nd Crimson Mantle). **Strike** (Magi →57).
5. **Forgotten Ritual**: energy 4→**7** and ~5 damage to ALL three (inferred: "gain 3
   Energy, deal 5 to all"? verify text). This is the energy spike that pays for the rest.
6. **Crimson Mantle ×2** (powers down mid-combo), **Stampede+** (queues end-of-turn
   attack auto-plays — this matters at the end).
7. **Duplicator potion → Cascade+ at X=4** (energy 4→0): the next card plays twice, so
   Cascade resolves **twice — 8 deck cards auto-played**. The trace shows the payoff
   avalanche: block climbing 4→9→12→16→21→26 (Colossus among the flips), the whole hand
   turning *upgraded* mid-fight (a Brand autoplay — "upgrade your hand"? verify), and all
   three Knights melting: Magi →33→28→4→dead, Spectral 88→69→59→54→49, Flail 96→80→61→56→51.
8. Cascade's draws left **Bloodletting+ in hand → played it** (−3 HP, energy 0→**3**) — a
   second energy refuel *after* going to zero — then **Entropy+**, **Perfected Strike+**
   (Spectral dead), **Strike+** (Flail 51→23), **Burning Pact+**.
9. **End of turn: Stampede+'s queued auto-attacks finish Flail** (23→18→0). The "one-turn
   kill" technically completes in the end-of-turn phase — lethal math had to count the
   queued auto-plays.

## Why this is a useful canonical example (what the bot would need)

Every hard item from the owner's human-baseline list (PLAN §8.4) appears **in one turn,
composed**:

- **Potions as combo pieces, not emergency valves.** Two of three potions *created cards*
  (with context-aware 0-cost picks), the third (Duplicator) was held to double the
  biggest X-play. None of this fits the current taxonomy (reactive/proactive/hail-mary);
  with Delicate Frond the correct frame is "3 free cards per fight, spend them for tempo."
- **Sequencing with dynamic resources:** two separate energy refuels (Bloodletting pre-
  and post-Cascade, Forgotten Ritual) interleaved so the turn never stalls at 0 — the
  planner's fixed-energy DFS can't represent "spend to zero, then refuel and continue."
- **Cascade valuation requires draw-pile knowledge** — Burning Pact filtered the deck
  *first*, and by f44 the deck (38 cards, but attack/value-dense after the run's
  upgrades) made "top 8 cards" a good bet. Luck helped (owner's own caveat), but it was
  a *shaped* bet, not a gamble.
- **Duplicator × X-cost interaction** — the single highest-leverage decision of the
  fight; a per-potion handler would need "pair with the best multiplicable play."
- **Queued end-of-turn damage (Stampede) counted toward lethal** — the bot's lethal calc
  stops at played cards; here ~23 HP of the kill arrived after the last card.
- Aside for the model: the mid-fight **hand-wide upgrade** (Brand?) is a mechanic we have
  no representation for at all (cards changing identity mid-combat).

None of this is scheduled work; it's the §8.3 per-card pass + §5-C multi-turn layer seen
end-to-end in a single real example. When that work opens, this fight is the acceptance
test: *could the planner find (or even approximate) this line?*
