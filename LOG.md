# Lab Notebook

*Newest first. One entry per live session / milestone (see PLAN.md §6).*

## 2026-07-16 (Fable 5, session 4) — Whirlwind dock ships; harness FIGHT-BOUNDARY bug; Plating modeled (real accuracy: 79%/64%)

**Whirlwind-class early dock shipped (8a7853d, hash -> f0e54b35df1b)** per the owner's
refined spec: X-cost spend-energy damage gets no flat AoE bonus, no early-damage bonus
(granting it exactly canceled the dock — caught in test), and a -2.5 Act-1 dock; late
acts untouched. Conflagration (dedicated AoE) is the tested control.

**Harness bug (found drilling into "Sludge Spinner -8.6")**: turns were grouped by
round number PER FILE, but rounds reset each combat — so round R of fight A paired with
round R+1 of fight B, contaminating every metric and dropping most turns (87 audited
where 371 exist in 10 runs). REAL
numbers: **HP prediction 79% within +-2, damage 64%** (the earlier "42%/47%" was the
artifact). Fight boundary detection: round number decreasing = new combat.
The pre-bake findings stand (verified by direct trace, and their signatures vanished
post-fix in both groupings). The "Sludge Spinner" signature was pure contamination.

**Plating modeled (the dominant CLEAN signature, n=31)**: "At the end of your turn,
gain N Block" lands BEFORE the enemy turn, soaking incoming like played block — but
hp_loss ignored it, over-predicting losses by ~Plating every turn it was up (and
over-blocking in response: Gorget/Stone Armor decks were double-spending on defense).
Parsed from status text into SimState.end_turn_block; joins the block pool in _score
and the hp_loss diagnostic, lethal-gated.

Remaining clean signatures (backlog, n>=4 in 10 runs): Tunneler -4.6 (n=11),
Parafright/Obscura -7.3, Ceremonial Beast -4.2 (n=10, the Plow cycle?), Corpse Slug
-9.0, residual STRENGTH_POWER -4.8 (n=6, post-prebake — needs a look), Nibbit -5.8.
All "less than predicted" — the bot is systematically pessimistic now, which beats
optimistic but wastes block/potions.
## 2026-07-14 (Opus 4.8) — A/B #2: seed J48A843QK0 (Ceremonial Beast). Same offers, different decks: the bot drafts GLASS

Owner piloted the seed the bot lost (CB @80/80 f17). Two human attempts: run 1 lost CB
(self-noted heal-vs-upgrade misplay); run 2 WON CB at 2 hp, died at the Act-2 boss.
CAVEAT up front: the human matched their OWN run-1 drafting, not the bot's, and routes
diverged after ~f6 — so this compares DRAFTING+piloting, not piloting in isolation
(the clean isolation experiment is the stop_at_floor manual-takeover: let the bot build
its deck to the boss, hand over the fight — deferred). Offers were seed-identical while
routes matched (verified: f1 Shrinker Beetle + first 4 offers byte-identical).

Decks at Ceremonial Beast:
- BOT (17 cards, 80/80 -> LOST r10, beast still at 61): Bash, 4 Defend, 4 Strike, Pommel
  Strike, Whirlwind, Expect a Fight++, Taunt++, Offering, Pact's End + TWO curses
  (Clumsy, Guilty). An offense/combo lean (Whirlwind + Expect-a-Fight energy) a
  starter-heavy deck can't reliably assemble, and no survival tools.
- HUMAN r2 (20 cards, 70/92 -> WON r13 @2hp): Bash, 5 Strike, 4 Defend, Taunt++,
  Offering, Pact's End, Blood Wall, Colossus, Feel No Pain, Feed, Tremble, Breakthrough
  + ONE curse. A defensive grind package + max-HP (Feed -> 92).

Per-offer picks (identical offers): f6 (Blood Wall / Body Slam / Whirlwind)
bot->Whirlwind, human->Blood Wall; f3 (Breakthrough / Expect a Fight / Setup Strike)
bot->Expect a Fight, human->Breakthrough.

OWNER READ (2026-07-14, sharpens the above — the earlier framing over-counted the
divergences):
- The ONE dubious bot pick is WHIRLWIND EARLY. X-cost multi-hit AoE is BELOW a Strike's
  efficiency without energy/strength support — a card the owner "simply wouldn't pick
  first/early." How the logic lets it through: Whirlwind parses as a 5-dmg AoE (X
  unknown at draft), so it collects the flat bonus_aoe (+3) + its Spirebird prior, while
  the tag machinery's energy/strength needs are BONUS-ONLY (penalty=False) — nothing
  docks it. The +1.5 early-block nudge on Blood Wall didn't overcome that.
- f3 is NOT a divergence/error: GIVEN Whirlwind, Expect a Fight is the correct
  follow-up (Whirlwind needs the energy). The human's Breakthrough was a different valid
  call (wanting some AoE). The two bot picks are one coherent plan, not two mistakes.
- Blood Wall itself is ambiguous (owner took it only out of a weak offer set); the whole
  draft was "desperate, not great choices" from poor offers, and the human "would never
  have made it close without" the LATER Offering/Colossus. So the seed is hard and the
  CB loss is weak evidence of a bot flaw.

