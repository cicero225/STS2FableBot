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
│  Slay the Spire 2 · Godot 4.5/C# · release branch · bot plays modded profile 1 │
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

- Python 3.12+ (NFR-1; 3.14 on the original box, 3.13.2 since the 2026-07 machine move),
  stdlib `venv` + pip, `pyproject.toml` (no uv on box).
- **pydantic v2** for state models (validation = patch-drift detection per C5),
  **httpx** for the client, **typer** for CLI, **pytest**, **ruff**.
- SQLite (stdlib) for run index; JSONL for decision logs (one file per run).
- Config as TOML in `config/` with a content hash recorded per run (FR-3.4).
- LLM calls via `anthropic` SDK, behind one gateway module with the ledger + caps.

## 4. Phases

**Current phase (stamped 2026-07-08): P1 — Competence.** M0 is closed; M1 (≥40% A0 win
rate, n≥20) is the target — first-ever A0 win landed 2026-06-26, win rate otherwise ~0%,
binding wall = the Act-2 bosses (Knowledge Demon / Kaiser Crab, f33). P2's fork item
(§P2.1) landed early, out of order; the rest of P2 waits on M1.

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
*Status: ✅ **CLOSED** (stamped 2026-07-08 — met long before: hundreds of clean end-to-end
runs since 2026-06-11). Item 8's investigation leftovers (non-interactive modded launch,
locked-character representation) move to the §7 open-items table where they already live.*

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

*Owner steer 2026-09-28:* the A0 graduation reading must be **definitive** —
23/120 (19.2%) on the observed-capability keys is not yet (95% CI ~13-27%;
batches 2-4 (3/28, 3/33, 5/39 on 09-28..30) pooled to 34/220 = 15.5%; batch 5 -- the first with all five 09-28..30 mechanic fixes (Matriarch sleeper v4, True Grit, Setup Strike, Entomancer hive, Waterfall eruption budget) -- went **12/40 (30%), a record**, act-3 conversion 12/17; batch 6 cut at 2/25 (soft eruption budget harmful, gated off), batch 7 8/39 with the Tainted model, batch 8 8/39 with the recalibrated eruption model (Waterfall 5/5); batch 9 6/40 (heavy act-1 batch), batch 10 9/40 with random-target pessimism + chooser exhausts, batch 11 9/40 with a record 24/40 act-3 arrivals, batch 12 12/40, batch 13 5/40; **final A0 reading on the post-decode code: 71/343 = 20.7% (95% CI ~16.4-25.0%)**; pooled 105/563 = 18.7%. **GRADUATED to A1 on 2026-10-01 (owner, biasing early: ~15% still gives signal)**; batch 14 onward at `--ascension 1`; **batch 14 (first A1): 4/40 (10%)** after a 0/29 open; **batch 15: 5/39 (12.8%) -> pooled A1 9/79 = 11.4%** (under the ~15% line; act-1 thin-deck elites, forced-elite lanes, act-3 boss 9/27); batch 16 (Painful Stabs) 4/15 -> pooled A1 13/94 = 13.8%; batch 17 adds Dex potions in the DFS, lethal hail-mary at any HP, and final-boss rest below 90%; **batch 17: 7/40 (17.5%), best A1 batch -> pooled A1 20/134 = 14.9%** (act-3 boss 7/12; KD/Vantom dips replay-verified as not code-caused); **batch 18: 9/40 (22.5%) -> post-fix A1 16/80 = 20.0%, pooled A1 29/174 = 16.7%** ; **batch 19: 12/40 (30%) -> post-fix A1 28/120 = 23.3% (CI ~16-31%), all A1 41/214 = 19.2%** -- above the A0 graduation level; A1->A2 is the owner's call (next bar: Ironclad A3 at ~20%); owner act-1 narration seeds banked (6CWS5L0XMV first) -- A1 differs only in elites (+0.5/act; HP/intents/start identical), gap is act-3 boss conversion 4/14 vs 49% + act-1 elite deaths; next bar Ironclad A3 at ~20%, then switch class);
plan two or three more clean 40-run batches (~±5pp) before calling it. Then
climb Ironclad to **A3 at ~20%**, then **switch class** as a break (a broader
class base likely helps each class; diminishing returns per ascension, with
the sharpest spikes at A8/9/10). Ascension is set per run via set_ascension;
the picker remembers the last level and climbs after wins — verify the meta
ascension of every batch (the 09-28 slip ran A3-A8 unnoticed until the enemy
HP gave it away).
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

### 5.2 Forward-model requirements — harvested from live piloting A/Bs (2026-07-24/25)

Sources: Soul Fysh fight/draft A/Bs (X9VM7AR5PF), act-2 handoff (Infested Prism -12 HP),
and the narrated Exoskeleton fight (LKG20K3FBE f21 — bot died r4 from 47; owner won at
3/80 with full turn-by-turn reasoning on record in logs/manual/runs/20260726-171135).
Each item is something the one-turn planner structurally cannot represent:

1. **Draw-pile forecasting.** "The remaining 6 cards are X — so blocking three enemies
   next turn is bad regardless." Plans discount block-now vs block-later using known
   pile contents; the owner tracked the exact last card before each reshuffle.
2. **Deck-state clocks.** Bad Luck recurs per cycle -> kill speed outranks HP thrift,
   and exhaust-thinning becomes BAD (smaller deck = faster curse recursion). Tempo
   preference must be a function of what the deck does when it cycles.
3. **Cap-aware kill sequencing.** Hard to Kill (9/hit) makes spreading damage nearly
   worthless; the fight is a two-turn-kill scheduling problem. Note the meta-lesson:
   caps PRUNE the search ("the 9-cap saves me a detailed calculation"), they don't
   just rescale values — mechanics as search-space reducers.
4. **Anticipatory focus-fire.** Target the FUTURE-strongest (the buffing body), and
   don't switch when a buffer merely converges to the current target's strength —
   banked chip under a cap is a sunk asset.
5. **Cross-fight potion economy.** "With multiple normal fights coming up I wouldn't
   commit potions to this fight's opening" — potion value is a run-level resource
   allocation, not per-fight; stacking potions (Powdered Demise) invert this when a
   fight is KNOWN hard (perfect play = turn 1 deploy).
6. **Conditional card economics.** Fight Me!'s downside erased by killing its
   recipient; Cruelty near-worthless into caps; Brightest Flame's permanent -1 Max HP
   almost never worth deferring (relic-conditional: Chosen Cheese offsets).
7. **Verified already-correct**: minimal-lethal lines (planner drops downside cards on
   lethal turns — probe 2026-07-25), Bad Luck's 13 in survival math (hand-curse lane
   parses it), relic-counter-conditional "play everything" turns.

**P1/P1.5 executed (2026-07-25, eb6505b + 798e1ca):** rollout engine built
(`sts2bot/policy/rollout.py` — greedy policy, content-derived seed) and the
calibration loop closed: a dps sensitivity probe localized the error to the ENEMY
model; `scripts/build_enemy_dps.py` harvested realized per-enemy dps from intent
labels (106 enemies; priors ran ~2x hot — Soul Fysh 8.4 realized vs 25 modeled).
Post-fix backtest: elite-act1 94% predicted vs 97% actual (bias +4.4), elite-act2
67% vs 67% — ELITES CALIBRATED; bosses still 15-22% vs 55% pending potion/relic
terms (the live bot wins bosses with resources neither engine models yet).
CAUTION for the next batches: the elite gate's July thresholds (pool frac 0.40,
floor 0.20) were loosened to compensate for estimator pessimism that no longer
exists — with calibrated inputs the gate will open far more often (correctly, per
the 97% actual win rate, but the thresholds may need RE-TIGHTENING once the
compensation is redundant; the next batch is the live A/B).

**Round 2 additions (Ovicopter A/B, DELDJQX3BP f24, 2026-07-25 — bot died r3 from
19 HP, owner won r2 from 19 HP, zero potions spent):**

8. **Fight-level intent.** The owner locked "burst the spawner, no AoE for the swarm"
   at the door and every turn served it; the bot had only turn-local scores. A fight
   opens with a PLAN (race / clear / stall), refreshed on evidence.
9. **Route-state sets the fight's risk budget.** Campfire-chest-campfire ahead ->
   attrition to near-1 acceptable -> Bloodletting plays freely. Routing context must
   flow INTO combat, not just out of it.
10. **Exact arithmetic at binary stakes.** "Either I have lethal or I don't" — when a
    line is kill-or-die (enemy-buff riders, counterattack lethals), the owner switches
    from heuristic scoring to exact damage accounting with a declared bailout
    (energy potion) — and the miscount he DID make (unupgraded Strike, -5) is exactly
    what a simulator never gets wrong.
11. **Draw-pile stacking as tutor value.** Headbutt+ returned Bloodletting+ to the
    draw pile top to guarantee next-turn energy — put-back/tutor effects are worth
    far more than their stat line when sequenced across turns.
12. **Archetype-conditional potion value.** Flex is weak in general but "very hard to
    get a better turn" for an all-attack hand, and notably strong in eternal/attack-
    heavy decks — potion value conditions on hand shape and deck archetype.
13. **Turn-order as next-turn setup (History Course, owner 2026-07-30).** "At the
    start of your turn, play the last played Attack or Skill from last turn" — the
    replay target is CHOSEN by this turn's play ordering (end on the best card),
    and its value depends on next turn's needs. The trigger table can't express
    cross-turn state; a cheap interim exists (bias plans to END on the strongest
    Attack/Skill while held, Rage-sequencing style) but the honest treatment is
    multiturn. In-turn effects need nothing: the auto-replay resolves before the
    planner sees the state (pre-bake).
14. **Fight-open plan selection — SHIPPED in miniature (62a6261, Kin A/B 2026-07-30).**
    Owner won 9NUW6E6TGZ from 67 HP (bot lost from 77) by killing the Followers first
    with a scaling deck — while his June fight RACED the same boss with a burst deck.
    Round-1 rollout comparison of both target orders now picks per fight (the owner's
    "correspondence between scaling cards and investing in defensive resources" is what
    the comparison measures implicitly — a scaling deck wins more sims in the
    buy-time order). Remaining from the same A/B, for the POTION PASS: (a) known-hard
    fights front-load the belt turns 1-2 instead of the reactive one-per-near-death-turn
    hail-maries the bot showed; (b) ONE-TURN debuff potions (Potion of Binding: 1 Weak +
    1 Vulnerable) are TIMED, not auto-T1 — the owner held Binding to turn 2 because turn
    1 the enemy was buffing and his own output was low pre-Rupture; value = biggest
    enemy attack turn x own biggest output turn.

Encoded immediately (4b4b4ee): enemy-buff riders in the sim (kill-or-pay), strength
potions in the lethal search, full-belt spend prior.

**Calibration baseline (scripts/calibrate_capability.py, 2026-07-25, n=292 modern-era
elite/boss fights):** estimate_fight is uniformly pessimistic, never optimistic —
predicted 0% act-1 boss wins vs 55% actual; 55% predicted act-1 elite wins vs 97%
actual (gate-selection caveat applies to elites, NOT to bosses — every run fights its
boss); mean HP-loss bias +8 to +24 by segment; false-positive rate ~0% everywhere.
Consequence: every gate threshold tuned to date has been compensating for a broken
absolute scale. The forward model's acceptance test = beat this table.

Root confirmation from three independent audits: the static capability estimate
(deck_output) cannot see engine/generative decks (owner's f6 Stoke deck read as 9.6
sustained dmg/turn, gate said 0/6 elites, owner went 3-for-3). The forward model must
simulate DRAWS AND PLAYS over multiple turns, not summarize the deck as static output.

**Engine-coherence gap (2026-08-01, same-seed deck diff E4ZW92AFP5 — the sharpest
draft evidence on record):** owner (won) and bot (lost) shared an identical early
spine off the same seed, then diverged: owner built TWO engines (Barricade + 2x
Body Slam block-to-damage; Rupture++ + Crimson Mantle + Bloodlettings self-damage
-> Strength, the Str-23 source) with support drafted FOR them; the bot amassed
individually-excellent cards (Bludgeon++, Whirlwind, 2x Dominate...) with no
engine — including Barricade++ with ZERO block payoff, violating the owner's
stated Barricade criteria even post-clamp. Root: §5-C prices MARGINAL deltas;
engine piece #1 always deltas weak (Body Slam alone ~ nothing), so multi-card
engines are unreachable by greedy gradient. Candidate mechanisms, in cost order:
(a) parser: 'damage equal to your Block' reads fx.damage=0/stale-preview — make
block-scaling damage dynamic in the sim (unblocks Body Slam valuation NOW);
(b) drafttags: engine-seed tags (barricade_core, self_damage_engine) with
draft_bonus steering once a seed card is owned — cheap archetype commitment;
(c) the honest version: pairwise/lookahead deltas (price card X assuming the
deck also gets its partners later) — §5.2-scale. Owner: 'a comparison of exact
decks may be worthwhile for insight' — it was.

**Forward-model rollout status (2026-07-30):** P2a rollout elite gate live (win_rate +
p25 tail floor; pass-side evidence logged since 185b7a9). P1.7 DFS-policy boss rollouts
live for known bosses — one physics (_RolloutSim), two turn policies; backtest 52% vs
greedy 38% (actual 65%); live latency: median 704ms, max 10.4s, cached per deck+boss
(4a55200). P2b: the pre-boss rest gate now consumes the DFS estimate (1f69f96), retiring
the hand-patched per-boss rest bumps for known bosses. Boss residual ~13 pts = synth
bridge v1 gaps (Strength not re-baked into card texts) — next calibration lever.

## 6. Working conventions

- Mock-first; live game sessions are attended (owner present) until owner flips
  unattended on. Every live session starts with `scripts/backup_saves.py`.
- Commit per coherent step; config changes are separate commits (FR-3.4 auditability).
- After each live milestone: short LOG.md entry (date, game version, what happened) —
  the project's lab notebook.
- Re-clone the mod when absent: **our fork, `v107-fork` branch** — see CLAUDE.md for the
  exact commands. (An earlier version of this line said to clone upstream `Gennadiyev/STS2MCP`;
  doing that is the 2026-06-23 regression — upstream silently lacks `player.deck` etc.)
- LLM usage: ledger from day one, even in dev (FR-5.4).

## 7. Open investigation items (rolling)

