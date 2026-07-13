# Card Pass Step 2 — DRAFT-pass proposal (OWNER REVIEW — nothing here is live)

Produced by the 12-agent audit of all 157 draftable Ironclad/colorless cards
(2026-07-12, workflow wf_1c79ed42-a44). Verdicts: 86 CTX, 7 SPECIAL, 3 SCALE, 61 OK.

## Proposed machinery (one mechanism, not 93 micro-rules)

1. **Tag table** `data/card_draft_tags.json` (written, unconsumed): per card,
   `provides`/`needs` archetype tags. Starter cards are tagged too (Bash provides
   `vulnerable_source`), so enabler counts see the starting deck.
2. **Two generic scorer rules** in `_card_score`:
   - `enabler_present`: a needs-tag with zero deck providers -> dock (strength-scaled);
     one-or-more providers -> neutral or small bonus.
   - `density_threshold`: needs-tag counting deck providers against a threshold
     (e.g. Vicious wants >=2 vulnerable_sources); smooth, not cliff.
3. **Copy caps / anti-synergy** as a small third rule (second Barricade class).
4. **Depth-caution**: SCALE cards (Demon Form, Juggernaut, Rupture-class engines) are
   flagged and exempt from global docks per the standing 8.1 rule.

Magnitudes below are hints (mild/moderate/strong), to be mapped to 2-3 config weights
-- not per-card numbers. Impact/conf are the audit's estimates.

## Review log (owner, 2026-07-12)

**Vulnerable package — approved with three refinements:**
1. *Magnitude-weighted sources* (Bully): tag table carries stack weights
   (`vulnerable_source: 2` for Bash, 3 for Tremble), density rules count weighted
   stacks, not cards. Owner left feasibility to implementer judgment — it is cheap.
2. *Self-provision* (Dominate): when evaluating `needs`, the candidate card counts
   itself as a deck member. Any self-providing card keeps baseline value and its
   conditional becomes bonus-only. Also: Dominate's Strength payload synergizes with
   multi_hit (Twin Strike class) — reflected in the Strength package both ways.
3. *Chicken-and-egg principle (structural, applies to ALL packages)*: unmet-PENALTIES
   are reserved for pure payoffs (Vicious/Rupture/Forgotten Ritual class — near-blank
   without support). Enabler-side cards with decent baseline value (Dominate, Tremble)
   are BONUS-ONLY — speculatively pickable to seed the archetype while Bash-class
   starter sources remain. The audit's Tremble penalty row is overridden accordingly.

**Exhaust package — owner refinements (Brand / Burning Pact / True Grit):**
4. *Controlled exhaust = thinning value in its own right.* Exhausting Strikes/Defends is
   itself valuable, and StS's draw-5/3-energy pattern blunts the "card disadvantage"
   argument. New tag `controlled_exhaust` (Brand, Burning Pact — cards that CHOOSE the
   exhaust target, vs random/awkward exhausters like base True Grit, Thrash, Cinder):
   mild-to-moderate bonus scaled by thinnable-basics count (Strikes/Defends remaining —
   already computed for the weak-deck threshold) and damped when the deck already has
   deck_thinning. The audit's Brand row ("raw card disadvantage" without payoffs) is
   overridden: baseline thinning value stands in basic-heavy decks.
5. *Upgrade-awareness (True Grit)*: the upgrade makes the exhaust targeted — a class
   jump, not a stat bump. Mechanism: a per-card `upgrade_unlocks` flag -> mild
   anticipation bonus when offered unupgraded (campfire upgrade makes it controlled),
   full controlled_exhaust treatment when offered/held upgraded. True Grit+ is
   "definitely takeable" (owner).

