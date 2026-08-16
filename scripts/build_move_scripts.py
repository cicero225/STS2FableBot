"""Harvest per-enemy, turn-indexed move scripts from the fight logs.

Multiturn planner P1 (owner design session 2026-08-11): the feasibility oracle
needs "what does this enemy do on turn N" -- Kaiser Rocket's T4 Laser, Soul
Siphon every 4th round, Sandpit's clock. Owner: scripts are MOSTLY turn-indexed;
exceptions are single-threshold bosses (Ceremonial Beast), Queen (Torch-death
trigger), Test Subject (staged bodies) -- those get special-cased, and every
harvested script gets cross-checked against the online wiki before the planner
trusts it (owner: the wiki reliably gives exact turn-by-turn behavior).

Output: data/move_scripts.json
  {enemy: {"turns": {"1": [{intent, label, n}, ...], ...},
           "n_fights": int, "notes": str}}
Turn index = the fight's round counter at the time the intent was shown.
Only intents actually observed are recorded; the wiki pass annotates gaps.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sts2bot.policy.forward import canonical_enemy_name  # noqa: E402

LOGS = ROOT / "logs" / "runs"
DEST = ROOT / "data" / "move_scripts.json"


# Intent types that mean "not acting yet" -- a sleeper's dormant phase. Scripts
# for sleepers are anchored to the WAKE turn (owner P1.1: Matriarch's absolute
# turn-10 rows blended across whenever she woke in 240 fights; her real script
# is 'W1, W2, ...' counted from the first active intent).
_DORMANT = {"sleep", "stun", ""}


def main() -> int:
    # Curated fields survive rebuilds (bestiary lesson: rebuilds are
    # destructive): wiki-verified notes and cycle lengths are hand-added
    # after harvest and must carry over.
    prev: dict = {}
    if DEST.is_file():
        prev = json.loads(DEST.read_text(encoding="utf-8"))

    # (enemy, run, floor) -> {round: [(itype, label), ...]}
    per_fight: dict[tuple, dict[int, list]] = defaultdict(lambda: defaultdict(list))

    for f in sorted(LOGS.glob("*/decisions.jsonl")):
        run_id = f.parent.name
        seen: set[tuple] = set()
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            st = json.loads(line).get("state") or {}
            b = st.get("battle") or {}
            rnd = b.get("round")
            floor = (st.get("run") or {}).get("floor")
            if not rnd or not b.get("enemies"):
                continue
            for e in b["enemies"]:
                # canonicalize: Test Subject's per-encounter specimen suffix
                # ("#C137") fragmented the harvest into 113 one-fight keys
                name = canonical_enemy_name(e.get("name"))
                if not name or (e.get("hp") or 0) <= 0:
                    continue
                for i in e.get("intents") or []:
                    itype = (i.get("type") or "").strip()
                    label = (i.get("label") or "").strip()
                    key = (name, run_id, floor, rnd, itype, label)
                    if key in seen:
                        continue
                    seen.add(key)
                    per_fight[(name, run_id, floor)][rnd].append((itype, label))

    # aggregate: absolute turn index for normal enemies; wake-anchored for sleepers
    abs_scripts: dict[str, dict[int, Counter]] = defaultdict(lambda: defaultdict(Counter))
    wake_scripts: dict[str, dict[int, Counter]] = defaultdict(lambda: defaultdict(Counter))
    slept_fights: Counter = Counter()
    n_fights: Counter = Counter()

    for (name, _run, _floor), rounds in per_fight.items():
        n_fights[name] += 1
        wake_rnd = None
        for rnd in sorted(rounds):
            if any((t or "").lower() not in _DORMANT for t, _ in rounds[rnd]):
                wake_rnd = rnd
                break
        if wake_rnd is not None and wake_rnd > 1:
            slept_fights[name] += 1
        for rnd in sorted(rounds):
            for t, lbl in rounds[rnd]:
                abs_scripts[name][rnd][(t, lbl)] += 1
                if wake_rnd is not None and rnd >= wake_rnd:
                    wake_scripts[name][rnd - wake_rnd + 1][(t, lbl)] += 1

    out: dict[str, dict] = {}
    for name in sorted(n_fights):
        sleeper = slept_fights[name] >= max(3, 0.3 * n_fights[name])
        src = wake_scripts[name] if sleeper else abs_scripts[name]
        prefix = "W" if sleeper else ""
        turns = {}
        for rnd in sorted(src):
            turns[f"{prefix}{rnd}"] = [
                {"intent": t, "label": lbl, "n": n}
                for (t, lbl), n in src[rnd].most_common(6)
            ]
        out[name] = {
            "turns": turns,
            "n_fights": n_fights[name],
            "wake_anchored": sleeper,
            "notes": (prev.get(name) or {}).get("notes", ""),
        }
        if (prev.get(name) or {}).get("cycle"):
            out[name]["cycle"] = prev[name]["cycle"]
    DEST.write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
    print(f"wrote move scripts for {len(out)} enemies "
          f"({sum(1 for n in out.values() if n['wake_anchored'])} wake-anchored) to {DEST.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