PROPOSED (owner's call, config-hash change) — REFINED by the owner's follow-up
(2026-07-15): the axis is EARLY-vs-LATE, not "energy source in deck". Whirlwind IS AoE,
but INEFFICIENT AoE (every dedicated AoE does more dmg/energy — the tell that AoE alone
doesn't redeem it). Its real payoff is (a) card efficiency — one card slot dumping the
whole energy bar into damage-to-all — and (b) spending SURPLUS energy at high X. Both
are late-game conditions (thick deck / energy economy above card costs), rarely true
early. So the fix is: (1) don't grant the full flat bonus_aoe to X-cost "spend-energy"
AoE (Whirlwind/Volley class) — it's not efficient AoE; (2) dock it in ACT 1 specifically
(the payoff is late); energy_source in deck stays a positive modifier, not the hinge.
Turns early Whirlwind from ~neutral to a skip while leaving it a fine LATE pick.

Damage rates were SIMILAR (~20/turn; the bot was actually AHEAD on damage — beast at 129
by r6 vs the human's 167). The bot lost on SURVIVABILITY: 80 max HP vs 92 (Feed), and no
defensive package. Standout drafting insight: the human's Colossus + Tremble is a
boss-specific defensive synergy — stacking Vulnerable on the beast both raises your
damage AND (via Colossus, "50% less damage from Vulnerable enemies") halves the beast's
hits. That boss-context value is exactly what the step-2 tags don't yet capture (filed
under the deferred boss-profile conditionals).

Bottom line: reinforces A/B #1 and the boss audit — the lever is DRAFTING/deck power, and
the bot's tendency is toward GLASS (offense over survival). But with the owner's nuance
this is a WEAKER data point than A/B #1: mostly a bad offer set both players struggled
with, one genuinely dubious pick (Whirlwind-early), and a human win that hinged on late
Offering/Colossus luck. The concrete, generalizable takeaway is the Whirlwind-class
proposal above; the rest is "hard seed, mediocre cards."

## 2026-07-14 (Opus 4.8) — ★★ THE PREDICTION HARNESS (owner idea) — and the pre-bake bug FAMILY it exposed

**Owner's idea**: flag when end-of-turn HP isn't what the planner expected — "a fairly
reliable signal for potential planner issues". Built as `scripts/predict_audit.py`:
POST-HOC over the logs (zero runtime cost, no policy contamination, audits the whole
130k-state corpus retroactively). Two channels: predicted hp_loss vs actual HP delta,
and (new `plan_damage` score field) predicted damage vs enemy HP actually lost.
Noise handled by AGGREGATION — bucket by enemy/status/relic, rank by frequency x
magnitude; a one-off is noise, a recurring signature is a bug.

**It paid for itself within minutes.** First run over 60 runs / 538 turns: only 42% of
HP predictions land within +-2, and the top signatures were diagnostic:
- `STRENGTH_POWER n=13, +9.4 HP worse than predicted` — the double-count I shipped
  yesterday, visible in the pre-fix corpus. The harness detected a known bug: validated.
- `FRAIL_POWER n=17, -5.2` and `WEAK_POWER n=13, -4.2` — SAME BUG CLASS, unknown until
  now. Trace-verified: a Defend under Frail READS "Gain 3 Block" (5 x 0.75); a Strike
  under Weak READS "Deal 4 damage" (6 x 0.75). The sim was multiplying them AGAIN.
  Fixed: FRAIL_MULT/WEAK_MULT no longer applied to the player's own turn-start Weak/Frail
  (enemy Weak that we apply mid-plan is unaffected and still modeled).

**THE RULE, now paid for three times (Pen Nib, Str/Dex, Frail/Weak): the mod's card text
is a FULLY-RESOLVED PREVIEW. Never re-apply any modifier the text can already show —
verify against a trace first.**

Still open from the harness (evidence logged, not yet fixed): Leaf Slime (+8.8, n=19),
Damp Cultist (+9.6, n=7), Kin Priest (-12.1, n=8), Waterfall Giant (-8.6, n=11 — matches
the audit's unmodeled-heal finding), PLATING end-of-turn block (+3.7, n=15), player
VULNERABLE (+8.7, n=6 — is the enemy intent label boosted or not? needs a trace check).

## 2026-07-14 (Opus 4.8) — ★ Act-1 boss audit: 21/24 deaths are DECK POWER — and it caught a Strength DOUBLE-COUNT I shipped yesterday

Six agents, one per Act-1 boss, four death traces each (24 total), audited against the
CURRENT planner code. Two findings, one of them a self-inflicted regression.

**1. CRITICAL: the mod's card text is a fully-RESOLVED preview** (the Pen Nib lesson,
generalized — and I failed to generalize it). Trace-verified: at Strength 1 a Strike
READS "Deal 7 damage"; at Dex 2 a Defend READS "Gain 7 Block" (an Unmovable-doubled
Defend+ read 26 = (8+5)x2 — even the relic doubling is baked in). So yesterday's
_POWER-suffix fix (a516867), which made my_strength populate for the first time,
introduced a DOUBLE-COUNT: text damage + my_strength again. The old exact-match bug had
been masking it — two bugs cancelling. Fix: SimState carries my_strength_start /
my_dex_start (the baked-in values) and the sim adds only the UNBAKED delta — strength
gained mid-plan (Inflame, Dominate, Shuriken/Kunai triggers) is real and still applies.
Every plan since a516867 over-estimated its own damage whenever Str/Dex != 0 — i.e.
exactly the strong-deck fights. Regression tests use live-shaped pre-baked text.
**Lesson (again): the mod previews EVERYTHING. Never re-apply a modifier the text can
already show — verify against a trace first.**

**2. The Act-1 wall is DECK POWER, not mechanics: 21/24 deaths.** Kin 4/4 deck_power
(correct leader targeting, correct race line — one run died with the Priest at 27/190).
Soul Fysh 4/4. Ceremonial Beast 4/4. Vantom 4/4 (slippery/ramp/nuke all modeled and
priced; the bot SEES the 28-damage nuke and cannot block it). Lagavulin and Waterfall
Giant "mixed" — 4 mechanic findings total: the Str double-count (above), Waterfall's
unmodeled periodic heal (capability _EMPIRICAL_MOVES gap -> over-rates the matchup),
and Vantom's Wound-shuffle deck pollution (second-order). NO per-boss handlers proposed
by the audit for Kin/Fysh/CB — the fights are played correctly and simply lost on
arithmetic. This RETIRES the "Phase-1 per-boss handlers" hypothesis as the top lever:
the lever is deck power (drafting), which the A/B pilot independently showed.

## 2026-07-14 (Fable 5, session 3 cont.) — A/B pilot verdict + draw/block draft rework (config hash CHANGES)

**The human-vs-bot A/B on seed CJN9M609YW** (owner piloted, `sts2bot record`): the
bot's Soul Fysh f17 loss was decided at the DRAFT TABLE, not in the fight. Owner
assembled Inferno+Juggernaut fed by Stone Armor Plating — damage ACCELERATED
18/26/33/53 per turn, 211-HP Fysh dead in ~9 rounds at 63-74hp throughout; the bot's
flat ~12/turn chip could never close. Bot's in-fight play was fine (Beckon clears,
Intangible respect); its picks were not: Pommel over Hemokinesis at f2, a SECOND
Pommel over Ashen Strike at f4, FNP with zero enablers; 16-card/7-nonbasic deck vs
the owner's 21/11. Boss entry 56 vs 74 hp. (Owner also LOST the seed in late Act 2
after deliberately gambling a 3-elite lane — the seed is genuinely hard.)

