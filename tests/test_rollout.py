"""Rollout engine (PLAN §5.2 P1): sanity + determinism. Calibration against the
n=292 corpus lives in scripts/calibrate_capability.py, not here."""
from types import SimpleNamespace as NS

from sts2bot.policy.capability import FightEnemy
from sts2bot.policy.rollout import rollout_fight

FX = {
    "STRIKE_IRONCLAD|0": "Deal 6 damage.",
    "STRIKE_IRONCLAD|1": "Deal 9 damage.",
    "DEFEND_IRONCLAD|0": "Gain 5 Block.",
    "BASH|0": "Deal 8 damage. Apply 2 Vulnerable.",
    "BLUDGEON|0": "Deal 32 damage.",
    "SHRUG_IT_OFF|0": "Gain 8 Block. Draw 1 card.",
}


def card(cid, typ="Attack", cost="1", up=False, name=None, desc=None):
    return NS(id=cid, name=name or cid.title(), type=typ, cost=cost,
              is_upgraded=up, description=desc)


def starter():
    return ([card("STRIKE_IRONCLAD")] * 5
            + [card("DEFEND_IRONCLAD", typ="Skill")] * 4
            + [card("BASH", cost="2")])


def test_deterministic_for_same_inputs() -> None:
    deck = starter()
    foe = [FightEnemy(hp=140, dps=17, str_ramp=1)]
    a = rollout_fight(deck, foe, 70, 80, card_effects=FX)
    b = rollout_fight(deck, foe, 70, 80, card_effects=FX)
    assert a == b


def test_starter_loses_to_big_elite_and_built_deck_does_better() -> None:
    foe = [FightEnemy(hp=140, dps=17, str_ramp=1)]
    weak = rollout_fight(starter(), foe, 70, 80, card_effects=FX)
    built = rollout_fight(
        [*starter(), *([card("BLUDGEON", cost="3")] * 3),
         *([card("SHRUG_IT_OFF", typ="Skill")] * 3)],
        foe, 70, 80, card_effects=FX)
    assert built.win_rate >= weak.win_rate
    assert built.exp_end_hp >= weak.exp_end_hp


def test_hand_curse_bleeds_the_rollout() -> None:
    bad_luck = card("BAD_LUCK", typ="Curse", cost="0", name="Bad Luck",
                    desc="Unplayable. At the end of your turn, if this is in your "
                         "Hand, lose 13 HP. Eternal.")
    foe = [FightEnemy(hp=60, dps=8)]
    clean = rollout_fight(starter(), foe, 60, 80, card_effects=FX)
    cursed = rollout_fight([*starter(), bad_luck], foe, 60, 80, card_effects=FX)
    assert cursed.exp_end_hp < clean.exp_end_hp


# ---- phased spawns (Phrog phase 2, 2026-07-30: wrigglers arrive AFTER the parasite dies) ----

def test_dormant_wave_does_not_attack_or_soak_damage_before_spawning() -> None:
    # leader hits for 0; wave-1 bodies hit for 12 each. If waves were concurrent the
    # starter would bleed out; dormant wave means turn-N damage starts only post-kill.
    leader = FightEnemy(hp=1, dps=0)
    wave = [FightEnemy(hp=200, dps=12, wave=1) for _ in range(4)]
    r = rollout_fight(starter(), [leader, *wave], 70, 80, card_effects=FX, max_turns=3)
    # leader dies turn 1, wave spawns with 800 HP nobody can clear in 3 turns -> losses,
    # but the fight must NOT be scored a win at leader-kill (kill-HP includes the wave)
    assert r.win_rate == 0.0


def test_killing_leader_activates_wave_instead_of_winning() -> None:
    leader = FightEnemy(hp=1, dps=0)
    wave = [FightEnemy(hp=4, dps=0, wave=1)]
    r = rollout_fight(starter(), [leader, *wave], 70, 80, card_effects=FX)
    # harmless 5-HP total fight: always a win, but only after clearing BOTH waves
    assert r.win_rate == 1.0


