"""Selector: policy-driven choice of which runs deserve to become cases.

Tier: core.

Selection signals in v1alpha1 (deliberately few, all reproducible):
    failure          run ended in error
    human_handoff    a human took over
    destructive      an effect_class=destructive call occurred
    unobserved       collector had a visibility gap (observed=False anywhere)
    cost_ceiling     estimated cost above a threshold
    step_ceiling     step count above a threshold

Explicitly NOT in v1alpha1: semantic dedup / clustering. It is easy to build
and easy to get wrong in the most damaging way -- deleting the rare failure
that was the whole point of the case.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..models.event import CanonicalEvent

SIGNALS = (
    "failure",
    "human_handoff",
    "destructive",
    "unobserved",
    "cost_ceiling",
    "step_ceiling",
)


def _has(run: Sequence[CanonicalEvent], predicate: Any) -> bool:
    return any(predicate(e) for e in run)


class RulesSelector:
    name = "rules"
    version = "0.1.0"

    def select(
        self, runs: Sequence[Sequence[CanonicalEvent]], **options: Any
    ) -> list[dict[str, Any]]:
        wanted = set(options.get("signals") or ("failure", "human_handoff", "destructive"))
        cost_ceiling = float(options.get("cost_ceiling", 0.5))
        step_ceiling = int(options.get("step_ceiling", 40))
        limit = int(options.get("limit", 0))  # 0 == no limit

        picked: list[dict[str, Any]] = []
        for run in runs:
            if not run:
                continue
            run_id = run[0].run_id
            matched: list[str] = []

            if "failure" in wanted and _has(run, lambda e: e.kind == "error"):
                matched.append("failure")
            if "human_handoff" in wanted and _has(run, lambda e: e.kind == "human.handoff"):
                matched.append("human_handoff")
            if "destructive" in wanted and _has(run, lambda e: e.effect_class == "destructive"):
                matched.append("destructive")
            if "unobserved" in wanted and _has(run, lambda e: not e.observed):
                matched.append("unobserved")
            if "step_ceiling" in wanted and len(run) > step_ceiling:
                matched.append("step_ceiling")
            if "cost_ceiling" in wanted:
                total = sum(
                    float(e.payload.get("cost_usd", 0.0))
                    for e in run
                    if isinstance(e.payload.get("cost_usd"), (int, float))
                )
                if total > cost_ceiling:
                    matched.append("cost_ceiling")

            if not matched:
                continue
            picked.append(
                {
                    "run_id": run_id,
                    "signals": sorted(matched),
                    "steps": len(run),
                }
            )

        picked.sort(key=lambda item: (item["run_id"],))
        if limit:
            picked = picked[:limit]
        return picked
