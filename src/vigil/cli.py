"""CLI: the only user-facing surface in v1alpha1.

Deliberately stdlib-only (argparse). The core must install and run on a
laptop with no Docker, no cloud credentials and no model provider key --
that is what makes the first 15 minutes cheap enough for anyone to try.

Commands mirror the asset chain:
    collect -> mint -> run -> gate -> explain
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Sequence
from typing import Any

from . import __version__
from . import runner as runner_mod
from .artifacts import (
    load_cases,
    render_pr_comment,
    write_json_report,
    write_junit,
)
from .cas import cas_uri, raw_digest
from .models.case import CaseManifest, Provenance
from .models.gate import SLO
from .models.result import RunResult
from .protocol import GROUP_COLLECTOR, GROUP_MINIMIZER, GROUP_SELECTOR
from .registry import discover_all, get

DEFAULT_SLOS: tuple[dict[str, Any], ...] = (
    {"metric": "policy_violations", "op": "max", "value": 0, "hard": True},
    {"metric": "unrecoverable_rate", "op": "max", "value": 0.05, "hard": True},
    {"metric": "pass_rate", "op": "min", "value": 0.9},
    {"metric": "p95_cost_usd", "op": "max", "value": 0.25},
    {"metric": "flake_rate", "op": "max", "value": 0.02},
)


def _load_agent(path: str) -> Any:
    """Import an agent callable from a Python file.

    Expected: module exposes `run(case: CaseManifest) -> RunResult`.
    """
    spec = importlib.util.spec_from_file_location("vigil_user_agent", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load agent from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, "run", None)
    if fn is None:
        raise SystemExit(f"{path} must define run(case) -> RunResult")
    return fn


def _load_slos(path: str | None) -> list[SLO]:
    if not path:
        return [SLO.from_dict(item) for item in DEFAULT_SLOS]
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    items = data["slos"] if isinstance(data, dict) else data
    return [SLO.from_dict(item) for item in items]


def cmd_plugins(args: argparse.Namespace) -> int:
    found = discover_all()
    for group, plugins in found.items():
        print(f"{group}")
        if not plugins:
            print("  <none installed>")
        for name in sorted(plugins):
            print(f"  - {name}")
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    collector_cls = get(GROUP_COLLECTOR, args.collector)
    events = collector_cls().collect(args.source, **json.loads(args.options or "{}"))
    payload = [e.to_dict() for e in events]
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")

    minimizer_cls = get(GROUP_MINIMIZER, args.minimizer)
    minimized, removed = minimizer_cls().minimize(events)

    out = {
        "spec_version": "v1alpha1",
        "raw_hash": raw_digest(raw),
        "canonical_hash": cas_uri([e.to_dict() for e in minimized]),
        "redactions": removed,
        "events": [e.to_dict() for e in minimized],
    }
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, sort_keys=True, ensure_ascii=False)
        print(f"wrote {args.out}: {len(minimized)} events, {len(removed)} redaction types")
    else:
        json.dump(out, sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
        sys.stdout.write("\n")
    return 0


def cmd_select(args: argparse.Namespace) -> int:
    collector_cls = get(GROUP_COLLECTOR, args.collector)
    events = collector_cls().collect(args.source)
    runs: dict[str, list[Any]] = {}
    for event in events:
        runs.setdefault(event.run_id, []).append(event)
    selector_cls = get(GROUP_SELECTOR, args.selector)
    picked = selector_cls().select(
        list(runs.values()),
        **json.loads(args.options or "{}"),
    )
    json.dump(picked, sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def cmd_mint(args: argparse.Namespace) -> int:
    """Create a case manifest from a collected run (scaffold, not magic).

    v1alpha1 does NOT auto-generate oracles. A case without a human-reviewed
    oracle is a liability, so `mint` requires --oracle and stamps
    confidence=low unless --reviewed is passed.
    """
    if not args.oracle:
        raise SystemExit("--oracle is required; automatic oracle generation is out of scope")
    oracle = json.loads(args.oracle)
    case = CaseManifest(
        case_id=args.case_id,
        title=args.title,
        input=json.loads(args.input or "{}"),
        oracle=oracle,
        oracle_version=args.oracle_version,
        replay_mode=args.replay_mode,
        severity=args.severity,
        labels=args.label or [],
        confidence=1.0 if args.reviewed else 0.3,
        provenance=Provenance(
            collector=args.collector,
            source_ref=args.source_ref or "",
            reviewed_by=args.reviewed_by,
        ),
    )
    case.canonical_hash = cas_uri(case.to_dict())
    payload = case.to_dict()
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    print(f"wrote {args.out}  case_id={case.case_id}  confidence={case.confidence}")
    if not args.reviewed:
        print("note: confidence=0.3 until a human reviews the oracle (--reviewed)")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cases = load_cases(args.cases)
    agent = _load_agent(args.agent)
    scorers = tuple(args.scorer.split(",")) if args.scorer else ("exact",)

    def wrapped(case: CaseManifest) -> RunResult:
        result = agent(case)
        if not isinstance(result, RunResult):
            raise SystemExit(f"{args.agent}: run(case) must return a vigil RunResult")
        return result

    reports, agg = runner_mod.run_suite(
        cases,
        wrapped,
        env_name=args.env,
        scorers=scorers,
        repeats=args.repeats,
    )
    slos = _load_slos(args.slo)
    decision = runner_mod.decide(agg, slos)
    fingerprint = runner_mod.suite_fingerprint(reports)

    if args.junit:
        write_junit(args.junit, reports, suite_name=args.suite)
    if args.json:
        write_json_report(args.json, reports, agg, decision, fingerprint)
    if args.comment:
        with open(args.comment, "w", encoding="utf-8") as fh:
            fh.write(render_pr_comment(agg, decision, fingerprint, reports))

    print(render_pr_comment(agg, decision, fingerprint, reports))
    for report in reports:
        for warning in report.warnings:
            print(f"warning: {report.case.case_id}: {warning}", file=sys.stderr)
    return decision.exit_code


def cmd_gate(args: argparse.Namespace) -> int:
    """Re-evaluate a previously produced JSON report against SLOs.

    Keeping gate separate from run means gate policy can change without
    paying for another agent execution.
    """
    with open(args.report, encoding="utf-8") as fh:
        data = json.load(fh)
    from .models.case import CaseManifest
    from .models.result import Aggregate, RunResult
    from .runner import RunReport

    reports = [
        RunReport(
            case=CaseManifest.from_dict(item["case"]),
            result=RunResult.from_dict(item["result"]),
            env_digest=item.get("env_digest", ""),
        )
        for item in data.get("runs", [])
    ]
    agg_raw = data.get("aggregate") or {}
    agg = Aggregate(**{k: v for k, v in agg_raw.items() if k != "pass_at_k"})
    slos = _load_slos(args.slo)
    decision = runner_mod.decide(agg, slos)
    print(render_pr_comment(agg, decision, data.get("fingerprint", ""), reports))
    return decision.exit_code


def cmd_explain(args: argparse.Namespace) -> int:
    """Print one case, with the vocabulary it is allowed to use."""
    cases = load_cases(args.cases)
    for case in cases:
        if args.case_id and case.case_id != args.case_id:
            continue
        print(json.dumps(case.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
        print(f"claims_determinism={case.claims_determinism}")
        print(f"allowed_vocabulary={'replay' if case.claims_determinism else 'best-effort rerun'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vigil",
        description=(
            "Turn agent executions into replayable, scoreable, gateable reliability assets."
        ),
    )
    parser.add_argument("--version", action="version", version=f"vigil {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("plugins", help="list installed plugins")
    p.set_defaults(func=cmd_plugins)

    p = sub.add_parser("collect", help="collect + minimize a trace into canonical events")
    p.add_argument("source")
    p.add_argument("--collector", default="file")
    p.add_argument("--minimizer", default="default")
    p.add_argument("--options", default="{}")
    p.add_argument("--out")
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("select", help="choose which runs deserve to become cases")
    p.add_argument("source")
    p.add_argument("--collector", default="file")
    p.add_argument("--selector", default="rules")
    p.add_argument("--options", default="{}")
    p.set_defaults(func=cmd_select)

    p = sub.add_parser("mint", help="scaffold a case manifest (oracle required)")
    p.add_argument("--case-id", required=True)
    p.add_argument("--title", default="")
    p.add_argument("--input", default="{}")
    p.add_argument("--oracle", required=True)
    p.add_argument("--oracle-version", default="v1")
    p.add_argument("--replay-mode", default="mock-replay")
    p.add_argument("--severity", default="unknown")
    p.add_argument("--label", action="append")
    p.add_argument("--collector", default="manual")
    p.add_argument("--source-ref", default="")
    p.add_argument("--reviewed", action="store_true")
    p.add_argument("--reviewed-by", default=None)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_mint)

    p = sub.add_parser("run", help="run a case suite and emit CI artifacts")
    p.add_argument("--cases", required=True)
    p.add_argument("--agent", required=True)
    p.add_argument("--env", default="noop")
    p.add_argument("--scorer", default="exact")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--suite", default="vigil")
    p.add_argument("--slo")
    p.add_argument("--junit")
    p.add_argument("--json")
    p.add_argument("--comment")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("gate", help="re-evaluate a JSON report against SLOs")
    p.add_argument("--report", required=True)
    p.add_argument("--slo")
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("explain", help="show a case and its replay guarantees")
    p.add_argument("--cases", required=True)
    p.add_argument("--case-id")
    p.set_defaults(func=cmd_explain)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