def test_wave_split_prices_phrog_hotter_than_concurrent_split() -> None:
    from sts2bot.policy.capability import elite_fight_members
    bestiary = {"Phrog Parasite": {"hp": [40, 46], "statuses": {}},
                "Wriggler": {"hp": [10, 12], "statuses": {}}}
    members = elite_fight_members(
        "Phrog Parasite", bestiary["Phrog Parasite"], bestiary, dps=12)
    parasite = [m for m in members if m.wave == 0]
    wrigglers = [m for m in members if m.wave == 1]
    assert len(parasite) == 1 and len(wrigglers) == 4
    # phase 1: the parasite alone carries the FULL act estimate (was 12//5 = 2)
    assert parasite[0].dps == 12
    # phase 2: the wave splits the act estimate among its own 4 bodies
    assert all(w.dps == 3 for w in wrigglers)


def test_composition_members_use_their_own_realized_dps_when_harvested() -> None:
    from sts2bot.policy.capability import elite_fight_members
    bestiary = {"Phrog Parasite": {"hp": [40, 46], "statuses": {}},
                "Wriggler": {"hp": [10, 12], "statuses": {}}}
    table = {"Phrog Parasite": {"dps_early": 5.4, "dps_mean": 6.7},
             "Wriggler": {"dps_early": 3.7, "dps_mean": 4.1}}
    members = elite_fight_members("Phrog Parasite", bestiary["Phrog Parasite"],
                                  bestiary, dps=12, dps_table=table)
    # harvested per-body numbers win over the act-estimate split
    assert next(m for m in members if m.wave == 0).dps == 5
    assert all(w.dps == 4 for w in members if w.wave == 1)


# ---- synth bridge v2: Strength re-baked into planner-visible texts (2026-07-30) ----

def test_rebake_strength_adjusts_numeric_damage_only() -> None:
    from sts2bot.policy.rollout import _rebake_strength
    assert _rebake_strength("Deal 6 damage.", 3) == "Deal 9 damage."
    assert _rebake_strength("Deal 6 damage 2 times.", 3) == "Deal 9 damage 2 times."
    assert _rebake_strength("Deal damage equal to your Block.", 3) == \
        "Deal damage equal to your Block."
    assert _rebake_strength("Deal 6 damage.", 0) == "Deal 6 damage."
    # drained past the base: the game floors a hit at 0, so does the re-bake
    assert _rebake_strength("Deal 6 damage.", -9) == "Deal 0 damage."
    # 'Deals N additional...' riders are per-X scaling, NOT a hit — Strength must
    # only land on the primary 'Deal N damage' clause (8 such texts in the catalog)
    assert _rebake_strength(
        "Deal 6 damage. Deals 3 additional damage for each card in your Exhaust Pile.",
        5) == "Deal 11 damage. Deals 3 additional damage for each card in your Exhaust Pile."


def test_synth_state_shows_planner_strength_adjusted_attacks() -> None:
    import random

    from sts2bot.policy.rollout import _build_cards, _RolloutSim, _synth_state
    cards = _build_cards([card("STRIKE_IRONCLAD"), card("DEFEND_IRONCLAD", typ="Skill")],
                         FX)
    sim = _RolloutSim(cards, [FightEnemy(hp=30, dps=5)], 50, 80,
                      random.Random(1), [], {})
    sim.start_turn()
    sim.my_str = 3
    st = _synth_state(sim)
    texts = [c.description for c in st.player.hand]
    assert any("Deal 9 damage" in t for t in texts)      # Strike re-baked
    assert all("Gain 8" not in t or "damage" not in t for t in texts)  # skills untouched


