"""Minimizer: default-deny field allowlist + regex redaction.

Tier: core.

The rule that matters: unknown fields are DROPPED, not kept. An eval case
that quietly carries a customer's email into a public CI log is worse than
an eval case that misses a signal.

`keep_fields` is intentionally small. Extending it is an RFC-grade change
because it changes the privacy boundary of every generated case.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from ..models.event import CanonicalEvent

# Only these payload keys survive minimization by default.
DEFAULT_KEEP: tuple[str, ...] = (
    "tool",
    "tool_name",
    "arguments",
    "arguments_digest",
    "status",
    "error",
    "error_type",
    "model",
    "prompt_digest",
    "completion_digest",
    "usage",
    "duration_ms",
    "return_shape",
    "reason",
)

# Keys that look like secrets but are not: token *counts* are usage metrics,
# not credentials. Mis-classifying them silently destroys cost/latency signal
# and makes people disable minimization altogether.
NOT_SECRET_PATTERN = re.compile(
    r"(?:tokens|token_count|tokenizer|usage|max_tokens|seed|timeout|ttl)$|_count$|_ms$"
)


def _looks_like_secret(key: str) -> bool:
    lowered = key.lower()
    if NOT_SECRET_PATTERN.search(lowered):
        return False
    return any(hint in lowered for hint in SECRET_FIELD_HINTS)


# Cheap, high-precision patterns. Deliberately not exhaustive: minimization is
# defense in depth, not the only control.
PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("phone_cn", re.compile(r"1[3-9]\d{9}")),
    ("id_card_cn", re.compile(r"\b\d{17}[\dXx]\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
    ("ipv4", re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")),
    ("jwt", re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+")),
    ("api_key", re.compile(r"\b(?:sk|pk|api|token|bearer)[-_][A-Za-z0-9]{16,}\b", re.I)),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)

REDACTED = "[REDACTED]"
SECRET_FIELD_HINTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "private_key",
)


def _redact_str(value: str) -> tuple[str, list[str]]:
    hits: list[str] = []
    out = value
    for label, pattern in PII_PATTERNS:
        if pattern.search(out):
            out = pattern.sub(REDACTED, out)
            hits.append(label)
    return out, hits


def _scrub(obj: Any, path: str, keep: Sequence[str], depth: int = 0) -> tuple[Any, list[str]]:
    """Recursively scrub. Returns (cleaned, [labels of what was removed])."""
    removed: list[str] = []
    if depth > 8:
        return "[TRUNCATED_DEPTH]", ["depth_limit"]

    if isinstance(obj, str):
        cleaned, hits = _redact_str(obj)
        removed.extend(f"{label}@{path or 'root'}" for label in hits)
        return cleaned, removed

    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            key_str = str(key)
            if _looks_like_secret(key_str):
                label = f"secret_field:{path}.{key_str}" if path else f"secret_field:{key_str}"
                removed.append(label)
                out[key_str] = REDACTED
                continue
            if keep and path == "" and key_str not in keep:
                # top-level payload keys are allowlisted
                removed.append(f"dropped_field:{key_str}")
                continue
            cleaned, hits = _scrub(value, f"{path}.{key_str}" if path else key_str, keep, depth + 1)
            removed.extend(hits)
            out[key_str] = cleaned
        return out, removed

    if isinstance(obj, list):
        out_list = []
        for idx, item in enumerate(obj):
            cleaned, hits = _scrub(item, f"{path}[{idx}]", keep, depth + 1)
            removed.extend(hits)
            out_list.append(cleaned)
        return out_list, removed

    return obj, removed


class DefaultMinimizer:
    name = "default"
    version = "0.1.0"

    def __init__(self, keep_fields: Sequence[str] | None = None) -> None:
        self.keep_fields = tuple(keep_fields or DEFAULT_KEEP)

    def minimize(
        self, events: Sequence[CanonicalEvent], **options: Any
    ) -> tuple[list[CanonicalEvent], list[str]]:
        keep = tuple(options.get("keep_fields") or self.keep_fields)
        report: list[str] = []
        cleaned_events: list[CanonicalEvent] = []

        for event in events:
            payload, removed = _scrub(event.payload, "", keep)
            meta, meta_removed = _scrub(event.meta, "meta", ())
            report.extend(removed + meta_removed)
            cleaned_events.append(
                CanonicalEvent(
                    event_id=event.event_id,
                    run_id=event.run_id,
                    parent_id=event.parent_id,
                    seq=event.seq,
                    ts=event.ts,
                    kind=event.kind,
                    name=event.name,
                    payload=payload,
                    effect_class=event.effect_class,
                    observed=event.observed,
                    meta=meta,
                )
            )

        # de-duplicate the report but keep it ordered and bounded
        seen: set[str] = set()
        ordered = []
        for item in report:
            if item not in seen:
                seen.add(item)
                ordered.append(item)
        return cleaned_events, ordered
