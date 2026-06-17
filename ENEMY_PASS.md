# Enemy Mechanics Pass — implementation plan

Owner-requested 2026-06-16; the [PLAN.md](PLAN.md) §8.5 priority-#2 ("all-enemies analysis"),
expanded into its own plan because it's an involved, high-impact piece. Cadence: **bosses first,
batch, then elites, then normals** — not all at once.

## Goal
Make the bot handle each enemy's **mechanics**, not just generic HP/intent stats. The one-turn planner
and the §5-C capability estimate are blind to most enemy statuses/powers, and that blindness is now a
top run-killer: we reliably *reach* the bosses and lose the *fight*. "No longer blind," not "100%
optimal."

## The key enabler (confirmed 2026-06-16)
The mod exposes **enemy status/power descriptions as rules text** in the game state. Lagavulin
Matriarch's Plating arrives as:
`{"id":"PLATING_POWER","name":"Plating","amount":12,"description":"At the end of your turn, gain 12
Block. Plating is reduced by 1 at the start of your turn.",...}`
So most mechanics can be **harvested from our own logs** (every enemy we've fought, with statuses +
intents + HP), the way `card_effects.json` harvests card text. **Online research is the fallback** —
only for what a single observation can't reveal (revive/Adaptable, escalating DoT, phase changes) and
enemies we haven't yet encountered.

## Data layer — the bestiary
- `scripts/build_bestiary.py` → `data/bestiary.json`: per enemy (keyed by name / entity_id), harvest
  **HP range, the act(s) seen in, role (boss/elite/normal), the full status list with descriptions,
  and intent patterns** from `logs/runs/*`. Enemies carry
  `name, hp, max_hp, status[{id,name,amount,description}], intents`.
- Annotate each with its **taxonomy class**, **handling status**, and a free-text note for hidden
  behaviour (researched / owner tooltip). This file is both the source the estimate/planner consult
  *and* the pass's tracking checklist.

## Mechanic taxonomy (how each status/power gets handled)
- **(A) Already modelled** — Strength/Vigor (ramp), Vulnerable/Weak, Minion (flee on leader death),
  Summon (race the leader), Slippery (estimate via `biggest_hit`). *Gap:* several are modelled in the
  **estimate but not the combat planner** (Slippery — the planner still chips it).
