"""Shared loaders/splits for the stage-0 dataset (logs/datasets/)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def jsonl_rows(path: Path):
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def is_test_run(run_id: str) -> bool:
    """Stable ~20% holdout BY RUN (rows of one run share outcomes — a row
    split would leak). Keep this the single split definition across all
    stage-1+ training/eval so metrics stay comparable."""
    return int(hashlib.md5(run_id.encode()).hexdigest(), 16) % 5 == 0
