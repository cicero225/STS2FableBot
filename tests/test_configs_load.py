"""Every committed config TOML must parse and validate (2026-09-03: an arm config
shipped with a duplicated [rest] key and broke tomllib; caught only at load)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sts2bot.kb.config import load_policy_config

CONFIGS = sorted((Path(__file__).resolve().parent.parent / "config").glob("*.toml"))


@pytest.mark.parametrize("path", CONFIGS, ids=[p.name for p in CONFIGS])
def test_config_loads(path: Path) -> None:
    cfg = load_policy_config(path)
    assert cfg.config_hash and len(cfg.config_hash) == 12
    assert cfg.combat.w_kill > 0