- **(B) Extend the estimate + planner** — a generic model + a `FightEnemy` flag covers it:
  block-bypass damage (Soul Fysh status-card), escalating end-of-turn DoT (Slithering Strangler),
  self-block/armor (Plating, Hardened Shell), Intangible (all damage → 1; don't dump burst),
  revive/Adaptable (sum phase HP), Reattach, …
- **(C) Per-enemy handler** — irreducibly bespoke: Ceremonial Beast (Ringing in its low-HP phase →
  one card/turn, play the lethal), multi-phase bosses (Test Subject #C8, Knowledge Demon), Asleep
  (wakes/escalates on hit — attack timing), the Kin priest/follower structure.

Owner steer (do not violate): route decisions through the **capability estimate**, not a pile of
universal micro-rules. Per-enemy handlers are for the genuinely specific only.

## Integration points
1. **Capability estimate (`policy/capability.py`)** — `FightEnemy` already carries `slippery /
   str_ramp / counts_toward_kill / dps`; add flags for the (B) mechanics (block_bypass, dot,
   self_block, intangible, revive-HP) and **detect them from the harvested status descriptions**.
   Also: feed real **per-boss HP/mechanics from the bestiary** in, replacing the rough `_GENERIC_*`
   priors used by the elite gate / drafting.
2. **Combat planner (`policy/combat.py`)** — make per-turn play respect the mechanic: don't chip
   Slippery, don't burst into Intangible, race escalating DoT / ramp, chew armor, play the lethal
   under Ringing. This is the planner finally *consuming* the same enemy knowledge the estimate uses.
3. **Per-enemy handlers** — a small dispatch keyed by enemy id, consulted by the planner, for (C).

## Phasing (bosses first; batch between phases)
- **Phase 0 — infrastructure (no game needed): ✅ done 2026-06-17.** `build_bestiary.py` → 75 enemies
  w/ status text; the 44-status vocabulary classified; `detect_mechanics` parses dmg-cap / self-block
  / death-damage / stun-threshold / thorns / slippery / ramp from the descriptions; `estimate_fight`
  applies them; `bestiary_enemy` builds a per-boss `FightEnemy` (real HP + mechanics); **drafting now
  prices cards vs the *real* upcoming boss** (map.boss cached → bestiary), e.g. multi-hit over a big
  swing vs a Slippery boss. *Open:* the **combat planner** still ignores throttling in-fight (Phase 1),
  and the elite gate still uses the generic elite (the specific elite isn't named on the map node).
- **Phase 1 — Act-1 bosses** (the immediate win; the pool we keep dying to, by death count):
  **Kin** (13), **Vantom** (9 — Slippery), **Ceremonial Beast** (6 — Ringing low-HP), **Soul Fysh**
  (6 — block-bypass card), **Lagavulin Matriarch** (3 — Plating armor), **Kaiser Crab**, **Waterfall
  Giant**. Document → classify → handle → mock-test each, then **batch** (Act-1-boss survival/win-rate
  is the metric). Seeded custom runs give deterministic per-boss A/B.
- **Phase 2 — Act-2/3 bosses:** Knowledge Demon, The Insatiable, Test Subject #C8 (Adaptable), …
- **Phase 3 — Elites:** Bygone Effigy (3), Phrog Parasite (2 — spawns ramping Wrigglers), Terror Eel,
  Decimillipede, Phantasmal Gardeners (hard Undergrowth elite), …
- **Phase 4 — Normals:** scan for unusual mechanics; most are generic — flag the exceptions
  (Slithering Strangler DoT, Ovicopter summon, The Obscura, Fogmog, Nibbits, Overgrowth Crawlers, …).

## Per-enemy workflow (the repeatable unit)
1. **Document** — harvest its statuses/intents/HP from the bestiary; read the mod's descriptions; fill
   hidden / multi-turn behaviour from online research + owner tooltips.
2. **Classify** — taxonomy (A/B/C); name the run-relevant decision the bot currently gets wrong.
3. **Implement** — estimate flag / planner rule / per-enemy handler.
4. **Mock-test** — a constructed `FightEnemy` / combat state asserting the right play (correctness
   without a live harness; the project's mock-first rule).
5. **Confirm live** — a seeded run for that boss (deterministic) and/or a standard batch.

Commit per enemy or per coherent group (FR-3.4 auditability).

## Testing
Mock-first unit tests per mechanic. Live confirmation via **seeded custom runs** (deterministic
per-boss, custom mode now unlocked) — far less noisy than the n=5 standard batches — plus periodic
standard batches for the aggregate boss win-rate. See PLAN §8.3 (seeded-runs harness).

## Definition of done (per phase)
Every enemy in the phase has its **run-relevant** mechanics modelled + a mock test, the bot makes a
defensible play in each fight (verified on a seeded run where possible), and the phase's
death-by-that-enemy rate drops in a batch.

## Tracking & seeds
`data/bestiary.json` doubles as the checklist (handling-status per enemy). The existing PLAN §8.4
notes — Vantom (Slippery), Ceremonial Beast (Ringing), Soul Fysh (block-bypass), Test Subject
(Adaptable), Ovicopter (Summon), Slithering Strangler (DoT) — seed the first entries.

## Status vocabulary — classified (Phase 0, from the 44 harvested)
The harvested statuses cluster into a few mechanic *types*. The dominant one is **damage-throttling**
— the bot wastes burst into caps/block it can't see (the Slippery/Ringing observations generalise).
Highest-impact group to model first, **in the §5-C race estimate** (it changes turns-to-kill):

- **Damage-throttling — burst is wasted:**
  - *Hard per-turn caps:* **Hardened Shell** (≤15 HP lost/turn), **Hard to Kill** (≤9/turn),
    **Intangible** (all damage → 1, 1 turn). → cap my effective damage/turn; **never burst into one**.
  - *Recurring self-block:* **Plating** (+12 Block end of turn, −1/turn), **Skittish** (+6 on first
    hit/turn), **Curl Up** (+14 on first hit). → reduce effective damage; **multi-hit beats first-hit
    block** (same shape as Slippery → reuse `biggest_hit`).
  - *First-hit reduction:* **Slippery** (next HP-loss → 1) — already in the estimate.
- **Ramp (race it / deny the trigger):** **Ritual** (+2 Str/turn), **Territorial** (+1/turn),
  **Vigor** (+6 next attack) → flat `str_ramp`. **Suck/Fossil Stalker** (+3 Str on *unblocked*
  damage) → block to deny. **Crab Rage / Ravenous** (gain on an *ally* death) → don't feed kills.
- **Stun windows — exploit (free enemy turn / phase break):** **Plow** (Ceremonial Beast ≤150 → Stun
  + loses all Strength), **Shriek** (Terror Eel ≤70 → Stun), **Imbalanced** (Bowlbug Rock: fully
  block it → Stun), **Burrowed** (Tunneler: strip its Block → Stun), **Flutter** (5 hits → Stun).
  Pushing past the threshold buys a turn — value it.
- **Retaliation / hit-cost (attacking hurts me):** **Thorns** (5 back per hit → multi-hit is *worse*),
  **Personal Hive** (a Dazed into my draw per hit), **Steam Eruption** (15 self-damage on kill). →
  self-damage cost in the estimate; don't over-multi-hit Thorns.
- **Hard timers (race or lose):** **Sandpit** (eaten/die in 4 turns), **Escape Artist** (flees after
  5 → lose the kill), **Asleep / Slumber** (wake timers — attack-timing).
- **Revive / segments:** **Illusion** (revive full HP — handled), **Reattach** (segment revives 25 HP
  / 2 turns — kill all segments together), **Infested** (death-summon).
- **Debuff-resist:** **Artifact** (negates 2 debuffs → my Vulnerable/Weak may whiff).
- **Not enemy mechanics (ignore):** Dark Shackles, Shackling Potion, Debilitate (these are *our*
  debuffs applied to enemies). **Low combat priority:** Thievery / Heist / Swipe (gold), Back Attack,
  Surprise, Hatch.

**Implication for the estimate (Phase 0c):** extend `FightEnemy` with a small set of generic flags —
`dmg_cap_per_turn`, `block_per_turn` (regen), `thorns`, `death_damage`, plus a `stun_threshold`
(HP at which it loses a turn) — detected from these status descriptions in the harvest. That one set
covers most bosses; the bespoke ones (multi-phase, Sandpit timer, Ringing) stay per-enemy handlers.
