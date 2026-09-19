"""Scaffold a new plugin package from a template.

Usage:
    python scripts/new_plugin.py --group scorers --name myjudge \
        --class MyJudge --tier community

The generated package is OUT-OF-TREE by default: third-party plugins must not
live in this repository's src/ tree (HARD-4: heavy SDKs stay out of core).
"""

from __future__ import annotations

import argparse
import os
import textwrap

TEMPLATE = '''"""{doc}

Tier: {tier}
Conforms to: vigil.protocol.{protocol}
"""

from __future__ import annotations

from typing import Any

{imports}


class {cls}:
    name = "{name}"
    version = "0.1.0"

{method}
'''


def _method_body(signature: str) -> str:
    return "\n".join(
        [
            "    def " + signature + ":",
            "        raise NotImplementedError",
        ]
    )


PROTOCOLS: dict[str, tuple[str, str, str]] = {
    "collectors": (
        "Collector",
        "collect",
        _method_body("collect(self, source: str, **options: Any) -> list[CanonicalEvent]"),
    ),
    "minimizers": (
        "Minimizer",
        "minimize",
        _method_body(
            "minimize(\n"
            "        self, events: Sequence[CanonicalEvent], **options: Any\n"
            "    ) -> tuple[list[CanonicalEvent], list[str]]"
        ),
    ),
    "selectors": (
        "Selector",
        "select",
        _method_body(
            "select(\n"
            "        self, runs: Sequence[Sequence[CanonicalEvent]], **options: Any\n"
            "    ) -> list[dict[str, Any]]"
        ),
    ),
    "environments": (
        "EnvironmentProvider",
        "provision",
        _method_body('provision(self, contract: dict[str, Any]) -> "EnvHandle"'),
    ),
    "scorers": (
        "Scorer",
        "score",
        _method_body("score(self, case: CaseManifest, result: RunResult) -> JudgeVerdict | None"),
    ),
    "gates": (
        "Gate",
        "decide",
        _method_body("decide(self, aggregate: Aggregate, slos: Sequence[SLO]) -> GateDecision"),
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", required=True, choices=sorted(PROTOCOLS))
    parser.add_argument("--name", required=True)
    parser.add_argument("--class", dest="cls", required=True)
    parser.add_argument("--tier", default="community")
    parser.add_argument("--out", default=".")
    args = parser.parse_args()

    protocol, _method, body = PROTOCOLS[args.group]
    pkg = f"vigil-{args.group[:-1]}-{args.name}"
    target = os.path.join(args.out, pkg, "src", f"vigil_{args.name}")
    os.makedirs(target, exist_ok=True)

    imports = "\n".join(
        [
            "from typing import Any, Sequence",
            "",
            "from vigil.models.case import CaseManifest",
            "from vigil.models.event import CanonicalEvent",
            "from vigil.models.gate import GateDecision, SLO",
            "from vigil.models.result import Aggregate, JudgeVerdict, RunResult",
        ]
    )
    source = TEMPLATE.format(
        doc=f"{args.cls}: {args.name} plugin for Vigil.",
        tier=args.tier,
        protocol=protocol,
        imports=imports,
        cls=args.cls,
        name=args.name,
        method=body,
    )
    with open(os.path.join(target, "__init__.py"), "w", encoding="utf-8") as fh:
        fh.write(source)

    print(
        textwrap.dedent(f"""\
        created {target}/__init__.py

        next steps:
          1. implement {args.cls} (methods must be fully annotated)
          2. declare the entry point in pyproject.toml:
               [project.entry-points."vigil.{args.group}"]
               {args.name} = "vigil_{args.name}:{args.cls}"
          3. add a behavioural contract test under conformance/
          4. run: pytest conformance -m conformance
    """)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