**Attack-density package — owner refinements:**
6. *Stampede*: also improves with high-cost/high-damage attacks (free end-of-turn play
   of what you couldn't afford) — bonus keys on big/expensive attacks too, not just
   attack fraction. Upgrade (2 -> 1 energy) is a considerable jump: upgrade-aware note.
7. *Thrash (audit overridden)*: big_single_hit attacks are GREAT fodder (exhaust a
   30-damage attack -> next Thrash deals 34x2), not a hazard. Real cautions: attacks
   with riders/accumulators (early Ashen Strike) get eaten, and large decks without
   tutors rarely redraw Thrash in time -> dock scales with deck size.
8. *Aggression*: attack QUALITY over quantity — repeatedly returning one premium attack
   is enough if the deck is energy-rich or the attack is 0-cost. Density threshold
   softened; quality/energy condition instead.
9. *Cascade*: also value the deck's energy-cost profile — expensive cards that "scoot
   out of the way" after autoplay (powers, Exhaust cards) make X-autoplay safer/better.
10. *Cloak and Dagger*: Silent card — analysis fine for Ironclad exposure, flawed if
    ever scored for Silent. Caveat noted for future character support.
11. *Havoc (audit partially overridden)*: playing a Power via Havoc is FINE — powers
    vanish on play, nothing is exhausted. Remaining caution is situational skills only;
    synergy note: card generation pairs well.

**Owner question, answered**: yes — all conditionals land ON TOP of the existing score
(rarity base + Spirebird prior + planner-blind dock + cost/deck-size penalties +
capability delta). They are additive adjustments, not replacements.

**Block package — owner refinements:**
12. *Juggernaut*: block-gaining RELICS make it better than it looks (defer full
    relic-card interaction modeling to the relic pass, but remember it there). Also:
    per-proc autoblock counts — Plating and Feel No Pain's block each trigger it every
    proc, so block_engine counting must include recurring autoblock sources, which are
    high-frequency triggers, not one block card.
13. *Prolong (audit factually overridden)*: does NOT need surplus block standing at end
    of turn — it snapshots current Block when played; even if the enemy then consumes
    the block, next turn still grants the snapshot (owner example: 10 block -> Prolong
    -> hit for 10 -> still +10 next turn). Condition softens to "deck produces a decent
    block turn at all" — near-dead penalty removed.
14. *Speculative window (extends the chicken-and-egg principle to PAYOFFS)*: cards like
    Rupture and Unmovable are literally nothing alone yet often worth taking in Act 1
    anyway — the deck is still malleable and enablers arrive later. Unmet-penalties on
    pure payoffs get an ACT-1 DISCOUNT (mild early, full strength Act 2+). Spirebird
    priors may partly cover this, but the act-scaling makes it explicit.

**Other groups — owner refinements:**
15. *Armaments*: upgrades to "Upgrade ALL cards in your hand" — pro advice: generally
    only worth picking AS Armaments+ (slow otherwise). Joins the upgrade_unlocks set
    (True Grit, Stampede, Apotheosis: 2 -> 1 energy on upgrade).
16. *Perfected Strike*: strike_name counting must include ALL cards with "Strike" in
    the name (Pommel/Twin/Setup/Seeker/Ultimate/Leading Strike, itself) — name-contains
    count, not just starter Strikes.
17. *Fasten*: good early power, priors should carry it. Subnote — its PRESENCE makes
    removing Defends worse: removal-target scoring should read the tag table (Fasten
    provides a basic-Defend payoff -> Defends stop being removal fodder). Same
    machinery, applied to removal policy instead of drafting.
18. *Hellraiser*: better with strong card draw (draw_engine bonus); boss-dependent
    hazard — random Strike autoplay is dangerous vs Kaiser Crab (back-attack punish).
19. *Anger*: relic-pass pointer #2 — per-N-attacks relics (Pen Nib class) synergize
    with attack-copy flooding.
20. *Mayhem*: softened — unplayable curses are harmless via Mayhem (played -> just
    discarded); the caution is only genuinely situational cards (defensive timing).
21. *Feed*: step-1 audit confirms the on-fatal rider is invisible to the planner (plays
    it as a plain 10-damage exhaust; never sequences it as the killing blow). Open
    C-class item with a proposal — queue as a quick single alongside step-2 work.

## Vulnerable package (9 cards)

| Card (rarity/cost) | Text | Proposed conditional | Strength | Impact/Conf |
|---|---|---|---|---|
| Bully (U/0) | Deal 4 damage. Deals 2 additional damage for each Vulnerable on the enemy. | Value scales with vulnerable_source count: near-dead at 0 sources (0-cost 4 damage), fine at 1 (starter Bash), strong at >=2 stacking sources; bonus grows with density | strong | high/high |
| Colossus (U/1) | Gain 5 Block. You receive 50% less damage from Vulnerable enemies this turn. | Penalty when deck has no vulnerable_source beyond nothing; scales up with vulnerable_source density since '50% less damage from Vulnerable enemies this turn' needs vuln uptime on the turns you defend | moderate | high/high |
| Dominate (U/1) | Apply 1 Vulnerable. Gain 1 Strength for each Vulnerable on the enemy. Exhaust. | Bonus scales with other vulnerable_source density ('gain 1 Strength for each Vulnerable on the enemy' counts stacks from the whole deck) and with vulnerable_payoff/attack density to spend the Strength; playable baseline, so bonus-only | moderate | high/high |
| Vicious (U/1) | Whenever you apply Vulnerable, draw 1 card. | gate on count of vulnerable_source cards in deck (Bash, Taunt, Uppercut, ...): strong penalty below 2 sources, scaling bonus at 3+; the power is a blank without triggers | strong | high/high |
| Dismantle (U/1) | Deal 8 damage. If the enemy is Vulnerable, hits twice. | Penalty when deck has no reliable vulnerable_source: 'If the enemy is Vulnerable, hits twice' is binary, so it needs vuln uptime, not stacks; bonus once >=1-2 sources present | moderate | med/high |
| Molten Fist (C/1) | Deal 10 damage. Double the enemy's Vulnerable. Exhaust. | 'Double the enemy's Vulnerable' is zero without another vulnerable_source already applying it (Bash, Thunderclap, Tremble, Falling Star) — penalty if deck has no other vulnerable_source; extra bonus if a vulnerable_payoff (Cruelty, Bully) is also present, since doubling stacks feeds them. | strong | med/high |
| Tremble (C/1) | Apply 3 Vulnerable. Exhaust. | penalty unless deck has >=1 vulnerable_payoff or meaningful attack damage density (big_single_hit / multi_hit) to amplify; a no-damage exhausting debuff in a damage-poor deck is a wasted slot | moderate | med/high |
| Cruelty (R/1) | Vulnerable enemies take an additional 25% damage. | bonus only if deck has >=2 vulnerable_source cards (or one high-uptime/AoE source); otherwise the multiplier has too little uptime to justify a power slot | strong | low/high |
| Debilitate (U/1) | Deal 10 damage. Vulnerable and Weak are twice as effective against the enemy for the next 2 turns. | Strong penalty when deck has no vulnerable_source (and ideally weak sources) -- without debuffs to double, it is a below-rate 1-cost 10 damage; bonus scales with debuff density | strong | low/high |

## Exhaust package (16 cards)

| Card (rarity/cost) | Text | Proposed conditional | Strength | Impact/Conf |
|---|---|---|---|---|
| Ashen Strike (U/1) | Deal 6 damage. Deals 3 additional damage for each card in your Exhaust Pile. | bonus scaled by count of exhaust_enabler cards in deck (self-exhausting cards, Stoke, Thrash, Shiv generators); penalty when deck has 0 exhaust_enablers — it is then a below-rate attack | strong | high/high |
| Evil Eye (U/1) | Gain 8 Block. Gain another 8 Block if you have Exhausted a card this turn. | penalty unless deck has >=1 reliable exhaust_enabler that fires before/with block plays (True Grit, Second Wind, Fiend Fire, Burning Pact, self-exhausting skills) — otherwise the second 8 Block never triggers and the card is a Defend | moderate | high/high |
| Forgotten Ritual (U/1) | If you Exhausted a card this turn, gain [ironclad_energy_icon.png][ironclad_energy_icon.png][ironclad_energy_icon.png]. Exhaust. | penalty unless deck has >=2 exhaust_enabler / self-Exhaust cards (the condition must be satisfied BEFORE playing it in the same turn, so a single enabler rarely lines up) — unmet it is a dead card that exhausts itself for zero effect | strong | high/high |
| Second Wind (U/1) | Exhaust all non-Attack cards in your Hand. Gain 5 Block for each card Exhausted. | bonus when deck has >=1 exhaust_payoff card or is status/curse-heavy (fodder); mild penalty in decks whose plan depends on playing their skills | moderate | high/med |
| Brand (R/0) | Lose 1 HP. Exhaust 1 card. Gain 1 Strength. | bonus only if deck has >=1 exhaust_payoff (refunds the exhausted card) or multi_hit attacks to cash Strength; without either, 'Exhaust 1 card' per play is raw card disadvantage | moderate | med/high |
| Burning Pact (U/1) | Exhaust 1 card. Draw 2 cards. | Bonus when deck has >=1 exhaust_payoff (Dark Embrace / Feel No Pain-style) or curses/statuses worth burning; baseline it is still acceptable 1-cost draw | mild | med/high |
| Dark Embrace (R/2) | Whenever a card is Exhausted, draw 1 card. | bonus only if deck has >=3 exhaust_enabler / Exhaust-keyword cards that fire in normal play; strong penalty when the deck exhausts nothing | strong | med/high |
| Feel No Pain (U/1) | Whenever a card is Exhausted, gain 3 Block. | penalty unless deck has >=2 cards tagged exhaust_enabler or self-Exhaust (volume matters — one trigger per combat is not worth a power slot); bonus scales with exhaust density | strong | med/high |
| Fiend Fire (R/2) | Exhaust your Hand. Deal 7 damage for each card Exhausted. Exhaust. | bonus when deck has >=1 exhaust_payoff or a draw_engine that reliably fills the hand; base score otherwise (do not dock — the nuke is playable anywhere) | mild | med/high |
| Pact's End (R/0) | If you have 3 or more cards in your Exhaust Pile, deal 17 damage to ALL enemies. | bonus only if deck has >=4 exhaust_enabler / self-Exhausting cards (so the pile plausibly reaches 3 by mid-fight); strong penalty below ~3 such cards | strong | med/high |
| Stoke (R/1) | Exhaust your Hand. Add 1 random card into your Hand for each card Exhausted. | bonus only if deck has >=1 exhaust_payoff (e.g. Ashen Strike) or other exhaust-count scaler; otherwise the random-replacement gamble does not earn a Rare slot | moderate | med/high |
| True Grit (C/1) | Gain 7 Block. Exhaust 1 card at random. | bonus if deck has >=1 exhaust_payoff OR is basic-heavy (random exhaust = thinning); mild penalty in a small, refined deck with no exhaust payoffs where random exhaust eats good cards | moderate | med/high |
| Cinder (C/2) | Deal 18 damage. Exhaust 1 card at random. | 'Exhaust 1 card at random' makes every play an exhaust trigger: bonus when the deck has >=1 exhaust_payoff (Dark Embrace, Ashen Strike, Pact's End); mild secondary bonus in basics-heavy decks where random exhaust is effectively thinning; mild caution when the deck carries singleton combo pieces the random exhaust can eat. | mild | med/med |
| Drum of Battle (U/1) | Draw 2 cards. When this card is Exhausted, gain [ironclad_energy_icon.png][ironclad_energy_icon.png]. | bonus if deck has >=1 exhaust_enabler that can exhaust cards from hand (True Grit, Second Wind, Fiend Fire, Cinder, Thrash) — the 'when Exhausted, gain [E][E]' rider needs an external exhauster | mild | low/high |
| Bombardment (R/3) | Deal 18 damage. At the start of your turn, if this is in your Exhaust Pile, play it. Exhaust. | bonus if deck has >=1 exhaust_payoff or exhaust_enabler — the per-turn self-Exhaust triggers payoffs every turn, and enablers put it into the loop without paying its 3 cost | moderate | low/med |
| Howl from Beyond (U/3) | Deal 16 damage to ALL enemies. At the end of your turn, if this is in your Exhaust Pile, play it. | Bonus if deck has >=1 exhaust_enabler (can put it in the Exhaust Pile without paying its 3-cost cast); still playable standalone, so no dock when unmet. | moderate | low/med |

## Attack-density package (17 cards)

| Card (rarity/cost) | Text | Proposed conditional | Strength | Impact/Conf |
|---|---|---|---|---|
| Expect a Fight (U/2) | Gain [ironclad_energy_icon.png] for each Attack in your Hand. You cannot gain additional [ironclad_energy_icon.png] this turn. | penalty unless deck attack density is high (roughly >=50% Attacks, so expected hand holds 3+); additional mild anti_synergy dock when deck already relies on other energy_source cards, since 'cannot gain additional [E] this turn' locks them out | strong | high/high |
| Rage (U/0) | Whenever you play an Attack this turn, gain 3 Block. | penalty unless deck has high cheap-Attack density (>= ~50% Attacks with several 0-1 cost ones, so 3+ attacks/turn is routine) | moderate | high/high |
| Stampede (U/2) | At the end of your turn, 1 random Attack in your Hand is played against a random enemy. | penalty unless deck Attack fraction is high (>= ~55%) so an unplayed Attack is usually left in hand at end of turn | moderate | high/high |
| Thrash (R/1) | Deal 4 damage twice. Exhaust a random Attack in your Hand and add its damage to this card. | bonus when deck has >=4 cheap/low-value attacks as exhaust fodder; penalty when attacks are few or premium (random exhaust can hit a key attack) | moderate | high/med |
| Juggling (U/1) | Add a copy of the third Attack you play each turn into your Hand. | Penalty unless deck clears an attack-density threshold (roughly half the deck cheap attacks, or attack_generator present) so that 3 attacks/turn is routine; bonus scales with the quality of the attack being copied. | moderate | med/high |
| Pillage (U/1) | Deal 6 damage. Draw cards until you draw a non-Attack card. | bonus when deck Attack fraction is high (>= ~55% Attacks); baseline is already a playable 1-cost cantrip so no penalty when unmet | mild | med/high |
| Stomp (U/3) | Deal 12 damage to ALL enemies. Costs 1 less [ironclad_energy_icon.png] for each Attack played this turn. | bonus when deck has high cheap-Attack density (2+ attacks/turn routine, making effective cost <=1); offsets the flat cost>=3 dock which misprices its self-discount | moderate | med/high |
| Aggression (R/1) | At the start of your turn, put a random Attack from your Discard Pile into your Hand and Upgrade it. | bonus only if Attack fraction of deck is high (>= ~40%) with non-basic attacks worth upgrading/replaying; penalty in skill/power-heavy decks where the discard rarely holds a good Attack | moderate | med/med |
| Bolas (R/0) | Deal 3 damage. At the start of your next turn, return this to your Hand. | bonus only if deck has >=1 strength_source or attack_density_payoff (Envenom, Aggression, ...) — a recurring free attack multiplies those; without either it is 3-damage filler occupying a hand slot each turn | moderate | low/med |
| Cascade (R/X) | Play the top X cards of your Draw Pile. | bonus only if deck is dense in unconditionally-good autoplays (high Attack fraction, few situational/X-cost/defensive-timing cards); penalty otherwise | moderate | low/med |
| Cloak and Dagger (C/1) | Gain 6 Block. Add 1 Shiv into your Hand. | Bonus only if deck has >=1 per-attack payoff (attack_density_payoff / vulnerable_payoff amplifiers like Envenom 'Whenever an Attack deals unblocked damage', or exhaust_payoff counters like Pact's End / Ashen Strike that Shivs feed since Shivs self-Exhaust). Without a payoff it is a below-rate Defend. | mild | low/med |
| Havoc (C/1) | Play the top card of your Draw Pile and Exhaust it. | 'Play the top card of your Draw Pile and Exhaust it' — value tracks the average value of a random deck card. Bonus only when deck is attack-dense (roughly >=60% attacks, ideally expensive ones); penalty when deck carries Powers or situational skills, since playing-and-exhausting a Power or a dead skill is a disaster. | moderate | low/med |
| Metamorphosis (E/2) | Add 3 random Attacks into your Draw Pile. They're free to play this combat. Exhaust. | bonus when deck attack density is LOW (damage-starved deck gets a free damage battery); no bonus in attack-dense decks | mild | low/med |
| Primal Force (R/0) | Transform all Attacks in your Hand into Giant Rock. | bonus only if deck has >=5 low-value attacks (Strikes/commons) that upgrade into Giant Rock; mild penalty when the deck's attacks are mostly rare/scaling (transforming them is a downgrade) | moderate | low/med |
| Setup Strike (C/1) | Deal 7 damage. Gain 2 Strength this turn. | bonus only if deck has >=2 multi_hit cards or high attack density (enough same-turn attacks to convert 'Strength this turn' into damage) | mild | low/med |
| Up My Sleeve (U/2) | Add 3 Shivs into your Hand. Reduce this card's cost by 1. | bonus when deck has >=1 strength_source or attack-count payoff (each Shiv is a separate Attack play/hit); baseline rate without them is below par | moderate | low/med |
| Rattle (U/1) | Osty deals 7 damage. Hits an additional time for each other time he has attacked this turn. | penalty unless deck has >=2 other companion_attack (Osty-attacking) cards so multi-Osty-attack turns actually happen | strong | low/low |

## Self-HP-loss package (2 cards)

| Card (rarity/cost) | Text | Proposed conditional | Strength | Impact/Conf |
|---|---|---|---|---|
| Spite (U/0) | Deal 5 damage. If you lost HP this turn, hits 2 times. | penalty unless deck has >=1 self_hp_loss_source; without one it is only a 0-cost 5-damage filler and rarely worth the reward slot | moderate | high/high |
| Rupture (U/1) | Whenever you lose HP on your turn, gain 1 Strength. | strong penalty unless deck has >=1 self_hp_loss_source (scaling bonus at >=2); the power is inert without them | strong | med/high |

## Strength package (10 cards)

| Card (rarity/cost) | Text | Proposed conditional | Strength | Impact/Conf |
|---|---|---|---|---|
| Conflagration (R/1) | Deal 2 damage to ALL enemies 4 times. | bonus if deck has >=1 strength_source — per-hit-per-enemy scaling multiplies Strength ~4x per target; baseline without it is merely decent AoE | moderate | med/high |
| Whirlwind (U/X) | Deal 5 damage to ALL enemies X times. | bonus when deck has >=1 strength_source or energy_source (both multiply X-cost multi-hit output); without either, discount toward plain small-AoE value rather than full aoe bonus | moderate | med/high |
| Peck (E/1) | Deal 2 damage 3 times. | bonus only if deck has >=1 strength_source (Demon Form, Brand, ...) — per-hit damage triples Strength value; without one it is sub-Strike filler | moderate | low/high |
| Sword Boomerang (C/1) | Deal 3 damage to a random enemy 3 times. | bonus only if deck has >=1 strength_source (Demon Form, Brand, Setup Strike...); without one it is below-rate damage | moderate | low/high |
| Celestial Might (C/2) | Deal 6 damage 3 times. | 'Deal 6 damage 3 times' (4 times upgraded): each point of Strength is multiplied by hit count, so bonus when the deck has >=1 strength_source (Demon Form, Brand, Setup Strike); at 18-for-2 baseline it is merely average without one. | mild | low/med |
| Exterminate (E/1) | Deal 3 damage to ALL enemies 4 times. | bonus if deck has >=1 strength_source (4 hits per enemy quadruple every point of Strength) | moderate | low/med |
| Fisticuffs (U/1) | Deal 7 damage. Gain Block equal to damage dealt. | bonus if deck has >=1 strength_source (or vulnerable_source density) — the block-equals-damage clause double-counts every point of Strength | mild | low/med |
| Omnislice (U/0) | Deal 8 damage. Damage ALL other enemies equal to the damage dealt. | Bonus if deck has >=1 strength_source (Strength is applied to the base hit and mirrored to ALL other enemies); baseline 0-cost AoE value stands otherwise. | mild | low/med |
| Twin Strike (C/1) | Deal 5 damage twice. | small bonus if deck has >=1 strength_source or a strike_name payoff (Perfected Strike, Hellraiser) | mild | low/med |
| Volley (U/X) | Deal 10 damage to a random enemy X times. | bonus when deck has energy_source (X-cost needs surplus energy) or strength_source (per-hit multiplier); at base 3 energy with no Strength it is fair-rate at best and random-target besides | moderate | low/med |

## Block package (5 cards)

| Card (rarity/cost) | Text | Proposed conditional | Strength | Impact/Conf |
|---|---|---|---|---|
| Body Slam (C/1) | Deal damage equal to your Block. | 'Deal damage equal to your Block' is near-zero without block already on board when played: needs high block_engine density (big-block cards like Blood Wall/Impervious, or a block power) and is best with Barricade-style retention. Strong penalty when deck block output is low; bonus when block_engine density is high or Barricade/Juggernaut-class block payoff shell exists. | strong | med/high |
| Juggernaut (R/2) | Whenever you gain Block, deal 6 damage to a random enemy. | bonus only if deck has >=5 block_engine sources (block-granting cards or per-turn block powers); penalty when block density is low | moderate | med/high |
| Barricade (R/3) | Block is not removed at the start of your turn. | bonus only if deck has >=2 block_engine sources producing surplus block to carry over; hard penalty if a copy is already owned (copy_cap: 2nd Barricade is dead — effect does not stack) | strong | low/high |
| Prolong (U/0) | Next turn, gain Block equal to your current Block. Exhaust. | penalty unless deck has >=2 block_engine cards (needs surplus Block standing at end of turn to copy); near-dead card otherwise | strong | low/high |
| Unmovable (R/2) | The first time you gain Block from a card each turn, double the amount gained. | bonus only if deck has >=1 large single-instance block card (>=10 block from one play, i.e. a block_engine); starter Defends alone do not justify it | moderate | low/high |

## Other: density_threshold (9 cards)

| Card (rarity/cost) | Text | Proposed conditional | Strength | Impact/Conf |
|---|---|---|---|---|
| Bloodletting (C/0) | Lose 3 HP. Gain [ironclad_energy_icon.png][ironclad_energy_icon.png]. | 'Gain [energy][energy]' needs sinks: bonus when the deck has >=3-4 cards costing 2+ (or X-cost); in a deck of cheap cards the energy is often wasted and the card is 'Lose 3 HP, do nothing'. Secondary: it is a premier enabler for self_hp_loss_payoff cards, so their presence adds bonus too. | moderate | high/high |
| Armaments (C/1) | Gain 5 Block. Upgrade a card in your Hand. | 'Upgrade a card in your Hand' is only worth a slot while the deck still contains many unupgraded cards (roughly >=8); as smith/event upgrades accumulate the rider becomes blank and the card is a weak Defend. Penalty when unupgraded-card density is low (typical Act 2+). | moderate | med/high |
| Perfected Strike (C/2) | Deal 6 damage. Deals 2 additional damage for ALL your cards containing “Strike”. | 'Deals 2 additional damage for ALL your cards containing "Strike"' — bonus when deck has >=5 strike_cards (starter Ironclad qualifies: 5 Strikes + itself = ~18 damage for 2 early), penalty below that. Anti-synergy: any deck_thinning plan that removes Strikes decays it, so dock it when a thinning strategy is active. | moderate | med/high |
| Apotheosis (A/2) | Innate. Upgrade ALL your cards. Exhaust. | Bonus proportional to count of unupgraded non-Basic cards in deck (strong at >=8 unupgraded); fade toward zero as the deck approaches fully-upgraded. Deck-property scan, same machinery class as the deck_size penalty. | strong | low/high |
| Crescent Spear (C/1) | Deal 8 damage. Deals 2 additional damage for ALL your cards that have a [star_icon.png] cost. | 'Deals 2 additional damage for ALL your cards that have a [star] cost' — bonus scales with count of star-cost cards in deck; with 0 it is a vanilla 8-damage 1-cost. Penalty unless deck has >=3 star_cost_source cards (a Regent/Venerate-archetype resource the Ironclad pool basically never supplies). | strong | low/high |
| Fasten (U/1) | Gain an additional 4 Block from Defend cards. | penalty unless deck retains >=4 Defend cards (basic_defend_density); also anti_synergy with deck_thinning — planned Defend removals erase the power's payload | strong | low/high |
| Hellraiser (R/2) | Whenever you draw a card containing “Strike”, it is played against a random enemy. | bonus only if deck has >=4 cards with 'Strike' in the name AND deck is not on a thinning plan; strong penalty below ~3 Strikes (near-dead Power) | strong | low/high |
| Panache (U/0) | Every time you play 5 cards in a single turn, deal 10 damage to ALL enemies. | Penalty unless deck can routinely play 5+ cards a turn: needs draw_engine or energy_source present, or a high density of 0-cost cards. | moderate | low/high |
| Automation (U/1) | Every 10 cards you draw, gain [colorless_energy_icon.png]. | Bonus only when deck has >=2 draw_engine cards (Battle Trance, Burning Pact, Pommel-style riders); penalty otherwise | moderate | low/med |

## Other: deck_size (4 cards)

| Card (rarity/cost) | Text | Proposed conditional | Strength | Impact/Conf |
|---|---|---|---|---|
| Anger (C/0) | Deal 6 damage. Add a copy of this card into your Discard Pile. | 'Add a copy of this card into your Discard Pile' grows the deck every play, permanently. Penalty when deck is already over ~25 cards or has high power_setup/draw_engine density (consistency decks that need to find specific cards); no penalty in lean, front-loaded aggressive decks where extra 0-cost 6s are pure upside. | mild | med/high |
| Rampage (U/1) | Deal 9 damage. Increase this card's damage by 5 this combat. | bonus when deck is small (<= ~18 cards) or has >=2 draw_engine cards (replays per combat are what the +5/hit cashes in) | mild | med/high |
| Mind Blast (U/1) | Innate. Deal damage equal to the number of cards in your Draw Pile. | Bonus in large decks (roughly 25+ cards) and when no deck_thinning strategy is active; penalty in small/thinning decks where draw pile empties. | moderate | low/high |
| Stratagem (U/1) | Whenever you shuffle your Draw Pile, choose a card from it to put into your Hand. | value scales with shuffle frequency: bonus in thin decks (roughly <20 cards) or with deck_thinning/draw_engine density in deck; penalty in large decks that rarely shuffle | moderate | low/med |

## Other: anti_synergy (5 cards)

| Card (rarity/cost) | Text | Proposed conditional | Strength | Impact/Conf |
|---|---|---|---|---|
| Battle Trance (U/0) | Draw 3 cards. You cannot draw additional cards this turn. | Mild dock when deck already holds >=2 other draw_engine cards -- the 'cannot draw additional cards this turn' rider turns off any draw played after it, so stacked draw packages collide | mild | med/high |
| The Gambit (R/0) | Gain 50 Block. If you take unblocked attack damage this combat, die. | never-draft while the play-planner gates self-death-rider cards to never-play (existing self_death_rider -> -100 gate in _card_score already implements this) | strong | low/high |
| Catastrophe (U/2) | Play 2 random cards from your Draw Pile. | Dock when deck contains statuses/curses or planner-marked never-play/situational cards that 'Play 2 random cards from your Draw Pile' can hit; bonus side (dense expensive attacks) left to the prior | moderate | low/med |
| Mayhem (R/2) | At the start of your turn, play the top card of your Draw Pile. | penalty when deck contains curses/statuses or planner-flagged never-play / bad-random-play cards; mild bonus in small (<20) decks of uniformly playable cards | moderate | low/med |
| Panic Button (U/0) | Gain 30 Block. You cannot gain Block from cards for 2 turns. Exhaust. | penalty when deck has >=2 block_engine cards (per-turn block plans get locked out for 2 turns by this card); neutral-to-mild-bonus otherwise | moderate | low/med |

## Other: act_time (2 cards)

| Card (rarity/cost) | Text | Proposed conditional | Strength | Impact/Conf |
|---|---|---|---|---|
| Feed (R/1) | Deal 10 damage. If Fatal, raise your Max HP by 3. Exhaust. | value decays with remaining run length: full bonus in Act 1, taper to near-zero rider value by Act 3 (the 10-damage Exhaust body alone is below rare rate) | moderate | med/high |
| Dramatic Entrance (U/0) | Innate. Deal 11 damage to ALL enemies. Exhaust. | Bonus in Act 1 (and vs multi-enemy hallway profiles) where a guaranteed turn-1 11-to-ALL swings fights; value fades in later acts as one-shot 11 damage stops mattering | mild | low/high |

## Other: enabler_present (12 cards)

| Card (rarity/cost) | Text | Proposed conditional | Strength | Impact/Conf |
|---|---|---|---|---|
| Inflame (U/1) | Gain 2 Strength. | Mild bonus if deck has multi_hit or high attack count (Strength triggers per hit); baseline value stands regardless on an attack-heavy deck, so no penalty when unmet. | mild | med/high |
| Envenom (R/2) | Whenever an Attack deals unblocked damage, apply 1 Poison. | bonus only if deck has >=2 multi_hit attacks (per-hit trigger); penalty in big-single-hit decks where a 2-cost power buys ~1 Poison per turn | moderate | low/high |
| Lethality (U/1) | Ethereal. The first Attack each turn deals 50% additional damage. | Penalty unless deck has >=1 big_single_hit attack to amplify (the % rider needs a large base hit to beat a card slot, given Ethereal). | moderate | low/high |
| Mirage (U/1) | Gain Block equal to Poison on ALL enemies. Exhaust. | Near-zero value unless deck has >=1 poison_source; scales well only in a dedicated poison deck (unlikely on Ironclad). | strong | low/high |
| One-Two Punch (R/1) | This turn, your next Attack is played an extra time. | bonus only if deck has >=1 big_single_hit attack (or a multi_hit heavy) worth copying; penalty when the deck's best attack is small | moderate | low/high |
| Cosmic Indifference (C/1) | Gain 6 Block. Put a card from your Discard Pile on top of your Draw Pile. | Bonus only if deck has >=1 premium recursion target (big_single_hit or a key combo/engine card worth replaying). Without one it is a 1-cost 6-block skill, strictly worse than the block commons. | mild | low/med |
| Equilibrium (U/2) | Gain 13 Block. Retain your Hand this turn. | bonus if deck has >=1 big_single_hit / cost>=3 card worth banking across turns — retain-hand is the card's real value over a plain block skill | mild | low/med |
| Hailstorm (U/1) | At the end of your turn, if you have Frost, deal 6 damage to ALL enemies. | Near-zero value unless deck has >=1 frost_source; with Frost reliably up it's a strong repeating AoE engine. | strong | low/med |
| Headbutt (C/1) | Deal 9 damage. Put a card from your Discard Pile on top of your Draw Pile. | Bonus only if deck has >=1 premium recursion target (big_single_hit or key exhaust-free combo card) — 'Put a card from your Discard Pile on top of your Draw Pile' is the whole reason to draft it. Without a target it is a vanilla 1-cost 9-damage attack. | mild | low/med |
| Unrelenting (U/2) | Deal 14 damage. The next Attack you play costs 0 [ironclad_energy_icon.png]. | bonus only if deck has >=1 attack costing 2+ (big_single_hit / costly attacks) for the 'next Attack costs 0' rider to discount; without one it is a below-rate 2-cost attack | mild | low/med |
| Collision Course (C/0) | Deal 11 damage. Add a Debris into your Hand. | Small bonus if deck has >=1 status_cards_payoff (Debris becomes fuel instead of a tax). No penalty otherwise — the base rate carries it. | mild | low/low |
| Snap (C/1) | Osty deals 7 damage. Add Retain to a card in your Hand. | penalty unless deck/class provides a summon_source (Osty must exist for 'Osty deals X damage' to function) | moderate | low/low |

## Other: boss_dependent (2 cards)

| Card (rarity/cost) | Text | Proposed conditional | Strength | Impact/Conf |
|---|---|---|---|---|
| Dark Shackles (U/0) | Enemy loses 9 Strength this turn. Exhaust. | Bonus when the upcoming boss/elite profile ramps or carries high Strength (bestiary str_ramp / high-attack scalers); near-zero value vs non-attacking or flat-damage fights | moderate | low/med |
| Mangle (R/3) | Deal 15 damage. Enemy loses 10 Strength this turn. | bonus when the upcoming boss is a Strength-ramper or heavy multi-hit attacker (the -Strength turn is worth ~a full block turn); otherwise base score with the standard 3-cost penalty | mild | low/med |

## SCALE (flagged, no dock proposed)

- **Rolling Boulder** — "increase this damage by 5" every turn makes this a pure long-fight engine: near-dead in 3-turn hallway fights, excellent vs bosses and multi-enemy elites. Cost-3 penalty already docks its front-load; per the standing de
- **Stone Armor** — 'Gain 4 Plating' is a passive per-turn block engine: near-zero value turn 1, compounding value in long fights (elites/bosses). Classic engine-power profile — flag for depth-aware scaling, no global dock per the standing 
- **Demon Form** — 'At the start of your turn, gain 2 Strength' is the premier long-fight scaler; its value tracks run depth and fight length, not deck composition (any deck has attacks to cash Strength, and multi_hit merely improves the r

## OK (context-free scoring adequate)

Acrobatics, Astral Pulse, Bash, Blood Wall, Bludgeon, Bodyguard, Breakthrough, Crimson Mantle, Dagger Throw, Defend, Defend, Defend, Defend, Discovery, Dredge, Falling Star, Fight Me!, Finesse, Flame Barrier, Flash of Steel, Giant Rock, Glitterstream, Guiding Star, Hand of Greed, Hemokinesis, Impervious, Infernal Blade, Iron Wave, Jack of All Trades, Leg Sweep, Luminesce, Master of Strategy, Neow's Fury, Neutralize, Not Yet, Offering, Pommel Strike, Production, Pyre, Reap, Relax, Salvo, Shiv, Shockwave, Shrug It Off, Slice, Strike, Strike, Strike, Strike, Survivor, Taunt, Thinking Ahead, Thrumming Hatchet, Thunderclap, Ultimate Defend, Ultimate Strike, Unleash, Uppercut, Venerate, Wisp
