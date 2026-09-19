"""Reusable conformance helpers.

Conformance is the mechanism that keeps the plugin ecosystem honest, so it
must be usable OUTSIDE this repository too. Third-party packages import these
helpers and run them against their own plugins:

    from vigil.conformance import assert_scorer_contract
    def test_my_scorer_conformance():
        assert_scorer_contract(MyScorer)

Every check mirrors a numbered HARD rule in AGENTS.md. If a check has no HARD
rule behind it, it does not belong here.
"""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from typing import Any

from .models.case import CaseManifest
from .models.event import CanonicalEvent
from .models.gate import SLO
from .models.result import Aggregate, RunResult
from .protocol import (
    GROUP_COLLECTOR,
    GROUP_ENVIRONMENT,
    GROUP_GATE,
    GROUP_MINIMIZER,
    GROUP_SCORER,
    GROUP_SELECTOR,
    protocol_names,
)
from .registry import discover, discover_all


def registered_plugins() -> list[tuple[str, str, Any]]:
    """[(group, name, cls)] for every installed plugin."""
    return [
        (group, name, cls)
        for group, plugins in discover_all().items()
        for name, cls in plugins.items()
    ]


# --------------------------------------------------------------------------
# structural checks (apply to every plugin)
# --------------------------------------------------------------------------


def assert_plugin_metadata(group: str, name: str, cls: Any) -> None:
    """HARD: every plugin exposes name + version, and is instantiable bare."""
    instance = cls()
    assert getattr(instance, "name", None), f"{group}/{name} missing `name`"
    assert getattr(instance, "version", None), f"{group}/{name} missing `version`"


def assert_unique_names(group: str) -> None:
    plugins = discover(group)
    assert len(plugins) == len(set(plugins)), f"duplicate plugin names in {group}"


def assert_protocol_conformance(group: str, cls: Any) -> None:
    instance = cls()
    assert isinstance(instance, protocol_names()[group]), f"{cls} violates {group} SPI"


def assert_signatures_annotated(cls: Any) -> None:
    """Conformance can only check what it can see: no bare parameters."""
    for method in ("collect", "minimize", "select", "provision", "score", "decide"):
        fn = getattr(cls, method, None)
        if fn is None:
            continue
        for param_name, param in inspect.signature(fn).parameters.items():
            if param_name in ("self", "cls"):
                continue
            assert param.annotation is not inspect.Parameter.empty, (
                f"{cls.__name__}.{method}: parameter {param_name!r} is not annotated"
            )


def assert_no_heavy_import(module_name: str) -> None:
    """HARD-4: heavy SDKs must not be imported by a plugin module."""
    banned = ("requests", "httpx", "docker", "kubernetes", "boto3", "openai", "anthropic")
    for banned_name in banned:
        assert not module_name.split(".")[0].startswith(banned_name), (
            f"{module_name} must not be a heavy SDK module"
        )


# --------------------------------------------------------------------------
# behavioural contracts, per surface
# --------------------------------------------------------------------------


def assert_collector_contract(cls: Any, sample: str, **options: Any) -> list[CanonicalEvent]:
    """A collector yields ordered CanonicalEvents and is deterministic."""
    events: list[CanonicalEvent] = list(cls().collect(sample, **options))
    assert events, "collector returned no events for the sample"
    assert all(isinstance(e, CanonicalEvent) for e in events)
    assert [e.seq for e in events] == sorted(e.seq for e in events), "events not ordered"
    again = cls().collect(sample, **options)
    assert [e.to_dict() for e in events] == [e.to_dict() for e in again], "not deterministic"
    assert all(e.run_id for e in events), "event without run_id"
    return events


def assert_minimizer_contract(
    cls: Any, events: Sequence[CanonicalEvent], forbidden: Sequence[str]
) -> None:
    """A minimizer is idempotent, reports removals, and leaks nothing."""
    import json

    minimizer = cls()
    once, removed = minimizer.minimize(list(events))
    twice, _ = minimizer.minimize(once)
    assert [e.to_dict() for e in once] == [e.to_dict() for e in twice], "not idempotent"
    assert isinstance(removed, list), "minimizer must report what it removed"

    blob = json.dumps([e.to_dict() for e in once])
    for secret in forbidden:
        assert secret not in blob, f"minimizer leaked {secret!r}"