**Score forensics**: Pommel 9.62 vs Hemokinesis 2.23 = a 7.4-pt gap driven by the
Spirebird prior swing (+1.0 vs -2.8, x1.8) plus our flat bonus_draw 2.0.

**Owner model rework (SHIPPED — policy.toml changed, hash 93676cd0fe72 ->
cf7e1362a3b4)**: StS2 energy is scarcer and cycling pressure lower than StS1 — pure
draw / strike+draw is a weak speculative draft, and tutors are weaker too. Changes:
- bonus_draw REMOVED; draw now PENALIZED (-2.0) when the deck has no energy_source
  (tag machinery); neutral once one exists.
- bonus_block replaced by early_block_bonus 1.5, ACT-1-SCOPED and deliberately lesser
  than early_damage_bonus 2.5 (damage-first, block-second in Act 1); later acts price
  block via the §5-C capability delta.
- Spirebird deliberately NOT overridden (owner: "the hope is that Spirebird knows
  better than our ability to express my vague card opinions").
Also filed from the A/B: duplicate-copy dampening (the Pommel x2 pattern) — pending
owner review.
## 2026-07-13 (Fable 5, session 3 cont.) — Routing batch bfm3sv4yj VERDICT: swerve cured, avoidance now honest; the wall is boss competence

**0/10, act-reach 1.40, elites 0.1/17 — but the mechanism changed completely: ZERO
'route to Elite' decisions all batch (vs 27 per 20 runs pre-fix).** The
route-then-swerve pathology is gone; the capability projection prices elites for the
actual deck from floor 1 and consistently declines. Given SIX Act-1 boss deaths in
the same batch (Soul Fysh, Vantom x2, Lagavulin@75, WG, Kin — the decks can't beat
REGULAR bosses), that refusal is probably TRUE, not timid.

Causality now legible: weak boss-fight competence -> capability gate correctly closed
-> no elite relics -> weak f33+ decks. The unlock is NOT the gate or its knobs — it is
making the fights winnable (ENEMY_PASS Phase-1 per-boss handlers + deck quality); the
same gate then opens by itself. Options (b) hysteresis / (c) boss-need shelved as
moot for now: there is nothing to stabilize when no elite route exists, and boss-need
modulation without fight competence just schedules deaths.

Next: the owner pilots seed CJN9M609YW (the Soul Fysh @56hp loss) via `sts2bot record`
for the human-vs-bot A/B — draft/route drift + the Soul Fysh counter-play as the
Phase-1 handler spec.

## 2026-07-13 (Fable 5, session 3 cont.) — capability routing ships; Foul saga; R1+R2 batch cold at 1.40

**Capability-aware routing (owner pick (a), 9e8ca68)**: elite/boss nodes project the
current deck's §5-C estimate (median over the act's real elite pool; _upcoming_boss for
the boss); monsters use the mean not p75. The routing-test fixture got honest:
Strikes+Bludgeons prices at ~46 HP/elite (2.6 block/turn) and correctly isn't worth a
relic chase — HP-gating tests now use an elite-ready deck. Act 2/3 elite sub-pass ARMED
in ENEMY_PASS (owner): fires if elites_fought AND elite-death share both rise.

