"""The conformance helpers are part of the public surface: third-party
packages import them. They therefore need their own tests."""

import pytest

from vigil import conformance
from vigil.models.event import CanonicalEvent
from vigil.protocol import GROUP_MINIMIZER, GROUP_SCORER
from vigil.registry import RegistryError, get


def test_registered_plugins_lists_builtins():
    entries = conformance.registered_plugins()
    groups = {group for group, _, _ in entries}
    assert "vigil.collectors" in groups
    assert ("vigil.collectors", "otel", get("vigil.collectors", "otel")) in entries


def test_metadata_check_rejects_anonymous_plugin():
    class Anon:
        pass

    with pytest.raises(AssertionError):
        conformance.assert_plugin_metadata("vigil.scorers", "anon", Anon)


def test_signature_check_requires_annotations():
    class Bad:
        def score(self, case, result):
            return None

    class Good:
        def score(self, case, result):
            return None

    Good.score.__annotations__ = {"case": "CaseManifest", "result": "RunResult", "return": object}
    with pytest.raises(AssertionError):
        conformance.assert_signatures_annotated(Bad)
    conformance.assert_signatures_annotated(Good)


def test_collector_contract_on_otel_sample():
    cls = get("vigil.collectors", "otel")
    events = conformance.assert_collector_contract(cls, "examples/otel-export/trace.otlp.json")
    assert events


def test_minimizer_contract_catches_a_leak():
    class Leaky:
        name = "leaky"
        version = "0.0.0"

        def minimize(self, events, **options):
            return list(events), []

    events = [
        CanonicalEvent(
            event_id="e1",
            run_id="r1",
            parent_id=None,
            seq=0,
            ts="",
            kind="tool.call",
            name="t",
            payload={"note": "mail alice@example.com now"},
        )
    ]
    with pytest.raises(AssertionError):
        conformance.assert_minimizer_contract(Leaky, events, ["alice@example.com"])


def test_scorer_contract_on_builtin():
    conformance.assert_scorer_contract(get(GROUP_SCORER, "exact"))


def test_gate_contract_on_builtin():
    conformance.assert_gate_contract(get("vigil.gates", "hard"))


def test_check_plugin_unknown_name():
    with pytest.raises(AssertionError):
        conformance.check_plugin(GROUP_SCORER, "does-not-exist")


def test_check_plugin_runs_minimizer_contract():
    events = [
        CanonicalEvent(
            event_id="e1",
            run_id="r1",
            parent_id=None,
            seq=0,
            ts="",
            kind="tool.call",
            name="t",
            payload={},
        )
    ]
    conformance.check_plugin(GROUP_MINIMIZER, "default", minimize_events=events)


def test_environment_contract_accepts_declared_capabilities():
    from vigil.plugins.env_noop import NoopEnvironment

    conformance.assert_environment_contract(NoopEnvironment)


def test_no_heavy_import_rejects_sdk_modules():
    with pytest.raises(AssertionError):
        conformance.assert_no_heavy_import("docker.models.containers")


def test_registry_rejects_unknown_group():
    with pytest.raises(RegistryError):
        get("vigil.nope", "x")
