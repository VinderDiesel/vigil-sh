import pytest

from vigil.envbase import CapabilityError, enforce, required_capabilities, snapshot_digest


def test_dry_run_needs_nothing():
    assert required_capabilities({}) == ()


def test_live_side_effects_require_capability():
    assert "live-side-effects" in required_capabilities({"side_effect_policy": "live"})


def test_open_network_requires_capability():
    assert "open-network" in required_capabilities({"network_policy": "open"})


def test_snapshot_requires_capability():
    assert "snapshot" in required_capabilities({"init_snapshot": "snap"})


def test_enforce_raises_on_missing_capability():
    with pytest.raises(CapabilityError) as exc:
        enforce({"side_effect_policy": "live"}, ("in-process",))
    assert "live-side-effects" in str(exc.value)


def test_enforce_passes_when_declared():
    enforce({"side_effect_policy": "live"}, ("live-side-effects",))


def test_snapshot_digest_changes_with_the_world():
    a = snapshot_digest({"image": "img:1", "network_policy": "none"})
    b = snapshot_digest({"image": "img:2", "network_policy": "none"})
    assert a != b


def test_snapshot_digest_ignores_key_order():
    a = snapshot_digest({"image": "img:1", "seeds": {"a": 1}})
    b = snapshot_digest({"seeds": {"a": 1}, "image": "img:1"})
    assert a == b
