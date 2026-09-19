"""Minimal in-memory agent used by the v0.1 demo.

It is intentionally dumb: a lookup table keyed by case input. That is the
point -- the first end-to-end loop should prove the ASSET CHAIN works
(collect -> mint -> run -> gate), not that the agent is smart.

Agents used with Vigil must expose:

    def run(case: CaseManifest) -> RunResult: ...

The agent owns its own output contract; Vigil owns the contract around it.
"""

from vigil.models.result import RunResult

TABLE = {
    "refund-policy": "Refunds are allowed within 14 days with the original receipt.",
    "shipping-window": "Standard shipping takes 3-5 business days.",
    "unknown-intent": "I could not determine the intent; escalating to a human.",
}


def run(case):
    question = case.input.get("question", "")
    answer = TABLE.get(question, TABLE["unknown-intent"])
    escalated = question not in TABLE
    return RunResult(
        case_id=case.case_id,
        outcome="PASS",  # provisional; the runner recomputes from verdicts
        artifacts={"output": answer},
        steps=1,
        intervention=escalated,
        cost_usd=0.002,
    )
