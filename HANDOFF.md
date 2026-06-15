# Fable 5 Handoff / Continuation Point

*Written 2026-06-14. This branch (`fable5-handoff`) is a frozen snapshot of the
project as it stood at the end of Fable 5's work, preserved so the project can be
resumed from here if Fable 5 is re-enabled.*

---

## 0. Why this document exists

This project ([StS2FableBot](https://github.com/cicero225/STS2FableBot)) was built
across four sessions by **Claude Fable 5**, partly as a working bot and partly as a
test of Fable 5's coding capabilities on a long, uncertain, real-world problem. Fable
5 was then disabled (external/regulatory reasons), and the owner asked **Claude Opus
4.8** to continue the project on `main`.

Before continuing, Opus cut this branch as a clean bookmark. **Everything on this
branch up to its tip is Fable 5's work.** If Fable 5 returns and you want to continue
*its* timeline (the capability test), check out this branch and pick up from §6 (the
backlog). `main` will, separately, carry Opus's continuation — those are two parallel
timelines on purpose. Merge them later if desired; nothing here depends on that.

If you are a fresh agent (Fable 5 or otherwise) reading this cold: read
[CLAUDE.md](CLAUDE.md) → [REQUIREMENTS.md](REQUIREMENTS.md) → [PLAN.md](PLAN.md) →
[LOG.md](LOG.md), then this document's §3 (state) and §6 (what's next). The four
core docs are the durable spec; this file is the narrative glue and resume guide.

---

## 1. The one-paragraph summary

A bot that plays **Slay the Spire 2** (Steam, open access, build v0.103.3, release
branch) autonomously. Deterministic Python decision engine drives a forked community
mod ([STS2MCP](https://github.com/cicero225/STS2MCP)) that exposes game state + actions
over a localhost REST API. The bot reliably reaches **Act 1 bosses (floor ~17)** and
has reached the **Act 2 boss** once (floor 33); it has **not yet won a run** (0/34).
Boss fights are the current ceiling. The headline deliverable is "the climb":
A0→A10 on all five characters from a fresh profile. We are early in that climb —
still proving baseline competence on Ironclad A0.

---

## 2. The narrative log (session by session)

This is the "conversation log" the owner asked to preserve — a faithful account of
what was discussed, decided, and built, including the human observations that drove
most of the tuning. The owner watched runs live (often streaming) and fed back
specific in-game observations; Fable 5 root-caused each from the decision logs and
shipped a tested fix, usually within ~15 minutes. That human-in-the-loop tuning loop
(§5) was the most productive part of the project and is the main thing to preserve.

### Session 0 — Requirements, planning, P0 plumbing (2026-06-11)
- Started from the owner's `RoughInitialPrompt.md` (still in repo). Researched the
  StS2 technical surface: **Godot 4.5 + C#/.NET**, official mod loader, and crucially
  the **STS2MCP** community mod — a localhost REST bridge that is effectively the
  "Communication Mod" of StS2. Audited its source: action coverage near-complete.
  This retired the project's biggest risk ("can we even drive the game?").
- Wrote [REQUIREMENTS.md](REQUIREMENTS.md) (constraints **C1–C6**: protect owner's
  profile, deterministic-first, legitimate play / no cheating, respectful data use,
  patch resilience / fail-loud, observability) and resolved four scoping decisions
  with the owner: **release branch**, **hybrid LLM usage**, **attended-first** runtime,
  **fast-by-default** pacing.
- Built the P0 Python scaffold (Python 3.14 venv, pydantic/httpx/typer, ruff/pytest),
  typed client for all 18 documented state types, action senders, the agent loop
  (poll → parse → route → act → log) with stall/error safety rails, trivial
  first-legal-choice policies, JSONL decision logs + SQLite run index, and a scripted
  **mock game** so the whole loop is testable offline before ever touching the game.
- **First live session (M0):** installed STS2MCP 0.4.0, confirmed save isolation
  (modded save scope is a physically separate tree; the bot uses modded `profile1`,
  owner's vanilla saves untouched and backed up). First complete live run: trivial
  policy, Ironclad, died floor 9, dismissed game-over, returned to menu. Found and
  fixed 3 doc-vs-live gaps (transitional combat state with no `battle` block;
  character-select lingering after embark; the singleplayer menu structure). Added
  outcome enrichment from the game's own `saves/history/*.run` records (authoritative
  win/seed/build/killed_by). Discovered the **Timeline epoch-reveal gate** (after
  meta-progression milestones the main menu hides `singleplayer` until the owner
  manually reveals an epoch — the mod refuses to automate this; bot waits MANUAL).

### Session 1 — C# fork: the character-select bug (2026-06-11)
- Owner forked STS2MCP to their account; cloned to `fork/` (gitignored), `upstream`
  remote wired. Installed .NET 9 SDK; used `ilspycmd` to decompile `sts2.dll` into
  `external/decompiled/` for reference.
- **Root-caused a subtle bug:** when a character unlock is pending, the game's
  `NCharacterSelectScreen.PlayUnlockCharacterAnimation` runs async and `Select()`s the
  newly-unlocked character ~1s after the screen opens, silently overwriting any pick
  made via the API; embark then starts the wrong character. Worse,
  `NCharacterSelectButton.Select()` no-ops while a stale `_isSelected` flag is set, so
  naive re-selection couldn't recover.
- **Fork fix (commit `7e4977a`):** `Deselect()` then `Select()` to force the full
  commit path; refuse picks (retryable) while an unlock animation owns the screen;
  expose `selected_character` + `selection_busy` in state. Bot side: a
  verify-before-confirm navigator (re-select until `selected_character` matches, then
  embark). **Live-verified** with deliberate Ironclad + Silent picks — and the unlock
  animation race actually fired and was handled correctly, twice, silently in
  production.

### Session 2 — C# fork: remaining features (2026-06-11)
- Added to the fork (`a84c9e1`): **master deck** in player state, **`set_time_scale`**
  (engine speed, for fast batches), **`set_ascension`** at character select (drives
  `NAscensionPanel`). Bot side: `DeckCard` model, `--speed`/`--ascension` CLI flags.
- Live-verified all three. Two follow-ups: the game's cinematics reset
  `Engine.TimeScale` to 1.0 (so the loop now **re-asserts** the configured speed every
  ~25 decisions), and the `.run` records pad the unused killer slot with a truthy
  `"NONE.NONE"` (cleaned before use, or event deaths were masked).

### Session 3 — P1: real decision policies (2026-06-11 → 06-12)
- This is where the bot stopped being plumbing and started playing. Built: a **config
  layer** ([config/policy.toml](config/policy.toml) + loader, hash recorded per run for
  attribution), **textparse** (regex extraction of damage/block/draw/debuffs/HP-cost
  from rules text + intent labels), a **one-turn combat planner** (DFS over
  energy-feasible card sequences with target branching and a minimal effect
  simulation, weighted scoring), and the **StandardRouter** covering combat, map,
  events, card rewards, rest, shop, and potions.
- Added a **replay harness** (`sts2bot replay`) that runs any policy over *every*
  state the bot has ever logged — so each policy change is validated against thousands
  of real historical states before going live.
- Tuning iterations from logged post-mortems: focus-fire scoring (lost to a pack from
  full HP), potion heal/hail-mary rules, `actions_disabled` handling (fork `56f41da` —
  scripted combat lockouts look actionable but reject input), act-level **map path
  planning** over the full DAG (stop walking into forced-elite lanes),
  **rest-before-boss**, the generic **death-countdown survival rule** (The Insatiable's
  "Sandpit" — play the injected escape card when the counter is low).
- **Reached the Act 2 boss** (The Insatiable, floor 33) — two full acts deeper than
  the trivial-policy ceiling of floor 11.

### Session 4 — Spirebird priors + the pilot-skill tuning night (2026-06-12)
- Owner exported `cohort_stats.json` from [spirebird.com](https://spirebird.com)
  (**440,240 community runs**; one-time export, per C4). `scripts/build_priors.py`
  distills it to a committed **53 KB** table ([data/priors_cards.json](data/priors_cards.json)):
  picked-weighted, sample-size-shrunk Elo per (card, character). **100% coverage** of
  every card the bot has ever been offered. These drive card-reward picks.
- The priors-only batch did **not** move the win rate by itself. The owner's key
  insight: **community Elo prices cards for a skilled pilot the bot isn't yet.** This
  produced seven owner-observed, log-diagnosed, regression-tested fixes in one night:
  1. **Pilotability discount** — positive priors are scaled down for cards whose value
     the planner can't cash in (conditional/synergy text ×0.7, unparseable ×0.45);
     negative priors stay full strength.
  2. **Max-HP drain** parsed as a heavy cost (the "vampire" event had killed 3 runs
     while reading as free).
  3. **Play friction** — each card played costs a little, stopping "energy generator →
     pointless Defends vs a non-attacker."
  4. **Barricade-aware block scoring** — the exception to #3 (persistent block is never
     waste).
  5. **Offering trio** — drawn cards revalued (`w_draw` 1.5→3.0), HP-cost scaled by
     scarcity (cheap at full HP, ruinous when low), and a **desperation draw** (play a
     survivable draw card when facing lethal rather than dying with it in hand).
  6. **One potion per round** + treat "already queued" as transient (a used potion
     lingers visibly in the belt; the gate re-fired 8× and railed); plus a **strict
     `.run` watermark** so an errored, unfinished run can't inherit the previous run's
     record.
  7. **Rescue plays target properly** (desperation fired an attack-that-draws with no
     target, railing 8×).

---

## 3. Current system state

- **Metrics:** 34 runs logged, **0 wins**. Reliably reaches Act 1 bosses (floor ~17,
  five times in session 4). Three Act 1 bosses catalogued (Vantom, **Ceremonial Beast**
  — 3 losses, the project's nemesis — and The Kin) plus 2 Act 2 trips and 1 Act 2 boss
  encounter (The Insatiable). **Boss fights are the ceiling.**
- **Tests:** 101 passing (`pytest`). Replay harness clean over all ~6,000+ logged
  states. Lint clean (`ruff`).
- **Architecture** (see PLAN.md §1 for the diagram):
  - `sts2bot/client/` — typed REST client, state models (`models.py`), actions.
  - `sts2bot/policy/` — pure decision functions. `trivial.py` (plumbing + the
    menu navigator, still used for menus/overlays), `standard.py` (the real P1
    policy set), `combat.py` (one-turn planner), `textparse.py`, `base.py` (protocol).
  - `sts2bot/kb/` — `config.py` (typed policy.toml), `priors.py` (Spirebird table).
  - `sts2bot/orchestrator/loop.py` — the agent loop, safety rails, time-scale
    re-assertion, outcome enrichment.
  - `sts2bot/runlog/` — JSONL decision logger, SQLite index, `.run` record reader.
  - `sts2bot/replay/` — offline policy re-evaluation over logged states.
  - `config/policy.toml` — **all tunable weights** (FR-3.4). Change behavior here,
    commit it, and the run index attributes runs to a config hash.
- **The C# mod fork** lives in its own repo, [cicero225/STS2MCP](https://github.com/cicero225/STS2MCP),
  cloned to `fork/` (gitignored). Currently at **`fork.3`** (`56f41da`): char-select
  fix, master deck, set_time_scale, set_ascension, actions_disabled. Built with
  `.NET 9` via `fork/STS2MCP/build.ps1`. The char-select fix and others are
  **PR-worthy upstream** but no PR has been opened (owner's call).

---

## 4. Environment & live-session protocol

- **Host:** Windows 11, PowerShell. Python **3.14** venv at `.venv/` (call
  `.venv\Scripts\python.exe` directly; no activation needed). uv is not installed.
- **Game:** Steam, install at `I:\SteamLibrary\steamapps\common\Slay the Spire 2`,
  build **v0.103.3**, **release branch**. Launch via Steam → **"Play with Mods"**;
  first launch each session may need a one-time in-game "Load Mods" + restart.
- **Save safety (C1):** the bot plays the **modded** save scope (`profile1`), which is
  a separate tree from the owner's vanilla saves. `scripts/backup_saves.py` zips all
  save locations to `backups/` (gitignored). Run it before risky live work.
- **The mod:** built/installed via `scripts/install_mod.py` (fetches latest release) or,
  for the fork, `fork/STS2MCP/build.ps1 -GameDir "...Slay the Spire 2"` then copy
  `out/STS2_MCP/STS2_MCP.dll` + `mod_manifest.json` (→ `STS2_MCP.json`) into the game's
  `mods/` folder. API on `http://127.0.0.1:15526`.
- **Reload rules (important):** **pure-Python changes need no game restart** — they
  take effect on the next `sts2bot play`. **Only C# fork changes** require rebuild +
  reinstall + game restart (the DLL is locked while the game runs, so the game must be
  fully closed to overwrite it).
- **Manual interventions the owner performs** (the bot surfaces these as `MANUAL`
  waits and waits patiently ~5 min):
  - **Timeline epoch reveals** after meta-progression milestones (first death, etc.).
    Owner opens Timeline in-game and advances. The bot will *not* touch an open
    Timeline (it would kick the owner off the screen).
  - Occasionally an opaque overlay/dialogue (first-Neow arrival, Ancients, the
    Architect ending) may need a click-through.
- **Commands:**
  - `.venv\Scripts\sts2bot doctor` — connectivity + profile check.
  - `.venv\Scripts\sts2bot play --runs N --policy standard --character IRONCLAD --speed 3.0`
    — run batches. `--speed` accelerates the engine (re-asserted during runs).
  - `.venv\Scripts\sts2bot replay --policy standard` — offline validation over all logs.
  - `.venv\Scripts\python scripts\show_runs.py` — the run-index scoreboard.
  - `.venv\Scripts\python -m pytest -q` / `python -m ruff check .` — tests / lint.
- **Background runs:** the owner cannot answer mid-run; long batches were run in the
  background and reported on completion. Attended-first is the default (owner watches);
  unattended is capable but switched on only on request (FR-4.4).

---

## 5. The working method (preserve this)

The loop that produced almost every improvement after M0:

1. Run a small live batch (3–5 runs) at high speed, owner watching.
2. The owner reports a specific in-game observation ("it drank potions when it had
   lethal in hand," "Offering goes unplayed," "it walked into a forced elite").
3. **Diagnose from the decision logs** — every decision records the full state it saw,
   the action, the rationale, and the numeric `scores`. `logs/runs/<stamp>/decisions.jsonl`.
   The answer is almost always already in the log.
4. Fix as a **config weight** if possible (attributable, no code), else code.
5. **Regression-test** it (reconstruct the situation from the logged fight data).
6. **Replay** over all historical states (`sts2bot replay`) to confirm nothing breaks.
7. Commit (separate commit for config changes), redeploy on the next batch.

This is the human-powered prototype of **FR-6.1 (automated post-run debriefs)**. The
next big leverage item is to automate it: have an LLM read fight transcripts, name the
losing pattern, and propose the config diff. Session 4 generated ideal training data
for exactly this.

---

## 6. What's next (the backlog, roughly prioritized)

1. **Boss-fight analysis.** The ceiling is floor-17 boss fights. Open question, fully
   answerable from logs: are losses due to (a) the one-turn planner's inability to set
   up multi-turn lines, (b) raw deck power, or (c) specific boss mechanics? The
   Ceremonial Beast (3 losses) and The Insatiable transcripts are logged and waiting.
   Likely needs either deeper combat lookahead (beam search over 2 turns / a partial
   simulator for common effects — PLAN.md §5 "phase C") or deck-archetype focus.
2. **FR-6.1 automated debriefs** — automate §5 (LLM reads logs → proposes config diffs,
   owner-audited). Plumbing is mostly there; the run logs are rich and structured.
3. **Deck-archetype awareness** in card rewards (synergy-seeking beyond per-card priors;
   the priors are per-card and don't see combos).
4. **Relic / shop / event priors** from the same Spirebird export (only cards are wired
   in so far; the export also has `relics` and `events` per cohort).
5. **Spectator narration** (FR-6.3, optional, owner-gated) once it's fun to watch.
6. **The climb proper** — ascension ramp, character rotation. Currently all runs are
   Ironclad A0. All five characters are unlocked on the bot profile.
7. **Open the upstream PR** for the fork fixes (char-select especially) if the owner
   wants to contribute back.

---

## 7. Known gotchas / watch items

- **Game patches** will eventually break the state schema. The bot fails loud
  (`StateParseError`, dumps the payload) per C5 — that's by design, not a crash to
  paper over. Record the new build, diff the schema, fix the model.
- **`config/policy.toml` is the steering wheel.** Most behavior is weights, not code.
  When a behavior looks wrong, check the logged `scores` first.
- **The combat planner is deliberately one-turn** (C5 patch-churn caution). It does
  *not* simulate drawn cards, multi-turn setups, or most conditional/synergy text —
  hence the pilotability discount on priors. Deepening this is the main lever for boss
  fights but raises maintenance cost; weigh carefully.
- **Two timelines now exist:** this branch (Fable 5's endpoint) and `main` (Opus's
  continuation). Don't accidentally cross them without intending to.
- The **Spirebird raw export** (`data/spirebird/cohort_stats.json`, 58 MB) is
  gitignored; only the distilled `data/priors_cards.json` is committed. To refresh:
  owner re-downloads the export, run `scripts/build_priors.py`.

---

*End of handoff. The torch passes to Opus on `main`; this branch keeps Fable 5's seat
warm. — Opus 4.8, 2026-06-14*
