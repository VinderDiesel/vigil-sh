"""Data models. Dependency-free on purpose.

If a change here requires a third-party library, the change is wrong.
"""

from .case import CaseManifest, EnvironmentContract, Provenance
from .event import CanonicalEvent
from .gate import FAILURE_TAXONOMY, SLO, GateDecision, SLOViolation
from .result import Aggregate, JudgeVerdict, RunResult

__all__ = [
    "Aggregate",
    "CanonicalEvent",
    "CaseManifest",
    "EnvironmentContract",
    "FAILURE_TAXONOMY",
    "GateDecision",
    "JudgeVerdict",
    "Provenance",
    "RunResult",
    "SLO",
    "SLOViolation",
]
