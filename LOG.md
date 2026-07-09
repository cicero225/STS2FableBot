# Lab Notebook

*Newest first. One entry per live session / milestone (see PLAN.md §6).*

## 2026-07-09 (Fable 5, session 2 cont. 5) — Batch boltv1gi4: KD handler VALIDATED; elite avoidance now near-total

**Batch (10 clean): 0 wins, act-reach 1.30. Elites fought 0.1/run, ZERO elite deaths** —
the death-class lane pricing works emphatically; flip side: **relics fell to 4.8/run**
(weak decks now dodge elites entirely). The calibration question going forward: when the
deck strengthens mid-act, does the gate reopen fast enough to bank relics? Watch
relic-vs-depth in the next batches.

**Knowledge Demon handler VALIDATED live** (run 8, f33): all THREE Curse-of-Knowledge
rounds picked Disintegration deliberately — vs Mind Rot, vs Sloth, vs Waste Away (the
whole preference table exercised) — and the planner blocked the tick (hp_loss 23→0 as
Defends played with Disintegration 6 up). Free-this-turn subsidy also sighted (Pyre
drafted from an in-combat pick and later upgraded).

**Shipped this stretch (owner Q&A driven):**
- **§5-C estimate**: Waterfall's ACCUMULATING kill explosion (+3/turn); KD regen
  (Ponder ~7/turn, capped, post-turn) + averaged Disintegration load in its dps.
