# StS2 Bot — Implementation Plan

*Companion to [REQUIREMENTS.md](REQUIREMENTS.md). Drafted 2026-06-11. This is the working
map: update it as phases complete or decisions change (it is allowed to be wrong and then
corrected — history lives in git).*

---

## 1. Architecture

```
┌─────────────────────────────  this repo (Python)  ─────────────────────────────┐
│                                                                                │
│  orchestrator/          climb manager · run lifecycle · watchdog ·             │
│      │                  attended/unattended modes · game process mgmt          │
│      ▼                                                                         │
│  agent loop:  GET state ──► parse (models) ──► route by state_type             │
│      ▲                                            │                            │
│      │                                            ▼                            │
│  client/  (HTTP)                            policy/  (pure functions)          │
│      ▲                                      combat · map · card_reward ·       │
│      │                                      shop · event · rest · potion ·     │
│      │                                      start_bonus · menu                 │
│      │                                            │     ▲                      │
│      │                                   scores + rationale                    │
│      │                                            │     │                      │
│      │                                            ▼     │                      │
│      │                                      kb/  (static per game version)     │
│      │                                      cards · relics · enemies ·         │
│      │                                      priors (Spirebird) · synergies     │
│      ▼                                                                         │
│  runlog/   JSONL decision log · SQLite run index · LLM usage ledger            │
│  llm/      post-run debrief · unknown-content triage · narrator (opt-in)       │
│  replay/   re-run policies offline against logged states                       │
└────────────────────────────────────────────────────────────────────────────────┘
            │  localhost:15526 REST
            ▼
┌──────────────────────────────  game side (C#)  ────────────────────────────────┐
│  STS2MCP mod  (upstream binary for P0–P1; our fork from P2:                    │
│  + SP ascension selector  + speed/timescale control  + master deck in state)   │
│  Slay the Spire 2 · Godot 4.5/C# · release branch · bot plays profile slot 2/3 │
└────────────────────────────────────────────────────────────────────────────────┘
```

Key principle (REQUIREMENTS C2/C6): policies are **pure functions** `(state, kb, config) →
(action, scores, rationale)` — no I/O inside policy code. That makes every decision
unit-testable, replayable, and loggable for free.

**No-fork-needed insight:** a fresh profile starts at Ascension 0 and stock STS2MCP covers
every action M0–M1 needs. The C# fork is deferred to P2, where ascension selection, speed,
and master-deck state actually matter. P0–P1 run on the upstream release binary.

## 2. Repo layout

```
sts2bot/                  Python package
  client/                 REST client, typed state models, action senders
  policy/                 one module per decision domain + shared scoring utils
  kb/                     content DB build/load, Spirebird priors import
  orchestrator/           run loop, climb manager, watchdog, process mgmt
  runlog/                 JSONL writer, SQLite index, LLM ledger
  llm/                    advisor calls (budget-capped), narrator
  replay/                 offline re-evaluation harness
  cli.py                  entry point (`python -m sts2bot ...`)
tests/                    pytest; fixtures/ holds captured & doc-derived states
config/                   policy parameters (versioned!), bot settings
data/                     KB artifacts (committed if small), spirebird exports
scripts/                  setup helpers (mod install, save backup, KB refresh)
external/                 gitignored clones for reference (STS2MCP)
```

## 3. Stack decisions

- Python 3.14 (installed here), stdlib `venv` + pip, `pyproject.toml` (no uv on box).
- **pydantic v2** for state models (validation = patch-drift detection per C5),
  **httpx** for the client, **typer** for CLI, **pytest**, **ruff**.
- SQLite (stdlib) for run index; JSONL for decision logs (one file per run).
- Config as TOML in `config/` with a content hash recorded per run (FR-3.4).
- LLM calls via `anthropic` SDK, behind one gateway module with the ledger + caps.

## 4. Phases

### P0 — Plumbing (→ M0: full unattended run, trivial policy)
Build **mock-first**: STS2MCP's `docs/raw-full.md` documents exact response shapes, so the
entire loop is built and tested against fixtures before ever touching the live game.

1. ✅ Scaffold package, venv, pyproject, ruff/pytest config.
2. ✅ State models for every `state_type` + action senders (from API docs).
3. ✅ Agent loop: poll → parse → route → act → log; popup/menu/game-over recovery
   reflexes; stall + error-streak safety rails; `sts2bot doctor` / `sts2bot play` CLI.
4. ✅ Trivial policies (first-legal-choice) for every state_type.
5. ✅ Run logger v1: JSONL decisions + run header/outcome rows in SQLite.
6. ✅ Scripted mock game replaying doc fixtures; full synthetic run (menus → Neow →
   map → combat → rewards → rest → game over → menu) passes E2E in tests.
7. ✅ Live setup done 2026-06-11 (see LOG.md): mod installed, isolation confirmed
   (modded save scope is a separate tree — bot uses modded `profile1`), three
   doc-vs-live gaps fixed, **first complete live run** (Ironclad A0, died floor 9,
   159 decisions, ~5 min). Outcomes now enriched from the game's `saves/history/*.run`
   records (win/seed/build_id/killed_by — authoritative).
