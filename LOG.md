# Lab Notebook

*Newest first. One entry per live session / milestone (see PLAN.md §6).*

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