- **Damage potions in lethal planning**: pseudo-cards in the DFS (0-cost, cap-exempt,
  −18 reluctance, one-per-round shared bookkeeping) so card+potion lethals beat block
  patterns; gated on threat-or-setup (a 1-turn horizon can't see a free slow win) —
  which also enforces the owner's zero-threat HOLD in both the planner AND the finisher.
- **Foul Potions thrown at merchants** (+100 gold each, before buying; bounded attempt —
  the mod's use_potion at a shop should map to the game's own throw; live-verify).

Still pending live rolls: sleeper no-op (no Lagavulin this batch), merchant throw,
Pen Nib's actual double.

## 2026-07-09 (Fable 5, session 2 cont. 4 — day end) — Batch bn4v9mf75: PEN NIB ROLLED; elite-death forensics

**Batch (10 clean): 0 wins, act-reach 1.40** (4× Act 2: Insatiable f33, Obscura f30,
Decimillipede f27, Hunter-Killer f24).

**PEN NIB finally rolled** (run 9, after ~90 runs): counter plumbing **validated live**
(0→6 across two floors, persists between fights) but the run died before counter 9 — the
10th-attack DOUBLE remains unexercised, so the TEMP tripwire stays.

**Elite-death forensics (3 deaths):** Gardeners f12 + Terror Eel f8 were **forced
single-option lanes** — the composed gate visibly refused Gardeners when options existed
(path values −54/−122). **Decimillipede f27 was a genuine gate-pass**: the Act-2 pool
held only Entomancer (Decimillipede's 46-HP single-segment harvest fell under the pool
floor), so the run chose the elite over a RestSite. Live-counted the real fight — **3
Reattach segments** ("revives in 2 turns with 25 HP if others alive") — and composed it
(138 effective HP; revive modeling stays the ENEMY_PASS (B) refinement). → The remaining
elite exposure is **forced lanes**, a route-DP commitment problem, not a gate problem.

**Not yet validated** (didn't roll): sleeper-leak fix (no Lagavulin), Knowledge Demon
handler (no KD), free-this-turn potion picks (no card-gen potion observed). Next batch.

## 2026-07-09 (Fable 5, session 2 cont. 3) — Batch bnyka47dn + the Act-2-wall work ships

**Batch (10 clean): 0 wins, act-reach 1.30, ZERO elite deaths** (15 elite fights taken,
none lost — the gate+pool pipeline works; the two 4-elite runs banked 11–12 relics and
reached f33). **Kaiser Crab ×3 at f33 is now the wall for deep runs** — model validated,
these are deck-power losses. Lagavulin ×2, Vantom, Kin, Fysh, Waterfall at f17.

**Fix validations in-batch:** potion targeting **0 errors / 9 targeted drinks** (Beetle
Juice fix); **16 removals, 0 Guilty**; card-gen potion dropped at boss start (Skill
Potion, run 1). **Sleeper leak found live** (run 1/3 audit: the asleep deny left the HP
reduction in the sim → _score's focus term rewarded the chip → Volley/Tremble woke her
round 1) → fixed mid-batch (damage into a sleeper is now a complete sim no-op);
validates next batch, as do the owner-caught Pyre free-this-turn subsidy and the
Knowledge-Demon/multi-body work below.

**Shipped this stretch (all owner-steered or unblocked by captures):**
- **Knowledge Demon "Choose a Card" handler** — screen captured live (ordinary
  card_select, all-Status options); pick-your-poison by the owner's least-bad table
  (Disintegration first); the resulting DISINTEGRATION_POWER on the player now counts
  as end-of-turn blockable incoming (text-parsed, tracks 6→7→8).
- **Multi-body elite synthesis** — _ELITE_COMPOSITIONS expands Gardeners (3× Skittish
  bodies) and Phrog (+4-Wriggler wave) for the pool gate.
- **Free-this-turn pick subsidy** — card-gen potion / discovery offers show printed cost
  but play free; in-combat picks subsidize cost (Powers ×2.0 — the owner's Pyre case).

Pen Nib: still unseen (~90 runs).

## 2026-07-09 (Fable 5, session 2 cont. 2) — Batch b8oazdsui: best act-reach of the week; owner live-watch catches 4 more bugs

**Batch (10 clean runs, full fix stack): 0 wins, act-reach 1.50 (max 3) — week's best.**
4 runs past Act 1 (Kaiser Crab f33, Knowledge Demon f33, Ovicopter f23, and an **Act-3
push to f35**, deepest since the 06-26 win). Only **1 elite death** (Phrog f15 — the
multi-body gap, filed). Elite take-rate 0.7/run of 3.8 offered — the pool gate being
choosy as designed. Boss-entry HP 35–76.

**Validation checks all green:** Cascade drafts **2 → 0** (planner-blind dock);
Soul Fysh fight cleared 5 Beckons (entered at 71 HP, lost on deck power); Ovicopter
targeting **7 hits leader / 0 minions** (race-the-leader clean).

**Owner live-watch catches, all fixed+committed mid-batch (next batch validates):**
- **Beetle Juice hail-mary death** (run 2, 4 HP vs Kaiser Crab): the hail-mary FIRED but
  the drink errored — enemy-targeted debuff, category missed it, no target passed
  ("Potion requires a target enemy") → died with the potion in the belt. drink() now
  enforces targeting from the potion's own target_type; "%-less" text classifies debuff.
- **Guilty removal waste**: self-expiring curse ranked below basics; now above (and a
  Guilty-only deck doesn't trigger paid removal).
- **Lethal with a heal in hand + spare energy**: the DFS credited [kill > Not Yet] equal
  to [Not Yet > kill]; search now cuts at lethal states — heal-before-kill only.
- **Slither-on-Strike enchant** (net loss): filed as the events/enchant pass anchor;
  §8.5 order revised: enemies+cards → relics → events → potions. Pen Nib cross-combat
  tick-storage filed under the relic pass.

Knowledge Demon remains the Act-2 wall; its "Choose a Card" handler is next in line
there. Pen Nib: still never rolled (~70 runs).

## 2026-07-09 (Fable 5, session 2 cont.) — Batch b8msts8jx: single-body elite deaths fixed; swarms are the residue

**Batch (10 runs, clean, 0 stalls): 0 wins, act-reach 1.20** (Insatiable f33 deepest;
Slumbering Beetle f23 — the deliberately-unmodeled sleeper). Boss-entry HP 49–68.

**Elite-gate validation: partial win, sharp residue.** Terror Eel deaths **2 → 0** (the
single-body pool pricing works). All 3 remaining elite deaths are **multi-body elites the
single-FightEnemy model flatters**: Phrog+Wrigglers f9, Phantasmal Gardeners f7 and f12.
Run 10's two elite fights were **forced single-option lanes** (map log: `f8 options=[Elite]`,
`f11 options=[Elite]`, path values −0.8/−78.5 — the scorer knew, floors too late). → Filed:
**multi-body elite synthesis** (Gardeners ≈ 3×31 HP w/ Skittish; Phrog + Wriggler treadmill)
— fixes both the gate AND lets the route DP dodge those lanes at commit time.

**Mid-batch owner-steered fixes** (landed during, so in effect only for the NEXT batch):
desperation draw skipped under Ringing (owner-caught: Battle Trance burned the capped play
on a sealed-anyway death — R11 same fight showed the cap logic itself correct);
**planner-blind draft dock** (owner-approved: Cascade drafted+upgraded twice via the
8.1d-lowered thresholds; `recognized == []` → −4.0, self-removing once parseable,
attack-generators exempt).

**Still awaiting live validation:** Soul Siphon drain + sleeper wake-cost (no Lagavulin
rolled), card-gen potion boss-drop (mostly), Pen Nib (never once, ~60 runs and counting).

## 2026-07-09 (Fable 5, session 2) — Beckon fix VALIDATED live; owner-steered pricing + potion fixes; Soul Siphon captured

Validation day for the Beckon-clearing fix, split 6+4 by a **Timeline-epoch interruption**
(run scores crossed another unlock threshold → `IRONCLAD6_EPOCH` reveal blocked new runs;
MANUAL rail stopped the batch cleanly; owner clicked, batch resumed under new config).

**Headline — the Soul Fysh Beckon fix works live:** the continuation's Fysh fight cleared
**10 Beckons** (vs 0 cleared / 11 wasted attacks-into-Intangible yesterday); only 3
non-Beckon plays during Intangible turns. The fight was still a loss (entered at 64 HP
with a weak deck) — behavior fixed, deck power still the war.

**Owner-steered changes shipped mid-batch** (runs 1–6 = Beckon fix only; runs 7–10 add
all of this under config `93676cd0fe72`):
- **Conflagration parse bug** (owner-caught live: Bloodletting+ unplayed): "Deal 2 damage
  to ALL enemies 4 times" read as 2×1. Hit counts now survive target clauses; Whirlwind's
  "X times" resolves to its X-cost energy; "(Hits 6 times)" parentheticals trusted.
- **Self-HP costs are tempo, not chip** (owner: "play Bloodletting+ as low as 15 hp...
  unless it led to death"): flat-cheap above a projected-end-HP floor (15), scarcity below,
  −500 wall on non-lethal death projection. BL+ line now plays at 30 HP, drops at 20.
- **Card-gen potions (Skill/Attack/Power/Colorless) drop at boss start** — they were
  category "other" → hail-mary-only, way too late (owner). New `card_gen` category.
- **§8.5 priority ruling filed:** enemies+cards → relic pass → full potion pass → events.

**Soul Siphon captured** (run 2's Lagavulin loss): −2 Str −2 Dex per cast, every 4th round
post-wake, via her Debuff intent — the §8.4-A data-block is resolved, drain ready to
implement (with the negative-Dexterity planner gap, done together).

**Batch (10 real runs): 0 wins, 3× Act 2 (deepest f33 Kaiser Crab @56hp entry).** Act-1
boss deaths: Ceremonial Beast, Lagavulin, Kin, Soul Fysh; elite deaths: Phrog f8, Terror
Eel f7+f9 (the generic elite gate underrating real elites — known §8.4 item). Mixed-code
halves, so read directionally only. Also fixed: batch_summary crash on error rows.
Pen Nib: STILL never rolled.

## 2026-07-09 (Fable 5) — Batch bsmwhj26u: Underdocks pool live; Soul Fysh is the new Act-1 wall

First batch with the restored Underdocks (10 runs, A0 Ironclad, clean, 0 stalls; config
`374480217e9e` — LF hash restored). **0/10 wins, act-reach 1.10** — 9/10 reached the Act-1
boss, only 1 passed. **The alt-Act-1 pool dominated: Soul Fysh ×4 (all losses), Waterfall
Giant ×2, Vantom, Ceremonial Beast**; 1 elite death (Phantasmal Gardeners f7 — so Gardeners
are in the pool even without the Undergrowth unlock), 1 Act-2 death to an **Entomancer
elite (first capture, not in bestiary)** at f28.

**Headline: the filed Soul Fysh Intangible gap is now measured, and it's the top Act-1
item by death count.** Trace check across the 4 Fysh fights: **11 cards played while
Intangible was visibly up** (17 such states) — Pommel Strike / Whirlwind / Fight Me!
thrown into per-hit-cap-of-1 turns. The §8.4-A note ("share the per-hit-cap model with
the Vantom Slippery fix") is the implementation path; priority should rise now that
Underdocks makes Fysh ~40% of Act-1 boss encounters.

Also notable: **elites fought jumped 0.4 → 1.8/run** (26 chances offered vs 16 — the new
pool's map gen differs), with correspondingly lower boss-entry HP (36–70). Watch whether
the elite gate needs a re-look against Underdocks elites. Pen Nib: still never rolled.

*Ops note:* first launch attempt aborted cleanly — the game had been left on the
compendium screen and menu recovery has no handler for it ("no back option"); the stall
rail caught it exactly as designed (C5). Small robustness item: try a blind
`menu_select back` on unknown menu screens before stalling out.

## 2026-07-08 (Fable 5, cont. 3) — Underdocks restored via save edit; unlock mechanics decoded

**Goal:** restore the Underdocks (lost with the pre-unlock profile) without grinding ~50
bot runs. Owner-proposed and authorized save edit; *C3 note: this restores meta-progression
the profile had already earned on the old machine (June batches were full of Underdocks
content) — no run outcome or win-rate is affected.*

**Method + what we learned about the unlock system** (owner-corrected from live test):
- `progress.save`'s **`current_score` is the LAST run's score, not a cumulative total**
  (a stopped batch's 4 runs left it unchanged at 749 = the manual win's score; the online
  "2450 total" framing maps to the *unlock track*, not this field).
- At **run end** (abandons count), the game **deposits `current_score` into a progressive
  unlock track** ("X of Y points to next unlock"). Byte-edited the field to 2500 (game
  closed, backups kept, Cloud off); owner then started+abandoned two runs: deposit 1 →
  **"Open" rare-potions unlock** (`POTION1_EPOCH`), deposit 2 → **`UNDERDOCKS_EPOCH`
  revealed**. `total_unlocks` 2→4.
- **Self-correcting:** the second abandon overwrote `current_score` with its own ~0 score
  (now 10), so the inflated deposits stopped automatically — future unlocks accrue from
  real run scores again.

**State:** Underdocks + rare potions restored → batch map pool is much closer to the June
baselines (Soul Fysh / alt-Act-1 back in rotation). Still pending from the old machine
(~2026-07-10): the post-unlock profile (custom mode + Undergrowth + the rest) and `logs/`
(bestiary source). Score-grind batch bh1jsqy7u was stopped after 4 runs once this path
opened (runs banked; mid-run 5 abandoned by owner from menu).

## 2026-07-08 (Fable 5, cont. 2) — Owner's recorded manual WIN #1/3; Queen first-capture; bestiary near-miss

**Owner played one recorded run (`sts2bot record`, seed `7Q4QCYQ09J`, A0 Ironclad): a WIN**
— Kin (f17) → Kaiser Crab (f33) → **the Queen (f48)**. Profile now shows **1 of the 3
Act-3 wins** needed to re-earn custom mode; owner will do the other two later. (Setup
notes: batch had left the engine at 4x — reset to 1x before play; pre-session
backup_saves taken.)

**Trace findings:**
- **Queen (Act-3 boss) first-capture** — 400 HP, Str ramp, Torch Head Amalgam minion
  (leader-kill ends it); Queen = control (`Debuff`/`CardDebuff`/`Buff`/`Defend`), Amalgam
  = escalating attacker. Filed in PLAN §8.4 next to Aeonglass.
- **Kaiser Crab model live-confirmed from human play:** Crusher ended at Strength 8 =
  base 2 **+6 Crab Rage** after Rocket died — the kill-one-claw-is-a-boon line, as modeled.
  `BACK_ATTACK_LEFT/RIGHT` + Crab Rage text match the planner's constants exactly.
- **No Strength-strip ever landed on the player in the Kin fight** — consistent with the
  owner's Dark Shackles ruling (it's our colorless card, not a Kin move). Bonus
  confirmation of the harvest-pollution pattern: the owner's own Mangle card showed up as
  an "enemy status" on the Amalgam.
- No Lagavulin → Soul Siphon stays data-blocked.
- **Owner post-run commentary filed (PLAN §8.4):** the win leaned on four things the bot
  can't execute — Stomp's dynamic in-turn cost, Neow's-Fury-as-tutor (fetch Bloodletting
  for energy), Cascade's X-cost deck-autoplay, and Delicate Frond flipping potion policy
  to spend-every-fight. A concrete human-baseline for the §8.3/§5-C work.

**Near-miss:** ran `build_bestiary.py` to bank the new data — it rebuilds from scratch off
`logs/runs/` and silently replaced the committed 75-enemy bestiary with a 46-enemy one
(this machine only has today's 10 runs; old logs never transferred). **Reverted via git.**
Filed in §7: don't rebuild until the old machine's `logs/` is fetched or the script merges.

## 2026-07-08 (Fable 5, cont.) — Shakeout batch b34khuptc: new machine works end-to-end; plan audit

**Batch (10 runs, A0 Ironclad, speed 4, owner-authorized unattended):** 10/10 completed
cleanly — **zero stalls/errors**, so the §7 batch-resilience hazard never fired this time.
**0/10 wins, act-reach avg 1.40 (4 runs to Act 2, deepest f33 dying to the Knowledge
Demon — the standing wall).** Act-1 boss: 8/10 reached it (entry HP 36–80), 4/8 passed;
deaths: Ceremonial Beast ×2, Vantom, Kin. Elites fought only 0.4/run of 1.6 offered.
Per-run profile snapshots + run logs confirmed writing.

**Read the numbers with three caveats:** (1) the restored profile is the pre-unlock
Jun-12 state — **no Undergrowth, no unlock cards, and `CUSTOM_AND_SEEDS_EPOCH:
not_obtained` (seeded custom runs are LOCKED again on this machine)** — so this batch
isn't map-pool-comparable to the June baselines; (2) runs logged under config hash
`8f6e6fcf2418`, a CRLF-checkout **alias of `374480217e9e`** (same content; fixed with
.gitattributes after launch); (3) n=10. As a shakeout it's a full pass: game + mod +
profile + planner + snapshots + logging all work on the new machine.

**Plan audit (Fable 5 over the Opus-era docs)** — fixed: config-hash CRLF fork
(.gitattributes), PLAN §6 still said to clone *upstream* (the 2026-06-23 regression),
diagram said profile "slot 2/3", ENEMY_PASS's stale Back Attack classification. Flagged
for owner: PLAN §8.4-A vs memory disagree on whether custom mode was unlocked as of
06-26; Dark Shackles is classified as *our* debuff in ENEMY_PASS but as a Kin-Priest
player-debuff in PLAN §8.4-A; LOG.md has no entries 06-16→06-26 (the first A0 win is
undocumented here); P0/M0 phase bookkeeping stale. Getting the old machine's
`backups/profile_snapshots/` (post-unlock profile) is now the highest-value recovery item.

## 2026-07-08 (Fable 5) — New-machine spin-up (repo folder now `STS2FableBot`)

Machine transplant per HANDOFF.md. Environment rebuilt and verified: fresh venv
(**Python 3.13.2**, not 3.14 — 232 tests + ruff green, recreate from 3.14 if parity
matters), STS2MCP fork re-cloned. The `STS2MCP-newbuild-fix.patch` no longer applies —
its content is now **committed on the fork's `v107-fork` branch** (f553315, plus a newer
card-select commit 79f1b69); checked that branch out instead. Needed .NET 9 SDK
(winget-installed). Mod built clean and installed to the game's `mods/`.

**Game dir on this machine:** `C:\Program Files (x86)\Steam\steamapps\common\Slay the Spire 2`
(was `I:\SteamLibrary\...`).

**Bot profile recovery:** the live save tree (`%APPDATA%\SlayTheSpire2\steam\<id>\`) had
no `modded/` scope — the bot profile didn't travel (backups/ is gitignored; AppData
doesn't sync). BUT Steam userdata's frozen cloud folder
(`userdata\50041417\2868840\remote\modded\`) held a copy last synced **2026-06-12, two
days before the reshuffle** (Cloud is off here — `cloudenabled 0`, sync stuck at
`conflictingchanges`, so it never pulled the corrupted state). Zipped it to
`backups/cloud_recovery_jun12/` and installed it as the live modded profile.
**Caveat: it's ~2 weeks stale** — pre-dates the Jun-26 first A0 win and all runs after
Jun 12; unlock progression is as of Jun 12. If the old machine's
`backups/profile_snapshots/` is still reachable, restore its newest snapshot over this.

Not yet done: live smoke test (launch game, confirm mod REST API answers and the modded
profile loads) — attended, per FR-4.4.

## 2026-06-16 → 2026-06-26 (Opus) — BACKFILLED 2026-07-08: the capability-estimate arc + FIRST A0 WIN

*Backfilled summary (Fable 5, from PLAN §5.1/§8 and HANDOFF.md — these sessions logged into
PLAN.md instead of here; see git history for detail).* The arc: §5-C `estimate_fight`
capability estimate built + wired into the elite gate (06-16) → seeded-run combat fixes via
`B04BGZEDRN` while it lasted (06-15/16) → HP-aware path-EV routing → mod broken + rebuilt
through the v0.103.3→v0.107.1 game update, including the build-from-upstream `player.deck`
regression + fix (06-23/24) → deck-power diagnostic over 91 runs: tempo mismatch, not
thinning (06-25) → powers-under-played Tier-1 horizon fix, play-rate 48%→83% (06-25/26) →
Act-1/Act-2 boss deep-dives, Artifact validated live (06-26). **2026-06-26: first-ever A0
win (Ironclad, floor 48)** — the 0-wins wall broke; Act-1-boss clear ~44%; the binding wall
moved to the Act-2 bosses (batch ble3lyl8a: 10 clean runs, 0 wins, 4/10 past Act 1).

## 2026-06-15 (session 5 cont., Opus) — Rest/upgrade optimization + a 2-session-old bug

Owner asked to optimize rest-vs-smith and upgrade choice (with the caveat that combat
tactics are the bigger, deferred problem — true). Built:
- **Upgrade by value:** build_priors now emits an upgrade delta `u` per card (upgraded
  vs base variant Elo; Havoc +5.7, Body Slam +4.5, basics ~none). Smith/upgrade screens
  target the card that *gains* the most, not the best base card.
- **Survival-based rest:** scripts/build_combat_stats.py distills the bot's own logs into
  per-fight-type HP loss (monster ~11, elite ~30, boss ~38 mean / 66 p75). Pre-boss
  campfire rests only if HP can't cover the boss's likely damage (p75 × safety), else
  smiths; auto-adapts as the deck improves. General campfire keeps the 60% rule.
- **By-act priors / earlier deck-power work** — see the 06-14 entries.

**The catch:** validating the above (prompted by an owner "why did it skip a card?"
question — the skip was a correct community-rated skip) revealed the rest-vs-smith
decision had been a **no-op since session 3**. Live rest options are id `HEAL`/`SMITH`,
but the code keyed on `rest`/`smith` and never lowercased the id, so every rest site
fell through to "Rest" and the bot **never smithed by choice** — a big reason decks never
upgraded. Fixed (canonical key mapping) + regression test with the real ids. Post-fix
batch: a run smithed twice (upgraded Flame Barrier + Bash, 3 upgraded cards vs 0 before).
Lesson: fixtures used the old ids, so tests/replay couldn't catch it — live strings ≠
fixture strings. Reinforces the value of the planned slowed-down observation run.

Still 0 wins; combat tactics remain the ceiling. Filed owner's dynamic take-vs-skip
threshold idea (PLAN.md §8.1d) for that run.

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