def test_loss_gradient_survives_unwinnable_fights() -> None:
    # KD audit 2026-07-30: on a forecast-lost boss every option used to score end_hp
    # 0 -- exp_enemy_hp_left restores the 'got closer to the kill' gradient drafting
    # needs. A deck with Bludgeons leaves less boss standing than the bare starter.
    boss = [FightEnemy(hp=400, dps=30)]
    weak = rollout_fight(starter(), boss, 60, 80, card_effects=FX)
    strong = rollout_fight([*starter(), *([card("BLUDGEON", cost="3")] * 3)],
                           boss, 60, 80, card_effects=FX)
    assert weak.win_rate == 0.0 and strong.win_rate == 0.0
    assert strong.exp_enemy_hp_left < weak.exp_enemy_hp_left


def test_artifact_charges_eat_vulnerable_in_the_sim() -> None:
    # Aeonglass tape (4 fights, 2026-07-30): she opens with Artifact 3, so early
    # Vulnerable-based plans fizzle -- the +581-peak-then-collapse signature. The
    # live planner already knew; the sim let vuln land turn 1 (optimistic exactly
    # where the fight is hardest). Bash x many vs artifact=1: first vuln eaten.
    from sts2bot.policy.capability import detect_mechanics
    flags = detect_mechanics([{"name": "Artifact", "description": "Negates 3 debuffs."}])
    assert flags.get("artifact") == 3
    # sim: same deck, same boss, artifact 3 vs 0 -- charges must cost win equity
    boss = dict(hp=300, dps=18, str_ramp=2)
    plain = rollout_fight([*starter(), *([card("BASH", cost="2")] * 3)],
                          [FightEnemy(**boss)], 75, 80, card_effects=FX)
    shielded = rollout_fight([*starter(), *([card("BASH", cost="2")] * 3)],
                             [FightEnemy(**boss, artifact=3)], 75, 80, card_effects=FX)
    assert (shielded.win_rate, shielded.exp_end_hp - shielded.exp_enemy_hp_left) <= \
        (plain.win_rate, plain.exp_end_hp - plain.exp_enemy_hp_left)


def test_target_order_changes_outcomes_in_leader_plus_ramp_fights() -> None:
    # Kin shape: big leader + small ramping bodies. "sweep" clears the ramps
    # (shedding their growing dps); "focus" races the big body while they scale.
    # For a low-burst deck the orders are night and day (probe: 1.00 vs 0.00) --
    # which is exactly the signal _fight_plan selects on.
    leader = FightEnemy(hp=90, dps=5)
    ramps = [FightEnemy(hp=12, dps=4, str_ramp=5) for _ in range(2)]
    deck = starter()
    sweep = rollout_fight(deck, [leader, *ramps], 60, 80, card_effects=FX,
                          target_order="sweep")
    focus = rollout_fight(deck, [leader, *ramps], 60, 80, card_effects=FX,
                          target_order="focus")
    assert sweep.win_rate > focus.win_rate + 0.5


def test_sleeper_gives_free_setup_turns_and_wakes_on_damage() -> None:
    # Matriarch A/B 2026-07-30: she sleeps ~3 turns unless damaged; the owner set
    # up through the window and burst her down, where the bot chipped her awake.
    # Sim: a sleeping boss deals nothing while asleep, and the greedy banks setup
    # instead of waking her -- so the same fight prices better than the old
    # attacks-from-turn-1 model.
    from sts2bot.policy.capability import bestiary_enemy
    entry = {"hp": [222, 222], "statuses": {}}
    # the empirical row now carries sleep_turns=3 for every Matriarch, so the
    # awake control must override it explicitly
    # drain-free overrides isolate the SLEEP effect: since 2026-08-03 the rollout
    # models Soul Siphon too, which decays both arms and would blur this margin
    awake = bestiary_enemy(entry, dps=13, name="Lagavulin Matriarch",
                           sleep_turns=0, drains_player=0, drain_every=0)
    asleep = bestiary_enemy(entry, dps=13, name="Lagavulin Matriarch",
                            drains_player=0, drain_every=0)
    assert asleep.sleep_turns == 3  # empirical row still rides along
    assert bestiary_enemy(entry, dps=13, name="Lagavulin Matriarch").drains_player
    fx = {**FX, "INFLAME|0": "Gain 2 Strength."}
    deck = [*starter(), *([card("BLUDGEON", cost="3")] * 3),
            *([card("INFLAME", typ="Power", cost="1")] * 2)]
    r_awake = rollout_fight(deck, [awake], 44, 80, card_effects=fx)
    r_sleep = rollout_fight(deck, [asleep], 44, 80, card_effects=fx)
    # the window is worth real progress (~2 turns of damage: probe 132 -> 104)
    assert r_sleep.exp_enemy_hp_left < r_awake.exp_enemy_hp_left - 15