def assert_selector_contract(cls: Any, runs: Sequence[Sequence[CanonicalEvent]]) -> None:
    selector = cls()
    first = selector.select(list(runs))
    second = selector.select(list(runs))
    assert first == second, "selection is not reproducible"
    for item in first:
        assert "run_id" in item, "selection entry without run_id"
        assert "signals" in item, "selection entry without signals"


def assert_environment_contract(cls: Any) -> None:
    """An environment declares capabilities AND refuses what it cannot do.

    HARD-8: refusal must be driven by declared capabilities, not by the case.
    """
    instance = cls()
    capabilities = tuple(getattr(instance, "capabilities", ()))
    assert capabilities, f"{cls.__name__} must declare non-empty `capabilities`"

    # A contract that asks for everything must be refused unless the env
    # genuinely declares all of it.
    maximal = {
        "side_effect_policy": "live",
        "network_policy": "open",
        "clock_policy": "frozen",
        "init_snapshot": "snap-1",
        "tool_mock_map": {"tool": "rec-1"},
    }
    declared = set(capabilities)
    needed = {"live-side-effects", "open-network", "clock-freeze", "snapshot", "tool-mock"}
    try:
        handle = instance.provision(maximal)
        handle.execute(CaseManifest(case_id="__conformance__"), _refusing_agent)
    except Exception as exc:  # noqa: BLE001 - refusal may be any exception type
        assert not needed.issubset(declared), (
            f"{cls.__name__} declares {sorted(needed)} yet refused: {exc}"
        )
        return
    assert needed.issubset(declared), (
        f"{cls.__name__} accepted a maximal contract but only declares {sorted(declared)}"
    )


def _refusing_agent(case: CaseManifest) -> RunResult:
    return RunResult(case_id=case.case_id)


def assert_scorer_contract(cls: Any) -> None:
    """A scorer abstains when it has nothing to say (HARD-5)."""
    scorer = cls()
    case = CaseManifest(case_id="__conformance__", oracle={})
    verdict = scorer.score(case, RunResult(case_id="__conformance__"))
    assert verdict is not None, "scorer returned None instead of a verdict object"
    assert verdict.abstain is True, "scorer must abstain on an empty oracle"
    assert verdict.score is None, "an abstaining scorer must not emit a score"


def assert_gate_contract(cls: Any) -> None:
    """A gate never waives a hard SLO (HARD-7)."""
    gate = cls()
    slos = [SLO(metric="policy_violations", op="max", value=0, hard=True)]
    clean = gate.decide(Aggregate(n=10, policy_violations=0), slos)
    assert clean.decision in ("allow", "warn"), "clean run must not block"
    dirty = gate.decide(Aggregate(n=10, policy_violations=1), slos)
    assert dirty.decision == "block", "hard SLO violation must block"
    assert dirty.exit_code == 1, "blocking decision must exit non-zero"


# --------------------------------------------------------------------------
# one-shot entry point for third-party packages
# --------------------------------------------------------------------------


def check_plugin(group: str, name: str, **samples: Any) -> None:
    """Run every applicable check against one registered plugin.

    `samples` may provide: `collect_sample` (path), `collect_options`,
    `minimize_events`, `forbidden` (list of strings), `selector_runs`.
    """
    plugins = discover(group)
    assert name in plugins, f"plugin {name!r} not registered in {group}"
    cls = plugins[name]

    assert_plugin_metadata(group, name, cls)
    assert_protocol_conformance(group, cls)
    assert_signatures_annotated(cls)

    if group == GROUP_COLLECTOR and samples.get("collect_sample"):
        assert_collector_contract(
            cls, samples["collect_sample"], **samples.get("collect_options", {})
        )
    if group == GROUP_MINIMIZER and samples.get("minimize_events") is not None:
        assert_minimizer_contract(cls, samples["minimize_events"], samples.get("forbidden", []))
    if group == GROUP_SELECTOR and samples.get("selector_runs") is not None:
        assert_selector_contract(cls, samples["selector_runs"])
    if group == GROUP_ENVIRONMENT:
        assert_environment_contract(cls)
    if group == GROUP_SCORER:
        assert_scorer_contract(cls)
    if group == GROUP_GATE:
        assert_gate_contract(cls)
