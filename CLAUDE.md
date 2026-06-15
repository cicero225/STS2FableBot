# StS2FableBot

Bot that plays Slay the Spire 2 via the STS2MCP mod's localhost REST API. Deterministic
Python decision engine; LLMs only for post-run analysis, new-content triage, optional
narration — every LLM call goes through the ledger (budget-capped).

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
- Reference clone (gitignored, re-clone if absent):
  `git clone --depth 1 https://github.com/Gennadiyev/STS2MCP external/STS2MCP`
  — API docs at `external/STS2MCP/docs/raw-full.md`.

## Conventions

- Commit per coherent step; policy-config changes get their own commits.
- Config lives in `config/*.toml`; run logs record the config hash — don't hand-tweak
  weights without committing.
- Update PLAN.md phase checkboxes / open-items table as work lands.
