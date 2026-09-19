"""The six plugin surfaces (SPI).

This module is the closest thing Vigil has to a constitution. It is allowed to
change slowly and only via RFC. Everything else moves fast.

Layering rule that keeps the project out of dependency hell:

    collector -> minimizer -> selector -> environment -> scorer -> gate

Data flows left to right only. A plugin may import `vigil.models.*` and
`vigil.cas`. It may NOT import another plugin's implementation. Cross-layer
needs go through the manifest, never through direct calls.

Core stays I/O-free: no network, no subprocess, no Docker SDK. Anything that
touches the outside world lives in a plugin.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from .models.case import CaseManifest
from .models.event import CanonicalEvent
from .models.gate import SLO, GateDecision
from .models.result import Aggregate, JudgeVerdict, RunResult

SPEC_VERSION = "v1alpha1"

# Entry point groups. Plugin packages declare these in pyproject.toml.
GROUP_COLLECTOR = "vigil.collectors"
GROUP_MINIMIZER = "vigil.minimizers"
GROUP_SELECTOR = "vigil.selectors"
GROUP_ENVIRONMENT = "vigil.environments"
GROUP_SCORER = "vigil.scorers"
GROUP_GATE = "vigil.gates"

ALL_GROUPS: tuple[str, ...] = (
    GROUP_COLLECTOR,
    GROUP_MINIMIZER,
    GROUP_SELECTOR,
    GROUP_ENVIRONMENT,
    GROUP_SCORER,
    GROUP_GATE,
)


class Plugin(Protocol):
    """Common metadata every plugin exposes."""

    name: str
    version: str


@runtime_checkable
class Collector(Plugin, Protocol):
    """Turn a vendor-native trace into canonical events.

    Contract:
      - must not invent events it did not see (mark observed=False instead)
      - must not resolve or re-fetch external content
      - must not write raw payloads to disk by itself
    """

    def collect(self, source: str, **options: Any) -> list[CanonicalEvent]: ...


@runtime_checkable
class Minimizer(Plugin, Protocol):
    """Reduce risk and volume: redaction, truncation, purpose limitation.

    Contract:
      - default deny: unknown fields are dropped, not kept
      - every removal is reported, so provenance stays auditable
    """

    def minimize(
        self, events: Sequence[CanonicalEvent], **options: Any
    ) -> tuple[list[CanonicalEvent], list[str]]: ...


@runtime_checkable
class Selector(Plugin, Protocol):
    """Decide which executions deserve to become cases.

    Contract:
      - selection is policy-driven and reproducible for the same input
      - selection never mutates events
    """

    def select(
        self, runs: Sequence[Sequence[CanonicalEvent]], **options: Any
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class EnvironmentProvider(Plugin, Protocol):
    """Stand the world back up, then tear it down.

    Contract:
      - restore() must be verifiable: return a digest or raise
      - destructive effects default to dry-run; live execution requires an
        explicit opt-in in the manifest's side_effect_policy
      - if the environment cannot guarantee restore, it must say so
    """

    def provision(self, contract: dict[str, Any]) -> EnvHandle: ...


@runtime_checkable
class EnvHandle(Protocol):
    def restore(self) -> str:
        """Return a digest of the restored state, or raise if unverifiable."""
        ...

    def execute(self, case: CaseManifest, agent: AgentCallable) -> RunResult: ...

    def teardown(self) -> None: ...


@runtime_checkable
class Scorer(Plugin, Protocol):
    """Produce one opinion about one run.

    Contract:
      - return None or abstain=True rather than guessing
      - always carry judge_version and, for LLM judges, prompt_digest
      - deterministic scorers must be deterministic (same digest -> same score)
    """

    def score(self, case: CaseManifest, result: RunResult) -> JudgeVerdict | None: ...


@runtime_checkable
class Gate(Plugin, Protocol):
    """Decide allow / warn / block.

    Contract:
      - hard SLO violations always block, regardless of statistics
      - a blocked decision must be explainable in one sentence per violation
    """

    def decide(self, aggregate: Aggregate, slos: Sequence[SLO]) -> GateDecision: ...


AgentCallable = Any  # (case: CaseManifest) -> RunResult, supplied by a harness


def protocol_names() -> dict[str, type]:
    """Expose protocols for conformance testing."""
    return {
        GROUP_COLLECTOR: Collector,
        GROUP_MINIMIZER: Minimizer,
        GROUP_SELECTOR: Selector,
        GROUP_ENVIRONMENT: EnvironmentProvider,
        GROUP_SCORER: Scorer,
        GROUP_GATE: Gate,
    }
