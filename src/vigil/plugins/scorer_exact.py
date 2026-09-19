"""Scorer: deterministic exact / contains matching against the oracle.

Tier: core.

Deterministic scorers are the backbone of trust: they never drift, never need
calibration, and they are what LLM judges are later audited against. If a
case can be scored deterministically, it MUST be -- an LLM judge on a
deterministic case is wasted variance.
"""

from __future__ import annotations

import json
import re

from ..cas import canonical_bytes, digest_bytes
from ..models.case import CaseManifest
from ..models.result import JudgeVerdict, RunResult

# Oracle keys recognized in v1alpha1.
EXPECT_KEYS = ("exact", "contains", "regex", "not_contains")


def _output_of(result: RunResult) -> str:
    """Extract the agent's textual output from artifacts.

    v1alpha1 convention: agents write their final answer to
    artifacts["output"]. Anything else is scorer-specific and must be
    documented in the case.
    """
    value = result.artifacts.get("output")
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


class ExactScorer:
    name = "exact"
    version = "0.1.0"
    deterministic = True

    def score(self, case: CaseManifest, result: RunResult) -> JudgeVerdict | None:
        oracle = case.oracle or {}
        if not any(key in oracle for key in EXPECT_KEYS):
            # No opinion available: abstain rather than guess.
            return JudgeVerdict(
                judge=self.name,
                judge_version=self.version,
                abstain=True,
                rationale="oracle has no exact/contains/regex/not_contains key",
                prompt_digest=digest_bytes(canonical_bytes(oracle)),
            )

        output = _output_of(result)
        passed = True
        reasons: list[str] = []

        if "exact" in oracle:
            ok = output.strip() == str(oracle["exact"]).strip()
            passed &= ok
            reasons.append(f"exact: {'match' if ok else 'mismatch'}")
        if "contains" in oracle:
            needles = oracle["contains"]
            needles = [needles] if isinstance(needles, str) else list(needles)
            for needle in needles:
                ok = str(needle) in output
                passed &= ok
                reasons.append(f"contains({needle!r}): {ok}")
        if "not_contains" in oracle:
            needles = oracle["not_contains"]
            needles = [needles] if isinstance(needles, str) else list(needles)
            for needle in needles:
                ok = str(needle) not in output
                passed &= ok
                reasons.append(f"not_contains({needle!r}): {ok}")
        if "regex" in oracle:
            ok = re.search(str(oracle["regex"]), output) is not None
            passed &= ok
            reasons.append(f"regex: {ok}")

        return JudgeVerdict(
            judge=self.name,
            judge_version=self.version,
            score=1.0 if passed else 0.0,
            confidence=1.0,
            abstain=False,
            rationale="; ".join(reasons),
            prompt_digest=digest_bytes(canonical_bytes(oracle)),
        )


class ContainsScorer(ExactScorer):
    """Alias scorer kept for readability in case files."""

    name = "contains"
    version = "0.1.0"
