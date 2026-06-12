"""Policy protocol: pure decision functions over typed states.

A policy handler maps (state, ctx) -> Decision | Wait. Handlers must not perform I/O
(REQUIREMENTS C2/C6); the loop owns all side effects. `LoopContext.screen_mem` is the
one concession to statefulness: scratch memory for multi-step screens (e.g. "select two
cards then confirm"), cleared by the loop whenever the state fingerprint changes class.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from sts2bot.client.actions import Action
from sts2bot.client.models import GameState


class Decision(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    action: Action
    rationale: str
    scores: dict[str, float] | None = None


class Wait(BaseModel):
    """No action available/appropriate; loop should poll again (counts toward stall)."""

    reason: str


class LoopContext(BaseModel):
    """Mutable per-run context owned by the agent loop."""

    goal: str = "start_run"
    character: str = "IRONCLAD"
    ascension: int = 0
    profile_id: int | None = None
    screen_mem: dict[str, Any] = Field(default_factory=dict)
    run_started: bool = False
    decisions: int = 0


class PolicyRouter(Protocol):
    def decide(self, state: GameState, ctx: LoopContext) -> Decision | Wait: ...
