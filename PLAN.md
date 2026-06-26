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
| **Mod build provenance — build the FORK, not upstream** | infra/done | 2026-06-23: rebuilding the v0.107.1 mod from upstream `Gennadiyev/STS2MCP` silently dropped the fork's `player.deck` (+ `set_time_scale`/`set_ascension`/`actions_disabled`) → capability drafting **and** the elite gate no-op'd for a whole batch (deck = `None`, so the b3b7593yb results don't test §5-C). Fixed: build from `cicero225/STS2MCP` + re-apply `patches/STS2MCP-newbuild-fix.patch`; CLAUDE.md + patches/README corrected. **Re-batch bxtd5uum8 (2026-06-24) confirmed the fix: act-reach 1.0→1.8 (max 3 — two Act-3 runs, one reaching the Aeonglass boss), relics 4.0→7.0, elites 0.2→0.6; still 0/5 wins but the wall moved from Act-1 boss to Act 2/3.** |
| **Card descriptions render ENERGY as icon tokens, not text** | infra/parsing | 2026-06-26: the game writes gained energy as `[<char>_energy_icon.png]` tokens, not "N Energy" (Luminesce = "Retain. Gain `[ironclad_energy_icon.png][ironclad_energy_icon.png]`. Exhaust."). The text-only `_ENERGY` regex parsed these to 0 → **Luminesce / Bloodletting / Offering all read as 0-value and went unplayed** (owner-caught). Fixed: `textparse` now counts per-char energy icons after "Gain". Trace scope-check: **only energy** is iconized (damage/block/draw are plain text; `star_icon` is a separate resource). **Watch:** if a future card iconizes another value (or stars become relevant), the same text-regex blind spot applies — grep traces for `\[[a-z_]+\.png\]` when a card mysteriously reads as 0-value. |
| **Batch resilience — one unclean run kills the whole batch; no abandon-to-menu recovery** | infra | 2026-06-25: `play` halts the batch on any non-`completed` run ([cli.py:160](sts2bot/cli.py)). A run that *stalls* (60-tick timeout) leaves the game mid-run, so the next run can't start fresh either — the batch is stuck until a manual kill+restart. Root trigger seen: a **rare treasure-claim glitch** — `ClaimTreasureRelic` occasionally doesn't register (relic stays listed on an *open* chest; hit once on a Bellows chest, Act 2, 4x), and the very next treasures claimed fine, so it's isolated/transient, **not** speed-systematic. Lesson learned the hard way: the bot must **never proceed past an unclaimed chest** — doing so leaves the treasure node unresolved, freezes map nav, and black-screen-**softlocks** the game (that "recovery" was reverted; original keeps claiming → clean stall-abort). Proper fix: orchestrator **abandons the run to the main menu on a stall-abort** so the batch self-recovers; optionally a watchdog re-claim/dwell on transitional treasure `message`. Bigger change — deferred. **Update (2026-06-25, batch bdbfpnckb run 4): trigger pinpointed = a `War Paint` treasure on a `?` (Unknown) map node.** Trace: arrive at the `?`-node treasure (relics already empty — War Paint auto-applies its 2 random Skill upgrades), bot `proceed`s, next state is the map → **frozen** (40+ identical `choose_map_node`, state never advances). Live capture: `current_position` stuck on the Unknown node (row 13) with two valid `next_options` (Monster/Elite at row 14) it won't take, and **3 cards now `is_upgraded`** (War Paint applied). No API-visible pending screen — the game is internally stuck after the auto-applied upgrade, so the bot's valid `choose_map_node` no-ops. **Deterministic repro seed `ZWSK88UNQN`** (Ironclad A0, config 379cb9c6744b; owner read it off the in-game seed display). Likely a *mod/game* bug (`?`-node + auto-pickup relic not finalizing the node); seeded repro + decompile of the `?`-node→treasure flow is the path. **2nd instance (2026-06-26, batch bg3h3mw5w run 20, Act 2 floor 27): an enchant card-select hang** — `NDeckEnchantSelectScreen` "Choose 3 cards to Enchant": the bot selects 3 → `confirm_selection` (can_confirm=true) → the screen **resets to 0 instead of closing**, looping select→confirm to the abort. The cards expose no `selected` field, so the select/confirm isn't resolving — the enchant screen needs its resolution understood (interactive 1x test or mod look). Confirms the meta-point: **rare per-screen hangs will keep killing batches one at a time** (treasure, now enchant, more to come) — the durable fix is the abandon-to-menu batch-resilience above, higher-leverage than whack-a-mole per screen. |

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

- **Draft calibration: Spirebird Elo over-values long-game scaling for the bot's *short* games** (owner
  lookthrough 2026-06-25). The bot drafted **Drum of Battle** (draw 2; exhaust → +2 energy) on a
  starter-heavy deck with no energy-gen / fish target and only one random-Exhaust (unupgraded True Grit).
  Spirebird rates it high because draw-2 compounds *if the game runs long* — but the bot's runs end at
  the Act-1 boss, so the payoff never lands. Plausible **plateau driver**: the Elo prior pulls toward
  late-game scaling while the §5-C capability term (immediate boss-closing power) is outweighed. Test in
  the deck-power diagnostic; consider tilting capability-vs-Elo by run depth (favor immediate power early).
