# StS2 Bot — Requirements

*Drafted 2026-06-11 from [RoughInitialPrompt.md](RoughInitialPrompt.md) plus initial research.
Status of each researched fact is marked: ✅ = multiple sources agree, ❓ = verify against the
local install before relying on it.*

---

## 1. Vision

Build a bot that plays **Slay the Spire 2** (Steam, open access) competently and autonomously,
using deterministic code for the vast majority of decisions and LLMs only where judgment is
hard to encode. The project doubles as a capability demonstration: most code is written by
Claude (Fable 5), with the human owner available for key decisions, Steam-side setup, and
physical access to the machine.

**The headline deliverable is "the climb":** starting from a fresh in-game profile, win at
every Ascension level from 0 up through **Ascension 10 on each of the five characters**,
handling content/character unlocks along the way. Reference point: top human players hold
\>90% win rates at A10, so a competent bot should aspire to a meaningful (not necessarily
elite) win rate, and "how good can it get" is an explicit secondary goal.

## 2. Deliverables & Milestones

| ID | Milestone | Definition of done |
|----|-----------|--------------------|
| M0 | **Plumbing** | Bot launches the game, reads full game state, and completes an entire run end-to-end (win not required) with a trivial policy, unattended, including menu/reward/event/map handling and post-run cleanup. Detailed logs produced. |
| M1 | **Competence** | Bot wins ≥40% of runs at Ascension 0 with at least one character over a ≥20-run sample. |
| M2 | **First summit** | Bot completes the A0→A10 climb (a win at every level) with one character. |
| M3 | **The climb** | A10 win achieved on all five characters (Ironclad, Silent, Defect, Regent, Necrobinder ✅), from a fresh profile, all unlocks earned by play. |
| M4 | **Optimization (open-ended)** | Push sustained A10 win rate as high as possible; post-run analysis loop demonstrably improves play over time. |

Progress metrics (win rates per character/ascension, run counts, climb status) must be
computable from logs at any time.

## 3. Hard Constraints & Principles

- **C1 — Protect the owner's profile.** The bot plays on a separate in-game profile
  (StS2 supports multiple profiles with per-profile save folders ✅; STS2MCP exposes
  profile switching ✅). Before the bot's first launch: full backup of the StS2 save
  directory, and a decision about Steam Cloud sync (❓ — cloud sync could propagate or
  clobber saves; likely disable for this game or verify per-profile isolation).
- **C2 — Deterministic-first.** Standard code makes every routine decision. LLM calls are
  reserved for judgment that is genuinely hard to encode (see §6). Every LLM call is
  counted, logged with purpose + token usage + cost estimate, and visible in a running
  usage report. The bot must function (possibly degraded) with LLM calls disabled.
- **C3 — Legitimate play.** No savescumming, no memory editing of outcomes, no exploiting
  the mod layer to peek at hidden information (e.g., undrawn cards, unrevealed map content,
  future RNG) beyond what a human player could know. The mod layer is an *interface*, not
  a cheat. Win rates should mean something.
- **C4 — Respectful data use.** Spirebird (and any wiki/community source) is fetched as
  one-time downloads or occasional manual/rate-limited refreshes — never hammered. Prefer
  official exports (Spirebird has a `cohort_stats.json` export ✅) and local game-file
  extraction over scraping.
- **C5 — Patch resilience.** The game is in open access and patches frequently. The bot
  must record the exact game version per run, detect schema/content mismatches (unknown
  cards, changed enemies), and **halt gracefully with a clear report** rather than flail.
  Adapting to patches is part of the project, not an exception to it.
- **C6 — Observable.** Every decision the bot makes is logged with the state it saw and the
  reason (numeric scores at minimum). A human should be able to reconstruct any run
  decision-by-decision after the fact.

## 4. Technical Foundation (researched)

