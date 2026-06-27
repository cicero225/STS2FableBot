# HANDOFF — "you are here" (2026-06-26)

Quick spin-up note for continuing on another machine. Read order: **CLAUDE.md →
REQUIREMENTS.md → PLAN.md** (PLAN.md is the real lab notebook; this file is just the
pointer). Delete/refresh this when it goes stale.

## Where the project is
- **First-ever A0 win landed this session** (floor 48). The headline 0-wins wall is broken;
  Act-1-boss clear holds ~44%. **The binding wall is now the Act-2 boss** (Kaiser Crab /
  Knowledge Demon, floor 33) — confirmed by batch `ble3lyl8a` (10 runs, clean, 0 wins but
  4/10 past Act 1, 1 deep into Act 3 @ f39).
- **Current config hash: `374480217e9e`** (`config/policy.toml`). 232 tests green, ruff clean.

## Landed this session (all committed; details in PLAN §8.4 / §8.4-A / §8.4-B)
- Combat-modeling pass: Artifact, Pen Nib, in-combat healing (Not Yet), one-time crossing-based
  stun (Ceremonial Beast Plow), Waterfall invincible/DeathBlow, **Vantom stacked Slippery**,
  player **Weak/Frail**.
- **Artifact VALIDATED LIVE** (tripwire caught it 4× in the batch; planner withholds debuffs
  into Artifact). **Pen Nib still unvalidated** — never rolled yet.
- Act-1 boss deep-dive (6 bosses) + Act-2 dive: **Kaiser Crab fully modeled** — Crab Rage
  enrage + back-attack/facing (killing a claw is a *boon*, ends Surrounded) + Bug Sting Weak/Frail.

## TEMP code to remove later
- `loop.py` **Artifact/Pen-Nib tripwire** (fenced `>>> TEMP TRIPWIRE <<<`) + its test in
  `tests/test_mock_run.py`. Delete once **Pen Nib** is also validated live (Artifact is done).

## Open / next (no particular order — see PLAN for full list)
- **Knowledge Demon "Choose a Card"** debuff-selection policy (the one substantive Act-2 item left).
- §5-C multi-turn pass: player-debuff half (b) **DATA-BLOCKED** (needs a live Lagavulin/Kin trace
  for Soul Siphon params); Lagavulin asleep-window; Waterfall Steam-Eruption stack (part a);
  `block_per_turn` ignores passive relic/power block; Apotheosis power-adjacent-Skill (Tier-2).
- Validation cadence (owner): frugal **10-run** batches for boss/mechanic checks, full 40 only for
  win-rate. Run: `.venv\Scripts\sts2bot.exe play --runs 10 --speed 4 --profile 1` (profile 1 = the
  bot's own modded slot, C1-safe). Needs game running + mod built.

## New-machine setup
- `python -m venv .venv; .venv\Scripts\pip install -e .[dev]`
- Re-clone the mod FORK (not upstream): `git clone https://github.com/cicero225/STS2MCP external/STS2MCP`
  then re-apply `patches/STS2MCP-newbuild-fix.patch` (see CLAUDE.md). Only needed for live runs.
- `.venv\Scripts\python -m pytest` to confirm green.
