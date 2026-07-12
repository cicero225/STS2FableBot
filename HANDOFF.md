# HANDOFF — "you are here" (2026-06-26)

> **2026-07-12: REVERSE HANDOFF COMPLETE — back on the MAIN machine.** Repo pulled
> (2eccfa5 + spin-up commits), venv rebuilt (Python 3.14), 280 tests green, logs MERGED
> (345 runs), bestiary rebuilt (75→101 enemies incl. all Act-3 bosses), card_effects
> 284, combat_stats re-grounded, catalog seen-set 149→176. Game v0.107.1 unchanged →
> June mod build still valid. **Profile verified: custom mode + Underdocks + Undergrowth
> unlocked, 4 wins — the seeded harness is BACK.** Steam Cloud confirmed OFF. The old
> `StS2bot` folder remains as archive-in-waiting (owner will archive it later).
> The checklist below is retained for reference:

> **2026-07-09 (superseded): REVERSE handoff pending — this (laptop) machine now has the NEWER state.**
> Owner returns to the MAIN machine evening of 2026-07-11. To move the project back:
> 1. **Repo**: ~15 commits ahead of the 07-08 transplant (through the elite-pool gate /
>    planner-blind dock work). Push to the remote if one exists, else copy the repo folder.
> 2. **Copy from THIS machine**: `logs/` (all July runs + manual win trace — bestiary
>    source data), `backups/` (profile snapshots + the Jun-12 cloud-recovery zips).
> 3. **Bot profile**: this machine's live profile (`%APPDATA%\SlayTheSpire2\steam\<id>\
>    modded\profile1\`) has the Underdocks/rare-potion unlocks + 1 of 3 Act-3 wins.
>    The MAIN machine's profile has custom mode + Undergrowth (all pre-move unlocks).
>    **Prefer the main machine's profile** (superset except the 07-08+ run history);
>    the unlock-track deposit mechanics are decoded in LOG (2026-07-08 cont. 3) if score
>    reconciliation is wanted.
> 4. **Claude context**: copy `%USERPROFILE%\.claude\projects\<this-repo's-key>\`
>    (transcripts + `memory/`) onto the main machine under the same key — same procedure
>    as the 07-08 transplant, opposite direction. Rename the key dir if the main machine's
>    repo folder name differs.
> 5. **Game-dir path** in CLAUDE.md will need re-pointing back if the main machine still
>    uses `I:\SteamLibrary`.

> **2026-07-08: spin-up on the new machine is DONE** (see LOG.md entry) — venv rebuilt,
> mod built from the fork's `v107-fork` branch and installed, bot profile restored from
> the pre-reshuffle Steam Cloud copy (Jun-12 state, ~2 weeks stale). Remaining: attended
> live smoke test; optionally restore a newer profile snapshot from the old machine.

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
- ~~`loop.py` **Artifact/Pen-Nib tripwire**~~ — **REMOVED 2026-07-09**: Pen Nib validated
  live (batch b0j3rzhj1; the owner's preview gotcha was real and is now modeled).

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
