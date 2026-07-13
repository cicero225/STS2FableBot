# Relic Trigger Pass — §8.5.6 (2026-07-13)

The f44 Knights analysis showed trigger relics doing load-bearing work the planner
can't see (Letter Opener, Centennial Puzzle). This pass sweeps all relics the way
ENEMY_PASS/CARD_PASS swept their domains.

## Data

- `scripts/build_relic_catalog.py` → `data/relic_catalog.json`: 180 relics harvested
  from the run-log corpus (live rules text; 172 ever held; 23 with live counters).
- 12-agent audit (wf_d0019428-929) → `data/relic_notes.json`: per-relic class,
  trigger spec, impact/confidence, status.

## Classification

| Class | Meaning | Count |
|---|---|---|
| A | No mid-turn impact — economy/map/pickup one-shots, and crucially anything that materializes as visible status/energy/block in the polled state (start-of-combat buffs, Happy Flower) | 132 |
| B | Mid-turn trigger in the generic vocabulary (per-N-attacks/skills, on-kill, on-exhaust, on-potion, first-HP-loss) | 14 |
| C | Mid-turn/valuation effects needing more than the vocabulary — mostly 4 families (below) | 31 |
| D | Cross-combat counter banking (Pen Nib, Nunchaku, Tuning Fork) | 3 |

## Tranche R1 — SHIPPED 2026-07-13

`RelicTrigger` engine in `policy/combat.py`: per-turn counters are pure functions of
play counts; lifetime counters continue the mod's live relic counter (Pen Nib pattern).
Fired effects flow through existing sim channels (block/energy/draw/Str/Dex/AoE damage
— trigger damage participates in lethality).

Modeled: Ornamental Fan, Shuriken, Kunai, Kusarigama, Daughter of the Wind, Letter
Opener, Lost Wisp, Game Piece, Gremlin Horn, Reptile Trinket, Forgotten Soul, Charon's
Ashes, Centennial Puzzle (armed-at-full-HP approximation), Demon Tongue, Nunchaku,
Tuning Fork (+ Pen Nib pre-existing). Plus two non-trigger passives: **Paper Phrog**
(Vulnerable 75% — rides the Cruelty `vuln_mult_bonus` lane) and **Velvet Choker**
(6-card cap — rides the Ringing/Normality card-cap machinery, swept from relic text).

## Tranche R2 — end-of-turn conditionals — SHIPPED 2026-07-13

Evaluated at the plan's end state inside `_score`: Orichalcum (free 6 block on
blockless turns — the planner stops burning Defends the relic covers), Cloak Clasp
(+1 block per retained card), Sturdy Clamp (10 block of overblock is never waste),
Ice Cream (unspent energy banked, waste penalty waived), Parrying Shield / Screaming
Flagon (end-state damage credits), Pael's Tears / Art of War / Pocketwatch /
Self-Forming Clay (next-turn value credits via w_next_turn_energy/draw).
*Runic Pyramid / Ringing Triangle intentionally skipped*: retention does NOT defuse
Beckon-type stranded penalties (a retained Beckon still fires — it stays in hand),
and no current score term penalizes ordinary discards; nothing to adjust yet.

## Tranche R3 — first-per-combat latches (open, needs arming heuristic)

Vambrace, Unsettling Lamp, Ruined Helmet, Burning Sticks, Permafrost: the mod exposes
no fired-flag; needs a conservative armed-detection (and Vambrace carries a Pen
Nib-style preview-text risk — check live before modeling).

## Bespoke stragglers (open, filed)

Unceasing Top / The Abacus / Biiig Hug (shuffle/hand-empty chains), Mummified Hand /
Razor Tooth (card mutation), Rainbow Ring (compound condition), History Course
(next-turn replay banking), Stone Calendar (turn-7 schedule), Red Skull / Belt Buckle
(threshold flips mid-turn), Lizard Tail (death safeguard — hail-mary interaction).

## Draft-side pointers (from card-pass step 2, for a later draft tranche)

Block-gaining relics feed Juggernaut-class payoffs; per-N-attacks relics (Pen Nib,
Shuriken, Kunai) feed Anger-class attack flooding — relic-aware draft tags.
