"""Gate decisions, SLO definitions and the failure taxonomy.

Two classes of gate, and they must never be mixed:
  HARD   -- deterministic safety/policy thresholds. No statistics, no
            baseline comparison, no waiver. (destructive action, PII leak,
            policy violation)
  STAT   -- reliability thresholds with a baseline comparison and an explicit
            minimum detectable effect. v1alpha1 ships HARD only, plus a
            non-blocking STAT report. See spec/v1alpha1/gate.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Decision = Literal["allow", "warn", "block"]

# v1alpha1 fixed taxonomy. Each entry must be decidable from evidence, not
# from vibes. `oracle_ambiguous` exists because eval systems fail most often
# by being wrong about the case, not about the agent.
FAILURE_TAXONOMY: dict[str, str] = {
    "tool_argument": "wrong or malformed arguments passed to a tool",
    "tool_permission": "tool called outside its authorized scope",
    "state_transition": "agent lost, corrupted or failed to restore state",
    "policy": "explicit policy / compliance violation",
    "oracle_ambiguous": "the case or oracle itself is wrong or unverifiable",
    "environment_flake": "failure originates in the environment, not the agent",
    "model_reasoning": "planning/reasoning error under a correct environment",
    "unobserved_side_effect": "effect happened but the collector could not see it",
}


def is_valid_label(label: str) -> bool:
    return label in FAILURE_TAXONOMY


@dataclass
class SLO:
    """One reliability objective. `hard` == non-negotiable."""

    metric: str
    op: Literal["min", "max", "max_slope", "eq"]
    value: float
    hard: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "op": self.op,
            "value": self.value,
            "hard": self.hard,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SLO:
        op = data.get("op")
        if op not in ("min", "max", "max_slope", "eq"):
            raise ValueError(f"unsupported SLO op={op!r}")
        return cls(
            metric=str(data["metric"]),
            op=op,
            value=float(data["value"]),
            hard=bool(data.get("hard", False)),
        )


@dataclass
class SLOViolation:
    slo: SLO
    observed: float
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "slo": self.slo.to_dict(),
            "observed": self.observed,
            "message": self.message,
        }


@dataclass
class GateDecision:
    """What CI should do, and -- critically -- why."""

    decision: Decision = "allow"
    hard_violations: list[SLOViolation] = field(default_factory=list)
    stat_violations: list[SLOViolation] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "hard_violations": [v.to_dict() for v in self.hard_violations],
            "stat_violations": [v.to_dict() for v in self.stat_violations],
            "reasons": list(self.reasons),
            "artifacts": dict(self.artifacts),
        }

    @property
    def exit_code(self) -> int:
        return 1 if self.decision == "block" else 0
