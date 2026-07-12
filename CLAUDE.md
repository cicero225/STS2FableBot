# StS2FableBot

Bot that plays Slay the Spire 2 via the STS2MCP mod's localhost REST API. Deterministic
Python decision engine; LLMs only for post-run analysis, new-content triage, optional
narration — every LLM call must go through the ledger (budget-capped). *(Neither exists
yet: `sts2bot/llm/` is an empty stub and the bot makes no LLM calls — PLAN P1.8.)*

**Read first:** [REQUIREMENTS.md](REQUIREMENTS.md) (what & why, constraints C1–C6),
[PLAN.md](PLAN.md) (architecture, current phase, open items), LOG.md (lab notebook of
live sessions, once it exists).

## Hard rules

- **C1:** never touch the owner's game profile (bot owns its own modded profile slot).
  Save safety: `scripts/backup_saves.py` (full-tree backup, before risky work) ·
  `sts2bot play` auto-snapshots the bot profile after each run to
  `backups/profile_snapshots/` · `scripts/restore_saves.py --list|--restore|--full`
  to restore. **Steam Cloud should stay OFF for StS2** — it reshuffled the modded
  profiles once (2026-06-14); local backups are the source of truth.
- **C3:** no cheating — the mod is an interface, not an oracle. Only player-visible info.
- **FR-4.4:** live game runs are *attended* (owner present) unless owner explicitly
  enables unattended mode.
- Policies are pure functions `(state, kb, config) → (action, scores, rationale)`;
  no I/O in `sts2bot/policy/`.

## Dev environment

- Windows 11, PowerShell. Python 3.14 venv at `.venv/`:
  `.venv\Scripts\python.exe` (activation not required; call the venv python directly).
- Install: `python -m venv .venv; .venv\Scripts\pip install -e .[dev]`
- Test: `.venv\Scripts\python -m pytest` · Lint: `.venv\Scripts\python -m ruff check .`
- Mock-first: build/test everything against fixtures in `tests/fixtures/` before live.
- Mod source (gitignored, re-clone if absent) — clone **our fork**, not upstream:
  `git clone https://github.com/cicero225/STS2MCP external/STS2MCP`
  The fork = upstream `Gennadiyev/STS2MCP` + commits the bot depends on (master `deck` in
  state, `set_time_scale`/`set_ascension` actions, `actions_disabled`). Building from upstream
  silently drops `player.deck` → drafting + elite gate no-op (regression hit 2026-06-23).
  API docs at `external/STS2MCP/docs/raw-full.md`. Build: `external/STS2MCP/build.ps1
  -GameDir "<game dir>"` (outputs to `out/`, does NOT install — copy to game `mods/` yourself).
  Game dir: `I:\SteamLibrary\steamapps\common\Slay the Spire 2` (main machine, since
  2026-07-12; the July laptop stint used `C:\Program Files (x86)\Steam\...`). After a
  re-clone, check out the **`v107-fork` branch** — it carries the v0.107.1 game-API compat
  fix that used to live in `patches/STS2MCP-newbuild-fix.patch` (patch kept for reference;
  it no longer applies on top of the branch).

## Conventions

- Commit per coherent step; policy-config changes get their own commits.
- Config lives in `config/*.toml`; run logs record the config hash — don't hand-tweak
  weights without committing.
- Update PLAN.md phase checkboxes / open-items table as work lands.