- **Context-dependent card value the Elo prior may miss: Expect a Fight** (owner lookthrough 2026-06-25).
  Expect a Fight (2e, gain energy per Attack in hand, no further energy this turn) is **deck-dependent**:
  weak here (deck already has Luminesce + Bloodletting for energy, and few attacks → likely nets +1 or
  less), strong only with heavy draw / many attacks. The §5-C capability term *should* downrate it (the
  deck can't convert the energy), but the Elo prior may over-rate it — same theme as the note above.
- **✅ DIAGNOSTIC RESULT — hypothesis confirmed *and sharpened: it's a tempo mismatch, not thinning***
  ([scripts/deck_power_diagnostic.py](scripts/deck_power_diagnostic.py), config `a45509a7b572`, 91
  Ironclad runs, 2026-06-25). The bot reaches the **Act-1 boss in 63/91** runs but **wins only 30%
  (19/63)**; losers die a **median 33% of boss HP short** (mean 35%; only 12/44 are ≥80%-damage
  near-misses — most losses are a real gap, not a sliver). **Key negative result:** boss-entry deck
  *size* and *%basics* are **identical** between winners and losers (17.2 / 43% vs 16.4 / 46%), so the
  gap is **not** under-thinning. The differentiator is card **role/tempo** (avg copies/deck, won−lost):
  *winners over-index on burst + Vulnerable enablers* — Conflagration (+0.24), Evil Eye, Neow's Fury,
  Stampede, Ashen Strike, Molten Fist+, **Bash / Dominate / Tremble** (the Vulnerable package the owner
  keeps flagging); *losers over-index on slow block/scaling/utility engines* — Second Wind, Burning
  Pact, Colossus, Feel No Pain, Spoils Map. The top winner signal is **Shrug It Off (+0.47)** — *cheap
  efficient* block+draw, while the loser-side block (Colossus, Feel No Pain, Second Wind) is *slow/
  setup-heavy* — so the real axis is **tempo/efficiency per energy in a short fight**, not block-vs-
  damage. **Lever:** the draft term should reward tempo-efficient burst + Vulnerable enablers and
  downweight slow scaling/engine/big-block cards *early* (mirror onto the §5-C capability tilt above).
- **✅ REGRESSION-vs-VARIANCE — no regression; "stuck at Act 1" is recency/variance** (index dig
  2026-06-25). Across Ironclad configs, the **current** config `a45509a7b572` (n=91 — by far the
  largest sample) is the **best**-performing: 76% reach the Act-1 boss, 22% beat it, 4% reach Act 3.
  Older configs (n=5 each) were no better (40–60% reach, 0–20% beat). By **mod build**, the newer
  corrected build **v0.107.1 reaches the Act-1 boss 85%** vs old v0.103.3's 60% — the 2026-06-23
  fork/deck fix *helped*. **Wins remain 0 on every config.** So the owner's "used to reach Act 2-3,
  now stuck Act 1" is consistent with the current ~22% Act-2 / 4% Act-3 base rate seen against a
  memorable earlier good streak — variance, not a capability regression. The real, stable barrier is
  the 0-win plateau + the tempo gap above, not a lost capability.
- **⚠ Cautions on the tempo lever (owner 2026-06-25) — shape the design, don't naively penalize:**
  **(1) Depth-aware, not global.** Over-suppressing slow block/scaling starves the *long* Act-2/3 boss
  fights that genuinely need it; burst/tempo priority is a known **Act-1** optimization, not a global
  rule. **(2) The won−lost differential is confounded by the bot's own piloting.** Power-scaling cards
  (**Juggernaut, Feel No Pain**) look bad in the data partly because the bot rarely plays them early
  (powers-under-played, §8.4) — they function as effective *curses* much of the time, so of course they
  correlate with losing. Baking that into the draft prior is **circular** (bot mis-pilots a power → data
  says "powers bad" → bot stops drafting them → the real fix, playing them, never gets exercised). So:
  prefer **positive** signals (burst, **Vulnerable** enablers — immediate-value, *un*-confounded) over
  **penalizing** scaling/powers. Vulnerable is the cleanest, strongest lever (owner: arguably the best
  Ironclad synergy) and the §5-C `vuln_mult` already knows how to cash it in.
- **✅ FIRST CUT shipped — Vulnerable *uptime* model (replaces the binary flag)** (2026-06-25).
  `deck_output.vuln_mult` was binary (any Vulnerable source → ×1.3, 2nd source worth nothing); now it
  scales with **uptime** = `min(1, sources × cards_drawn / deck_size)` against the same 1.3 ceiling. So
  a lone Bash in a 16-card deck earns only ~×1.09 (intermittent), and a 2nd enabler lifts it to ~×1.18 —
  exactly the owner's Dominate insight ("a single Bash is a weak source; even one more helps a lot").
  This reaches drafting through the deck-aware §5-C term (`_capability_deltas` → `deck_output`), so
  Vulnerable enablers are now priced by accurate forward-model uptime instead of leaning on the Elo
  prior. **Pure forward-model improvement — no scaling/power penalty** (honors the confound caution).
  *Remaining:* the broader burst/tempo-vs-slow-scaling tilt is **deferred until the powers-under-played
  fix (§8.4) de-confounds the data** — penalizing powers now would just encode the bot's own misplay.
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

- **Draft × route should be joint near a boss; card value is boss-dependent** (owner lookthrough
  2026-06-25). Thunderclap-vs-Bloodletting draft, 3 rooms from Soul Fysh with a shop branch: owner's
  optimal is draft **Bloodletting** *and* **divert to the shop** (save HP + buy boss-damage) — the pick
  and the route reinforce each other, but the bot decides them separately. Context nuance: Bloodletting's
  +2 energy is unusually good *vs Soul Fysh* — the energy discards **Beckons** even when the deck can't
  otherwise spend it. Beyond current scope (joint draft+route+boss-proximity); a seed for integrated
  routing. (Vacuum pick: still Bloodletting, unless 2 rooms from a burst boss + desperate for Thunderclap.)
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

- **Powers under-played — the one-turn planner defers permanent buffs** (owner 2026-06-25; viewer-
  jarring + real upside). The planner scores end states by *this turn's* damage/block/lethal, so a
  **Power** (0 immediate damage/block) gets only the flat `w_power_played = 8.0` (per-turn powers like
  Demon Form even have their immediate effects zeroed, combat.py:124), which routinely loses to spending
  the same energy on an attack — so it's deferred until "spare" energy that rarely comes early. The
  compounding payoff (Juggernaut's 6 dmg per *future* Block; Demon Form's +Str *every* turn) is invisible
  to a one-turn horizon. **Scoped plan (owner-agreed 2026-06-25):**
  - **Tier 1 (build now):** horizon-aware power value = per-turn benefit × **remaining fight turns**, so
    early powers dominate and late ones don't. Remaining turns from a *local* `enemy_total_HP /
    base_per-turn-damage` estimate (owner: the cheaper turn-number proxy would just need re-fixing — do
    the HP/damage one). Tier 1 reuses `w_power_played` as the generic per-turn value; calibrate the
    multiplier against a live batch, don't guess.
  - **Tier 2:** per-power knowledge table (effect + ASAP-vs-gated timing) with a per-power **defer/gated
    flag** the generic can't express. The category is non-empty across characters (owner: **Neurosurge**
    for Necrobinder), so build the hook even though Ironclad is mostly ASAP.
  - **Owner's timing rules (Ironclad):** assuming a power was drafted where it has value (Feel No Pain
    into a real exhaust deck), almost everything goes down **ASAP**; defer only when *forced*. Forced
    cases mostly fall out of existing terms — **incoming damage** (survival via `hp_loss`/`w_kill`),
    **Demon Form 3e** unplayable in short fights (energy term). The one genuinely new guard: **self-
    damage powers (Inferno, Crimson Mantle)** are strong but must **not** be front-loaded at low HP —
    their per-turn HP cost hits at *next*-turn upkeep, which the one-turn tally misses (ties to the
    Inferno death-tally note below). **Corruption** (rare-event power) needs deferring in some long
    fights — a Tier-2 corner case. `PlannedCard.is_power` exists but is too weak as a flat flag.
    *Validation:* re-run a batch; expect turns-to-first-power-play ↓, Act-1-boss win ↑, and the
    diagnostic's power-card loss-correlation to shrink (de-confounds the deferred §8.1 tempo tilt).
  - **✅ Tier 1 SHIPPED** (config `379cb9c6744b`): `_score` now multiplies `w_power_played` by
    `power_horizon = min(cap 6, enemy_HP / this-turn base damage)` (powers excluded from the base read,
    no circularity), so a Power goes down ASAP early and is ignored when near-lethal. Self-damage
    powers (Inferno) front-load only above `power_self_damage_hp_safe = 0.5` HP, else fall back to the
    flat value; also zeroed per-turn powers' "lose N HP" *this* turn (a next-turn upkeep cost the
    parser misread as immediate). Knobs in `config/policy.toml`. **Pending:** validate + tune the cap
    against a live batch (the calibration step — the multiplier could over/undershoot).
  - **✅ Tier 1 VALIDATED — mechanism (partial outcome)** (batch bg3h3mw5w, 22 runs, 2026-06-26).
    Power **play-rate 48%→83%** (97/117 fights with a playable Power now play one; baseline 48%),
    first-play round 2.7→2.2 — the horizon fix does exactly what it should: the bot now plays its
    Powers. **Outcome inconclusive at n=20** (batch stopped early at a new enchant card-select hang,
    §7): Act-1-boss win 15% (3/20) vs baseline 30% (19/63) — within noise at this sample; losers still
    ~30% boss-HP short. **Encouraging:** the runs that got going went *deep* — floors 33/39/**48**
    (deep Act 3; baseline reached Act 3 only ~4%), consistent with Powers paying off in long Act-2/3
    fights (§8.1 thesis). Need a clean full 40+ batch for a definitive win-rate read (blocked on §7).
- **~~Energy-gain cards unmodeled (Production)~~ — ✅ ACTUALLY MODELED; note was wrong** (re-verified
  2026-06-26). Energy gain *is* wired end-to-end and has been since the original planner (commit
  5c9c59d, *before* the lookthrough): the parser's `_ENERGY` regex sets `fx.energy_gain` (matches
  "Gain 2 Energy") and `_apply_card` adds it to `SimState.energy` (combat.py:327). Direct planner test
  confirms it plays **Production → Defend×2 → Strike×3** (exactly the "optimal" line) — locked by
  `test_planner_plays_zero_cost_energy_card_to_enable_more`. So the Fight-1 *Production-unplayed* the
  owner saw was **not** an energy gap; likely causes to re-check if it recurs: (a) it was a *lethal*
  turn (bot correctly skips Production/Defends to take the kill — and note Defend doesn't block
  **thorns** anyway, which is unblockable self-damage from attacking, so the "soak thorns" framing was
  off), or (b) the live colorless card arrived without a parseable `description`. Not a planner-logic
  fix.
- **Free 0-cost card-draw should be played FIRST, then re-assess** (owner 2026-06-25). The DFS values
  draws by a flat `w_draw` proxy and never sees the drawn cards (random/unknown at plan time) — it plans
  the current hand as one set. The orchestrator re-plans after *every* card (one card per decision,
  [loop.py:240](sts2bot/orchestrator/loop.py)), so the bot *does* draw-then-reassess across cycles — but
  only if the free draw is played first; today the first-card choice uses the proxy, so it can commit a
  non-draw card *before* drawing and throw away the information. Fix: a **free-draw-first** heuristic —
  if a 0-energy card-draw card is playable, play it before other cards, gated on **no card/skill-count-
  penalty enemy**. Sequencing-only; pairs with the "play 0-cost energy-positive cards first" note above
  (Production) — both are *play free card-economy first*.
  **⏸ DEFERRED until enemies are modeled (owner 2026-06-26).** The penalty-gate list is long and the
  naive "play first" upside is real-but-untested, so not worth it until the gating enemies exist. The
  card/skill-count penalties to detect: **(1) Thorns** (if the free draw is an Attack, e.g. Flash of
  Steel); **(2) Living Fog** (Act-1 Underdocks normal) — applies **Smoggy** (1 Skill/turn), which caps
  draw *skills*; **(3) Hunter-Killer** (Act 2) — **Tender 1**: each card played lowers Str+Dex 1 for the
  turn; **(4) attacking a *sleeping* Beetle / Lagavulin Matriarch** — breaks plating + **wakes** it, so
  a free draw-that's-an-Attack-generator has a hidden cost; **(5) Aeonglass** — generates statuses per
  card played. So the gate isn't just "skip on enemy X" — it's whether the *free draw is/produces an
  Attack* (1,4) vs a Skill (2) vs any card (3,5). Revisit once §5-C enemy modeling is broad.
- **Retain cards — hold when not needed** (owner lookthrough 2026-06-25). True Grit gained **Retain**
  (stays in hand at end of turn). The one-turn planner doesn't manage it: if you can full-block
  *without* the retain card, holding it is effectively deck-thinning + optionality next turn. Fix: a
  small weight to prefer NOT playing a Retain card when it isn't needed for this turn's block/lethal.
  Bounded planner tweak; Retain is rare on Ironclad, so narrow scope.
- **Near-lethal: block-and-wait when next-turn lethal is likely** (owner lookthrough 2026-06-25; ~5 HP
  suboptimality observed). The bot sacrificed HP to chip the enemy to 3 this turn; better to **block +
  kill next turn** *if* it's very likely to draw ≥9 damage (e.g. 2× Strike) AND the enemy won't escape
  (no big block/heal intent). Needs multi-turn reasoning the one-turn planner lacks: (1) draw-pile
  lookahead for next-turn damage (expert humans track this constantly), (2) the enemy's next intent
  (block/heal that punishes waiting). §5-C / multi-turn-forward-model territory, not a simple fix.
- **Inferno overkill — its guaranteed next-turn AoE is the *easy* block-and-wait case** (owner
  lookthrough 2026-06-25; theoretical, didn't bite here). With **Inferno** up (6/8 AoE at the start of
  your turn), if that AoE will kill the enemy *next* turn and you already have block to survive this
  turn, don't spend resources finishing it now — Inferno does it free. Unlike the case above, the
  next-turn damage is *guaranteed* (no draw-pile lookahead), so it's the easier sub-case — still gated
  on the enemy not escaping (block/heal/summon). Same multi-turn-lethal model.
- **Pen Nib (relic) unmodeled — missed lethal** (owner lookthrough 2026-06-25). Pen Nib: **every 10th
  attack deals double damage** (it carries a counter). With a Vulnerable front minion the bot had lethal
  via the doubled 10th attack, but the planner (blind to Pen Nib) under-counted it → attacked once then
  blocked with True Grit, missing the kill + eating the front minion's damage. Fix: read the Pen Nib
  counter from player relics; in the DFS, double the attack that lands as the 10th. Per-relic combat
  modeling, same class as Strength / scaling-card effects. **Owner rules (2026-06-26):** (a) the counter
  **persists between fights** — read the *live* value, never assume a per-fight reset; best is whatever
  the API exposes for the relic counter (in-game the number is shown on the relic — on **9** the next
  attack doubles). (b) **Gotcha to verify in the API:** while on 9 the game previews **all** attack cards
  at doubled damage (like Vulnerable's +50% preview), but only the **first** attack actually doubles —
  so if the parsed card damage reflects that preview, the planner would over-count; apply the double to
  exactly **one** attack (the first played while on 9), and check whether `card.description`/damage
  already carries the doubling.
- **Artifact unmodeled — planner wastes debuffs into it** (owner lookthrough 2026-06-25). Enemies had
  **Artifact 2** (negates the next 2 debuffs/status effects). The bot played **Dominate** (apply 1
  Vulnerable, +1 Str per Vulnerable layer) → Artifact ate the Vulnerable → zero effect for 1 energy
  (pure waste; the enemies were dying well before the Artifacts would clear). The planner applies
  Vulnerable/Weak without checking Artifact. Fix: model Artifact on the enemy — process each card's
  debuffs **in card-text order**, decrementing Artifact by 1 **per unique status type** while >0 (so
  debuff/Vulnerable cards into Artifact score ~0 unless intentionally stripping it). **Owner rules
  (2026-06-26):** (a) decrement is **per unique status, not per stack** — magnitude-independent, so
  **Bash**'s 2(3) Vulnerable strips only **1** Artifact; (b) a multi-status card strips one **per
  status** — **Uppercut** (Weak *then* Vulnerable) strips **2**, and at **Artifact 1** the Weak is eaten
  (Artifact→0) and the Vulnerable then **lands**; (c) order follows the card text. General mechanic
  (also **Aeonglass**); detect_mechanics + `_apply_card`.
- **Healing on cards (Not Yet) parsed but NOT modeled in combat** (owner 2026-06-26, live question). The
  parser sets `fx.heal` (Not Yet = 2e, Heal 10 HP) and *event* scoring uses it, but the combat planner's
  `_apply_card`/`_score` ignore `fx.heal` — so an in-combat heal reads as a 0-value energy sink and the
  planner won't play it even when hurt with spare energy. Fix: track capped healing in `_apply_card`
  (`min(heal, max_hp − hp)`, no overheal) and credit it in `_score` scaled by the same HP-scarcity curve
  as `hp_loss` (worth more when low, ~nothing at full HP — symmetric with the Offering logic). Small.
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
- **Waterfall Giant (boss) — Steam Eruption delayed explosion unmodeled; Hail-Mary no-fired on a blatant
  lethal** (owner 2026-06-26, confirms a long suspicion). **Mechanic:** the boss stacks **Steam Eruption**
  over the fight; when its HP first hits 0 there's a **one-turn delay**, then it explodes for the *full*
  Steam-Eruption stack all at once (must be blocked) *before* it dies. **(a)** The bot doesn't model the
  delayed explosion → it "kills" the boss and then dies to the eruption (often with genuinely too little
  block, so many of these deaths weren't misplays). **(b)** But this batch it **failed to Hail-Mary a
  clear lethal**: full potion belt (≥1 damage-saving potion), low HP, **~69 incoming** from the eruption
  — should have fired trivially, didn't. **Post-batch check (from the trace):** does the API surface the
  ~69 as `incoming`/an intent? If **yes** → the Hail-Mary/desperation gate has a bug (didn't read it);
  if **no** → the bot is blind to the eruption and needs **Steam-Eruption modeling** (a scheduled
  post-lethal hit the §5-C / hp_loss tally reserves block for, like a delayed Beckon). Ties to the
  hail-mary note above and the death-tally completeness items.
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
- **Ringing status (Ceremonial Beast, low-HP phase)** (owner, seen live 2026-06-16; status
  `RINGING_POWER` "You can only play 1 card this turn.") — caps you at **ONE card** that turn. Live:
  the Beast low, the bot played an unrelated **Block** first, so its **Attack was then unplayable**
  (Ringing consumed) → missed the kill, ate ~10 unnecessary damage. **✅ cap done 2026-06-17:**
  `plan_combat_turn` detects "only play N card" on the player and caps the DFS to N plays, so it never
  *starts* a 2-card plan it can't finish; it commits to the single best card by the turn score.
  **Remaining nuance (owner 2026-06-17 — attack-beats-block is NOT universal; deferred to §5-C):**
  the proper logic is (1) if a one-card **lethal**, play it; (2) if one-card **block is needed to
  survive**, block; (3) else weigh one-card damage vs block **factoring next turn** — the Beast
  *alternates* Ringing then attacks while Ringing is up, so a **clean attack turn is guaranteed
  next**, making "block now, hit then" often best; (3a) full optimality reads the **draw pile**.
  Steps 1–2 fall out of the turn score today; step 3 is the multi-turn capability layer. Per-enemy
  special-case (§8.3) / planner constraint.
- **Undergrowth elites are newer + harder; combat-stats / `_GENERIC_ELITE` lag them** (owner,
  2026-06-16). The **Undergrowth** (Act-1 area, unlocked by the Act-3 wins) adds tough elites like
  **Phantasmal Gardeners** — a notoriously hard one (of all elites to randomly lose to, the most
  sensible). Live: a 15-card starter-ish deck was **forced** into one at f8 (`opts=['elite']`, the only
  next node) and died. *Two implications:* (1) the §8.2 elite **gate can't help when the elite is the
  only path** — a routing/avoidance limit, not a gate miss; (2) `combat_stats` HP-loss and the
  `_GENERIC_ELITE` prior predate the Undergrowth, so they **underrate these elites** — rebuild
  combat-stats once enough Undergrowth runs accumulate, and consider an Undergrowth-aware profile.
- **Data currency after the v0.107.1 game update** (owner, 2026-06-23 — game auto-updated v0.103.3 →
  v0.107.1 over the trip, breaking + then rebuilding the mod, see [patches/](patches/)). Our harvested
  data predates the new build, so refresh when convenient: (a) **re-harvest `bestiary.json` /
  `card_effects.json`** from a few new-build runs (text-based mechanics like Slippery/Plating should
  hold; HP/numbers may shift); (b) **Act-3 boss Doormaker → replaced by Aeonglass** with new mechanics
  — document Aeonglass when ENEMY_PASS Phase 2 (Act-3 bosses) starts; our bestiary never had Doormaker
  (bot's never reached Act 3); (c) **Spirebird card priors** (`priors_cards.json`) — the live build has
  now caught up to the recent betas, so a 4-version jump may have rebalanced cards, biasing stale Elos
  in the drafting score; fold a re-export into the next Spirebird pull (marginal, owner-assisted, not
  blocking — the capability-aware drafting term partly compensates).
- **Slithering Strangler — escalating end-of-turn DoT** (owner, 2026-06-16) — applies a debuff that
  deals **X self-damage at end of turn, escalating each turn**. The one-turn planner doesn't model
  incoming end-of-turn self-damage, so it can't price the clock. But **blocking it isn't necessarily
  right — the Strangler wants to die fast anyway** (race it, like a ramp). Another status the planner
  is blind to (cf. Slippery / Ringing); the §5-C capability/race estimate is the real arbiter.
- **Soul Fysh — block-bypassing status card** (owner, 2026-06-16; a recurring run-killer, normal +
  boss) — deposits a unique **damaging status as a card in your hand** that **bypasses Block/armor**;
  **playing the card discards it but costs 1 energy** to clear. The planner neither prices the
  unblockable damage it inflicts nor knows that spending the energy to play the junk card removes it.
  Per-enemy handling (§8.3) + a status the §5-C estimate should count as unavoidable chip.
  *✅ Partial (2ac2d90): combat `hp_loss` now counts unplayed Beckon as unblockable HP so the hail-mary
  fires; still TODO — make the planner* value *spending the energy to play it.*
  *✅ Extended (owner lookthrough 2026-06-25): generalized the end-of-turn-in-hand tally to a second
  flavor — **Toxic** ("take N damage" if held), which the owner flagged was being missed. Modeled*
  **differently** *per the owner's correction: Beckon "lose N HP" is unblockable (straight to hp_loss);
  Toxic "take N damage" is **blockable** (joins the incoming pool so leftover block soaks it). Keyword-
  gated on "in your hand" + "end of" so card word-order/phrasing don't matter. Same energy-to-clear TODO
  (with Luminesce's +2 energy unplayed, the bot couldn't clear two Toxics to save 10 — the energy-gap).*
- **Death-tally completeness — self-HP-loss powers (Inferno) the lethal projection misses** (owner
  2026-06-25, theoretical). `hp_loss` now counts thorns + self-HP-cost cards + unplayed Beckon, but
  NOT start-of-turn self-damage **powers**: **Inferno** (lose 1 HP/turn — ×copies — at turn start
  while dealing 6 AoE; the bot drafts it often and does well with it) sets up a *next*-turn-start
  drain this turn's tally can't see, so at ~1 HP with Inferno up the bot could read "survive" then die
  on upkeep. (NOT to be confused with the Knowledge Demon's Disintegration, which per owner memory is
  *end*-of-turn and **blockable** — a different case the tally also misses, but one block covers.)
  Marginal (never seen live), but for completeness the projection should add active "lose N HP at
  start of turn" powers.
- **Knowledge Demon (Act-2 boss)** — complex mechanics, **not yet documented** (the f33 run was too
  injured to matter, but the owner notes it would have "put up a better show" understanding its
  options). Document its powers/intents when next seen; per-enemy special-case (§8.3).
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
  alongside HP-at-boss work. Like the Kin, it's a deck-power + per-enemy-mechanic wall. *✅ Slippery
  now modeled (Phase 1, 2026-06-17): the planner leads with a throwaway hit then lands the big one;
  the deeper race / HP-at-boss work remains.*
- **Phantasmal Gardeners (Act-1 elite) — Skittish swarm, and the elite-gate-mismodel it exposes**
  (owner live + investigation 2026-06-25). **Skittish**: *"the first time each Gardener is hit each
  turn, it gains 6 Block."* The first hit lands, then +6 Block soaks every follow-up that turn — so it
  **guts chip / multi-hit decks** (the bot's starter-heavy ones: only one hit per gardener per turn
  really counts) and rewards **one big hit per gardener**. The exact mirror of Slippery, and just as
  modelable: `detect_mechanics` → a reactive first-hit +block; `_apply_attack` adds it after the first
  hit on that enemy. *Live-confirmed: bq8fskrg9 R2 nearly died from full HP to the swarm — saved only
  by a Fairy in a Bottle auto-revive, not by play.*
  - **Wider problem**: the §5-C elite **gate** prices every Act-1 elite as a *generic* 90 HP / 17 dps
    with no mechanic, but real ones run 21→140 HP with Skittish / Hardened Shell / Shriek — so it
    chases un-winnable fights. Kill-tally: **Bygone Effigy (127 HP) #1 (4×)**, then Phrog Parasite /
    Phantasmal Gardeners (2×), Terror Eel (140 HP). Fixes: (1) model Skittish in the planner; (2) a
    tougher / zone-aware gate — zone (Underdocks vs Overgrowth, different elite pools) isn't in state,
    so infer from the boss. Pool-depletion (no elite repeats until all 3 in the act are seen → narrow
    the estimate after one is met) = future optimization.
- **Lagavulin Matriarch (Act-1 boss, 222 HP) — Asleep + Plating + Soul Siphon** (owner 2026-06-23,
  precise mechanics + online-verified; ≥2 deaths in the deck-blind v0.107.1 batch). Three layers:
  - **Asleep 3**: −1/turn, wakes at 0 *and acts that turn*; **any unblocked HP loss wakes it early**
    on its upcoming turn (or the current enemy turn if hit mid-turn, e.g. poison). **Wake removes ALL
    Plating immediately** — so the wall only exists while asleep.
  - **Plating** (decaying stack): +12 Block at end of your turn, −1/turn. While asleep it isn't
    swinging, so chip ≈ wasted into block — but chipping also *wakes it early*.
  - **Soul Siphon** (move name verified online): post-wake cycle Slash → Disembowel → Block/Attack →
    Soul Siphon (~every 4th turn). Each cast **permanently −2 Str AND −2 Dex to the player and +2 Str
    to the boss** — double-ended ramp, you decay while she grows. Makes it a **DPS race**.
  - **Optimal line** (owner, matches consensus): spend the 3 sleep turns setting up (powers / scaling
    / draw), *don't* chip it awake, then **burst the turn it wakes** (Plating gone) and kill before
    Soul Siphon cycles neuter you. Punishes decks that can't stack damage early, lack big attacks, or
    hold powers.
  - **Model gaps**: §5-C estimate models Plating (`self_block`) but NOT (a) the Asleep free-setup
    window, (b) **player-side permanent decay** — our `str_ramp` ramps the *enemy*; Soul Siphon is a
    *reverse ramp on us* (damage **and** block decay), unmodeled, and (c) wake timing. One-turn planner
    sees only current Plating block. Per-enemy handler candidate; the −Str/−Dex move isn't in our
    bestiary yet (logging gap — capture its power text from a post-fix run that survives to it).
    *Hypothesis validated (re-batch bxtd5uum8, 2026-06-24): 0 Matriarch deaths (was 2/5); the one
    Matriarch fight was a **win** — lean 17-card deck, Strength ramped 3→8 by R4 + Bash Vulnerable →
    boss 198→22 in **6 rounds** (biggest effective hit 40 off a raw biggest_hit of 15), dead before
    Soul Siphon stacked. Vs the deck-blind losses that stalled the boss at 95–143 over 10 rounds while
    decaying to −4/−4. Stack-early + big-effective-hits = win; can't-stack = loss, exactly as owner
    called. **§5-C estimate gap exposed:** it predicted this winning deck would LOSE (win=False,
    boss_hp_left=200) — it models neither in-fight Strength ramp (Vajra) nor Vulnerable amplification,
    so it's pessimistic about ramp/Vuln decks (drafting-valuation bug; backlog).*
- **Slumbering Beetle (Act-2 normal, 86 HP) — Slumber + Plating** (owner 2026-06-23; same family,
  no Soul Siphon). **Slumber 3** decrements on **each HP-loss *or* turn** (3 combined events → wake),
  so unlike the Matriarch's binary damage-wake, **chipping it actively speeds the wake**; wakes next
  turn at 0 (current turn if poison) and **sheds all Plating** (15/turn here). Lower stakes (normal),
  but the wake-accounting differs — worth a shared "sleeper" handler with a per-enemy decrement rule.
- **The Insatiable (Act-2 boss, 321 HP) — Sandpit = a SOFT, extendable race** (owner 2026-06-25 +
  online-verified; now modeled). **Sandpit** is a ~4-turn countdown to an insta-kill — *but* the
  Insatiable shuffles in **6 Frantic Escape** cards; playing one **raises the counter** (+1 cost to
  that copy each time, so escalating), and **exhausting one loses a turn off the clock**. So the real
  race window is **~6-8 turns**, not a hard 4. The one-turn planner already plays Frantic Escape
  opportunistically (0-value cards go *late* in a sequence — owner: "already modeled"), so the bot
  does extend the timer. **§5-C now models it**: `detect_mechanics` parses the Sandpit deadline →
  `FightEnemy.death_timer`; `estimate_fight` pads it (`+_SANDPIT_SLACK` → ~7) and calls the fight a
  loss if not closed in that window → drafting now values burst for this matchup. Heavy hitter, ramps
  Strength. Won once (bxtd5uum8 R2, Vulnerable + race, 4 HP) / lost once (bx5u0h4ec R4, boss@80).
  **Refinement** (later): play Frantic Escape *strategically* — reserve for low Sandpit, mind the
  escalating cost + exhaust risk — rather than opportunistically.
- **Knowledge Demon (Act-2 boss, 379 HP) — Curse-of-Knowledge choice + a race** (owner 2026-06-25 +
  online-verified). Fixed 4-move cycle: **Curse of Knowledge** → **Slap** (17, 18 hi-asc) → **Knowledge
  Overwhelming** (8×3, 9×3) → **Ponder** (11 dmg + **heal 30** + **+2 Str**; 13/+3 hi-asc). After the
  3rd Curse of Knowledge it's skipped (the other three repeat).
  - **Curse of Knowledge** is a do-nothing turn that forces a **1-of-2 permanent-debuff choice**:
    R1 **Disintegration 6** (take 6 dmg end of each turn, *blockable*) | Mind Rot (−1 card drawn/turn);
    R2 **Disintegration 7** (stacks) | Sloth (≤3 cards/turn); R3 **Disintegration 8** | Waste Away
    (−1 energy/turn).
  - **Strategy (owner, first approximation): pick Disintegration every round** — the alternatives
    need expertise; refine later. So the fight is a **race**: by R3 you're eating 6+7+8 = 21 blockable
    self-damage/turn while it heals 30 + ramps Str on Ponder. Speed (and block) matter.
  - **Bot gaps** (handler candidate, ENEMY_PASS Act-2): (a) the **Curse-of-Knowledge choice screen** —
    needs a handler that picks Disintegration; *verify its screen type when next seen* (card-select vs
    event-like vs custom — determines where the handler lives); (b) the §5-C estimate models none of
    the escalating Disintegration self-damage, the Ponder heal, or the Str ramp → it under-rates the
    fight; (c) high HP + self-heal ⇒ needs a genuine race deck.
- **Aeonglass (Act-3 boss — replaced Doormaker in v0.107.1) — FIRST CAPTURE** (bxtd5uum8 R4,
  2026-06-24; our bestiary/card data predates it). High-HP wall (seen at 375). Mechanics: **Withering
  Presence** — *every 6 cards you play, add a Wither to your Hand* (punishes cheap/wide card-spam,
  rewards a lean high-impact deck); **Artifact** — negates your first debuff (strip it before Vulnerable
  /Weak lands); **Strength +7** behind 26 / 33 / 18×2 hits. The bot barely dented it before dying f48.
  New per-enemy handler candidate; re-harvest its full intent cycle + exact HP from a deeper run.
- **Kaiser Crab (Act-2 boss) — a DUAL boss with a facing / Back-Attack mechanic** (owner 2026-06-25,
  detailed). Captured raw as **two crabs**: **Crusher** (209 HP, Back Attack *Left*) + **Rocket**
  (199 HP, Back Attack *Right*); you start **facing Rocket**. Two intertwined mechanics, neither
  modeled:
  - **Back Attack = facing.** The crab you are **not facing** deals **+50%**. *Clicking* an enemy
    (attack / potion / any targeted action) **turns you to face it**, so the *other* crab now carries
    the +50%; the faced one doesn't. **Multi-target attacks (hit both) do NOT rotate** facing;
    **end-of-turn auto-plays (Stampede etc.) rotate it arbitrarily.** Rule: **end the turn facing
    whichever crab throws the bigger hit next**, so it lacks the bonus.
  - **Crab Rage.** When one crab dies, the other gains **+6 Strength + 99 Block** (one turn).
  - **Strategy (owner — corrects the naive "kill them together"):** killing one is generally a
    **boon** — you then face the survivor *permanently* (no more back-attack risk), and its one-turn
    +6 Str / 99 Block is a manageable cost. NOT an even-kill puzzle.
  - **Bot gaps** (handler candidate, ENEMY_PASS Act-2; no facing model at all): (a) *targeting order
    matters* — the last enemy you click is who you face at turn-end, so the planner must end facing
    the bigger threat; (b) the non-faced crab's incoming is +50%, so the §5-C estimate (flat 2-leader
    race) under-counts incoming and ignores both facing and the kill-one-buffs-the-other dynamic;
    (c) **draft trap** — end-of-turn auto-play cards (Stampede) can rotate facing badly; devalue them
    in Act 2 when Kaiser Crab is on the table.
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
  - **⚠ Survival hail-mary — the highest-value potion case** (owner, live 2026-06-25): bb2r3v7os R5
    died to Soul Fysh holding a combat-usable potion, no defensive use (one would have covered the
    lethal ~6). The post-plan hook's *first* question must be *"does the planned turn leave me dead —
    and can any potion (Block, Blood, even Glowwater → draw into a block) save me?"*. This is a
    **universal** survival fix — it would also save Act-1-boss deaths (the current wall), where the
    bot can't yet reach the Act-2 bosses the per-enemy work targets — so it ranks **above** the rest
    of the taxonomy and above further per-enemy handlers.
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
- **Slippery Bridge event** (owner lookthrough 2026-06-25; unmodeled, deferred). Picks a **random**
  deck card and offers to remove it, threatening 3 HP loss to decline; declining costs the HP, then it
  picks a *different* random card (preferring not-yet-offered) at +1 HP (4, 5, …) — escalating until you
  accept or die. The bot always accepts the first offer (fine for now). Ideal: know the deck and **fish
  for basic/curse removals** — accept the first "good" one, willingness rising as HP drops — gated on how
  much HP the rest of the Act will cost. Complicated; per-event handling. *(Ironic this run: it removed
  the Drum of Battle just drafted.)*
- **Byrdonis Egg event** (owner, 2026-06-16, seen live): Choose-1 — (a) gain Max HP, or (b) gain a
  **Byrdonis Egg**, a pseudo-curse (unplayable card). The egg can later be *removed* (pointless — you
  could have just taken the Max HP) or, uniquely, **hatched at a rest site** (a 3rd campfire option)
  into a moderately strong Act-1 attack, replacing the curse. **The bot currently takes the egg but
  never hatches it → strictly worse than the Max HP.** Right logic: at *event time* only take the egg
  if it'll reach the next rest site positioned to **hatch instead of rest** — i.e. arriving near max
  HP so the forgone heal is cheap; else take the Max HP. Then at the campfire, hatch when holding the
  egg and near-full. The "arrive near max HP at the next rest" check can reuse the §8.2 map
  HP-projection (it already walks the route projecting HP). Precision play; deferred. Minor caveat for
  the current batches: the bot eats this value when the egg event fires. *Live-confirmed (bxtd5uum8,
  2026-06-24): a run took the egg and then passed **3 rest sites without hatching** — it rode along as
  a dead unplayable curse, exactly the strictly-worse outcome. Still backlog (owner: "leave it").*
- **Pael's Tooth (Ancient relic) — an upgrade engine, not a removal** (owner 2026-06-25, seen live).
  On pickup: *remove 5 cards from your Deck; after each combat randomly add 1 back **Upgraded***. So
  the 5 "removed" cards return permanently upgraded (1/combat) — optimally pick the **5 highest-impact
  cards to upgrade**, not the worst, at the cost of a thinner deck for ~5 early-Act-2 combats (real
  risk). First approximation (owner): high-roll the 5 best and hope. But the screen is just "Choose 5
  cards to Remove", so the bot can't tell it from a normal removal → treats it as one and picks the 5
  **worst** (backwards). The relic is in `player.relics`, so the handler could detect Pael's Tooth on
  a remove screen and flip prefer-worst→best. Backlog (ancient relics as a class; owner: note for now).
  *(NB: this screen also surfaced the card-select hang regression — now fixed, commit 47e661d.)*
- **Girya (relic) — "Lift" rest option, and the non-standard-campfire class** (owner 2026-06-25,
  seen live). Girya adds a **Lift** choice at rest sites: **permanent +1 Strength**, up to **3 times**
  total (then greyed out) — for Ironclad that's +3 Str over the run, usually a **strong early pick**
  (it compounds) above Smith/Rest unless HP is critical. Same class as the **Byrdonis Egg hatch**:
  a relic/item-added campfire option the rest handler is blind to (it only weighs Rest vs Smith — the
  Byrdonis note confirmed it skips Hatch across 3 rests). Backlog: a pass to **read the actual rest
  options off the screen** and value the non-standard ones, rather than assuming Rest/Smith exist.
- **Miniature Tent (shop relic, Spirebird-top-rated) — "all rest options may be picked"** (owner
  2026-06-25). Lets you take **every** rest-site option, not just one — baseline Rest *and* Smith is
  already excellent, and it compounds absurdly with Girya / other rest relics (Rest + Smith + Lift×3 …).
  Weak only in the sad edge case of getting it just before Act 3's last rest. **Bot risk:** the
  rest handler picks **one option and leaves** (the game allows it) — wasting the multi-pick — or could
  **hang** if the screen stays open expecting more. *Observed: bx5u0h4ec R4 owned Miniature Tent and
  reached f33, so it did **not** hang on a rest — consistent with the pick-one-and-leave (suboptimal)
  case.* This is the capstone of the read-the-rest-options pass: with Miniature Tent, take **all**
  worthwhile options (Smith every upgrade, Lift to cap, Rest if needed), then leave.

### 8.5 The special-casing scrub — owner priority (2026-06-16)
Watching the live runs convinced the owner we will need an **exhaustive scrub of all Ironclad cards,
all enemies, and (eventually) all events** for things that need special-casing — *"there's just a lot
of these, and we're at the point where it's starting to matter."* The scrub is a category of its own;
the owner's projected-impact ranking within it:

1. **Deck synergy / archetype drafting** (§8.1a) — the deepest deck-power lever; data-gap-blocked
   (no co-occurrence in the export). Overlaps §8.0's deck-power priority.
2. **All-enemies analysis** — *already a run-killer.* The one-turn planner is blind to most enemy
   statuses/mechanics (see the §8.4 cluster: Slippery, Ringing, Adaptable, Illusion, escalating
   end-of-turn DoT, **Soul Fysh** block-bypass status-card, **Knowledge Demon**). **→ Dedicated plan:
   [ENEMY_PASS.md](ENEMY_PASS.md)** — bosses-first, harvest mechanics from the mod's own status
   descriptions (confirmed they ship as rules text), classify (A already-modelled / B extend the
   estimate / C per-enemy handler), route through the §5-C estimate; seeded custom runs as the
   deterministic test bed.
3. **Play Powers earlier** (first approximation to card analysis) — the "play 0-cost Powers
   immediately" fix (§8.4) generalises to better power-timing priority overall. Small, near-term.
4. **Card-by-card examination** — a systematic pass over the full Ironclad list flagging cards the
   generic planner can't reason about (Anger, Fiend Fire, scaling/conditional cards), then encode
   per-card handlers/annotations (§8.3 "per-card special-case pass").
5. **Event analysis** — mostly already covered by event-choice WAR; only a few events carry nuance
   (Byrdonis Egg, §8.4). Lowest priority.

Sequencing note: this complements §8.0 (the immediate routing/deck-power items). Items 2–4 are the
combat-side maturation that the §5-C capability estimate was built to anchor — they slot in as its
consumers, not as a pile of one-off rules.
