# Lab Notebook

*Newest first. One entry per live session / milestone (see PLAN.md §6).*

## 2026-09-30i (Fable 5) -- batch 6 cut at 2/25 (boundary stop); batch 7 launched with Tainted + the gated budget

Batch 6 (code f413d30/36b9e43 across the crash; 25 clean at A0, 1 crash
error): **2/25 (8%)** -- wins XE51ZG3AEY, U0315K3J4T. Act reach 1: 9, 2: 14,
3: 2. Killers: Kaiser 5, Waterfall 5 (all eruption deaths, on the soft
budget), KD 3, Chompers 2, Entomancer 2, Prisms, Decimillipede, Beetle,
Mecha Knight f43, Queen, Vantom, Fysh. Stopped at the run-21 boundary of
the resumed segment: the soft eruption budget was gated off (c8ec19c) and
the Prism Tainted model landed (1e98ce2) while it ran, so its remaining 16
runs on known-harmful code were not worth the measurement time. Pooled A0
on the promoted keys: 48/285 (16.8%); the last two batches (12/40 then
2/25) bracket the variance a 40-run batch carries.

Batch 7 (bnn9l8fgh, code f1303d9) launched on the same session; its run 1
continues the run the stop interrupted at floor 2. First batch with the
Tainted model, the gated soft budget, the Exoskeleton per-hit cap and the
Enthralled rule together.

## 2026-09-30h (Fable 5) -- batch 6 cold at 2/23; act-2 elite tail; Infested Prism's Tainted decoded and modeled; soft eruption budget gated off

Batch 6 (resumed, code 36b9e43) through run 19: 2/23 clean overall. Act 2
is the sink: 12 of the 16 runs that reached it died there (75% vs 35% in
batch 5), mean loss per early-act-2 fight 16.0 vs 12-13, same p75 -- the
tail moved, not the middle. Blowout list: Infested Prism x8 at 32-47,
Decimillipede x3 at 57-68, the Keep-the-Key knight x2 at 51-58, Bowlbug
packs 42-56. Prism losses averaged 25 (13 fights) vs 11-16 in batches 4-5,
Decimillipede 36 (5) vs 15-16. No batch-6 code path touches those fights
(the per-hit cap regex matches nothing on them) -- but the Prism tape
showed an unmodeled mechanic: Vital Spark 'ALL Skills are Tainted N' ->
each Skill 'Gain N Tainted when played', Tainted = '+N damage from Attacks
this turn' PER HIT. A Defend into 5x3 blocks 5 and adds 6; a 5x3 landed
for 31 after two Skills. Modeled (next commit): tainted stacks + per-Skill
rider -> incoming += stacks x hits; potions untaxed. Lands with batch 7.

Also: the Waterfall Giant soft budget ran 5/11 (45%) vs 32/46 with fights
two rounds longer and stacks to 54 -> gated off (eruption_budget_mult=0,
c8ec19c); the kill-turn accounting stays. Kaiser refresh: 31/57 (54%);
entries <60 HP win 2/15, 60-70 14/22, 70+ 15/20 -- the pre-boss rest line
(~56) admits exactly the losing band (per-boss rest candidate). KD shows no
entry-HP dependence (70%+ every bucket; batch 6's 1/4 is noise). Three
early-elite deaths at floor 7 in two batches: floor<=8 with deck<=12 =
4/36 (11%) vs 3/121 (2.5%).

## 2026-09-30g (Fable 5) -- batch 6 opened 1/4, then the game crashed (~9 h session); relaunched, batch resumed

Batch 6 (bbunrocnv, code f413d30) ran four clean runs (1/4: XE51ZG3AEY won;
Queen, Waterfall, Mecha Knight f43 losses) and then run 5 died at floor 16
to 'connection forcibly closed by the remote host' -- the game process was
gone (the 09-03 crash signature, ~9 h into the session after batch 5's
40). Abandon recovery needs a live server, so the batch stopped on C5.
Relaunched via the steam_appid procedure (menu in ~45 s), profile 1
verified, Continue available; batch 6 resumed as a fresh 40 (bzwwjezq5,
code 36b9e43 = same policy code) whose run 1 continues the crashed run.
Third long-session failure (09-03 crash, 09-29 hang, 09-30 crash): the
periodic-relaunch candidate in PLAN section 7 now has three data points --
all past ~3 h / 35+ runs at 3x.

## 2026-09-30f (Fable 5) -- batch 5 closes 12/40, a new record; batch 6 launched

Batch 5 (b65is18sx, code 262d1aa = sleeper v4 + True Grit sequencing +
Setup Strike temp-Str parse + Entomancer hive + Waterfall eruption budget;
40/40 clean at A0): **12/40 (30%)** -- wins DL9A0TXAV9, 6Y4YWW7YGV,
XKD12ULC2G, XPP8MBWNHF, FQKCA8HMYV, ZRYD017JUV, 6HNJJVWANV, S5P7PTEM1X,
ULUDQLJFE1, W7ZC9SN3CU, GG9B249QJK, JYE5K14JP5. Act reach 1: 14, 2: 9,
3: 17 -- and **12 of the 17 act-3 arrivals converted (71%)** vs 3/16 in
batch 3 and 3/13 in batch 4. Composites: act reach 2.08, relics 11.1,
elites 5.0/run of 185. Killers: Kaiser 4, Waterfall 3 (all eruption deaths
from single-digit HP where no line lived), Aeonglass 3, Ceremonial Beast 3,
Exoskeletons 2, Vantom 2, KD 2, Fysh 2, singles (Kin, Entomancer,
Sculptor/Enthralled stall, Matriarch, Byrdonis f7, Phrog f7). Act-1 boss
record 22/33 (67%); Matriarch 4/5 on sleeper v4 (era 45%).

Pooled A0 on the promoted keys: **46/260 (17.7%)**. Under the pre-batch-5
pooled rate (15.5%) a 12/40 batch has ~1.5% probability, so the mechanic
fixes of 09-28..30 read as real, though one batch is one batch. Early-elite
tally refreshed: floor<=8 with deck<=12 = 4 deaths / 36 fights (11%) vs
3/121 (2.5%) on bigger decks -- still a data note, owner's call (the deck
floor arm overshot once).

Batch 6 (bbunrocnv, code f413d30) launched on the same session (2.4 GB,
8.4 h): adds the Exoskeleton per-hit cap and the Enthralled must-play-first
rule. If it holds near 25-30%, the pooled definitive read starts moving
toward the 20% bar; the next 40 decide.

## 2026-09-30e (Fable 5) -- batch 5 at 3/15; Enthralled locked the hand for four turns (stall fixed)

Batch 5 through run 15: 3/15. Run 9 was the first Waterfall Giant fight on
the eruption budget: the term correctly refused a kill at 8 HP into a 33
blast (blocked instead), but the deck (59-HP entry, ~30 dmg/turn vs 240
HP) was lost by round 6 either way -- capability, not the model. Run 12
entered an Entomancer elite at 22/87 via a forced Shop -> Unknown ->
Unknown -> Elite lane (the second Unknown was a 32-HP fight): the
optionality item, nothing new.

Run 15 (0BWV4FMJFB) died at act-3 floor 35 from an 80/80 entry to a
'weak' Devoted Sculptor: the tape shows FOUR consecutive end-turns at 4,
8, 12, 16 energy with a full hand while Ritual ramped the enemy 21 -> 48.
Cause: Enthralled ('must be played before other cards. Eternal.') locks
every other card until played; the planner saw no value in it. Era: 42
such stalled turns in the 69 runs that drew it. Fix (next commit): a
playable, affordable must-play-first card is played before any search.
Lands with batch 6 along with the Exoskeleton per-hit cap.

## 2026-09-30d (Fable 5) -- batch 5 opens 3/8; Exoskeletons' Hard to Kill was read as a per-turn cap

