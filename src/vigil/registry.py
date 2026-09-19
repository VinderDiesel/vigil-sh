"""Plugin discovery via importlib.metadata entry points.

Built-in plugins are declared in pyproject.toml exactly like third-party ones.
There is no "core plugin" shortcut: if a built-in cannot satisfy conformance,
it should be able to fail the same way a community plugin would.
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any

from .protocol import ALL_GROUPS


class RegistryError(RuntimeError):
    pass


def discover(group: str) -> dict[str, Any]:
    """Return {plugin_name: loaded_class}. Raises on duplicate names."""
    if group not in ALL_GROUPS:
        raise RegistryError(f"unknown plugin group: {group}")
    found: dict[str, Any] = {}
    for ep in entry_points(group=group):
        if ep.name in found:
            raise RegistryError(
                f"duplicate plugin name {ep.name!r} in group {group}; "
                "plugin names must be globally unique per group"
            )
        found[ep.name] = ep.load()
    return found


def discover_all() -> dict[str, dict[str, Any]]:
    return {group: discover(group) for group in ALL_GROUPS}


def get(group: str, name: str) -> Any:
    plugins = discover(group)
    if name not in plugins:
        available = ", ".join(sorted(plugins)) or "<none>"
        raise RegistryError(f"plugin {name!r} not found in group {group}; available: {available}")
    return plugins[name]