def test_fiddle_relic_shapes_the_sim_draws() -> None:
    # Fiddle: 7-card turn starts, card-text draws dead (owner 2026-07-31)
    from types import SimpleNamespace as NS
    fiddle = [NS(id="FIDDLE", name="Fiddle", description="x")]
    foe = [FightEnemy(hp=60, dps=8)]
    deck = [*starter(), card("SHRUG_IT_OFF", typ="Skill")]
    with_f = rollout_fight(deck, foe, 60, 80, card_effects=FX, relics=fiddle)
    without = rollout_fight(deck, foe, 60, 80, card_effects=FX)
    # both must complete; the fiddle run sees bigger hands (7/turn) so it should
    # not do worse against a soft target
    assert with_f.win_rate >= without.win_rate


def test_whispering_earring_models_both_halves() -> None:
    # Owner 2026-08-01: '+1 energy at the start of each turn. Vakuu plays your
    # first turn for you (left-to-right).' Upside: 4-energy turns. Drawback:
    # turn 1 unprioritized. Net vs a soft target the energy should dominate;
    # and the run must complete with the autopilot in the loop.
    from types import SimpleNamespace as NS
    ear = [NS(id="WHISPERING_EARRING", name="Whispering Earring", description="x")]
    foe = [FightEnemy(hp=70, dps=9)]
    deck = [*starter(), card("BLUDGEON", cost="3")]
    with_e = rollout_fight(deck, foe, 60, 80, card_effects=FX, relics=ear)
    without = rollout_fight(deck, foe, 60, 80, card_effects=FX)
    assert (with_e.win_rate, with_e.exp_end_hp) >= (without.win_rate, without.exp_end_hp)


def test_body_slam_scales_with_block_in_the_sim() -> None:
    # Owner 2026-08-01: Body Slam is THE Barricade finisher -- 'often lack a
    # finisher otherwise'. Catalog text has no/stale numbers so the sim computed
    # ~0 damage, making the whole archetype invisible to draft deltas. Now:
    # a Barricade + Defends + Body Slam deck must beat the same deck with the
    # slams swapped for Strikes against a big single body.
    FX2 = {**FX, "BODY_SLAM|0": "Deal damage equal to your Block.",
           "BARRICADE|0": "Block is not removed at the start of your turn."}
    boss = [FightEnemy(hp=260, dps=14)]
    base = [*([card("DEFEND_IRONCLAD", typ="Skill")] * 6),
            card("BARRICADE", typ="Power", cost="3"),
            *([card("STRIKE_IRONCLAD")] * 2)]
    slams = [*([card("DEFEND_IRONCLAD", typ="Skill")] * 6),
             card("BARRICADE", typ="Power", cost="3"),
             *([card("BODY_SLAM", cost="1")] * 2)]
    r_strike = rollout_fight(base, boss, 65, 80, card_effects=FX2)
    r_slam = rollout_fight(slams, boss, 65, 80, card_effects=FX2)
    assert (r_slam.win_rate, r_slam.exp_end_hp - r_slam.exp_enemy_hp_left) > \
        (r_strike.win_rate, r_strike.exp_end_hp - r_strike.exp_enemy_hp_left)


