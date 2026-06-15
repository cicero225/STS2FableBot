"""Spirebird event ratings (distilled by scripts/build_event_stats.py).

Each event: an overall vsBaseline plus per-option vsBaseline keyed by Spirebird's internal
option key. The live EventOption has only a title, and the key is not a clean title
derivation, so option matching is best-effort (article-tolerant word-subset) and returns
None when it can't be sure — the policy then leans on its own gain/cost heuristic.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DEFAULT_EVENT_STATS_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "event_stats.json"
)
_ARTICLES = {"THE", "A", "AN", "AND", "TO", "YOUR", "OF", "IT", "OR", "FOR"}


def _words(s: str) -> set[str]:
    toks = re.sub(r"[^A-Z0-9]+", " ", (s or "").upper()).split()
    return {t for t in toks if t not in _ARTICLES}


class EventStats:
    def __init__(self, events: dict[str, dict] | None = None, meta: dict | None = None):
        self.events = events or {}
        self.meta = meta or {}

    @classmethod
    def load(cls, path: Path | str | None = None) -> EventStats | None:
        p = Path(path) if path else DEFAULT_EVENT_STATS_PATH
        if not p.exists():
            return None
        d = json.loads(p.read_text(encoding="utf-8"))
        return cls(d.get("events"), d.get("meta"))

    def overall_vs(self, event_id: str | None) -> float | None:
        ev = self.events.get((event_id or "").upper())
        return ev.get("overall_vs") if ev else None

    def option_vs(self, event_id: str | None, option_title: str | None) -> float | None:
        """Best-effort vsBaseline for a live option, matched by title->internal-key word
        subset. None when the event is unknown or no option key confidently matches."""
        ev = self.events.get((event_id or "").upper())
        if not ev:
            return None
        title_words = _words(option_title)
        if not title_words:
            return None
        best: tuple[int, float] | None = None  # (specificity, vs)
        for key, info in ev.get("options", {}).items():
            kw = _words(key)
            if kw and kw <= title_words and (best is None or len(kw) > best[0]):
                best = (len(kw), info["vs"])
        return best[1] if best else None
