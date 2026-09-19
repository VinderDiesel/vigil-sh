import json

from vigil.harness import load_callable, run_one
from vigil.models.case import CaseManifest
from vigil.models.result import RunResult

AGENT = "examples/minimal-agent/agent.py"


def test_load_callable():
    fn = load_callable(AGENT)
    case = CaseManifest(case_id="c1", input={"question": "refund-policy"})
    assert fn(case).artifacts["output"]


def test_run_one_returns_result():
    fn = load_callable(AGENT)
    case = CaseManifest(case_id="c1", input={"question": "refund-policy"})
    result = run_one(case, fn)
    assert isinstance(result, RunResult)
    assert result.case_id == "c1"


def test_crash_becomes_error_not_silent_pass():
    def boom(case):
        raise RuntimeError("boom")

    result = run_one(CaseManifest(case_id="c1"), boom)
    assert result.outcome == "ERROR"
    assert "RuntimeError" in result.notes


def test_wrong_return_type_becomes_error():
    result = run_one(CaseManifest(case_id="c1"), lambda case: "a string")
    assert result.outcome == "ERROR"


def test_cli_writes_json(tmp_path):
    from vigil.harness import main

    case_path = tmp_path / "case.json"
    out_path = tmp_path / "result.json"
    case_path.write_text(
        json.dumps(
            {
                "case_id": "c1",
                "spec_version": "v1alpha1",
                "input": {"question": "refund-policy"},
                "oracle": {"contains": ["14 days"]},
            }
        )
    )
    exit_code = main(["--case", str(case_path), "--agent", AGENT, "--out", str(out_path)])
    assert exit_code == 0
    payload = json.loads(out_path.read_text())
    assert payload["artifacts"]["output"]