def test_guarded_queen_torch_first_beats_queen_first() -> None:
    """Queen A/B (owner 2026-08-02, seed 373PFAE7EE, both orders taped): while
    her torch lives the Queen never attacks -- she Buffs both bodies and
    re-blocks 20; the torch's death breaks the guard (block ends, she attacks
    at the accumulated dps, no resummon). Torch-first unlocks her HP bar; the
    sim must rank it over racing 400 HP through 20 block/turn under a ramping
    torch."""
    deck = ([card("STRIKE_IRONCLAD", up=True)] * 6
            + [card("BLUDGEON", cost="3")] * 2
            + [card("SHRUG_IT_OFF", typ="Skill")] * 3
            + [card("BASH", cost="2")])
    queen = FightEnemy(hp=400, dps=0, self_block=20, guarded_by_minions=True,
                       awakened_dps=18, awakened_buff_per_turn=2)
    torch = FightEnemy(hp=150, dps=18, str_ramp=2, counts_toward_kill=False)
    sweep = rollout_fight(deck, [torch, queen], 83, 98, card_effects=FX,
                          target_order="sweep")
    focus = rollout_fight(deck, [torch, queen], 83, 98, card_effects=FX,
                          target_order="focus")
    assert (sweep.win_rate, sweep.p25_end_hp, -sweep.exp_enemy_hp_left) >= \
           (focus.win_rate, focus.p25_end_hp, -focus.exp_enemy_hp_left)
    # and the guard must actually bite: queen-first can't be a cakewalk
    assert focus.win_rate < 0.9


def test_miniature_cannon_boosts_upgraded_attack_decks() -> None:
    """Epoch relic (owner 2026-08-02): 'Upgraded Attacks deal 3 additional
    damage' -- an upgraded-strike deck must roll out strictly better holding it."""
    deck = [card("STRIKE_IRONCLAD", up=True)] * 7 + [card("DEFEND_IRONCLAD", typ="Skill")] * 3
    foe = [FightEnemy(hp=120, dps=12, str_ramp=1)]
    cannon = [NS(id="MINIATURE_CANNON", name="Miniature Cannon",
                 description="Upgraded Attacks deal 3 additional damage.", counter=None)]
    without = rollout_fight(deck, foe, 70, 80, card_effects=FX)
    with_c = rollout_fight(deck, foe, 70, 80, card_effects=FX, relics=cannon)
    assert (with_c.win_rate, with_c.exp_end_hp) > (without.win_rate, without.exp_end_hp) or \
           with_c.exp_enemy_hp_left < without.exp_enemy_hp_left


def test_tungsten_rod_reduces_chip_losses() -> None:
    """Epoch relic (owner 2026-08-02): 'Whenever you would lose hp, lose 1 less'
    -- modeled as -1 per attacker per turn and -1 on card self-HP costs."""
    deck = starter()
    foe = [FightEnemy(hp=100, dps=10)]
    rod = [NS(id="TUNGSTEN_ROD", name="Tungsten Rod",
              description="Whenever you would lose HP, lose 1 less.", counter=None)]
    without = rollout_fight(deck, foe, 70, 80, card_effects=FX)
    with_r = rollout_fight(deck, foe, 70, 80, card_effects=FX, relics=rod)
    assert (with_r.win_rate, with_r.exp_end_hp) >= (without.win_rate, without.exp_end_hp)
    assert with_r.exp_end_hp > without.exp_end_hp or with_r.win_rate > without.win_rate


