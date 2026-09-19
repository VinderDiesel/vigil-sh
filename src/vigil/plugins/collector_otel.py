"""Collector: OTLP JSON -> CanonicalEvent.

Tier: core. Stdlib only -- OTLP/HTTP and OTLP/file exporters both commonly
emit JSON (`{"resourceSpans": [...]}`), which needs no protobuf dependency.

What this collector does and does not promise:
  * it maps OpenTelemetry spans (including the GenAI semantic conventions,
    whose spec is still moving) onto CanonicalEvent;
  * it does NOT reconstruct container state, secrets, external API responses
    or oracles. OTel carries telemetry, not the world (see README §3).

Effect classification is heuristic and conservative: anything unrecognised is
`unknown`, and `unknown` is treated as potentially destructive downstream.
"""

from __future__ import annotations

import json
from typing import Any, cast

from ..models.event import CanonicalEvent, EffectClass, EventKind

# --- span kind detection ----------------------------------------------------
# Keys are attribute-name fragments; first match wins.
EVENT_KIND_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("gen_ai.request.model", "gen_ai.response.model", "llm.request", "llm.response"), "llm.call"),
    (("gen_ai.tool.name", "tool.name", "mcp.tool.name", "function.name"), "tool.call"),
    (("gen_ai.tool.result", "tool.result", "mcp.tool.result"), "tool.result"),
    (("human.handoff", "handoff", "escalation"), "human.handoff"),
    (("checkpoint",), "state.checkpoint"),
    (("error.type", "exception.type", "status.code"), "error"),
)

DESTRUCTIVE_HINTS = (
    "delete",
    "remove",
    "revoke",
    "cancel",
    "refund",
    "pay",
    "charge",
    "transfer",
    "send",
    "publish",
    "drop",
    "truncate",
    "terminate",
)

WRITE_HINTS = (
    "create",
    "update",
    "write",
    "insert",
    "upsert",
    "patch",
    "append",
    "set",
    "submit",
    "place_order",
)

READ_HINTS = (
    "get",
    "list",
    "read",
    "search",
    "query",
    "fetch",
    "lookup",
    "retrieve",
    "find",
    "describe",
)


def _attrs_of(span: dict[str, Any]) -> dict[str, Any]:
    """Flatten OTLP attributes (list of {key, value:{...}}) into a dict."""
    flat: dict[str, Any] = {}
    for attr in span.get("attributes") or []:
        key = attr.get("key")
        if key is None:
            continue
        value = attr.get("value") or {}
        for field in ("stringValue", "string_value", "boolValue", "intValue", "doubleValue"):
            if field in value:
                flat[key] = value[field]
                break
        else:
            if "arrayValue" in value:
                flat[key] = value["arrayValue"]
            elif "array_value" in value:
                flat[key] = value["array_value"]
    return flat


def _detect_kind(name: str, attrs: dict[str, Any], status: str) -> EventKind:
    lowered_name = name.lower()
    keys = {key.lower() for key in attrs}
    for hints, kind in EVENT_KIND_HINTS:
        if any(hint.lower() in keys for hint in hints):
            return cast(EventKind, kind)
    if status == "error":
        return "error"
    for token, kind in (
        ("llm", "llm.call"),
        ("chat", "llm.call"),
        ("completion", "llm.call"),
        ("tool", "tool.call"),
        ("handoff", "human.handoff"),
        ("escalat", "human.handoff"),
        ("checkpoint", "state.checkpoint"),
    ):
        if token in lowered_name:
            return cast(EventKind, kind)
    return "unknown"


def _classify_effect(name: str, attrs: dict[str, Any]) -> EffectClass:
    declared = attrs.get("vigil.effect_class") or attrs.get("effect_class")
    if declared in ("read", "write", "destructive"):
        return cast(EffectClass, declared)
    lowered = name.lower()
    for group, label in (
        (DESTRUCTIVE_HINTS, "destructive"),
        (WRITE_HINTS, "write"),
        (READ_HINTS, "read"),
    ):
        if any(token in lowered for token in group):
            return cast(EffectClass, label)
    return "unknown"


def _span_status(span: dict[str, Any]) -> str:
    status = span.get("status") or {}
    code = status.get("code") or status.get("status_code") or ""
    if isinstance(code, int):
        return "error" if code >= 2 else "ok"
    return "error" if str(code).upper().endswith("ERROR") else "ok"