- **Engine:** Godot 4.5.x custom build ("MegaDot"), with game logic in **C#/.NET**
  (`sts2.dll`) ✅. Game assets in Godot `.pck` files; C# is decompilable for reference ✅.
- **Modding:** Official built-in mod loader (`/mods` folder + `manifest.json`, Steam
  Workshop, "Play with Mods" launch option) ✅. Mods are C# assemblies using **Harmony**
  runtime patching; modding contracts are version-sensitive ✅.
- **Game I/O — key prior art:** [STS2MCP](https://github.com/Gennadiyev/STS2MCP) (MIT,
  ~400★, actively maintained, tested vs StS2 v0.103.2 as of May 2026 ✅) is a mod exposing
  game state + actions over a localhost REST API (`localhost:15526`), including menu/lobby
  control, profile switching, popup/tutorial handling, and an optional MCP wrapper.
  **Plan-of-record: build on a fork of this mod** (extend endpoints as needed) rather than
  writing a mod from scratch. Exact action-endpoint coverage ❓ (docs incomplete; audit the
  source early — this is the first technical task).
- **Anti-automation risk:** none identified — single-player game, officially moddable, no
  known anti-cheat ✅. (Achievements/leaderboards: don't care / don't manipulate.)
- **Data sources:**
  - [Spirebird](https://spirebird.com) (jorbs' community stats): card Elo/WAR/win-rate,
    per-character relic stats, events, potions, encounters, campfire actions, with
    ascension cohort filters ✅. Primary source for **numeric priors** on card/relic value.
  - Game files / compendium API: ground-truth card/relic/enemy/potion data for the
    installed version (STS2MCP exposes a compendium endpoint ✅).
  - Wikis (slaythespire.wiki.gg, sts2.gg) for mechanics reference during development.
- **Save data:** per-profile folders under the StS2 app-data directory (exact path ❓),
  including a `current_run.save` — useful for crash recovery and backup tooling.
- **Characters:** 5 at open access — Ironclad, Silent, Defect, Regent, Necrobinder ✅, with
  an unlock chain on fresh profiles (e.g., Necrobinder unlocks via a completed Regent run
  ❓) plus per-character card/relic unlock progression (❓ assumed similar to StS1).
- **Ascension:** user states A10 is the current cap; some sources claim 20 levels ❓.
  Target is A10 regardless; anything beyond is stretch (M4).

## 5. Functional Requirements

### 5.1 Game I/O layer (the mod + client)
- FR-1.1 Read complete *player-visible* game state as structured data: combat (hand,
  energy, piles counts/contents as visible, enemy intents/HP/statuses, own
  statuses/powers), map, deck, relics, potions, gold, HP, shop inventory, event text +
  options, card/relic reward choices, current act/floor, run seed, ascension, character.
- FR-1.2 Execute every player decision type: play card (with target), use/discard potion,
  end turn, map node choice, reward picks/skips, shop buy/remove, event option, rest-site
  action, card select prompts (discard/exhaust/upgrade/transform...), Neow-equivalent
  start bonuses, run start (character + ascension) and abandon, menu navigation,
  profile selection, popup dismissal.
- FR-1.3 Survive the real client: detect and recover from unexpected popups, tutorial/FTUE
  interruptions, game-over screens, version-update dialogs; relaunch the game after
  crashes; resume an in-progress run from save after restart.
- FR-1.4 Report game version + mod version; refuse to act when state schema doesn't match
  expectations (per C5).
- FR-1.5 (Throughput, after M0) Support accelerated play where feasible — e.g., animation
  speed/timescale tweaks via the mod — with a "watchable" mode preserved (see §8).

### 5.2 Knowledge base
- FR-2.1 Versioned local card/relic/enemy/potion/event database for the installed game
  version, built from game data (compendium/decompiled resources), refreshed on patch and
  diffed (new/changed/removed content flagged).
- FR-2.2 Numeric priors per card/relic (pick value, WAR/Elo-style scores, per-character,
  ideally per-ascension-cohort) imported from Spirebird exports; refresh manual/occasional
  (C4).
- FR-2.3 Unknown-content handling: content present in game but absent from KB is flagged,
  playable via safe defaults, and queued for evaluation (LLM-assisted, §6).

### 5.3 Decision engine
- FR-3.1 Distinct, independently testable policies per decision domain: combat play
  sequencing & targeting, potion use, map routing, card reward picking, upgrade priority,
  shop purchasing, event choices, rest-site choice, starting-bonus choice.
- FR-3.2 Combat policy must reason at least one step ahead (e.g., simulate/score candidate
  plays for damage, block vs incoming intent, status effects, energy) — pure greedy
  card-by-card play is insufficient for A10. Depth of search/simulation is an
  implementation choice, but the evaluation function must be tunable from configuration
  (not hardcoded constants scattered in code).
- FR-3.3 Deck-building policies must be archetype-aware (synergy-seeking, curve/deck-size
  aware, character-specific), seeded from Spirebird priors, tunable per §6 feedback loop.
- FR-3.4 All policy parameters live in versioned config files so post-run analysis can
  propose diffs, and changes are attributable in run logs (config hash per run).

### 5.4 Run orchestration ("climb manager")
- FR-4.1 Unattended operation across many runs: start runs per climb policy (which
  character, which ascension), handle unlock gates, stop conditions (time budget, run
  count, error), crash/hang watchdog with game relaunch.
- FR-4.2 Climb policy: configurable character rotation vs. focus; default proposal —
  rotate characters at the lowest unbeaten ascension to spread learning, prioritizing
  unlock-chain progress first. (Owner explicitly delegated this choice; revisit with data.)
- FR-4.3 Safe-stop: finish or abandon current run cleanly, never corrupt saves.
- FR-4.4 Supervision modes: **attended** (current default) — owner starts the bot, is
  nearby, can pause/stop instantly, watch-friendly; **unattended** — multi-run overnight
  operation with watchdog, enabled only when the owner explicitly switches it on. The
  architecture treats unattended as a first-class mode from day one; the default just
  stays attended until trust is earned.

### 5.5 Logging, analytics, replay
- FR-5.1 Structured per-run log (JSONL or similar): every state snapshot + chosen action +
  policy scores/rationale + RNG-visible context, plus run header (game version, config
  hash, seed, character, ascension) and outcome summary.
- FR-5.2 Run index (e.g., SQLite) with queryable aggregates: win rate by
  character/ascension/config version, death causes, floor reached, climb progress.
- FR-5.3 Post-hoc replay tooling: re-run a policy against logged states offline (for
  debugging and for regression-testing policy changes against historical decisions).
- FR-5.4 LLM usage ledger: every call's purpose, model, tokens, $ estimate, cumulative
  totals (C2). Surfaced in a status report.

### 5.6 LLM integration (judicious)
- FR-6.1 **Post-run analyst:** after a run (or batch), an LLM reviews the run summary +
  key decisions and produces (a) a readable run debrief, (b) proposed config-parameter
  diffs with reasoning, gated by human-auditable changelog before adoption. Model
  selection configurable (cheap default; "deep review" on demand, potentially Fable 5 in a
  dev session rather than via API).
- FR-6.2 **Unknown-content triage:** when a patch adds/changes cards/relics/events, an LLM
  rates the new content once (vs. existing priors), cached until next change (C5, FR-2.3).
- FR-6.3 **Optional narrator:** a cheap model (e.g., Haiku) produces short
  decision-narration for spectating/streaming; strictly off by default, rate-limited,
  feel-dependent (owner may kill it if grating).
- FR-6.4 Hard budget controls: per-run and per-month call/cost caps; bot continues
  (degraded) when cap is hit.

### 5.7 Spectating (QoL, post-M2 unless trivial)
- FR-7.1 The real game client renders anyway — "watch mode" = normal animation speed +
  optional narration overlay/console.
- FR-7.2 Twitch streaming integration is **out of scope initially** (revisit after M3);
  design should not preclude it (e.g., narration as an OBS-readable text source).

## 6. Non-Functional Requirements

- **NFR-1 Stack:** Bot brain in **Python 3.12+** (rich ecosystem, fast iteration); mod
  fork in C#/.NET (matching STS2MCP). Windows 11 host (this machine).
- **NFR-2 Testing:** decision policies unit-tested against fixture states (replayed from
  logs); KB import and config parsing tested; CI-ready layout even if CI comes later.
- **NFR-3 Operability:** one command to start/stop the whole stack (game + mod + bot);
  status report (current run, climb progress, LLM ledger) accessible while running and
  written to disk on stop.
- **NFR-4 Code history:** git from day one (owner sets up the remote; local repo
  immediately). Meaningful commit messages; config changes (FR-3.4) committed, so the
  evolution of the bot's "opinions" is in history.
- **NFR-5 Cost discipline:** development favors free/local resources (game files, one-time
  Spirebird exports); LLM spend per §5.6 caps.

## 7. Key Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| STS2MCP action coverage incomplete for full unattended runs | High | Audit source first; we fork and extend (MIT). Worst case: write our own mod using its patterns. |
| Game patches break mod/state schema | High | Release branch chosen (§8.1); C5 halting behavior; record game+mod version per run; budget time for repair after each patch. |
| Combat too complex for chosen search depth → low win rate ceiling | Medium | Tunable eval + replay regression harness (FR-5.3) enables iterating; Spirebird priors reduce deck-building error; accept "competent ≠ optimal". |
| Throughput too low for the climb (≥55 wins + losses; runs are 30–60 min at human speed) | Medium | FR-1.5 acceleration; unattended overnight operation (open decision #3). |
| Steam Cloud / profile contamination of owner's saves | Medium | C1 backups + cloud-sync decision before first bot launch. |
| Spirebird data shape ≠ what policies need | Low | Compendium + manual priors as fallback; LLM triage (FR-6.2). |

## 8. Decisions (resolved with owner, 2026-06-11)

1. **Game branch: → release/default branch.** Owner will flip the Steam beta setting off.
   Better mod compatibility; patch adaptation still in scope, just calmer.
2. **LLM usage: → hybrid.** Automated cheap calls (triage, debriefs, optional narration)
   under a hard cap (~$20–30/mo, FR-6.4); deep periodic reviews run as Fable 5 dev
   sessions in Claude Code over the logs, at no API cost.
3. **Runtime: → attended-first, unattended-capable.** Owner wants eyes on it initially;
   unattended (overnight/away) operation must exist and be switchable on request, but is
   off by default for now (FR-4.4).
4. **Pacing: → fast by default.** Accelerated play where the mod allows; watchable normal
   speed as a toggle (FR-1.5, FR-7.1).

## 9. Out of Scope (initially)

Multiplayer/co-op; Twitch streaming infra (FR-7.2); custom content mods; non-Windows
hosts; playing ascensions beyond the current cap; leaderboards/achievements; perfect-play
research (we want *competent and improving*, not solved).

## 10. References

- Prior art: [STS2MCP](https://github.com/Gennadiyev/STS2MCP) ·
  [StS2 modding tutorial](https://github.com/fresh-milkshake/Modding-Tutorial) ·
  [bottled_ai (StS1)](https://github.com/xaved88/bottled_ai) ·
  [ForeverVirus AIBot (StS2, in-game agent)](https://github.com/ForeverVirus/Slay_The_Spire_2_AIBot)
- Data: [Spirebird](https://spirebird.com) · [sts2.gg](https://sts2.gg) ·
  [slaythespire.wiki.gg](https://slaythespire.wiki.gg)
- Engine: [Godot showcase — StS2](https://godotengine.org/showcase/slay-the-spire-2/)