**Foul Potion saga (owner watched one live)**: claimed from Grab Potions (discarding a
Speed Potion for it — belt-room logic didn't compare values), then DISCARDED for an
ordinary reward potion before ever meeting a merchant (rank 'downside' = first out).
Fix: Foul ranks 3 (~100g, above junk, below real combat potions) and reward discards
now fire only for a genuine upgrade (incoming rank > worst-in-belt, from the reward's
live description — RewardItem now parses potion_description). The merchant throw
remains live-unvalidated: the next Foul should survive to a shop.

**R1+R2 validation batch bow305spn: 0/10, act-reach 1.40 (cold) — SEVEN Act-1 boss
deaths** (Soul Fysh x2, Lagavulin x2, Vantom, CB, Waterfall Giant; entries 42-62hp),
one f48 Queen loss, elites 0.4/11. Ten runs can't judge R1+R2; what it shouts is the
f17 wall again — ENEMY_PASS Phase-1 per-boss handlers (Kin, CB low-HP Ringing phase,
Soul Fysh block-bypass) are the standing open items this keeps pointing at.

**Relic pass R2 shipped** (same session as R1): the ten end-of-turn conditional relics
evaluated on the plan's END state in _score — Orichalcum (planner stops burning Defends
the relic covers), Cloak Clasp, Sturdy Clamp, Ice Cream (banked energy, no waste
penalty), Parrying Shield / Screaming Flagon damage credits, Pael's Tears / Art of War /
Pocketwatch next-turn credits. Runic Pyramid deliberately skipped with reasoning
(retention does NOT defuse Beckons). Pass status: R1+R2 = 28 relics modeled + Pen Nib.

**Morning batch bb6qu53b2 (pre-R1 code): 0/10, act-reach 1.70, relics 6.8, elites
0.1/22.** Usual kill list (KD x2, Insatiable, Kin, CB, Lagavulin Matriarch; Hunter
Killer x2, Slumbering Beetle x2 in hallways).

**Elite finding (probe, last 20 runs): the gate is NOT the bottleneck — routing
stability is.** 27 'route to Elite' decisions were made, but ~2 elite fights happened:
the bot plans a path TOWARD an elite, then re-plans away as per-floor projections
shift. Nearly all path values run negative (-54..-253) in late acts — death-class
pricing dominates the map. Filed for a dedicated routing-stability look (owner
philosophy question: commitment vs re-planning).

## 2026-07-13 (Fable 5, session 3) — RELIC TRIGGER PASS R1 SHIPS: 18 relics modeled in one morning

The §8.5.6 pass, card-pass playbook applied to relics: corpus harvest (180 relics,
live text, 23 live counters) -> 12-agent audit in 96s (132 A / 14 B / 31 C / 3 D) ->
RELIC_PASS.md -> tranche R1 implemented. Key audit insight: class A is huge because
anything materializing as visible status/energy in the polled state needs NO modeling
— the blind spots are triggers fired mid-turn by the bot's own sequencing.

R1: the RelicTrigger engine — per-turn counters as pure functions of play counts;
lifetime counters (Nunchaku/Tuning Fork) continue the mod's live counter, Pen Nib
pattern. Letter Opener/Lost Wisp trigger damage participates in LETHALITY (3 Defends
now kill a 5-HP enemy through Letter Opener); Gremlin Horn's kill->energy+draw chains;
Shuriken/Kunai mid-plan Str/Dex affect later cards. Paper Phrog rides yesterday's
Cruelty vuln lane (75%); Velvet Choker rides the Ringing card-cap machinery from relic
text. Centennial Puzzle armed-at-full-HP (under-credits, never over). R2 (end-of-turn
conditionals) and R3 (first-per-combat latches) filed in RELIC_PASS.md.

## 2026-07-13 (Fable 5, session 3) — Bowlbug pin RESOLVED by corpus forensics: no guard mechanic (owner right)

Instead of the seed replay, scanned all 91 Bowlbug fights in the corpus (917 attack
plays) comparing submitted target vs which enemy actually lost HP: **662 normal, 3
"redirect"-pattern (0.3%), and Nectar was hit normally dozens of times with Rocks
alive.** No guard mechanic — the fatal trace was a stale-state/interleaving anomaly
(same family as the duplicate-submission race; all 3 events are from the 4x era, and
the new debounce should suppress the cause). _GUARD_PAIRS stays empty; the redirect
machinery remains tested-but-dormant for any future genuinely-guarding enemy.
Method note: corpus forensics beat a live seed replay — faster, no divergence risk,
and 917 data points instead of one.