8. Remaining investigation items: how "Play with Mods" launches non-interactively
   (CLI arg? needed for P2 crash-relaunch); locked-character representation at
   character select (matters when unlock chain starts).

**Exit:** bot finishes real runs end-to-end at A0 unattended-while-watched, logs complete.
*Status: behavior demonstrated live; a few more shakeout runs before calling M0 closed.*

### P1 — Competence (→ M1: ≥40% win rate at A0, one character, n≥20)
1. KB build: compendium endpoint + game-version stamp; diff tooling for patches.
2. Spirebird priors: one-time export import (owner-assisted download OK), normalize to
   per-card/per-relic pick-value tables; fallback = hand-seeded priors for ~Ironclad.
3. Combat policy B (see §5): one-turn planner with tunable eval weights.
4. Deck policies: card reward / shop / rest / upgrade with archetype awareness (priors +
   simple synergy tags), deck tracked incrementally in Python (master deck fork lands P2).
5. Map routing: value-per-node heuristics (elites/rests/shops vs HP state).
6. Event policy: per-event choice table for known events, safe default for unknown.
7. Replay harness: re-run new policy against logged runs; fixture suite from real logs.
8. Start LLM ledger + unknown-content triage (FR-6.2) — cheap model, hard cap.

**Exit:** M1 stats from the run index; Ironclad (or best character) ≥40% over 20+ runs.

### P2 — Climb machinery (→ M2: A0→A10 with one character)
1. C# fork (live at github.com/cicero225/STS2MCP, builds via build.ps1 + .NET 9):
   ✅ **feature-complete 2026-06-11** — character-select commit fix, ascension
   selector, set_time_scale (3x ≈ 1.5–2x effective decision rate), master deck in
   state; all live-verified (see LOG.md). Remaining: epoch-reveal investigation
   (parked); upstream PR (owner's call).
2. Climb manager: pick character/ascension per policy (FR-4.2), unlock-chain handling,
   stop conditions, crash/hang watchdog + game relaunch, resume-from-save.
3. Unattended mode behind explicit flag (FR-4.4) + status report (NFR-3).
4. Ascension-aware policy adjustments (A1–A10 modifiers change eval weights).
5. Post-run LLM debrief loop live (FR-6.1) with config-diff proposals → owner-audited.

**Exit:** one character climbs to an A10 win, mostly unattended, no save corruption.

### P3 — All characters (→ M3: the full climb)
1. Character-specific policy packs (Silent/Defect/Regent/Necrobinder mechanics: orbs,
   pets, stars; archetype tables per character from priors).
2. Tuning loop cadence: batch debriefs, config evolution in git, win-rate dashboards.
3. Optional narrator (FR-6.3) once attended-watching gets boring.

**Exit:** A10 win on all five characters from the fresh profile. 🏔️

### P4 — Optimization (M4, open-ended)
Deeper combat search, learned weights from accumulated logs, Spirebird refresh cadence,
possibly streaming. Direction set by what the data says is losing us runs.

## 5. Combat policy phasing (the hard part)

- **A (P0):** play first playable card until none playable, end turn. Exists only to
  exercise plumbing.
- **B (P1):** one-turn planner. Enumerate playable sequences this turn (with pruning:
  cards are mostly order-insensitive within categories; cap branching), score resulting
  end-of-turn state: enemy damage dealt (weighted by kill progress), block vs. summed
  incoming intent, status/power deltas, energy efficiency, hand quality next turn.
  Weights in `config/combat.toml`. Potion policy: thresholded (use when fight-losing risk
  or boss). Explicitly *not* a full game simulator — effects approximated by tables in kb.
- **C (P2+, data-driven):** extend lookahead where logs show B losing (multi-turn setups,
  AoE timing, stance/orb/pet micro). Options: partial simulator for the ~50 most common
  effects, beam search over 2 turns, or per-character heuristic modules. Decide from
  loss analysis, not speculation.

### 5.1 §5-C capability estimate — design (2026-06-16)
The recurring root lever (memory `combat-capability-estimate-is-the-root-lever`; §8.3/§8.4): nearly
every contested combat/route call — race-vs-turtle, minion-leader vs chase-minions, elite/path
appetite, rest timing, multi-phase burst — is one question the one-turn planner can't answer:
**"can I win this fight, and at what HP cost?"** The 2026-06-16 routing batch made it concrete —
HP-aware elite-chasing took elites the bot *survives* but can't *win* with a weak deck (no benefit,
one death to a chased Terror Eel). The fix isn't more micro-rules (owner's repeated steer) — it's a
forward estimate. **The shipped stopgaps it will retire:** the `gains_strength / incoming≥6` minion
bias, the anti-turtle combat weights, and the HP-only elite gate in the map scorer.

