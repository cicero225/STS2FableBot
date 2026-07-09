# Card Pass — Ironclad card-by-card logic (owner-requested 2026-07-09)

The §8.5 item-4 scrub, expanded into its own plan (ENEMY_PASS.md precedent). Owner framing:
**two steps — (1) how to tactically PLAY each card, (2) DRAFTING considerations** — with
subagents examining cards in parallel. Step 1 ships value immediately and feeds step 2
(a card the planner learns to play automatically sheds its planner-blind draft dock).

## Why this order works

The planner-blind dock (`penalty_planner_blind`, owner-approved) means **step 1 IS a
drafting improvement**: every card the parser/planner learns to read stops being docked at
draft time with zero extra work. Step 2 then only has to cover what play-modeling can't:
enabler-dependence, anti-synergies, deck-context.

## Data layer (step 0)

- **Ground truth**: the mod's `GET /api/v1/compendium` → `card_library.discovered_ids`
  (250 currently) + `GET /api/v1/wiki?q=<id>` → full entry: base AND upgraded rules text,
  type, rarity, keywords. All local, no scraping. (Wiki only serves *discovered* cards —
  fine: undiscovered cards can't be offered to this profile either; re-run the extractor
  after unlocks.)
- `scripts/build_card_catalog.py` → `data/card_catalog.json`: one entry per card
  (id, name, type, rarity, cost, base/upgraded text, keywords), tagged Ironclad /
  colorless / other via the Spirebird priors' per-character tables (ambiguous → agent
  judgment). Include **exposure** stats (compendium times_picked/times_lost + Spirebird
  pick counts) so impact is rankable.

## Step 1 — the PLAY pass

**Per-card question:** "does the one-turn planner play this card correctly, and if not,
what's the smallest change that fixes it?"

**Classification taxonomy** (from this week's live lessons — most cards are NOT bespoke):

| Class | Meaning | Recent examples | Action |
|---|---|---|---|
| A | Fully modeled by textparse+planner | Strike, Defend, Bash | none — mark verified |
| B | **Parser gap** — a generic text pattern | Conflagration ("N times" after target clause), energy icons, "(Hits N)" | extend textparse; auto-fixes every card sharing the phrasing |
| C | **Planner mechanic** — needs sim support | Rage (sequencing), Fiend Fire (hand-scale), Retain-hold, Apotheosis (power-like Skill) | generic mechanic if ≥2 cards share it, else per-card annotation |
| D | **Multi-turn / §5-C class** — beyond one-turn horizon | Inferno upkeep, draw-pile lookahead, Cascade | FILE with the §5-C backlog, don't force |

**Subagent structure** (owner-authorized):
1. **Fan-out**: chunks of ~12 cards per agent. Each agent receives: its cards' full
   catalog entries; a capability digest (what `textparse` recognizes; the planner's
   existing mechanics: caps/Slippery/Artifact/stun/Rage/Fiend-Fire/X-cost/potions/
   stranded-status/asleep/facing); and the classification taxonomy. Returns structured
   JSON: per card — class, evidence (which text the parser misses), proposed handling,
   impact guess (exposure-weighted), confidence.
2. **Synthesis** (single agent or main loop): dedupe cross-card patterns — five cards
   sharing an "exhaust synergy" phrase are ONE class-C mechanic, not five handlers
   (the Conflagration lesson: one regex fixed three cards). Output: an ordered worklist
   — parser fixes (B) first, shared mechanics (C) second, bespoke C stragglers third,
   D filings last.
3. **Implementation**: mock-first per project rule — every behavior change lands with a
   test using the card's REAL text; replay suite must stay clean; batch validation after
   each implementation tranche, not after every card.
4. **Bookkeeping**: `data/card_notes.json` = the per-card annotation table (class,
   status, notes) — the pass's checklist, mirroring `bestiary.json`'s role for enemies.

**Verification**: agents work from real card text, not memory; anything an agent flags
"uncertain" or that contradicts observed behavior gets a targeted re-check against run
logs before implementation (a second agent or the main loop, not trust-by-default).

## Step 2 — the DRAFT pass (after step 1 + one validation batch)

Builds on `card_notes.json`. Per-card drafting considerations the play-model can't express:
- **Enabler-dependence** (owner's standing example: Rupture needs self-HP-loss sources;
  Expect a Fight needs attack density) → conditional score gated on "enabler in deck".
- **Anti-synergies / archetype tension**; boss-dependent value (Bloodletting vs Soul
  Fysh); curve/deck-size effects beyond the existing heuristics.
- Output: the **conditional-card list** — which, per the owner's explicit steer
  (PLAN §8.4 deck-aware drafting), goes to the OWNER for review before it ships.

## Guardrails

- **No universal micro-rules** where a general term exists (the standing owner steer) —
  prefer parser/mechanic generality; bespoke handlers only for the genuinely bespoke.
- **Depth-aware caution** (§8.1): don't let step-2 penalties suppress scaling cards
  globally; the powers-confound lesson applies to draft changes derived from play data.
- The f44 Knights one-turn-kill remains the acceptance benchmark for what "fully
  correct play" looks like; step 1 is not expected to reach it — it's expected to
  eliminate the *silent* misplays (unparsed values, missed mechanics).

## Cadence

Step 0 + step 1 fan-out and synthesis fit one working session with subagents; the
implementation tranches land as separate commits with a validation batch between B and C
tranches. Step 2 starts only after step 1's batch shows no regressions.
