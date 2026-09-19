"""Collector: read canonical events from a JSONL replay file.

Tier: core. This is the reference collector -- the one used by conformance
tests, because it needs no vendor account, no network and no credentials.
"""

from __future__ import annotations

import json
from typing import Any

from ..models.event import CanonicalEvent


class FileCollector:
    name = "file"
    version = "0.1.0"

    def collect(self, source: str, **options: Any) -> list[CanonicalEvent]:
        events: list[CanonicalEvent] = []
        with open(source, encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{source}:{line_no}: invalid JSON: {exc}") from exc
                events.append(CanonicalEvent.from_dict(raw))
        events.sort(key=lambda e: (e.seq, e.ts, e.event_id))
        return events