| Item | Phase | Notes |
|------|-------|-------|
| **Mod broken on game v0.111.0 (public-beta, 2026-09-26): rebuild the fork** | infra/mod | STS2_MCP.dll throws TypeLoadException on MegaCrit.Sts2.Core.Entities.Multiplayer.LobbyPlayer at load (0/1 mods loaded). v111-fork branch built clean against v0.111 the same day (lobby members by reflection; local commit, not pushed; DLL in external/builds/). NOT installed: the owner runs the main branch (v0.107) for testing, where the v107 DLL is right. When the real patch lands: build the matching branch, copy the DLL to mods/, doctor. Also: the game in modded mode shows only modded/profile1..3 -- the owner's personal profile is the UNMODDED profile1 (present, verified 2026-09-26); 'profile missing' after a branch switch = mods still enabled, not data loss. |
| **Shop bought-list never reset between shops (FIXED 2026-09-11, fab6f08) -- affected the entire record since 2026-06-11** | infra/shop | screen_mem['shop_bought'] accumulated across the run, so stable slot indices bought earlier (removal = last item; relics 7-9; potions 10-12) were unbuyable at every later shop: no run in the era bought a 2nd removal (493 at exactly 1, 56 at 0); shop #4+ averaged 1.27 buys vs 1.6 (31% zero-buy visits, 10% zero-buy with >=200 gold). Owner caught it as 1170 gold walked out of an act-3 shop before Aeonglass. Every batch before this date, live and arm, carried it -- the era baseline (9.6%) is a with-bug baseline; a fresh live control on the fixed code is queued after the replication. |
| **Capability estimate MISCALIBRATED: elite gate + boss forecast (2026-09-03, from the HQX8M7T6VN full-run diff) -- A/B arm running** | §5-C / P2a | Owner fought 6 elites (20 relics) on the seed where the bot fought 0 (10). Exact map replay: the gate's greedy pool rollout priced the act-1 pool at a MEDIAN 75-of-80-HP loss (elite nodes death-class at every floor; f10 fork Elite -195.9 vs Monster 19.1) and the DFS boss forecast read a full loss at every floor (desperation on 81% of era gate evals; every pre-boss campfire a rest). Era calibration (423 runs since 08-27; logs/reports/elite_calibration.md): 500 real elite fights won 95.6%, fights the rollout rated <20% won 88%; predicted loss 37.6 vs actual 23.5, corr 0.18 (no rank signal); deaths entered at median 63% HP vs survivors' 80%. Boss: >=90%-max-HP forecast on 61-99% of evaluations vs actual act-1/2 wins 59-86%. Arm (config/experiment_calibrated_capability.toml, 237a23779317; hooks ba2150a): elite_loss_source=observed (mean 22, gate bypassed, HP projection + 50% entry floor govern), boss_loss_source=observed. RESULT (arm v1, 40/40): **7 wins (17.5%)** vs era 9.6% -- record batch; elites/run 3.5, relics 12.4 vs 9.7, act-2/3 boss survival 74%/44% vs 59%/29%; elite deaths 1.8% of 113 fights. Arm v2 (218c180e300e) adds the pre-elite campfire rule (the DP assumed a heal the campfire policy skipped). Decimillipede DECODED 2026-09-03 (bestiary Reattach text: segments revive at 25 in 2 turns while others live; the API drops dead segments so 'last one' read as lethal) -> planner futile-kill rule 18347c6 + replan play-kind seeding 41fe501 (per-turn relic cadences were reset on every replan -- a missed Kusarigama lethal lost that fight). Sub-arms v3/v4/v5 (per-act entry floors, deck-size floors) were tuned on 1-3 deaths each and ran 5/54 vs v1's 7/40 -- reverted; arm v6 (440a99adf4b7) = v1 keys + pre-elite campfire rest + boss safety 1.4 (both n>=40). v6 ran 0/10 (its rest rules cost upgrades); v1's exact config REPLICATED 7/40 on the fixed code + shop fix (2026-09-11) -> two clean v1 batches 14/80 (17.5%) vs era 9.6%, ~2.2 sigma. Live control x40 on the fixed code: 6/40 (15%) -- the code fixes (shop bug above all) lift live by ~5pp; v1 arm 14/80 (17.5%) on the same code, 3x the elites and +3 relics/run. PROMOTED 2026-09-28 (owner GO, b92cc58). The three 09-28 batches on it (3/38, 2/19, 0/12) ran at ASCENSION 3-8 by a charselect bug (e22cc74) and are not comparable; first A0 batch on the promoted config 2026-09-28: **9/40 (22.5%), record**; v1 keys at A0 over three clean batches 23/120 (19.2%); batch 2 (09-28, stopped at 28/40 for the owner's GPU, run 29 saved for Continue) 3/28 -> pooled 26/148 (17.6%), act-1 deaths 13/28 (Matriarch x3, Waterfall x3, early elites x5) -- sleeper v4 + True Grit sequencing (ce7359d, 928a820) land with batch 3. Soft spot: act-1 boss (reach act 2 65%). Pool-zero elite veto built, act-scoped, default off; A0 evidence supports act 3 (owner's call). Still to watch: act-2 normal packs vs weak decks, Effigy -50 tails into campfire-less lanes (the optionality item below). ELITE HEAD (first fit 2026-09-03, logs/reports/elite_calibration.md): P(elite loss>=40 or death) from deck features + elite id, test AUC 0.62 on 799 fights -- the only estimator with any deck-quality signal (rollout and closed-form both ~0). Refit at ~1500 elite fights and wire as est_elite_loss = E[loss | deck, act] in the map DP (the §9 'fitted evaluator at an existing decision point' shape). Still open after the arm: the same rollout family prices DRAFT capability deltas and sweep/focus plans; §9's learned boss head is the principled replacement for both forecasts. |
| **Desperation coupling: latch observation (RESOLVED as non-regression, 2026-08-03 morning)** | P2a | The 2026-08-02 "regression" was a BASELINE ERROR: the ~12% reference was the session-17 hot-streak window (4 wins/34); the actual full-day 08-01 record was 1/91 (1%), long-run ~1.5%. The 08-02/03 batches (4/132, 3%) were the BEST day on record: reach-act-2 56%→67%, act-1 boss conversion 62%→71%, act-3 boss conversion 7%→15%. Attribution arms (both-on 2/60, desperation-off 1/20, both-off 1/40) are all consistent with ~3% and distinguish nothing; both toggles REVERTED same night. Standing observations that remain real: (a) gate_desperate latches run-long once a deck forecasts doomed (46/47 map rows in one f48 run) — by design but worth a calibration look eventually; (b) the binding constraint is now clearly BOSS CONVERSION in acts 2–3, not act-1 survival (Insatiable f33 cluster: 5 deaths in one evening). Lesson recorded: always compute the baseline from the full ledger, not a remembered streak. |
| **Multiturn planner spec #1: Kaiser kill-by-Laser-turn test (owner A/B 2026-08-03)** | §5.2-P4 | Owner won 68→20 all-in Rocket-first. His actual rule is NOT 'never block in the two-claw phase' — it is a feasibility calculation: Rocket's turn-4 Laser is the fight's biggest hit; estimate 'can I kill Rocket by T4 without dropping below ~25 HP?' If yes: all-in (block ≈ waste — the surround clock costs ~10/round regardless). If no: semi-defensive, still prioritizing Rocket, aim the kill at T5–7 and DEFEND the Laser turn. A flat block-devalue was rejected as too blunt (it would block wrong on exactly the Laser turn). Requires: enemy move-script awareness (Laser=T4) + a kill-ETA estimate vs current hand/draws — the first concrete, owner-specified multiturn test case. Related encoded now: rollout surround parity (14d8136); facing-redirect-as-block already representable. Also noted: late-fight exhaust gambles (True Grit eating Inflame+ when block > future Str) are value-horizon calls in the same family. |
| **Silent batch early-exit — RESOLVED 2026-08-04 (was the C5 halt with discarded stdout)** | infra | With output finally captured, the 'silent' exit reads plainly: 'stopping: run did not complete cleanly (C5)' after a treasure-claim wedge stall-abort — the designed batch halt, invisible only because launches piped stdout to /dev/null. (The 24/30 'no error run' case likely wrote its error meta a moment after my count.) Real remaining item = the WEDGE frequency: treasure-claim stale-UI-ref wedges hit 3x in ~36h (f26, f38, f41 — act-2/3, ?-node correlation), each costing a batch halt + owner restart. The fork session (UI-ref re-resolution + scene liveness) and abandon-to-menu batch resilience remain the fixes; frequency now justifies scheduling both. |
| **Prediction-audit debugging block (owner directive 2026-08-04: 'resolve remaining forecast-vs-actual discrepancies; prioritization yours')** | P2/§5-C | predict_audit over 120 fresh runs (5,958 turns): HP model 84% within ±2. Ranked worklist -- HP side: (1) STRENGTH_POWER bucket n=106 avg +2.9 (most frequent; drill needed -- correlation vs real leak), (2) Waterfall Giant −10.3 RESOLVED 2026-08-09: owner decoded the full mechanic (0 HP → untargetable 'preparing' shell w/ sentinel HP 2^32−1, does nothing that turn → next turn intent = accumulated Steam Eruption, delivered blockably on ITS turn → dies; poison-kill on its own turn shifts phases one turn later) — rollout now models the delayed blockable finale instead of an instant unavoidable hit (c494a72); one-turn planner was already correct via intents (knockdown skips predicted attacks -> systematic over-blocking; may connect to WG f17 deaths), (3) Bygone Effigy +9.8 / Spiny Toad +6.1 (unmodeled attack scaling), (4) Axebot round-1 chip pred=0 actual=3-7 (STOCK_POWER turn-1 behavior + a suspicious r1 LETHAL tag vs 72 HP -- check for another phantom-lethal species). DAMAGE side: near-uniform 'MORE than predicted' (+5..28) across bosses suggests part METRIC artifact (plan_damage excludes thorns/potions/replays -- fix the tool first, then re-rank); Axebot −15.7 and Thieving Hopper −8.5 overpredictions are real model candidates (plating/dodge). Protocol per discrepancy: drill -> classify (model bug / metric artifact / variance) -> fix with regression test -> re-audit. The Ashen pile double-count (5b9d2cd) is the template: each fixed class removes a misplay family. |
| **Prediction-fuzzing experiment (owner design 2026-08-06; scheduled AFTER the audit block + queued work, BEFORE the multiturn planner)** | P4-prep | Owner protocol: bot runs to random normals/elites/bosses, then plays cards in RANDOM order while logging the planner's per-play predictions; compare predicted vs actual HP/damage per PLAY (finer than the audit's per-turn grain). Rationale: the passive audit only covers states the policy chooses -- random play is OFF-POLICY exploration that reaches orderings/combinations the planner never picks, where conditional riders and sequencing bugs hide. Code prep: (a) a --fuzz-combat mode picking random legal plays with full prediction logging per action; (b) safety rail: PAUSE + notify (handoff-style, never die) when HP < floor or the fight nears its end -- the owner savescums, the bot resumes NORMAL play to reach deeper fights, then fuzzes again; (c) analysis: per-card prediction ledger bucketed like predict_audit (card x enemy x status). Attended sessions only (owner is the savescum operator). |
| **KD in-fight choice screens are TEXTLESS via API (fork ask #4, found 2026-08-06)** | fork | The Knowledge Demon's forced picks surface as event screens whose options carry NO label/text in the API payload (tape: opt 0/1/2, enabled None, empty strings) -- the bot resolves them via generic event machinery + Spirebird name-matching only when a name leaks through ('Tea of Discourtesy'). The owner's remembered 'always take the HP-loss option' rule does not exist in code and CANNOT be implemented until the mod exposes the option text. Fork asks now: (1) UI-ref re-resolution, (2) scene-liveness field, (3) abandon-to-menu, (4) in-fight event option labels. KD choice-quality data pass blocked on #4. OWNER-PROVIDED choice table (2026-08-06) for when #4 lands: Set1 Disintegration(6 dmg/turn) vs Mind Rot(draw -1); Set2 Disi(7) vs Sloth(max 3 cards/turn); Set3 Disi(8) vs Waste Away(-1 energy/turn). Disintegration STACKS and is ALWAYS the right pick -- and by luck it is also the current blind default (option 0), so no behavior gap today; implement the explicit rule (+ per-set Disintegration self_end_damage tracking, already text-parsed live) once labels exist. |
| **Game crash instance #2 (2026-08-07 morning, unattended)** | infra | Same signature as #1 (2026-08-06: WinError 10054, connection forcibly closed mid-run; game process gone). Batch C5-halted cleanly after 6 runs; run f9 lost. No bot-side trigger visible in the tape (mid act-1 combat). The crash-watchdog/relaunch infra item is now twice-motivated for unattended trains -- note the bot CANNOT relaunch the game itself (Steam/GUI); a watchdog could only alert. Port watcher armed; train auto-resumes on owner relaunch. |
| Modded non-interactive launch — **RESOLVED 2026-08-27** (owner authorized bot self-launch, remote session) | P0.8 | Procedure: (1) one-time `steam_appid.txt` containing `2868840` in the game dir (direct exe launch otherwise dies at a Steamworks "No appID" popup — first attempt hit exactly that); (2) Steam client must be running; (3) `Start-Process SlayTheSpire2.exe` directly — mod loading is a PERSISTENT game setting (Settings→Mods consent, long accepted), NOT a per-launch choice, so plain launch comes up modded ("RUNNING MODDED", MCP server on 15526, ~30s to menu); (4) `sts2bot doctor` to verify state=menu + current_profile_id=1 before batching. Works under a LOCKED Windows session (game renders fine, lock screen on top). This INVALIDATES the 2026-08-07 note "the bot CANNOT relaunch the game (Steam/GUI)" — a crash-relaunch watchdog is now buildable, upgrading unattended-batch resilience from "alert and wait for owner" to full auto-recovery. |
| Real save path + Steam Cloud behavior per profile | P0.7 | decide cloud on/off before first bot launch |
| Locked character/ascension representation in API | P0.8 | affects climb manager |
| Spirebird export shape & licence/courtesy ask | P1.2 | jorbs Discord if unclear (C4) |
| Game patch cadence on release branch | P1+ | informs KB diff automation priority |
| StS2 ascension cap (10 vs 20) | P2 | owner reports 10 currently; verify in-game |
| Act-2/3 elite mechanics pass (Knights trio, Infested Prism, Decimillipede) | P1 tactical | 2026-07-24: owner flags the planner likely doesn't know the unique act-2/3 elite mechanics (the Knights "are very unique" -- never discussed). Corpus: these fights ran near-lethal (44->9, 38->death, 53->death, 33->11 entry->exit HP), which is also why the elite gate correctly refuses them. Not the current blocker (act-1 rate 0.4/run is the lane in use); do a bestiary+rule pass when act-2/3 elite aggression becomes the lever. REFRAMED 2026-07-24 (owner): Act 2 has the HARDEST elites relative to deck power -- humans take the fewest there; they still reach for one when they judge the deck can take it, but shirking is more reasonable there than in any other act, and some winning runs dodge act-2 elites entirely and make up in Act 3 (not true of Act 1). So the gate's act-2 conservatism is human-endorsed in shape (a nuanced judgment, not a hard no); the real aggression gap to close is ACT 3, where our elite rate is also zero. |
| Phantom duplicate map decisions | RESOLVED 2026-07-25 (8ae71ce) | Root: after an ACCEPTED travel the mod re-renders the map minus the consumed option within the same second; the fast poll caught it, the router re-decided on the leftovers and submitted a second travel (ok-ed, ignored). Fixed with a map travel-hold keyed on (floor, position), 8-tick recovery budget. Historical logs before this date still contain phantom rows -- filter route-intent analyses by first-decision-per-position. |
| Fake Merchant event -- bot always proceeds; discount '???' relics unbought | event pass | 2026-08-01 (owner): the fake merchant sells WEAK VARIANTS of real relics ('Anchor???', 'Mango???') at ~50g -- clearly worse than the real thing but 'surprisingly worth buying sometimes' (owner bought several in the winning E4ZW92AFP5 run). Only the trivial fallback handles FakeMerchantState ('ignores fake merchant'); StandardRouter has no handler at all. Minor pass: buy cheap ???-relics when gold-rich (value ~1/3 of the real relic's WAR?); calibration note: N bought ???-relics ~ 1-1.5 real relics for relic-count comparisons. |
| Shop CARD purchases -- no lane exists; egg-relic ordering pinned | shop pass (ELEVATED 2026-08-01: owner flagged twice; Signet Ring windfalls make the missing gold sinks measurable -- design constraint per owner: the relic-vs-card balance 'is not easy') | 2026-07-30 (owner live catch, Toxic Egg): the shop ladder buys discounts -> removal -> relics -> potions and NEVER cards (spend-down excludes them deliberately). When a card lane lands: (1) it must sit BELOW the relic step so the egg relics (Toxic/Molten/Frozen = upgrade every future added Skill/Attack/Power) are bought FIRST -- same shape as Membership Card; (2) an egg's value is CONDITIONAL on matching-type card adds -- owner bought Toxic Egg then immediately a skill; consider a lowered buy bar when a matching-type card purchase is planned in the same shop. Spirebird today: Toxic 0.035 (buyable), Frozen 0.005 (sub-bar), Molten -0.015 (skipped) -- owner broadly endorses this ranking, with a mild CLASS dependency (revisit per-character when multi-class play starts). |
| Routing: optionality value (elite-or-bypass paths) | P1 routing design | 2026-07-24 shadow review: the owner routes for paths that KEEP THE CHOICE open -- "either go into an elite or avoid it (ideally a campfire)" -- e.g. took Shop->Elite over the forced-Elite line on X9VM7AR5PF f7 because the shop branch had a post-elite bypass. Current path scoring prices the single best path, so committed and optional lines with equal EV tie. UPGRADED SPEC (owner's live route monologue, act-2 handoff 2026-07-24): (1) plan BACKWARD from act anchors (guaranteed pre-boss chest, boss) -- find the branch with elites+campfire+escape hatches near the top; (2) value DEFERRED choice points: elite->campfire->? where the ? row lets you dodge elite #2 after seeing post-elite HP; the whole branch declinable at the chest if limping (explicit safe line: campfire-monster-shop-monster-...); (3) enter mid-map through nodes that PRESERVE the safe-vs-elite choice (reach the chest via campfire OR elite, chosen late); (4) front-load fights early in the act (first ~3 fights easiest -- our row<EARLY_ROWS pricing agrees, though the monster_early stat isn't act-split and is act-1-dominated) and shop early when gold-rich (had 314g); (5) deck sanity gates ambition (3-elite act 'possible but not probable'; early fights are the test). Winged Boots (owner 2026-07-29): charge economy is the same family — charges are options-insurance (rest when desperate, shop when gold-rich); interim flat boots_jump_cost shipped, the full treatment (charge value scaled by remaining charges, act position, and gold/HP state) belongs here. Pael's Tears cross-turn energy banking belongs to the rollout relic terms. Implementation shape: not a per-node bonus but a small policy tree over the act graph -- value(path) should include the max over CONDITIONAL continuations at each branch point, i.e. one-step option value, not committed-line EV. |
| Map path values go hugely negative (RestSite -58.7, Shop -150) | P1 routing audit | 2026-07-24 shadow replay (X9VM7AR5PF f6-f8): a RestSite next-node priced -58.7 and a Shop -150.2 -- owner: 'rest sites are not negative 58 hp'. Suspect downstream pocket pricing (forced elite rows behind them) double-charging or rest-heal not credited on the path sum; also the monotone slide into -80 by f16 in the same act. AUDITED 2026-07-25: no arithmetic bug. -58.7 = rest 16.1 + 0.8 x (-93.5): BOTH rest-branch continuations funneled into elites and the SS5-C gate had priced the whole act-1 pool unwinnable (0/6, est loss = death) for the owner's 15-card f6 deck -- deck_output credits a Stoke/Bloodletting engine with only 9.6 sustained dmg/turn (generative effects are invisible to the static read; the owner then went 3-for-3 on elites with it). The monotone negative slide near act end = shared boss death-pricing (est_boss_loss = death for weak-rated decks), constant across paths, cosmetic for ordering. ROOT = the capability estimator, not the DP -- folds into the forward-model phase; no weight fix applied. |
| Combat flicker under status-cap curses (poll-driven re-render) | aesthetics / livewatch prep | 2026-07-25: twice-audited ILLUSION -- under Normality the hand twitches like the bot is fighting the cap, but act-3 audit shows 77 play submits, 1 benign index-drift reject, 0 hammering. Cause: the mod re-renders on every /state poll (~0.15s at 4x). Owner: not important now; revisit when the bot goes up for LIVEWATCHING. Fixes, best first: (a) mod-side passive /state read (also fixes recorder click-fighting + phantom map re-renders -- highest-leverage mod change on the books); (b) slow polls during non-actionable windows (enemy turn). |
| Fork: expose map-node modifiers (Fur Coat marks etc.) | mod fork / routing | 2026-07-25 (owner): Fur Coat picks 7 random fights this act and dials enemy HP to 1 -- effectively free rooms -- but the mod's map payload carries NO marker (verified: node keys identical before/after pickup), so routing can't see them even in principle. Fork ask: serialize per-node modifier/icon list on map nodes (generalize -- other room modifiers likely exist). Consumer change is then trivial: coated Monster nodes project ~0 HP loss + full rewards in the path DP. Also revisit Fur Coat's catalog 5.5 upward once routable. |
| Pael's Wing: sacrifice action on card-reward screens | relic edge case | 2026-07-25 (owner): adds a sacrifice option to card rewards -- every 2 sacrifices = a relic; STRICTLY better than skip, and with our skip rate it's relic income. RESOLVED TO A FORK ITEM 2026-07-25: the bot HAS held it (2 runs; the earlier 'never held' read was a bad search, record intact) and the card_reward payload with it held shows only can_skip+cards -- the mod does NOT expose the sacrifice option or action at all. Policy can't fix this; fork ask #3: serialize the sacrifice button + action on card-reward screens. Boon stays 2.5 until the fork lands, then wire skip->sacrifice and restore 4.5+. |
| Foul-potion merchant throw | RESOLVED 2026-07-25 (no fork needed) | Live probe A/B with the owner (savescum loop on the win seed): the throw works via plain use_potion but ONLY on the SHOPKEEPER screen -- which our own /state polling auto-advances past (the re-render side effect). Fixed in the orchestrator: throws fire BLIND between the accepted shop travel and the next poll (both Fouls landed live, +200g, merchant dialogue played). Foul keep-rank restored to 3; late-act-3 claim guard kept (merchant reachability still real) but config-gated. The polling side effect is now implicated in THREE mechanisms (flicker, phantom maps, this) -- raises the priority of mod-side passive /state (fork ask #1). CORNER CASE filed 2026-07-30 (owner): a shop can hide inside a '?' -- the throw hook keys on choosing a Shop-typed node, so a ?-resolved shop misses the shopkeeper window entirely. Candidate fix once the base case validates: also fire blind throws after choosing an Unknown node while Fouls are held (non-shop resolutions just eat one harmless 'cannot be used' error each); or wait for fork ask #1, which retires the whole timing dance. ALSO PENDING: the 2026-07-29 delay-timed retry itself is not yet live-validated (batch b0kpzar7l fired at accept-instant and errored; the fix shipped after). |
| THE POTION PASS (owed; relic pass done, potions never) | P1 pass | data/potion_notes.json SEEDED 2026-08-12 (Stable Serum: drink end-of-good-turn on elites/bosses, NEVER round-1 buff-lane; completely useless under Runic Pyramid -- owner decode, needs a Pyramid veto + end-of-turn lane when the pass lands). Elevated 2026-07-29 (owner). Scope: (1) the owner's explicit potion VALUE ORDERING exercise (banked by owner -- informs the discard ladder, full-belt deploys, Future-of-Potions sacrifices, and shop buys in one sweep); (2) a potions catalog file (like relic_notes) with per-potion class/timing notes -- current classes are name/text-heuristic buckets; (3) protected-potion veto (Entropic Brew, Fairy, Gigantification, Orobic Acid, Ambergris -- filed 2026-07-21); (4) rollout relic/potion terms feed from the same data (boss-model work). Existing lanes stay until the pass replaces them. |
| Restlessness x Runic Pyramid (owner, deferred 2026-08-10) | P4/multiturn | Restlessness now held until the hand empties (cfb01e8) -- correct EXCEPT under Runic Pyramid ('no longer discard your Hand'), where the right move flips to playing it as a hand-space clear. Pyramid IS in the pool (32 logged runs, held in 2; relic_notes RUNIC_PYRAMID already flags it as an end-of-turn-semantics rules change needing bespoke handling). Fix needs hand-space valuation -- likely the multiturn planner; until then Pyramid runs just hold the card. Meta-lesson: the original code comment claimed the relic was 'not in the seen pool' WITHOUT checking the logs (owner caught it watching batches) -- pool claims must be grepped, never assumed. |
| Insatiable 'Sandpit' death_timer=4 makes every forecast a 0% loss (found 2026-08-10 in the slow-node hunt) | forecast/OWNER Q | Bestiary status 'In 4 turns, you will be eaten and die' harvests as death_timer=4, and the rollout prices that as auto-loss at sim turn 4 from FIGHT START -- yet run 20260809-230646 beat The Insatiable live (win 0.0 forecast, actual win). Also unmodeled and probably load-bearing: its Demise power (boss loses 9 HP at end of ITS turn -- Queen has it too), which shortens the real clock. ANSWERED same day (owner, THIRD telling of this mechanic -- which triggered the canonical-decode-file fix): Sandpit is applied AFTER turn 1; 6 seeded Frantic Escape status cards extend it +1 turn each at escalating cost (1,2,3...); Demise is OUR Powdered Demise potion, not innate. Fixed: _SANDPIT_TIMER_PAD=4 now pads BOTH the closed form and the rollout (the rollout raced the raw 4). Decode recorded in data/enemy_notes.json -- the new canonical home for owner-decoded mechanics (CLAUDE.md points at it) so compactions stop eating them. |
| **FORK SESSION 2026-08-10 (owner-approved) -- 3 of 4 asks landed, mod BUILT, awaiting install at next game restart** | fork/infra | Mod commit 40cbba4 + bot 12b00d3. (a) abandon_run action: decompile showed RunManager.Abandon() -> AbandonInternal() is a DIRECT teardown that never enters the ActionQueueSet, so it can recover a wedged run; batch loop now tries it on any non-completed run and continues from the menu (pre-fork mod errors -> halts as before; hard engine freezes may still need manual force-close). (b) engine liveness in /state: process/physics frames + ActionQueueSet.IsEmpty/NextActionId + passive_state flag. (c) PASSIVE /state -- root cause of fork ask #1 FOUND: the state builder itself called ForceClick/OpenInventory on every poll (chest, shop, fake merchant); at 0.15s cadence a click barrage and the prime re-entrancy suspect for the treasure wedge + shopkeeper auto-advance family. GET no longer mutates; new open_chest / open_shop_inventory actions; bot opens gently (8-poll dwell, 3 attempts). (d) Fork ask #4 (KD textless options) is STALE: tape 20260810-024702 shows the KD pick as a fully-labeled card_select and the bot chose Disintegration via the owner's _DEBUFF_PREFERENCE table -- no mod work needed. INSTALL: copy external/STS2MCP/out/STS2_MCP/STS2_MCP.dll to game mods/ while the game is closed (manifest unchanged). Post-install watch: shop/treasure flows on the new contract, first wedge -> does abandon-recovery fire? Foul-throw can later become aimed (stable shopkeeper screen). |
| Audit re-run 2026-08-10 (fresh 60-run corpus, 2,974 turns) | P2/§5-C | HP within ±2 steady at 94%. CONFIRMED DRAINED: Bygone Effigy + Spiny Toad buckets gone (Slow-display fix validated at scale). NEW top buckets, all one-turn-planner side: (1) WG hp n=24 avg 17.2 over-predicted -- likely pricing an attack during the do-nothing 'preparing' knockdown turn (phase does nothing, owner decode); damage channel shows the mirror (n=12 avg 28.7 damage projected into the untargetable shell); (2) Axebot damage n=14 avg 26 LESS -- plans project damage through the Stock respawn full-heal; (3) chronic small over-block tail (PLATING/STRENGTH rows, 2-7 HP) = conservative bias, low priority. Full output: scratchpad audit_20260810.txt (session) -- re-derive with scripts/predict_audit.py. |
| Resume-load wedge (new subclass, 1 instance, fuzz session 2026-08-10) | infra | Run 20260810-201707 f38: save_and_quit -> menu -> Continue -> the fight LOAD hung -- /state served bare 'monster' husks (no battle/player/ENGINE dict) for 60+ ticks -> C5 -> abandon-recovery continued the batch (owner saw it as a stall-then-death: the abandon kills the player, reads as a death screen). 21 savescums that run; 20 clean. Note the diagnostic: the engine liveness dict VANISHING from /state is itself a wedge signature (the builder takes an early path). Mitigated: the rail no longer savescums fights with zero fuzzed plays (nothing to rewind -- the f38 scum was pointless; hp-floor trips at fight entry now just hand to normal policy). Watch recurrence on legitimate savescums. |
| Fuzz session #1 RESULTS (2026-08-10, 5 runs, 1319 plays, 1270 paired) | P4-prep | Finds: (1) Plating-as-immediate-block REAL BUG, fixed 4473bbd; (2) card-text rider contamination class, harvest fixed d5921b8; (3) pointless-savescum rail flaw, fixed 8875cb5; (4) resume-load wedge subclass (PLAN row). Remaining CHECK rows are HARNESS ARTIFACTS: PRED is the NAIVE parse, so conditional cards the planner already models correctly flag anyway (Pact's End pile gate -18, Fiend Fire per-exhaust -7.5, Forgotten Ritual exhaust gate -4, Pyre per-turn power, Burning Pact choice-screen frame, strength-context attack noise +-1-3). PRED now carries cond= so v1 audits self-label them. FUZZ V2 (the real payoff): log the PLANNER's own single-play expectation (EnemySim preview) instead of the naive parse -- then divergence indicts the actual model, not the parse. |
| Game crash class (WinError 10054): 4 instances, 2 on f17 boss floor | infra | #3 and #4 both mid-run on 2026-08-10 (#4 at f17 act-1 boss = WG floor; #3 at run 13 mid-act). Recovery pattern proven and now routine: dead-process check -> Steam relaunch (rungameid/2868840) -> port wait -> resume train (bot Continues the crashed run). Watch whether crashes cluster on WG-knockdown floors -- if yes this is the freeze class escalating to a process kill and belongs to the same fork/decompile investigation. |
| Mod REST server death (10061, game alive) is now a repeating class: 2 instances in 2 days | infra/fork | 2026-08-12 run 38 (bht41z4a2 predecessor) and 2026-08-12 run 14 (bgu417enr): GET refused with the game process healthy -- previously seen only as a wedge CONSEQUENCE, now standalone mid-run. Recovery routine (force-close + Steam relaunch + resume; bot Continues the run). FORK SESSION CANDIDATE: server lifetime under long sessions -- heartbeat/self-restart for the HttpListener, or diagnose what kills it (exception on a handler thread?). ~1 per 50 runs currently: below wedge-class priority, above ignore. |
| **GRADUATION CRITERION A0 -> A1 (owner 2026-08-13)** | goal | Human baselines from the StS-tracker site (dedicated-player population): per-act survival 58.7% / 61.5% / 65.5% (of runs REACHING each act), overall winrate just shy of ~20%; top humans 90%+ at A10 (heavy power-law tail). Hardest bosses for humans: AEONGLASS and KNOWLEDGE DEMON -- matching our top killers (KD #1, Aeonglass #3), i.e. our wall is the game's wall. CRITERION: ~20% A0 winrate with no major queue items outstanding -> consider A1. Bot profile at criterion-setting (148 full-stack runs): overall 8.8%; per-act survival 76% / 48% / 24% -- BETTER than average humans in act 1, behind in act 2, far behind in act 3: the gap steepens with fight complexity, consistent with the multiturn thesis (piloting depth, not fundamentals). |
| Relic Trader residual-value lane (owner design 2026-08-13) | events | The event offers 3 fixed give->get pairs; the generic Spirebird scorer handles it today but prices the GIVEN relic at acquisition value. Owner: give-side should be RESIDUAL -- 'Upon pickup' relics are spent (residual 0, near-free trades), per-run/out-of-combat relics decay by act, combat relics keep full value. Tier 1 (text-detectable 'Upon pickup' residual-zero) is mechanical; tier 2 needs per-relic assessment (relic_notes._RELIC_TRADER_DESIGN). |
| **Draw-vs-play energy judgment (PROMOTED from parked 'draw-early DFS preference'; KD A/B 2026-08-14 quantified it: 25-90 dmg per burst turn)** | P4/planner top | Owner rule (verbatim nuance): NOT 'always draw first' -- 'Is my hand good value for the amount of energy I have, or is it worth spending X to draw into my deck?' At 3 energy drawing can waste energy better spent on good in-hand cards; at 6 energy (Pyre engines) it is 'decently safe to glance and evaluate whether it is possible to spend all energy on non-strike/defends, and draw if not.' Encodable shape: energy surplus after the hand's non-basic value plays > 0 -> sequence draws/tutors EARLY (surplus converts to options); else draws compete normally. Evidence: owner's recorded r5/r6 burst turns (111/137 dealt) vs planner static plans (85/45) from identical snapshots -- the delta is draw-first sequencing + replan chaining. Owner tape: logs/manual/kd_ab_rep2. Also queued from the same anatomy: Rampage per-play growth parse audit; five-skill Pen Nib variant trigger audit. |
| **Test Subject P3 burst_window mode (wiki pass DONE 2026-08-15, 040f97b)** | planner/mode table, OWNER REVIEW | Decode verified + banked (data/enemy_notes.json); harvest de-fragmented (specimen-suffix canonicalization, 160 fights consolidated). Remaining planner work: (1) burst_window mode flavor — P3 Nemesis gains Intangible 1 at the end of every OTHER turn, so gate ATTACK spend onto non-intangible turns and dump block/setup into intangible ones (inverse of defend_deadline; intangible period 2 rides UNDER the 3-move cycle, LCM 6 — read the live Intangible status, don't infer parity); (2) phase-kill debuff-waste guard — ALL statuses clear on revive, so Vuln/Weak invested into a dying body is wasted (generalizes to Phrog-class staged bodies); (3) P1 Enrage skill tax + P2 Painful Stabs unblocked-hit tax. FIGHT_MODE_TABLE row stays TBD until owner reviews the mode design. |
| **Act-3 A/B rep 1 rule candidates (2026-08-15, seed BKF0WL1V3E; owner commentary + alignment in logs/manual/act3_ab_rep1/)** | events/map/draft | Same-screen Vakuu disagreement (bot: Earring on static 5.5; owner: Music Box — 'Earring's turn-1 impact is hard to justify with +3 energy from Pyre') = 3rd appearance of the energy-curve principle. SHIPPED phase 1 (3bb5791): energy_sat_* discount on energy_source boons in the ancients pass, Vakuu screen is the regression test. Remaining consumers of the same statistic: Mad Science Chaos-vs-Wisdom flip (row below), graduating the binary draw penalty_draw_no_energy to scaled, shop energy relics (WAR-based today — needs care not to fight empirical values). Other candidates from the tape, unbuilt: (1) relic-conditional PATHING (owner diverted left for double shop BECAUSE Music Box rewards optionality; path_value has no relic term); (2) ?-node value rising as the deck solidifies (owner: '? events in StS2 are generally quite good... deck already reasonably solid, I'd rather see the event than one hallway fight' — a deck-strength discount on score_monster, not a ?-boost); (3) boss-slate-aware drafting (Barricade at the KD reward priced vs the act-3 boss DISTRIBUTION, not the revealed boss); (4) innate-opener combo drafting (Juggling+ taken because Innate Mad Science makes it a free-T1 power — no innate-sequencing term exists). Convergent (no work): rest-handler Hatch, Armaments __unupgraded need, pre-boss rest DFS forecast (est loss 87 vs Queen — accurate). Direct Queen comparison pending: owner finishes the parked run vs bot's f48 loss. |
| **Setup-then-burst mode — phases A+B SHIPPED 38ca162 (owner answers 2026-08-18: 15hp ABSOLUTE floor + risky-setup death sentinel in batch_summary; bosses only, KD+Queen setup_burst rows to start; looser flip eta<=2 + half-dent hand check). Phase C (hold damage into next-turn vuln/Str windows) deferred to the multi-turn sim; extending setup_burst to more bosses goes through snapshot A/Bs per the owner's methodology steer.** | P4/planner top | Evidence 2-for-2: KD A/B (owner burst turns 111/137 vs planner 85/45 from IDENTICAL snapshots), Queen (owner ~304 in one turn, r4->r5 327->23; bot died at the same boss/seed). The template: bank cheap turns (powers, tutors, exhaust-engine setup, draws) while pressure is low, then concentrate everything into one window. Proposed triggers, all from existing machinery: **(A) setup-turn detector** — script-known fight AND this turn's incoming (incoming_by_turn) is within comfortable block reach AND kill_eta_p25 > 2 -> fight_plan="setup": power/tutor/draw credit UP, small immediate-damage credit DOWN (mirror of race; the WG dead-turn Defends and owner's Pen Nib skill-pumping live here too). **(B) burst-flip** — when eta_p25 with banked multipliers (Str, vuln up, growth_banked, energy surplus) drops <= ~1.5, flip to "unload": race scoring + draw/tutor-first sequencing (energy-surplus judgment already shipped does the in-turn ordering). **(C) hold-damage nuance (later)** — defer attacks into a next-turn vuln/Str window; needs the multi-turn sim, folds in the strength-horizon backlog item. OWNER QUESTIONS: (1) setup-turn read at LOW player HP — block-first override threshold? (2) bosses only, or hallway fights with known scripts too? (3) flip threshold eta<=1 strict vs <=2 with a hand-quality check? Implementation phase A+B is mode-table + one new score branch; C is deferred. |
| **Tutor valuation — owner design shape (2026-08-20, audit #2 item 18 thread)** | planner design | Full implementation needs SPECULATIVE AWARENESS: for each discard-pile target, ask 'if I added this card to my hand, what could I do with it?' -- plus scheduling awareness (tutors EARLY rather than late; the energy-surplus judgment covers ordering but not target valuation). Owner examples: Neow's Lament -> Bloodletting + Battle Trance is a direct tempo play; pull a good 0-COST card when out of energy. 'Complicated' -- owner. Cheap first step candidate: when a tutor's select screen is live, the select-best heuristic could dry-run the DFS with each candidate added to hand and pick the max (bounded: top-k candidates by draft score). MECHANICAL NOTE banked: Hologram-class retrieval ('put into your hand', no 'draw' wording) is IMMUNE to Battle Trance/Fiddle no-draw riders -- textparse confirms fx.draw=0 for these, so the machinery is accidentally correct; future retrieval parsing must NEVER map put-into-hand to fx.draw. |
| Kill-reliability test for kill-conditional riders (owner, audit item 102 follow-up, 2026-08-22) | planner, Defect-era | Sunder-class 'if this kills, gain X' riders currently parse to ZERO (the unconditional icon-run credit was 3 phantom energy/play -- fixed conservative). Owner: with no pre-verified kill the card's potential is 'greatly reduced'; bank a MINOR check for the Defect pass -- the DFS already computes per-plan lethality (Feed's on_fatal machinery), so kill-conditional energy/star refunds could credit ONLY inside plans where the target dies to planned damage. Same lane as Knockout Blow's 5-star kill rider. |
| Mad Science variant-conditional refinements | events/draft | 2026-07-29 owner brief encoded (catalog + catalog-first + smith premium); remaining: (1) Chaos-vs-Wisdom head-to-head should flip to Wisdom in energy-rich decks; (2) the designed card is ONE id with many texts -- draft-tag providers should be variant-conditional (Curious = big draft bonus to powers, Wisdom = draw-needs-energy, Expertise = str/dex source), needs a description-conditional provider mechanism in drafttags; (3) Choking/Chaos trigger texts parse to ~nothing in the planner (conditional) -- underplayed once designed. |
| Per-boss observed loss for the pre-boss campfire and the map DP (2026-09-29, from the Kaiser Crab tally) | P2/owner call | Kaiser Crab is the act-2 outlier at A0 (20/34 = 59% vs KD 86%, Insatiable 81%); entry < 50 HP = 0/4, losses enter at 58 vs wins 71. The rest rule and `est_boss_loss` use the POOLED survivor-only p75 (41, combat_stats.json built 07-12 from 345 runs) x 1.1, so the bot smiths at 46-57 HP before a boss whose own survivor p75 is 46-53 with a 41% death rate (Waterfall similar, 47-50). Candidate: `combat_stats` keyed by boss name (fallback pooled when n < ~15), rebuilt from the fixed-code era, used by both callers; a boss-head P(win) (section 9) is the fuller answer. Costs upgrades at some campfires (arm v6 lesson) -- run as its own arm after the definitive A0 read, not tuned in. **Same shape for hallways (2026-09-30):** `monster` loss is one pooled mean (9.7) across acts, but act-2 packs run far above it -- Spiny Toad mean 18.4 / p75 29 / 37% of fights cost >= 25 (n=52), Hunter Killer 18.9 / 28 / 29% (n=43), Myte 15.1; act-2 hallway deaths x4 in batches 3-4 were all upstream bleeds (Tunneler 35 + Obscura 38 in one run). Neither pack hides a mechanic (Thorns/Empower/7x3 are modeled): per-act (or per-act-tier) hallway stats would reprice act-2 monster nodes vs events/campfires. **Refresh 2026-10-02 (A0+A1 since 09-20, entry HP at the boss):** act-1 bosses <60% 50/86 (58%), 60-80% 229/323 (71%), 80%+ 222/274 (81%); act-2 <60% 19/53 (36%), 60-80% 104/158 (66%), 80%+ 179/217 (82%). Kaiser <60 HP ~1/3 vs >=60 ~3/4; KD 80%+ 82%/77% (A0/A1) vs 60-80% 58%/47%. Confounded by deck strength (healthy runs are stronger runs), and arm v6's stricter rests went 0/10 by costing upgrades -- so the clean test is a 40-run arm of 'rest below ~80% before act-1/2 bosses' (the final-boss rule, 0.90, already shipped 2026-10-02). Elite entry, same corpus: act-2/3 elite deaths ~1% at >=80% HP vs 7-10% below (A1 act-3 1/91 vs 7/73) -- the dormant elite_entry_min_hp_pct_act2/3 knobs are the arm for it. **OWNER GO 2026-10-02:** run the act-1/2 boss-rest arm (config/experiment_boss_rest.toml, boss_rest_below_hp_pct 0.80) as the next 40-run batch at A1, then move to A2. **ARM RESULT 2026-10-03: 10/39 = 25.6% vs control 34/175 = 19.4% (+6.2pp, z 0.87)** -- act-1/2 boss wins 84%/77% vs 73%/69%, reach act-3 boss 51% vs 33%, act-3 boss 50% vs 59% (9.4 vs 11.9 upgrades). Promote? owner's call (recommend yes). **PROMOTED 2026-10-03 (owner).** **A2 batch 1: 9/40 (22.5%)** -- on par with A1; A2's 80% start HP shows up only as extra act-1 elite deaths. **A2 act-1 elite entry proposal (2026-10-03, owner call):** act-1 elite death rate by entry HP -- A0 <60% 10.5% (38 fights) / 60-75% 2.1% / 75%+ 2.1%; A1 10.9% / 0.9% / 3.7%; A2 23.1% (13) / 7.0% (43) / 3.4% (58). Terror Eel at A2 4/21 deaths (19%) vs 3-4% at A0/A1 with an unchanged 140-HP Eel: A2's 64-HP start puts floor-7 elites at ~45-57 HP vs ~70 at A0. The live gate (elite_entry_min_hp_pct 0.50 = 40/80) admits them. Candidate arm: act-1 elite entry floor 0.60-0.65 (costs early relics; n is small). **A2 final 25/107 = 23.4%; owner GO -> A3 (25% less gold) from 2026-10-03.** Kaiser A2 11/23 (48%) is the new watch item. |
| Treasure-claim wedge is relic-agnostic: 19 halts across the corpus (2026-09-29 tally) | P2/infra, owner call | After `claim_treasure_relic` the treasure block vanishes and the engine sits in phase=to_run; the stall rail aborts after 60 ticks and the recovery ABANDONS the run (batch 4 run 10 lost at act-3 floor 41 this way). 16 different relics over 19 cases (Captain's Wheel x3, Lasting Candy x2, the rest singles), so it is a claim-transition race, not a relic. Candidate recovery: on a treasure wedge try `save_and_quit` + Continue first (the fork primitive restores the room; the chest relic is already rolled, so no C3 concern -- owner to confirm) and only abandon if that fails; mod-side, look at what the claim handler awaits. |
| Waterfall Giant soft eruption budget (2026-09-30, be33aa1 -> gated off in the follow-up) | P4/A-B | The kill-turn accounting (pending blast minus an 8-block hand charged on the kill turn) stays on: 13/14 era WG deaths were kills the blast finished. The SOFT term (HP below next stack - 8 charged at the scarcity rate while the Giant lives) ran in batches 5-6: 11 fights, 5 won (45%) vs 32/46 (70%) before, fights 10.8 rounds vs 8.8, final stacks up to 54 -- consistent with blocking stretching races the deck cannot win while the stack grows 3/turn. n=11 and losses entered at 60 HP vs wins' 77, so not conclusive; `eruption_budget_mult` (default 0) reinstates it at 1.0 for an A/B. **Calibration 2026-09-30 (later):** the 32 pre-model wins killed at mean +5 HP over the blast, but 12 of them killed BELOW it and lived on a blast-turn block averaging 15 (range 6-69); every loss with margin < -20 died. The kill-turn wall at expected block 8 refused those coin-flip kills (batch 7 WG 0/3 at 56-62 entries; post-model 5/14). Recalibrated: `eruption_expected_block` 8 -> 15, and the blast's remainder is charged as HP loss but no longer trips the death wall. Owner-reviewable; batch 8 measures it. |
| Early-elite deaths are a Phrog Parasite problem (2026-09-30, era act-1 elite table) | P2/owner call | Act-1 elites, era: Skulking 0 deaths/154, Gardener 0/143, Effigy 1/133, Byrdonis 1/108, Terror Eel 4/153 -- and **Phrog Parasite 8/130**, five of them full-HP starter decks (11-13 cards) at floors 7-8. The tape: the 61-HP Phrog casts 3 Infection status cards every other turn, a starter deck needs ~5 turns to kill it, and the four Wrigglers it spawns (17-20 HP, +2 Str per Buff) then meet a deck that is a third Infections. The map DP cannot see WHICH elite a node holds, so the only routing lever is the deck-size floor at floors <= 8 (the withdrawn arm v4 applied its floor act-wide at 13 and overshot to 2/21). Narrow arm to consider: elite floor at deck < 12 only for act-1 floors <= 8. **Refresh 2026-10-01 (518 promoted-key runs):** floor<=8 elites, deck<=12: 7/64 deaths (10.9%) vs deck>12: 6/234 (2.6%); early elite deaths are 13/518 runs (2.5%) in total. Rough EV of the floor: ~7 deaths avoided (x ~0.18 win each) vs ~57 forgone elite relics (x ~1pp) = about +0.7 wins per 518 runs (+0.1pp) -- positive but small; not a lever for the 20% read. |
| Periodic game relaunch inside long batches (2026-09-29) | P2/ops | Second long-session failure: 09-03 connection reset mid-run, 09-29 hang at floor 24 after ~3 h / 35 runs at 3x (process alive, not responding, working set 13.3 GB -- a leak). The batch stops on C5 because abandon recovery needs a live server. Candidate: the orchestrator relaunches the game every N runs (steam_appid procedure already proven) or when the game's working set crosses a threshold; the interrupted run resumes via Continue.  Fourth failure 2026-10-01 at ~4 h / 23 runs on a fresh session: relaunch every ~15-20 runs inside a batch.  Fifth failure 2026-10-01: crash ~13 runs into a session that was itself a scheduled relaunch -- crashes now land at 13-23 runs regardless of uptime, so a fixed cadence alone will not prevent them. The real fix is in the orchestrator: on a connection-reset C5, relaunch the game (steam_appid procedure) and resume via Continue instead of stopping the batch -- every crash so far has been recoverable that way by hand. |
| Matriarch wake bar per forfeited turn (2026-09-28, sleeper v4 ce7359d) | P4/owner call | `w_wake_sleeper` (−16, the 08-06 "per-turn threat" sizing) now charges once per forfeited free turn (Asleep stacks−1) and a paid wake turn earns plain damage credit only. Consequence: at 3 stacks the bar is ~32 raw damage, so the 08-06 "bursts (25+) clear it" line no longer holds on round 1 (a 32-Bludgeon still clears; a 22 wake — one of the era's wins — would hold). Owner to confirm the per-turn unit or set a round-1 discount. Batch 3 onward carries it; watch the Matriarch row of the act-1 boss tally (45% → ?). |
| Safe automation of Timeline epoch *reveals* | P2 fork candidate | mod automates timeline advance/back + queued unlock screens, but deliberately refuses to force-reveal "Obtained" epochs ("invalid unlock path"); decompile the reveal flow to see if a safe replication exists, else it stays a rare owner click |
| **Mod build provenance — build the FORK, not upstream** | infra/done | 2026-06-23: rebuilding the v0.107.1 mod from upstream `Gennadiyev/STS2MCP` silently dropped the fork's `player.deck` (+ `set_time_scale`/`set_ascension`/`actions_disabled`) → capability drafting **and** the elite gate no-op'd for a whole batch (deck = `None`, so the b3b7593yb results don't test §5-C). Fixed: build from `cicero225/STS2MCP` + re-apply `patches/STS2MCP-newbuild-fix.patch`; CLAUDE.md + patches/README corrected. **Re-batch bxtd5uum8 (2026-06-24) confirmed the fix: act-reach 1.0→1.8 (max 3 — two Act-3 runs, one reaching the Aeonglass boss), relics 4.0→7.0, elites 0.2→0.6; still 0/5 wins but the wall moved from Act-1 boss to Act 2/3.** |
| **Bestiary rebuild is destructive; its source logs live only on the OLD machine** | infra/data | 2026-07-08: `build_bestiary.py` rebuilds `data/bestiary.json` from scratch off `logs/runs/` — running it on the new machine (only 10 local runs; `logs/` is gitignored and didn't transfer) silently replaced the committed 75-enemy/110-run bestiary with a 46-enemy one (caught + reverted via git). **Don't rebuild here** until either (a) the old machine's `logs/` (+ `backups/profile_snapshots/`, accessible ~2026-07-10) is copied over, or (b) the script learns to **merge** new harvests into the existing file. Same trip: fetch the post-unlock profile snapshot (restores custom mode + Undergrowth). |
| **Card descriptions render ENERGY as icon tokens, not text** | infra/parsing | 2026-06-26: the game writes gained energy as `[<char>_energy_icon.png]` tokens, not "N Energy" (Luminesce = "Retain. Gain `[ironclad_energy_icon.png][ironclad_energy_icon.png]`. Exhaust."). The text-only `_ENERGY` regex parsed these to 0 → **Luminesce / Bloodletting / Offering all read as 0-value and went unplayed** (owner-caught). Fixed: `textparse` now counts per-char energy icons after "Gain". Trace scope-check: **only energy** is iconized (damage/block/draw are plain text; `star_icon` is a separate resource). **Watch:** if a future card iconizes another value (or stars become relevant), the same text-regex blind spot applies — grep traces for `\[[a-z_]+\.png\]` when a card mysteriously reads as 0-value. |
| **Batch resilience — one unclean run kills the whole batch; no abandon-to-menu recovery** | infra | 2026-06-25: `play` halts the batch on any non-`completed` run ([cli.py:160](sts2bot/cli.py)). A run that *stalls* (60-tick timeout) leaves the game mid-run, so the next run can't start fresh either — the batch is stuck until a manual kill+restart. Root trigger seen: a **rare treasure-claim glitch** — `ClaimTreasureRelic` occasionally doesn't register (relic stays listed on an *open* chest; hit once on a Bellows chest, Act 2, 4x), and the very next treasures claimed fine, so it's isolated/transient, **not** speed-systematic. **RECURRENCE 2026-08-01 (f41, Captain's Wheel): the treasure-claim transient escalated to the BLACK SCREEN softlock (2nd black-screen instance) — and post-stall, API claims returned 'ok' into the black screen with /state still reporting a healthy treasure payload. Same API-ok-into-dead-UI signature as the enchant wedge. Sharpened fork ask: the mod should RE-RESOLVE UI element references per action (not cache them) and/or report a scene-tree liveness field so the bot can distinguish wedged from healthy.** Lesson learned the hard way: the bot must **never proceed past an unclaimed chest** — doing so leaves the treasure node unresolved, freezes map nav, and black-screen-**softlocks** the game (that "recovery" was reverted; original keeps claiming → clean stall-abort). Proper fix: orchestrator **abandons the run to the main menu on a stall-abort** so the batch self-recovers; optionally a watchdog re-claim/dwell on transitional treasure `message`. Bigger change — deferred. **Update (2026-06-25, batch bdbfpnckb run 4): trigger pinpointed = a `War Paint` treasure on a `?` (Unknown) map node.** Trace: arrive at the `?`-node treasure (relics already empty — War Paint auto-applies its 2 random Skill upgrades), bot `proceed`s, next state is the map → **frozen** (40+ identical `choose_map_node`, state never advances). Live capture: `current_position` stuck on the Unknown node (row 13) with two valid `next_options` (Monster/Elite at row 14) it won't take, and **3 cards now `is_upgraded`** (War Paint applied). No API-visible pending screen — the game is internally stuck after the auto-applied upgrade, so the bot's valid `choose_map_node` no-ops. **Deterministic repro seed `ZWSK88UNQN`** (Ironclad A0, config 379cb9c6744b; owner read it off the in-game seed display). Likely a *mod/game* bug (`?`-node + auto-pickup relic not finalizing the node); seeded repro + decompile of the `?`-node→treasure flow is the path. **2nd instance (2026-06-26, batch bg3h3mw5w run 20, Act 2 floor 27): an enchant card-select hang** — `NDeckEnchantSelectScreen` "Choose 3 cards to Enchant": the bot selects 3 → `confirm_selection` (can_confirm=true) → the screen **resets to 0 instead of closing**, looping select→confirm to the abort. The cards expose no `selected` field, so the select/confirm isn't resolving — the enchant screen needs its resolution understood (interactive 1x test or mod look). Confirms the meta-point: **rare per-screen hangs will keep killing batches one at a time** (treasure, now enchant, more to come) — the durable fix is the abandon-to-menu batch-resilience above, higher-leverage than whack-a-mole per screen.  **3rd instance (2026-07-29, seed Q9FF8Z6WPR, f17 WG turn 6): mid-combat card-resolution FREEZE at the Waterfall Giant knockdown -- Defends stuck mid-flight above the field, sentinel infinity on the HP bar, state reports is_play_phase=true/actions enabled while the engine is wedged (end_turn 'ok' into the void; owner watched the button grey out with no effect). Both the original batch and a re-attach aborted correctly on the stall rail. Correlation with the new eruption block-stacking play unknown. Recovery = force-close + Continue (freeze state isn't saved). The abandon-to-menu batch-resilience fix remains the durable answer.** **6th instance (2026-08-02, owner screenshot): the mid-combat card-resolution freeze extends beyond WG -- KAISER CRAB, turn 4, a Defend frozen mid-flight above the field, 2/4 energy, engine wedged while the fight UI stays rendered. The class is now boss-agnostic; with the settle-dwell family landing on selection/treasure screens, in-combat card RESOLUTION remains the one surface without a pacing guard (cards are submitted on consecutive polls at 4x). Candidate mitigation if instances continue: a post-play settle poll in combat when an animation-heavy resolution is in flight. Recovery unchanged: force-close + Continue (freeze state isn't saved).** **ROOT-CAUSED 2026-08-02 (instances #6a/#6b, seed 373PFAE7EE, f33 Kaiser Crab r4 — the freeze reproduced DETERMINISTICALLY twice, giving a controlled experiment): the trigger play was Pillage (with a Replay 1 enchant) killing Rocket — a multi-second double draw-until-non-attack + death-animation chain. The tape shows the bot re-sending plays into it (5 Defend sends with 3 in hand) plus end-turn, replanning against stale API state every 0.15s poll. The owner then hand-replayed the bot's EXACT four-turn sequence from Continue: no freeze — the game script is exonerated; the wedge is OUR input pressure during long resolutions, the in-combat analog of the treasure/enchant hammering. Fix 5260dbc: action-settle guard — after any combat action (play/potion/end-turn) the bot WAITs until the state visibly changes (hand/energy/HP/enemies/potions/phase signature), with a 40-poll fall-through so a silently-failed action can't soft-lock. This closes the 'one surface without a pacing guard' gap named above; whether WG-knockdown instances #3/#4 were the same mechanism is unproven but now plausible (both involve card queues frozen mid-flight during heavy resolutions).** **GUARD v1 FAILED LIVE, v2 SHIPPED (2026-08-02, instance #6c — the savescum validation run froze identically): v1 released on the FIRST state change, but the Pillage chain mutates state every 0.15s poll (HP ticks, draws landing one by one), so v1 released mid-animation and still pushed 3 Defends + end-turn into the resolution — freeze now 3-for-3 under bot pacing vs 0-for-1 under the owner's hand replay of the same sequence (a beautifully controlled experiment, thanks to the deterministic savescum repro). v2 inverts the semantics to QUIESCENCE: after any combat action, nothing is sent until the state signature has been identical for action_quiesce_polls (3) consecutive polls — 'the resolution finished', not 'something changed' — scoped to the action→settled window (fight-start sends were never implicated), same 40-hold fall-through. VALIDATED LIVE same day (run 20260802-161959, savescum replay #2): the bot crossed the exact freeze beat — Pillage kill, 4 quiesce holds through the tick-chain, end-turn only after the board went quiet — the crab's scripted move ran cleanly and the bot KILLED Kaiser Crab r7. Bonus: the post-draw replan played 1 Defend + end-turn instead of the blind [Defend x3] script, the owner's 'reassess after card draw' point falling out of the guard for free. The mid-combat resolution class is mitigated bot-side; the WG-knockdown variants (#3/#4) get their test whenever WG next appears in a batch.** **4th instance (2026-07-30, batch b8xzsljdf run 6, f17 act-1 boss, phase=to_run): CONFIRMED same WG-knockdown freeze -- owner screenshot shows the identical presentation to #3 (card queue frozen mid-flight, a stack of identical cards behind a resolving Taunt+, sentinel INFINITY on the WG HP bar, End Turn lit but dead, turn 6). WG is now 2-for-2 on the mid-combat subclass. New downstream fact: left frozen long enough the mod's REST server dies outright (WinError 10061) while the game process stays Windows-responsive -- #3's server kept serving during its freeze, so the server death is a CONSEQUENCE of the wedge, not a separate failure. The tripled stall leash (180 ticks) ran its course before C5 -- correct behavior. Fork-session asks sharpened: (a) mod-side heartbeat that detects the wedged engine, (b) decompile the WG knockdown card-resolution path; the frozen identical-card queue suggests a replay/duplication interaction jamming the resolution stack.** **ENCHANT HANG REFINED (2026-08-01, owner screenshot + owner correction, batch 51476 f3): the enchant flow shows a before->after preview with a checkmark, and it has resolved correctly through confirm_selection dozens of times ('worked any number of times' -- owner) -- so the hang is an INTERMITTENT UI/API DESYNC, not a structural gap: the API reported '1/1 selected' and ok'd confirms while the real screen sat on the preview untouched. Two instances ever (2026-06-26, 2026-08-01), both at 4x -- suspect a race in the mod's screen model during the select->preview transition, same transient family as the treasure-claim glitch. The mod server again died during the wedge (instance-#4 downstream pattern). ROOT-CAUSED same day (owner live debugging: his own confirm click ALSO failed; back -> re-select -> confirm worked): the wedge was SELF-INFLICTED -- the June fix cleared pick-tracking on preview_showing, so a single transient confirm failure triggered a re-select that toggled the game's internal selection OFF under the live preview. Fixed eb92a1b: never clear tracking on-screen; re-confirm x4 then CancelSelection reset (the owner's recovery, mechanized). FULLY SOLVED (2026-08-01, three-experiment live dissection on the owner's quit-scum repro): zero-gap confirm resolved fine; mid-poll resolved fine; 4x resolved fine -- then the wedged run's RESULT LOG confessed: TWO select actions back to back ('choose Taunt' + 'select best Taunt', both 'Toggling card selection'). FORCED single-pick grids (no cancel/skip/confirm pre-selection) misroute poll 1 into the resolves-on-select branch, which never recorded its pick; poll 2's pick-N path re-selected, toggling the card OFF under the open preview -- every later confirm clicked a dead container. The owner's double-selection theory, verbatim. Fix 44388cb records the pick; settle-dwell (3b5f834) + recovery ladder (23d6a1e) stay as defense in depth. The MOD behaved correctly throughout -- the API-vs-click parity ask is RETRACTED. Port caveat stands: 'server dead' claims (#2/#4) probed 7777, real port 15526, unverified.** **TREASURE WEDGE x2 IN 24H (2026-08-10): batch bl7868o6c died at run 31/40 (f41, Bag of Marbles) and batch bodib6eca at run 38/40 (f26, Captain's Wheel) -- same signature both times (watchdog 3x re-claim fails, claim returns 'ok' into frozen state, force-close+Continue recovers). Relic tally across treasure wedges now: Captain's Wheel x2, Bag of Marbles, War Paint (?-node), Bellows -- Captain's Wheel repeating is worth an eye. At this cadence the wedge is the dominant batch tax: elevates abandon-to-menu AND the owner-approvable scripted recovery (taskkill + steam relaunch + auto-Continue) as the interim watchdog.** **'5th instance' RETRACTED (2026-07-31): the owner had closed the game to wrap up the day -- not a crash. Kept as a lesson: a missing process between batches is ambiguous (owner action vs crash), and the correct unattended response (pause + report, never blind-relaunch) was followed. The crash-watchdog/relaunch infra item still matters for genuine overnight trains.**|

| **Seed-A Aeonglass owner-commentary work queue (2026-08-29)** | combat | The richest fight pair on record (logs/reports/aeonglass_seedA_tapes.md): identical deck/seed, bot died r8, owner won r6 at 46 HP. Owner per-turn commentary extracted to 6 items: (1) SIM GAP hand-limit draw fizzle (confirmed unmodeled — bot burned ~2 draws T1 and reached Pact's End+ a turn late); (2) draw-rider-before-Trance sequencing (falls out of #1); (3) Dominate/Molten-Fist-class hold-until-real-vuln (payoff cards must not be artifact strips); (4) Rampage-before-X-cost sequencing; (5) Burning-Pact-eats-the-incoming-Wither timing (speculative); (6) hold-for-recycle post-shuffle pairing (§5-C material); (7) artifact-strip credit scaled by deck vuln-payoff density (owner: 'clear underrating' at flat 3.0); (8) strip-ordering (cheap debuff before plain attacks while charges remain); (9) hand-reroll potions (Bottled Potential 'shuffle ALL cards into draw pile, draw 5') as a proactive fix-the-hand lane + Swift-on-bad-hand, with pre-reroll energy pickup (also flushes hand Withers into the diluted pile); (10) cheap-draw-opens-the-turn — generalize the KD 0-cost-draw opener to cost<=1 draw attacks on near-tied orderings (draw-first optionality; T5 verified: Dominate led NOT via a Str-vs-Artifact bug — code applies vuln through Artifact correctly — but via strip credit + exhaust enablement, i.e. item #3's payoff-as-stripper pattern). REFRAME from owner T5: the detonation was adaptive ('awful turn -> fix the hand'), not scheduled — encode the trigger as hand-quality-vs-incoming recognition, beat alignment emerges. (17-CAL) w_energy_waste rewards NULL SPENDS: burning energy on a dead play (unfulfilled Forgotten Ritual, T7) scored +0.15 over leaving it — the dock should measure unrealized VALUE, not unspent points; two symptomatic fixes landed (FR veto, heal-waste out-vote), the calibration itself still open. SPEC TIER (multi-turn, for the 5-C planner): (5) chooser-exhaust timing vs the Withering countdown; (6) hold-for-recycle post-shuffle pairing (Molten Fist); (11) Battle-Trance-vs-held-draw-potions brick; (18) desperation-draw lane spends energy mid-plan without re-budgeting the plan's later commitments (seed-B r8: the planned Evil Eye+ evaporated); BEAT-TRIGGER: hand-quality-vs-incoming recognition arming reroll/detonation (owner reframe) — the encodable core of 'setup is essential.' (19) Duplicator margin rule: when dup_armed and proj loss is within projection error of hp, prefer the DEFENSIVE double (Queen death-by-1, 2026-08-30; hail-mary gate landed, the in-plan choice rule is spec). (11) Battle-Trance-vs-held-draw-potions brick (speculative); (12) hail-mary/reroll potion ORDERING — reroll-class before draw-class on junk hands (r7 tape: Swift's 3 draws 100%% flushed by a subsequent Bottled Potential; lane currently drinks in belt-slot order). (13) Barricade-in-plan: _apply_card never sets sim.barricade when the power is PLAYED (only turn-start status seeds it) — same-turn block after Barricade gets no persistence credit until replan; seed-B T1 tape: plan flipped to Evil Eye+ only after Barricade resolved. Mid-plan flag set = ~3 lines + test. (14) FRACTIONAL Withering cost: charge ~tier_dmg/period per card play vs her, not only at the crossing — seed-B T3 tape: Whirlwind played at 0 ENERGY (zero hits, no DotW in deck) purely advancing the counter; crossing-only pricing makes counter-advancement free. (15) INVESTIGATE: planned [Molten Fist > Taunt] (seed-B T4) — backwards vs the vuln-doubling; either the DFS ordering credit for doubles_target_vuln fails to surface or a tie-break hides it; also 2nd concrete draw-first cost (Dominate-before-Pommel locked out a Taunt->MF->Dominate line: reinforces #10). Plus the fight-level finding: beat-aligned detonation (defend the Laser beat, kill on the II beat) = defend_deadline generalized to her 3-cycle + burst-bank arming. |

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

#### 8.4-A Act-1 boss mechanics — deep-dive reference (2026-06-26)

Full pass on the **six** Act-1 bosses (web: STS2 wiki, sts2companion, spire-codex, pcgamer; mechanics
cross-checked against `data/bestiary.json`). Frequency in our 110-run bestiary: **Kin 20**, **Ceremonial
Beast 14**, **Vantom 12**, **Soul Fysh 6**, **Lagavulin 5**, **Waterfall 3** (Soul Fysh is the **Underdocks**
alt-Act-1 boss). *Correction (2026-06-26): an earlier draft of this section claimed Vantom/Soul Fysh had
`runs_seen 0` — that was my error (I inferred "never seen" from a name-grep that didn't match them, instead
of reading their entries; the bestiary build is fine). They're mid-frequency, ahead of Lagavulin/Waterfall.*
Sourced mechanics, diffed against the planner (`combat.py`) and §5-C (`capability.py`).
Live validation is **opportunistic** until seeded runs are available again *(clarified 2026-07-08,
owner-confirmed: custom mode WAS unlocked 2026-06-15 on the original profile — the "needs 3 Act-3 wins"
phrasing here was an error; but it's re-locked on the current machine's restored pre-unlock profile.
Restore the old machine's newer snapshot (~2026-07-10) or re-earn 3 Act-3 wins — owner offered a manual
re-grind, which doubles as fresh `record` data)* — so this is model-against-docs + fixture tests,
confirm live when a run reaches one. **Common thread across all four: a DPS race** — the bot's weak decks are exactly the
profile these punish, so §5-C race-accuracy + tempo drafting are the binding levers, not micro-tactics.

- **Ceremonial Beast** (252 HP). *Mechanic:* ramps **Strength** (Plow); **first time** HP ≤150 → **Stunned
  + loses ALL Strength** (one free turn); Phase 2 **Beast Cry → Ringing** (play only 1 card/turn). Pure
  race, ~100 dmg ASAP. *Modeled:* Str-ramp race ✓; Ringing `card_cap` (generic, live) ✓; **stun now
  crossing-based + one-time** in the planner (`stunned_this_turn`, set when our damage crosses 150 — fixes
  the level-based bug that would treat it as stunned every turn below 150) ✓ **[done 2026-06-26]**; §5-C
  **zeroes enemy Strength on stun** ✓ **[done]**. *Open:* none material.
- **Lagavulin Matriarch** (222 HP). *Mechanic:* starts **Asleep + 12 Plating** (sleeps 3 turns OR until
  unblocked damage; wakes → loses Plating). Awake cycle Slash → Disembowel → Block/Attack → **Soul Siphon**
  (= permanent **−2 Strength AND −2 Dexterity to the PLAYER** each cycle). Multi-hit pierces Plating; rush
  once awake. *Modeled:* Plating as §5-C `self_block` (12) ✓; multi-hit-vs-block soak ✓; Asleep = Sleep
  intent → `incoming` 0 (passively) ✓; Str-ramp ✓. *Open (filed):* **(a)** Soul Siphon stripping the
  player's Str/Dex is unmodeled — §5-C `my_str` only grows, so it **over-rates** survivability vs Lagavulin; **(b)** Asleep is a **multi-turn setup window** (buff/scale during the 3
  free turns, don't wake it early with chip attacks) — the one-turn planner can't price the hidden cost of
  waking it; §5-C race-vs-setup territory; **(c)** Plating's −1/turn decay is ignored (treated constant →
  slightly over-rates its defense).
- **Waterfall Giant** (240 HP). *Mechanic:* almost every move adds **+3 Steam Eruption**; killed-while-
  -Steam-Eruption → **invulnerable**, "About To Blow" then **Explode** next turn for the **accumulated**
  stack, then dies. Speed race. *Modeled:* DeathBlow telegraph counted as incoming ✓ **[done]**; sentinel-
  HP **invincible → damage wasted** ✓ **[done]**; §5-C `death_damage` ✓. *Part (a) estimate-side DONE
  2026-07-09:* §5-C now grows the projected explosion by 3/turn (`death_damage_growth`, _EMPIRICAL_MOVES)
  — a slow kill projects the real 30–60+ stack. *Still open:* the in-fight pre-kill decision (push to 0
  this turn vs wait) needs scheduled-post-lethal-hit modeling in the planner. Multi-turn; deferred.
- **The Kin** (Kin Priest 190 + 2 Kin Followers ~58). *Mechanic:* Priest cycles **Frail → Weak → triple-hit
  → +Str**; Followers ramp Str; **Orb of Frailty** (Frail −25% your Block) / **Orb of Weakness** (Weak −25%
  your damage). Kill Priest → Followers **flee** (Minion); or clear Followers first; **AoE trivializes**.
  *Modeled:* Minion-aware lethal (leader-kill ends it) ✓; focus-fire ✓; Str-ramp ✓. *Open (filed):*
  **Frail/Weak on the PLAYER** (−25% block / −25% damage) is unmodeled — the planner treats its own
  block/damage as un-debuffed, so it **over-projects** both vs the Kin (same class as Lagavulin Soul Siphon:
  enemy-applied player-debuffs). General item: **model enemy debuff-intents onto the player** (Str/Dex/
  Frail/Weak strips), feeding §5-C's per-turn block/damage and the planner's lethal check.

- **Vantom** (173 HP; `runs_seen 12` — toughest Act-1 boss, strict 4-turn cycle). *Mechanic:* enters with
  **9 stacks of Slippery** — each stack reduces the next damage *instance* (any source) to 1 and is
  consumed, so **multi-hit strips stacks fast and single big hits are wasted**; clear Slippery, then burst.
  Cycle: T1 attack+apply Slippery, T2 attack, **T3 Tail Stab (~20 dmg + 3 Wounds to hand)**, T4 +Strength.
  *Modeled — DONE 2026-06-26:* the planner's old Slippery model was per-turn-first-hit (`slippery_pending =
  lost==0`), which mis-priced the **9-stack** Vantom (it thought hits 2..n of a multi-hit landed full when
  each deals 1). Now `EnemySim.slippery_stacks` is sourced from the status **amount** (Inklet 1, Vantom 9 —
  both are the same consume-on-hit mechanic, so nothing regressed); `_apply_attack` drops each damaging hit
  to 1 while charges remain, spends one, and threads the count across cards in a sequence. So the planner
  reads realistic (low) damage during the strip phase and prefers cheap multi-hit over a wasted big single
  hit. 4 tests. *Still open:* §5-C's per-turn biggest-hit reduction stays a rough multi-turn proxy (it only
  strips ~one big hit/turn, so it over-rates how fast a multi-hit deck clears 9 stacks — acceptable for a
  draft/route estimate; the in-combat planner is what plays the fight). *Wounds to hand* (clog) unmodeled.
- **Soul Fysh** (211 HP; `runs_seen 6` — **Underdocks** alt boss, 5-turn cycle). *Mechanic:* Beckon → Lure →
  Nibble → **Intangible** → Vulnerable-Bite + Intangible, repeat. **Beckon** adds status cards (cost 1e; if
  not exhausted/discarded by end of turn → **6 unblockable** each). **Intangible** turns reduce **every hit
  you land to 1** (don't attack — defend + clear Beckons). *Modeled:* Beckon-type unblockable end-of-turn
  hand cards ✓ (`_HAND_HP_LOSS_RE`, owner-confirmed Beckon→HP). *Update 2026-07-09 (batch
  bsmwhj26u made Fysh 4/9 Act-1 bosses, all losses — 11 cards measured going into visibly-Intangible
  turns):* the diagnosis flipped on investigation. **Intangible was ALREADY modeled** — `_CAP_RE2`
  parses its text into `dmg_cap_per_turn=1` and `_apply_attack` enforces it; the planner *knew* the
  attacks were ~worthless (they scored negative). The real bug was the long-filed **Beckon-clearing
  value gap**, compounded by a parser misread: (a) the stranded Beckon/Toxic end-of-turn penalty was
  only in the post-hoc `hp_loss` diagnostic, never in the scored objective, so the search could not
  prefer spending energy to clear one; (b) `parse_card_description` read Beckon's "lose 6 HP" as an
  immediate self-cost of *playing* it, exactly canceling any clearing credit. **FIXED 2026-07-09**:
  the stranded penalty (unblockable Beckon / blockable Toxic, keyed by hand index, skipped on lethal)
  now lives in `_score`, and stranded-status text zeroes the misread fx. Replayed the real failure
  state: `[Pommel Strike > Strike]` → `[Beckon > Pommel Strike > Beckon]`, hp_loss 17→5. 4 new tests;
  6740-state replay clean. **Pending live validation** (next batch). This closes the "make the planner
  value spending the energy to play it" TODO from the Soul Fysh block-bypass item below.

**Cross-boss filed item — enemy-applied player debuffs** (Soul Siphon, Frail, Weak): the
recurring gap is that §5-C/`planner` model *my* Str/block/damage as monotonic, but several Act-1 bosses
actively **strip or weaken** them. Split into two halves:
- **(a) In-the-moment — DONE 2026-06-26.** The planner now reads my **own** Weak / Frail off `player.status`
  and applies them this turn: Weak (`my_weak`) cuts my Attack damage ×0.75 in `_apply_attack`; Frail
  (`my_frail`) cuts Block-gained-from-cards ×0.75 in `_apply_card` (`FRAIL_MULT`). Universal (every
  Weak/Frail fight, not just bosses — the Kin applies **both** via Orb of Weakness / Orb of Frailty), so
  the lethal/survival math is no longer over-stated when debuffed. 2 tests.
- **(b) Multi-turn — filed, DATA-BLOCKED.** §5-C still treats `my_str`/block as only-growing across turns,
  so it doesn't model a boss **permanently stripping** them. Verified 2026-06-26 that this **can't be done
  well from current data**: **Soul Siphon** (the impactful one — Lagavulin, −2 Str AND −2 Dex *per cycle*,
  permanent) is **not in `bestiary.json` at all** (it's a move/intent, never captured as a status), so
  modeling it = hardcoding web numbers (fragile). *(Correction 2026-07-08, owner + wiki-verified: an
  earlier draft cited "Dark Shackles" as a Kin Priest Str-strip — wrong. Dark Shackles is **our**
  colorless 0-cost Skill ("enemy loses 9 Strength this turn"); it shows up in harvested data because
  our own debuffs land as enemy statuses. The Kin's real player-debuffs are the Orbs' Frail/Weak,
  already modeled in-the-moment. Soul Siphon is the only data-blocked item here.)* **UNBLOCKED 2026-07-09 — live trace captured** (batch bljp94t0d run 2, `logs/runs/20260709-104702*`):
  Soul Siphon lands as plain `STRENGTH_POWER`/`DEXTERITY_POWER` stacks on the player that **go
  negative** (Str +3→+1→−1, Dex 0→−2→−4), **−2 Str −2 Dex per cast, every 4th round post-wake**
  (rounds 6 and 10 here), delivered via a `Debuff (Strategic)` intent while the boss ramps (+2→+4).
  Same trace also shows the Asleep-window misplay live (bot chipped 222→213 in round 1, waking her
  early). *Ready to implement:* a per-enemy "drains my Str/Dex by 2 every 4 turns" term in
  `estimate_fight` (empirical params, no more web-number hardcoding), and note the planner already
  handles negative live Str; **negative Dexterity (block-per-card reduction) is NOT modeled** —
  smaller sibling gap, do together.

- **§5-C `block_per_turn` ignores passive relic/power start-of-turn block** (owner question 2026-06-26).
  The **in-the-moment planner is fine** — `my_block = player.block` ([combat.py:555]) reads the live block,
  and beginning-of-turn block resolves *before* the play phase, so it's already counted. But the §5-C fight
  estimate's `block_per_turn = total_block / cycle` sums only the **deck's block cards** (`fx.block`,
  [capability.py:312]); it misses passive per-turn block from **relics/powers** (e.g. a "gain N Block at the
  start of your turn" relic, Necrobinder/defensive powers). So the multi-turn estimate **under-counts block
  → over-rates fight danger** for such builds, skewing route/draft EV (not how any turn is played). Fix:
  fold a per-turn passive-block term (sourced from `player.relics`/`player.status` like §5-C's enemy
  mechanics) into `block_per_turn`. Modest; do with the §5-C enemy-mechanic-awareness pass.

#### 8.4-B Act-2 boss mechanics — deep-dive reference (2026-06-26)

**Three** Act-2 bosses (the **Hive**; one chosen at random) — web (STS2 wiki, sts2companion, games.gg,
bossdown) cross-checked vs `data/bestiary.json` (thin: `runs_seen` 1–2, Act 2 rarely reached). All three
killed runs in the validation batch ble3lyl8a (Kaiser Crab f33, Knowledge Demon f33) — **this is the
current wall**. The Act-1-style in-the-moment fixes ported here are the lever.

- **Kaiser Crab** (two claws: **Crusher** 209 HP tanky + **Rocket** 199 HP heavy-hitter; kill BOTH → the
  body flees). *Mechanics:* **Crab Rage** — "when an ally dies, [survivor] gains **6 Strength and 99
  Block**" (`CRAB_RAGE_POWER`) for ONE turn; **Surrounded / Back Attack** — the claw you face *away from*
  deals **+50%** (`BACK_ATTACK_LEFT/RIGHT_POWER` + player `SURROUNDED_POWER`); **Bug Sting** — Weak 2 +
  Frail 2 on the player. **Facing mechanic (owner, from a prior session):** you face whichever enemy you
  **single-target-clicked LAST** this turn (attack/potion); the *other* claw takes the +50%. AoE does
  **not** rotate. So face the claw with the bigger incoming at end of turn. Crucially, **killing one claw
  ends Surrounded → you face the survivor permanently (no +50%)**, so killing a claw is **generally a
  BOON** despite the one-turn enrage — *not* the "trap" the first cut assumed. **DONE 2026-06-26**
  (config `8914a6c97a18` → `374480217e9e`): (1) `EnemySim.back_attack` + `SimState.surrounded` +
  `SimState.facing` (tracks the last single-target click through the sequence); `_score` adds +50% to the
  unfaced claw's incoming while 2+ claws live (label is **base** — verified live: facing changed
  None→Rocket at seq1168→1170 with labels steady 18/3), defaulting to facing the biggest hitter. Killing
  a claw drops to one → no +50% → the boon shows up as an incoming drop. (2) `EnemySim.crab_rage`: at
  *card* granularity a claw's death gives surviving allies +99 Block +6 Str (AoE that kills both enrages
  no one); the in-sim 99 Block stops the planner over-crediting a sequential double-kill it can't punch
  through. (3) `w_crab_rage_split` **reduced −80 → −20** — only a gentle nudge against a *needless* split,
  since the back-attack model now carries the real kill-the-claw value. Bug Sting's Weak/Frail ✓ (the
  in-the-moment fix). *Open/filed (edge):* **Stampede & end-of-turn auto-play cards rotate facing
  arbitrarily** (owner) — the facing model assumes none active; a card that auto-plays attacks at end of
  turn can flip you to face the wrong claw. Rare; could later flag such cards as bad picks vs Kaiser Crab.
  *Simplification:* the initial/carried facing (turn start, before any click) defaults to "facing the
  biggest" rather than the true last-turn facing (the API exposes no facing field); self-corrects once the
  bot clicks.
- **Knowledge Demon** (379 HP). *Mechanic:* every few turns **"Choose a Card"** forces an escalating
  player debuff — Disintegration (end-of-turn DoT) vs Mind Rot (draw −1); later **Sloth** (max 3 cards/turn,
  = Normality-class card cap) vs **Waste Away** (−1 energy). Race it before the choices compound; pick the
  least-bad for your deck. *Modeled:* Str ramp / Vuln / Weak ✓; race ✓. *Open/filed:* the **in-combat
  debuff CHOICE** (pick least-harmful) is unmodeled — it surfaces as an in-fight card/selection the policy
  must resolve well (deck-aware); and the *resulting* debuffs touch the planner (Waste Away → energy, Sloth
  → `card_cap` like Normality, Disintegration → per-turn self-damage, Mind Rot → −1 draw). Bigger lift
  (decision policy + several debuff models); not in static data (the choices aren't bestiary statuses).
- **The Insatiable** (321 HP). *Mechanic:* **Sandpit** — "In 4 turns, you will be eaten and die"
  (`SANDPIT_POWER`); ramps every turn, no cap → pure DPS check, kill in ~5 turns. It shuffles **Frantic
  Escape** cards into your deck; playing one **raises the death timer by 1** (owner reminder). *Modeled:*
  **already well-covered (confirmed 2026-06-26)** — §5-C parses Sandpit as `death_timer` (race-or-die) and
  pads it `_SANDPIT_SLACK = 3` for the Frantic Escapes; **and the in-combat policy already plays Frantic
  Escape** — `StandardRouter._survival_card` ([standard.py]) generically detects a death-countdown status
  ("you…die/eaten") and, once it drops to `survival_status_threshold = 2`, plays the injected card whose
  text names that status (Frantic Escape) to push the timer back. Str ramp + Vuln modeled. No new work;
  optimal Frantic-Escape *timing* is a later refinement (the `_SANDPIT_SLACK` comment already flags it).

**Act-2 takeaway:** **Kaiser Crab is DONE** (Crab Rage + back-attack/facing + Bug Sting all modeled; the
key insight — killing a claw ends Surrounded so it's a boon, not a trap — corrected from owner notes).
**Knowledge Demon "Choose a Card" — DONE 2026-07-09** (screen captured live in batch b8oazdsui run 10:
an ordinary `card_select`, `screen_type: "choose"`, all-Status options — Disintegration vs Mind Rot).
Two pieces shipped: (1) an all-Status card_select is a **pick-your-poison** chosen by the owner's
least-bad table (`_DEBUFF_PREFERENCE`: Disintegration > Mind Rot > Sloth > Waste Away; unknown
debuffs sort last) — the old best-quality pick got Disintegration only by index luck; (2) the chosen
debuff lands as **`DISINTEGRATION_POWER` on the player** and the planner now counts its end-of-turn
blockable damage in the incoming pool (text-parsed amount, tracks the 6→7→8 escalation live).
*Estimate side DONE 2026-07-09* (`heals_per_turn=7` capped-at-start Ponder regen +
`player_dot_avg=5` via _EMPIRICAL_MOVES — the race now respects both). *Still open:* planner
effects for the OTHER poisons if a fight ever forces one (Sloth = card cap the
existing Ringing machinery could carry; Waste Away = energy; Mind Rot = draw). The Insatiable is
already covered including Frantic Escape.

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
  - **Power-*adjacent Skills* miss the horizon value — Apotheosis under-played** (owner live 2026-06-26).
    **Apotheosis** (2e, Innate, Exhaust, *upgrade all your cards for the rest of combat*) is a one-shot
    **combat-long buff** that plays like a Power, but it's `type == "Skill"` with no immediate
    damage/block the parser recognizes — so it gets neither the horizon term (`is_power` is False) nor a
    this-turn score, and loses to spending the 2e on attacks (the exact deferral the Tier-1 fix cured for
    real Powers). Same root as the powers item, different card class. **Fix:** flag combat-long-buff
    Skills as power-like for scoring — either a phrase heuristic on "rest of combat" / "this combat" +
    upgrade/buff (cheap, some false-positive risk) or the Tier-2 per-card table (Apotheosis tagged
    power-like). Then it rides `power_horizon` and goes down ASAP early. Edge case; do with Tier 2.
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
- **[RESOLVED 2026-06-26]** Pen Nib, Artifact, in-combat healing (Not Yet), planner-side stun-threshold,
  and invincible-enemy handling all landed in the combat-modeling pass (commit on `combat.py`; 9 tests).
  Details inline below per item. Normality's card cap stays deferred — no API field exposes
  cards-already-played-this-turn, so `3 − played` can't be sourced (the in-game `can_play` flag
  self-enforces the hard cap on replan anyway).
- **Pen Nib (relic) unmodeled — missed lethal** (owner lookthrough 2026-06-25). **DONE:** read the live
  relic counter (`Relic.counter`, persists per-run); in the DFS each attack increments it and the one
  landing as the 10th (counter ≡ 9 mod 10) doubles its post-Strength damage. **Pen Nib:** **every 10th
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
- **Artifact unmodeled — planner wastes debuffs into it** (owner lookthrough 2026-06-25). **DONE +
  ✅ VALIDATED LIVE 2026-06-26** (batch ble3lyl8a, tripwire caught Artifact in 4 runs — Cubex Construct
  Artifact 1, Chomper Artifact 2). Concrete proof from run 6's Chomper fight (both Chompers Artifact 2):
  at seq848 the planner played **Defend+ → Defend → Strike+ → Defend** and **withheld Uppercut+/Bash**
  (their Weak/Vuln would be eaten) while still playing the *pure* attack Strike+; at seq875, with the hand
  clogged by 3 Dazed and Uppercut+ the only damage, it **did** play Uppercut+ into the Artifact-2 Chomper
  — correct nuance (an attack-debuff is still worth its *damage* once it's the best play). Run 5 likewise
  played Defend over **Dominate** (pure debuff) into Artifact 2. Resolves the held "await live sighting"
  for Artifact. (Pen Nib still unseen — tripwire stays.) Implementation:
  `EnemySim.artifact`; `_apply_card` resolves a card's debuffs against the target's Artifact in
  card-text order (`PlannedCard.debuff_order`), stripping one per unique status (magnitude-blind),
  landing only what survives. Dominate-into-Artifact-2 scores ~0; Uppercut at Artifact 1 strips Weak
  and lands Vulnerable. Original detail: Enemies had
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
- **Healing on cards (Not Yet) parsed but NOT modeled in combat** (owner 2026-06-26, live question).
  **DONE:** `_apply_card` accrues `min(heal, max_hp−hp)` into `SimState.healing` (no overheal), and
  `_score` nets it against `hp_loss` on the same HP-scarcity curve — worth ~nothing at full HP, a lot
  when hurt (symmetric with Offering). Original detail: The
  parser sets `fx.heal` (Not Yet = 2e, Heal 10 HP) and *event* scoring uses it, but the combat planner's
  `_apply_card`/`_score` ignore `fx.heal` — so an in-combat heal reads as a 0-value energy sink and the
  planner won't play it even when hurt with spare energy. Fix: track capped healing in `_apply_card`
  (`min(heal, max_hp − hp)`, no overheal) and credit it in `_score` scaled by the same HP-scarcity curve
  as `hp_loss` (worth more when low, ~nothing at full HP — symmetric with the Offering logic). Small.
- **Stun-threshold as a defensive play (Ceremonial Beast / Terror Eel) — modeled in §5-C, NOT the
  planner** (owner 2026-06-26; not 100% sure of the instance but the gap is real). **DONE:**
  `EnemySim.stun_threshold` (sourced via `detect_mechanics`, same as the other throttling mechanics);
  the stun is **one-time + crossing-based** (`stunned_this_turn`, set in `_apply_attack` only when our
  damage drops it from *above* the threshold to at/below — corrected 2026-06-26 from an initial level-based
  check that would have treated the Beast as stunned every turn it sat below 150, i.e. after the stun was
  already spent and it was awake again). `_enemy_attacking()` then drops the stunned enemy's `incoming`, so
  the planner attacks-to-threshold to dodge the otherwise-lethal hit instead of blocking. Original
  detail: These bosses are
  **Stunned** when dropped to/below an HP threshold (Beast ~150), skipping a turn — so *attacking down
  to the threshold* can cancel an otherwise-lethal hit and buy a turn. `estimate_fight` already models
  this (`stun_threshold` → skip the enemy turn when crossed), but the one-turn **combat planner**'s
  `EnemySim` has no `stun_threshold`, so in the moment it treats `incoming` as fixed and can't choose
  "attack to the threshold → stun → survive" — owner saw it block (and die) instead. Fix: carry
  `stun_threshold` into the planner's `EnemySim` (source it from the bestiary like §5-C, or
  detect_mechanics) and in `_apply_attack`/`_score` zero that enemy's `incoming` once cumulative damage
  crosses it (stunned this turn). Concrete instance of the standing theme: **the planner needs §5-C's
  enemy-mechanic awareness in the moment, not just at draft/route time.**
- **Normality (curse) — 3-card/turn cap unmodeled** (owner 2026-06-26; "at some point"). While
  **Normality** is in hand you can't play **>3 cards this turn**, *inclusive of cards already played*
  before it was drawn into hand. Same class as **Ringing** (the planner's existing `card_cap` —
  Ceremonial Beast's 1/turn), just cap **3** and sourced from a curse in *hand* rather than an enemy
  status. Fix: detect Normality in hand → set the plan's `card_cap = 3 − cards_already_played_this_turn`
  so the DFS doesn't start a sequence it can't finish and picks the best ≤3-card play. Deferred.
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
  — should have fired trivially, didn't. **RESOLVED (b), the no-fire — `incoming` filter bug** (fixed
  2026-06-26, commit on `combat.py`): the eruption **is** surfaced by the API, as a **`DeathBlow`**
  intent (the boss flips invincible at an HP sentinel `999999999`, then telegraphs the explosion as
  DeathBlow with the full stack as its label). But the combat planner's incoming tally filtered intents
  to `type == "attack"` only, so DeathBlow read as **0 incoming** → no block reserved, and the
  hail-mary/desperation gate (compares incoming vs HP) never saw the lethal. Now counts
  `type in ("attack", "deathblow")`. So this was a **parsing/filter bug, not eruption-blindness** — the
  fix makes the bot block it and hail-mary it like any other big hit. **Also done (owner refinement
  2026-06-26):** while the giant shows its sentinel/invincible HP, damage into it is wasted — it dies on
  its own after the eruption, only mitigation matters — so `EnemySim.invincible` (HP ≥ 1e8) makes
  `_apply_attack` credit no progress for hitting it, steering the planner onto block/potions instead of
  chipping an unkillable wall. **(a) still open** for the general
  case: when the eruption is *not* yet on the board as a DeathBlow intent (the bot is mid-fight deciding
  whether to push the boss to 0 *this* turn), it still doesn't model the one-turn-delayed post-lethal
  hit — that needs scheduled-hit modeling (block reserved like a delayed Beckon), tied to the
  death-tally completeness items. The lethal/desperation-on-post-plan-survivability note above also
  still stands.
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
  - **Wider problem — RESOLVED in three layers (2026-07-09):** the §5-C elite gate priced every
    elite as a generic 90 HP / 17 dps blob. Now: **(1)** the gate judges the act's REAL bestiary
    pool (win ≥ `elite_gate_pool_win_frac` of it; Terror Eel deaths 2→0 same day); **(2)**
    multi-body elites compose to their true body count (`_ELITE_COMPOSITIONS`: Gardeners 3×
    Skittish, Phrog + Wriggler wave, Decimillipede 3× Reattach segments — the last live-counted
    from a genuine gate-pass death); **(3)** a gate-rejected elite is priced **death-class** in
    the route DP, so lanes ENDING in forced elites are refused at commit time (bn4v9mf75
    forensics: all remaining elite deaths were forced lanes). Still future: zone-aware pools
    (Underdocks vs Overgrowth split — infer from the boss), pool-depletion narrowing, Reattach
    revive modeling.
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
  - **Sleeper v4 (2026-09-28, ce7359d)** — A0 promoted-key era: Matriarch **9/20 (45%)** vs 69–93%
    for every other act-1 boss; 18/20 fights woke her by card, 9 of 11 losses were round-1/2 pokes
    (mode=setup_window throughout — the sim's pricing leaked, not the mode). Fixed: wake = **HP loss
    only** (a Plating-soaked hit stays asleep and pays nothing; the old any-hit rule pre-paid the bar on
    the blocked card and let the real waking poke land free); `w_wake_sleeper` is **per forfeited free
    turn** (stacks−1; a hit on her last asleep turn is free); a paid wake turn earns **no focus/ramp
    premium** on her (19 raw read as ~52 and out-bid the Power). Owner-unreviewed: the −16/turn unit
    keeps the 08-06 flat sizing, so a ~25 round-1 burst no longer clears a 2-turn forfeit (§7 row).
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
- **Human-baseline capability list from the recorded win** (owner commentary 2026-07-08, seed
  `7Q4QCYQ09J` — "this run landed incredibly deep in the range of things the bot cannot currently
  execute"). Four named mechanics that carried the win, with what each demands:
  - **Stomp — dynamic in-turn cost** (3e, costs 1 less per Attack played this turn, *including
    attacks played before it was drawn*). The planner reads live `card.cost` at plan time
    ([combat.py:123]) and the loop replans per card, so the *discount itself* is visible on
    replan — but the DFS plans a sequence off the cost snapshot, so it never **chooses to
    front-load attacks to make Stomp cheap**; it can only stumble into the discount. Needs
    within-sequence dynamic cost (same family as the free-draw-first sequencing items).
  - **Neow's Fury as a tutor** — owner repeatedly played it to **fetch a specific card for this
    turn's plan** (usually Bloodletting for the +2 energy). *Owner correction 2026-07-08: it
    tutors from the **discard pile** specifically* — so valuing it requires **discard-pile
    knowledge** (player-visible; the state exposes `discard_pile`). Three gaps: the planner
    doesn't track pile contents, doesn't value search/fetch effects, and the resulting in-combat
    card-select screen would be answered by the generic best-prior pick, not by *what this turn
    needs* (energy when energy-starved, a finisher at lethal range). Context-aware in-combat
    select is the harder, more general half.
  - **Cascade — X-cost autoplay from deck** (plays the top X cards of the deck). X already
    resolves to current energy in the planner, but the *effect* is unparseable text → scores ~0;
    real value needs draw-pile composition/order awareness (multi-turn / §5-C territory). NB the
    pilotability discount (×0.45, session 4) already keeps the bot from over-drafting it — the
    owner's run shows the ceiling that discount is protecting against, not a drafting bug.
  - **Delicate Frond (Act-3 Ancient relic) — potions refill at the START of EVERY combat** →
    optimal potion policy flips from "hoard for elites/bosses" to **"spend usefully every
    fight"** (owner did exactly this). The potion taxonomy's thresholds are all
    scarcity-shaped; needs a relic-conditional aggressiveness switch (belt is perpetually
    full, so today's full-belt deploy would dribble low-value potions out, not *use* them).
  - *Meta-note:* none of these four is individually filed work yet — they're the concrete
    picture of what "winning execution depth" looks like vs the one-turn planner, and good
    candidates for the §8.3 per-card special-case pass / §5-C consumers when those open.
  - **All four composed in one fight — the f44 Knights ONE-TURN KILL** (owner's proudest
    fight, reconstructed card-by-card from the trace:
    [combat_notes_2026-07-08-f44-knights.markdown](combat_notes_2026-07-08-f44-knights.markdown)).
    276 HP of Act-3 elites cleared in round 1: two potions *generated* 0-cost combo pieces,
    Duplicator doubled a Cascade+ X=4 (8 deck auto-plays), two mid-turn energy refuels, and
    Stampede's queued end-of-turn auto-attacks delivered the last ~23 damage of the lethal.
    Flagged as the **acceptance test** for the eventual §8.3/§5-C planner work: could the
    bot find (or approximate) this line?
- **The Queen (Act-3 boss) — FIRST CAPTURE** (owner's manual recorded win, seed `7Q4QCYQ09J`,
  2026-07-08). **400 HP**, ramps Strength; fights alongside a **Torch Head Amalgam** carrying
  `MINION_POWER` (leader-kill ends the fight — existing minion logic applies). Division of labor:
  the **Amalgam is the attacker** (escalating 6→24, multi-hits 9x3/10x3/13x3), the **Queen is
  support/control** (intent types `Debuff`, **`CardDebuff`** — junk-card injection?, `Buff`,
  `Defend`; occasional 25 or 7x5 attacks). Full trace in `logs/manual/runs/20260708-212420*`;
  per-enemy handler candidate alongside Aeonglass (Act 3 has multiple bosses). Not yet in
  bestiary.json (see the §7 rebuild-hazard row).
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
   **→ DONE in two steps (CARD_PASS.md): step 1 (play) shipped tranches B/C/delta 07-09..12;
   step 2 (draft) SHIPPED 2026-07-12** — owner-reviewed tag machinery
   (`policy/drafttags.py` + `data/card_draft_tags.json`, CARD_PASS_STEP2_PROPOSAL.md review
   log is the authority). This also delivers a big piece of item 1 (deck-synergy drafting)
   without the co-occurrence data. *Deferred from step 2, filed here:* boss/enemy-profile
   draft conditionals (Dark Shackles/Mangle/Flame Barrier vs multi-attack profiles;
   Hellraiser vs Kaiser Crab back-attack), Feed/Dramatic-Entrance act-decay, Metamorphosis
   inverse-density, deck-size conditionals (Rampage/Mind Blast/Stratagem), Thrash large-deck
   dock. *For the relic pass (6):* block-gaining relics feed Juggernaut-class payoffs;
   per-N-attacks relics (Pen Nib) feed Anger-class attack flooding.
5a. **ANCIENTS pass** — ✅ v1 shipped 2026-07-16 (jumped ahead of the events pass after
   A/B #3 proved the f18 PAEL choice separated a human win from the bot's death on the
   same seed). Shipped: `data/ancient_boons.json` (scripts/build_ancient_boons.py; 88
   boons = full 8-Ancient pool from 459-run log harvest ∪ wiki, incl. log-only boons the
   wikis miss), catalog-first scoring for `is_ancient` events in `_event` (the generic
   heuristic was BAITED: Pael's Tooth "+5 for remove" beat the run-winning Legion),
   choice-time `deck_bonus` fit (Legion scales with block providers), and owned boons as
   drafting context via `boon_relic_context` — `provides` count toward tag needs (energy
   boons lift the draw penalty) and `draft_bonus` steers offers toward the boon's engine
   (Legion → block_engine, the owner's boon-then-Barricade causality). Uncatalogued
   titles fall back to the generic heuristic (new epochs degrade gracefully).
   **Open:** 25/88 boons flagged `uncertain` (unknown StS2 keywords: Goopy, Imbued,
   Maul, Relax, Apparition...) pending owner review; Pael's-Tooth remove-screen
   prefer-best flip (§8.4 backlog); relic-catalog provides (Kettle etc.) could ride the
   same `boon_relic_context` mechanism in the relic R3 pass.
5. **Event analysis** — mostly already covered by event-choice WAR; only a few events carry nuance
   (Byrdonis Egg, §8.4). *Promoted 2026-07-09 (owner: "matters around the edges", now ranked after
   relics, before potions) with a concrete anchor case: the bot **enchanted a Strike with Slither**
   ("drawn card cost randomizes between 1 and 3") — a net LOSS on a 1-cost card. The enchant
   handler treats enchant like upgrade (pick the best un-upgraded card) but never evaluates the
   ENCHANTMENT itself — its value is card-dependent and can be negative; the pass should score
   enchant×card pairs (and decline/park when everything is negative, if the screen allows).*
*Owner priority ruling (2026-07-09, revised same day): items 2 and 4 (enemies, cards)
first, then the relic pass (6), then **events/enchants** (5), then the **full potion
pass** (7).*

6. **Relic combat-trigger pass** — **STARTED 2026-07-13, tranche R1 SHIPPED: see
   [RELIC_PASS.md](RELIC_PASS.md)** (180 relics audited: 132 A / 14 B / 31 C / 3 D;
   the RelicTrigger engine models 18 relics incl. Letter Opener, Lost Wisp, Gremlin
   Horn, Nunchaku/Tuning Fork lifetime counters, Paper Phrog, Velvet Choker; R2 =
   end-of-turn conditionals, R3 = first-per-combat latches, both filed there).
   (Original framing, 2026-07-08, owner: "worth parsing through the list of
   relics, which unfortunately adds a lot of complication"). The f44 one-turn-kill analysis
   ([combat_notes_2026-07-08-f44-knights.markdown](combat_notes_2026-07-08-f44-knights.markdown))
   showed trigger relics doing load-bearing work the planner can't see — **Letter Opener** (3
   Skills/turn → 5 AoE), **Centennial Puzzle** (first HP loss → draw 3), **Delicate Frond**
   (potions refill every combat) — and the state-diff reconstruction *mis-attributed relic
   effects to cards*, which is exactly the planner's blind spot. Pen Nib (modeled) and the §5-C
   passive-block gap (§8.4-A) are the same class; the pass would sweep `player.relics` text for
   combat triggers (on-skill-count / on-attack-count / on-HP-loss / per-turn) the way
   `detect_mechanics` sweeps enemy statuses. *(Ranked 2026-07-09: after enemies+cards.)*
   *Advanced note (owner 2026-07-09, filed for this pass): deliberately "storing" relic
   counter ticks across combats — e.g. ending a fight with Pen Nib on 9 so the NEXT fight
   opens with a doubled attack — is real human play the planner can't see; needs cross-combat
   relic-state valuation.*
   *Sub-item filed 2026-07-09 (batch b8msts8jx): **multi-body elite synthesis** — the pool gate
   fixed single-body elites (Terror Eel deaths 2→0) but Phrog+Wrigglers / Phantasmal Gardeners
   killed 3 runs; synthesize swarms as multi-FightEnemy pools (Gardeners ≈ 3×31 HP w/ Skittish,
   Phrog + Wriggler treadmill) so both the gate and the route DP price them. Belongs to the
   enemies pass (item 2), noted here because the gate work exposed it.*
   *Update 2026-07-30: Phrog re-fixed as a **dormant wave** (wrigglers spawn AFTER the parasite
   dies — the tape showed concurrent modeling was optimistic, not conservative) and composition
   members now use their own realized per-body dps (Wriggler 4.1, n=1028). 8e53a26, 7649ca2.*
6b. **Curses pass — DONE INLINE 2026-07-09** (owner: "low hanging, right after cards").
   All 9 discovered curses audited: **Normality's** 3-card cap now read from the HAND
   (conservative — the true remainder isn't sourceable, the game's can_play enforces it on
   replan; the win is the DFS stops planning unfinishable lines); **Decay** verified riding
   the stranded-Toxic machinery (blockable, unclearable); **Guilty** removal-ranking done
   earlier; Clumsy/Poor Sleep/Greed/Injury/Spore Mind are combat-inert clog the sim already
   experiences naturally; **Debt** (end-of-turn gold loss) noted, ignored as non-HP.
7. **Full potion pass** (scheduled 2026-07-09, after relics — owner ruling).
   *Scope census 2026-08-30 (owner framing: 'we've merely stochastically sniped
   down each potion I see misbehaving live'): 51 distinct potions ever held,
   40 now categorized/laned; the formal remainder is ELEVEN, several
   legitimately passive: Ashwater (chooser mass-exhaust — Wither tech!),
   Distilled Chaos (play top 3 — plays_pile_n family), Droplet of Precognition
   (draw-pile tutor), Duplicator (hail-mary-gated, no proactive lane; spec
   #19), Entropic Brew (lane-0 special exists), Fairy in a Bottle (passive
   revive — belt-hold is correct, but keep-value ranking should know),
   Fortifier (triple Block — big-block-turn timing), Gambler's Brew (hand
   filter), Gigantification (triple next Attack — burst-arming, dup family),
   Speed Potion (turn-scoped Dex burst), Stable Serum (Retain 2 turns —
   detonation-bank synergy). One sitting's work when scheduled.* The taxonomy
   (§8.4) covers reactive/proactive/hail-mary/downside plus the 2026-07-09 quick fix
   (card-gen potions dropped at boss start); the full pass adds per-potion handlers,
   Delicate-Frond-style abundance switching, Duplicator×X pairing, and the
   full-belt/reward-deploy logic.

Sequencing note: this complements §8.0 (the immediate routing/deck-power items). Items 2–4 are the
combat-side maturation that the §5-C capability estimate was built to anchor — they slot in as its
consumers, not as a pile of one-off rules.

## 9. Learning direction — value functions over the existing decision points (2026-08-27)

**Stage 2 plan (owner-approved 2026-09-28).** The Stage-1 heads (win AUC .684,
boss .757) are usable state evaluators but the ΔV pick signal is not (spread
~0.02 inside model noise; picks are the bot's own choices -> confounded; 26%
agreement). More rows of the same kind will not fix it: wins are 10% of runs and
one card moves P(win) by ~1-2pp, and 47k draft rows are only ~3.2k independent
outcomes. Plan: (1) keep batching on the fixed code (shop fix + observed
capability pricing, from 2026-09-11) and RETRAIN both heads on that era only
once it reaches ~300 runs (~106 at approval); (2) build the pick model on DENSE
labels (hp_delta_next3 / beat_act_boss) with OFFERS as the unit (intention-
to-treat framing, every offered card labelled by the run outcome -> no pick
confounding by construction), deck context as features; (3) run it as a
SHADOW re-ranker for several batches (log its pick beside the bot's; score the
disagreements on the offer-counterfactual basis) before it drafts; (4) the
retrained boss head becomes the act-3 capability estimate (the wall). Drafting
stays on the tag tables + counterfactual docks meanwhile.

Owner opened the RL question 2026-08-25 (spec: *"best possible bot in reasonable
human-viewing time on my machine"* — seconds per decision OK, minutes not; consumer
GPU at most). Agreed framing: **not end-to-end RL** — the bot stays search + evaluators;
we replace hand-set evaluator numbers with fitted ones at the same decision points.
The tag table / textparse infrastructure from the Aug audit IS the featurizer
(cards as feature vectors, not IDs → patch- and class-transferable, addresses the
beta-drift and other-classes concerns). Nested-feedback concern (drafting model
trained under a weak tactician) handled by: config-hash era stratification (already
logged per run), outcome labels less entangled with tactical skill (per-fight HP
deltas, boss-entry HP, act survival — not just win/loss), and offer-set
counterfactuals (same state, 3 candidates, one chosen).

**Value target ruling (owner Q 2026-08-27, answered):** the win-chance head is not an
add-on — P(win | run state) IS the value function the pick model is a delta over, so
we get it for free and should keep it exposed. The **boss-conditional head
P(beat current act boss | deck, relics, HP)** is the learned successor to the §5-C
capability estimate — the owner's own "root lever" — and is what rest/path/elite/shop
decisions want to consume. Also: a calibrated P(win) traced across a run localizes
blame (biggest drops = drafting vs fights vs pathing), which is the cleanest
diagnostic for the nested-feedback loop. So: train pick models as ΔP over a shared
value head; keep both heads (overall + boss-conditional) as outputs.

Stages (each gated on the previous paying off):

- [x] **Stage 0 — dataset builder** (`scripts/build_run_dataset.py`): walk `logs/runs/`
  → JSONL tables under `logs/datasets/` (gitignored, regenerable): runs, drafts,
  events, rests, fights. Raw ids + light derived labels only — feature extraction
  stays a separate training-time module so the feature schema can evolve without
  rebuilding. Doubles as the drafting-review analysis substrate.
  *DONE 2026-08-27: 2803 runs -> 40k drafts / 19.5k events / 34.4k fights, 0 parse
  errors. Plus `sts2bot/learn/` (featurizer + no-dep logreg) and a label-sanity
  baseline (`scripts/baseline_boss_head.py`, report in logs/reports/): P(survive
  act boss) at boss entry — ctx (hp+boss) AUC 0.755; linear deck features add
  ~nothing on aggregate BUT within-boss they beat hp-only for 9/12 bosses
  (Vantom .67→.78, Ceremonial .68→.78, Aeonglass .58→.63) and LOSE on
  Crusher+Rocket (.76→.64): per-boss interactions are real and a global linear
  weight can't express them — exactly the stage-1 GBT case. Entry-HP note:
  Aeonglass hp-only AUC is the lowest (.58) — entering healthy doesn't save you,
  the dossier's front-loaded-bleed shape in statistical form.*
- [~] **Stage 1 — draft/event value model**: gradient-boosted trees (CPU, µs inference)
  over tag-table/textparse features, deployed as a config-flagged BLEND with
  `_card_score`; validated snapshot-A/B then batches. Attacks the hand-tuning treadmill.
  *PARTIAL 2026-08-27 — heads trained, pick-blend deliberately NOT wired:*
  *(a) Value heads shipped (`scripts/train_draft_value.py` →
  `data/models/draft_value_v1.json.gz`, dependency-free inference in
  `sts2bot/learn/gbt.py`, lightgbm parity-tested): win head test AUC .684, boss
  head .757, calibrated; per-run row weights + by-run early stopping after the
  first fit memorized run identity (train .989/test .634 — effective n is ~2.2k
  runs, not 60k rows). These are the learned capability estimates for rest/path
  consumers and P(win)-trace diagnostics.*
  *(b) ΔV = V(deck+card)−V(deck) as a PICK signal FAILED face validity (prefers
  Cinder/Thunderclap over Impervious/Offering): observational confounding — deck
  archetype correlates with winning; the delta is not causal. Do not blend it.*
  *(c) The pick signal instead: `scripts/offer_counterfactuals.py` (offers are
  quasi-random given act → ITT per card, ÷ pick-rate ≈ per-pick effect; report in
  logs/reports/). Headline: STAMPEDE worst in the era (−16pp per-pick, n=1076) —
  independently corroborates the owner's live-spotted Kaiser trap, era predates
  the fix; SWORD_BOOMERANG second-worst (−10pp) = same random-target class;
  EVIL_EYE −6pp at 57% bot pick rate and BLOODLETTING/COLOSSUS mildly negative at
  both row and fixed-exposure run level = owner-review candidates. Rankings feed
  snapshot A/Bs, not automatic weight changes. Run-level table uses a first-3-
  drafts exposure window — offered-EVER is length-biased (deeper runs see more
  offers; v1 of the table fell for it).*
  *(d) 2026-08-27 owner review + conditional pass
  (`scripts/conditional_counterfactuals.py`): act IS a signal (engines decay by
  act 3, cheap attacks flip positive); Howl From Beyond flips sign on support
  (its declared exhaust_enabler need does not discriminate — mis-specified?);
  Bloodletting flat across acts and needs → suspicion moved to play-time
  HP-spend pricing (fights-level follow-up). ΔV rescue candidates, in order:
  score-margin regression discontinuity (margins logged; 2.8k era drafts < 0.5
  margin), R-learner on offer randomization, short-horizon V targets. Owner
  watches: Pact's End (old exhaust→PE planner bug), Demon Form rating, Howl
  overpick.*
- [ ] **Stage 2 — fit the combat evaluator's weights**: black-box optimization
  (Optuna/CMA-ES) of the existing `_score` weights against rollout-sim outcomes +
  live validation. "RL for card play" in its safest form: search keeps deciding.
- [ ] **Stage 3 (only if 1–2 pay)**: small learned net replacing the linear `_score`
  inside the DFS; sim self-play + live corpus. GPU-optional, CPU inference.
- **Out of scope**: end-to-end policy nets, joint draft+play models, anything whose
  data needs exceed passive batches on the owner's machine(s). Caveat pinned: the sim
  is approximate (audit found real gaps weekly) — a learned evaluator will exploit sim
  errors as eagerly as enemies; live corpus + snapshot A/Bs stay ground truth.

Complementary zero-data lever: the 2s/decision budget is underspent — search
depth/rollout count can be raised independently of any learning.
