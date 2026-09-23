"""Minimal runner: manifest -> env -> execution -> scores -> verdict.

The runner owns orchestration only. It performs no I/O beyond what a plugin
does, and it never decides policy -- that is the gate's job.

Failure handling philosophy: a run that cannot be trusted reports
UNDETERMINED/ERROR rather than a comforting PASS. Silent optimism is the
single most expensive bug class in eval tooling.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .cas import canonical_bytes, cas_uri, digest_bytes
from .envbase import advisory_warnings
from .harness import LoadedAgent
from .models.case import DETERMINISTIC_MODES, CaseManifest
from .models.gate import SLO, Decision, GateDecision, SLOViolation
from .models.result import Aggregate, JudgeVerdict, RunResult
from .protocol import GROUP_ENVIRONMENT, GROUP_SCORER
from .registry import get

AgentCallable = Callable[[CaseManifest], RunResult]


def resolve_agent(agent: AgentCallable | str | LoadedAgent) -> LoadedAgent:
    """Accept a callable, a path, or a pre-resolved LoadedAgent.

    Remote environments need the path; in-process ones need the callable.
    LoadedAgent carries both.
    """
    return LoadedAgent.from_any(agent)


DEFAULT_ENV = "noop"
DEFAULT_SCORERS = ("exact",)


class RunnerError(RuntimeError):
    pass


@dataclass
class RunReport:
    case: CaseManifest
    result: RunResult
    env_digest: str = ""
    env_restored: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case": self.case.to_dict(),
            "result": self.result.to_dict(),
            "env_digest": self.env_digest,
            "env_restored": self.env_restored,
            "warnings": list(self.warnings),
        }


def run_case(
    case: CaseManifest,
    agent: AgentCallable,
    *,
    env_name: str = DEFAULT_ENV,
    scorers: Sequence[str] = DEFAULT_SCORERS,
    scorer_options: dict[str, Any] | None = None,
) -> RunReport:
    """Execute one case once. Returns a report; never raises for agent errors."""
    warnings: list[str] = []
    agent = resolve_agent(agent)

    if case.replay_mode == "record-only":
        warnings.append("replay_mode=record-only: no rerun guarantee is claimed")
    if not case.env.image and case.replay_mode in ("snapshot-replay", "sandbox-execute"):
        warnings.append(
            f"replay_mode={case.replay_mode} declared without env.image; "
            "treated as best-effort rerun"
        )
    if case.replay_mode == "live-canary":
        warnings.append("live-canary: only contract checks are meaningful")

    env_cls = get(GROUP_ENVIRONMENT, env_name)
    env = env_cls()
    warnings.extend(advisory_warnings(case.env.to_dict(), tuple(getattr(env, "capabilities", ()))))

    handle = env.provision(case.env.to_dict())
    env_digest = ""
    restored = False
    try:
        env_digest = handle.restore()
        restored = True
    except Exception as exc:  # noqa: BLE001 - env failure must degrade, not crash
        warnings.append(f"environment restore failed: {exc}")

    started = time.monotonic()
    execution_failed = False
    try:
        result = handle.execute(case, agent)
    except Exception as exc:  # noqa: BLE001
        result = RunResult(
            case_id=case.case_id,
            outcome="ERROR",
            notes=f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=5)}",
        )
        execution_failed = True
    elapsed = int((time.monotonic() - started) * 1000)
    if result.latency_ms == 0:
        result.latency_ms = elapsed
    result.env_digest = env_digest or result.env_digest

    options = scorer_options or {}
    for name in scorers:
        scorer_cls = get(GROUP_SCORER, name)
        scorer = scorer_cls(**options.get(name, {}))
        try:
            verdict = scorer.score(case, result)
        except Exception as exc:  # noqa: BLE001
            result.verdicts.append(
                JudgeVerdict(
                    judge=name,
                    judge_version=getattr(scorer, "version", "0.0.0"),
                    abstain=True,
                    rationale=f"scorer crashed: {type(exc).__name__}: {exc}",
                )
            )
            continue
        if verdict is None:
            verdict = JudgeVerdict(
                judge=name,
                judge_version=getattr(scorer, "version", "0.0.0"),
                abstain=True,
                rationale="scorer returned None (explicit abstention)",
            )
        result.verdicts.append(verdict)

    # The agent's self-reported outcome is informational only; verdicts decide.
    if result.outcome not in ("PASS", "FAIL", "UNDETERMINED", "ERROR"):
        warnings.append(f"agent reported unknown outcome {result.outcome!r}; ignored")

    if execution_failed:
        # Execution blew up: no verdict can rescue it, and no verdict should
        # be allowed to hide it.
        result.outcome = "ERROR"
    elif not restored:
        # An unverified environment cannot support a PASS claim.
        result.outcome = "UNDETERMINED"
        warnings.append("outcome forced to UNDETERMINED: environment not verified")
    elif case.expired:
        # Expired cases cannot gate (spec/v1alpha1/manifest.md). The ERROR
        # path above still wins, and policy_violation flags on the result are
        # untouched: expiry must never hide a safety signal (HARD-7).
        result.outcome = "UNDETERMINED"
        warnings.append("outcome forced to UNDETERMINED: case expired, cannot gate")
    else:
        result.outcome = result.combine_outcome()

    try:
        handle.teardown()
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"teardown failed: {exc}")

    return RunReport(
        case=case,
        result=result,
        env_digest=env_digest,
        env_restored=restored,
        warnings=warnings,
    )


def run_suite(
    cases: Sequence[CaseManifest],
    agent: AgentCallable,
    *,
    env_name: str = DEFAULT_ENV,
    scorers: Sequence[str] = DEFAULT_SCORERS,
    repeats: int = 1,
) -> tuple[list[RunReport], Aggregate]:
    """Run every case `repeats` times. repeats>1 exposes flakiness."""
    reports: list[RunReport] = []
    for case in cases:
        for _ in range(max(1, repeats)):
            reports.append(run_case(case, agent, env_name=env_name, scorers=scorers))
    return reports, aggregate(reports)


def _percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def aggregate(reports: Sequence[RunReport]) -> Aggregate:
    if not reports:
        return Aggregate()

    results = [r.result for r in reports]
    n = len(results)
    passed = sum(1 for r in results if r.outcome == "PASS")

    by_case: dict[str, list[RunResult]] = {}
    for r in results:
        by_case.setdefault(r.case_id, []).append(r)

    flaky = sum(
        1 for runs in by_case.values() if len(runs) > 1 and len({x.outcome for x in runs}) > 1
    )
    case_count = len(by_case) or 1
    max_runs = max((len(runs) for runs in by_case.values()), default=0)
    # pass_at_k[k]: share of cases with at least one PASS among their first k runs.
    pass_at_k = {
        k: round(
            sum(1 for runs in by_case.values() if any(r.outcome == "PASS" for r in runs[:k]))
            / case_count,
            6,
        )
        for k in range(1, max_runs + 1)
    }

    return Aggregate(
        n=n,
        pass_rate=round(passed / n, 6),
        pass_at_k=pass_at_k,
        p50_latency_ms=int(_percentile([r.latency_ms for r in results], 50)),
        p95_latency_ms=int(_percentile([r.latency_ms for r in results], 95)),
        p95_cost_usd=round(_percentile([r.cost_usd for r in results], 95), 6),
        intervention_rate=round(sum(1 for r in results if r.intervention) / n, 6),
        unrecoverable_rate=round(sum(1 for r in results if r.unrecoverable) / n, 6),
        policy_violations=sum(1 for r in results if r.policy_violation),
        flake_rate=round(flaky / case_count, 6),
        needs_review_rate=round(sum(1 for r in results if r.needs_review()) / n, 6),
    )


def evaluate_slos(
    aggregate: Aggregate, slos: Sequence[SLO]
) -> tuple[list[SLOViolation], list[SLOViolation]]:
    """Split violations into hard (block) and soft (report) buckets."""
    observed = {
        "pass_rate": aggregate.pass_rate,
        "p95_latency_ms": float(aggregate.p95_latency_ms),
        "p95_cost_usd": aggregate.p95_cost_usd,
        "intervention_rate": aggregate.intervention_rate,
        "unrecoverable_rate": aggregate.unrecoverable_rate,
        "policy_violations": float(aggregate.policy_violations),
        "flake_rate": aggregate.flake_rate,
        "needs_review_rate": aggregate.needs_review_rate,
        "n": float(aggregate.n),
    }
    hard: list[SLOViolation] = []
    soft: list[SLOViolation] = []
    for slo in slos:
        value = observed.get(slo.metric)
        if value is None:
            soft.append(
                SLOViolation(slo, float("nan"), f"metric {slo.metric} not produced by this run")
            )
            continue
        ok = value >= slo.value if slo.op == "min" else value <= slo.value
        if ok:
            continue
        violation = SLOViolation(
            slo,
            value,
            f"{slo.metric}={value} violates {slo.op} {slo.value}",
        )
        (hard if slo.hard else soft).append(violation)
    return hard, soft


def decide(aggregate: Aggregate, slos: Sequence[SLO], gate_name: str = "hard") -> GateDecision:
    hard, soft = evaluate_slos(aggregate, slos)
    decision: Decision = "block" if hard else ("warn" if soft else "allow")

    # Statistical comparison is deliberately NOT implemented in v1alpha1.
    # Gating on "pass_rate +0.5%" without a declared minimum detectable
    # effect is how teams learn to ignore their own CI.
    reasons = [v.message for v in hard] + [v.message for v in soft]
    if soft and not hard:
        reasons.append(
            "soft SLO violated; statistical gating is not enabled in v1alpha1 "
            "and this does not block the build"
        )
    return GateDecision(
        decision=decision,
        hard_violations=hard,
        stat_violations=soft,
        reasons=reasons,
    )


def suite_fingerprint(reports: Sequence[RunReport]) -> str:
    """Stable identity of a suite run, for PR comments and regression diffs."""
    payload = [
        {
            "case_id": r.case.case_id,
            "outcome": r.result.outcome,
            "env_digest": r.env_digest,
            "verdicts": [v.to_dict() for v in r.result.verdicts],
        }
        for r in sorted(reports, key=lambda x: x.case.case_id)
    ]
    return cas_uri(payload)


def digest_of(obj: Any) -> str:
    return digest_bytes(canonical_bytes(obj))


__all__ = [
    "RunReport",
    "RunnerError",
    "run_case",
    "run_suite",
    "aggregate",
    "evaluate_slos",
    "decide",
    "suite_fingerprint",
    "DETERMINISTIC_MODES",
]