def test_player_stat_drain_decays_long_fights() -> None:
    """Matriarch forensics 2026-08-03: Soul Siphon (-2 Str per cast, every 4th
    turn) was modeled in the static estimator but NOT the rollout -- forecasts
    blessed 10-12 round grinds whose damage decays, producing razor losses
    (boss at 6-18 HP). A draining foe must roll out strictly worse than the
    same foe without the drain."""
    deck = starter()
    plain = FightEnemy(hp=200, dps=10)
    drainer = FightEnemy(hp=200, dps=10, drains_player=2, drain_every=4)
    a = rollout_fight(deck, [plain], 80, 80, card_effects=FX)
    b = rollout_fight(deck, [drainer], 80, 80, card_effects=FX)
    assert (b.win_rate, b.exp_end_hp) <= (a.win_rate, a.exp_end_hp)
    assert b.win_rate < a.win_rate or b.exp_enemy_hp_left > a.exp_enemy_hp_left


def test_surround_bonus_prices_the_two_claw_clock() -> None:
    """Kaiser A/B (owner 2026-08-03, won 68->20 by all-in Rocket-first): while
    both claws live the back-attack makes the phase a ~10 HP/round clock;
    killing one claw ends it. The pair with surround bonuses must price worse
    than the same pair without -- the delta is the claw-kill-speed incentive."""
    deck = starter() + [card("BLUDGEON", cost="3")] * 2
    plain = [FightEnemy(hp=180, dps=8), FightEnemy(hp=140, dps=10)]
    crabs = [FightEnemy(hp=180, dps=8, surround_bonus_dps=5),
             FightEnemy(hp=140, dps=10, surround_bonus_dps=5)]
    a = rollout_fight(deck, plain, 70, 80, card_effects=FX)
    b = rollout_fight(deck, crabs, 70, 80, card_effects=FX)
    assert (b.win_rate, b.exp_end_hp) <= (a.win_rate, a.exp_end_hp)
    # both arms can floor at 0% for a modest deck -- the loss GRADIENT still
    # shows the surcharge: dying faster leaves more claw standing
    assert (b.win_rate < a.win_rate or b.exp_end_hp < a.exp_end_hp
            or b.exp_enemy_hp_left > a.exp_enemy_hp_left)


def test_every_fightenemy_field_reaches_the_rollout() -> None:
    """Parity regression guard (the Matriarch-drain class, owner 2026-08-03
    'may be worth a full audit'): every FightEnemy field must be consumed by
    the _RolloutSim constructor mapping, or forecasts silently diverge from
    the static estimator's knowledge."""
    import dataclasses
    import inspect
    import re as _re

    import sts2bot.policy.rollout as ro
    src = inspect.getsource(ro._RolloutSim.__init__)
    mapped = set(_re.findall(r"e\.(\w+)", src))
    missing = [f.name for f in dataclasses.fields(FightEnemy) if f.name not in mapped]
    assert not missing, f"FightEnemy fields invisible to the rollout: {missing}"


def test_wg_eruption_is_delayed_and_blockable_not_instant() -> None:
    """WG decode (owner 2026-08-09): 0 HP -> untargetable 'preparing' shell for
    one turn (deals nothing) -> the accumulated eruption lands as a NORMAL
    BLOCKABLE strike -> the shell dies. The old model charged it instantly and
    unavoidably at the kill, which over-priced WG fights (audit -22.9 bucket)
    and could scare low-HP decks away from the kill."""
    # a deck that kills turn 1: eruption should NOT hit instantly; with enough
    # block income the eruption turn is survivable where the instant model died
    deck = ([card("BLUDGEON", cost="3")] * 5
            + [card("SHRUG_IT_OFF", typ="Skill")] * 5)
    wg = FightEnemy(hp=25, dps=10, death_damage=15, death_damage_growth=3)
    r = rollout_fight(deck, [wg], 30, 80, card_effects=FX)
    # the fight is winnable: the eruption is blockable and the shell then dies
    assert r.win_rate > 0.0
    # and the win is not instant-turn-1 with zero consequence either: fights
    # run at least 3 sim turns (kill + preparing + eruption)
    assert r.mean_turns >= 3.0


