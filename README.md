# STS2FableBot

A bot that plays **Slay the Spire 2** on its own, through the
[STS2MCP](https://github.com/Gennadiyev/STS2MCP) mod's local REST API.
The decision engine is deterministic, search-based Python: it reads the same
game state a player sees, scores its options, and logs every decision with the
numbers behind it. No neural network sits in the play loop.

The project started in June 2026 (first commit 2026-06-11) as a long-running
experiment in building a competent game-playing agent out of explicit models
and search, with machine learning kept to offline, inspectable evaluators.
Most of the code is written by Claude (Anthropic's Fable 5.1) working with a
human owner who directs the work, watches the runs, and decodes game mechanics
the bot gets wrong; that collaboration is part of the point of the project.

## Ground rules

- **No cheating.** The mod is an interface, not an oracle. The bot only uses
  information a human player could see on screen: no peeking at undrawn cards,
  hidden map content, or RNG, and no save-scumming to undo outcomes. Win rates
  are meant to mean something.
- **Observable.** Every decision is written to a JSONL log with the state the
  bot saw, the scores it computed, and a one-line rationale. Any run can be
  reconstructed and any decision replayed offline against the logged state.
- **Separate profile.** The bot plays on its own in-game profile and never
  touches the owner's saves. Save backups are part of the tooling.
- **Patch-aware.** Every run records the game build. Unknown content halts
  the bot with a report rather than letting it flail.

## Where it stands

Ironclad only. The bot cleared its Ascension 0 benchmark on 2026-10-01,
played Ascension 1 until 2026-10-03, and is now playing Ascension 2.

| Metric | Value |
|---|---|
| Win rate, Ascension 0, final code (343 runs) | 20.7% (95% interval 16-25%) |
| Win rate, Ascension 1, after the act-3 fixes (175 runs) | 19.4% (95% interval 14-25%) |
| Win rate, Ascension 1, with the boss-campfire rest rule (39 runs) | 25.6% |
| Reference: dedicated-player average on the community tracker | about 20% |
| Current level | Ascension 2 |
| Completed runs logged since June 2026 | about 4,200 |
| Game build | v0.107.1 |

Most of the gains came from decoding enemy and card mechanics from the game's
own status text and fixing the simulator to match, one death tape at a time
(sleeping bosses, post-kill eruptions, per-hit damage caps, keyword-borne
self-damage, random-target attacks, wounds from unblocked hits). Ascension 1
(more elites) first cost about 7 points (13.8% over the first 94 runs); a round of act-3 fixes and a
campfire rule that rests before act-1/2 bosses below 80% HP brought it back.
Arriving healthy turned out to be the strongest single predictor of beating a
boss or an elite. The current weak spots are early elites against thin decks,
the first act-2 elite, and the Queen. The roadmap is Ironclad to Ascension 3
at about 20%, then a second character. The long-term target in
[REQUIREMENTS.md](REQUIREMENTS.md) is the full climb to Ascension 10 on every
character.

## How it plays

- **Combat** is a depth-first search over this turn's play sequences against
  a simulator of the visible board: card text parsed into effects, enemy
  intents, statuses, relic triggers, potions. A fight-mode table and a small
  forward model (kill deadlines, setup windows, race vs. defend) shape the
  scoring across turns.
- **Map routing** is a dynamic program over the act's paths that prices
  elites and bosses from the bot's own observed fight history, with HP
  projections and death floors.
- **Drafting, shops, events, rest sites, and potions** use hand-written
  scoring over card tags and data-derived priors, with a growing set of
  owner-decoded rulings in `data/*_notes.json`.
- **Learning** (in progress) fits gradient-boosted evaluators on the run
  logs at existing decision points, such as a P(win) and boss-survival head
  for drafting. The play loop only ever reads exported model JSON; there is
  no end-to-end reinforcement learning.

Policies are pure functions `(state, knowledge base, config) -> (action,
scores, rationale)` with no I/O, which is what makes them unit-testable and
replayable. Policy weights live in `config/policy.toml`, and every run log
records the config hash it played under.

## Layout

```
sts2bot/
  client/        REST client, typed state models, action senders
  policy/        combat planner, map DP, drafting, shop/event/rest/potion rules
  kb/            config loading, knowledge-base access
  orchestrator/  run loop, batch driver, watchdog, game process management
  learn/         offline evaluator training and JSON-model inference
  runlog/        JSONL decision logs
  cli.py         entry point (`sts2bot ...`)
config/          policy parameters (versioned; hashed into run logs)
data/            card/relic/enemy catalogs, priors, owner-decoded mechanics
scripts/         analysis, calibration, catalog builders, save backup/restore
tests/           pytest suite with captured live states as fixtures
```

Project documents:

- [REQUIREMENTS.md](REQUIREMENTS.md): what the bot must do and the hard
  constraints it plays under.
- [PLAN.md](PLAN.md): architecture, phases, and the rolling table of open
  investigations.
- [LOG.md](LOG.md): the lab notebook, newest first. Every live session,
  experiment, and root cause is written up there.
- `data/enemy_notes.json`, `card_notes.json`, `relic_notes.json`: mechanics
  as decoded from live play, in the form the planner consumes.

## Running it

The bot runs on Windows against a Steam install of Slay the Spire 2 with the
STS2MCP mod. It needs **our fork** of the mod, which adds the master deck to
the state payload plus ascension and time-scale controls the bot depends on:
[cicero225/STS2MCP](https://github.com/cicero225/STS2MCP), branch
`v107-fork` for game build v0.107.1 (`v111-fork` for the v0.111 public beta).
The fork's README lists what each branch adds.

```powershell
python -m venv .venv
.venv\Scripts\pip install -e .[dev]

# build the mod fork against your game directory and copy the DLL into the
# game's mods/ folder (see external/STS2MCP/build.ps1 and patches/README.md)

.venv\Scripts\sts2bot doctor                      # can we see the game?
.venv\Scripts\sts2bot play --runs 5 --profile 1   # play five runs on profile 1
.venv\Scripts\sts2bot replay                      # re-run the policy over logged states
```

Before the first live run, back up your saves (`scripts/backup_saves.py`)
and turn Steam Cloud off for the game: the bot plays whatever profile you
point it at, and cloud sync has reshuffled modded profiles before.

Development:

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\python -m ruff check .
```

## Acknowledgements

- [STS2MCP](https://github.com/Gennadiyev/STS2MCP) by Gennadiyev, the mod
  that exposes the game over HTTP. This project would not exist without it.
- [Spirebird](https://spirebird.com), jorbs' public Slay the Spire statistics
  site. The card-pick priors in `data/priors_cards.json` are distilled from its
  cohort exports (card pick rates, win rates), fetched as occasional one-time
  downloads, never scraped.
- Slay the Spire 2 is by Mega Crit. This project is not affiliated with or
  endorsed by Mega Crit.

## License

[MIT](LICENSE).
