"""Gate: hard-threshold gate.

Tier: core.

v1alpha1 ships ONLY hard gates. Reasons, in order of importance:

  1. A soft reliability gate without a declared minimum detectable effect
     teaches teams to rerun CI until it goes green.
  2. Safety thresholds (destructive action, PII leak, policy violation) must
     never be subject to a statistical waiver.
  3. Statistical gating (bootstrap / McNemar / sequential) is planned for
     v0.2 behind an explicit `--stat-test` flag and its own conformance
     suite. Until then it must not exist half-built.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..models.gate import SLO, Decision, GateDecision
from ..models.result import Aggregate


class HardGate:
    name = "hard"
    version = "0.1.0"

    def decide(self, aggregate: Aggregate, slos: Sequence[SLO]) -> GateDecision:
        from ..runner import evaluate_slos  # local import: keep gate import-light

        hard, soft = evaluate_slos(aggregate, slos)
        decision: Decision = "block" if hard else ("warn" if soft else "allow")
        reasons = [v.message for v in hard]
        if soft:
            reasons.append(
                f"{len(soft)} soft SLO violation(s) reported; statistical gating "
                "is not enabled in v1alpha1"
            )
        return GateDecision(
            decision=decision,
            hard_violations=hard,
            stat_violations=soft,
            reasons=reasons,
        )
