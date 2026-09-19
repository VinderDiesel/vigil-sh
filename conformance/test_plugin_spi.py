"""Conformance suite: the mechanism that keeps the plugin ecosystem honest.

A plugin that does not pass these tests must not be published to the
registry, and must not be described as "supported" in any doc.

Third-party packages reuse the same helpers -- that is the point of putting
them in `vigil.conformance` instead of in a test file:

    from vigil.conformance import assert_scorer_contract

    def test_my_scorer():
        assert_scorer_contract(MyScorer)
"""

import json

import pytest

from vigil import conformance
from vigil.conformance import registered_plugins
from vigil.models.event import CanonicalEvent
from vigil.plugins.collector_file import FileCollector
from vigil.plugins.minimizer_default import DefaultMinimizer
from vigil.protocol import (
    ALL_GROUPS,
    GROUP_COLLECTOR,
    GROUP_ENVIRONMENT,
    GROUP_GATE,
    GROUP_MINIMIZER,
    GROUP_SCORER,
    GROUP_SELECTOR,
)
from vigil.registry import RegistryError, discover, get

TRACE = "examples/minimal-agent/trace.jsonl"
OTEL = "examples/otel-export/trace.otlp.json"

# Secrets present in the sample traces. If a plugin lets any of these reach an
# artifact, the suite fails -- this is the privacy regression detector.
FORBIDDEN = ["alice@example.com", "sk-abcdefghijklmnop123456"]

SAMPLES = {
    "file": {"collect_sample": TRACE},
    "otel": {"collect_sample": OTEL},
}


def _event(**payload):
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


# ---- structural checks over everything installed ---------------------------


@pytest.mark.conformance
def test_unique_names_per_group():
    for group in ALL_GROUPS:
        conformance.assert_unique_names(group)


@pytest.mark.conformance
@pytest.mark.parametrize("group,name,cls", registered_plugins(), ids=lambda v: str(v)[:40])
def test_plugin_metadata(group, name, cls):
    conformance.assert_plugin_metadata(group, name, cls)


@pytest.mark.conformance
@pytest.mark.parametrize("group,name,cls", registered_plugins(), ids=lambda v: str(v)[:40])
def test_protocol_conformance(group, name, cls):
    conformance.assert_protocol_conformance(group, cls)


@pytest.mark.conformance
@pytest.mark.parametrize("group,name,cls", registered_plugins(), ids=lambda v: str(v)[:40])
def test_annotated_signatures(group, name, cls):
    conformance.assert_signatures_annotated(cls)


@pytest.mark.conformance
def test_registry_rejects_unknown_group():
    with pytest.raises(RegistryError):
        discover("vigil.nonexistent")


# ---- collectors ------------------------------------------------------------


@pytest.mark.conformance
@pytest.mark.parametrize("name", ["file", "otel"])
def test_collector_contract(name):
    cls = get(GROUP_COLLECTOR, name)
    conformance.assert_collector_contract(cls, SAMPLES[name]["collect_sample"])


@pytest.mark.conformance
def test_collected_events_are_ordered_and_typed():
    events = FileCollector().collect(TRACE)
    assert all(isinstance(e, CanonicalEvent) for e in events)
    assert [e.seq for e in events] == sorted(e.seq for e in events)


# ---- minimizers ------------------------------------------------------------


@pytest.mark.conformance
def test_minimizer_holds_the_privacy_line():
    events = FileCollector().collect(TRACE)
    conformance.assert_minimizer_contract(get(GROUP_MINIMIZER, "default"), events, FORBIDDEN)


@pytest.mark.conformance
def test_minimizer_drops_unknown_fields_rather_than_keeping_them():
    cleaned, removed = DefaultMinimizer().minimize([_event(some_random_field="keep me?")])
    assert "some_random_field" not in cleaned[0].payload
    assert any(r.startswith("dropped_field:") for r in removed)


# ---- selectors -------------------------------------------------------------


@pytest.mark.conformance
def test_selector_is_reproducible():
    events = FileCollector().collect(TRACE)
    runs: dict[str, list[CanonicalEvent]] = {}
    for event in events:
        runs.setdefault(event.run_id, []).append(event)
    conformance.assert_selector_contract(get(GROUP_SELECTOR, "rules"), list(runs.values()))


# ---- environments ----------------------------------------------------------


@pytest.mark.conformance
def test_environment_declares_capabilities_and_refuses_what_it_cannot_do():
    conformance.assert_environment_contract(get(GROUP_ENVIRONMENT, "noop"))


@pytest.mark.conformance
def test_noop_environment_refuses_live_side_effects():
    from vigil.envbase import CapabilityError

    env_cls = get(GROUP_ENVIRONMENT, "noop")
    with pytest.raises(CapabilityError):
        env_cls().provision({"side_effect_policy": "live", "network_policy": "none"})


# ---- scorers ---------------------------------------------------------------


@pytest.mark.conformance
@pytest.mark.parametrize("name", ["exact", "contains"])
def test_scorer_abstains_instead_of_guessing(name):
    conformance.assert_scorer_contract(get(GROUP_SCORER, name))


# ---- gates -----------------------------------------------------------------


@pytest.mark.conformance
def test_gate_never_waives_a_hard_slo():
    conformance.assert_gate_contract(get(GROUP_GATE, "hard"))


# ---- core hygiene ----------------------------------------------------------


@pytest.mark.conformance
def test_core_imports_no_heavy_sdk():
    """HARD-4: heavy SDKs belong in separate distributions, never in core."""
    import sys

    for module_name in list(sys.modules):
        if module_name.startswith("vigil."):
            conformance.assert_no_heavy_import(module_name)


@pytest.mark.conformance
def test_artifacts_never_contain_secrets_from_samples():
    """End-to-end privacy guard: run the demo suite and grep the output."""
    from vigil.artifacts import write_json_report
    from vigil.models.case import CaseManifest
    from vigil.models.result import RunResult
    from vigil.runner import decide, run_suite

    cases = [
        CaseManifest(case_id="c1", oracle={"exact": "ok"}, replay_mode="mock-replay"),
    ]

    def agent(case):
        return RunResult(case_id=case.case_id, artifacts={"output": "ok"})

    reports, agg = run_suite(cases, agent)
    decision = decide(agg, [])
    path = "/tmp/vigil-conformance-report.json"
    write_json_report(path, reports, agg, decision, "fingerprint")
    with open(path, encoding="utf-8") as fh:
        blob = json.dumps(json.load(fh))
    for secret in FORBIDDEN:
        assert secret not in blob
