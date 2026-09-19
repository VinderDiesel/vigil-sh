"""Vigil (衡鉴) -- reliability assets for agent executions.

Execution  ->  CanonicalEvent  ->  CaseManifest  ->  Score  ->  GateArtifact

What this package deliberately is NOT:
  - not a tracing platform (Langfuse / LangSmith / Phoenix already exist)
  - not a benchmark leaderboard
  - not a promise that any agent execution can be deterministically replayed

See README.md (humans) and AGENTS.md (coding agents) before changing anything.
"""

__version__ = "0.1.0"
__spec_version__ = "v1alpha1"

from .models.case import CaseManifest
from .models.event import CanonicalEvent
from .models.gate import SLO, GateDecision
from .models.result import Aggregate, JudgeVerdict, RunResult

__all__ = [
    "__version__",
    "__spec_version__",
    "CaseManifest",
    "CanonicalEvent",
    "GateDecision",
    "SLO",
    "Aggregate",
    "JudgeVerdict",
    "RunResult",
]
