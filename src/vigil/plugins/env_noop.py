"""Environment: no-op, in-process, no external state.

Tier: core.

This is the ONLY environment that ships in core. It is honest about what it
is: it can execute an agent callable in-process, it cannot guarantee anything
about filesystems, containers, browsers or network. Cases run under `noop`
are valid for:
    record-only, mock-replay (agent reads recorded responses), sandbox-execute
    with a purely in-memory agent.

It is NOT valid for snapshot-replay and must not be used to claim
determinism for anything touching the outside world.

Refusal is driven by `capabilities` via `vigil.envbase.enforce` (HARD-8):
a case cannot escalate privileges by editing YAML.
"""

from __future__ import annotations

from typing import Any

from ..envbase import enforce, snapshot_digest
from ..models.case import CaseManifest
from ..models.result import RunResult


class NoopEnvHandle:
    def __init__(self, contract: dict[str, Any]) -> None:
        self.contract = contract
        self._digest = snapshot_digest(contract)

    def restore(self) -> str:
        # No external state to restore; the digest is the contract itself.
        return self._digest

    def execute(self, case: CaseManifest, agent: Any) -> RunResult:
        # Re-checked here, not only at provision time: handles are cheap to
        # forge and expensive to trust.
        enforce(self.contract, NoopEnvironment.capabilities)
        result = agent(case)
        if not isinstance(result, RunResult):
            raise TypeError("agent callable must return a vigil RunResult")
        return result

    def teardown(self) -> None:
        return None


class NoopEnvironment:
    name = "noop"
    version = "0.1.0"
    # Declared capability set. Runners, docs and conformance read this.
    capabilities = (
        "in-process",
        "no-network",
        "dry-run-only",
        "no-snapshot",
        "tool-mock",
    )

    def provision(self, contract: dict[str, Any]) -> NoopEnvHandle:
        enforce(contract, self.capabilities)
        return NoopEnvHandle(contract)
