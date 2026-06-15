# Lab Notebook

*Newest first. One entry per live session / milestone (see PLAN.md §6).*

## 2026-06-14 (session 5 cont., Opus) — Deck-power package + by-act priors

The boss analysis said deck power is the ceiling, so this stretch made the deck
actually improve:
- **Smart card-selection targeting.** Removal/transform was hitting arbitrary cards
  (first-legal fallback), so thinning never helped. Now remove/transform target the
  WORST cards (curses < un-upgraded basics < by prior), upgrade/enchant the BEST
  un-upgraded, add/choose the BEST. Live-confirmed: "select worst Strike for: Choose
  a card to Transform", "select best Bash for: Choose a card to Enchant".
- **Price-aware removal** (owner): don't pay >150g to remove (efficiency drops as the
  price escalates +50/use); skip removal when nothing's worth removing.
- **Card-select robustness.** A 'choose' screen returned select 'ok' but didn't always
  resolve, and the handler waited forever → run rail. Now every path is bounded
  (re-press then skip); live-confirmed un-sticking an abandoned run.
- **Hail-mary throws multiple potions** (owner): the one-per-round cap (Kin "already
  queued" fix) limited a death-turn to one potion. Now tracks used *slots* — regular
  use stays one/round, hail-mary drinks successive different potions until safe or empty.
- **By-act priors (8.1b).** warA/picked[act] gives per-act per-pick WAR, but it's
  survivorship-biased (act-3 picks come from winners). De-biased by subtracting the
  population per-act mean, centered per card, ≥300 picks/act, capped ±1.0 — a bounded
  secondary nudge (weight 3.0) toward act-appropriate cards. Directionally sound for
  cards that matter (Offering/Adrenaline/Footwork early, Whirlwind late).

Save-safety tooling also landed here (per-run profile snapshots + restore script) after
Steam Cloud reshuffled the modded profiles — see the entry below. 120 tests green,
replay clean over ~8.8k logged states throughout.

## 2026-06-14 (session 5, Opus) — Handover; boss-fight analysis; BlockedByHook fix

Fable 5 was disabled mid-project (it had been the builder through session 4); **Opus
4.8 takes over on `main`.** Per owner request, froze Fable 5's endpoint on branch
`fable5-handoff` (+ a detailed `HANDOFF.md`) so its timeline can be resumed if it
returns. Filed the owner's drafting/strategy backlog notes into PLAN.md §8 with
data-feasibility verdicts (by-act WAR present in the Spirebird export; synergy and
deck-size are gaps; relic/event priors + skill-band cohorts available).

**Boss-fight analysis (the greenlit work).** Reconstructed all 6 boss losses from the
decision logs. Two findings:
- **Strategic (the real ceiling): deck power, not the combat planner.** Decks at the
  boss are small (15–21) and basic-heavy (6–9 of the 10 starter Strikes/Defends still
  in). The one run that thinned hard (The Insatiable run, only 2 basics left) reached
  the deepest (floor 33). Two losses came at *full HP* — so it's not just HP
  management. The planner's sequencing looked sound (vuln-first, focus-fire, Fight Me!
  usage). **Conclusion: prioritize deck-building sophistication (removal cadence,
  upgrades, the owner's by-act/archetype drafting notes) over deepening combat
  lookahead.** This redirects PLAN.md's phase-C question — multi-turn search is not the
  bottleneck yet.
- **Tactical bug (fixed): transient `BlockedByHook` hands.** Run 33 (Ceremonial Beast):
  a planned triple-Defend collapsed to one, 14 HP → 3. Right after a play the engine
  briefly reports every card unplayable (reason `BlockedByHook`); the planner trusted
  it and ended the turn, dumping 10 block at 14 HP. Now re-polls (bounded) instead.
  Replay confirms it catches 4 such states in the historical logs. 104 tests green.

Rest-before-boss is working (it rested 16→46 pre-boss) but a single 30% rest can't
undo arriving that low — another symptom of weak decks taking too much Act-1 chip.

**Next:** deck-building sophistication (the strategic finding above), starting likely
with by-act priors (8.1b, data confirmed present) + smarter card removal/upgrades.

**Validation batch (later 2026-06-14, on restored modded profile 1).** Steam Cloud had
reshuffled the modded profiles; data was intact (modded/profile1, 63 KB) — added per-run
profile snapshots + a restore script + an immediate backup, and recommended Cloud OFF.
Then ran 3 Ironclad runs to validate the BlockedByHook fix and the backups:
- **Per-run backups confirmed** — one `modded-profile1_*.zip` per run in
  `backups/profile_snapshots/`.
- **Hook fix confirmed engaging live** — run 1's Ceremonial Beast fight hit a
  `BlockedByHook` hand and the policy re-polled (retry 1…11) instead of ending the turn,
  then proceeded cleanly. No rail.
- **Milestone: first Ceremonial Beast kill** (the 3-loss nemesis). Run 1 beat it and
  reached **Act 2 floor 24** before dying to a *normal* Spiny Toad. Could be partly draft
  variance, but the wall has clearly moved from Act-1 bosses into Act 2 — and an Act-2
  death to a normal enemy is the same deck-power story, one act deeper. Still 0 full wins
  (3/3 this batch: fl 24, fl 17 Ceremonial Beast, fl 8).

## 2026-06-12 (session 4) — Spirebird priors + the great pilot-skill tuning night

**Spirebird priors shipped:** owner exported cohort_stats.json (440,240 community
runs); scripts/build_priors.py distills to committed 53KB (picked-weighted Elo,
shrunk, per character). 100% coverage of every card ever offered. Verdict of the
priors-only batch (17/7/14/7/17): good cards alone didn't move the needle —
**owner's diagnosis: community Elo prices cards for skilled pilots.**

**Seven owner-observed fixes in one night** (watch stream → log post-mortem → fix
→ test → replay → redeploy, cycle time ~15 min each):
1. Pilotability-discounted priors (Evil Eye/Dark Embrace/Cascade upside ×0.7/×0.45).
2. Max-HP drain = heavy cost (the 'vampire' event killed 3 runs while parsing free).
3. Play friction (Production → pointless Defends vs non-attackers).
4. Barricade-aware block scoring (the nuance exception to #3).
5. Offering trio: w_draw 1.5→3.0, HP-cost scarcity curve (×0.5 full → ×2.5 empty),
   desperation draw before lethal.
6. One potion per round + 'already queued' transient (rail at Ceremonial Beast);
   strict .run watermark (errored run had inherited the previous run's seed/killer —
   which also mislabeled the stuck fight as The Kin in the narration, fittingly).
7. Rescue plays target properly (desperation fired Pommel Strike untargeted ×8).

**State:** 30 runs, 0 wins. The bot now reliably reaches Act 1 bosses (floor 17
five times tonight) and has beaten them ~3 times historically; boss fights are the
ceiling. Three different Act 1 bosses catalogued (Vantom, Ceremonial Beast ×3
losses, The Kin) + 2 Act 2 trips + 1 Act 2 boss encounter (The Insatiable, now
counter-armed). **Next:** boss-fight analysis (multi-turn setups? deck archetype
focus?), FR-6.1 automated debriefs — tonight WAS the debrief loop, human-powered
at remarkable bandwidth.

## 2026-06-12 (session 3 encore) — Act 2 routine; Act 2 boss reached; 4 upgrades

**Shipped** (each from a logged death or owner observation, each tested + replayed):
1. **Act-level map path planning** — DP over the full map DAG; forced-elite lanes
   lose to clean lanes (1-ply lookahead retired).
2. **Rest-before-boss** — boss autopsy showed Ceremonial Beast loss was HP, not
   deck (entered 46/91, boss died-not at 32/252): rest below 90% on the boss row.
3. **Lethal-skips-potions** — owner watched a hail-mary fire alongside lethal in
   hand; planner now stamps LETHAL lines and survival measures stand down.
4. **Generic death-countdown survival rule** — The Insatiable's Sandpit ("you will
   be eaten and die") + injected Frantic Escape ("Increase Sandpit by 1"): play the
   card naming the death-status when the counter ≤ 2. Pattern-generic, fight
   reconstructed in tests entirely from logs.

**Validation batch (path planning + rest-before-boss active; countdown rule landed
mid-batch):** floors 33 (Act 2 boss — The Insatiable), 13, 29. Two of three runs
fully cleared Act 1; floor 33 = new record. Trivial-era ceiling was 11.

**State of play:** Ironclad A0, 0 wins, frontier = The Insatiable (countdown rule
untested live). Deck quality is now the limiting factor everywhere → Spirebird
priors are next session's headline, then FR-6.1 automated debriefs (the manual
post-mortem workflow is fully proven — five fixes traced to specific logged deaths
today).

## 2026-06-11 (session 3) — P1 lands: standard policy reaches Act 2; tuning loop proven

**Built:** config-driven policy layer (policy.toml, hash per run in meta+index);
textparse (rules text → numbers); one-turn combat planner (sequence DFS with target
branching, vuln/weak/strength/block sim); StandardRouter (elite-avoiding HP-aware
map routing, HP-gated events, scored card rewards, rest/smith threshold, potion
management); replay harness v1 (`sts2bot replay`) — every policy change validated
against all logged states (1600+) before going live. CLI `--policy/--ascension/
--speed` (speed now self-healing: cinematics reset Engine.TimeScale, loop
re-asserts; observed at Act 1 boss).

**Live tuning loop, three iterations (batch → log post-mortem → fix → test →
replay → batch):**
1. Run 10 died at 3 HP holding two unusable-by-rules potions → heal-when-dire +
   hail-mary drinking.
2. Run 13 lost to a 4-Nibbit pack from full HP (event-spawned fight; flat damage
   scoring spread hits) → quadratic focus-fire term.
3. Run 16 made history (first Act 1 boss kill → Act 2 floor 23, died to Ovicopter)
   then rail-erred hammering its own death sequence ("Player actions are currently
   disabled") → fork.3 exposes battle.actions_disabled, policies wait; loop treats
   the error as transient; outcomes now enrich from .run records even on errored
   loops. Post-death flow is richer than early deaths (death screen → EXP bar →
   unlock reveals) — navigator handled it unaided in batch 3.

**Scoreboard (Ironclad A0):** trivial floors 5-11, 0 boss fights. Standard floors
3-29: two Act 1 boss fights, two Act 2 trips (23, 29), zero wins yet. Distinct
loss causes now measurable in the index (killed_by per run).

**Misc:** owner-found bug: bot's back-out reflex kicked owner off the Timeline
screen mid-reveal → open Timeline is now always hands-off (MANUAL wait).

**Next:** Spirebird priors import + KB-from-observation; act-level map path
planning (forced-elite lanes); boss-fight analysis (2 losses); FR-6.1 automated
debriefs — the manual post-mortems above are the template.

## 2026-06-11 (session 2) — Fork feature-complete: deck, speed, ascension; all verified live

Fork.2 (cicero225/STS2MCP@a84c9e1) adds the remaining planned mod features, all
live-verified same session:
- **Master deck in player state** (`deck`: id/name/type/cost/star_cost/rarity/
  is_upgraded) — verified mid-combat on Necrobinder (10-card starter), fixture
  captured. Unblocks P1 deck policies.
- **`set_time_scale`** (0.25–10x, engine-level) — set/clamp/reset verified. 3x run
  measured **61.5 dec/min vs ~30–40 at 1x**; CLI now also scales the poll interval
  with `--speed` (the loop was becoming the bottleneck).
- **`set_ascension`** at character select via NAscensionPanel (panel signal → screen
  syncs lobby; per-character max enforced) — state fields + refusal-at-locked
  verified; embark-at-A1 self-tests after first win. CLI: `--ascension`.

Run 9 (Necrobinder, 3x, fl.11): first **death by event** — EVENT.DENSE_VEGETATION
("Trudge On" HP loss at low HP; trivial policy picks first option blindly). Exposed
an index bug: the game pads the unused killer slot with truthy "NONE.NONE", which
masked the event killer — fixed + regression test. P1 event policy note: HP-cost
options need gating on current HP.

Fork status: all planned P2 mod features done early. Parked: epoch-reveal
automation investigation. PR upstream still pending owner's go-ahead.

## 2026-06-11 (fork session 1) — Character-select bug root-caused, fixed, verified live

**Setup:** owner forked STS2MCP → github.com/cicero225/STS2MCP, cloned to `fork/`
(gitignored, upstream remote wired). .NET 9 SDK installed via winget; `build.ps1
-GameDir I:\SteamLibrary\...` builds clean. ilspycmd (pinned 9.1.0.7988) used to
decompile game classes into `external/decompiled/` for reference.

**Root cause (from decompiled NCharacterSelectScreen/Button):** when a character
unlock is pending, `PlayUnlockCharacterAnimation` runs async after screen open and
`Select()`s the newly unlocked character ~1s later — overwriting any API-made pick;
embark reads `_lobby.LocalPlayer.character`, hence wrong-character runs. Worse,
`NCharacterSelectButton.Select()` is guarded by `_isSelected`, and the animation
never deselects other buttons, so retrying the pick silently no-ops (why the
double-click experiment failed).

**Fix (fork commit 7e4977a):** action side — `Deselect()` then `Select()` to force
the full commit path; retryable refusal while `Progress.PendingCharacterUnlock !=
none`. State side — `selected_character` + `selection_busy` on character_select.
Bot side — navigator waits while busy, re-selects until verified, then embarks
(fire-and-hope fallback for unforked mod).

**Live verification — the race actually fired:** owner's earlier click-through
hadn't consumed the pending Necrobinder unlock; entering charselect started the
animation. Log: `wait: unlock animation playing` → `select IRONCLAD (screen has
NECROBINDER)` → `selection verified (IRONCLAD); embark` → run started as The
Ironclad (died fl.5, seed 26WPYS0Y57). Second run requesting SILENT started as The
Silent. Character control proven with two deliberate distinct picks.

**Roster:** Ironclad, Silent, Regent, Necrobinder unlocked; Defect is the last lock.
**TODO:** offer the fix upstream as a PR from the owner's fork; remaining fork
items — ascension selector, speed control, master deck state, epoch-reveal
investigation.

## 2026-06-11 (final) — Shakeout series done: 3 clean runs, 3 characters, all fixes tested

**Run 5** (Regent, resumed) stalled at a rewards screen: potion reward + full belt
no-ops with status "ok" forever; stall rail killed the run as designed. Fixed:
rewards policy abandons items after two claim attempts. **Run 6** (same Regent run
resumed) completed: died floor 11 Act 1 to ENCOUNTER.BYGONE_EFFIGY_ELITE, seed
MVPTHFRUWN — deepest run yet; exercised multi-card select overlay ("Choose 2 Common
Cards"), Regent star costs, Unknown map nodes.

**Session tally (modded profile, all A0, trivial policy):** 6 runs — 3 completed
clean (Ironclad fl.9 / Silent fl.5 / Regent fl.11), 3 errored (each found a real
bug/gap, each fixed with a regression test: transitional battle-less combat state,
epoch-reveal menu gate, full-belt reward no-op). Owner interventions: 1 epoch
reveal + 1 accidental dialogue click-through. Everything else autonomous.

**Next session:** C# mod fork (character-select commit fix is the gateway to M1
character control; ascension selector + speed control + master deck ride along),
then P1 knowledge base + real policies. Open owner decision: GitHub fork of STS2MCP
under owner's account vs vendoring into this repo.

**Run 3** stalled by design: after the profile's first death the game gates the main
menu behind a Timeline epoch reveal (NEOW_EPOCH) which the mod refuses to automate
(can corrupt unlock state). Bot now surfaces `MANUAL:` waits loudly and waits ~5 min.
Owner revealed; recurrence is per-epoch (meta milestones), front-loaded then rare.
Fork investigation item filed.

**Run 4** (first fully-instrumented run): completed; victory=False from the game's
.run record, seed K4AQ5JS9JD, build v0.103.3, killed_by ENCOUNTER.SLIMES_WEAK, floor
5. Start event ("Nutritious Oyster" = relic boon) handled by the generic event
policy. **M0 exit criterion met.**

**BUG (top fork priority): character select does not commit.** Requested IRONCLAD
(mod clicked it; confirm became enabled) but the run started as The Silent; a
double-select experiment then started The Regent — who had just been unlocked by the
Silent run, supporting the theory that embark commits the screen's *focused*
character (the "NEW!"-badged newest unlock when present) and the mod's
`NCharacterSelectButton.Select()` doesn't update the embark payload on v0.103.3.
Roster snapshot from run 4's logs: Ironclad+Silent unlocked at profile start;
Regent/Necrobinder/Defect locked. Until the fork lands, the bot records the *actual*
character truthfully (player block + .run record) and stats split accordingly.

**Owner intel on dialogue screens:** click-through dialogue appears (a) on a
character's first arrival at Neow, (b) at Ancients, (c) at run end reaching the
Architect. Unknown yet whether (a)/(c) present as `event.in_dialogue` (handled) or
as opaque `overlay` (manual). Watch on next occurrences; (c) matters for win-path
game-over detection.

## 2026-06-11 — First live session: M0 plumbing verified

**Game:** v0.103.3, Steam release branch · **Mod:** STS2MCP 0.4.0 · **Bot profile:**
modded scope `profile1` (fresh; physically separate tree from owner's vanilla saves —
isolation confirmed on disk and via API).

Setup: mod installed via `scripts/install_mod.py` (game found at
`I:\SteamLibrary\...`), saves backed up twice via `scripts/backup_saves.py`
(owner's vanilla profile1 has an in-progress run; untouched). Owner enabled
"Load Mods" in-game (needs one manual restart the first time).

**Run 1** (halted by design): 8 decisions in, hit `monster` state with no `battle`
block — transitional room-loading state not in the API docs. C5 fail-loud worked.
Three doc-vs-live gaps found and fixed:
1. `battle` is briefly absent while a combat room loads → optional + policy waits.
2. `character_select` lingers after embark; re-confirming errors → confirm sent once.
3. `singleplayer` menu goes straight to character select (no standard/daily submenu).

**Run 2** (first complete run): trivial policy, Ironclad A0. Died floor 9, Act 1, to
ENCOUNTER.NIBBITS_NORMAL (per the game's own `.run` record). 159 decisions, ~5 min
wall clock (poll 0.5s, normal animation speed). Full decision log + SQLite row
written; game-over dismissed; loop returned to main menu cleanly. **M0 behavior
demonstrated end-to-end live.**

Discoveries:
- The game writes rich JSON run records to `saves/history/*.run` (win flag, seed,
  build_id, killed_by, per-floor history) — wired in as the authoritative outcome
  source; better than the API for post-run analysis later.
- The mod's `/api/v1/compendium` 404s on this build ("Not found") — not needed (the
  `.run` records + `/api/v1/profile` cover us), but noted upstream-issue-worthy.
- Fresh-profile FTUE: one tutorial prompt at run start, declined by the navigator.
- Throughput estimate at normal speed: ~2s/decision → a full (3-act?) run maybe
  20-40 min; speed control (P2 fork) will matter for the climb.

Open: double game-over dismiss (two `ok` menu_selects — harmless, tidy later);
victory=None on run 2 (fixed after the fact — enrichment from `.run` records now in,
verified by run 3).
