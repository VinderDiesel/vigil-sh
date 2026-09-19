"""Run outcome, judge verdicts and aggregated reliability metrics.

Core invariant: a judge may ABSTAIN. Abstention is a first-class outcome,
never coerced into 0.0, never silently averaged away. Disagreement between
judges is a quality signal, not noise to be smoothed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Outcome = Literal["PASS", "FAIL", "UNDETERMINED", "ERROR"]

# Priority when combining outcomes. ERROR/UNDETERMINED must never be
# downgraded to PASS just because one judge liked the output.
OUTCOME_RANK: dict[str, int] = {
    "PASS": 0,
    "UNDETERMINED": 1,
    "FAIL": 2,
    "ERROR": 3,
}


@dataclass
class JudgeVerdict:
    """One scorer's opinion about one run.

    `abstain=True` means "I have no reliable opinion here". The score field
    is then advisory only and must not be used for gating.
    """

    judge: str
    judge_version: str
    score: float | None = None
    confidence: float = 0.0
    abstain: bool = False
    rationale: str = ""
    prompt_digest: str = ""
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "judge": self.judge,
            "judge_version": self.judge_version,
            "score": self.score,
            "confidence": self.confidence,
            "abstain": self.abstain,
            "rationale": self.rationale,
            "prompt_digest": self.prompt_digest,
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JudgeVerdict:
        return cls(
            judge=str(data.get("judge", "unknown")),
            judge_version=str(data.get("judge_version", "0.0.0")),
            score=data.get("score"),
            confidence=float(data.get("confidence", 0.0)),
            abstain=bool(data.get("abstain", False)),
            rationale=str(data.get("rationale", "")),
            prompt_digest=str(data.get("prompt_digest", "")),
            evidence_refs=list(data.get("evidence_refs") or []),
        )


@dataclass
class RunResult:
    """The outcome of replaying/running one case once."""

    case_id: str
    outcome: Outcome = "ERROR"
    verdicts: list[JudgeVerdict] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    trace_ref: str = ""
    latency_ms: int = 0
    cost_usd: float = 0.0
    steps: int = 0
    intervention: bool = False  # human took over
    unrecoverable: bool = False  # retrying cannot help
    policy_violation: bool = False
    env_digest: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "outcome": self.outcome,
            "verdicts": [v.to_dict() for v in self.verdicts],
            "artifacts": dict(self.artifacts),
            "trace_ref": self.trace_ref,
            "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd,
            "steps": self.steps,
            "intervention": self.intervention,
            "unrecoverable": self.unrecoverable,
            "policy_violation": self.policy_violation,
            "env_digest": self.env_digest,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunResult:
        return cls(
            case_id=str(data.get("case_id", "")),
            outcome=data.get("outcome", "ERROR"),
            verdicts=[JudgeVerdict.from_dict(v) for v in data.get("verdicts") or []],
            artifacts=dict(data.get("artifacts") or {}),
            trace_ref=str(data.get("trace_ref", "")),
            latency_ms=int(data.get("latency_ms", 0)),
            cost_usd=float(data.get("cost_usd", 0.0)),
            steps=int(data.get("steps", 0)),
            intervention=bool(data.get("intervention", False)),
            unrecoverable=bool(data.get("unrecoverable", False)),
            policy_violation=bool(data.get("policy_violation", False)),
            env_digest=str(data.get("env_digest", "")),
            notes=str(data.get("notes", "")),
        )

    def combine_outcome(self, pass_threshold: float = 1.0) -> str:
        """Derive a case outcome from verdicts.

        ERROR is NOT computed here: it is set by the runner when execution
        itself blew up. An agent that self-reports ERROR must not be able to
        veto its own judges, and must not be able to claim one either.

        Rules, in order:
          1. no usable verdict       -> UNDETERMINED (never PASS)
          2. all usable verdicts FAIL-> FAIL
          3. all usable verdicts PASS-> PASS
          4. disagreement            -> UNDETERMINED + review flag
        """
        usable = self.usable_scores()
        if not usable:
            return "UNDETERMINED"
        fails = [score for score in usable if score < pass_threshold]
        if fails and len(fails) == len(usable):
            return "FAIL"
        if not fails:
            return "PASS"
        return "UNDETERMINED"

    def usable_scores(self) -> list[float]:
        """Scores from judges that did not abstain. Empty means "no opinion"."""
        return [float(v.score) for v in self.verdicts if not v.abstain and v.score is not None]

    def disagreement(self) -> float:
        """Spread of non-abstaining scores, 0..1. High spread => needs review."""
        usable = self.usable_scores()
        if len(usable) < 2:
            return 0.0
        return round(max(usable) - min(usable), 6)

    def needs_review(self) -> bool:
        return (
            self.combine_outcome() == "UNDETERMINED"
            or self.disagreement() >= 0.34
            or not any(not v.abstain for v in self.verdicts)
        )


@dataclass
class Aggregate:
    """Suite-level reliability numbers. These are the SLO inputs."""

    n: int = 0
    pass_rate: float = 0.0
    pass_at_k: dict[int, float] = field(default_factory=dict)
    p50_latency_ms: int = 0
    p95_latency_ms: int = 0
    p95_cost_usd: float = 0.0
    intervention_rate: float = 0.0
    unrecoverable_rate: float = 0.0
    policy_violations: int = 0
    flake_rate: float = 0.0
    needs_review_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "pass_rate": self.pass_rate,
            "pass_at_k": {str(k): v for k, v in sorted(self.pass_at_k.items())},
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "p95_cost_usd": self.p95_cost_usd,
            "intervention_rate": self.intervention_rate,
            "unrecoverable_rate": self.unrecoverable_rate,
            "policy_violations": self.policy_violations,
            "flake_rate": self.flake_rate,
            "needs_review_rate": self.needs_review_rate,
        }
