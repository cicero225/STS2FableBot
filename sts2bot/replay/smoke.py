"""Replay harness v1 (FR-5.3): run a policy over previously logged states.

Smoke mode answers one question cheaply: does the policy return a sane
Decision/Wait (no exception) for every state the bot has ever actually seen?
Behavioral comparison between policies builds on this later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from sts2bot.client.models import StateParseError, parse_state
from sts2bot.policy.base import Decision, LoopContext, PolicyRouter, Wait


@dataclass
class ReplayReport:
    states: int = 0
    decisions: int = 0
    waits: int = 0
    errors: list[str] = field(default_factory=list)
    skipped: int = 0  # states that no longer parse (logged pre-schema-change)

    @property
    def ok(self) -> bool:
        return not self.errors


def iter_logged_states(logs_root: Path | str):
    """Yield (run_dir_name, seq, raw_state) for every fully-logged decision state."""
    root = Path(logs_root)
    for decisions_file in sorted(root.glob("runs/*/decisions.jsonl")):
        for line in decisions_file.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            raw = record.get("state")
            # wait-tick records carry only {"state_type": ...}; skip those
            if isinstance(raw, dict) and len(raw) > 1:
                yield decisions_file.parent.name, record.get("seq", -1), raw


def replay_smoke(router: PolicyRouter, logs_root: Path | str) -> ReplayReport:
    report = ReplayReport()
    ctx_by_run: dict[str, LoopContext] = {}
    for run_name, seq, raw in iter_logged_states(logs_root):
        report.states += 1
        try:
            state = parse_state(raw)
        except StateParseError:
            report.skipped += 1
            continue
        ctx = ctx_by_run.setdefault(run_name, LoopContext())
        try:
            decision = router.decide(state, ctx)
        except Exception as e:
            report.errors.append(f"{run_name}#{seq} {state.state_type}: {type(e).__name__}: {e}")
            continue
        if isinstance(decision, Decision):
            report.decisions += 1
        elif isinstance(decision, Wait):
            report.waits += 1
        else:
            report.errors.append(f"{run_name}#{seq}: returned {type(decision).__name__}")
    return report
