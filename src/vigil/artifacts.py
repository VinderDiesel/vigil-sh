"""Machine-readable CI artifacts.

Output formats are chosen for what CI systems already understand:
    JUnit XML  -> GitHub Actions / GitLab / Jenkins test reporting
    JSON       -> PR comments, regression diffs, dashboards
    SARIF      -> planned (v0.2), not faked here

No HTML dashboard in v1alpha1. Reports are meant to be read inside the PR,
next to the code that caused them.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any
from xml.etree import ElementTree as ET

from .models.gate import GateDecision
from .models.result import Aggregate
from .runner import RunReport


def write_json_report(
    path: str,
    reports: Sequence[RunReport],
    aggregate: Aggregate,
    decision: GateDecision,
    fingerprint: str,
) -> None:
    payload = {
        "spec_version": "v1alpha1",
        "fingerprint": fingerprint,
        "aggregate": aggregate.to_dict(),
        "gate": decision.to_dict(),
        "runs": [r.to_dict() for r in reports],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def write_junit(path: str, reports: Sequence[RunReport], suite_name: str = "vigil") -> None:
    """Emit JUnit XML. One <testcase> per verdict plus one per case outcome."""
    suites = ET.Element("testsuites", {"name": suite_name})
    suite = ET.SubElement(
        suites,
        "testsuite",
        {
            "name": suite_name,
            "tests": str(len(reports)),
            "failures": str(sum(1 for r in reports if r.result.outcome == "FAIL")),
            "errors": str(sum(1 for r in reports if r.result.outcome == "ERROR")),
        },
    )
    for report in reports:
        case = report.case
        result = report.result
        node = ET.SubElement(
            suite,
            "testcase",
            {
                "name": f"{case.case_id}:{case.title or case.case_id}",
                "classname": f"vigil.{case.replay_mode}",
                "time": f"{result.latency_ms / 1000:.3f}",
            },
        )
        if result.outcome == "FAIL":
            ET.SubElement(node, "failure", {"message": "case failed"}).text = _detail(report)
        elif result.outcome == "ERROR":
            ET.SubElement(node, "error", {"message": "case errored"}).text = _detail(report)
        elif result.outcome == "UNDETERMINED":
            # Surfaced as skipped, not passed: silence here is how flakes hide.
            ET.SubElement(
                node, "skipped", {"message": "undetermined / needs review"}
            ).text = _detail(report)
        props = ET.SubElement(node, "properties")
        for key, value in (
            ("case_id", case.case_id),
            ("replay_mode", case.replay_mode),
            ("env_digest", report.env_digest),
            ("disagreement", str(result.disagreement())),
            ("needs_review", str(result.needs_review()).lower()),
            ("oracle_version", case.oracle_version),
        ):
            ET.SubElement(props, "property", {"name": key, "value": str(value)})
        for warning in report.warnings:
            ET.SubElement(props, "property", {"name": "warning", "value": warning})

    tree = ET.ElementTree(suites)
    ET.indent(tree, space="  ", level=0)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _detail(report: RunReport) -> str:
    lines = [f"case_id={report.case.case_id}", f"mode={report.case.replay_mode}"]
    for verdict in report.result.verdicts:
        state = "abstain" if verdict.abstain else f"score={verdict.score}"
        lines.append(f"  {verdict.judge}@{verdict.judge_version}: {state} ({verdict.rationale})")
    for warning in report.warnings:
        lines.append(f"  warning: {warning}")
    if report.result.notes:
        lines.append(report.result.notes.strip())
    return "\n".join(lines)


def render_pr_comment(
    aggregate: Aggregate,
    decision: GateDecision,
    fingerprint: str,
    reports: Sequence[RunReport],
) -> str:
    """Short, dense, and honest about uncertainty."""
    icon = {"allow": "✅", "warn": "⚠️", "block": "🚫"}[decision.decision]
    lines = [
        f"{icon} **vigil: {decision.decision}**  (fingerprint `{fingerprint[:20]}`)",
        "",
        "| metric | value |",
        "|---|---|",
        f"| cases | {aggregate.n} |",
        f"| pass_rate | {aggregate.pass_rate:.3f} |",
        f"| p95 latency | {aggregate.p95_latency_ms} ms |",
        f"| p95 cost | ${aggregate.p95_cost_usd:.4f} |",
        f"| flake_rate | {aggregate.flake_rate:.3f} |",
        f"| needs_review | {aggregate.needs_review_rate:.3f} |",
        f"| policy_violations | {aggregate.policy_violations} |",
        "",
    ]
    if decision.reasons:
        lines.append("**Reasons**")
        lines.extend(f"- {reason}" for reason in decision.reasons)
        lines.append("")
    review = [r for r in reports if r.result.needs_review()]
    if review:
        lines.append("**Needs human review** (judge disagreement or abstention)")
        lines.extend(f"- `{r.case.case_id}` disagreement={r.result.disagreement()}" for r in review)
    return "\n".join(lines)


def load_cases(path: str) -> list[Any]:
    """Load a case file (JSON list) or a directory of *.json case files."""
    import os

    from .models.case import CaseManifest

    paths: list[str] = []
    if os.path.isdir(path):
        paths = sorted(
            os.path.join(path, name) for name in os.listdir(path) if name.endswith(".json")
        )
    else:
        paths = [path]

    cases: list[CaseManifest] = []
    for file_path in paths:
        with open(file_path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            cases.extend(CaseManifest.from_dict(item) for item in data)
        else:
            cases.append(CaseManifest.from_dict(data))
    return cases
