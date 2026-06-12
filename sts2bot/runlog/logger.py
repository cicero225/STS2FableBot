"""Per-run structured logging (REQUIREMENTS FR-5.1, C6).

Layout under the log root:
    runs/<YYYYmmdd-HHMMSS>_<character>/decisions.jsonl   one record per decision
    runs/<.../>meta.json                                  header + outcome
    index.sqlite                                          queryable run aggregates
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class RunOutcome(BaseModel):
    status: str = "unknown"  # completed | error | aborted
    victory: bool | None = None
    character: str | None = None
    ascension: int | None = None
    act: int | None = None
    floor: int | None = None
    decisions: int = 0
    error: str | None = None
    game_over_message: str | None = None


class RunLogger:
    """Writes one run's decision stream and metadata. Not thread-safe; one per run."""

    def __init__(self, log_root: Path, character_hint: str = "unknown"):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.run_dir = Path(log_root) / "runs" / f"{stamp}_{character_hint.lower()}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._decisions_path = self.run_dir / "decisions.jsonl"
        self._meta_path = self.run_dir / "meta.json"
        self._fh = self._decisions_path.open("a", encoding="utf-8")
        self.seq = 0
        self.started_at = _now_iso()
        self._t0 = time.monotonic()
        self._write_meta({"started_at": self.started_at, "outcome": None})

    def _write_meta(self, meta: dict[str, Any]) -> None:
        self._meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def log_decision(
        self,
        state_raw: dict[str, Any],
        action_payload: dict[str, Any] | None,
        rationale: str,
        result: dict[str, Any] | None,
        scores: dict[str, float] | None = None,
    ) -> None:
        """action_payload/result are None for Wait ticks worth recording."""
        self.seq += 1
        record = {
            "seq": self.seq,
            "ts": _now_iso(),
            "t": round(time.monotonic() - self._t0, 3),
            "state_type": state_raw.get("state_type"),
            "state": state_raw,
            "action": action_payload,
            "rationale": rationale,
            "scores": scores,
            "result": result,
        }
        self._fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._fh.flush()

    def finalize(self, outcome: RunOutcome) -> None:
        self._write_meta(
            {
                "started_at": self.started_at,
                "ended_at": _now_iso(),
                "outcome": outcome.model_dump(),
            }
        )
        self._fh.close()
