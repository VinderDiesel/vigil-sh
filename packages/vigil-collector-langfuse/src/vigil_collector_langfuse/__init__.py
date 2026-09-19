"""Collector: Langfuse export (file) or Langfuse API -> CanonicalEvent.

Tier: maintained. Distributed separately from core because talking to a
Langfuse server needs an HTTP client (HARD-1 / HARD-4: heavy SDKs never enter
core, and never at import time).

Two modes, one SPI:
    collect("export.json")                      -- parse an export file
    collect("langfuse://cloud.langfuse.com", ...)  -- pull via the public API

Privacy posture: `input` / `output` blobs are the richest PII in any trace.
By default this collector emits ONLY digests of them (`prompt_digest` /
`completion_digest`). Passing `include_io=True` carries the raw text, which
the minimizer will then scrub -- opt in deliberately, and prefer not to.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from vigil.cas import canonical_bytes
from vigil.models.event import CanonicalEvent, EffectClass, EventKind

__all__ = ["DEFAULT_KEEP_DIGEST_ONLY", "LangfuseCollector"]

# Digest of a blob: stable, non-reversible, enough for lineage and dedup.
DEFAULT_KEEP_DIGEST_ONLY = True

OBSERVATION_KIND: dict[str, EventKind] = {
    "GENERATION": "llm.call",
    "SPAN": "tool.call",
    "EVENT": "tool.result",
    "EMBEDDING": "llm.call",
    "RETRIEVER": "tool.call",
    "TOOL": "tool.call",
    "AGENT": "run.start",
    "CHAIN": "run.start",
    "EVALUATOR": "tool.call",
    "GUARDRAIL": "tool.call",
}

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
WRITE_HINTS = ("create", "update", "write", "insert", "upsert", "patch", "append", "submit")
READ_HINTS = ("get", "list", "read", "search", "query", "fetch", "lookup", "retrieve")


def _digest(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return hashlib.sha256(canonical_bytes(value)).hexdigest()
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _flatten(value: Any) -> Any:
    """Langfuse nests usage/metadata arbitrarily; keep it JSON-safe."""
    if isinstance(value, dict):
        return {str(k): _flatten(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_flatten(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _classify_effect(name: str, obs_type: str) -> EffectClass:
    lowered = (name or "").lower()
    for group, label in (
        (DESTRUCTIVE_HINTS, "destructive"),
        (WRITE_HINTS, "write"),
        (READ_HINTS, "read"),
    ):
        if any(token in lowered for token in group):
            return label  # type: ignore[return-value]
    if obs_type in ("GENERATION", "EMBEDDING"):
        return "read"  # a model call does not change the world by itself
    return "unknown"


class LangfuseCollector:
    """Collect canonical events from a Langfuse export or API."""

    name = "langfuse"
    version = "0.1.0"

    def collect(self, source: str, **options: Any) -> list[CanonicalEvent]:
        include_io = bool(options.get("include_io", False))
        limit = int(options.get("limit", 0))

        if source.startswith("langfuse://"):
            observations = self._from_api(source, options)
        else:
            observations = self._from_file(source)

        events = [
            self._to_event(obs, index, include_io)
            for index, obs in enumerate(observations)
            if isinstance(obs, dict)
        ]
        events.sort(key=lambda e: (e.run_id, e.ts, e.seq))
        if limit:
            events = events[:limit]
        return events

    # -- sources -------------------------------------------------------------

    def _from_file(self, path: str) -> list[dict[str, Any]]:
        with open(path, encoding="utf-8") as fh:
            text = fh.read().strip()
        if not text:
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            rows = []
            for line_no, line in enumerate(text.splitlines(), start=1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            return self._extract(rows)

        rows = payload if isinstance(payload, list) else [payload]
        return self._extract(rows)

    @staticmethod
    def _extract(rows: list[Any]) -> list[dict[str, Any]]:
        """Flatten the shapes Langfuse exports actually use."""
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if "observations" in row and isinstance(row["observations"], list):
                out.extend(o for o in row["observations"] if isinstance(o, dict))
            elif "data" in row and isinstance(row["data"], dict):
                data = row["data"]
                if isinstance(data.get("observations"), list):
                    out.extend(o for o in data["observations"] if isinstance(o, dict))
                elif isinstance(data.get("data"), list):
                    out.extend(o for o in data["data"] if isinstance(o, dict))
            elif "type" in row or "observationId" in row or "id" in row:
                out.append(row)
        return out

    def _from_api(self, source: str, options: Any) -> list[dict[str, Any]]:
        host = source[len("langfuse://") :].rstrip("/")
        public_key = options.get("public_key") or os.environ.get("LANGFUSE_PUBLIC_KEY", "")
        secret_key = options.get("secret_key") or os.environ.get("LANGFUSE_SECRET_KEY", "")
        if not (public_key and secret_key):
            raise RuntimeError(
                "langfuse API mode needs public_key/secret_key "
                "(or LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY)"
            )

        params = {"limit": str(options.get("page_size", 100))}
        if options.get("trace_id"):
            params["traceId"] = str(options["trace_id"])
        if options.get("name"):
            params["name"] = str(options["name"])
        if options.get("since"):
            params["fromStartTime"] = str(options["since"])
        if options.get("type"):
            params["type"] = str(options["type"])

        payload = self._fetch_json(
            f"{host}/api/public/observations", public_key, secret_key, params
        )
        return list(payload.get("data", []))

    def _fetch_json(
        self, url: str, public_key: str, secret_key: str, params: dict[str, str]
    ) -> dict[str, Any]:
        """HTTP call, isolated so tests can stub it and core stays clean.

        httpx is imported INSIDE the function: importing it at module import
        time would make this plugin unusable without the dependency, and would
        violate HARD-4.
        """
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - depends on install
            raise RuntimeError(
                "API mode requires httpx: pip install vigil-collector-langfuse[api]"
            ) from exc

        response = httpx.get(url, params=params, auth=(public_key, secret_key), timeout=30.0)
        response.raise_for_status()
        return dict(response.json())

    # -- mapping -------------------------------------------------------------

    def _to_event(self, obs: dict[str, Any], index: int, include_io: bool) -> CanonicalEvent:
        name = str(obs.get("name") or "")
        obs_type = str(obs.get("type") or "").upper()
        kind = OBSERVATION_KIND.get(obs_type, "unknown")
        level = str(obs.get("level") or "").upper()
        if level in ("ERROR", "WARNING") and obs.get("statusMessage"):
            kind = "error"

        payload: dict[str, Any] = {
            "status": "error" if level == "ERROR" else "ok",
        }
        if obs.get("model"):
            payload["model"] = str(obs["model"])
        if obs.get("usage"):
            payload["usage"] = _flatten(obs["usage"])
        if obs.get("usageDetails"):
            payload.setdefault("usage", _flatten(obs["usageDetails"]))
        if obs.get("tool") or obs_type in ("TOOL", "RETRIEVER"):
            payload["tool"] = str(obs.get("tool") or name)

        # I/O: digests by default. Raw text is opt-in and still gets scrubbed
        # downstream by the minimizer.
        payload["prompt_digest"] = _digest(obs.get("input"))
        payload["completion_digest"] = _digest(obs.get("output"))
        if include_io:
            if obs.get("input") is not None:
                payload["input"] = _flatten(obs["input"])
            if obs.get("output") is not None:
                payload["output"] = _flatten(obs["output"])

        if obs.get("statusMessage"):
            payload["error"] = str(obs["statusMessage"])
            payload["error_type"] = "langfuse_status"
        if obs.get("startTime") and obs.get("endTime"):
            payload["duration_ms"] = self._duration_ms(obs["startTime"], obs["endTime"])

        return CanonicalEvent(
            event_id=str(obs.get("id") or obs.get("observationId") or f"obs-{index}"),
            run_id=str(obs.get("traceId") or obs.get("trace_id") or "unknown-run"),
            parent_id=(str(obs["parentObservationId"]) if obs.get("parentObservationId") else None),
            seq=int(obs.get("_seq", index)),
            ts=str(obs.get("startTime") or ""),
            kind=kind,
            name=name,
            payload=payload,
            effect_class=_classify_effect(name, obs_type),
            observed=True,
            meta={"langfuse_type": obs_type, "source": "langfuse"},
        )

    @staticmethod
    def _duration_ms(start: Any, end: Any) -> int:
        from datetime import datetime

        def parse(value: Any) -> datetime | None:
            if isinstance(value, datetime):
                return value
            text = str(value).replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(text)
            except ValueError:
                return None

        a, b = parse(start), parse(end)
        if a is None or b is None:
            return 0
        return int((b - a).total_seconds() * 1000)
