from vigil.models.event import CanonicalEvent
from vigil.plugins.minimizer_default import DefaultMinimizer


def ev(**payload):
    return CanonicalEvent(
        event_id="e1",
        run_id="r1",
        parent_id=None,
        seq=0,
        ts="2026-01-01T00:00:00Z",
        kind="tool.call",
        name="t",
        payload=payload,
    )


def test_pii_is_redacted_not_dropped():
    keep = ("note",)
    cleaned, removed = DefaultMinimizer().minimize(
        [ev(note="mail me at alice@example.com")], keep_fields=keep
    )
    assert "alice@example.com" not in cleaned[0].payload["note"]
    assert "[REDACTED]" in cleaned[0].payload["note"]
    assert any("email" in r for r in removed)


def test_unknown_field_is_dropped_before_pii_ever_matters():
    cleaned, _ = DefaultMinimizer().minimize([ev(note="mail me at alice@example.com")])
    assert "note" not in cleaned[0].payload


def test_secret_fields_are_dropped_by_name():
    cleaned, removed = DefaultMinimizer().minimize(
        [ev(api_key="sk-abcdefghijklmnop123456", tool="x")]
    )
    assert cleaned[0].payload["api_key"] == "[REDACTED]"
    assert "tool" in cleaned[0].payload


def test_unknown_fields_are_dropped_not_kept():
    cleaned, removed = DefaultMinimizer().minimize([ev(some_random_field="keep me?")])
    assert "some_random_field" not in cleaned[0].payload
    assert any(r.startswith("dropped_field:") for r in removed)


def test_nested_scrub_reports_path():
    cleaned, removed = DefaultMinimizer().minimize(
        [ev(arguments={"token": "sk-abcdefghijklmnop123456"})]
    )
    assert cleaned[0].payload["arguments"]["token"] == "[REDACTED]"
    assert any("secret_field" in r for r in removed)