**Model: a closed-form HP-race**, not a stochastic simulator (that's P4, only where the race model
mispredicts in logs — "measure don't simulate"). The owner's own framing *is* a race ("close the
leader before the ramp out-scales me"; "58 dmg on a 58-HP Follower loses the race"):

  `estimate_fight(my_hp, deck/relics/powers, enemies, config) -> FightOutcome(win, exp_end_hp, turns, margin)`

- **My output/turn:** the deck's expected damage & block per turn — reuse `parse_card_description`
  (`CardEffects`) over the deck ÷ cards-drawn-per-cycle, scaled by Strength & energy. A deck-average,
  not a draw simulation.
- **Enemy threat:** Σ enemy damage/turn from current intents (`parse_intent_damage`) + **ramp**
  (`gains_strength` → +Str/turn) − my block/turn. **Slippery** (Vantom) caps my *effective* damage
  (first HP-loss/turn → 1). **Minion structure:** race the **leader** (leader-kill ends it); a
  **summoner**'s minions don't add to the kill total (treadmill), **fixed adds** (Kin) do.
  **Multi-phase** (Test Subject Adaptable): sum effective HP across phases.
- **Verdict:** `turns_to_kill_leader < turns_to_kill_me` → win; `exp_end_hp = my_hp − net_enemy_dps
  × turns_to_kill`; margin → confidence.

**Consumers (one estimate replaces the stopgaps):** *map routing* — gate `elite_relic_value` on
`estimate_fight(elite).win` (the batch fix) + rest on a dangerous-fight `exp_end_hp` floor; *combat*
— race-vs-turtle / minion-leader from the same estimate.

**First increment — ✅ landed 2026-06-16 (mock-first):** `estimate_fight` race model + `deck_output`
in `sts2bot/policy/capability.py` (11 canonical tests: Vantom/Slippery, leader-race, ramp, starter-
vs-built). **Wired into the map elite gate:** the survivable-elite relic bonus applies only if the
deck can *win* a typical elite of the act (`_GENERIC_ELITE` prior) with an HP margin
(`elite_gate_min_end_hp_pct`); a starter-heavy deck stays elite-neutral. Map `DeckCard`s carry no
rules text, so `deck_output` prices them via a harvested `id|upgrade→description` table
(`scripts/build_card_effects.py`). *Open:* re-batch to calibrate `_GENERIC_ELITE` (loosen if no
elites taken / tighten if elite deaths persist); then combat-side rewiring (race-vs-turtle from the
same estimate), and `deck_output` refinements (energy relics, X-cost, scaling cards).

## 6. Working conventions

- Mock-first; live game sessions are attended (owner present) until owner flips
  unattended on. Every live session starts with `scripts/backup_saves.py`.
- Commit per coherent step; config changes are separate commits (FR-3.4 auditability).
- After each live milestone: short LOG.md entry (date, game version, what happened) —
  the project's lab notebook.
- Re-clone reference repos when absent: `git clone --depth 1
  https://github.com/Gennadiyev/STS2MCP external/STS2MCP`.
- LLM usage: ledger from day one, even in dev (FR-5.4).

## 7. Open investigation items (rolling)

| Item | Phase | Notes |
|------|-------|-------|
| Modded non-interactive launch (CLI arg vs launcher memory) | P0.8 | check Steam launch options / Godot args |
| Real save path + Steam Cloud behavior per profile | P0.7 | decide cloud on/off before first bot launch |
| Locked character/ascension representation in API | P0.8 | affects climb manager |
| Spirebird export shape & licence/courtesy ask | P1.2 | jorbs Discord if unclear (C4) |
| Game patch cadence on release branch | P1+ | informs KB diff automation priority |
| StS2 ascension cap (10 vs 20) | P2 | owner reports 10 currently; verify in-game |
| Safe automation of Timeline epoch *reveals* | P2 fork candidate | mod automates timeline advance/back + queued unlock screens, but deliberately refuses to force-reveal "Obtained" epochs ("invalid unlock path"); decompile the reveal flow to see if a safe replication exists, else it stays a rare owner click |

## 8. Backlog: drafting sophistication & strategy (owner notes 2026-06-14)

Owner-raised future topics. Data-feasibility checked against the committed Spirebird
cohort export (`data/spirebird/cohort_stats.json` — 57-field per-card entries; cohorts
`all / a10 / midA10 / strongA10 / a10Sub50 / a10Sub75`; per-cohort sections
`summary / cards / relics / events`).

