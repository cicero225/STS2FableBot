import sts2bot


def test_package_imports() -> None:
    assert sts2bot.__version__


def test_fingerprint_ignores_engine_liveness_dict() -> None:
    """Own-goal caught live 2026-08-10 (owner: '12 minutes with no movement'):
    the fork mod's engine.process_frames increments every poll, so hashing it
    made every state look changed and the stall rail never fired -- the wedge
    sat in an infinite claim-cap wait. The liveness dict must not feed the
    staleness fingerprint."""
    from sts2bot.orchestrator.loop import _fingerprint

    base = {"state_type": "treasure", "treasure": {"relics": [{"name": "Horn Cleat"}]}}
    a = dict(base, engine={"process_frames": 100, "action_queue_empty": False})
    b = dict(base, engine={"process_frames": 999, "action_queue_empty": False})
    assert _fingerprint(a) == _fingerprint(b) == _fingerprint(base)
    # real state changes still register
    c = dict(base, state_type="map")
    assert _fingerprint(c) != _fingerprint(base)