def _walk_spans(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for resource_span in payload.get("resourceSpans") or []:
        for scope_span in resource_span.get("scopeSpans") or []:
            spans.extend(scope_span.get("spans") or [])
    # tolerate a bare list of spans, and the snake_case variant
    if not spans:
        for resource_span in payload.get("resource_spans") or []:
            for scope_span in resource_span.get("scope_spans") or []:
                spans.extend(scope_span.get("spans") or [])
    return spans


class OTelCollector:
    """Collect canonical events from an OTLP JSON export."""

    name = "otel"
    version = "0.1.0"

    def collect(self, source: str, **options: Any) -> list[CanonicalEvent]:
        payloads = self._load(source)
        events: list[CanonicalEvent] = []
        run_ids: dict[str, str] = {}

        for payload in payloads:
            for span in _walk_spans(payload):
                trace_id = span.get("traceId") or span.get("trace_id") or ""
                span_id = span.get("spanId") or span.get("span_id") or ""
                parent = span.get("parentSpanId") or span.get("parent_span_id") or None

                # A trace maps to one run; a span with no parent opens the run.
                run_id = run_ids.get(trace_id) or trace_id or span_id
                run_ids.setdefault(trace_id, run_id)

                attrs = _attrs_of(span)
                name = span.get("name") or ""
                status = _span_status(span)

                start = span.get("startTimeUnixNano") or span.get("start_time_unix_nano")
                events.append(
                    CanonicalEvent(
                        event_id=span_id or f"{trace_id}:{len(events)}",
                        run_id=run_id,
                        parent_id=parent or None,
                        seq=len(events),
                        ts=self._ts(start),
                        kind=self._kind(name, attrs, status, has_parent=bool(parent)),
                        name=name,
                        payload=self._payload(span, attrs, options),
                        effect_class=_classify_effect(name, attrs),
                        observed=True,
                        meta={"trace_id": trace_id, "otel_status": status},
                    )
                )

        events.sort(key=lambda e: (e.run_id, e.seq))
        return events

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _kind(name: str, attrs: dict[str, Any], status: str, has_parent: bool) -> EventKind:
        """Root span opens the run; everything else is classified by hints."""
        if not has_parent and status != "error":
            return "run.start"
        return _detect_kind(name, attrs, status)

    @staticmethod
    def _load(source: str) -> list[dict[str, Any]]:
        with open(source, encoding="utf-8") as fh:
            text = fh.read().strip()
        if not text:
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            # JSONL: one span batch or one span per line
            payloads = []
            for line_no, line in enumerate(text.splitlines(), start=1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    payloads.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{source}:{line_no}: invalid JSON: {exc}") from exc
            return [p if isinstance(p, dict) else {"resourceSpans": [p]} for p in payloads]

        if isinstance(payload, list):
            return [p if isinstance(p, dict) else {"resourceSpans": [p]} for p in payload]
        return [payload]

    @staticmethod
    def _ts(nanos: Any) -> str:
        """Convert epoch nanoseconds to RFC3339-ish UTC. Best effort only.

        We deliberately avoid a dependency on a datetime parser; if the value
        is missing or unparseable the field is left empty rather than guessed.
        """
        import datetime as _dt

        try:
            seconds = int(nanos) / 1e9
        except (TypeError, ValueError):
            return ""
        if seconds <= 0:
            return ""
        stamp = _dt.datetime.fromtimestamp(seconds, _dt.timezone.utc)  # noqa: UP017
        return stamp.isoformat().replace("+00:00", "Z")

    # Vendor attribute -> canonical payload key. This mapping IS the collector's
    # job: if we handed raw `gen_ai.*` attrs downstream, the minimizer's
    # allowlist would drop the very fields a case needs.
    ATTR_ALIASES: tuple[tuple[tuple[str, ...], str], ...] = (
        (("gen_ai.tool.name", "tool.name", "mcp.tool.name", "function.name"), "tool"),
        (
            (
                "gen_ai.tool.arguments",
                "tool.arguments",
                "mcp.tool.arguments",
                "function.arguments",
            ),
            "arguments",
        ),
        (
            ("gen_ai.request.model", "gen_ai.response.model", "llm.request.model"),
            "model",
        ),
        (("gen_ai.usage.prompt_tokens",), "usage.prompt_tokens"),
        (("gen_ai.usage.completion_tokens",), "usage.completion_tokens"),
        (("gen_ai.usage.total_tokens",), "usage.total_tokens"),
        (("tool.duration_ms", "duration_ms"), "duration_ms"),
        (("handoff.reason", "escalation.reason"), "reason"),
    )

    @staticmethod
    def _payload(span: dict[str, Any], attrs: dict[str, Any], options: Any) -> dict[str, Any]:
        """Normalize vendor attributes into canonical payload keys.

        Raw tool results are NOT carried over by default: they are the richest
        source of PII in a trace and the minimizer's allowlist exists to drop
        them. Pass `keep_attributes` explicitly if a case genuinely needs them.
        """
        payload: dict[str, Any] = {}
        alias_map = {name: target for names, target in OTelCollector.ATTR_ALIASES for name in names}

        for key, value in attrs.items():
            target = alias_map.get(key)
            if target is None:
                continue
            if target.startswith("usage."):
                payload.setdefault("usage", {})[target.split(".", 1)[1]] = value
            else:
                payload[target] = value

        status = _span_status(span)
        payload["status"] = status
        if status == "error":
            status_obj = span.get("status") or {}
            payload["error"] = status_obj.get("message") or "span status=error"
            payload.setdefault("error_type", "span_error")

        extra = options.get("keep_attributes")
        if extra:
            allow = set(extra)
            payload.update({k: v for k, v in attrs.items() if k in allow})
        return payload
