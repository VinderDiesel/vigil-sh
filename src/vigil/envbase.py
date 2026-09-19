"""Shared guard for environment plugins.

Why this exists (HARD-8): an environment must refuse on its OWN declared
capabilities, never because a case asked nicely. Case YAML is data, not a
privilege escalation channel.

Contract:
  * every environment declares `capabilities: tuple[str, ...]`
  * every request implies a set of required capabilities
  * if a requirement is missing, `enforce()` raises RuntimeError

The runner turns that RuntimeError into a warning + UNDETERMINED, so a
mis-configured case degrades instead of silently running something dangerous.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

# request value -> capability that must be declared (refusal if missing)
REQUIRED_CAPABILITIES: dict[str, str] = {
    "live": "live-side-effects",
    "mock": "tool-mock",
    "open": "open-network",
    "allowlist": "allowlist-network",
}

# request value -> capability that SHOULD be declared (warning if missing).
# Clock freezing is best-effort in every sandbox we know of; refusing on it
# would make almost no environment usable, so it degrades to an advisory that
# shows up in the run report instead.
ADVISED_CAPABILITIES: dict[str, str] = {
    "frozen": "clock-freeze",
}

# A contract key that is present and non-default implies a capability.
IMPLICIT_REQUIREMENTS: tuple[tuple[str, str], ...] = (("init_snapshot", "snapshot"),)


class CapabilityError(RuntimeError):
    """Raised when a contract asks for something the environment cannot do."""


def required_capabilities(contract: dict[str, Any]) -> tuple[str, ...]:
    """Derive the capabilities a contract demands."""
    required: list[str] = []

    policy = contract.get("side_effect_policy", "dry-run")
    capability = REQUIRED_CAPABILITIES.get(policy)
    if capability:
        required.append(capability)

    network = contract.get("network_policy", "none")
    capability = REQUIRED_CAPABILITIES.get(network)
    if capability:
        required.append(capability)

    for key, capability in IMPLICIT_REQUIREMENTS:
        if contract.get(key):
            required.append(capability)

    # A declared mock map is useless without the ability to serve it.
    if contract.get("tool_mock_map"):
        required.append("tool-mock")

    return tuple(dict.fromkeys(required))


def enforce(contract: dict[str, Any], capabilities: Iterable[str]) -> None:
    """Raise CapabilityError if the contract exceeds declared capabilities."""
    declared = set(capabilities)
    missing = [cap for cap in required_capabilities(contract) if cap not in declared]
    if missing:
        raise CapabilityError(
            "environment does not support: "
            + ", ".join(sorted(missing))
            + f"; declared capabilities: {sorted(declared) or '[]'}"
        )


def advisory_warnings(contract: dict[str, Any], capabilities: Iterable[str]) -> list[str]:
    """Non-fatal gaps between what a case asks for and what the env can do.

    These are warnings, not refusals: they travel with the run report so a
    "deterministic" claim can be audited after the fact.
    """
    declared = set(capabilities)
    warnings: list[str] = []

    clock = contract.get("clock_policy")
    if clock in ADVISED_CAPABILITIES and ADVISED_CAPABILITIES[clock] not in declared:
        warnings.append(
            f"clock_policy={clock} requested but environment does not declare "
            f"{ADVISED_CAPABILITIES[clock]!r}; timing-dependent results may vary"
        )

    if contract.get("allowlist") and "allowlist-network" in declared:
        warnings.append(
            "network allowlist is approximated by the environment; verify "
            "outbound policy independently before claiming isolation"
        )

    if contract.get("init_snapshot") and "snapshot" not in declared:
        warnings.append("init_snapshot provided but environment has no snapshot capability")

    return warnings


def snapshot_digest(contract: dict[str, Any]) -> str:
    """Digest of the parts of a contract that define the world.

    Used as `env_digest` so runs with different worlds cannot be compared
    as if they were the same experiment.
    """
    from .cas import canonical_digest

    return canonical_digest(
        {
            "image": contract.get("image"),
            "init_snapshot": contract.get("init_snapshot"),
            "network_policy": contract.get("network_policy", "none"),
            "allowlist": sorted(contract.get("allowlist") or []),
            "tool_mock_map": dict(sorted((contract.get("tool_mock_map") or {}).items())),
            "seeds": contract.get("seeds") or {},
            "clock_policy": contract.get("clock_policy", "frozen"),
            "side_effect_policy": contract.get("side_effect_policy", "dry-run"),
            "env_vars": dict(sorted((contract.get("env_vars") or {}).items())),
        }
    )