def test_rollout_sandpit_timer_padded_for_late_application_and_escapes() -> None:
    """Owner decode (told THREE times -- now canonical in data/enemy_notes.json):
    Sandpit lands AFTER turn 1 (~turn-5 base expiry) and 6 Frantic Escape status
    cards extend it +1 turn each at escalating cost (1,2,3...). The closed form
    padded the deadline; the ROLLOUT raced the raw turn-4 clock, so every
    Insatiable forecast read 0% while run 20260809-230646 beat it live.
    Pin: a pure-survival deck against a timed foe dies AT the deadline -- the
    recorded loss turn shows which clock ran (raw 4 = the bug, padded 8 = fix)."""
    deck = [card("SHRUG_IT_OFF", typ="Skill")] * 10
    timed = FightEnemy(hp=170, dps=1, death_timer=4)
    r = rollout_fight(deck, [timed], 80, 80, card_effects=FX)
    assert r.win_rate == 0.0
    assert r.mean_turns >= 7.5  # eaten at the padded deadline, not the raw 4
    # no timer: the same unkillable stall runs to the sim cap instead
    r2 = rollout_fight(deck, [FightEnemy(hp=170, dps=1)], 80, 80, card_effects=FX)
    assert r2.mean_turns > r.mean_turns


def test_brimstone_models_both_edges() -> None:
    """Owner check 2026-08-13: Brimstone (+2 Str us / +1 Str all enemies per
    turn) was absent from the rollout relic table -- forecasts missed both
    edges. An attack deck should forecast BETTER with Brimstone vs the same
    fight (our ramp outpaces theirs 2:1 for a lone enemy)."""
    from types import SimpleNamespace as NS

    deck = ([card("STRIKE_IRONCLAD", cost="1")] * 6
            + [card("DEFEND_IRONCLAD", typ="Skill")] * 4)
    foe = FightEnemy(hp=120, dps=10)
    brim = NS(id="BRIMSTONE", name="Brimstone", counter=None)
    base = rollout_fight(deck, [foe], 70, 70, card_effects=FX, n=20)
    with_b = rollout_fight(deck, [foe], 70, 70, card_effects=FX, n=20,
                           relics=[brim])
    assert with_b.mean_turns < base.mean_turns or with_b.win_rate >= base.win_rate
    # and the enemy edge is real: a no-attack deck suffers MORE incoming
    turtle = [card("DEFEND_IRONCLAD", typ="Skill")] * 10
    base_t = rollout_fight(turtle, [foe], 70, 70, card_effects=FX, n=20)
    with_t = rollout_fight(turtle, [foe], 70, 70, card_effects=FX, n=20,
                           relics=[brim])
    assert with_t.exp_end_hp <= base_t.exp_end_hp


def test_rampage_growth_compounds_in_rollouts() -> None:
    """Owner audit 2026-08-15: the rollout now grows Rampage per play WITHIN a
    rollout (per-sim tracking -- _Card objects are shared across rollouts, so
    fx mutation would leak). A Rampage deck must beat the same deck with a
    flat 9-damage card vs a big-HP target."""
    ramp = card("RAMPAGE", cost="1")
    flat = card("STRIKE_IRONCLAD", cost="1")
    filler = [card("DEFEND_IRONCLAD", typ="Skill")] * 6
    FX2 = dict(FX)
    FX2["RAMPAGE|0"] = "Deal 9 damage. Increase this card's damage by 5 this combat."
    FX2["STRIKE_IRONCLAD|0"] = "Deal 9 damage."
    foe = FightEnemy(hp=300, dps=8)
    r_ramp = rollout_fight([ramp] * 3 + filler, [foe], 80, 80, card_effects=FX2, n=20)
    r_flat = rollout_fight([flat] * 3 + filler, [foe], 80, 80, card_effects=FX2, n=20)
    assert r_ramp.mean_turns < r_flat.mean_turns, (r_ramp, r_flat)