## 2026-07-13 (Fable 5, session 2 cont.) — Batch bfawc8h74 (everything live + new potion epoch): 10/10 clean, act-reach 1.80

First batch with the full stack (debounce, Omnislice targeting, Ancient-uncommon,
spend-down, Cruelty, Replay, elite gate 0.50): **0 wins, act-reach 1.80, relics 6.4,
elites 0.3/21 — and zero infrastructure incidents** (the previous batch's two bug
classes did not recur). Max depth A3 f38; three Vantom f17 boss deaths (Vantom is
heavily represented in the Act-1 roster lately); one death TO a Decimillipede elite.

Owner catches during the batch, both shipped same-session:
- **Armaments+ stranded** when block was moot -> hand-upgrade rider credit
  (w_hand_upgrade per actual unupgraded target; 22878f3).
- **Bowlbug "guard redirect"** (run 8, seed 9LM6ALXZAQ): an attack aimed at the 2-HP
  Nectar damaged the Rock instead -> modeled, then PINNED at owner direction (never
  seen such a mechanic in play; rival hypotheses: mod-side target-resolution bug,
  stale-state misattribution). Machinery ships tested but DORMANT (_GUARD_PAIRS empty);
  verify by seed replay of 9LM6ALXZAQ before enabling (epoch permitting).
Also filed: Imbalanced (Bowlbug Rock) block-to-stun is an exploitable enemy-pass item;
hail-mary potion standalone-usefulness check still queued.
- **Bloodletting suicide (run 10, owner-caught)**: at 3 HP both branches sat on the
  projected-death wall, so the energy bonus broke the tie into a self-kill. Fix:
  self-lethal HP costs are an ABSOLUTE VETO in the playable filter, not a scored
  preference (certain self-death loses now; the enemy turn at least has variance).

## 2026-07-13 (Fable 5, session 2 cont.) — Batch btc3g1ycl HALTED at 8 (C5): two new bug classes surfaced, both fixed same night

The everything-live batch (spend-down + Cruelty + Replay + elite gate 0.50): **0 wins,
six A1 f17 boss deaths, one A3 f45, then a C5 halt on run 8.** Cold on the surface, but
the batch earned its keep by surfacing two latent bugs:

1. **Owl Magistrate wedge (run 2, owner-caught live)**: a stale state poll made the loop
   resubmit an accepted Stampede+ play; the duplicate wedged an engine hook, the hand
   locked as BlockedByHook, and a COMPUTED LETHAL (Ashen Strike math checks out: ~28
   into 21 HP) died on the vine at 4 HP. Fix: duplicate-submission debounce in the
   orchestrator (94cdba6) — identical decision on an unchanged fingerprint holds up to
   20 ticks. Old logs show duplicate spam was routine; only hook-carrying powers punish it.