### 8.0 Current priority (2026-06-16, from the standard-batch evidence)
The wall is **deck power**, manifesting as a chain: weak decks deal ~5 dmg/round → normal fights
drag 15+ rounds → cumulative chip-bleed → arrive at the Act-1 boss at 38–69/80 HP → lose (0/5; 2/5
reach Act 2 after §8.1d). **Sharpened 2026-06-16 (post anti-turtle weights):** boss-entry HP rose to
77–80/80, yet the bot *still lost the Act-1 boss at full 80/80* (run 4, 10 rounds) — so **deck power
is the *binding* constraint; HP/routing is necessary-but-not-sufficient.** Weight the priority toward
**deck-strengthening** (removal, elite→relic routing, synergy) over pure HP-management. Order:
1. **Routing / whole-route path-EV (§8.2)** — ✅ **2026-06-16.** Hits two links: the bleed (arrive at
   the boss healthy) AND the elite/relic deficit (the bot under-takes elites → starves itself of relics
   → weak deck). (a) combat-stats split early-act vs late (monster_early p75=5 vs monster p75=18 over
   90 runs); (b) HP-aware map DP — projects HP along each route via the bot's own p75 loss, penalises
   routes it can't survive, and rewards a *survivable* elite for its relic (net +16, just above
   treasure), so the bot now **chases elites at ~70+ HP** and rests/avoids when low (real-map replay
   confirms). Caveat: far-future (boss) death is path-discounted → whole-route boss-survival is softer
   than the robust near-term elite-affordability check; deeper survival is a later pass.
2. **Ancient / relic-choice awareness** — ✅ 2026-06-16. StandardRouter `_relic_select` ranks free
   relic choices (Neow, start of Act 2/3, treasure) by value (`shop_stats.relic_war`) instead of
   TrivialRouter's `relics[0]` (was effectively random).
3. **Removal aggressiveness** — ✅ 2026-06-16. Starter-heavy decks spend down to a smaller gold
   reserve for shop removal (scaled by % basics), still under the 150g price cap. Marginal by design
   (removal chances are rare — owner).
3. **Combat aggression stopgap** — ✅ 2026-06-16 (anti-turtle weights: block double-count trimmed,
   healthy HP-loss penalty flattened). A placeholder for §5-C; batch-tuned, not principled.
4. **Per-enemy special-cases (§8.3)** — Vantom Slippery, Test Subject Adaptable, …; each unlocks a boss.
5. **Multi-turn fight planning / capability estimate (§5-C)** — the *real* combat answer (race-vs-turtle,
   minion targeting, rest all flow from it). Biggest lift; deferred but "not forever" (owner).
6. **Synergy/archetype drafting (§8.1a)** — deepest deck-power lever; data-gap-blocked (co-occurrence).
- *Done this session:* §8.1d take-vs-skip scaling (✅ 2/5→Act 2); 6 combat/potion fixes (summoner,
  value potions, discard, Illusion, enchant-hang, value-rank discard). *Non-bug:* max-HP valuation.
- *Quick fruit (opportunistic):* Vambrace first-block, Stampede timing, Dominate-early, potion value-allocation.

### 8.1 Card drafting beyond single-card Elo
Current: card rewards scored by one pooled Elo prior ([data/priors_cards.json](data/priors_cards.json)),
discounted for pilotability, plus by-act tilt and a few heuristics. Refinements:

