"""In-sandbox execution probe.

Remote environments (docker, k8s, a VM, another machine) cannot call a Python
callable in this process. They need a tiny, dependency-free entry point they
can run INSIDE the sandbox:

    python -m vigil.harness --case /case/case.json --agent /case/agent.py \
                            --out /case/result.json

It loads the case, calls the user's `run(case)`, and writes the RunResult as
JSON. Nothing else: no network, no orchestration, no policy. The environment
plugin stays responsible for isolation and the runner stays responsible for
scoring and gating.

Stdlib only (HARD-1) -- this module is shipped into sandboxes.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import traceback
from collections.abc import Sequence
from typing import Any

from .models.case import CaseManifest
from .models.result import RunResult


def load_callable(path: str, attr: str = "run") -> Any:
    """Import `run` (or `attr`) from a standalone Python file."""
    spec = importlib.util.spec_from_file_location("vigil_user_agent", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load agent module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, attr, None)
    if fn is None:
        raise RuntimeError(f"{path} must define {attr}(case) -> RunResult")
    return fn


class LoadedAgent:
    """A callable agent that remembers where it came from.

    In-process environments just call it. Remote environments (docker, k8s, a
    VM) cannot ship a live Python callable across the boundary, so they read
    `path` and re-load the agent inside the sandbox via `vigil.harness`.
    """

    def __init__(self, fn: Any, path: str | None = None, attr: str = "run") -> None:
        self.fn = fn
        self.path = path
        self.attr = attr

    def __call__(self, case: CaseManifest) -> RunResult:
        return self.fn(case)  # type: ignore[no-any-return]

    @classmethod
    def from_any(cls, agent: Any, attr: str = "run") -> LoadedAgent:
        if isinstance(agent, cls):
            return agent
        if isinstance(agent, str):
            return cls(load_callable(agent, attr), path=agent, attr=attr)
        return cls(agent)


def run_one(case: CaseManifest, agent: Any) -> RunResult:
    """Execute one case, converting any failure into an ERROR result.

    The sandbox must never swallow a crash into a silent pass.
    """
    try:
        result = agent(case)
    except Exception as exc:  # noqa: BLE001 - reported, not hidden
        return RunResult(
            case_id=case.case_id,
            outcome="ERROR",
            notes=f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=8)}",
        )
    if not isinstance(result, RunResult):
        return RunResult(
            case_id=case.case_id,
            outcome="ERROR",
            notes=f"agent returned {type(result).__name__}, expected RunResult",
        )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vigil.harness",
        description="Run one Vigil case inside a sandbox and emit a RunResult JSON.",
    )
    parser.add_argument("--case", required=True, help="path to CaseManifest JSON")
    parser.add_argument("--agent", required=True, help="path to agent .py exposing run(case)")
    parser.add_argument("--attr", default="run")
    parser.add_argument("--out", help="write JSON here instead of stdout")
    parser.add_argument(
        "--exit-nonzero-on-error",
        action="store_true",
        help="exit 1 when the run errored (useful for container logs)",
    )
    args = parser.parse_args(argv)

    with open(args.case, encoding="utf-8") as fh:
        case = CaseManifest.from_dict(json.load(fh))

    agent = load_callable(args.agent, args.attr)
    result = run_one(case, agent)
    payload = json.dumps(result.to_dict(), sort_keys=True, ensure_ascii=False, indent=2)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    else:
        sys.stdout.write(payload + "\n")

    if args.exit_nonzero_on_error and result.outcome == "ERROR":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