2. **Omnislice targeting (run 8, the C5 halt)**: splash-AoE ("Damage ALL other
   enemies...") is aoe in the sim but target_type=AnyEnemy in the game — submitted
   targetless, rejected 8x, error rail halted the batch. First-ever Omnislice draft
   (the step-2 tags picked it), so the latent bug had never fired. Fix: PlannedCard
   carries requires_target from the game's own target_type.

The f17 streak (6 deaths, boss entries at 40-83hp, mostly 0 elites fought) is the known
Act-1 boss-competence wall, not the new elite gate — engagement rose only to 0.2/run.
Elite gate 0.50 + Ancient-uncommon + debounce + Omnislice fix all land for the NEXT batch.

## 2026-07-12 (Fable 5, session 2) — Batch b0qaobh7g (step-2 drafting live): 1 WIN, act-reach 1.90 — best batch ever

First batch with deck-context drafting: **1/10 WIN (the first ever), act-reach 1.90**
(day's progression: 1.60 -> 1.70 -> 1.70 -> 1.90), relics 7.2, TWO Act-3 runs (f48 win
+ f42 loss to Lost and Forgotten with 13 relics), five Act-2 runs, three A1 boss deaths
(Waterfall Giant x2, Lagavulin Matriarch). Elites: 0.0/17 again — the gate stands
over-tight (owner: fundamentals first; revisit after the pass ladder).

Same-evening owner catches during the batch: the 500g/1423g last-shop leaks (fix
shipped 0c12c64, next batch), Cruelty's +25%-vs-Vulnerable not modeled (fixed below),
Replay-N enchant unmodeled (no live capture in 365 runs — awaiting exact wording).

## 2026-07-12 (Fable 5, session 2) — ★ FIRST BOT WIN ★ (run 3 of batch b0qaobh7g, seed FSD4ZEBD4Z)

**The bot won a full Act-1-through-Act-3 run** — first victory in ~365 logged runs, on
the FIRST batch with step-2 deck-context drafting live (plus today's _POWER fix). Act 3
f48, 753 decisions, killed the QUEEN round 6 and survived at 11/79. Owner watched live.

The deck is a textbook tag-machinery deck — the Vulnerable package (Bash, Tremble,
Dominate++, Molten Fist++, Taunt++ x2) feeding Sword Boomerang x3 + Inflame, and the
self-HP-loss package (Bloodletting x3, Offering x2, Feed): exactly the archetype
coherence the step-2 conditionals were built to produce. Bosses beaten en route:
Lagavulin Matriarch (A1), The Insatiable (A2), Queen + Torch Head Amalgam (A3).
Relics: Runic Pyramid, Centennial Puzzle, War/Gnarled Hammer, Happy Flower (14).

Owner-caught during the same run: left the last Act-3 shop with ~500 gold unspent —
last-shop spend-down filed and implemented right after (gold has zero terminal value).

## 2026-07-12 (Fable 5, session 2) — CARD-PASS STEP 2 SHIPS: deck-context drafting (owner-reviewed same evening)

The draft pass, end to end in one evening: 12-agent audit of all 157 draftable cards
(3 min, wf_1c79ed42-a44) -> proposal doc -> live owner review (32 review-log items,
several audit rows factually overridden: Prolong snapshots block, Lethality underrated,
Dark Shackles is multi-attack-profile not boss-scaling, Havoc plays Powers fine) ->
implementation shipped (737d128 + 5f554dd).

What landed: `policy/drafttags.py` (weighted provides/needs tags; bonus per met need;
penalties ONLY for pure payoffs at zero providers with an Act-1 speculative discount;
anti-synergy docks; copy caps; controlled-exhaust thinning; upgrade-awareness) +
`data/card_draft_tags.json` (127 cards, curated via scripts/build_draft_tags.py) +
removal policy reading the same table (Fasten protects Defends, Perfected Strike
protects Strikes) + Ancient/Event rarity fix + Feed on-fatal kill-sequencing credit.
Owner's structural principles baked in: chicken-and-egg (enablers stay pickable),
self-provision (Dominate), stack-magnitude weights (Tremble 3 > Bash 2), per-proc
autoblock (Stone Armor). 305 tests, replay clean over 107k states.

Deferred (filed in PLAN §8.5.4): boss/enemy-profile conditionals, act-decay riders,
deck-size conditionals; two relic-pass pointers banked. Elite gate deliberately NOT
touched (owner: fundamentals before parameter tweaks; the tension is real until the
bot can actually win elite fights).

## 2026-07-12 (Fable 5, session 2) — Batch bk9xif371 (post-_POWER-fix): act-reach 1.70, 7/10 to Act 2, but ZERO elites fought

First batch with player Strength / cross-turn Vulnerable / Colossus halving actually
credited. **0 wins, act-reach 1.70 (= baseline), relics 5.8/run, elites 0.0/19 offered.**
Shape shifted: more consistent (7/10 reached Act 2 vs 6/10, five f33 boss deaths), less
top-end (max A2 vs the baseline's f48). Deaths: KD x2, Kaiser Crab x2, Insatiable,
Lagavulin Matriarch (A1 boss variant, post-leak-fix data), Soul Fysh, Hunter Killer f25,
Exoskeletons f31, Ruby Raiders f8.

Read: the Strength fix can't move act-reach much in one 10-run sample, and the f33
deck-power wall stands. The louder signal is **elites_fought 0.0** (baseline 0.4, June
~0.7): zero elite relics -> relics 5.8 vs 6.9 -> thinner decks at the wall. Yesterday's
f48 run fought 2 elites and rode the relic engine. The death-class elite pricing may now
be over-tight — worth revisiting elite_gate_pool_win_frac (0.67) or the pool math,
especially since the capability estimate still ignores the planner's new damage credits.
Flagged for owner before touching config (policy-config changes get their own commits).

## 2026-07-12 (Fable 5, session 2) — Batch bq4bppl4y: act-reach 1.70 (best of the July batches); f48 Aeonglass run

First live batch on the main machine, 10/10 clean at 4x, zero stalls. **0 wins,
act-reach 1.70 (July batches ran 1.60-1.62), relics 6.9/run.** Deepest run: f48, died
to Aeonglass with 17 relics (Pandora's Box + Kusarigama/Candelabra engine), entered the
boss at 85hp. Kill list: Kaiser Crab, Soul Fysh, Ceremonial Beast, Knowledge Demon x2,
Slumbering Beetle, Aeonglass, Ovicopter, Kin, Vantom.

*(Correction, owner-caught: I first logged this as "first Act-3 run in a batch" — wrong.
The 355-run corpus holds 13 Act-3+ runs (June batches included), and one victory is in
the books: the owner's recorded manual run of 2026-07-08. The bot itself is still 0-for.)*

Caveats and reads:
- Ran on PRE-fix code for the _POWER family (below) — this is the baseline; the player-
  Strength credit lands next batch.
- Four A1 f17 boss deaths (entered at 52-80hp) — Act-1 boss variance, not a route issue.
- elites_fought 0.4/run of 18 offered (prev 0.7/36): consistent with death-class pricing;
  the f48 run fought 2 and banked the relic engine that carried it.
- The Gambit was never offered, so the draft gate stays live-unvalidated (harness-tested).
- Owner live-caught the Colossus/Ringing miss mid-batch (run 1) -> the _POWER forensics.

## 2026-07-12 (Fable 5, session 2) — The _POWER-suffix bug family: player Strength was NEVER credited live

Owner live-caught (run 1 of the first main-machine batch, Ceremonial Beast boss, a
**Ringing** turn — RINGING_POWER "You can only play 1 card this turn."): beast
Vulnerable(4), 15 attack telegraphed, and the bot cast Defend (5 block) over Colossus
(5 block + halve damage from Vulnerable enemies). Strictly dominated choice.

Forensics (decisions.jsonl has the full state; the round-6 record reproduced the miss
offline exactly): `_enemy_sims` matched `p.id.upper() == "VULNERABLE"` but live status
ids carry a `_POWER` suffix (`VULNERABLE_POWER`) — pre-existing Vulnerable was invisible,
so Colossus' halving never fired. The same exact-match pattern hid two bigger truths:

- **`pid == "STRENGTH"` (player): Strength has NEVER been credited in a live plan.**
  Every Demon Form / Strength-potion / Anger deck under-estimated its own damage; all
  conservative (real damage ≥ planned), which is why 345 runs never surfaced it.
- **`pid == "BARRICADE"`: block carryover never detected.**
- Cross-turn Vulnerable (applied last turn) also lost its 1.5x attack credit — only
  same-turn Bash→follow-up synergy worked, because the sim tracks its own applications.

Fix: `startswith()` on all three (safe vs a hypothetical INVULNERABLE). Also mirrored
the Colossus halving into the reported `hp_loss` diagnostic (hail-mary reads it). Tests
now use the live `_POWER` id shapes — the old fixtures used bare ids, which is exactly
how this family passed 292 tests while failing live. Repro confirms Colossus wins the
Ringing turn (4.7 vs −12.5). 292 tests, replay 101k states clean.

**Lesson recorded**: status-id fixtures must copy the live payload shape verbatim.
Batch bq4bppl4y (runs 1–7+ at this point) ran on the OLD code — it stays a valid
baseline for the delta fixes; the Strength credit lands for the NEXT batch.

## 2026-07-12 (Fable 5, session 2) — Gambit gate + Summon-as-block ship (70bd4a5)

The two queued quick singles: The Gambit (self-death rider → never play, never draft;
"die" appears in no other catalog card) and Summon N → +N block-equivalent (no companion
state in the mod API — probed 40 runs; full Osty model filed as mod-fork TODO).

## 2026-07-12 (Fable 5) — Reverse handoff COMPLETE: back on the main machine, full corpus restored

Owner returned and moved everything back (no OneDrive involved — the path is legacy
naming; the old `StS2bot` folder remains as archive-in-waiting). Spin-up verified:
- Repo at 2eccfa5 (61 commits pushed from the laptop), venv **rebuilt on Python 3.14**
  (laptop venv pointed at a 3.13 that isn't installed here), **280 tests + ruff green**,
  config hash `93676cd0fe72` intact (the .gitattributes LF pin doing its job).
- **logs/ MERGED: 345 runs** (June's ~110 + July's ~235). Rebuilt from the full corpus:
  **bestiary 75→101 enemies** (all SIX Act-3 bosses incl. Queen/Aeonglass/Test Subject
  #C10; the Knights trio; Entomancer; 62 statuses), **card_effects 284** texts,
  **combat_stats** re-grounded (monster p75 15, elite 35, boss 41; n=1836/195/284),
  catalog **seen-set 149→176**.
- Game **v0.107.1 unchanged** → the June mod build is still valid, no rebuild.
- **Profile verified: CUSTOM_AND_SEEDS_EPOCH revealed** — the seeded per-boss harness is
  BACK — plus Underdocks/Undergrowth/Glory discovered, 4 wins, Steam Cloud OFF.
- CLAUDE.md game dir re-pointed to `I:\SteamLibrary`; HANDOFF marked complete; the
  seeded-harness memory corrected to AVAILABLE.

Next up (from the 07-09 close): The Gambit death-rider gate + Osty companion model,
then card-pass step 2 (the draft pass — its gate condition is met), then the relic
trigger pass. And the first full 40-run win-rate batch once step 2 lands.

## 2026-07-09 (Fable 5, session 2 — close) — Batch bzgprtnae: tranche C validated in the wild; elite deaths are pure topology now

**Batch (10 clean): 0 wins, act-reach 1.60, relics 6.6/run** — second-best depth ever,
right behind yesterday's 1.62; six runs past Act 1, three f33 Act-2 boss runs (Kaiser
Crab, Insatiable, Kin/CB at f17; Obscura f31, Beetle f28, Exoskeletons f23).

**Tranche C is alive in the plans**: Bully in 84 plan lines, Ashen Strike 106, Colossus
52, Dominate 21, Forgotten Ritual 12, Evil Eye 10, Mangle 11 — the new scaling visibly
changed play. No regressions observed.

**Elite forensics: the residual is pure map topology.** The Entomancer run's log is
conclusive — the bot chose AGAINST elites at every real fork (Unknown 31.8 > Elite;
Monster 24.7 > Elite; RestSite > Elite) and every fatal elite entry was a single-option
row at hugely negative path value (−164/−136/−129/−158/−112: the death-class pricing
screaming into a map with elite chokepoints). Phrog f9 likewise forced (−62). Nothing
left to fix at the policy layer; this is variance.

**Slumbering Beetle 4th death, exoneration RE-CONFIRMED**: zero attacks into the
sleeper across the fight. Act-2 pack-vs-entry-HP remains the real storyline.

Still unrolled: Lagavulin post-leak-fix, merchant Foul-throw, Pen Nib post-fix.

## 2026-07-09 (Fable 5, session 2 — night) — PEN NIB SAGA CLOSED; tranche C ships; the tripwire retires

**Pen Nib, validated and corrected after ~130 runs** (batch b0j3rzhj1 run 1 drove the
counter through 9): the owner's June gotcha was REAL — at counter 9 the game pre-doubles
every attack's rules text (Strike "Deal 12", Salvo "Deal 24"), so our own pen_double on
top of the doubled parse was a 4× over-credit, and later attacks parsed doubled without
doubling. New model: a turn STARTING at 9 takes the first attack's parsed damage at face
value and halves later attacks back to base (`pen_turn_started_at_nine`). Live compose
sighted: `[Not Yet > Strike]` — heal first, then the doubled hit. **The TEMP tripwire is
removed** (its fence's own condition met; its final act was surfacing this very bug).

**Card-pass tranche C shipped** (6 clustered mechanics, 10 cards): per-target-Vulnerable
scaling (Bully/Dominate), Molten Fist's vuln doubling, enemy-Str-down (Dark Shackles/
Mangle → incoming reduction), the exhausted-this-turn flag gating Evil Eye + Forgotten
Ritual (the DFS now sequences an exhauster first — the f44 Burning-Pact→Ritual line is
plannable), Expect a Fight = energy per Attack in hand, Ashen Strike exhaust-pile
scaling, Colossus' vuln-damage reduction in the score. Validates next batch.

**Batch b0j3rzhj1 (10 clean): 0 wins, act-reach ~1.4** (Insatiable f33, Kaiser Crab f33;
Soul Fysh ×2, Waterfall ×2, CB, Slumbering Beetle f24, Hunter-Killer f24, Crawlers f7).
**Slumbering Beetle's THIRD run-kill** → trace-audited and EXONERATED (same night): the
bot ignored the sleeper correctly (Slumber ticked on turns, hits went to the Bowlbugs);
the deaths are route/entry-HP losses (18/80 into a 3-enemy pack) wearing the Beetle's
name. No per-enemy model needed; the wake-turn under-block is the filed §5-C
next-turn-horizon class. Also
2nd kill for Hunter-Killer (Tender). Owner live-caught during the stretch: Infernal
Blade unplayed (attack-generator credit), the Phrog false-LETHAL (spawns_on_death),
Retain-curse discard ranking + refinement, Normality retroactivity documented.

Still unrolled live: Lagavulin post-leak-fix, merchant Foul-throw.

## 2026-07-09 (Fable 5, session 2 — evening) — Card pass lands; act-reach 1.62 (best ever); gate calibration answered

**The card pass** (CARD_PASS.md): step 0 catalog (250 cards, full rules text from the
mod's own compendium+wiki, no scraping) → step 1 fan-out (13 subagents, EMPIRICAL parser
checks per card) → 149 classified: **76 A verified / 22 B parser gaps / 40 C planner
mechanics (pattern-clustered) / 11 D multi-turn filings** → `data/card_notes.json` is the
checklist. **Tranche B shipped same evening**: 8 parser fixes covering 17 cards
("Deals" companion damage, twice/thrice hits, compound debuffs, trigger-sentence scoping
that also fixed the whenever-power over-credit class, retrieval-as-draw, Plating,
splash-AoE, Shiv approximation). Owner live-catches folded in as they happened:
Infernal Blade attack-generator credit, the Phrog false-LETHAL (spawns_on_death +
unified _fight_over), the **curses pass done inline** (Normality hand-cap + all 9
audited), Retain-curse discard ranking (+ same-day refinement: parking ≈ one junk-tier).
One self-inflicted crash (potion bookkeeping vs the battle-less loading state) caught by
the C5 rails and fixed with the raw transitional payload as a regression test.

**Batch bxpnvd8ck (7 real runs + a Timeline block): 0 wins, act-reach 1.62 — best ever
logged.** Two Act-3 runs: f45 (died to the KNIGHTS elite — the owner's f44 one-turn-kill
pack; 43 floors toward the skill-gap benchmark) and f39. **Gate calibration ANSWERED**:
the f45 run fought 3 elites and banked 12 relics — the pool gate reopens for a
strengthened deck exactly as designed; weak decks still abstain (0.5 elites/run overall).
**KD handler 2nd live exam: 7/7 Disintegration picks, 11 fully-blocked cursed
decision-states.** Batch interrupted at run 9 by another Timeline epoch (DARV_EPOCH —
the deep runs' scores crossed a threshold); 2 runs owed after the owner's click.

Still unrolled: Lagavulin (sleeper no-op), merchant Foul-throw, Pen Nib counter 9.

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