- **(a) Multi-card synergy** — value of a card *given another is already in the deck*.
  **Data gap:** the cohort export is per-card aggregates only; no co-occurrence /
  conditional fields. Realistic paths: (i) hand-curated synergy/archetype tags (overlaps
  the existing "deck-archetype awareness" item), or (ii) a different source exposing
  pairs (raw run files, or ask via jorbs' Discord whether such a product exists). Highest
  strategic value, highest effort — table until archetype work begins.
- **(b) Elo/WAR by act** — ✅ **done 2026-06-15** (de-biased per-act tilt; see LOG).
- **(c) Elo by deck size** — **data gap:** cohorts slice by ascension/skill band, not deck
  size. Not data-driven here. A small `deck>25` penalty already exists heuristically;
  could extend it, but it stays hand-tuned rather than community-derived. Lowest priority.
- **(d) Dynamic take-vs-skip threshold** (owner, 2026-06-15; tabled for the slowed-down
  note-taking run). Top players almost never skip the *first* card pick. The `take_threshold`
  should not be flat: strong preference to take *something* early, decreasing with each card
  added — and scale with **deck power**, especially the *fraction of starter cards still in
  the deck* (a weak basic-heavy deck should take more readily than a refined one). A first
  approximation: lower the threshold by a term proportional to (% basics remaining) and/or
  (cards added so far). NB: the observed Armaments/Molten Fist/Bludgeon skip was itself
  defensible (all negative community priors) — this is about the *first-pick* and
  deck-state scaling, not that specific call.

  *Bonus findings, same export:* per-cohort **`relics` and `events`** sections exist →
  relic/event priors are available for the shop/event work below. **Skill-band cohorts**
  (`strongA10`, `a10Sub75`…) exist → as piloting improves we could shift the prior cohort
  upward (ties to the pilotability discount).

### 8.2 Strategy notes
**Status 2026-06-16:** the HP-aware path-EV scorer is **implemented** (the DP below: per-route HP
projection from the bot's own p75 loss, survivable-route preference, survivable-elite relic bonus,
early-act fight split). *Still open:* parallel **gold** estimate + shop-bonus, **character-specific**
net-loss (other chars lack Ironclad +6), boss-HP flexibility (b), branchy-path bonus + per-branch
re-assess (c), and **deck-power node gating** (can my deck actually clear this node — below).
- **Elite-rushing for relics.** ✅ Now HP-aware: a *survivable* elite earns a relic bonus, so the bot
  chases elites at ~70+ HP and backs off when low — instead of the old flat avoidance. Appetite still
  keys only on HP, not deck-strength/act; revisit those tilts when climbing ascensions.
- **Whole-route path awareness** (owner, live 2026-06-15: every individual fight handled fine,
  but the bot routed itself through a monster gauntlet with no rest and bled out — now a real
  ceiling). The map scorer is greedy per-node with shallow lookahead (`lookahead_discount`,
  `path_step_discount`); it never prices a *whole path's* cumulative HP loss against the rests
  on it. Owner's principled design:
  - Enumerate all paths to the boss; estimate **HP along each** = running HP − Σ(expected loss
    per fight on it, by type: normal / elite, from combat-stats) + Σ(campfire heals). Keep the
    **survivable** ones (HP stays above a floor). Note the combat-stats loss is *net* (measured
    from logs), so the **Ironclad +6 HP/combat is already baked in** — don't add it again; just
    keep the estimate **character-specific** (other characters lack that heal).
  - Among survivable paths prefer **≥1 elite** (bank relics — light elite-chasing), and add a
    **bonus for reaching a shop with ≳250 gold** (needs a parallel gold estimate).
  - (a) **First 3 nodes of each act are easier** than later fights — ✅ done: `build_combat_stats.py`
    now splits `monster_early` (floor − act_start < 3) from `monster`; the DP uses the cheap early
    number for `row < 3` so it isn't pessimistic about openings (90-run data: p75 5 vs 18).
  - (b) The Act-1 boss wants **nearly full HP**, but selecting hard for that can leave *no*
    elites on the viable paths — needs flexibility, not a hard HP-at-boss constraint.
  - (c) **Branchy paths** (multiple options) are moderately favorable (keep options open); and
    re-assess the route with **actual hp/gold at each branch**, not just once at act start.
- **Deck-power-aware node gating** (owner, 2026-06-15 manual run 2 — a loss). Died f7 to **Phrog
  Parasite** with a 16-card near-starter deck (burst = Bash / Pommel / Infernal Blade only, no AoE)
  and **321 gold unspent** (no shop on the route). Owner: "shouldn't have pathed into the elite with
  so little attack damage." The path scorer must price *can my deck actually clear this node*, not
  just HP — an AoE-needing elite is a death trap for a basic-heavy deck at any HP. Ties to the
  capability estimate (§5-C) and the take-vs-skip deck-power scaling (§8.1d). *Enemy knowledge:*
  Phrog Parasite is **two-phase** — parasite (62 HP) → on death spawns **4 ramping Wrigglers** (gain
  Str each turn) that shuffle **Infection** curses into hand; needs AoE / fast clear, else the hand
  clogs and the swarm out-scales.
- **Shops & events depth.** Note: basic deterministic shop/event policies *already exist*
  (StandardRouter, session 3) — conservative buying, HP-gated choices. The real backlog
  item is *priors-driven depth* (relic/event value from the export above, per-shop
  budgeting, known-event tables), not greenfield work.

### 8.3 Deferred infrastructure (owner, 2026-06-15 — write a detailed plan when revisited)
- **Passive state read (fork).** The mod re-renders the current screen on each `/state` read,
  which fights *human* in-game clicks (live 2026-06-15: the shop re-opened on every recorder
  poll, so `record` had to slow non-combat polling as a partial workaround). Make the state read
  passive (no screen re-render/re-focus) in the fork so manual recording is friction-free and
  fast polling is safe — benefits the agent loop's reads too.
- **Per-card special-case pass.** Optimal play will inevitably require special-casing some
  cards the generic planner can't reason about (owner example: **Anger** — adds a copy of
  itself to the discard, so its value depends on deck/turn context). Deferred task: take a
  systematic pass over the full card list and flag the cards with obvious coding
  exceptions, then encode them (likely as per-card handlers/annotations the planner
  consults). Pairs with the combat-tactics "phase C" work.
