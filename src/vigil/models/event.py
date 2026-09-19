"""Canonical event: the single normalized unit Vigil understands.

Vigil never stores raw vendor traces as its source of truth. Every collector
must map its native format (OTel span, OpenInference span, Langfuse
observation, JSONL replay file) into this shape before anything downstream
runs.

Design rule (see spec/v1alpha1/event.md):
    raw -> canonical -> redacted
Three layers, three different hashes. Never collapse them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

EventKind = Literal[
    "run.start",
    "run.end",
    "llm.call",
    "tool.call",
    "tool.result",
    "state.checkpoint",
    "human.handoff",
    "error",
    "unknown",
]

# Effect class drives the safety policy. Anything not in this list is treated
# as `unknown`, and `unknown` is treated as potentially destructive.
EffectClass = Literal[
    "read",  # no observable external change
    "write",  # changes external state, reversible in principle
    "destructive",  # delete / pay / send / revoke -- irreversible
    "unknown",
]


@dataclass(frozen=True)
class CanonicalEvent:
    """One normalized step of an agent execution.

    `payload` is intentionally free-form: Vigil does not try to own the
    semantics of every framework. It owns the envelope, the hashes, and the
    safety tags -- that is enough for lineage, minimization and gating.
    """

    event_id: str
    run_id: str
    parent_id: str | None
    seq: int
    ts: str  # RFC3339 UTC
    kind: EventKind
    name: str  # tool name / model name / span name
    payload: dict[str, Any] = field(default_factory=dict)
    effect_class: EffectClass = "unknown"
    observed: bool = True  # False => collector had a visibility gap
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "parent_id": self.parent_id,
            "seq": self.seq,
            "ts": self.ts,
            "kind": self.kind,
            "name": self.name,
            "payload": self.payload,
            "effect_class": self.effect_class,
            "observed": self.observed,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CanonicalEvent:
        return cls(
            event_id=str(data["event_id"]),
            run_id=str(data["run_id"]),
            parent_id=data.get("parent_id"),
            seq=int(data.get("seq", 0)),
            ts=str(data.get("ts", "")),
            kind=data.get("kind", "unknown"),
            name=str(data.get("name", "")),
            payload=dict(data.get("payload") or {}),
            effect_class=data.get("effect_class", "unknown"),
            observed=bool(data.get("observed", True)),
            meta=dict(data.get("meta") or {}),
        )


def sort_key(event: CanonicalEvent) -> tuple[int, str, str]:
    """Deterministic ordering: seq first, then ts, then id.

    Never rely on wall-clock arrival order for canonicalization.
    """
    return (event.seq, event.ts, event.event_id)