Batch 5 (code 262d1aa) through run 8: 3/8 (wins DL9A0TXAV9, 6Y4YWW7YGV,
XKD12ULC2G). Two Exoskeletons hallway deaths (runs 3, 7) against 0 deaths
in 122 era fights sent me to the tapes: 52-53 HP entries, the planner
spending Bully/Dominate/Dominate into one body. Status text: 'Reduce all
damage taken and HP lost by Exoskeleton to 9' -- and a live turn where one
body lost 27, so it is a PER-INSTANCE cap. The mechanics detector had
folded that wording (and Soul Fysh's Intangible) into the per-turn cap
built for Hardened Shell, so the sim and the rollout wrote off every
follow-up hit into a body that had taken 9: multi-hit cards read as waste
against the one pack they beat. Fixed (next commit): dmg_cap_per_hit
through detect_mechanics, EnemySim, FightEnemy and the rollout; per-turn
stays for Hardened Shell. Not a regression from the new models (no parser
overlap; era code had the same reading) -- batch 5's two deaths were the
era's 7% blowout tail landing on weak decks. Lands with batch 6.

## 2026-09-30c (Fable 5) -- batch 4 closes 5/39; batch 5 launched with the hive + eruption models

Batch 4 (b3sxi5cgj, code b432f16 = + Setup Strike temp-Strength fix; 39
clean at A0 + 1 treasure wedge): **5/39 (12.8%)** -- wins YSVE7X42L5,
QEFPEP9MQ0, 2HNVDL5MAQ, P7TQKFWU9C, 4S7RAEWLQM. Act reach 1: 8, 2: 18,
3: 13; composites act reach 2.15, relics 11.6, elites 5.5/run of 174.
Killers: Entomancer elite 4, Insatiable 4, Queen 4, Test Subject 4, KD 3,
Waterfall 3, Kaiser 3, Hunter Killer 2, singles. Act 2 was the sink this
batch (18 runs ended there: 10 bosses, 4 Entomancer, 4 hallways after
upstream bleeds). Pooled A0 on the promoted keys: **34/220 (15.5%)**.

Batch 5 (b65is18sx, code 262d1aa) launched on the same game session (2.2
GB, responsive, 4.3 h up): first batch with the Entomancer hive model and
the Waterfall Giant kill budget, on top of sleeper v4, True Grit sequencing
and the Setup Strike fix. The mechanic fixes since 09-28 each target a
named loss cluster (Matriarch pokes, Waterfall eruptions, Entomancer
blowouts); whether they move the pooled rate is what batch 5 measures.

## 2026-09-30b (Fable 5) -- Waterfall Giant: 13 of 14 deaths were the post-kill eruption; kill budget modeled

Batch 4 through run 36: 5/35 clean (+1 wedge). Act-2 bosses this batch:
Insatiable 3/7, KD 3/6, Kaiser 3/6 -- the Kaiser full-HP loss (79/80 entry)
was the two-claw grind under Frail with the race rule skipping 4-block
Defends (owner-reviewed line, left alone). 'Keep the Key' era check: chosen
9/9 at >=45% HP, 3 wins and 7 act-3 reaches of 9, so the catalog note holds;
the gate prices the Mysterious Knight as a 10-HP hallway while it costs 26
mean / p75 40 and killed 2 of 9 outright (data note only).

WATERFALL GIANT: runs 34 and 35 both died to the eruption, so the era tally
-- 13 of 14 WG deaths on the promoted keys were the telegraphed post-kill
blast, kills taken at 2-29 HP vs 30-42 blasts. The blast size is a visible
status from round 2 (STEAM_ERUPTION_POWER N, +3 per move) and the sim
treated the kill as fight-over, so the race ran at 0 block into it. Fix
be33aa1: the kill is non-terminal (like a dead spawner); the pending blast
minus an 8-block hand (eruption_expected_block) is charged on the kill turn;
while it lives, HP below (next stack - 8) pays the scarcity rate as a soft
budget. Replay r6 of 20260930-020512: [Defend > Spite > Cinder] instead of
the all-attack race; r7's kill still taken (both lines die). 653 tests.
Lands with batch 5 alongside the Hive model and the Setup Strike fix.

## 2026-09-30a (Fable 5) -- batch 4 mid-batch: treasure wedge is relic-agnostic; Entomancer's Personal Hive decoded and modeled

Batch 4 (b3sxi5cgj, code b432f16) through run 16: 3/15 clean (wins
YSVE7X42L5, QEFPEP9MQ0, 2HNVDL5MAQ) + run 10 lost to the treasure-claim
wedge at act-3 floor 41. Corpus tally: 19 treasure wedges on 16 different
relics -> a claim-transition race, not a relic; PLAN section 7 row filed
(try save_and_quit + Continue before abandoning; owner's C3 call).

Two act-2 hallway deaths (Hunter Killer f28, f31) were both decided
upstream: f26 elite 56 -> 13 into a campfire-less lane (the known
optionality item), and f24 Entomancer 80 -> 7 from FULL HP. That fight
exposed an unmodeled mechanic: Personal Hive -- a Dazed into the draw pile
per HIT taken, stack raised by Empower -- so Uppercut+/Whirlwind/Byrd
Swoop/Pillage flooded the deck (four Dazed in hand by r6, then 7x5
unblocked). Era: 135 fights, 3 deaths, mean loss 12, but 10 blowouts >=40
(7%) = exactly the act-2 attrition behind the low-HP Kaiser/Ovicopter
entries. Modeled (next commit): hits x stacks x w_hive_dazed (-2.5, one
dead draw each), killing turn exempt; decode in enemy_notes. Lands with
batch 5.

## 2026-09-29b (Fable 5) -- batch 3 closes 3/33 on a game hang; the wall has moved to act 3; batch 4 carries the parser fix

Batch 3 (b1gazilda, code ad1839e = sleeper v4 + True Grit sequencing, all
33 clean runs at A0): **3/33 (9.1%)** -- wins SCXPJX97HL, VRJSL2X8B3,
YRTQBF328S. Two error halts excluded: run 11 (post-event map freeze,
recovered) and run 35 (game HUNG at floor 24 after ~3h / 35 runs at 3x:
process alive, not responding, working set 13.3 GB; abandon recovery has
no live server -> batch stopped on C5; killed + relaunched via the
steam_appid procedure, profile 1 verified). Composites are the best on
record: act reach 2.26 (1: 6, 2: 11, 3: 16 -- 82% cleared act 1, 48%
reached act 3), relics 12.3, elites 4.7/run of 164 offered. The wall is
now act 3: 3/16 arrivals converted; killers Queen 7, Test Subject 3,
Aeonglass 2, Mecha Knight elite 1 (act 2: Kaiser 3, KD 3, Insatiable 2,
Ovicopter x2 hallways; act 1: Matriarch 2, Fysh 1, Vantom 1, elites 2).
Act-3 bosses on the promoted keys, era: Queen 12/33 (36%), Aeonglass 12/22
(55%), Test Subject 6/22 (27%); batch 3 alone Queen 2/9 at 65-95 HP
entries -- piloting, not HP (owner steer: snapshot A/Bs, not batch tuning).

Pooled A0 on the promoted keys after three clean batches + the partial:
**29/181 (16.0%)**. The 9/40 was the high tail; the definitive reading is
settling around 16-17%, below the 20% graduation bar.

Batch 4 (b3sxi5cgj, code b432f16 = + Setup Strike temp-Strength parse fix)
launched as a fresh 40; its run 1 continues the hung run from floor 24.
Ops note: two long-session game failures now (09-03 connection reset,
09-29 hang at 13 GB) -- a relaunch every ~20 runs would be cheap insurance
(PLAN section 7).

## 2026-09-29a (Fable 5) -- repo public-ready (README, MIT, fork published); batch 3 launched; Kaiser Crab is the act-2 outlier

Owner interrupt: README for GitHub (21a1953), MIT license + Spirebird credit
(ad1839e), fork pointer (77f2654); main pushed (was 565 commits behind).
Public-exposure scan of tracked files + history: clean. The mod fork
(cicero225/STS2MCP) was already public but v107-fork was 2 commits behind
GitHub (abandon_run / save_and_quit) and v111-fork unpushed -- both pushed,
plus an "About this fork" branch table in its README on main/v107/v111.
Owner is holding the public flip until friends weigh in.

jorbs' video (Spire2Side Chat, "I Built a Slay the Spire Engine. It just won
its first run.") read in full from captions: from-scratch PPO net in a Rust
emulator, ~2M self-play runs, first win ever; win rate "a rounding error away
from zero", no human A0 rate stated, no ascension stated. Reshuffles RNG on
lookahead forks (no peeking) -- same stance as C3. Nothing overlapping in
method; he is explicit that LLM-based attempts are what he's reacting against.

Batches resumed (owner: "may as well"): the game was closed -> relaunched
(steam_appid procedure, profile 1 verified via doctor), batch 3 (b1gazilda,
code ad1839e = sleeper v4 + True Grit sequencing) continued the saved run 29
as run 1 (Test Subject loss), then Prisms elite, Kaiser Crab, Queen: 0/4.
CATALOG STALE (Distraction) flagged at launch -- rebuild at a boundary.

Act-2 boss tally over the A0 promoted-key era: **Kaiser Crab (Crusher/Rocket)
20/34 (59%)** vs Knowledge Demon 86%, Insatiable 81%. Four death tapes +
34-fight stats: mode=defend_deadline every time (a p25 Rocket kill by T4 is
never feasible for these decks), so the fight is the owner's fallback line
(block the T4 Laser, kill Rocket T5-7, grind Crusher). Wins enter at 71 HP
mean and kill Rocket by r4.6 with 37 HP left; losses enter at 58, 8/14 never
kill Rocket; entry < 50 HP = 0 wins / 4 losses. The pre-boss campfire prices
the boss from the POOLED survivor-only stat (combat_stats.json, built
2026-07-12 from 345 runs: boss p75 41 -> rest below ~45), while Kaiser's own
survivor p75 is ~46-53 and its death rate 41% -- the rule smiths at 46-57 HP
where the data says rest. Same shape for Waterfall (survivor p75 47-50).
Filed in PLAN section 7 as a candidate (per-boss observed loss with pooled
fallback, feeding both the rest rule and the map DP), NOT changed live: the
definitive A0 read comes first and the pre-boss rest lever already burned
one arm (v6) by costing upgrades.

Batch 3 through run 25: 3/24 clean + 1 wedge (run 11: post-event map freeze,
phase=to_run, recovered; 5 error halts in 364 September runs). Drought
checks extended: decision timing identical across the record batch and
batches 2-3 (median 0.23-0.25 s, same wait fractions) -> not GPU-contention
lag; no enemy or event seen in batches 2-3 that the record batch lacked ->
not a Timeline unlock. Pooled on the promoted keys: 29/180 (16.1%).
Sleeper v4 live: fight 1 (B1VNZGC6EJ) held r1 and woke r2 with a 34-dmg
burst (by design; lost on a 49-HP basic deck); fight 2 (738CVJRL8Y) woke
r1 with 25 dmg -- term diff: strength_gained=2 from Setup Strike. ROOT
CAUSE: textparse's 'Gain N Strength this turn' regex carried a literal
0x08 byte where  was meant (never matched since it was written), so
Setup Strike paid the permanent-Strength horizon credit. Fixed (next
commit), replay holds. Kaiser again x2 (runs 5, 23): both entered at
39-44 HP after correctly resting from 12-20 HP at floor 32 -- the damage
is taken upstream in act 2, not at the campfire.

## 2026-09-28i (Fable 5) -- batch 2 stopped at the run-28 boundary (owner's GPU): 3/28

Owner asked (21:4x) to defer batches: their model training and the game
were crowding the machine. Stopped at the end of run 28 (a WIN, H7FH6P2XWR);
run 29 had just embarked (floor-1 map, no decisions) -> save_and_quit via
the fork, game at the main menu with Continue available; no bot process
left (the remaining python processes are VS Code's and the owner's jobs).

Batch 2 partial (bx61vrvnv, code 7e51956, hash 463619673047, all 28 at A0):
**3/28 (10.7%)** -- wins JRHJNAL2SK, GKAJZ7Q0M3, H7FH6P2XWR (runs 22, 25,
28) after a 0/21 open. Act reach 1: 13, 2: 5, 3: 10. Killers: Matriarch 3,
Aeonglass 3, Waterfall 3, Kaiser Crab 3, Queen 2, Phrog 2, Terror Eel 2,
Kin/KD/TS/Prisms/Axebots 1. Act-1 deaths 13/28 (46%) vs the record batch's
35% -- 8 act-1 bosses + 5 early elites. Pooled A0 on the promoted keys:
26/148 (17.6%). Composites vs the record batch: act reach 1.93 vs ~2.05,
relics 9.6, elites 4.4/run of 107 offered. Next: batch 3 tomorrow carries
sleeper v4 + True Grit sequencing (Continue picks up run 29 first).

## 2026-09-28h (Fable 5) -- batch 2 opens 0/17; Matriarch poke-wakes root-caused (sleeper v4)

Batch 2 at A0 on the promoted config (bx61vrvnv, same code/hash as the 9/40
record) opened 0/17 -- all runs verified at ascension 0, so a cold streak
(~4% under a true 19%), not a regression. Killer tally: 5 act-3 bosses,
5 act-1 bosses (Lagavulin Matriarch x3), 2 act-2, 3 elites/hallways.

Act-1 boss tally over the A0 promoted-key era (138 fights): Matriarch 9/20
(45%) vs Waterfall 69%, Kin 70%, Fysh 73%, Beast 90%, Vantom 93%. Every
Matriarch fight scanned: 18/20 woke her by card and 9 of the 11 losses were
round-1/2 pokes of 1-9 HP (mode=setup_window the whole time -- the mode was
right, the sim's pricing was not). Offline replay of seed HEKRVZMGUV round 1
reproduced the logged plan exactly (90.8 vs 45.8 for holding); the term diff
found three leaks: (1) ANY hit into a sleeper counted as the wake, so the
Plating-soaked Headbutt+ pre-paid the -16 and the real waking Strike was
free; (2) the bar was flat regardless of how many free turns the wake
forfeited; (3) the post-wake follow-ups collected the +0.8 focus and +1.5
ramp premiums (19 raw damage read as ~52), which is what out-bid the Power.

Fix ce7359d (sleeper v4): wake = HP loss only; w_wake_sleeper per forfeited
turn (stacks-1; a hit on her last asleep turn is free -- both natural wakes
in the logs confirm she wakes after stack 1 regardless); a paid wake turn
earns plain damage credit on her. Replays: HEKRVZMGUV r1 -> Headbutt+ into
her block + Stone Armor+ (no wake); 9JE1UAYWXH r1 -> Battle Trance + a
blocked Strike instead of the Unrelenting wake. 646 tests, ruff clean.
Code-only; the running batch keeps the old sim (its Matriarch fights are
pre-fix) -- batch 3 carries it. Open for the owner: the -16/turn unit is
the flat sizing from 08-06; whether a ~25 round-1 burst should still clear
a 2-turn forfeit (it no longer does) is unreviewed.

Run 21 (0/21; seed NDW2DDX5LZ, Waterfall Giant): the eruption turn read
[Pommel Strike > True Grit > Defend] = 12 block vs 39 at 29 HP (lives at 2);
True Grit's "Exhaust 1 card at random" ate the Defend and the bot died 3
short. The sim only modeled the Thrash wording. Fix 928a820: True Grit /
Cinder eat the affordable card a one-step lookahead wants most next
(Thrash's pessimism), so the DFS sequences the needed card first -- replay
gives [Pommel Strike > Defend > True Grit]. 648 tests. Batch-2 checks so
far: all runs at A0; code diff vs the record batch inert (veto default off
both ways); no pool change (3 new cards = 0.4% of offers); composites
identical (act reach 2.06 vs 2.05, relics 10.3 vs 11.0, elites 4.7 vs 4.9)
-- the drought is boss closes. Pooled era at A0: 32/181 (17.7%).

Run 22 WIN (JRHJNAL2SK), run 23 Bygone Effigy at floor 6 on an 11-card
starter deck at 80/80 (Sleep -> Empower +10 Str -> 23/turn; 127 HP). Era
data point, A0 promoted keys, act-1 elites: floor<=8 AND deck<=12 = 3
deaths / 22 fights (14%, mean loss 30-74) vs 1/73 at floor<=8 with a
bigger deck and 4/172 later in act 1. Same shape the withdrawn deck floor
(arm v4/v5, overshot to 2/21) was aimed at; 3 deaths is not a tuning
basis (owner steer) -- logged, config untouched. Observed-mean pricing
(Effigy 17.7) cannot see deck strength; the boss/P(win) heads (PLAN 9)
are the intended fix.

## 2026-09-03d (Fable 5) -- Decimillipede decoded from the bestiary text: Reattach modeled

Arm v3 run 4 died to Decimillipede from a 74/80 entry after a 12-round grind:
the tape shows the same segment killed, revived at 25, killed again. The
mechanic was sitting in the bestiary status text all along ('Reattach: if
other segments are still alive, revives in 2 turns with 25 HP') and the
planner had no model; worse, the API drops dead segments from the enemy
list, so every 'one segment left' read as LETHAL and the kill fed the loop.
Decimillipede: 3 of the arm's first 7 elite deaths, 4/51 era deaths.

Fix 18347c6 (+78c2ad2 lint): EnemySim.reattach; a segment kill that leaves
any visible segment alive at plan end loses its w_kill, pays
w_reattach_futile_kill (6) and is charged the revive heal (25 - hp at the
kill) -- the one-turn planner now lowers every segment into range and takes
them together (or holds); _fight_plan skips sweep/focus on Reattach boards.
Replay of the run-4 turns: round 3 no longer Uppercuts the 15-HP segment
(Strike + Impervious instead). Decoded into data/enemy_notes.json. 622 tests.
Code-only, so it applies to every arm from the next launch; the running v3
batch keeps the old planner (its Decimillipede fights are pre-fix).

## 2026-09-28g (Fable 5) -- first A0 batch on the promoted config: 9/40, a new record

Live, ascension 0 (verified per run: base boss HP, no WARNING), promoted
config 463619673047 + committed-elite tail check (code e22cc74..7e51956):
**9 wins / 40 (22.5%)** -- best batch on record (prior 7/40 x2). Act-3 boss
9/17 (53%; era 25%), elites/run 3.0, relics 11.2, deaths: 25 boss (15 of
them act-1 -- reach act 2 only 65% vs 75-85%, the batch's soft spot), 3
elite, 3 normal. The v1 configuration at A0 now stands at 23/120 (19.2%)
over three clean batches vs the with-bug era's 9.6% and the fixed-code
live control's 15%. It opened 1/11 with seven act-1 boss deaths, then went
8/29 -- the streak was a streak. Batch 2 at A0 launched on the same code.

## 2026-09-28f (Fable 5) -- ROOT CAUSE: every batch since the branch switch ran at ascension 3..8

While chasing the elite deaths (Skulking Colony f8, an elite with 0 deaths
in 48 era fights), the enemy HPs gave it away: Terror Eel 150 not 140,
Colony 80, Effigy 132, Matriarch 233, Insatiable 341 -- ascension scaling.
The run metas confirm: all 70 promoted-config runs of 09-28 were at A3, A4,
A5, A6 (33 runs), A7 and A8. Mechanism: the character-select handler sent
set_ascension only when the requested level was truthy, so a requested A0
never overrode the picker's REMEMBERED level, which climbs after each win;
the picker sat at A3 after the 09-26 branch/profile shuffle and climbed
to A8 on the bot's own ascension wins. Fix e22cc74 (`is not None`) plus a
once-per-run WARNING in the batch output when the run's ascension differs
from the requested one; the relaunched batch logged "set ascension 8 -> 0"
and runs at A0.

Ledger correction: the promoted-config batches (3/38, 2/19, 0/12) are
ASCENSION runs -- 5 wins at A3-A8 with the A0-tuned policy, not comparable
to anything. There is no A0 sample of the promoted config yet; the v1
configuration at A0 stands at 15/90 (arm batches + the 09-11 replication,
with the 09-03 batch: 237a23779317 A0 = 15/90 incl. stubs). The committed-
elite tail check (bbcc810) was motivated by A3-A8 tapes; it is principled
and stays, but its expected effect at A0 is small. The pool-zero veto
redone on A0 rows only (563 fights): act 3 6/57 (11%) vs 0/51 -- real;
act 1 4/83 vs 4/191 and act 2 1/28 vs 5/153 -- noise. Knob made act-scoped
(elite_veto_pool_min_win_min_act, 0 = off); recommendation to the owner:
3. The deck-floor recommendation is withdrawn (it was ascension). The
Decimillipede / Terror Eel forensics today were correct play against
ascension-scaled bodies. Lesson banked: the loud guard.

## 2026-09-28e (Fable 5) -- batch 3 opens 0/10 with five elite deaths; the pool-zero veto (built, default off, owner's call)

Batch 3 (promoted config + tail check): 0/10, elite deaths Terror Eel f7,
Phrog f7, Decimillipede f28, Knights f44, Terror Eel f8 -- promoted config
5/65 over three batches vs the arm's 14/80 on identical keys, the gap all
elite deaths. Forensics: Decimillipede = a damage-vs-block valuation vs a
three-body 150-HP elite (no bug); the floor-7/8 Eel deaths = basics decks
(16 cards with two curses in the last) vs a 150-HP ramping Eel -- correct
play, unwinnable fight. A card-count floor does not catch a 16-card
starter, and the tally for a 13-card floor (5 deaths / 36 fights at <=12
cards) is at best marginal.

Better instrument found: under observed pricing the rollout gate still
runs and LOGS its verdict without enforcing it -- a natural experiment over
810 elite fights. Its extreme call (any pool member at 0.0 win for this
deck) marks 8% / 9% / 9% death strata (acts 1/2/3) vs 2% / 4% / 2%; all
four Eel deaths sit in it. A death costs ~15-35pp of win chance per act, a
forgone relic ~1pp: refusing the stratum is net positive in every act and
lifts the moment the deck can beat the pool's worst body. 9c5fdda ships
config.map.elite_veto_pool_min_win (default OFF) + test; recommendation to
the owner: turn it on (replaces the deck-floor recommendation). 642 tests.

## 2026-09-28d (Fable 5) -- the elite-death excess explained: committed lanes priced at the mean; tail check shipped

Batch 2 on the promoted config opened 2/18 with four more elite deaths
(Terror Eel f15, Phrog f7, Entomancer f24, Byrdonis f11 -- Byrdonis had 0
deaths in 71 era fights). Promoted batches: 11 elite deaths / 56 runs vs
6 / 80 in the arm batches, config byte-identical (every key diffed), and no
combat regression (normal-fight losses lower, elite losses per fight lower,
false lethals negligible). The split that explains it: FORCED elites
(single-option nodes, committed floors earlier) died 8/86 (9%) at a median
71% entry vs 2/128 (2%) at 79% in the arms; non-forced entries unchanged.
The Byrdonis tape: at f8 the DP priced elite -> treasure -> elite as
63 -> 41 -> 19 (mean loss 22 each) and took the lane; the first elite cost
52, the second was forced at 11 HP. bbcc810: an elite node is death-class
when hp - p75 loss (35) reaches the death floor at that node's projected
HP (config.map.elite_tail_stat, "" = off); the running projection and the
node pricing keep the mean, so first elites are priced as before and only
hurt-lane continuations are refused. 641 tests. Batch 2 will be boundary-
restarted on it -- batch 2 closed 2/19 (Aeonglass f48 last), orphan
abandoned, batch 3 launched on 53460fa (its runs stay on the ledger as
promoted-config runs without the check). Whether the arm batches simply drew fewer double-elite
maps is unknowable; the check is right regardless.

## 2026-09-28c (Fable 5) -- first live batch on the promoted config: 3/38 (+2 wedges); elite deaths the watch item

Live batch 1 on policy.toml 463619673047 (code 2ce8b36..b1d1e0b, i.e. the
replication code + Unmovable + Cloak Clasp): **3 wins / 38 clean runs
(7.9%)**, two wedges recovered by the fork abandon (a Blood Vial chest that
never registered as claimed -- the treasure-claim class; and a Dense
Vegetation event double-pick that travelled into the pending fight, fixed
same day, 39165a6). The observed-capability keys behaved as designed
(elites/run 3.92, relics 11.1) but SEVEN elite deaths (Decimillipede at a
forced-lane 20% entry, Entomancer x2, Soul Nexus, Infested Prism,
Gardeners, Effigy) vs 6 across the two v1 arm batches (80 runs), and the
act-3 boss went 3/14. Checked for a code regression: normal-fight HP loss
is LOWER than the replication (a1 8.3 vs 9.0, a2 13.0 vs 15.6), false
lethals negligible (4/649), the post-3fdba35 combat changes are relic-gated
(Unmovable, Cloak Clasp); entry HP at elites ran 0.75 median vs 0.82. Verdict:
variance until shown otherwise (7 vs the expected ~3 is p ~ 0.05). The v1
configuration now stands at 17/118 (14.4%) over three batches vs the era's
9.6%. Batch 2 launched on the same config with the Beat Down + event-hold
code (39165a6); fixed-code sample ~125 runs toward the 300-run retrain.

## 2026-09-28b (Fable 5) -- Stage-2 trainer landed; owner catch: Beat Down ignored the discard pile

Stage-2 pipeline (scripts/train_offer_model.py) built and proven on the
08-27+ era: offer-unit rows (every offered card, ITT framing), dense labels;
beat-boss head AUC 0.768, hp_delta_next3 corr 0.53, per-card model score
recovers the model-free ITT ranking (rank corr 0.90 over 79 cards); on the
87-run fixed-code era the same heads read 0.674 / 0.42 (14 cards) -- retrain
at ~300 runs per the approved plan. Datasets now carry code_head.

Owner catch (run 080713, Bygone Effigy at 14 HP): Beat Down ('Play 3 random
Attacks from your Discard Pile') parsed to no damage; the discard held
Strike+ 10 and Perfected Strike 20 -- lethal with margin -- and the bot
played Defend/Defend/Strike instead and took the hit. 4dd561c: credit the
pessimistic floor (N smallest attack damages in the visible discard);
RandomEnemy cards submitted targetless. 639 tests. The owner's framing was
right that deck-statistics plays are largely unmodeled; this one is exact
because the pile is visible, so it was cheap to do now.

Housekeeping: the auto-mode safety check was down for ~20 minutes mid-turn
(shell tools refused); investigated the Beat Down turn read-only meanwhile.
Catalog stale again (Caltrops, Heirloom Hammer, Skim) -- rebuilt.

## 2026-09-28 (Fable 5) -- batches resume on the promoted live config; Stage-2 drafting plan approved

Owner back on the main branch (v0.107.1, modded, profile 1) and launched
the game for us: live batch x40 on the promoted policy.toml
(463619673047). Owner asked whether the drafting model can be improved or
is data-bound. Answer (PLAN section 9, approved): the label is the binding
problem, not volume -- win is 10%/run, one card ~1-2pp, 47k draft rows are
~3.2k independent outcomes; the Stage-1 ΔV pick signal was inside model
noise and pick-confounded. Plan: retrain on the fixed-code era at ~300 runs;
dense-label (hp_delta_next3 / beat_act_boss) offer-unit pick model; shadow
re-ranker before it drafts; boss head as the act-3 capability estimate.

## 2026-09-26 (Fable 5) -- beta branch v0.111.0: mod fails to load; owner's "missing" profile is the modded save set

Owner switched Steam to the public-beta branch (v0.111.0, updated 12:08) to
play personally and found their profile missing. Disk + today's godot log:
(1) the game launched still in MODDED mode (Settings -> Mods consent is
persistent) and read modded/profile1..3 -- the bot's profiles -- so the
owner's unmodded profile1 never appeared; (2) the owner's profile IS on
disk: steam/<id>/profile1/saves/progress.save, 237,255 bytes, parses as
JSON, byte-identical (sha256 4a9cac50...) to the copies in every full
backup since 08-27 and to the Steam userdata copy; unchanged since 06-11
(the owner's own play since then was on the bot's profile). (3) STS2_MCP
fails to load on v0.111.0: TypeLoadException on
MegaCrit.Sts2.Core.Entities.Multiplayer.LobbyPlayer -- the fork must be
rebuilt against the new API before any batch (PLAN row). (4) The beta
wrote modded/profile.save with a 1970 mtime, which broke backup_saves.py's
zip (2136f4b clamps pre-1980 stamps); fresh full backup
backups/20260926-121445 taken and verified. Advice to owner: disable mods
in Settings and relaunch; nothing to restore unless that fails.

Owner: "that's all it is... I will go back off beta for our run testing...
the next time they patch for real it will break the mod, worth planning
for." Done while the beta assemblies were on disk: fork branch v111-fork
(local commit) reads StartRunLobby.MaxPlayers / LoadRunLobby.
ConnectedPlayerIds by reflection (the only 4 compile errors; multiplayer
formatting the bot never uses); builds clean against v0.111 (0 errors), DLL
kept in external/builds/. Not installed (main branch = v0.107 DLL). Swap
procedure in CLAUDE.md. Caveat: the v111 DLL bakes v0.111 lobby types into
IL, so it is per-version -- one branch per game version, not one DLL.
Owner confirmed: mods off, relaunch, profile back. Nothing restored.

## 2026-09-11f (Fable 5) -- owner GO: observed-capability pricing promoted to live; pause; Cloak Clasp fix

Owner: "Go ahead re: v1's four map keys... pause batches at the end of this
run." b92cc58 promotes elite_loss_source observed / elite_loss_stat mean /
elite_entry_min_hp_pct 0.5 / boss_loss_source observed into policy.toml
(live hash 463619673047); c347c35 retires the arm file (its hash
237a23779317 stays in the run logs). Six tests pinned the old rollout/DFS
mechanisms through the default config -- re-pinned explicitly via a
_rollout_router helper (f857249); the mechanisms remain, config-gated.
Lesson banked the hard way twice today: never chain pytest through a pipe
before a commit -- gate on the exit code.

Arm batch 3 stopped at the run-4 boundary (0/4: Test Subject, Matriarch,
Test Subject, Waterfall Giant), orphan abandoned, game closed, machine
clean. Batches down until the owner's word; the next launch is plain
'sts2bot play' on the promoted live config.

Owner relic check, Cloak Clasp (bb8a49a): the end-of-turn hand count ignored
in-plan draws (a Pommel Strike's two drawn cards earned no Clasp block) and
did not subtract chooser / whole-hand exhausts; factored into _hand_at_end,
shared by _score (Clasp, Screaming Flagon, retain credit) and the hp_loss
diagnostic, which had also been missing the Clasp/Orichalcum block. 637
tests.

Session ledger (09-10/11): live-fixed 6/40, v1 repl. 7/40 (+1/6 stub), arm
batch 3 0/4; promoted. Owner catches folded in today: Brand free-lethal,
Equilibrium retain, Cascade X + death wall, the shop bought-list (June bug),
Cloak Clasp.

## 2026-09-11e (Fable 5) -- live control on the fixed code: 6/40; the code fixes lift live too

Live control (policy.toml f0e54b35df1b, code 424cc60 = all planner fixes +
the shop fix) ran 40/40: **6 wins (15.0%)** vs the with-bug era 9.6%
(n=426). Shop buys/run 4.4 -> 6.2 (the shop fix), reach act 2 79% -> 85%;
elites/run 0.82 (the rollout gate, as before), relics/run 9.1, reach act 3
40%, act-3 boss 6/16. So the code fixes alone are worth roughly +5pp on
live, and the observed-capability arm sits above that:

| | era live | live (fixed code) | v1 arm x2 (fixed code) |
|---|---|---|---|
| wins | 9.6% (41/426) | 15.0% (6/40) | 17.5% (14/80) |
| elites / run | 1.18 | 0.82 | 3.60 |
| relics / run | 9.7 | 9.1 | 12.4 |
| reach act 3 | 38% | 40% | 48% |
| act-3 boss survival | 25% | 38% | 37% |

Arm vs live on the same code is 2.5pp at n=80/40 -- not resolvable by
these batches; the mechanism (3x the elites, +3 relics, +8pp reaching act
3, identical act-3 boss survival) is the argument. Recommendation to the
owner: promote v1's four [map] keys to policy.toml (elite_loss_source
observed / mean, elite_entry_min_hp_pct 0.5, boss_loss_source observed);
holding for their word since it is the live config. Meanwhile a third arm
batch (same v1 hash) is running to grow n; alternate with live after.

## 2026-09-11d (Fable 5) -- v1 REPLICATED: 7/40 on the fixed code; live control launched

The v1 replication (config bytes identical, hash 237a23779317; code 3fdba35
= all planner fixes + the shop fix) ran 40/40: **7 wins (17.5%)** -- the
same count as the 09-03 record batch. Two clean 40-run batches of the v1
configuration now stand at 14/80 (17.5%) vs the era live 41/426 (9.6%),
about 2.2 sigma. The shop fix shows up underneath: shop buys/run 5.0 ->
7.2, upgrades at act-3 entry 6.4 -> 7.5 (era 6.9), reach act 3 42% -> 52%
(21 act-3 boss arrivals, 7 wins = 33%). Elites/run 3.7, relics/run 12.4
(era 1.18 / 9.7). Deaths: 8 act-1 bosses, 8 act-2 bosses, 14 act-3 bosses,
3 elites (Prism, Entomancer, Phrog), 3 normals -- the wall is now the act-3
bosses, where the learned boss head (PLAN section 9) is the next lever.

Ledger of the calibration line: v1 7/40, v2 1/6, v3 3/19, v4 2/21, v5
0/15, v6 0/10, v1-replication 7/40 (plus a 1/6 pre-shop-fix stub). The
kept-only-with-evidence rule held: the two batches with v1's exact keys are
the two record batches; every tuned variant underperformed. The v1 config
is the arm to promote once the live control on the same code reads --
launched now (40 runs, policy.toml, hash f0e54b35df1b): if live also jumps
on the fixed planner + shop fix, the gain is the code; if not, it is the
observed-capability pricing. Both are wanted.

## 2026-09-11c (Fable 5) -- owner catch: 1170 gold walked out of the act-3 shop; a shop bug since June

Owner watching the replication's run 4: the act-3 shop before Aeonglass
left with 1170 gold and NOTHING bought (removal 100g, Bag of Preparation
160g at WAR +0.037, Stone Cracker, Royal Stamp, three potions with a free
belt slot, an on-sale Evil Eye). Replay on a fresh context bought the
removal first. Cause: screen_mem['shop_bought'] (the bought-THIS-shop index
list) was created once per run and never cleared -- since 5c9c59d
(2026-06-11), i.e. the ENTIRE record. Every index bought at an earlier shop
was invisible at every later one, and shop indices are stable by slot
(removal is always the last item, relics 7-9, potions 10-12), so: no run in
the era EVER bought a second removal (493 runs at exactly 1, 56 at 0, none
at 2+); shop #4+ visits averaged 1.27 buys vs 1.6 at shops 1-3, 31% left
with zero buys, 10% left with zero buys AND >=200 gold. Fix fab6f08: keyed
by floor like shop_card_buy; test. 637 tests.

Pre-fix replication stub closed 1/6 (a WIN on its last run, seed
E5U76PE2PE); relaunched on 3fdba35 with the fix for a clean 40.
This is the largest single bug found this month and it hits act 3 hardest
(the most gold, the most shops behind it). The replication batch is
boundary-restarted on it (5 runs in: 0/5), so its 40 carry the fix; the
live control follows on the same code. Note for the ledger: every prior
batch, live and arm, ran with it.

## 2026-09-11b (Fable 5) -- owner catch on the Test Subject death turn: Cascade X + the death wall

v6's last run died to Test Subject P3 at 17 HP vs 10x3 with Cascade+ (X)
and Bloodletting in hand at 1 energy: it played Cascade+ at X=0 (one pile
card) and never touched Bloodletting -- Bloodletting -> Cascade+ X=3 plays
four cards, a real shot at block. Two planner holes (e7e13fb): 'Play the top
X(+1) cards' parsed to a static 1 for any X (so energy never mattered),
now resolved at play position like X-cost hits; and under the projected-
death wall the 3-HP self cost still decided the tie against the only line
with variance -- self cost is now moot on death-walled lines (suicide veto
intact). A third: the DFS affordability check for Stomp-class costs still
skipped the seeding baseline (masked by the refused-play net); fixed. 636
tests. Code-only, next launch.

## 2026-09-11 (Fable 5) -- arm v6 0/10; the kept rest changes cost upgrades; v1 replicated byte-for-byte

Arm v6 (v1 keys + pre-elite campfire rest + boss safety 1.4) ran 0/10
across its two stubs; post-v1 arms 5/63 (8%) vs v1 7/40. A mechanism, not
just variance: v6 rested 7.3x/run vs v1's 4.3 (smith 4.0 vs 4.9) and
entered act 3 with 5.0 upgrades vs v1's 6.4 (era 6.9); act-3 boss wins
0/5 vs v1's 7/17. Both kept changes were justified on HP survival and both
convert campfires from upgrades to heals -- the act-3 wall is a damage
check, so the trade lands exactly where the wins are lost. Reverted:
f78014b restores v1's config BYTES (hash 237a23779317, verified), so this
batch is a straight replication of the record batch on the fixed planner
(Reattach, replan seeding, refused-play net, Mecha Knight mode, Unmovable,
free-lethal, retain-hand). Boundary-switched after v6 run 9; 40 runs
launched. If it holds near v1's level the rest rules stay out; a fresh
live x40 follows either way.

## 2026-09-10 (Fable 5) -- batches resume (arm v6 x40); owner catch: free lethal must beat a paid one

Owner: "carry on". Game self-launched, profile 1 verified, arm v6 launched
(40 runs, 440a99adf4b7, code 28aa3ea); a fresh live x40 follows it.

Owner catch from the first run (f21 r5, hallway, Exoskeleton at 1 HP): the
bot played Brand (lose 1 HP, +1 Str) into Tear Asunder+ for a 'lethal' when
a Strike killed for free. Strength gain was already zeroed on lethal ends;
the pull was the damage term crediting the bigger hit past the kill plus
the energy-waste term rewarding a 2-energy spend over a 1-energy one.
c331564: lethal turns credit damage net of overkill and charge no energy
waste, so among lethal lines the cheapest (HP, cards) wins. Test; 633
total. Code-only -- rides the next launch (the live control); the running
v6 batch is left intact (no churn inside a batch).

Second owner catch (Insatiable r1, same run): a 0-cost Equilibrium (gain
13 Block, Retain your Hand this turn) went unplayed with block already up
against a 6 -- and the Bloodletting it would have kept was discarded. The
planner had no notion of hand retention. 4dbfc7b: textparse retain_hand ->
SimState -> _score credits w_retain_card 2.0 per retained playable card
(statuses/curses nothing) on non-lethal turns. Test; 634 total. Also
code-only, rides the next launch.

## 2026-09-04d (Fable 5) -- boundary stop (owner needs the GPU); Unmovable modeled from an owner catch

Owner back: "end at the conclusion of the current run". Arm v6 stopped after
its first run (Test Subject f48; v6 0/1), orphan abandoned via the fork
API, game closed (bot-launched, bot-closed), no bot or game process left.
Batches down until the owner's word; next up when cleared: v6 x40, then a
fresh live x40 on the fixed code.

Owner catch while watching (Infested Prism T1 this run): Unmovable ('first
time you gain Block from a card each turn, double it') applies the turn it
is played, so it must precede the first block card -- the bot blocked
first. Nuance (owner): Defend -> Unmovable -> Defend gets NO bonus. The
planner had no model at all (only the preview note that a doubled Defend+
reads 26). f9a74d1: grants_unmovable + in-plan doubling of the first block
card after the power; any block card spends the doubling; previews read
doubled while the power is up and unspent, so a second block card in such a
plan is halved back, and a block played earlier in the turn (turn memory)
means single previews. Three tests, 632 total. Ruling recorded in
data/card_notes.json.

Session ledger (2026-09-03/04): live 0/3, arm v1 7/40 (record), v2 1/6,
v3 3/19, v4 2/21, v5 0/15, v6 0/1. Code this session: calibration hooks,
pre-elite campfire, per-act floors, deck floor, Reattach (Decimillipede),
replan play-kind seeding + Stomp fix, refused-play net, Mecha Knight mode,
Unmovable; data: catalog 479, move scripts re-harvested, enemy notes for
Decimillipede + Mecha Knight; a config-load test.

## 2026-09-04c (Fable 5) -- arm v5 0/14; over-tuning lesson; arm v6 = v1 + the two n>=40 changes

Arm v5 (deck floor 13, boss safety 1.4; then the Mecha Knight mode from run
12) ran 0/14 across its two stubs. Sub-arm ledger since the planner fixes:
v3 3/19, v4 2/21, v5 0/14 = **5/54 (9%)** vs v1's 7/40 (17.5%) and the era's
9.6%. Neither gap is significant (p ~ 0.2), but the process was wrong: the
per-act entry floors (v3) and both deck-size floors (v4/v5) were each set on
1-3 deaths -- exactly the batch-statistics trap the owner warned about
(snapshot A/Bs for small effects) -- and each one traded away act-1 elites
and relics, the very lever v1 showed. Two changes DO have n>=40 support and
stay: the pre-elite campfire rest (v2; the DP assumed a heal the campfire
skipped) and rest.boss_safety_factor 1.4 (pre-boss smiths survived 72% vs
87% after resting, n=40 each). Arm v6 (cad2cba, hash 440a99adf4b7) = v1's
four keys + those two; the four code fixes (Reattach, replan seeding,
refused-play net, Mecha Knight mode) ride along on every arm. Plan from
here: v6 x40, then a fresh LIVE x40 on the fixed code (the 426-run era
baseline predates the planner fixes), and no further config edits inside a
batch unless a run stalls.

## 2026-09-04b (Fable 5) -- Mecha Knight decoded from the tapes; fight-mode row (defend the BIG turns)

Arm v5 opened 0/10 with three act-3 elite deaths in nine runs (Mecha Knight
x2, Knights). Act-3 elite tally: era 4/28 deaths, arm v3+ 5/29 -- and Mecha
Knight alone 6/21 (29%), two arm entries BELOW the 70% floor (forced lanes
committed before the HP dropped). No bestiary mechanic beyond Artifact 2 /
Str 5, no note. Eight tapes read round by round agree exactly, and the
re-harvested move script (62 fights) confirms: a 3-cycle -- BIG attack on
T1/T4/T7 escalating 25 -> 40 -> 45, a 4-damage StatusCard poke on T2/T5/T8,
Defend+Buff setup on T3/T6/T9 (15 Block up on the next BIG). Every death
landed on a BIG turn with no block in hand after block was spent on the
poke rounds. Recorded in enemy_notes (0b09c17) and the script (cycle 3,
notes); 2861600 adds a FIGHT_MODE_TABLE row (kill_by_deadline, never
feasible at 300 HP -> defend_deadline cycle 3): the router marks T4/T7/T10
as defend turns and races the rest. 629 tests. Code-only -> restart the v5
batch on it at the next boundary.

Also today: first learned elite head (AUC 0.62) and the closed-form race
estimate ruled out (corr ~0) -- see 2026-09-04a. Session ledger: live 0/3,
v1 7/40, v2 1/6, v3 3/19, v4 2/21, v5 0/10 (pre-Mecha-row).

## 2026-09-04a (Fable 5) -- arm v4: 2/21; the deck floor overshot; arm v5 (deck 13, boss safety 1.4)

Arm v4 (da2a70ea8227, deck floor 14) ran 21 runs incl. the crash resume:
**2 wins**, 12/21 to an act boss, 6 act-1 boss deaths. Diagnosis by act-1
stats per arm (n=412/37/17/17): the 14-card floor cut act-1 elites from
1.8-1.9/run (v1/v3) to 1.06 and relics at the act-1 boss from 6.1-6.6 back
to the era's 4.9 -- it removed the v1 gain in act 1, not just the floor-7
starter-deck deaths. Second finding, across ALL arms (n=40 vs 40): pre-boss
SMITH (the observed-history rule: need 41 x 1.1 = 45 HP) entered act-1
bosses at ~74% HP and survived 72%, vs 87% after resting -- the history stat
excludes deaths and act-1 boss survivors lose a median 44-48, so p75 41 is
too thin. Arm v5 (10b3226 + a3ef133 config-load test; hash 8e8f36484961):
elite_min_deck_cards 13 (blocks only 10-12-card decks: 12 fights, 1 death)
and rest.boss_safety_factor 1.4 (rest below ~57/80 before an act-1 boss;
act 3 with the +15 bump rests below ~78). First v5 commit shipped a
duplicated [rest] key that broke tomllib -- fixed in place; every
config/*.toml now has a load test. Boundary-switched after v4 run 21.

Side results: estimate_fight (closed form) vs actual elite loss corr 0.18 /
0.10 / -0.02 by act -- no deck-quality signal either (calls Effigy a win in
97% of fights incl. all 17 blowouts). First learned elite head
(deck_features + elite id, logreg, run split): test AUC 0.62 on 799 fights,
top tercile 26% big-loss vs 12-14% -- the only estimator with any signal;
refit at ~1500 (PLAN row). Session ledger: live 0/3, v1 7/40, v2 1/6,
v3(pre-fix) 0/8, v3 3/19, v4 2/21.

## 2026-09-03h (Fable 5) -- game crash mid-run; self-relaunch + batch resume (unattended)

Arm v4 run 4 (f36, act 3) ended with 'connection forcibly closed' from the
mod server, then no game process and port 15526 refusing -- a game crash,
not an owner close (mid-fight reset, owner away). The batch halted on C5
(abandon needs a live server). Relaunched the game (steam_appid procedure,
Steam was up; menu in ~10s), verified profile 1, resumed the arm (36 runs).
The crashed run's log carries no outcome (dataset marks it outcome_valid
False). v4 so far: 1/3 clean (Aeonglass f48, WIN, Queen f48).

## 2026-09-03g (Fable 5) -- arm v3 on the fixed planner: 3/19; arm v4 adds a deck-size elite floor

Arm v3 (3e9110e8a915, code 98a5472: Reattach + replan seeding + Stomp fix +
refused-play net) ran 19 clean runs: **3 wins**, 14/19 reaching an act boss,
12/19 the act-3 boss (Test Subject x4, Queen x2, Aeonglass x2 among the
losses -- the act-3 wall is now the dominant killer, as it should be). No
stalls after the fix. Elite deaths: Gardeners f8 (13-card deck, 68%),
Terror Eel f7 (12 cards, 76%), Mecha Knight f45. Arm-wide act-1 elite
fights by deck size at entry: <=13 cards 3 deaths / 28, 14: 1 / 31, >=15:
0 / 66 -- every small-deck death at floors 7-8. That's the shape the rollout
gate used to catch by accident (0.0 win for starter decks) and the observed
pricing can't see. 7d67186 adds elite_min_deck_cards (0 = off; elite nodes
death-class below it); arm v4 (77d68d6, hash da2a70ea8227) sets 14 -- the
DP re-plans each floor, so it mostly defers the first elite by a floor or
two while the deck fills. Boundary-switched after v3 run 19, v4 launched.
Session ledger: live 0/3, v1 7/40, v2 1/6, v3(pre-fix) 0/8, v3(fixed) 3/19.

## 2026-09-03f (Fable 5) -- the seeding fix regressed Stomp-class costs; stall safety net

The relaunched v3 batch stalled on its FIRST run (151507, f4): Stomp 'costs
1 less per Attack played this turn' was shown at cost 1 after two attacks --
the game's displayed cost already carries the turn's plays -- and the newly
seeded attack count discounted it again to -1; the planner played it at 0
energy, the game refused, and the settle loop resubmitted it until the
60-tick stall rail (the fork-API abandon recovered the batch). Fix 3e5f0ac:
SimState.n_attacks_played0 (plan-start count); the per-attack discount and
Second Wind's remaining-attacks count use the plan's OWN attacks only.

Safety net b4abfac for the whole stall class: a play the game refuses through
the entire settle window is excluded from the turn's replans (screen_mem
refused_cards -> plan_combat_turn excluded_indices), so the bot plays
something else or ends the turn instead of looping. The old settle-cap pin
('re-send after the cap') was the loop; re-pinned. 625 tests. Batch to be
boundary-restarted on b4abfac after its run 2.

## 2026-09-03e (Fable 5) -- replans forgot the turn's plays: relic cadences re-seeded

Same Decimillipede fight, second bug. Round 5 was a REAL lethal: Break+ (30)
kills the 25-HP segment, then Strike + Dismantle = attacks 2 and 3 -> the
held Kusarigama's third-attack 6 finishes the 19-HP segment (6+8+6 = 20),
and with no segment alive the dead one never revives. After Break+ the
replan started from zero attacks played, saw 14 < 19, called it non-lethal
and blocked. Every mid-turn replan had this hole for every per-turn cadence
relic (Kusarigama, Shuriken, Kunai, Ornamental Fan, Letter Opener) and the
Smoggy skill cap. Fix 41fe501: the router's turn_plays memory now records
play KINDS; plan_combat_turn seeds n_attacks/skills/powers_played from it.
Test: same hand, LETHAL only when seeded. 623 tests.

Both planner fixes are code-only and apply from the next launch; the v3
batch (0/5 so far, pre-fix planner) gets boundary-restarted after run 6 so
the remaining runs carry code_head 41fe501.

## 2026-09-03c (Fable 5) -- arm v2 cut at 6 (1 win), arm v3 adds per-act elite entry floors

Arm v2 (218c180e300e, pre-elite campfire rule) ran 6 runs: 1 win, and the
rule fired as designed (run 4 rested at 69% ahead of Infested Prism and won
it). But two more in-elite deaths in those six -- Soul Nexus at a 95% entry
(deck strength, act 3) and Infested Prism entered at EXACTLY the 50% floor
(40/80) -- made the arm's elite-death tally 5 in 46 runs (11% of runs vs the
era's 5%), all in acts 2-3 at 50-69% entries except Nexus. Era p75 elite
loss is 38/43 in acts 2/3 vs 30 in act 1, so one floor for all acts was the
wrong shape. f0b159b adds elite_entry_min_hp_pct_act2/_act3 (0 = base, live
unchanged); arm v3 (cd67622, hash 3e9110e8a915) sets 0.65 / 0.70 with act 1
at 0.5. Boundary-stopped v2 after run 6 (orphan abandoned via the fork API),
v3 launched (40 runs). Sub-era ledger so far: v1 7/40, v2 1/6.

## 2026-09-03b (Fable 5) -- calibration arm v1: 7/40, a new record batch; arm v2 launched

Arm v1 (config 237a23779317, code_head 50ce814) ran 40/40 unattended:
**7 wins (17.5%)** vs the era live 41/426 (9.6%) -- best single batch on
record (prior 6/40), ~1.6 sigma on its own, with the secondary signals all
pointing the same way:

| | era live (426) | arm v1 (40) |
|---|---|---|
| wins | 9.6% | 17.5% |
| elites / run | 1.18 | 3.50 |
| relics / run | 9.7 | 12.4 |
| act-2 boss survival | 59% | 74% (17/23) |
| act-3 boss survival | 29% | 44% (7/16) |
| act-1 boss survival | 81% | 78% (29/37) |
| reach act 2 / act 3 | 79% / 38% | 72% / 42% |
| boss-entry HP (median frac) | 0.91 | 0.79 |
| pre-boss campfire: smith / rest (runs) | 91 / 403 | 25 / 25 |

The cost side: 3 in-elite deaths (Terror Eel f7 on a 12-card deck; Decimillipede
x2 at 57-69% entries -- 2/14 arm fights vs the era's 4/51) and 7 normal-fight
deaths (5 of them act-2 packs vs weak decks -- the era's second-biggest killer
at 12%; 2 in act 1 after an Effigy blowout (-51, -55) into a lane with no
campfire). Arm elite death rate 1.8% vs era 4.4% across 113 elite fights;
the arm's elite HP-loss distribution (24/35/42 median/p75/p90) matches the
era's (23/35/46), so the observed pricing holds under the wider selection.
Veto candidates re-tested (rollout<0.2 / ==0, closed-form estimate, deck
size): none separates deaths well enough to be worth the fights refused
(addendum in logs/reports/elite_calibration.md). No veto added.

Mid-batch fix (d525f86, own commit; arm v2 config 3b5a877 -> hash
218c180e300e): the map DP projects a HEAL at every campfire, but the campfire
policy smithed at 58-62% and walked into the elite the projection had priced
post-heal (run 26: smith at 62% -> Effigy -51 -> dead; era: 308 smith->elite
steps). The map now flags a campfire whose DP-best continuation is an elite
(screen_mem pre_elite); _rest_site rests there below
rest_before_elite_hp_pct (0.75 in the arm; 0 = off on live). 621 tests.
Arm v2 launched immediately (40 runs) -- the arm-vs-arm delta is the more
informative next sample; the live control has 426 era runs. Live 40 after.

## 2026-09-03 (Fable 5) -- post-break: the HQX8M7T6VN diff finds the elite gate is the lever; calibration arm launched

Owner: "go ahead and resume, and continue any work you might think worth
doing." Game self-launched (steam_appid procedure), live-arm batch started,
then the deferred full-run diff.

**The diff (logs/reports/fullrun_HQX8M7T6VN.md).** Path, not drafts: the
owner took the SAME act-1 lane as the bot through (5,9) Treasure and then the
Elite at (6,10) where the bot took the Monster -- and went on to fight SIX
elites (20 relics, 99 max HP, Feed, Pantograph, Regal Pillow, White Star
rares) where the bot fought zero (10 relics, 87 HP). Act-1 offers were
identical until the paths split (bot Headbutt vs owner Cinder; Colossus vs
Evil Eye); the bot never saw Juggernaut / Daughter / Offering at all.

**Why (exact map replay of the bot's decisions).** The elite gate's greedy
pool rollout priced the act-1 pool at a MEDIAN 75-of-80-HP loss, so every
elite node was death-class at every floor (f10 fork: Elite -195.9 vs Monster
19.1), and the DFS boss forecast read a full loss at every floor of every act
(bot then WON two of those bosses at 19 and 37 HP) -- desperation permanently
on, every pre-boss campfire a rest, route values -80 at the boss.

**Era calibration (logs/reports/elite_calibration.md, 423 runs since 08-27).**
500 real elite fights won 95.6%; fights the rollout rated <20% to win were won
88%; predicted loss 37.6 vs actual 23.5 with corr 0.18 (no rank signal);
deaths entered at median 63% HP vs survivors' 80%. Boss forecast: >=90%-max-HP
loss on 61-99% of pre-boss evaluations vs actual act-1/2 wins 59-86%. The
capability estimate the whole map/rest/desperation stack consumes carries no
information -- the "root lever" memory, now with numbers.

**Arm.** Config-gated hooks (ba2150a; 620 tests): elite_loss_source=observed
(combat_stats elite MEAN 22, gate bypassed, HP projection + 50% entry floor
govern), boss_loss_source=observed (rest gate / map DP / desperation on
history). config/experiment_calibrated_capability.toml = policy.toml + those
four keys (59f4401, hash 237a23779317; p75 pricing still refused the f10 fork,
hence mean). Replayed on the seed: takes the (6,10) elite 52.0 vs 40.0.
Live batch stopped at the run-3 boundary (0/3: Queen f48, WG f17, Test Subject
f48; orphan run 4 abandoned via the fork API), calibration arm launched
(40 runs, code_head 50ce814). Watch: elites/run (1.18 era), elite deaths
(~4.4% era), relics, pre-boss smith rate, boss-entry HP.

Also: datasets rebuilt (3,246 runs); era counterfactuals rerun
(offer_counterfactuals_era.md: Taunt +3.1 sigma, Dominate +3.3; Setup Strike
-2.0, Rupture -1.8 -- nothing actioned); Splash / Anointed / Calamity are NOT
in the compendium's discovered list yet (unlocked != discovered), so the
tag review waits until one is offered.

## 2026-08-31b (Fable 5) — full-run experiment: OWNER BEATS the bot's Aeonglass seed; break begins

Owner played seed HQX8M7T6VN blind, full run — the bot's same-day Aeonglass
loss (died f48, her at 111/512). **Owner WON, killing her ~r10 at ~53 HP.**
First run-level human-vs-bot datapoint; commentary banked verbatim in
logs/reports/fullrun_HQX8M7T6VN.md (random-rare Neow philosophy, Second
Wind as pure future-pick w/ honest contamination flag, the triple-price
doll buy for Daughter of the Wind anticipating White Star -> Juggernaut,
Juggernaut-over-Offering). Full diff DEFERRED to post-break (owner
credits). Run ticked the epoch: Splash / Anointed / Calamity unlocked —
NOT resetting (fixtures immune, seeds were due to die, new pool = new
content to learn); catalog+tags rebuilt (474 cards). Era ledger at break:
experiment 13/119 (10.9%), live 7/78+ (~9%) — the ~10% level held all
weekend vs the ~6-8% historical band. BREAK until owner allocation
returns.

## 2026-08-30/31 (Fable 5) — spot-catch day + RECORD BATCH; boundary stop

Owner spot-watching between sessions produced four more fixes (Duplicator
hail-mary gate + spec #19, Chemical X dead-dependency shop gate, Liquid
Memories into the cost-zero lane w/ discard-side targets + round-gate
removal + no-2-cost softening), and the potion-pass census bounded PLAN
item 7: 51 potions ever held, 40 laned, ELEVEN remain — one sitting.
Owner framing honored: 'stochastic sniping' pending the formal pass.

New-era alternating batches on the full fix set: experiment arm 39/3 then
**40/6 — the first 15% batch and best single batch on record** (prior
best 5/40); live arm 38/3 then **23/3 partial** (boundary stop, owner needs
machine). Cumulative new era: experiment 79 runs 9 wins (11.4%), live 61
runs 6 wins (9.8%) — BOTH arms running ~10-13% on the new code vs the
~6-8% historical band; the level-shift signal strengthens. Machine handed back
clean; resume alternation (live arm remainder first) on owner's word.

## 2026-08-29e (Fable 5) — phase 3: fixtures rerun on the new planner

**Fixture A** (owner-winnable fight): still a LOSS but 71 HP closer —
died r7 with the boss at 39/512 where the old planner had her at 110 at
the same round. The turn-level fixes bought most of the gap; the
remainder is the spec-tier beat-detonation (bank the belt, unload on a
defensible beat, kill on her passive turn) — exactly what won the owner
the fight and what a one-turn planner cannot express. Owner verdict:
'heartbreaking... I consider this an improvement' (their own self-A/B
loss on identical draws calibrates: losing lines exist with reasonable
play). **Fixture B**: loss r8, player 47, boss 177 (old: r8/151 at 27 HP;
owner r10/135) — traded damage for durability, outcome unchanged; the
under-the-line verdict on that deck STANDS across all four playings.
Fixture suite proven end-to-end as a regression instrument: restore ->
Continue -> paired diff, ~4 min per fight. Machine handed back.

## 2026-08-29d (Fable 5) — phase 2 complete: 13 fixes from the fixture commentary

The seed-A/B commentary queue implemented, each own commit + tape-mirroring
test, suite 613: hand-limit draw fizzle (#1), payoff-dry gate (#3),
dynamic X-cost (#4 — [Rampage>Whirlwind] was literally undiscoverable),
vuln-scaled artifact strip (#7), fix-the-hand reroll lane + hand_reroll
category (#9), cheap-draw opener widening (#10), hail-mary reroll-before-
draw (#12), Barricade mid-plan flag (#13), amortized Withering tax (#14),
play-from-pile EV for Havoc/Cascade (#16). Closed by investigation: #15
(MF>Taunt was a tie under Artifact — the real error was playing MF at all,
now gated by #3), #2 (emergent from #1), #8 (emergent from #7 + search).
BONUS BUGS the work flushed: Dominate's flat-Str double-count (phantom
unconditional Str explained its plan-leading everywhere), phantom minimum
X-hit (0-energy Whirlwind 'dealt 6'), energy-waste dock BRIBING null
spends (dead Forgotten Ritual played for +0.15 — veto landed, calibration
open as 17-CAL), Evil Eye+ evaporation (desperation-draw mid-plan energy
spend, #18 spec note). Spec tier (5, 6, 11, 18, beat-trigger) filed for
5-C. Owner tape-catch count this arc: 12+.

Phase 3 pending: rerun fixtures A+B on this planner (needs ~10 min of
game time) — old tape vs new bot, the direct discrepancy check.

## 2026-08-29c (Fable 5) — fixture session: the Aeonglass regression suite exists

Owner returned for experiments (no batches after). Built the permanent
fixture suite: seeded replays of A and B parked at their f48 fight starts
via handoff -> save+quit -> full backup. **Fixture A = backups/
20260829-154956** (91/91 double-Offering deck; prior: bot died r8, owner
won r6@46); **Fixture B = backups/20260829-161432** (137/137 Feed deck,
drift-checked exact; prior: bot r8/151, owner r10/135). Registry:
logs/reports/aeonglass_fixtures.md. Restore+Continue = byte-identical
fight for ANY future planner version — the discrepancy protocol for the
whole queue. Epoch management en route: owner's fixture-A self-replay
LOSS ticked the epoch (owner caught it on the bar); reverted to 063132
again before seed B; fixture backups are themselves epoch-safe.

**Owner self-A/B on fixture A** (natural experiment, identical draws):
replayed 'running my same judgments', deviated on potion timing (all 3
drunk by r3 vs held to r5 in the win) -> LOST r7. Healthier midgame (87
vs 72 at r4), empty belt at the detonation window, dead. Single-variable
validation of hold-for-the-window; queue item 9 upgraded.

**Seed-B commentary continues** -> items 13 (Barricade mid-plan flag,
mechanism grep-confirmed) and 14 (fractional Withering cost; tape:
Whirlwind played at 0 ENERGY, zero hits, no DotW, pure counter tick).
Queue at 14. Phase 2 (implementation) begins; phase 3 = rerun fixtures
on the new planner.

## 2026-08-29b (Fable 5) — batch-then-revert executed; arms still statistically silent

Owner headed out on option 1. Batches ran while away: live arm completed
its 40 (2 wins), experiment arm 25/40 more before the requested boundary
stop. Bot + game down clean; **profile REVERTED to backups/20260829-063132**
per the arrangement — epoch un-ticked, seeds valid for the owner's planned
follow-up experiments (interim batch progression discarded from the
profile only; all run data kept repo-side; pre-restore state banked).

Dataset rebuilt (3,013 runs, 0 parse errors). Arm-era Aeonglass split so
far: setup 7/10 deaths (70%%, mean hp -64.7) vs race 2/3 (67%%, -69.7) —
statistically nothing at these n; the paired-checkpoint evidence (setup
+21 HP on identical draws) remains the only real signal. Verdict stays
open; volume or more paired snapshots will decide. 12-item seed-A queue
awaits the owner's green light; cheap four ready to land as their own era.

## 2026-08-29 (Fable 5) — the seed-A commentary session: 12-item work queue from one fight

The richest analysis session on record. Morning: overnight batches (exp
arm 4/33, live arm 3+/14 incl. a f48 win), then owner-driven seeded
rewinds. Seed A (KP6FWVU2EL, 91/91 double-Offering deck): owner WON r6 at
46 HP where the setup-arm bot died r8 — first human-beats-bot Aeonglass
pair. Seed B (P6AF3J78BW, 137-HP Feed deck): owner died r10 boss 135/512
vs bot r8 boss 151 — near-identical, bot acquitted, deck under the line.
Epoch ticked by the seed-B death; REVERTED via the per-run profile
snapshot (04:54:15, one second post-seed-A) — epoch preserved, seeds
alive. Determinism diagnosed: bot pure (all decisions matched on
identical states); the TS +1-Setup-Strike case = game-side reward roll
(Whetstone vs 100g, mechanism open: custom-run flag or profile-history
pools); seed-A divergence = MY tooling twice (wrong dir, then hand-diff
transcription losing draw-replacing plays — owner caught it from energy
math; fight_tape v2 does full per-poll deltas).

Then per-turn owner commentary on the seed-A pair -> PLAN work queue,
12 items. Highlights: hand-limit draw fizzle CONFIRMED UNMODELED (bot
burned ~2 draws T1, reached Pact's End+ a turn late — the whole draw
divergence); payoff-as-stripper pattern caught in code (Dominate led r5
via strip credit + exhaust enablement — verified NOT a Str-vs-Artifact
bug); r7 hail-mary drank Swift then Bottled Potential in BELT-SLOT ORDER,
flushing 100%% of Swift's draws (reroll-before-draw rule); detonation
REFRAME — owner's r5 was adaptive ('awful turn -> fix the hand'), not
scheduled, so the encoding is a hand-quality-vs-incoming trigger, not a
beat script. Also: vuln-density-scaled artifact strip, cheap-draw-opens,
BT-vs-draw-potion brick, Molten-Fist hold-for-recycle. Fight-level
finding: beat-aligned detonation + triple-potion banking (owner) vs
even-spread damage into her block turns (bot).

Owner live-catch streak this arc: 7 (Thrash, Wither pair, TOI text
drift, Weak-vs-staged, Not-Yet waste, tape transcription).

## 2026-08-28e (Fable 5) — owner tape catches x3 fixed; batches stopped at boundary (owner request)

Owner narrowed their TS-fight watch to three optimality comments -- all
three confirmed on tape and fixed (8df0762, suite 604): (1) Touch of
Insanity TEXT DRIFT -- game reworded to "free to play this combat", the
costs-0 regex unmatched, the potion fell to the hail-mary-only bucket while
its deploy lane (already encoding the owner's wait-for-a-2-cost rule from
07-29) sat unreachable; regex widened. Same class as the Guiding Star cost
drift: patch wording silently unhooks text-matched machinery. (2) Debuff
potions now HELD vs staged Test Subject until the final-phase body (revive
wipes statuses; the card-side guard knew, the potion lane didn't -- Weak
Potion had gone out r1 at P1). (3) w_heal_waste -2.0/pt forgone: Not Yet
burned at 77/83 for 6 real HP; sized to out-vote the energy-surplus dock
which had treated the wasteful heal as virtuous energy use. Owner live-spot
hit rate today: 5/5 (Thrash, Wither pair, these three).

Boundary stop on owner request after run 7 of the resumed experiment batch
-- run 7 was the FIRST batch-mode setup-arm Aeonglass arrival (f48 loss,
752 decisions; arm tally 0/1, pre-fix code). Machine handed back clean.
Resume: finish the experiment batch remainder, then alternate.

## 2026-08-28d (Fable 5) — Test Subject rewind: bot ACQUITTED (owner: "I don't think this fight is winnable")

Owner-requested rewind of the batch's TS death (seed UGS6U3DPZF, f48, died
r11 at 2 HP vs boss 72/300 — a 72-HP miss). Seeded replay via manual seed
entry + `play --stop-at-floor 48` handoff (the designed act-boss A/B flow):
**perfect draft replication for 10+ checked drafts**, one divergence
somewhere late (+1 Setup Strike) -> different fight shuffle. Owner played
the handoff (recorded, bot+human halves one log) and lost EARLIER than the
bot, then two savescum retries (recorder segments in logs/manual/), then:
"Mea culpa: I don't think this fight is winnable... something about the
draw order may be different now with the different deck." Verdict: the
original suspicion resolved AGAINST itself; the bot's r11/2-HP loss reads
near-line-optimal; deck (an experiment-arm draft) was just under the line.
Rewind protocol now proven end-to-end: seed from meta -> manual seed entry
-> deterministic replay -> handoff -> savescum retries. Alternating-arm
batches resume.

## 2026-08-28c (Fable 5) — owner: extend the experiment; alternating-arm batches begin

Owner on the A/B: n=1 matters less than the snapshot being "truly a winning
deck -- useful for informing future drafting, but hard to A/B on"; the +21
HP is evidence but "we can afford to experiment a bit more (cost is low
since it comes in the middle of normal batches anyway)". Design:
**ALTERNATE configs per batch** -- odd batches config/experiment_aeonglass_
setup.toml (hash ed040c20, Aeonglass routed through the setup/burst
refinement), even batches live policy.toml (f0e54b35, race row), both on
current code; ~5 Aeonglass arrivals per batch per arm. Comparison metric:
Aeonglass fight survival + hp_delta by config arm (fights table splits on
config_hash natively). Batch 1 (experiment arm): bbiycuo2u. Checkpoint
backup 20260828-140336 retained. Mode-row decision stays open until the
arms accumulate.

## 2026-08-28b (Fable 5) — Aeonglass A/B COMPLETE: setup arm dominates on the paired fight

Full four-way on the parked f48 snapshot (same seed M61B9L0NPM both bot
arms -> identical draws, a clean PAIRED comparison; wither fixes active in
both): **owner (human): WIN** ("ignored the Wither effect and just played
everything -- deck good enough to block while delivering damage, favorable
before it scales; coordinated Bloodletting + draw to extend turns").
**Race arm: WIN, finished ~37 HP** (killed ~r6-7). **Setup arm: WIN,
finished ~58 HP** -- modes setup_turn r1-r5 then burst-flip to race
mid-r5; boss HP fell nearly as fast during "setup" (503->434->338->182->95
by r5) because the refinement banks VALUE, not passivity. Same kill speed,
**+21 HP conserved** vs the race arm on identical draws. The pre-fix live
trace (120/512 at r5, 63 HP) was also winning. Verdict shape: on a strong
deck everything wins, but the setup refinement's turn-shaping preserved a
fifth of the health bar for the rest of... (well, the run was over -- but
at KD or Insatiable that margin is lethal-relevant). The burst-flip fired
correctly. NOTE: savescum arms are DETERMINISTIC (saved RNG -> same
draws), so extra passes add nothing; one snapshot = one paired datapoint.
Mode-row decision (setup_burst: True on AEONGLASS) is the owner's; the
n=1 evidence + the KD/Queen precedent both point yes.

## 2026-08-28 (Fable 5) — Aeonglass session: decode, planner fixes, CHECKPOINT CAPTURED (paused)

Owner-attended session (remote yesterday, present today). Owner delivered the
FULL Aeonglass decode (banked in enemy_notes same-turn): Withering Presence =
Wither to hand per 6 cards played (live countdown in the power's amount);
Wither dmg 3+3X by tier; Increasing Intensity every 3rd turn = quadratic
scaling; Artifact 3 vs vuln-setup; efficiency premium. Their hypothesis
("planner doesn't understand Withers/6-card trigger") VERIFIED 3 ways:
current-tier drain was priced, but (a) 6-card trigger unmodeled -> NOW
modeled (live countdown ticks per planned play, w_wither_incurred x tier
charge, lethal exempt); (b) exhaust never cleared stranded penalties -> NOW
Stoke/SW purge all, TG+/Purity choosers eat worst-K (hp_loss diagnostic
mirrors). Also: Aeonglass draft rule v2 (exhaust_tool_bonus 3.0, Stoke/SW
named tech, block premium, power bump; NO vuln dock -- 194-fight evidence:
mass-exhaust 45% survival vs 18% none, vuln package FLAT 31/28/29). A/B arm
built: config setup_burst_experimental routes her through the KD/Queen
setup/burst refinement; arms toggle via `play --config
config/experiment_aeonglass_setup.toml` (arm hash ed040c20 vs live
f0e54b35). Suite 601.

**CHECKPOINT CAPTURED** (watcher fired r5, floor 48, run 20260828-135348):
and a twist -- the PRE-FIX bot was WINNING the fight (Aeonglass 120/512,
player 63/80; boss-hp trigger, not player-hp). Deck: vuln-ish midweight
(Uppercut+/Vicious+/Colossus/Aggression), TG+ only exhaust tool, Crimson
Mantle, 2x Bloodletting, Stampede+, 12 relics. Save PARKED (Continue
reloads fight start), backed up in backups/20260828-140336 -- indestructible.
Owner ran out of time before playing; session PAUSED. Resume protocol:
game up -> Continue -> owner hands-on (savescum via mid-fight save+quit =
free retry; concluded fight = restore from backup) -> race arm -> setup arm
(--config), restore between. All arms run post-fix code; the live trace is
the pre-fix control.

## 2026-08-27k (Fable 5) — owner live-spot: Thrash phantom follow-ups (confirmed on tape, fixed)

Owner (remote, watching the last Queen fight): did the planner know Thrash
exhausts an attack? TAPE CONFIRMED THE BUG, exactly as they described: r4,
hand [Flame Barrier, Impervious, Thrash, Strike], Torch Head at 22 HP with a
22 intent — plan read **[Thrash > Strike]** with Strike the ONLY other
attack, so the follow-up was guaranteed torched ('Exhaust a random Attack in
your Hand'); the minion lived and swung. Second instance same fight (r6,
[Thrash > Dismantle+ > Spite] with three attacks at risk). Fiend Fire
phantom family — Thrash's single-random-attack variant was unmodeled. Fix:
exhausts_random_attack flag + DFS drops the best-damage remaining attack
(house pessimism → attack-first orderings surface naturally; potions
survive; the growth rider stays uncredited, conservative). Regression test
mirrors the live turn (kill needs Strike-first at 14 HP). 596 tests.
Rollout-sim handling deferred (deck-level effect minor). Owner spotted this
from REMOTE, at 3x speed, without seeing the details — the live-spotting
streak continues.

## 2026-08-27j (Fable 5) — batches stopped at run boundary (owner request); machine handed back

Owner (remote): "end at the end of next run." Stop-watcher killed batch 2
(bksmtaou8, -5 Stampede table) after run 2/40 completed — an act-3 run dying
to Queen at f48 — then closed the game too (bot-launched, bot-cleaned). No
sts2bot or SlayTheSpire2 process; machine clean. Treatment era stands at 42
runs (batch 1: 4/40 + batch 2: 0/2). Batches down until owner's word;
relaunch = steam_appid procedure + `sts2bot play --runs 40 --profile 1
--speed 3.0`.

## 2026-08-27i (Fable 5) — treatment batch 1: 4/40; docks verified, Stampede dock deepened

Treatment batch 1 (bdnucgwn6, code_head 2c8e19f): 40/40, **4 wins** (control
1/40 — small n, right direction). Dock predictions checked on fresh data:
Sword Boomerang 12%→6% picked, Tremble 19%→8%, True Grit base 35%→17% with
TG+ HOLDING at 36% (4/11 — the asymmetry exactly as designed). EXCEPTION:
**Stampede picked 5/13 (38%, UP)** — rationale scores show the dock firing
(-3 present) but the Aug-21 __attacks bug-fix raised its needs-bonus stack
more than -3 subtracts (picks at scores 4.0-9.4); the dock undershot the
approved intent in attack-dense decks. Deepened -3 → **-5** same day
(c9a0b95; cuts the marginal picks, keeps extreme-synergy ones). Batch 2
launched on the -5 table (bksmtaou8). Lesson: docks calibrated against
historical pick rates inherit the drift of that history — verify on the
first fresh batch.

## 2026-08-27h (Fable 5) — control batch closes 1/40; treatment era begins, code_head live

Control batch bf8njhwwg (OLD tag table): 40/40 completed, 1 win. Final-
stretch act-1 boss deaths spread across four different bosses = deck
variance, not regression (ledger lesson applies). Treatment batch bdnucgwn6
launched on the new table (Stampede/SwordBoomerang/Tremble/TG docks + Havoc
unlocks); first run's meta.json stamps **code_head 2c8e19f** — segmentation
live. NOTE DISCOVERED IN PASSING: config_hash does NOT cover the tag table
(data file, not config weights) — today's dock changes would have been
invisible to era segmentation without code_head. Pre-registered predictions
for the treatment era: Stampede/SB pick rates collapse, Tremble picks
concentrate in payoff decks, base-TG picks drop with TG+ offers holding,
their per-pick ITT rows shrink toward zero. Rerun the counterfactual suite +
Bloodletting waste audit once the era accumulates.

## 2026-08-27g (Fable 5) — True Grit base-dock lands; upgrade-disparity scan across all cards

**TG dock approved + landed**: new flat_adj_base lane (unupgraded offer
only) — TRUE_GRIT -1.5; upgrade_unlocks credit + upgrade-gated
controlled_exhaust untouched. 595 tests.

**Upgrade-disparity scan** (owner's proposed experiment;
`scripts/upgrade_disparity.py`, late-era + full-era slices): 55 cards with
both-variant volume. KEY METHOD FINDING first: the upgraded-offer stratum is
systematically confounded — mechanically-impossible negatives (Expect a
Fight+ strictly better than base yet measuring -7.5pp worse) expose it;
median gap -1.6pp (mean -3.0). Judge against the MEDIAN, not zero, and
demand a mechanical step-change before believing a gap. Survivors of that
screen: **HAVOC** +2.9pp full-era / +5.3 late (sig ~2.4) vs the -1.6
background, and it IS a cost 1→0 step-change (the classic 'Havoc+ is
playable, Havoc is not') — the one genuine candidate for ADDING
upgrade_unlocks, unflagged today. DISMANTLE +4.1 (thin, no step-change —
just +2 dmg — treat as noise). Counter-finding: **INFERNAL_BLADE carries the
unlocks flag but measures at/below background in both slices** (-4.6/-8.7) —
flag-review candidate. TRUE_GRIT's +5.2 gap remains the strongest
(handled). No flag changes made — owner called that the riskier half;
candidates presented only. All sigs ≤2.5 over 55 comparisons: ranking
evidence, not verdicts; snapshot A/Bs or next-era data to settle.

## 2026-08-27f (Fable 5) — owner docks land (Stampede/Sword Boomerang/Tremble); True Grit broken out

**Owner approved docks** ("happy to dock Stampede and Sword Boomerang.
Community consensus (and my own opinion) on those cards is fairly
negative"): new flat_adj lane (FLAT_ADJ in builder → additive in
score_adjustment) — Stampede -3.0, Sword Boomerang -2.5. **Tremble rule**
(owner: "pretty bad, unless a deck needs vulnerable badly and the only vuln
card is Bash"): flat -2.0 + kept vulnerable_payoff bonus (nets ~0 in exactly
the Bash-only starved scenario) + ANTI vulnerable_source>=4 (weight-
calibrated: Bash 2.0/Bash+ 3.0 stays under; a second real applier trips).
Review-#3 bonus-only pin superseded + updated. 594 tests. Applies from the
NEXT batch (current one loaded old tags).

**True Grit upgrade breakout** (owner Q #2 — late-era slice): the badness
concentrates in the BASE card exactly as suspected — **TRUE_GRIT offers
-7.0pp/pick (n=1,315) vs TRUE_GRIT+ offers -1.8pp (n=317)**. Random exhaust
is the problem; targeted (upgraded) is near-neutral. And the "pick it, smith
it later" plan does NOT rescue the pick: 81% of held copies DO get upgraded
eventually, yet the base-card pick still measures -7pp — smith slots carry
opportunity cost. Weakly corroborating: TG-upgraded runs win 9.5% vs 8.8%
plain (confounded). No TG weight change made — owner to rule (candidates:
shrink base-TG's exhaust_enabler provide or add a small flat dock, keeping
the upgrade_unlocks credit).

## 2026-08-27e (Fable 5) — global legacy-drift check built (owner Q); verdicts survive; git HEAD now logged

Owner asked (remote chat): is there a global check for legacy drift like the
Bloodletting case? Answer: YES, and it needs no statistics — policies are
pure functions and states are fully logged, so `scripts/drift_check.py`
REPLAYS the era's draft states through TODAY'S StandardRouter and counts
disagreements. Results: era f0e54b35 spans **162 code vintages** (453
policy-relevant commits repo-wide); draft divergence declines monotonically
**38.3% (July w3) → 1.3% (this week)**, 17.8% overall (8,648 replayed,
0 errors). The flip table names the dominant driver: top flips are all
SKIP→pick on the __attacks/__cheap_attacks family (Setup Strike, Stampede,
Expect a Fight, Rage, Stomp, Cascade...) = the July consumed-but-never-
computed pseudo-tag bug (fixed 08-21) suppressing those picks for a month.

**Robustness rerun** (offer_counterfactuals --since 2026-08-08, the
low-divergence window): every negative verdict SURVIVES AND STRENGTHENS —
Stampede -16.2 → **-20.7pp**/pick (n=659), Sword Boomerang -13.2, Tremble
-12.9, Whirlwind -11.1, Rampage newly -10.9, Evil Eye -6.4, True Grit -6.0;
positives stable (Mangle +25.9, Cascade +23.0, Tear Asunder +18.9, Vicious
up to +12.5). Drift DILUTED the findings, not created them. Note for owner:
per the flip table today's bot picks Stampede MORE than the logged era did —
the -20.7 verdict is about current policy; Stampede + Sword Boomerang
(random-target class) are now the top draft-dock candidates on
current-code evidence.

**Infra fix**: `meta.json` now records `code_head` (git short HEAD at batch
launch) — future eras segment by code vintage exactly instead of via
timestamp archaeology. Landed mid-batch; applies from the NEXT batch.

## 2026-08-27d (Fable 5) — bot launches the game itself; batches resumed; Bloodletting play-audit closes

**FIRST BOT-INITIATED GAME LAUNCH** (owner remote, explicit permission).
Attempt 1 died at a Steamworks "No appID" popup (direct exe launch); fix =
one-time `steam_appid.txt` (2868840) in the game dir. Relaunch: RUNNING
MODDED, MCP server up, menu in 27s, UNDER A LOCKED SESSION, profile 1
active (doctor-verified; owner profiles untouched; full save backup taken
first). P0.8 open item resolved; the 08-07 "bot CANNOT relaunch" note
invalidated — crash-relaunch watchdog now buildable. Batch bf8njhwwg
launched: 40 runs, 3x, per-run snapshots. This is also the first
post-audit-era code batch — new config-era data for all counterfactual
tables.

**Bloodletting play-time audit** (audit_bloodletting.py; 1,403 holding runs,
12,918 plays): mean **28.8 HP per run** spent on the card; 14.9% of its
turns end with the bought energy fully unspent (3 HP for nothing) — and the
payoff-deck split (Rupture/Tear Asunder/Inferno) does NOT explain it (14.3%
clean-waste in payoff-free decks). 829/1,293 holding-run deaths died IN a
fight with spend; 423 fatal fights carried 6+ HP of it. 7% of plays below
25% HP. BUT: a synthetic pin test against CURRENT code passes both ways —
the planner refuses the pure-waste play (cheap-mult self term -2.4 wins)
and leads with BL when it funds a Bludgeon. Verdict: the era's waste is
legacy-code states + draw-variance (config hash held while code churned all
summer — era != code version, worth remembering when reading these tables),
not a live bug. Test pinned (test_bloodletting_not_played_into_wasted_
energy); rerun the audit on the fresh era once batches accumulate — if
waste% stays ~15% under current code, the next suspect is replan
evaporation (BL played early in a plan whose later spends fizzle).

## 2026-08-27c (Fable 5) — owner reviewed the ITT table; conditional pass ran same-session

**Owner rulings/vibes banked (no weight changes ordered)**: Evil Eye +
Colossus underperforming matches their long-held intuition ("expect them to
be good, they underperform"). Bloodletting negative = "legitimately
surprising and suspicious" — maybe drafted too early / without support.
Demon Form ~1% pick = fine (Spirebird prior awful; old +3-str-this-turn
parse bug since fixed; "+0.7 adequately rated, keep an eye on it"). WATCH
Pact's End (planner historically couldn't plan exhaust→Pact's End
deliberately). Brand low = maybe play difficulty. Inferno low plausible
(punishes slow boss closes). Ashen Strike underrated at -1.3 ("reveals
something about how it's being played"?). Rupture low = play difficulty.
True Grit "a bit low imo". Howl From Beyond "potentially validates my
overpick theory".

**Conditional counterfactuals** (`conditional_counterfactuals.py`, report in
logs/reports/): owner's #3 (act signal) = YES — engine/defensive picks decay
hard by act 3 (Evil Eye -23pp, Feel No Pain -23, Second Wind -38, Hemokinesis
-20/pick act-3) while cheap attacks flip positive late (Pommel +22, Thunderclap
+29 act-3): too late to assemble engines, direct damage closes. Owner's #2
(conditional value) standouts: **Howl From Beyond flips sign on support**
(+33/pick with Inflame or Burning Pact, +22 with Pommel; -22 with Dominate,
-27 with Bully; -9 baseline) — overpick theory refined to overpicked-into-
wrong-decks, and its DECLARED need (exhaust_enabler) does NOT discriminate
(-5 both arms) while companions do → need likely mis-specified.
Sword Boomerang worst in GOOD decks (-52/pick with Uppercut, -34 with True
Grit): random targeting clashes with aimed-vuln lines. True Grit -20 with
Burning Pact (engine redundancy/over-thin). Tremble worst with FNP (-38) /
Battle Trance (-25). Tear Asunder/Mangle robustly positive everywhere
(Mangle+Battle Trance +83/pick, n=102). Whirlwind and Rupture negative EVEN
with needs met → misplay suspicion, not draft context. **Bloodletting: flat
-2..-3pp across acts AND both needs met/unmet** — kills drafted-too-early;
suspicion moves to play-time HP-spend pricing (fights-level analysis of
Bloodletting plays = follow-up; acting combat records carry full state).
Tag-needs validation mixed: Brand's need discriminates (+5 met / -1 unmet),
Evil Eye/Howl/True Grit needs don't.

**ΔV rescue path banked**: score margins are logged → regression
discontinuity on near-tie drafts is feasible (2,773 era drafts < 0.5 margin,
5,295 < 1.0) = quasi-random policy coin-flips for local causal pick effects.
Plus R-learner on offer randomization, and short-horizon V targets. PLAN §9.

## 2026-08-27b (Fable 5) — stage 1: value heads shipped; ΔV pick signal honestly killed; Stampede indicted by data

Owner greenlit stage 1 (still no game/GPU — all offline). Three deliverables:

**Value heads** (`train_draft_value.py` → `data/models/draft_value_v1.json.gz`,
1.0 MB; dependency-free inference `sts2bot/learn/gbt.py`, lightgbm
parity-tested to 1e-9; lightgbm 4.7 = new `[learn]` extra, bot never imports
it): win head test AUC .684, boss head .757, both calibrated. First fit
memorized run identity (train .989/test .634) — effective n is ~2.2k RUNS not
60k rows; fixed with per-run row weights + by-run early stopping + hard
regularization. These are the learned capability estimates (§5-C successors).

**ΔV pick signal REJECTED**: V(deck+card)−V(deck) prefers Cinder/Thunderclap
over Impervious/Offering — observational confounding (race-y attack decks
correlate with winning in our own history), not causal pick value. 27% test
agreement with the bot ≈ random. Not wired; recorded so nobody re-treads it.

**Offer-set counterfactuals** (`offer_counterfactuals.py`) — the model-free
pick signal, offers quasi-random given act: **STAMPEDE is the worst pick of
the era, −16pp per-pick (n=1076)** — the data independently convicts the
owner's live-spotted Kaiser trap (era predates the dock fix). SWORD_BOOMERANG
second (−10pp, n=2847): same random-target class. EVIL_EYE −6pp at 57% bot
pick rate; BLOODLETTING/COLOSSUS mildly negative at BOTH row level and the
fixed-exposure run level → owner-review candidates. Top positives:
Tear Asunder +22pp/pick (σ≈6), Mangle, Aggression, Feed, Impervious. Trap
caught in-session: "offered-ever" run-level ITT was length-biased (deeper
runs see more offers — every staple looked run-winning); rebuilt on a
first-3-drafts exposure window. Rankings feed snapshot A/Bs, not automatic
weight edits. Side question for owner: bot picks DEMON_FORM at ~1% of offers
(tags fine — base-scorer power dock?).

## 2026-08-27 (Fable 5) — learning direction ratified; stage 0 dataset shipped

Owner opened the RL question (usage-constrained day, big-picture only): scope
grew past expectation; hand-tuning drafting weights = maintaining a value
function by hand. Agreed direction now in **PLAN §9**: fitted value functions
at the existing decision points, never end-to-end RL; cards as tag/textparse
FEATURES not IDs (the audit built the featurizer); nested-feedback handled by
config-era stratification + HP-delta/boss-entry labels + offer-set
counterfactuals. Win-head ruling (owner Q): P(win) is the shared value head
pick models are deltas over — keep it, plus the boss-conditional head as the
learned §5-C capability estimate. Consumer-GPU ceiling, CPU inference.

**Stage 0 shipped same session** (`scripts/build_run_dataset.py`, 3 tests,
suite 582): all 2803 logged runs -> logs/datasets/ tables with ZERO parse
errors — 40,066 drafts, 19,512 events, 28,811 rests, 34,383 fights, 2706
outcome-valid runs (151 wins, 5.6% lifetime; 6.6% in the long f0e54b35 era).
First-look report (`scripts/dataset_summary.py` ->
logs/reports/dataset_summary_stage0.md): recent-era boss lethality quantifies
the wall — **act-3 slate: Aeonglass 84% death, Queen 74%, Test Subject 65%,
Crusher+Rocket 60%** vs act-1/2 bosses at 18-38%; mean boss-fight HP delta
about -68 for Aeonglass/Queen — matches the Aeonglass dossier shape
(front-loaded bleed). Draft pick-rates pass the sniff test (Offering 98%,
Impervious 90%, Bloodletting 82% ... Havoc 0%) — reviewable substrate for the
owner's digest exercise. No batches (machine is the owner's; usual reason).

**Label-sanity baseline shipped too** (`sts2bot/learn/` featurizer + no-dep
logreg; `scripts/baseline_boss_head.py`; suite 588): P(survive act boss) from
boss-entry state, dominant era, 4007 examples, split by run. ctx (hp+boss)
AUC .755; boss-only .694, hp-only .645. Aggregate deck features add ~nothing
in a LINEAR model, but **within-boss** full beats hp-only 9/12 (Vantom
.67→.78, Ceremonial .68→.78, Kin .68→.74, Aeonglass .58→.63) and loses on
Crusher+Rocket (.76→.64) — per-boss deck interactions are real and a global
linear weight can't express them: the stage-1 GBT case, made from our own
data. Two findings for the owner: (1) Aeonglass has the LOWEST hp-only AUC
(.58) — entering healthy doesn't save you; "setup is essential" in
statistical form. (2) Weight signs are sane (hp_frac +, act -, relics +,
big_single_hit/aoe/engines +, deck bloat/strike-named -). Featurizer trap
caught en route: deck_tag_weights only computes pseudo-tags AND needs
type/cost on card objects — the learn shim now catalog-enriches and mirrors
_providers' real-tag rules (test pinned; echoes the July
consumed-but-never-computed bug class).

## 2026-08-03..07 (Fable 5, sessions 21-23) — wins 12->36; the audit engine; owner-spotting golden age

**WIN EXPLOSION**: 3 lifetime wins pre-week -> ~36 by 08-07. Best day 08-03/04
(9/121); first fully clean unattended nights (40/40 runs, zero intervention).
Aeonglass 5+ kills post-model, Queen 3-in-a-night (torch-first converting),
Test Subject repeatedly, Kaiser appearing in win ROUTES post-surround-parity.
Funnel at 08-03 morning: act-1 boss 62->71%, act-3 boss 7->15%. Standing
baseline lesson (the 'regression' that wasn't): compute from the full ledger,
never a remembered streak -- one night was spent exonerating desperation +
elite-pool retarget with toggle arms before the 1/91 truth surfaced.

**THE PREDICTION-AUDIT ENGINE (owner directive 'resolve forecast-vs-actual
discrepancies; prioritization yours')**: predict_audit hardened into the
edge-case factory. Frame fixes (HP channel measures from the LAST decision;
damage channel = dealt-so-far + remaining projection) took HP accuracy 84->94%
and killed two artifact buckets (STRENGTH n=106 = Bloodletting self-costs;
uniform damage-MORE = replan additions). REAL kills: Flutter 50% attack
reduction unparsed (FL#5, Thieving Hopper), Slow's cumulative DISPLAY seeded
as this-turn stacks (FL#6, Bygone Effigy; plays-this-turn now router-tracked),
Axebot Stock respawn = spawns_on_death (-25 bucket), Ashen Strike pile bonus
double-baked vs live preview (FL#4, phantom lethal at 2 HP with Stoke in
hand). False-lethal species now number 6, all with regression tests.

**OWNER LIVE-SPOTTING (hit rate ~100% this week)**: Fiend Fire phantom
follow-ups (DFS hand-exhaust never cleared the hand -- potion-minted Powers
torched as 7-dmg fodder), Forgotten Ritual dead-in-hand (exhausted-this-turn
now snapshot-seeded), phantom Battle Trance under live NO_DRAW, Stampede
retained-attack credit, sleeper model v3 (Matriarch: damage counts + waking
hit pays; three scoring bribes cut -- energy-waste, ramp-race, ramp-stall;
burst-wakes representable per owner nuance), boots double-jump (charge-aware
map lookahead), 3x-Foul reward key collision, star-cost off-class veto
(Prismatic Gem trap), Shockwave mass-debuff AoE, Dismantle vuln-double, Stomp
dynamic cost, ethereal x FNP, FNP mid-plan grant, Mummified Hand trigger.
Potion sweep: Regen/Demise/Duplicator/Fortifier/Heart of Iron/Lucky
Tonic/Mazaleth/Beetle Juice(intent-keyed)/Fruit Juice(out-of-combat) +
Entropic freshness (minted potions re-open deploy lanes). Shovel dig lane.

**INFRA**: settle-guard family complete (armed-state seeds: NO_DRAW, exhaust
pile, DUPLICATION status, plays-this-turn). FightEnemy-parity guard test =
the Matriarch-drain gap class extinct. Fuzz harness ready (--policy fuzz,
owner-designed off-policy experiment; savescum-pause rail; per-fight
deterministic RNG). Fork asks now 4 (UI-ref re-resolution, scene liveness,
abandon-to-menu, in-fight event labels -- KD Curse-of-Knowledge choices are
TEXTLESS via API; owner's choice table recorded for when labels land).
Game crashes x2 (WinError 10054, unattended-morning class) -- port watcher
auto-resumes trains on relaunch. 'Silent batch exits' solved: C5 wedge halts
with stdout discarded; all launches now capture output. 516 tests.

## 2026-08-02 (Fable 5, session 20) — Kaiser Crab freeze KILLED (settle guard v2); Queen A/B; epoch relics

**THE FREEZE IS OURS, AND IT'S FIXED.** Kaiser Crab f33 (373PFAE7EE) froze
deterministically 4x under bot pacing. Dissection: Pillage + Replay 1 killing
Rocket = multi-second resolution; the bot replanned per 0.15s poll and fired
plays + end-turn into the running animation (tape: 5 Defend sends, 3 in hand).
Owner hand-replayed the bot's EXACT sequence: no freeze — input pressure, not
game script. Guard v1 (release on first state change) RE-FROZE: the chain
mutates state every poll. v2 = QUIESCENCE (5260dbc, b9335e0): after any combat
action, send nothing until the signature is identical 3 consecutive polls.
Validation savescum: crossed the freeze beat, killed the crab r7, ran to the
act-3 Queen. Bonus: post-draw replans now see drawn cards (owner's 'reassess
after Pillage' for free). WG-knockdown (#3/#4) plausibly same class — next WG
in a batch is the test.

**QUEEN A/B (owner played 2x from a handoff replay; --stop-at-floor recorder)**:
torch death = PHASE FLIP — no resummon, her Buff/Defend(20 blk) mode ends, she
attacks (7x5..10x5 ramping with banked buffs). Torch-first is the strategy
(fast: every torch turn buffs BOTH bodies); Queen-first only for extreme burst.
Bot's real error = uncommitted fight plan (both rolls lose -> plan None -> DFS
flipped targets, split 203 dmg, killed neither). Encoded 5f8c64c: guarded-
leader phase model in rollout physics + commit-when-losing plans. EXONERATED
by the same dissection: the 'unplayed Defend' turns were correct ORICHALCUM
play (6 free block > 5 played); Bound keyword visible at turn start, existing
one-bound-play constraint already right (owner spec'd full mechanics).

**Elite-pool draft retarget landed (13247be, owner-approved)**: early-act picks
price vs up to 3 fresh elite-pool fights averaged; boss late-act; next-act at
boss floors. **New epoch** (seeds invalidated): Miniature Cannon, Tungsten Rod
(with the ==1-HP-cost Brand countersynergy veto), White Star encoded (5f8c64c).
476 tests. Handoff infra note: --stop-at-floor 48 + recorder taped the owner's
fights turn-by-turn into the run log — the A/B workflow is now one flag.

## 2026-07-31/08-01 (Fable 5, session 18) — WIN #10; owner converts the act-3 residual live; relic-seam marathon

**WIN #10 = AEONGLASS AGAIN (D86CSF7L7C)** — 2-for-2 since her model landed
(0-for-5 before). Batch train ran all night at ~1 win/30 with the estimate
layer now pre-calling every boss death by name (Test Subject stage-table gate
fixed after GLTQT0XBN7 exposed the variant-name guard, e8659eb). **Batch 61328
(the full relic-sweep stack) set BOTH depth records: act-reach 2.50, relics
11.1/run, five act-3 arrivals** — the §5-C signature, pending aggregate.

**Owner relic/potion marathon encoded** (each a live catch or query): Production
energy-chain unblock (ae8a5fe — the DFS candidate pool dropped EnergyCostTooHigh
cards, so NO generator chain was ever discoverable; likely a long-standing
engine-deck tax), Barricade 92.5 overdraft (clamp + next-act boss pricing,
2afcfbd), Thrash+Howl keeper-rule inversion (67a875d), Gambit death-rider save
+ Entropic refill (4a66e02), Pumpkin Candle Kindle lane — FIRED LIVE on its
first-ever sighting (2cb6662), Mummified Hand draft pull (db11a78), Fiddle
no-in-turn-draw at all four layers (6b1642e), Ice Cream proactive banking
(de714f3), Whispering Earring both halves (a221879), Barricade block-banking
pinned (f15978c), full-belt drink-to-claim (9983802), Man-Sized Holes
catalog-first, egg ordering + shop-card-lane gap filed, Regal Pillow/Pantograph
routing seams.

**ACT-3 A/B (E4ZW92AFP5, Aeonglass): owner WON from a worse position than the
bot's loss** (62/75 + 1 potion vs 62/91 + 3; HP loss 23 vs forecast 38). His
line: strip Artifact 3 with cheap debuffs r2-r3, THEN land Vulnerable (250 dmg
in r4), out-ramp Empower (Str 23 vs 7), block only the big singles. VERDICT:
the promising-act-3-death residual is a PLAY-QUALITY GAP — convertible.
Encoded same-session: w_artifact_strip (24ef300) — eaten debuffs price as a
down payment, unblocking the strip-then-nuke line the bot structurally refused.
461 tests. Standing: potion pass, fork session, act-3 attrition lane,
boon-pick deck-conditioning (Fiddle/Throwing Axe class).

## 2026-07-30 (Fable 5, session 17) — WIN #7; P1.7 live latency measured; Phrog phase 2 root-caused; P2b lands

**P1.7 MAIDEN BATCH (b0smoa0p0): 1/10 win** — HHB656AQ8P, act-3 f48. Third
consecutive batch with a win (4 in the last 34 runs vs 3 in the prior ~200).
Latency (owner asked for numbers): gate_ms median 19.3 — free; boss_ms n=139,
median 704ms, max 10.4s. 139 fresh computes across 10 runs = the (deck, boss,
BELT) cache key was busted by potion churn -> cache now keys deck+boss only
(4a55200). Elites 1.50 act-1 / 1.90 all — the act-3 elite pool is newly
reachable and 0-for-2 (KNIGHTS_ELITE f43; the filed Knights-mechanics pass is
now load-bearing). Foul-throw backoff STILL untested — no foul+shop overlap in
10 runs.

**Phrog phase 2 root-caused from the tape** (20260730-084448, 3rd Phrog death):
turns 1-4 target only the parasite, turn 5+ only wrigglers — the swarm spawns
AFTER the parasite dies. Concurrent modeling was optimistic twice over: the sim
shed wriggler dps by killing cheap bodies early, and the 5-way split priced the
parasite at 1/5th of the estimate. Worse: the split's input was the TABLE'S
parasite-only 6.7 dps. Fixes: dormant-wave mechanics in the sim (wave>0 bodies
untargetable/not attacking until the prior wave dies; kill-HP still counts) +
composition members now use their OWN realized dps (Wriggler 4.1/body, n=1028
rounds -> phase 2 = 16/turn, matching the tape's proj-loss-19 hail mary).
Repricing: starter@64HP p25 57 -> 31; a 45-HP entry now fails the floor.
(8e53a26, 7649ca2.) Also: a PASSING gate used to log nothing — map scores now
carry won_n/pool_n + weakest fight's win_rate/p25 (185b7a9).

**P2b LANDS** (1f69f96): the pre-boss rest gate asks the DFS boss estimate
first (warm from the map cache; computes fresh for known bosses), falling back
to aggregate history + hand-bumps only for unknown bosses. This is the direct
answer to the Matriarch cluster ('~45 needed' vs three deaths from 62-64 HP).

**Session-16 leftovers closed this morning**: dial verdict INNOCENT (0.55 ≈
0.60 on elites, no attributable deaths — decision with owner still open);
Matriarch = Soul Siphon drain spiral -> race lane via _EMPIRICAL_MOVES drain
table (6c7a4a2); Foul guard text-drift fix ('ALL players and enemies' never
matched EVERYONE — suicide at 6 HP) (2dae5cb); Tent forensic REVERSED — first
scan read the wrong run; the real Tent runs chain rest actions PERFECTLY
(smith->rest, rest->smith by HP need, rest->Lift), replay exercise cancelled.
Explosive-on-normal suspicion ACQUITTED (all AoE spends were elite/boss).

Batch bb1jkxvr1 (Matriarch race + Foul guard + cache fix live; Phrog/P2b land
mid-batch) running as of this entry.

**Evening close: WIN #9 = AEONGLASS, first try with her model live.** She went
0-for-5 on the day under the flat-512-HP model; the afternoon tape decode
(compounding Empower ramp 26->40 by r10, Artifact 3 opener, Withering Presence
= Wither-per-6-plays) shipped as ea27f77, and the first run to face her with it
won: 'DFS vs Aeonglass est loss 95' -> rested to 93 -> converted (Q2WSD191ZC,
20 relics, Eternal Feather riding its new routing seam). Queen forecast also
verified live ('est loss 85/105' vs yesterday's ~free-win pricing). Day: ~120
runs, wins #7/#8/#9 — all three from batches carrying the newest code. The
estimate layer is effectively CALIBRATED (every boss death pre-called with
per-boss numbers); remaining walls: (1) KD, 10 kills today, pure deck-power —
SS5-C v2's target; (2) act-2 attrition (12 normal deaths, all <=15 HP
arrivals) — death class #2; (3) fight execution = the multiturn program.
A/B dossier: Queen + Aeonglass resolved from tape; Kin (belt front-load) and
Matriarch (drain-race horizon) queued for the owner. **NIGHT SESSION — both A/Bs
PLAYED AND ENCODED:** Kin (owner won from 67/80 killing Followers-first with a
scaling deck — inverting his own June race — 'no one strategy'): shipped as
fight-open plan selection, round-1 rollout of both target orders (62a6261).
Matriarch (owner won in 5 rounds from 44/80: all potions in her SLEEP window,
zero block, 116-dmg r4): shipped as sleep_turns modeling end-to-end + solo
drain/clock bosses auto-'focus' (5b24248). Owner then played on to Test Subject
and DIED AT STAGE 3 — a top-25% human with a burst deck also fails the
survivability check, independently confirming the deck-composition thesis. His
tape corrected the stage model: every '#C__' variant is ONE entity full-healing
100/200/300 (600 kill-HP; stage 3 = Nemesis intangible-alternation), now an
observed _BOSS_STAGES table (0368354). Harvest rebuilt from both manual tapes.
Live-catch relic seams: Pantograph (4f2befd), Regal Pillow (15afc05), Royal
Stamp targets-restriction note (8add8a8); Man-Sized Holes + egg-ordering filed
earlier. EPOCH ADVANCED at day's end (Alchemize/Nostalgia/Scrawl unlocked,
owner screenshotted — same-day triage in card notes; all banked seeds stale). Batch-killer #4 confirmed
WG-knockdown by owner screenshot (2-for-2); server death is downstream of the
wedge; fork asks sharpened (heartbeat + knockdown decompile).

**Afternoon addendum (session 17 continued): WIN #8 + two owner fixes validated
live in ONE run.** 2FQE720FCE (batch bh1ytvbe1, act-3 f48) threw BOTH Foul
Potions at the merchant for +200g (backoff ladder v2's first organic test —
both `ok`) and converted at the final boss. Day's arc: bb1jkxvr1 0/10 (zero
elite deaths in 25 elite fights — elites effectively solved; 7/10 boss deaths
from healthy HP), bxhdqtdfi 0/10 (KD x3; P2b's first live read: 'DFS vs
Lagavulin Matriarch est loss 80' — correct doom forecast; gate-pass logging
immediately solved the Gardeners f7 case: won_n 4/6 pool gamble drew a 0.0-win
member), bnglkzkyk 0/10 but ACT-REACH RECORD 2.20 with FOUR f48 final-boss
deaths, bh1ytvbe1 1/10 (win #8). Wins in 3 of the last 4 batches.

**KD audit (5 corpses)**: every death was a correctly-forecast loss (rest gate
saw 44<62, 43<62, 59<88, 21<98, 63<88 and rested) — fights lasted only 5-8
turns; the failure is UPSTREAM deck power by f33. Fix: §5-C v2 (5bb14fd) —
draft deltas priced by ROLLOUT vs the real upcoming boss (CRN seeding, n=40,
exp_enemy_hp_left loss gradient) instead of the static estimator; the rollout
correctly punished the old cost-2-for-5-block test fixture as worse than a
Defend. Re-bake A/B: NULL (36%/+7.1 both ways over 121 fights — physics
already counted Str; choice-flips too rare to move aggregates; kept as free
correctness). Recurrence pool (f606551): seen elites leave the gate pool until
3 fought (owner rule, player-visible, C3-clean). Mutual-kill ruling encoded
(d206af1): drinker-in-blast potions filtered by TEXT everywhere (HITS_EVERYONE
single source; hail-mary already priced it). Owner live catches: Man-Sized
Holes goes catalog-first — Perfect Fit over the Normality trap (2333ce7);
Eternal Feather entry heal rides the route projection (54a5141). Phrog f15
death post-fix: forced elite row at low HP, best path value -16.3 — the DP
knew; tail loss, not a model miss.

## 2026-07-29/30 (Fable 5, session 16) — WINS #5 AND #6 in one batch; P1.7 built; the live-watch harvest continues

**FIRST MULTI-WIN BATCH: 2/14** (byw7ikj6w, overnight, the accidental 0.55-dial
experiment) — Queen (YGHJ50QFHQ) and Test Subject (8CD49Y69TF, the 3-stage
anti-AoE boss) back-to-back. Counterweight: 8 of 14 died at the ACT-1 boss
(Matriarch x3 cluster) + 1 Phrog Parasite elite death (the swarm blind-spot
class). Dial verdict (0.55 vs 0.60) PENDING the deep scan — win ceiling up,
act-1 floor rougher; could be dial cost or one bad-variance night.

**P1.7 BUILT + BACKTESTED (commits pending a shell-tool outage — Sonnet
classifier down, owner opted to wait)**: rollout core refactored to ONE physics
(_RolloutSim) with TWO turn policies; DFS-policy (the real planner via
synthesized CombatStates) backtests boss-act1 at 52% predicted vs greedy 38%
(actual 65%), bias +7; median ~1.1s/estimate -> wired for KNOWN bosses with a
per-(deck,boss,belt) cache and boss_ms timing logs. Also staged: Juzu +2 on
'?' (no combat penalty existed to remove — verified), emergency Stoke shred
in the desperation lane (owner live catch: reroll a doomed hand, energy-first,
works under NO_DRAW), History Course filed as SS5.2 item 13, ?-hides-a-shop
foul-throw corner filed.

**Live-watch harvest**: Thorns potion = LIQUID BRONZE (name-keyword never
matched — text-matching now; same lesson as Touch of Insanity and Soldier's
Stew, both also encoded); Orobic Acid + card-gen deploys extended to elites;
Swift out-of-cards lane; Battle Trance NO_DRAW locks draws at all three layers;
Explosive AoE held for the swarms ahead (found the DFS pseudo-card spend path);
Shuriken/Kunai confirmed already covered by the trigger table. **Miniature Tent:
the bot does NOT chain rest actions** (one action then proceed at all 7 sites of
the win run) — payload forensic + Tent replay exercise queued (win seeds valid,
no epoch trigger). Mid-batch: a REAL game freeze at the WG knockdown (instance
#3 of the batch-killer class, cards frozen mid-resolution, state reports
healthy) cost a batch restart; stall leash tripled for phase-shaped waits.

'''PENDING NEXT SESSION''': commit the 5-item backlog + tests; batch deep scan
(dial verdict, Matriarch cluster); Tent payload forensic; P2b rest-handler onto
DFS boss estimates.

## 2026-07-29 (Fable 5, session 15) — the aggression era arrives; owner nuance harvest x7

**Batch b4xypb8pc (throw fix + Thorns + new epoch): 0/10, act-reach 1.9 — but the
profile has changed shape.** Act-1 elites 1.40/run, ALL-acts 1.90/run with the
FIRST act-2/3 elite fights in project history (calibrated dps opened them);
relics@f17 mean 6.0 (owner benchmark 7 in sight). TWO elite deaths (Bygone Effigy
f7; Mecha Knight f46 = the first act-3 elite ever attempted) — ~10.5% of elite
fights vs the backtest's 3-8% promise: WATCH, one more batch before touching
thresholds. Two more WG deaths: NOT fix failures (JE48MB r12: planner projected
death correctly, hand was two Strikes — arrived at the blast with nothing). The
human counter is "knock it down when you're ready to block" = delay-the-knockdown,
filed as the WG case in the forward-model spec. No organic foul-throw or Thorns
test arose; Insatiable x2 persists (boss-model work).

**Owner nuance harvest (all encoded same-session):** Planisphere +5/? and Meal
Ticket +15/shop ride a NEW relic seam in the map HP projection; Winged Boots
charges = insurance (off-path jumps pay 12 — the desperate rest-jump emerges from
death-floor math; live: 2 of 3 charges had been burned on marginal jumps); Sword
of Stone docked 5.5->3.8 + completion nudge (+8 on winnable elites at counter 4/5);
Touch of Insanity cost-zero deploy (TEXT-matched — the potion has never appeared
in logs; waits for a cost>=2 target in hand per the owner nuance); Tinker Time /
Mad Science full catalog with the owner's Power > Skill > Attack sort + a NEW
catalog-first-event mechanism (Spirebird confidently prefers Skill 14.0 vs 13.8 —
owner overrides) + text-detected smith premium for the Curious/Expertise variants.
THE POTION PASS elevated to a named PLAN item (relic pass done, potions never);
owner's potion value-ordering exercise banked as its centerpiece.

## 2026-07-25d (Fable 5, session 14 close) — the Foul-throw saga: our own polling was the culprit; epoch advance invalidates all seeds

**Owner potion catches off the win-run summary**: Thorns never deployed (categorized
'other' — now buff-class, boss-start deploy) and two unsellable Fouls banked. The
Foul thread went four layers deep: (1) forensics proved the run REACHED the f44
merchant and the shop-throw errored twice; (2) mod source showed the game's own
PassesCustomUsabilityCheck rejecting it; (3) a live probe A/B (owner savescum loop
on the win seed) tried the throw at four moments — all errored — while the owner
watched the bot click STRAIGHT PAST the shopkeeper screen; (4) a ZERO-POLL blind
throw landed both Fouls (+200g, merchant dialogue, owner-verified). Verdict: the
mod's /state read re-renders and auto-advances the shopkeeper screen — OUR POLLING
destroYED the throw window. Fixed in the orchestrator (9bc8c89): throws fire blind
between the accepted Shop travel and the next poll; Foul economy un-suspended.

**The /state re-render side effect now owns THREE bugs** (combat flicker, phantom
map decisions, the throw window) — passive reads promoted to the mod fork's top
item, ahead of map-node modifiers (Fur Coat) and the Pael's Wing sacrifice action.

**Also this session**: Prolong carryover (parsed to all-zeros — the 'Next turn'
clause is what the conditional strip removes), full-belt potion prior validated
live (Binding at fight start; owner initially read it as a Foul — lookalikes),
Pael's Wing docked to 2.5 (sacrifice not exposed by the mod).

**EPOCH ADVANCE (unavoidable, post-abandon): ALL PRIOR SEEDS INVALID** — the A/B
library (KJEZJQN609, LKG20K3FBE, DELDJQX3BP, TZSM9SV0P0...) no longer replays; new
content may appear in future runs (triage lanes ready). Queue: potion/relic terms
for the boss model, gate re-tightening watch, next batch validates the throw fix +
Thorns deploy organically.

## 2026-07-25c (Fable 5, session 13 close) — WIN #4; the calibrated gate's first batch is the strongest in project history

**Batch bwlg87wsp (calibrated realized-dps gate + 7 fixes), fresh 9: 1 WIN
(KJEZJQN609 — beat a 509-HP Aeonglass at 84 HP), act-reach 2.0 (record), THREE
act-3 arrivals.** Act-1 elites 1.22/run (era was 0.2-0.4); relics@f17 mean 5.5
with runs at 7 and 8 — the owner's benchmark of 7 finally in reach. 44 potion
actions (full-belt prior live). The win run also took a Waterfall Giant blast at
38 HP and LIVED — first save by the eruption block-stack (the other WG death
entered the blast at 1 HP: already dead walking, as the fix's caveat predicted).

**One elite death** (Phantasmal Gardeners f9) — and it's the KNOWN swarm-pollution
blind spot (harvests as one small body), not general recklessness: the calibrated
gate's false-positive promise (3-8%) held. Queen reached at f48, not beaten;
Kaiser/KD/Matriarch still take boss kills — consistent with calibration's residual:
boss fights need potion/relic terms in the model.

**Owner live-catches while the batch ran**: Prolong parsed to all-zeros (the
"Next turn..." clause is what the conditional strip removes — carryover priced,
790566a); Pael's Wing sacrifice is a MOD gap (payload has only can_skip — fork ask
#3; boon docked to 2.5); Fur Coat room marks not serialized (fork ask #2);
Slippery Bridge multi-stage gamble confirmed live. Normality flicker re-audited:
1 benign reject in 77 act-3 submissions — poll-driven re-render illusion, filed
for livewatch prep (mod-side passive /state = fork ask #1, fixes three quirks).

## 2026-07-25b (Fable 5, session 13 addendum) — Ovicopter A/B: the bot lost to a rule the owner stated before touching a card

**Narrated fight #2 (DELDJQX3BP f24, Ovicopter + 3 Hatchlings, both from 19/80)**:
bot died r3; owner won r2 with ZERO potions spent. The decisive divergence is the
cleanest yet: at r2 the bot held nearly the owner's exact hand and played Fight
Me!+ into a non-lethal — missed the kill by 9 WITH a Flex potion in the belt, ate
the str-buffed intent, died to the hatched swarm. The owner, same position: "if I
play Fight Me!+ I MUST kill this turn... either I have lethal or I don't", did the
exact arithmetic, killed pre-hatch (fight simply ended), held both budgeted potions
when the math cleared without them.

**Encoded same hour (4b4b4ee)**: enemy_strength riders parsed + simmed (the buffed
survivor's incoming rises; killing it erases the rider — kill-or-pay made literal);
strength potions join the lethal search as pseudo-cards; full belt raises the potion
spend prior (owner: "3 of 3, so my prior for playing one is higher"; the overflowing
Explosive Ampule proved it). PLAN 5.2 gains items 8-12 (fight-level intent,
route-informed risk budget, exact arithmetic at binary stakes, draw-pile stacking as
tutor value, archetype-conditional potion value). Withholding the bot's line until
the debrief kept the minion-targeting read unbiased this time.

## 2026-07-25 (Fable 5, session 13) — audits closed, the narrated-fight exercise, and the estimator's indictment by calibration

**Morning audits (owner away)**: negative path values = NO DP bug (-58.7 = rest +
0.8 x death-priced elite pocket; the SS5-C gate had rated the owner's 15-card Stoke
deck 0/6 vs the act-1 pool — deck_output sees 9.6 sustained dmg in an engine deck).
Phantom map decisions = post-travel transient re-render, FIXED with a travel-hold
(8ae71ce). WG rule 0-for-4 explained: the DeathBlow-telegraph assumption is false —
the invincible phase exposes intent null/statuses null; sentinel HP now assumes 50
blockable incoming so the planner block-stacks (381f564; the pre-fix batch promptly
lost two more runs to WG).

**The owner's exercise — narrated fight A/B (LKG20K3FBE f21, WEAK Exoskeletons)**:
bot died r4 from 47 HP; owner won at 3/80, narrating every turn. Root-caused the
death to three separable causes: (1) curse-roulette acquisition — 'select worst'
TRANSFORMED Writhe at f3 and rolled Bad Luck (Eternal, 13 HP/turn-in-hand);
owner-confirmed mechanic: curse transforms reroll IN THE CURSE POOL → transform
never targets a curse now (0059317); (2) cap-blind kill sequencing (Hard to Kill
9/hit — forward-model material); (3) the Bad Luck bleed itself — verified already
priced correctly by the hand-curse lane. Also encoded: curses count 2x in
controlled_exhaust (True Grit as Eternal-curse exorcism, 31c87a1; retain/ethereal
excluded, 9e17bc1), recorder survives game-close (aa9044b), minimal-lethal verified
already correct. Neow reprice validated same day: 10 runs, 10 DIFFERENT Neow picks.

**PLAN 5.2 written** — seven forward-model requirements straight from the owner's
narration (draw-pile forecasting, deck-state clocks, cap-aware sequencing,
anticipatory focus-fire, cross-fight potion economy, conditional card economics)
plus the verified-already-correct list.

**The calibration baseline (scripts/calibrate_capability.py, n=292)**: estimate_fight
is uniformly pessimistic, NEVER optimistic — predicted 0% act-1 boss wins vs 55%
actual, 55% act-1 elite wins vs 97% actual, HP-loss bias +8..+24, false positives
~0%. Every gate threshold tuned in July was compensating for this scale. The forward
model's acceptance test: beat this table.

## 2026-07-24 (Fable 5, session 12) — Elite retune validated; the tactical A/B instrument ships and pays for itself the same night

**Elite gate retune** (owner-blessed, a577e98): end-HP floor 0.30→0.20, pool frac
0.50→0.40, elite_relic_value 36→42. Validation batch: act-1 elites 0.13→0.40/run,
ZERO elite deaths, relics@f17 4.2→4.9, act-reach 1.9. Third loosening of this gate,
each earned by evidence. Act-2/3 elites still zero — corpus forensics say near-lethal
at current fight skill (44→9, 38→dead, 53→dead), so the refusal is honest; owner
reframe: act-2 elites are the HARDEST per deck power (shirking is most reasonable
there), the real aggression gap is Act 3. Do NOT weight-tune act-2/3 open.

**stop_at_floor becomes the tactical A/B instrument** (de7d7f0 + c4e034f): 1x reset
at handoff, passive follow records the human half into the SAME decisions.jsonl,
enrich retries the .run race, --stop-at-map hands off at the map screen. Three modes
validated live in one evening:
- **Fight A/B (X9VM7AR5PF)**: replay determinism HELD (identical route, same 76 HP at
  the door). Bot beat Soul Fysh r14/-48; owner r21/-63 on the same deck — "the deck
  was just not very good"; piloting had nothing to grip.
- **Draft A/B (same seed, owner drafts)**: 19-card engine deck (Neow Stoke → shred
  basics), 3 elites, SF in 9 rounds from 61 entry. Engine-coherence in drafting is
  what separates the owner's Act 1, not fight micro.
- **Act-2 handoff (random seed)**: owner took the f18 map with the bot's deck, gave a
  live route-planning monologue (backward planning from act anchors, DEFERRED choice
  points, conditional fallback lines — now the optionality spec in PLAN), downgraded
  his 2-elite ambition on early-fight evidence, paid **12 HP for Infested Prism**
  (bot corpus: near-lethal) and beat Insatiable 80→50. The act-2 elite piloting gap,
  quantified: ~2-4x.

**shadow_compare.py ships** (owner proposal, f478f28): replays recorded states
through the live router offline, diffs every decision screen. Two review rounds
same night → 5 commits: Stoke shred value scaled by basics ×2.0 (4f96468, "I'm
underestimating Stoke, especially early"); Colossus vuln bar 2→4 + hand_dump
anti (SW×Stoke) + Bloodletting fed by dumpers (22d110a); **deficit feeding** — the
reverse tag edge, candidate feeds cards the deck is starving for, external-supply
only, threshold+1 redundancy target (5baeb39, from the owner's Uppercut+ articulation:
"the deck lacked vulnerable appliers and defense, so I picked a card that gave
both"); Colossus prior dock -0.8 via new OWNER_OVERRIDES lane (owner: community Elo
runs hot on it).

**Live catch during the handoff leg**: BOTH enchant-target rules (slither/sharp)
were dead code — the mod's screen says only "Choose a card to Enchant.", the name
lives on the event option one screen back. Enchant intent now carried via
ctx.screen_mem from event choice to target screen (8a66472); Slither-on-Taunt was
the tell. Only live human-alongside-bot play could have caught it.

**Also**: Doll Room catalogued (02dc30f — parser took Spirebird's WORST option every
time; now pays 5 HP for selection, Examine with a Daughter deck, dolls ranked with
deck-fit). Filed: phantom duplicate map decisions (2nd decision per floor, wildly
negative values — poisons route-intent analysis), negative path-value audit
(RestSite -58.7 "rest sites are not negative 58 hp"), act-2/3 elite mechanics pass
(Knights trio), monster_early stat is act-1-dominated.

## 2026-07-23 (Fable 5, session 11) — A/B #5 verdict: the Act-1 gap is ELITE AGGRESSION, not fight micro; KD claims the owner too

**A/B #5 (TZSM9SV0P0, whole-run, blind)**: bot died f17 to Soul Fysh; owner cleared
it in 7 rounds and died f33 to the Knowledge Demon. Recorder race fix VALIDATED
(full outcome captured with the game left open — ddbbfba works).

**The decisive decomposition** (same seed, same offers):
- Bot: ZERO Act-1 elites, 3 relics at f17, entered SF at 73 HP → 16 dmg/round, dead r10.
- Owner: TWO elites (f12, f14), 7 relics, entered at 67 HP → 27 dmg/round, won r7.
- Owner blocked selectively (only the 24-hit turns); the bot also never blocked — the
  fight delta is DECK POWER from elite relics, not tactical micro. **HP preservation
  without power is a losing trade**: the bot arrived healthier and deader.
- Entry-HP study corroborated again from the other side.

**REOPENS THE ELITE GATE** (owner flagged it 2026-07-13: "too conservative, but core
competency wasn't there" — competency now is: 90% arrival last batch). The §5-C gate
(pool_win_frac + 30% end-HP floor) is leaving the decisive resources on the table at
A0. Candidate levers for the owner's magnitude call: elite_gate_min_end_hp_pct
0.30→0.20, elite_gate_pool_win_frac down a notch, elite_relic_value up.

**KD recalibrated**: he bled out the OWNER from a 101-HP entry (379→199 over 11
rounds, heals clawing back). Not a bot-specific failure — near-wall for everyone
without dedicated tools. Deprioritized as forward-model target; the Soul Fysh
7-vs-10-round diff is the better spec case, and it points at DRAFTING ECONOMY first.

## 2026-07-22 (Fable 5, session 10 close) — 90% ACT-1 PASS RATE; the wall moves to Act 2 wholesale; A/B phase opens

**Batch b45wjw8a9 (Frond mode + act3 rest bump + bridge gamble live): 0/10, 1.90 —
and NINE of ten cleared Act 1** (era average ~50%; owner's human estimate 90%). The
funnel's biggest screen just matched human-rate on its first post-fix batch (n=10,
variance caveat). Everything then died in Act 2: Insatiable ×2, Kaiser ×2, four
mid-act normals, one EVENT death — the Lantern Key kill-chain (fight option read as
a free relic at 25/85 HP; fixed same hour: fight-text options now price an expected
monster loss through the hp gates, and the costless floor excludes fights).

**Normality audit (owner stall report)**: 0 cap violations, 0 rejected plays — the
stall was poll-rhythm optics. The code-read still found a latent zero-budget gap in
the DFS (1-card plans generable at '(0 cards left)') — guarded (8f37c56).

**Death distribution, clean-build era (n=108)**: act1 53 (49 AT the f17 boss),
act2 41 (24 at f33), act3 14. Owner's read confirmed conditionally: 75% of runs
clearing f17 die in Act 2. Entry-HP study says the boss-door condition is equalized;
the differentiator is fight execution over horizons.

**PHASE TRANSITION (owner-agreed)**: knowledge lane is substantially mined. Next:
fight-turn A/B — owner pilots a bot death seed; A/B candidate from this batch:
**TZSM9SV0P0** (Soul Fysh f17, the batch's only Act-1 boss death). KD-from-82hp and
Queen-f48 remain the deeper target cases. The A/B's turn-diff spec's the multi-turn
forward model from evidence.

## 2026-07-22 (Fable 5, session 10) — 1.90 batch; rest actions fire live (Hatch ×6, Lift ×5); the entry-HP hypothesis REFUTED by data

**Batch b21tcq01j (rest actions + costless floor + Thrash/Smoggy live): 0/10,
act-reach 1.90** — second-best ever. TWO f48 runs (Queen; Test Subject at 825
decisions). Validations: **Hatch fired 6×, Lift 5×** (the Byrdonis Egg era ends),
event catalog 13 engagements. Cook/Clone didn't roll.

**Entry-HP study (owner hypothesis, n=39 f33 fights)**: REFUTED in strong form —
winners and losers enter the Act-2 boss at IDENTICAL HP (60.8 vs 62.5, both 74%).
The HP-economy levers are pulled; at equal footing the differentiator is what the
deck DOES — the KD lesson generalized. One real signal: act-2 START HP separates
(35 vs 28) → Act-1 exit condition matters via routing/shop freedom. f48 weakly
favors entries (n=9); the act3_boss_loss_bonus (+15, bed456d) addresses the real
gap there (Act-1-dominated aggregate estimate — Queen entered at 25/53 after a
CORRECT rest decision on a 53-HP pool; est said 41, truth is 60+).

**Shipped today**: rest-site non-standard actions (faa43ad: Hatch/Lift/Cook/Clone;
Growth 1.5→4.0, Cleaver 2.5→5.0), costless-unknown event floor (e08488a), Delicate
Frond aggressive potion mode + act3 rest bump (bed456d — Frond was aboard a live
run with the switch STILL unshipped since A/B #4; owner-caught). **Slippery Bridge
gamble filed** (owner mechanics: lose-shown-card vs pay-X-and-reroll; decision rule
documented; blocked on one clean sub-screen capture — the bot currently drops
whatever's shown first).

**Strategic (owner-aligned)**: knowledge lane nearly mined — WG mini-audit, catalog
curation, potion odds-and-ends remain. Every analysis now converges on the same
successor: multi-turn forward model, spec'd by fight-turn A/Bs (KD-from-82hp and
Queen-f48 are the documented target cases). 377 tests.
## 2026-07-20 (Fable 5, session 9 close) — Bound validates 14/14 vs the Queen; event catalog engages but coverage caps it

**Batch bo1bhqron (reviewed events catalog + Foul guard + Bound/FB/FNP): 0/10, 1.70.**
Queen fight at f48 (run 3): **Chains of Binding compliance 14/14 plans, zero
violations** — first mechanic-aware Queen fight; she still won (f48 remains the
deepest wall). Kaiser ×2 at f33 (focus-Rocket confirmed live earlier; his wall is
block instances + entry HP like the rest), Matriarch/Kin/Soul Fysh/WG ×1 each at f17.

**Event catalog live: engaged 8×, Spirebird 24×, but decline rate still ~60%** — the
53-title catalog covers the top events' main options; the full title universe is
~150+. Coverage, not correctness, is the gap — v2 = full-title harvest broadening.

**Owner minutiae round (shipped mid-batch, debut next)**: Thrash growth+thinning
priced (w_exhaust_growth=5.0, fodder-gated per the owner's keeper rule; forensics
exonerated the card-vs-card math — Skittish/thorns were correctly priced, the future
value wasn't); Smoggy one-Skill-per-turn (Bound family) + a latent counter bug
(n_skills_played froze at 0 in relic-less fights); Gremlin Merc gold-recovery
deferred per owner. Events-pass review: 0 uncertain, SLITHER REVERSED (targeting sin,
not bad option — picker takes highest-cost card), Sharp prefers multi-hits, protected
potions filed. 373 tests.
## 2026-07-20 (Fable 5, session 9) — Events pass ships; KD rest-gate validates but he wins anyway (the forward-model frontier marker)

**Batch bidee2frt (Bound + Flame Barrier + FNP live): 0/10, act-reach 1.80** — second
1.80 in three batches; one f48 (vs AEONGLASS, a third distinct new-epoch Act-3 boss).
No Queen roll again (Bound untested live). **Knowledge Demon ×3 at f33 — and the
rest-gate bump VALIDATED while losing**: "est loss 56" demanded ~62, entries came in
at 62/82/75 (vs the old fatal 52-56)… and 82 HP + correct racing still lost. First
boss where knowledge patches have PLATEAUED — the cleanest multi-turn-forward-model
frontier marker yet. Waterfall Giant ×2 more (rule 0-for-4: next mini-audit — did
blocks get drafted, or is the eruption math still under-banked?).

**Correction (owner)**: Test Subject is a 3-STAGE boss (sequential), not 3-body —
ANTI-AoE; stage transitions may reset debuffs and will confuse the harness/kill
logic when audited. Previous entry's AoE note is wrong.

**Shipped this session**: Foul Potion hail-mary guard (25e4572 — owner-caught suicide
at 9 HP); recorder .run-read retry (ddbbfba — the A/B #4 all-null race); new-epoch
triage (c4ef887 — 10 boons incl. 3 day-one Orobas gaps, bestiary → 107); **EVENTS
PASS v1 (37ef0e7)**: discovery found DECLINE-BY-DEFAULT (50%+ Proceed across all 52
events); 53-option title-keyed catalog now engages (Slither trap stays negative,
Spirebird still outranks where confident). 11 uncertain options pending owner
keyword review. 369 tests.

Next: owner event-keyword review → rest-handler non-standard actions (4-member
class) → WG mini-audit → next batch (events catalog + Foul guard debut live).
## 2026-07-19 (Fable 5, night batch) — bq2sre642: 0/10 at 1.60; no Queen roll (Bound fix untested); Vantom rule 0-for-2; Slumbering Beetle's 3rd

**0/10, act-reach 1.60** (band holds: 2.00/1.30/1.50/1.80/1.60/1.80/1.60). One f44
(Owl Magistrate normal), two f33s (Insatiable, Kaiser), five f17s (Vantom ×2, Soul
Fysh, Kin, Matriarch), two Act-2 normal deaths (Mytes f23 — new name, likely
new-epoch; **Slumbering Beetle f21 — third lifetime normal-fight kill**, no longer
ignorable). No Queen roll, so the Chains-of-Binding fix goes untested live; ditto
Flame Barrier/FNP (no note of either in a decisive spot — check next session).

**Watch-list updates**: Vantom rule now 0-for-2 live tonight (offer-flow check needed —
same question as the Matriarch's: does Act 1 supply the multi-hits his rule wants?).
Waterfall rule still 0-for-2 overall. Region weights now 5 batches (~25 UD runs) —
enough for the magnitude review. Slumbering Beetle promoted to audit (3 normal-fight
kills: SLUMBER wake mechanic is explicitly NOT Asleep per the sim comment — verify
the wake model matches reality).

Morning queue: Slumbering Beetle + Vantom offer-flow checks → new-epoch triage
(Phial Holster, Mytes, Test Subject, Lost and Forgotten) → region magnitude review →
recorder bug → events pass.
## 2026-07-18 (Fable 5, session 8 close) — WIN #3 on the full 8-rule table; no dominant wall for the first time

**Batch bhlrfgvf2 (complete boss-rule table live): 1 WIN, act-reach 1.80.** Three runs
at/near the end: the win (f48), a Queen death at f48, an f39. **Two wins in the last
five batches vs zero in the fifteen before** — the knowledge-first curve is bending.

**Win #3 (2E666RMTTX, f48) anatomy — the systems compounding**: f1 Ancient was
"Phial Holster", an UNKNOWN new-epoch boon handled by the clamp (heur-capped 5.0 —
graceful degradation's first live win); f18 Storybook 7.5 (Brightest Flame in the
final deck); f34 Spiked Gauntlets 7.5 — the double-energy-Ancient signature now
common to ALL THREE bot wins. Deck: 29 cards / 11 upgrades / 12 relics, Flame
Barrier ×2 (won while still priced as plain block — credit ships next batch).

**Killer board: spread thin for the first time** — no boss took 3+: Waterfall Giant
×2 (his rule 0-for-2 live; watch), Kin ×2 (rule live; check AoE offer flow), then
Matriarch / Kaiser / Insatiable / Queen ×1 each. The studied bosses stay receded.

**Owner-check fixes shipped mid-batch (debut next batch)**: Flame Barrier retaliation
credited (c566cfa — retaliate × incoming attack instances, score-only) and Feel No
Pain block per exhaust event (f88579b — makes Stoke playable in synergy context;
narrow exhaust-counting regexes; Drum-class trigger text counts zero).

Next: new-epoch triage (Phial Holster + friends), Waterfall/Kin rule check after
another batch, recorder bug, events pass. Queen (2 f48 deaths) is the next audit
candidate if she repeats.
## 2026-07-18 (Fable 5, session 8 cont.) — Kin + Insatiable audited: EVERY repeat killer now has a trace-grounded rule

**The Kin (00fe9a5)**: 2 Followers (58/59) + a 190-HP Priest with permanent Frail/Weak
cycling = 307 aggregate HP. AoE is the axis — the Conflagration deck cleared the
Followers by r5 and nearly won from a 52hp entry (the 38hp entry was dead on arrival).
New aoe_bonus rule field: THE KIN premiums AoE +2.0 (X-cost excluded), rest +10.

**The Insatiable (6868fb6)**: pure escalating attrition (Empower cycle, 6-status-card
pollution, 8x2 → 28 → 12x2 → 30 onto small blocks; ~17/round of our damage wasn't
enough from a 61hp entry). The human answer is on file — A/B #3's win from 51hp was a
Barricade engine banking 93 — so INSATIABLE names BARRICADE +2.5 as tech, premiums
block≥9, bumps rest +10.

**Boss-rule table: 8 entries** (LAGAVULIN, VANTOM, KNOWLEDGE, WATERFALL, KAISER,
SOUL FYSH, THE KIN, INSATIABLE) + kill-priority (SHRINKER, ROCKET) + enemy Intangible
in the sim. Every boss with 2+ lifetime kills is now covered. The recurring indictment
(5 of 8 rules premium block≥9) makes the global big-block draft term the obvious next
magnitude discussion once the next batch reports.
## 2026-07-18 (Fable 5, session 8 close) — Batch bwvwblkf9: fixes verified live (1.60); the wall rotates to the UNSTUDIED (Kin, Insatiable)

**0/10, act-reach 1.60.** Arrival streak ended at 41 (f15 Snapping Jaxfruit normal —
first pre-boss death in five batches). Second consecutive batch to reach the ACT-3
BOSS: f48 vs Queen (win #1's boss). f17 deaths ×6: Kin ×2, Matriarch, Soul Fysh,
Waterfall Giant (his rule's first live roll — lost), plus the f15.

**Fix validation (grep-confirmed live)**: Kaiser targeting now favors Rocket (4:1,
11:7 ratios; 1 Kaiser death, was 3); Soul Fysh Intangible turns flipped to non-attack
plans (3:1, 3:0, 5:1 non-attack-first). The audit → rule → validate loop is tight.

**Killer board rotation — the studied bosses recede, the UNSTUDIED lead**: The Kin ×2
this batch (~5 lifetime, never audited — multi-creature boss, the §5-C bestiary
composition case), The Insatiable f33 (3 lifetime, A/B #3's boss, never audited).
These two are the next forensics targets. Waterfall rule needs more rolls to judge.

Next session: Kin audit → Insatiable audit → new-epoch triage → recorder bug →
events pass. Watch: big-block scarcity (global-term candidate), region weights
(4 batches of data now), THORNS/STRENGTH_POWER harness residuals.
## 2026-07-18 (Fable 5, session 8) — Kaiser Crab + Soul Fysh audited; enemy Intangible lands in the sim

**Kaiser Crab (4 f33 deaths, cdd6257)**: the fight is Crusher+Rocket, and Rocket
decided every loss — escalating 27→33→49 nukes onto 0 block while the bot burst the
tamer Crusher (one fight: Crusher 209→39 as Rocket wound up the killing 49). ROCKET
joins the kill-priority lane (focus him while both claws live); KAISER rule: block≥9
+2.0 at draft, rest +10 (54-65hp entries all died).

**Soul Fysh (2 f17 deaths, 5c6d091)**: three-axis squeeze — Beckon flood (2/cycle;
mid-fight the bot spends 1-3 plays/turn on garbage disposal; one death turn held FOUR),
periodic **INTANGIBLE turns the sim was blind to** (two Strikes into one dealt 2 total
damage), escalating 16→24 hits on small blocks. **Enemy Intangible now modeled**: every
damage instance → 1, so the planner naturally spends shield turns clearing Beckons and
blocking. Likely closes the ancient +2.4 Soul Fysh harness residual. SOUL FYSH rule:
block≥9 +2.0. (Player-side Intangible / Apparition play value still unmodeled — the
Distinguished Cape reprice trigger stays open.)

**Boss-rule table complete for all observed repeat killers**: LAGAVULIN, VANTOM,
KNOWLEDGE, WATERFALL, KAISER, SOUL FYSH + kill-priority (SHRINKER, ROCKET). Recurring
meta-signature across five bosses: chronic lack of BIG BLOCK INSTANCES — if it persists
next batch, promote to a global draft term instead of per-boss premiums.

Next batch validates focus-Rocket + KAISER + SOUL FYSH live. Then: new-epoch triage,
recorder bug, events pass.
## 2026-07-18 (Fable 5, session 7 close) — Validation batch 1.80 (win-era level); Underdocks climbing; Kaiser Crab is the wall

**Batch bw8aag1aa (Vantom rule + Smith targeting + rest bumps + Primal Force pkg +
Waterfall rule all live): 0/10 but act-reach 1.80** — win-era average, second-best
batch ever. **Arrival 40/40** across the clean build. Run 9 died AT THE ACT-3 BOSS
(f48, "Test Subject" — new-epoch content, deepest loss on record); run 6 f44.

**Boss-rule scoreboard**: Lagavulin Matriarch down to 1 f17 kill (was 3) with her full
package live; Underdocks past-f17 climbing 1/5 → 3/6 → **4/7** across the three
region-weight batches. No Waterfall rolls (rule untested). **Kaiser Crab ×3 at f33**
(4 lifetime) — clearly the next audit; Soul Fysh ×2 f17 also unstudied.
HP prediction 84%; new residual: player STRENGTH_POWER bucket takes 7.3 MORE than
predicted (n=7 — possibly the Matriarch's negative-Strength display; file with THORNS).

New-epoch names seen: Test Subject (Act-3 boss), The Lost and Forgotten (Act-3
normal). Bestiary harvest picks them up automatically; boon triage still pending.

Next: Kaiser Crab audit → Soul Fysh audit → events pass. Primal Force keeper
protection (24f3ea2) shipped this session: DFS discovers keepers-before-PF unaided.
## 2026-07-18 (Fable 5, session 7) — A/B #4 (Matriarch): the region weights make the owner's pick; boss-rule round 2 ships

**A/B #4, seed Q9R71WZ58T** (bot's 135659 f17 death, 68hp entry, four 8s + one 17):
owner piloted blind and **WON the run** — humans are now 2-for-2 on bot death seeds
(A/B #3, #4). The win toggled ANOTHER epoch: **all seeds stale again; new-content
triage next session.** (Recorder bug filed: outcome meta came back all-null despite a
normal win + the game staying open — the extraction failed silently this time.)
- **Convergence headline: at the f2 offer [Anger, Stone Armor, Twin Strike] the bot's
  new machinery made the owner's exact pick** — Stone Armor at 13.0, underdocks-tagged
  — a pick the owner called "breaking my own damage-early rule" (Anger is actively bad
  vs the Matriarch; 4 early Plating is real). Region weights turning expert judgment
  into the top score, on the same reasoning.
- Owner divergences: Plating as a deck THEME (Stone Armor ×3 + upgrade), **Primal
  Force at f9 as dedicated Matriarch tech** (converts chip 8s into 16-dmg Giant Rocks
  — mass threshold-crossing; needs piloting to avoid transforming keeper attacks; our
  sim's primal_active already sequences within-turn), entry at 88hp vs the bot's 68,
  potion usage "at the edges" of her fight.
- **Act 3 ceiling demo: Delicate Frond + 5 potion slots = most potions played every
  fight** — "a bonanza of stuff the bot currently cannot do" (edge-casey, but the
  relic-conditional potion-aggressiveness switch from §8.5.4 notes just got a live
  exhibit).

**Shipped this session (boss-rule round 2 + 3):**
- Knowledge Demon: heal-race EXONERATED by trace (33/turn, +26 through his heal); the
  deaths were 52-56hp entries. KNOWLEDGE rest_loss_bonus +15 lifts the pre-boss gate
  ~66→82 (5feb164).
- Boss-aware Smith targeting: upgrades crossing the act boss's instance threshold
  (Headbutt 6→12) earn +2.0 on the upgrade key — second lever vs the Matriarch's
  offer-stream constraint (5feb164).
- Primal Force card_bonus (+2.5 vs LAGAVULIN) via new per-boss named-tech dict (454ee92).
- **Waterfall Giant solved** (owner mechanics: eruption = death mechanic, fires 1-2
  turns after 0 HP as a telegraphed DeathBlow, blockable, surviving = winning). First
  same-turn debt model REVERTED after owner's timing clarification (it made the
  planner stall on kill turns — the sim caught it before it shipped); the existing
  DeathBlow-intent lane already prices the block-up turn, and kill-ASAP is correct.
  WATERFALL rule: block≥9 +2.0, rest_loss_bonus +10 (575c315).

Boss-rule table now: LAGAVULIN (hits/blocks/powers/Primal Force), VANTOM (multi-hit/
blocks), KNOWLEDGE (rest), WATERFALL (blocks/rest). Remaining audits: Insatiable ×2,
Kaiser Crab. Then the events pass.
## 2026-07-17 (Fable 5, session 6) — Boss-rule era opens: Matriarch rule bites (1/4), Vantom rule shipped, arrival streak 30/30; the second wall is f33

**Batch bgni3z63s (region + Matriarch rule + Spoils Map + Normality live): 0/10,
act-reach 1.50.** Arrival **30/30 across the clean build** — pre-boss survival is a
solved problem for now. Past-f17 5/10; the killer board: Lagavulin Matriarch ×3 (f17),
Kin ×2 (f17), and an emerging **f33 wall**: Knowledge Demon ×2, Insatiable, Kaiser Crab
(4 Act-2 boss deaths — the Demon is at 4 lifetime and unbeaten since the heal-race fix
hasn't been live-validated against him... it WAS live this batch; still lost twice).

**Matriarch rule verdict: WORKING, INSUFFICIENT ALONE.** Big-instance takes 3/3, 2/4,
2/4, 3/4 in her four runs; entry decks now carry 12/17/24-damage instances where the
pre-rule era carried none; one of four beat her (the 24+25 burst deck, reached f33).
The offer stream is the binding constraint — 135659's entire damage suite was four 8s
and a 17. **Filed lever: boss-aware rest-site upgrades** (an 8→12 Smith crosses her
threshold; Smith targeting is currently boss-blind).

**Vantom rule shipped mid-batch (2255c44, next batch)**: forensics confirmed the
owner's theory exactly — Slippery 9 ate five rounds of single-hit attacks in
zero-multi-hit decks, and the rigid 26/28/30 cycle-nuke landed on zero block every
time. VANTOM premiums hits≥2 (+2.0) and block≥9 (+2.0) — the OPPOSITE attack profile
from LAGAVULIN, vindicating the boss-keyed table design.

**Region weights, two batches in**: UD past-f17 1/5 → 3/6 (incl. a Matriarch kill);
OG 2/5 → 2/4. Direction right, sample still thin; magnitudes untouched.

Next: Waterfall Giant + Insatiable audits (boss-rule candidates), Knowledge Demon f33
recheck (heal-race was live and still lost ×2 — trace whether racing happened),
boss-aware Smith targeting, then the events pass.
## 2026-07-17 (Fable 5, session 5 close #2) — Region-weights batch runs cold (1.30); arrival streak hits 20/20; the wall is now the f17 fight itself

**Batch bini668vh (region weights + Normality fix live): 0/10, act-reach 1.30** — a hard
swing from 2.00. Seven f17 boss deaths (Vantom ×3, Waterfall Giant ×2, Lagavulin
Matriarch, Soul Fysh), Insatiable f33, Spiny Toad f23, Decimillipede elite f29.

**Region verdict: NOT YET.** The ud_* weights demonstrably fired (6-8 region-tagged
drafts per UD run, 0 prior; entry HP 62→60) but past-f17 fell in BOTH regions (UD
3/6→1/5, OG 3/4→2/5 — three Vantom deaths in the unchanged region). n=5/cell = boss
variance, no tweak yet; bank 2-3 more batches (owner: "keep an eye on this").

**What held: f17 arrival is 20/20 across the clean build** — the pre-boss bleeding
that defined the regression era looks CURED (era average was 85%). The binding
constraint moved to the Act-1 boss fight: 9/20 past f17 at decent entry HP (36-70).
Clean-build killer board: **Lagavulin Matriarch 4** (harness: we over-fear her sleep
by 3.4/turn — likely blocking through the setup window), Vantom 3, Waterfall Giant 2,
Soul Fysh 2. Also of note: Slumbering Beetle took ANOTHER run (f29) and the
Insatiable remains unlearned since A/B #3.

Next: **Lagavulin Matriarch sleep model** (top killer + known harness signature) →
boss-fight competence generally (the multi-turn forward model's case strengthens as
knowledge patches saturate) → events pass. Spoils Map handling (7f0a0c6) debuts next
batch.
## 2026-07-17 (Fable 5, session 5 close) — WIN #2 and act-reach 2.00: the clean build delivers

**Batch b1i49b9k0 (first on the fixed build): 1 WIN, act-reach 2.00 — PROJECT RECORD**
(win-era peak was 1.78; the previous batch 1.30). Four runs into Act 3 (f38 / f43 /
f46 / f48-WIN), f17 arrival **10/10** (first zero-pre-boss-bleed batch of the era),
f17 boss win 6/10 = 60% (win-era: 53%). HP prediction 85% on deep-content mix; sole
systematic residual: player THORNS over-predicts our loss by 6.7 (n=9) — filed.

**Win #2: seed 8WJBRSSHG7, Overgrowth (The Kin), f48.** The Ancients pass carried it
(owner live-read agrees): Pael's Flesh (8.5) at f18 + Whispering Earring (5.5) at f34 —
a double-energy-boon run — and the boon→draft steering visibly fired: Battle Trance ×2
+ Bloodletting+ ×2 drafted BECAUSE owned energy boons lift the draw penalty. 15 relics
(late-shop routing live), Juggernaut+/Colossus/Taunt+ block seasoning. A coherent deck,
not goodstuff.

**Live-catch validations**: zero "not resolving; skip" across the batch (the debounce
exemption ended select-screen forfeits); 20 catalog ancient picks incl. 4 unknown-boon
clamps (new-epoch options handled gracefully); no bundle screens rolled (scoring
untested live). **Normality remainder** caught by the owner mid-batch: STS2's text
carries "(N cards left)" and we read only the static 3 — f45 planned a 3-card LETHAL
with 1 play left, spent it on Bloodletting, and run 7 (f46, Act 3) died the next fight.
Fixed same hour (15e4cf8); plausibly cost this batch a SECOND win.

**Region watch (weights not yet live this batch)**: the four f17 deaths split 3
Underdocks (Soul Fysh, Lagavulin Matriarch ×2) / 1 Overgrowth — same signature as the
retrospective. The ud_* draft weights (90bc951) debut next batch; track arrival by
region.

Next: next batch (region weights + Normality fix live) → Lagavulin Matriarch sleep
model → events pass. The fight-competence lane keeps its place behind knowledge
patches — this batch is strong evidence the knowledge-first philosophy is paying.
## 2026-07-17 (Fable 5, session 5 cont.) — REGION SPLIT: the owner's Overgrowth/Underdocks hypothesis lands; "new content" claim corrected

Owner hypothesis: Act 1 has two enemy-disjoint regions, elite players draft damage in
the **Overgrowth** and defense/scaling in the **Underdocks**, and our woes might be new
Underdocks enemies + an Overgrowth-tuned policy. Retro over 451 runs (enemy
co-occurrence union-find — no internet needed):
- **Clean 2-component split**, bosses region-exclusive: OG = Ceremonial Beast / The Kin /
  Vantom; UD = Lagavulin Matriarch / Soul Fysh / Waterfall Giant.
- **"New enemies" half REFUTED** (correcting the previous entry's claim): first-seen
  dates put the entire Act-1 roster before the win era. Act-1 killers are not new
  content. (Knowledge Demon / Act 2+ newness still unverified.)
- **Policy-fit half CONFIRMED**: arrival-at-f17 flipped exactly at the 07-14
  damage-first rework — Overgrowth 72%→90%, **Underdocks 87%→77%** (n≈20/cell,
  directional). The pre-boss bleeding is an Underdocks phenomenon; boss-fight win
  rates fell region-agnostically (that part stays with the fight-competence lane).

**Shipped (90bc951)**: region-conditional Act-1 draft bonuses. Region derived from the
f1-cached boss name (`_act1_region`); Underdocks swaps the early bonuses (damage
2.5→1.0, block 1.5→2.5 via `ud_*` weights — magnitudes provisional, owner: "will
require tweaking"). Draft rationales now carry a region tag for per-batch eyeballing.
**Watch item: track arrival-by-region in subsequent batches** (region_split.py in the
session scratchpad does the retro; fold into a script/ tool if it earns its keep).

Also this session, pre-batch fixes (see commits): Shrinker Beetle carrier lane
(8fcbddf), Knowledge Demon = heal-race + harness noise not a damage-model bug
(7dc9a29), early-damage saturation taper (0eead94). Batch b1i49b9k0 (running) carries
everything EXCEPT the region weights, which debut next batch.
## 2026-07-17 (Fable 5, session 5) — Ancients pass validates live; era mystery flips to CONTENT; three live catches fixed mid-batch

**Batch byupfrv22: 0/10, act-reach 1.30** (f17 boss ×5: Vantom, Lagavulin Matriarch ×2,
Kin ×2; Knowledge Demon f33 ×2; Infested Prisms elite f29; and two NORMAL-fight deaths —
Mawler f9, Sewer Clam f15). HP prediction 82% batch-scope (down from 92%: new-boss mix).
Owner live-watched: "the current run in Act 2 is impressive... barely scraped by half of
act 2, but *still scraped by*" — micro reads as genuinely improved; the losses are walls,
not blunders.

**Ancients pass: live-validated on its first outing.** Neow went catalog-driven
(Precarious Shears / Silver Crucible / Arcane Scroll — all sensible), and both observed
f18 picks were textbook: **Storybook 7.5** (owner's Brightest Flame steer) over
Cookie/Candle, **Pael's Flesh 8.5** over Claw/Eye. No remove-bait picks anywhere.

**Live-catch trio (owner eyes on the stream), all fixed same-night (95f741d):**
1. *Power Potion Cruelty forfeit*: the orchestrator debounce (Owl fix) held selection
   resubmits while the policy retry budget burned on decides-without-submits — 8
   "retries" in ~4s, one real submission, cancel valve fired. Selection-overlay actions
   (select_/confirm_/cancel_) are now debounce-exempt; play_card stays debounced.
   (Planner exonerated: w_power_played already values Powers; Cruelty never reached hand.)
2. *Havoc via blind bundle*: reward offers dock Havoc -9.79; it snuck in through the
   unscored Neow bundle screen (Trivial fallback takes #1). StandardRouter now scores
   bundles by summed deck-aware card value.
3. *Silken Tress hijack*: an uncatalogued new-epoch boon's hot heuristic knocked the
   whole Neow screen back to the generic path (→ baited Scroll Boxes 7.0 over Lava
   Rock). Unknown boons now rank clamped at 5.0 inside the catalog path; Tress catalogued.

Also shipped: **late-shop-loop routing** (b6e9801, owner's practice, A/B #3-validated):
shop nodes priced at projected gold-on-arrival (+12g/row); rich wallets bend routes
toward shops. Known limit: path_step_discount still prefers the earlier of two shops.

**THE ERA MYSTERY FLIPS.** Act-1-scoped comparison (run-length confound removed):
- Act-1 skip rate 13% → 15% — the draft-tightening story is dead in Act 1 too.
- f17 entry stats near-identical: hp 62→59, relics 4.2→3.8, deck 16.1→17.0, upgrades equal.
- What DID change: f17 arrival 100% → 85% (pre-boss deaths were UNHEARD OF in the win
  era), and f17 win-given-arrival 53% → 40%.
- The killers are largely NEW enemies (Mawler, Sewer Clam, Lagavulin Matriarch,
  Knowledge Demon, Infested Prisms — all post-epoch content, all in the bestiary via
  harvest but none with tuned mechanics), and the epoch timeline brackets the era
  boundary (RELIC1 + COLORLESS2 obtained mid-July). **Leading theory: the "regression"
  is substantially a content-difficulty shift, not a policy own-goal** — the win era
  fought a softer, known pool. The draft-audit-as-rollback is CANCELLED; the
  saturation taper stays (it's just correct); the enemy pass gains two anchors:
  **Knowledge Demon (we over-predict our own damage by 11.3/turn, n=10 — something
  eats our output; killed both f33 runs)** and Lagavulin Matriarch (we over-predict
  its threat 3.4/turn — sleep phase, likely mild).

Next: new-enemy mechanics mini-pass (Knowledge Demon first), early-damage saturation
taper, then events pass. Fixes from tonight (debounce/bundles/clamp/shop-loop) are all
post-batch — next batch runs the new build.
## 2026-07-16 (Fable 5, session 4 close) — A/B #3 (MY60EQE85L): owner WINS the bot's death seed; skip-hypothesis REFUTED, fight competence indicted

**Setup**: seed picked as the tightest-draft specimen of batch bskhaw1re (bot: 12 takes /
5 reward-screen skips, died f33 to The Insatiable, Act-1 boss entry 80hp). Owner piloted
blind (no knowledge of the bot's picks) via `sts2bot record` on profile 1. Validity
confirmed: the first six reward screens are byte-identical across runs; the epoch flip
(COLORLESS2_EPOCH, 3 new colorless cards) was unlocked BY the owner's win at run end, so
the whole run was played on the old epoch. **All pre-existing seeds are now stale.**

**Result: owner won the entire run** (Act 3, f48, beat the final boss at ~50/87hp).
Same seed the bot died on at f33.

**The skip hypothesis died on contact with evidence:**
- Aligned early offers: **5/6 identical picks** (Bully, Taunt, Dismantle, Aggression,
  Colossus; sole divergence Armaments > Sword Boomerang for the owner).
- Late offers: owner skipped **5 of their last 6** (took only Cruelty at f33); the bot
  skipped 5 of its last 6. Heavy Act-2/3 skipping is *what the human does too*.
- Relic income at the bot's death floor: **owner 9 vs bot 8** — parity. The owner's 17
  total came from Act-3 shop conversion of banked gold (740g at f33 → two big sprees).
  The era relic decline (7 → 5.3) is confounded by run length: shorter runs mechanically
  collect fewer relics. Deck size too: owner ended at 25 cards (with a curse!) vs bot 20
  — "arriving thin" was never the problem.

**What actually diverged (owner commentary sharpened all three):**
1. **THE ANCIENT CHOICE WAS THE ROOT.** Both runs hit the same PAEL Ancient at f18
   (Act 2 start): Pael's Horn / Pael's Tooth / **Pael's Legion** ("doubles Block gained
   from a card, then sleeps 2 turns"). The owner picked Legion *because they sensed the
   deck lacked block*, then drafted Barricade the very next floor (f20) explicitly to
   bank the doubled block across turns — the whole tank engine (Barricade+ / Unmovable+ /
   Colossus+ / Taunt+, Dominate ×2 payoff) grew from the boon. The bot, which scores
   ancient relics neutral-0, took Pael's Tooth and built nothing. Engine drafting is
   downstream of boon awareness: tags need relic/boon providers (Legion ⇒ block-engine
   need), not just card-to-card synergy.
2. **Fight competence, boon-powered.** Owner entered the Insatiable at 51/87 (not ~25 —
   earlier read was the post-fight poll) and exited 25/87. In-fight the Legion engine is
   visible in the trace: block banked 40→52→64→77→84→**93** while hp held 25→22→19. The
   boss threw ~26/turn; the bot (entered 49/80, same deck-quality tier) blocked 8–19/turn
   and bled out 49→31→21→7 in ~4 turns. No single-turn planner beats that fight without
   the engine — but the engine was *choosable at f18*.
3. **One true misdraft (owner-flagged): Sword Boomerang over Armaments at offer 3.**
   Scores: SwordBoom 11.09 / Spite 8.70 / Armaments 2.03. The Act-1 damage-first stack
   (early_damage_bonus + attack tags on a 75%-basic deck) kept paying with Bully+Taunt
   already in deck — a desperation-damage pick with no saturation check. Owner: skip or
   Armaments ("a Defend that upgrades" has real early value) were both fine; an average
   attack was not. Lever filed: **taper early_damage_bonus by non-basic damage-card
   count** (full at ≤1, decayed by 2–3+), mirroring the first-big-hit switch.

**Queue implications (audit re-scoped, not cancelled):**
- Draft-tightening audit **de-scoped from "loosen skips"** — the 22% skip rate is
  human-plausible. Concrete draft items instead: early-damage saturation taper;
  relic/boon-conditional engine tags (Barricade-class); double-Dominate copy behavior.
- **The Ancients pass (PLAN §8.5.5a) is now live-validated as decisive** — the single
  f18 choice separated a win from a death. Recommend it jump ahead of the events pass
  (small pool, huge leverage; PAEL options captured in both records as a starter corpus).
- The **multi-turn forward model** keeps its evidence but the sequencing softens: the
  human won this fight *via the boon engine*, not micro alone. Knowledge-first still
  holds.
- Era act-reach regression (1.78 → 1.38) needs a non-drafting explanation — rerun the
  era comparison with per-floor-normalized relic/skip stats before touching weights.

## 2026-07-16 (Fable 5, session 4 close) — Batch bskhaw1re: HP prediction hits 92%; the era gap is REAL and the draft audit fires

**Batch: 0/10, act-reach 1.40, relics 5.3, elites 0.3** (f17 x5 incl. Soul Fysh x2 /
Vantom x2 / Kin, one Bygone Effigy ELITE death at f15 — the gate took a fight and lost
it — two f33s, f24, f22). Burrowed/Ravenous/ramp-stall all live with no incidents.

**Harness: HP prediction 92% within +-2 (79 -> 86 -> 92 in three days).** Plating
residual GONE (0.2), Corpse Slug signature CLEARED (Ravenous fix validated live).
Remaining: Soul Fysh +2.4 (n=7, small — possibly Beckon chip), and one single-run
damage bucket (Centennial Puzzle deck +12.7 n=15) parked.

**The era gap is now firm at batch granularity**: win-era (07-12/13) averaged ~1.78
act-reach over 4 batches; post-rework (07-14+) averages ~1.38 over 4. Two quantified
suspects: (a) draft skip-rate 16% -> 22% (the rework wave tightening: draw penalty +
Whirlwind dock + block scoping + Ancient retier); (b) relics ~7 -> ~5.3/run (capability
routing declines most elites -> relic starvation -> weaker f33 decks). A third,
subtler: the pre-bake fixes REMOVED phantom damage credit — two cancelling bugs had
been accidentally encouraging aggression; correct estimates may have swung the
block/race balance conservative (ramp-stall partially counters).

**DECISION (watch item fires): the draft-tightening audit jumps the queue** — before
the events pass. Scope: per-change ablation over the logged offers (re-score the era's
skipped cards under each weight subset), check the skip-rate against the owner's
"weak decks take almost anything" principle, and revisit elite_relic_value vs the
honest gate (relic starvation is a ROUTING income problem, not just drafting).
## 2026-07-16 (Fable 5, session 4 cont.) — Batch bjqlx8sjo: cold (1.20) but the MODEL is the story: HP prediction 79% -> 86%

**Batch (first with card-select retry fix, Howl exhaust, Whirlwind dock, Plating): 0/10,
act-reach 1.20, relics 4.4** — cold: six f17 boss deaths (Kin x2, WG x2, Lagavulin, CB),
an f5 Cultists death and an f14 Sewer Clam death (both thin 2-3-relic starts), two f33s.
WATCH ITEM: three-batch act-reach trend 1.50 -> 1.40 -> 1.20 since the draft rework
wave — could be 10-run noise (the f48s/win era had the same code twice), but if the
next batch stays under ~1.4, audit the draft changes' interaction (draw penalty +
Whirlwind dock + block scoping may be over-tightening Act-1 picks together).

**Harness verdict on the same runs: HP prediction 86% within +-2 (from 79%), and the
Plating signature is effectively GONE** (residual +2.3 n=6, slight over-credit — maybe
decay timing; watch). Corpse Slug -4.5 persists as expected (the Ravenous fix landed
mid-batch, not in this batch's process). Remaining full backlog: tiny residuals only
(STRENGTH +2.4 n=5, FRAIL -0.6). The model now predicts its own turns at 86%/64% —
from 42%/32% apparent (79%/64% real) two days ago.

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

**Same session, two of those closed via the --enemy drill (both EXPLOITABLE stuns the
bot had been triggering by accident):**
- **Tunneler / BURROWED**: "Block is not removed at the start of Tunneler's turn.
  Stunned if all Block is removed." -> block-strip = attack cancelled. Modeled as a
  BLOCK-based stun next to the Plow HP-threshold stun; the planner can now aim for it
  (test: breaking 5 block cancels a 23 hit and beats defending).
- **Corpse Slug / RAVENOUS**: "When an enemy dies, Corpse Slug immediately eats it,
  becoming Stunned and gaining 4 Strength." -> killing ONE slug cancels the surviving
  pack's whole turn. Modeled as a crab-rage-style kill reaction (stun all living
  ravenous allies); the +4 Str arrives pre-resolved in next turn's intent labels.
- Parafright/Obscura CLOSED (owner co-debugged live): no mechanic at all — the entire
  signature was the Plating gap in a second costume. A stale mid-turn poll (read
  between two Stone Armor+ plays) faked a Plating inconsistency; with the true end-of-
  turn Plating (12, decaying to 11 next turn per the -1 rule the owner flagged), every
  number closes exactly: r2 22 incoming - 12 Plating = 10 taken; r3 26 - 13 block - 11
  Plating = 2 taken. The Obscura's dual intent fires BOTH halves (owner confirmed).
  Already fixed by this morning's Plating modeling.
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

## 2026-08-15 — Act-3 A/B rep 1 (seed BKF0WL1V3E): owner arm + alignment
- Owner played act 3 from the act-3-entry checkpoint (~30 min, recorder tape
  logs/manual/act3_ab_rep1/runs/20260815-164417_manual), 7 decisions banked in
  owner_commentary.md. Run PARKED via Save & Quit mid-act-3; owner continues
  next session. TRAINS HELD until then (parked run would be consumed by
  Continue; owner also needs the machine).
- Alignment vs bot arm (20260814-084223, died Queen f48), full note in
  owner_commentary.md. Headline: same-screen Vakuu event, bot took Whispering
  Earring on static catalog value; owner took Music Box, rejecting Earring
  because Pyre's energy curve nullifies it — third independent appearance of
  the energy-curve principle. Convergent: bot hatched the Byrdonis Egg at f40
  (rest handler knows Hatch). Confirmed-missing terms: relic-conditional
  pathing, deck-solidity ?-node preference, innate-opener combo drafting.
  Working: pre-boss rest DFS forecast (est loss 87 vs Queen — accurate).

## 2026-08-15 (evening) — Act-3 A/B rep 1 CONCLUDED: owner arm WINS the run
- Owner resumed the parked run (session 2 tape runs/20260815-193136) and WON.
  Queen: entered 87/87, guard down r3, ~304 damage in one turn (r4->r5,
  Queen 327->23), finish r6 at 36 hp. Bot arm died to Queen f48 on the same
  seed — the direct boss comparison lands squarely on damage concentration
  (setup-then-burst: KD 143, Queen ~304) plus arrival HP (87/87 vs ~96 into
  a longer bleed). Decisions 1-8 + outcome in act3_ab_rep1/owner_commentary.md.
- Win unlocked a NEW EPOCH: seed BKF0WL1V3E stale, full-bot-replay arm
  cancelled. New event in pool: Trash Heap (uncatalogued; generic floors
  apply until sighted in logs).

## 2026-08-18 — Test Subject savescum A/B (owner-suggested harness): burst_window near-NEUTRAL on this snapshot
- Watcher (scripts/watch_boss_checkpoint.py) checkpointed batch run 13's TS
  fight at f48 (r6, P3 body 71/300); snapshot replayed under new code, watcher
  re-fired at r6 preserving it. Row-by-row: both arms played the SAME r5
  intangible turn (Bash+ vuln poke into the wall -- correct dead-turn use --
  FNP+/Bloodletting+/Conflagration/Defend) because the one-turn DFS already
  knew Intangible caps hits (Soul Fysh modeling); r6 unloads identical (the
  apparent old-arm shortfall was the watcher interrupt, not the mode).
- Verdict: burst_window changed SCORES (Defend 4.5 -> 16.5 on the intangible
  turn) but not the argmax for this strong hand; its value case is weaker
  hands where defend promotion flips a play. Guard + snapshot harness both
  validated mechanically. This deck crushes TS regardless (P3 to 21 by r6).
- Trains resumed (28 runs; first Continue completes the TS fight for the win).

## 2026-08-18 — Setup-then-burst shipped + KD snapshot A/B (same-day)
- Owner answered the three spec questions (15hp ABSOLUTE floor + risky-setup
  death sentinel; bosses only, KD+Queen rows; looser flip eta<=2 + half-dent
  hand check) -> phases A+B shipped 38ca162. RISKY-SETUP sentinel lives in
  batch_summary.
- KD watcher checkpointed batch run's KD fight (f33) same hour; replay under
  new code: IDENTICAL per-round trajectories r1-r4 (player 90/88/81/60, KD
  379/313/253/163 both arms; interrupt-instant body 40 vs 58 = play-order
  noise). setup_turn tags fired r1-r4 (eta>2 throughout; flip was ~r5), but
  the argmax barely moved: this deck's damage WAS its value -- nothing to
  bank, so setup==race for it. Same result class as the TS burst_window A/B:
  mechanism verified row-by-row, effect size small on strong decks. The mode's
  target population is power/tutor-heavy decks that CAN'T static-race 379 hp
  (the 85/45-plan class from the original KD A/B); the sentinel + future
  snapshots on weaker decks are the watch.
- Also this session: Sai forecast row + real-Dex rollout (owner corrections),
  TS burst_window validated near-neutral, boss-checkpoint watcher script
  landed. Trains relaunched on all-new code; Queen watcher disarmed (re-arm
  deliberately after the next tuning change, not as a standing batch tax).

## 2026-08-18 (later) — RECORD BATCH: 9/40 wins (22.5%) on all-new code
- First batch ever past the ~20% A0 graduation bar (era ~11-12%; prior best
  trains 6-7/40). Act-reach avg 2.15. All of today's changes live:
  setup-then-burst (KD/Queen), TS burst_window, Sai forecast row, real Dex.
  Caveat honestly: single batch, ~2 sigma over era expectation -- the next
  batches say whether 20%+ is the new level or variance.
- RISKY-SETUP sentinel fired ONCE (its first data point): KD f33 death,
  setup r8 -> died r10. Dissection: 25 dmg/turn deck vs KD 379 + Ponder
  heals (161 -> 178 between rounds) = unwinnable regardless; player bled
  78 -> 21 through eight setup-tagged rounds because eta_p25 never came
  within flip range. The floor (15) isn't implicated -- but the pattern
  suggests a possible refinement for owner review: stop banking when
  eta_p25 exceeds a hopeless horizon (banking toward a burst that never
  comes), though vs Ponder this deck loses under ANY mode.

## 2026-08-18 (night) — reality check: 1/40 follow-up; day total 12/100 (~era level)
- The record 9/40 was followed by 1/40 on IDENTICAL code. Day total 2/20 +
  9/40 + 1/40 = 12/100 = 12% ~= era baseline. The graduation bar is NOT
  cleared -- the record batch was the right tail of ~12% variance, exactly
  the effect-size trap the owner named this morning (batch statistics
  resolve small planner deltas too slowly; snapshot A/Bs are the instrument).
- Batch-B delta forensics: act-1 deaths 11 -> 19, dominated by Matriarch
  (faced 6 -> 11 = incidence luck; death rate 50% -> 82% vs 32% pre-today
  baseline). Row-by-row check of today's 17 Matriarch fights: modes CORRECT
  (setup_window asleep, race awake); sample deaths are long grind losses on
  low-throughput decks. No behavioral regression found; 12/17 vs 13/40 is
  p~0.01 unadjusted but one of many per-boss comparisons -- WATCH ITEM, not
  a fire. If the elevated Matriarch rate persists next batch, snapshot-A/B
  a Matriarch fight (config-arm: pre-rebuild move_scripts) before touching
  anything.

## 2026-08-19 — post-catalog batches: 6/40, 2/40, 2/40 (10/120); sentinel cluster grows
- Catalog-fix batch hit 6/40 with record composites (act-reach 2.25, elites
  2.1, relics 10.1; Matriarch back to 1/4). The two strength-horizon batches
  came in 2/40 each (4/80) -- weak-evidence low; per the methodology steer,
  no batch-stat conclusions; a snapshot A/B (config-neutralized
  strength_horizon_*) is the instrument if suspicion grows.
- RISKY-SETUP sentinel: 8 KD instances became 11 KD + 1 QUEEN across the
  day. The KD hopeless-horizon proposal (net-of-Ponder ETA; blow past ~8
  turns -> race) sits ready, awaiting the owner's word. First Queen
  instance not yet dissected.
- Drift guard: first firing spurious (top-level-keys bug, fixed 98facef),
  but flushed out 4 REAL discoveries incl. DUAL_WIELD from the Trash Heap
  StS1 pool -- catalog 469, zero misses.
- Process slip x2 (same day): batch launches via shell-& with discarded
  output -- the old silent-launch mistake. Both caught within a minute,
  killed, relaunched tracked. The rule stands: EVERY batch launch goes
  through a tracked background task, no compound-command shortcuts.

## 2026-08-20 — owner-answer sweep + full card audit #2
- Shipped on owner answers: KD hopeless-horizon (cb20386, net-of-Ponder ETA,
  healing bosses only), Inferno/Tear Asunder tags (owner semantics),
  relic-conditional pathing phase 1 (cec4100: Music Box/Courier/Membership
  -> shop, Shovel/Dream Catcher -> rest; Meal Ticket excluded, already in HP
  projection). Off-class policy question ANSWERED from existing code/notes:
  star-cost veto + blessed blind-draft default -- no new policy needed.
- Card audit #2 (12-agent workflow, mistake-class-aware prompt from the
  compiled live-catch corpus + rollout-candidacy re-check per owner):
  209 reward-pool cards audited -> 102 ok / 48 untagged proposals / 59
  change proposals; 9 new-tag asks; 6 rollout mechanism lanes; verifier
  disputes preserved inline. Owner-review doc (items 1-113, reply-by-number
  flow): logs/reports/CARD_AUDIT_2026-08_PROPOSAL.md. Nothing baked until
  review. Decision digest also delivered for the owner's bulk-review
  exercise (1106 decisions / latest 40 runs).
- Batches remain DOWN at owner request.

## 2026-08-23 — first post-audit batch: 5/40; Matriarch normalized; live-catch day
- First batch on the full audit #2 haul (113/113 items, ~50 commits):
  5/40 wins, act-reach 2.05 — era-typical, NO regression from the massive
  tag/parser overhaul (the honest primary question). Matriarch watch item
  RESOLVED: faced 9, died 1 (11%) vs the 73% spike week — the earlier
  cluster reads as deck-power variance, closed.
- Owner live-catch day alongside the review tail: Brightest Flame check
  (draw credit was correctly dead under Fiddle; exposed UNPRICED 'Lose N
  Max HP' + Fiddle-blind opener nudges, both fixed), Vulnerable Potion
  mis-targeting (defensive Beetle Juice rule inherited by an offensive
  potion — now targets the fight-plan kill target), Stampede/Kaiser facing
  trap (long-noted, finally implemented: -14 dock + 0.2x credit in
  back-attack fights), Dominate/Uppercut sequencing check (CLEAN — no
  pre-existing vuln in the tape, and the synthetic conditional case orders
  Uppercut-first correctly).
- Next batch (bjyle284k) carries the live-catch fixes. 3 RISKY-SETUP flags
  this batch, not yet dissected.

## 2026-08-23 (later) — live-catch-fix batch: 1/40 wins BUT record composites
- Strange split: 1/40 wins yet act-reach 2.35 and relics 11.1 (both
  all-time highs), elites 1.9. Runs go DEEP and don't close: the killer
  histogram is an act-3 boss wall -- AEONGLASS x10 (a quarter of the
  batch!), Queen x5, TS x2, vs only 2 act-1 boss deaths. The
  draft/pathing side looks stronger than ever; the closing problem is
  concentrated at Aeonglass specifically. CANDIDATE next lever: Aeonglass
  setup_burst row (currently pure race) or a snapshot A/B on an Aeonglass
  checkpoint -- her superlinear Wither escalation may be exactly the
  hopeless-vs-bank boundary case. One KD RISKY-SETUP flag persists despite
  the net-of-Ponder fix (not yet dissected).
- Process slip #3 (silent batch launch in a compound command) -- caught,
  no stray process, relaunched tracked. The rule is now absolute: batch
  launches get their OWN tool call, nothing appended.

## 2026-08-23 (wrap) — batches stopped at owner request (run 38/40 boundary)
- Final partial batch summary appended below from batch_summary; machine
  handed back clean (no bot processes). Aeonglass loss dossier ready for
  the owner's hands-on session: logs/reports/aeonglass_losses_2026-08-23.md
  (15 losses; pattern: healthy full-HP entries, 18-31 HP front-loaded bleed
  in r1-2 racing into Artifact+Ebb, single-digit HP by r5-8 with the boss
  at 200-400/512; plan=race throughout). Next session plan banked in
  enemy_notes: Aeonglass checkpoint via watcher -> owner plays + bot A/B
  race-vs-setup arms.
