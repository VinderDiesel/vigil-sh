"""CaseManifest: the reliability asset Vigil produces and gates on.

A case is NOT "a prompt and an expected answer". It is an execution contract:
what environment, what seeds, what mocks, what side effects are permitted,
which oracle version judges it, and where the evidence came from.

Content addressing (see spec/v1alpha1/manifest.md):
    raw_hash        -> bytes as ingested
    canonical_hash  -> bytes after canonicalization + declared redaction
    cluster_id      -> semantic grouping, ALWAYS advisory, never identity
Never deduplicate on cluster_id. Never treat equal canonical_hash as
"same intent".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

ReplayMode = Literal[
    "record-only",  # audit only, no rerun promise
    "mock-replay",  # tool responses replayed from recording
    "snapshot-replay",  # fs/db/container state restored from snapshot
    "sandbox-execute",  # controlled env, real execution allowed
    "live-canary",  # external state keeps moving; contract check only
]

# Replay modes that may claim determinism. Everything else must degrade its
# vocabulary to "rerun".
DETERMINISTIC_MODES: frozenset[str] = frozenset(
    {"mock-replay", "snapshot-replay", "sandbox-execute"}
)

Severity = Literal["critical", "high", "medium", "low", "unknown"]


@dataclass
class EnvironmentContract:
    """Everything needed to stand the world back up.

    A run without this contract is a best-effort rerun, not a replay.
    """

    image: str | None = None
    init_snapshot: str | None = None
    network_policy: Literal["none", "allowlist", "open"] = "none"
    allowlist: list[str] = field(default_factory=list)
    tool_mock_map: dict[str, str] = field(default_factory=dict)
    seeds: dict[str, Any] = field(default_factory=dict)
    clock_policy: Literal["frozen", "real"] = "frozen"
    side_effect_policy: Literal["dry-run", "mock", "live"] = "dry-run"
    env_vars: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "image": self.image,
            "init_snapshot": self.init_snapshot,
            "network_policy": self.network_policy,
            "allowlist": list(self.allowlist),
            "tool_mock_map": dict(self.tool_mock_map),
            "seeds": dict(self.seeds),
            "clock_policy": self.clock_policy,
            "side_effect_policy": self.side_effect_policy,
            "env_vars": dict(self.env_vars),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnvironmentContract:
        return cls(
            image=data.get("image"),
            init_snapshot=data.get("init_snapshot"),
            network_policy=data.get("network_policy", "none"),
            allowlist=list(data.get("allowlist") or []),
            tool_mock_map=dict(data.get("tool_mock_map") or {}),
            seeds=dict(data.get("seeds") or {}),
            clock_policy=data.get("clock_policy", "frozen"),
            side_effect_policy=data.get("side_effect_policy", "dry-run"),
            env_vars=dict(data.get("env_vars") or {}),
        )


@dataclass
class Provenance:
    """Where this case came from, and what was removed on the way in."""

    collector: str  # e.g. "otel@0.1.0"
    source_ref: str  # trace id / file path / URL -- never raw content
    collected_at: str = ""
    redactions: list[str] = field(default_factory=list)
    reviewed_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "collector": self.collector,
            "source_ref": self.source_ref,
            "collected_at": self.collected_at,
            "redactions": list(self.redactions),
            "reviewed_by": self.reviewed_by,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Provenance:
        return cls(
            collector=str(data.get("collector", "unknown")),
            source_ref=str(data.get("source_ref", "")),
            collected_at=str(data.get("collected_at", "")),
            redactions=list(data.get("redactions") or []),
            reviewed_by=data.get("reviewed_by"),
        )


@dataclass
class CaseManifest:
    """A versioned, hash-addressable regression asset.

    `spec_version` is mandatory. A manifest without it cannot be loaded --
    this is the single cheapest defense against silent schema drift.
    """

    case_id: str
    spec_version: str = "v1alpha1"
    title: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    oracle: dict[str, Any] = field(default_factory=dict)
    oracle_version: str = "unversioned"
    env: EnvironmentContract = field(default_factory=EnvironmentContract)
    replay_mode: ReplayMode = "record-only"
    provenance: Provenance = field(default_factory=lambda: Provenance("unknown", ""))
    severity: Severity = "unknown"
    labels: list[str] = field(default_factory=list)
    confidence: float = 1.0  # confidence that the ORACLE is right
    expires_at: str | None = None  # cases rot; an expired case cannot gate
    raw_hash: str = ""
    canonical_hash: str = ""
    cluster_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "spec_version": self.spec_version,
            "title": self.title,
            "input": self.input,
            "oracle": self.oracle,
            "oracle_version": self.oracle_version,
            "env": self.env.to_dict(),
            "replay_mode": self.replay_mode,
            "provenance": self.provenance.to_dict(),
            "severity": self.severity,
            "labels": list(self.labels),
            "confidence": self.confidence,
            "expires_at": self.expires_at,
            "raw_hash": self.raw_hash,
            "canonical_hash": self.canonical_hash,
            "cluster_id": self.cluster_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CaseManifest:
        version = data.get("spec_version")
        if version != "v1alpha1":
            raise ValueError(
                f"unsupported or missing spec_version={version!r}; "
                "this build only understands v1alpha1"
            )
        return cls(
            case_id=str(data.get("case_id", "")),
            spec_version=version,
            title=str(data.get("title", "")),
            input=dict(data.get("input") or {}),
            oracle=dict(data.get("oracle") or {}),
            oracle_version=str(data.get("oracle_version", "unversioned")),
            env=EnvironmentContract.from_dict(data.get("env") or {}),
            replay_mode=data.get("replay_mode", "record-only"),
            provenance=Provenance.from_dict(data.get("provenance") or {}),
            severity=data.get("severity", "unknown"),
            labels=list(data.get("labels") or []),
            confidence=float(data.get("confidence", 1.0)),
            expires_at=data.get("expires_at"),
            raw_hash=str(data.get("raw_hash", "")),
            canonical_hash=str(data.get("canonical_hash", "")),
            cluster_id=data.get("cluster_id"),
        )

    @property
    def claims_determinism(self) -> bool:
        return self.replay_mode in DETERMINISTIC_MODES

    @property
    def expired(self) -> bool:
        """`expires_at` is an ISO date (YYYY-MM-DD); the case is valid through
        that day and expired the day after.

        An unparseable value cannot prove the case is still fresh, so it is
        treated as expired. Degrading toward "cannot gate" is the only safe
        reading (same posture as HARD-6).
        """
        if self.expires_at is None:
            return False
        try:
            # 3.11+ fromisoformat also accepts datetimes; compare dates only.
            parsed = date.fromisoformat(self.expires_at)
        except ValueError:
            return True
        expiry = parsed.date() if isinstance(parsed, datetime) else parsed
        return date.today() > expiry