- **Seeded custom runs = the boss/elite test harness** (owner reminder, 2026-06-15; this is what
  the manual-run grind is *for*). Custom game mode — **locked until 3 Act-3 wins** — supports
  **seeded** runs that **guarantee the Act-1 boss**. We already have **logged Kin seeds** (the manual
  win `1PKWCTW4M9` had a Kin Act-1 boss; several earlier batch runs died to the Kin — enumerable from
  run logs by Act-1 boss / `killed_by`; the mod exposes `MapInfo.boss` right after Neow). So once
  custom unlocks we **batch-test the bot on the Kin deterministically in the real game**, no
  enemy-behavior model required. This **defers the simulated harness below** (only needed for
  arbitrary fights/decks a seed can't reproduce) and lets us **tune the minion/rest/burst heuristics
  empirically against real outcomes** instead of building the multi-turn forward model first (§5-C) —
  *measure, don't simulate*, wherever a seed can hand us the fight.
- **Combat A/B test framework.** A simulated fight harness to A/B policy changes once
  their impact stops being obvious from live batches: run the bot through fixed difficult
  fights (Ceremonial Beast, specific elites, common packs) with preprogrammed or
  recent-run-sampled decks, simulating enemy behavior from the wikis. Lets us regression-
  test special cases and measure combat tweaks deterministically. Non-trivial (needs an
  enemy-behavior model); owner is prototyping the simulated-fight scripts. **Write a
  detailed implementation plan when we pick this up.** (Fallback to the seeded-runs harness
  above: build this only for what a seed can't reproduce.)

### 8.4 Combat-tactics backlog (from the 2026-06-15 observation run)
Done this session: Rage sequencing · smart in-combat exhaust targeting · false-pause fix
on `card_select` modals · **Fiend Fire hand-scaling** (missed lethals) · **hail-mary
block-awareness** (panic-drank at 13 HP vs 14 when a Defend survives) · **minion-aware
lethal + focus-fire** (leader-kill ends the fight; stop dumping damage on ignorable
minions; Illusion folded in) · **potion taxonomy** (per-potion classifier + categorised
use: hail-mary → Fruit Juice → heal → proactive buffs at elite/boss start → reactive
block + finisher at end of turn; downside held) · **early-damage bias** (Act 1 nudge toward
attacks). The Fiend-Fire / hail-mary / minion / potion / early-damage bullets below are now
implemented + tested. Potion deferrals: full-belt proactive
*deploy* is reward-screen logic (only discard exists); the finisher fires on board-clear
or a real attacker, not yet a minion-leader lethal-via-potion. Remaining:

- **Scaling-damage cards (Fiend Fire) in the planner** (live 2026-06-15). The planner scores
  Fiend Fire by the literal "7" in its text, not `per_card × (hand_size − 1)` for "exhaust
  your hand, deal N per exhausted card" — so it missed a 35-dmg lethal on a 21-HP enemy (and
  passed Fiend Fire across several Fight-5 turns), then panic-drank. Special-case hand-size
  scaling in `_to_planned`/`_apply_card` (same machinery as Rage); confirm other scaling cards
  as they appear.
- **Hail-mary must subtract the block we could play** (live 2026-06-15). At 13 HP vs incoming
  14 it panic-drank, but a single Defend (5 block) survives. The desperation / `_combat_potion`
  gate compares raw incoming vs HP; it should fire on *post-plan* survivability
  (incoming − best achievable block ≥ HP), not raw incoming ≥ HP.
- **Minion-aware combat** (owner tip: "Minion" rides as a *status* on the enemy —
  `enemy.status`; tooltip "Minions abandon combat without their leader"):
  - *Lethal*: `all(e.hp ≤ 0)` should count killing all **non-minion (leader)** enemies as
    lethal — minions flee. Live: Fiend Fire on the leader ends the fight with the minion up.
  - *Focus-fire*: highest-HP targeting pours damage into ignorable minions (Fight 5; recurs in
    Act 2). Deprioritize minions unless one is genuinely threatening.
  - *Illusion minion* (status "Illusion"): revives at the start of its turn after dying, without
    acting — so killing it on **your** turn is wasted (only worth it to deny that turn's action,
    or kill on its turn via poison/doom). Don't target it for damage.
  - *Not a universal rule* (owner, 2026-06-15 manual runs): kill-the-minion vs race-the-leader is a
    **burst-capability judgment**, not one policy. Same A0 Ironclad pilot: **raced the leader** on the
    **Kin** boss (left both ramping Followers alive — leader-kill ends the fight; spending ~58 dmg on a
    58-HP Follower loses the race) but **killed the minion first** on the **Act-3 boss**. The shipped
    `gains_strength / incoming≥6` bias is a stopgap; the real arbiter is the **multi-turn capability
    estimate** (§5-C / §8.3) — "can I close the leader before the ramp out-scales me?". Don't pile on
    more universal minion micro-rules.
- **Multi-phase / reviving bosses break the lethal calc** (verified from in-game status tooltips —
  **Test Subject #C8**, an Act-3 boss, 2026-06-15 manual run). **Adaptable** ("when defeated, revives
  even stronger") → 3 phases ≈ 100 / 200 / 300 HP (~600 effective), each a different punishing power:
  - *Phase 1 — Enrage* "whenever you play a Skill, gains 2 Strength." Strength **and Enrage wipe on
    revive**, so the owner's per-enemy call is: **burst the phase with Skills if you can kill it this
    turn** (the ramp evaporates) **else minimise Skills**. The one-turn planner can't see this.
  - *Phase 2 — Painful Stabs* "shuffle 1 Wound into your discard each time you take **unblocked** attack
    damage" → block fully or pollute the deck.
  - *Phase 3 — Painful Stabs (persists) + Nemesis* "at the end of every other turn, gains Intangible 1"
    (all damage to it → 1) → don't dump burst into an Intangible turn.
  - *Bot implications*: `lethal = all leaders dead` must know about **Adaptable / revive** (killing
    phase 1 does **not** end the fight); each phase wants different play — a canonical case for the
    per-enemy special-case pass (§8.3), with the seeded-runs harness as its deterministic test bed.
- **Ringing status (Ceremonial Beast, low-HP phase)** (owner, seen live 2026-06-16) — caps you at
  playing **ONE card** that turn; the energy-based one-turn planner ignores it and wastes the single
  play. Live: the Beast at **3 HP**, the bot played an unrelated **Block** card first, so its **lethal
  Attack was then unplayable** (Ringing consumed) → ended the turn, missed the kill, ate ~10
  unnecessary damage. Fix: model **Ringing → max 1 card this turn** as a planner cap (generalises to
  any "cards-per-turn" status the energy model misses); under it, plan the single best card — **prefer
  the lethal**, else the highest-value play. Per-enemy special-case (§8.3) / planner constraint.
- **Undergrowth elites are newer + harder; combat-stats / `_GENERIC_ELITE` lag them** (owner,
  2026-06-16). The **Undergrowth** (Act-1 area, unlocked by the Act-3 wins) adds tough elites like
  **Phantasmal Gardeners** — a notoriously hard one (of all elites to randomly lose to, the most
  sensible). Live: a 15-card starter-ish deck was **forced** into one at f8 (`opts=['elite']`, the only
  next node) and died. *Two implications:* (1) the §8.2 elite **gate can't help when the elite is the
  only path** — a routing/avoidance limit, not a gate miss; (2) `combat_stats` HP-loss and the
  `_GENERIC_ELITE` prior predate the Undergrowth, so they **underrate these elites** — rebuild
  combat-stats once enough Undergrowth runs accumulate, and consider an Undergrowth-aware profile.
- **Slithering Strangler — escalating end-of-turn DoT** (owner, 2026-06-16) — applies a debuff that
  deals **X self-damage at end of turn, escalating each turn**. The one-turn planner doesn't model
  incoming end-of-turn self-damage, so it can't price the clock. But **blocking it isn't necessarily
  right — the Strangler wants to die fast anyway** (race it, like a ramp). Another status the planner
  is blind to (cf. Slippery / Ringing); the §5-C capability/race estimate is the real arbiter.
- **Summoner leaders: race the leader, don't chase respawning minions** (first seeded Kin test, seed
  `B04BGZEDRN` — the bot **beat the Kin** at f17 but **died at f22** to this). The **Ovicopter** (Act-2
  normal, 126 HP) has a **Summon** intent that lays **Tough Eggs → Hatchlings** *repeatedly* (verified:
  the eggs/hatchlings carry status **Minion** = "abandon combat without their leader"; the Ovicopter
  also ramps Str and swings 28/33). The dangerous-minion fix flagged the Hatchlings (incoming ≥6 ×3),
  so the bot **chased the respawning minions** instead of racing the 126-HP summoner — a treadmill: it
  cleared wave after wave, never closed the Ovicopter (got it to 38/126), and drowned 77→0. The bot
  already knows "kill the leader → minions flee" (the lethal calc); it just needs to **not chase
  minions a summoner replaces**. Refinement (owner's call, per the no-universal-rule steer): when a
  leader has a Summon ability/intent, treat its minions as low-priority and **race the leader**.
  Contrast the **Kin** (same run, f17, won): its followers are a *fixed* set, so killing them first
  removes the ramp for good. **Fixed-add vs summoned-add is the distinction the minion logic misses.**
  - *Fixed + validated 2026-06-16:* `_ignorable_minion` is now summoner-aware (any enemy with a
    Summon intent → its minions are ignorable; race the leader). Same-seed A/B: the bot **raced the
    Ovicopter and survived** (killed it R7, minions fled) where before it drowned — but at only 7 HP
    (Burning Blood → 13), then died f23 (The Obscura) entering that low with no rest between.
    Targeting is solved here; the residual is **deck-power / surviving a costly race into the next
    node** — the capability estimate, not minion micro.
- **Vantom (Act-1 boss, ~173 HP) — Slippery negates chip damage** (recurring batch wall 2026-06-16:
  killed 3/5 of a batch + 1 earlier). Verified status **Slippery**: "the next time Vantom loses HP, it
  only loses 1 HP instead" — drops the *first* HP-loss each turn to 1, so multi-hit / small attacks are
  wasted; it also ramps Strength and swings 27–29. The one-turn planner doesn't model Slippery, so it
  over-values its damage, can't close the race, and bleeds out (live: entered 38/80, stuck at 12, died).
  Special-case candidate (§8.3): model Slippery (lead with a throwaway hit, then land big single hits)
  alongside HP-at-boss work. Like the Kin, it's a deck-power + per-enemy-mechanic wall.
- **Run-2 draft notes** (owner; reference): early-damage picks (Infernal Blade D1; Hemokinesis
  over Shrug It Off) → covered by the early-damage bias. The **Vicious** / Vulnerable-applier and
  *draft-affects-draft* observations fold into the deferred deck-aware drafting below. Pommel
  Strike / Fiend Fire picks were right.
- **Potion taxonomy** (owner; StS2 effects verified). A per-potion handler keyed by
  id/name. Categories:
  - *Reactive, end-of-turn* (drink after the plan plays its cards, vs known remaining
    incoming): **Block Potion** (12 block) when remaining incoming ≳ 10–12; **Fire
    Potion** (20 dmg) / **Potion-Shaped Rock** (15 dmg) / **Explosive Ampoule** (10 AoE)
    when it kills + prevents meaningful damage. (Needs a post-plan potion hook — _combat
    currently checks potions before planning.)
  - *Proactive at boss/elite start* (the bot struggles, so just deploy): long-term buffs
    **Strength/Dexterity/Fysh Oil**, disguised long-term **Power Potion / Blessing of the
    Forge**, debuffs **Vulnerable/Weak/Potion of Binding/Shackling**.
  - *Immediate*: **Blood Potion** (Ironclad heal, also usable out of combat) when <80% HP;
    **Fruit Juice** (+5 max HP) on sight.
  - *Downside* (**Foul** — 12 to everyone incl. self; **Glowwater** — exhaust hand draw 10):
    avoid; only via full-belt deploy or hail-mary.
  - Full belt + incoming potion reward → deploy a low-value potion, esp. vs boss/elite.
- **Scaling powers — play early, not "safe"** (owner; Demon Form is the prototype). A class of
  powers with big long-term payoff that hurt to play *this* turn (Demon Form "at start of turn
  gain 2 Strength"; the Kin-fight power the owner flagged Turn 1–2, name TBD). They pay off more
  the MORE enemy HP remains and the LOWER the current incoming, so they want to go down Turn 1–2
  — but `w_power_played` is a flat reward, so under any incoming pressure the bot defers them to
  "play safe", by which point the fight's nearly over and the payoff is gone. Heuristic: play a
  scaling power when this-turn damage taken would be ≤ X, where X rises with total enemy HP
  remaining and for elite/boss (afford the tempo loss in a long fight); else hold.
- **Play 0-cost Powers immediately** (owner, 2026-06-16, seen live: a 0-cost power played late in a
  turn) — distinct from the scaling-power tempo call above: a **free** Power banks a permanent buff at
  **no opportunity cost**, so it should go the **moment it's playable** (including straight out of a
  potion), ahead of the rest of the turn — only a few edge cases aside. The planner scores end-states
  and is **order-indifferent within a turn**, so it sequences free powers arbitrarily; force 0-cost
  powers to the front. Matters when the power buffs this turn's later plays, or under a cards-per-turn
  cap (Ringing). Likely a small, near-term planner fix.
- **Deck-aware drafting** (owner; deferred to a later project — "adjust drafting based on the
  current deck"). Two pieces, both needing deck state at draft time: (a) **conditional-card
  list** — **Rupture** / cards that do nothing without enablers (Bloodletting/Decay), gated on
  "enabler present in deck?"; (b) **Vulnerable-applier priority** once a payoff (e.g. **Vicious**)
  is already drafted, and *draft-affects-draft* generally. Owner will review the conditional-card
  list before it ships — **pass uncertain cases by owner.**
- **Early-draft damage bias** — ✅ done (`early_damage_bonus`): any Act-1 card that deals damage
  gets a tunable nudge (Hemokinesis over Shrug It Off); priors still do the heavy lifting.
- **Transform event: transform a Strike, not a curse** (events not yet policy-driven;
  noted for the eventual event work — transforming a curse is far worse value).
- **Byrdonis Egg event** (owner, 2026-06-16, seen live): Choose-1 — (a) gain Max HP, or (b) gain a
  **Byrdonis Egg**, a pseudo-curse (unplayable card). The egg can later be *removed* (pointless — you
  could have just taken the Max HP) or, uniquely, **hatched at a rest site** (a 3rd campfire option)
  into a moderately strong Act-1 attack, replacing the curse. **The bot currently takes the egg but
  never hatches it → strictly worse than the Max HP.** Right logic: at *event time* only take the egg
  if it'll reach the next rest site positioned to **hatch instead of rest** — i.e. arriving near max
  HP so the forgone heal is cheap; else take the Max HP. Then at the campfire, hatch when holding the
  egg and near-full. The "arrive near max HP at the next rest" check can reuse the §8.2 map
  HP-projection (it already walks the route projecting HP). Precision play; deferred. Minor caveat for
  the current batches: the bot eats this value when the egg event fires.
