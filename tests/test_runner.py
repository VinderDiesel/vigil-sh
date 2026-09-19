from vigil.models.case import CaseManifest
from vigil.models.gate import SLO
from vigil.models.result import JudgeVerdict, RunResult
from vigil.runner import aggregate, decide, run_case, run_suite


def make_case(case_id="c1", oracle=None, mode="mock-replay"):
    return CaseManifest(
        case_id=case_id,
        oracle=oracle or {"exact": "ok"},
        replay_mode=mode,
    )


def agent(result="ok"):
    def _run(case):
        return RunResult(
            case_id=case.case_id,
            artifacts={"output": result},
        )

    return _run


def test_pass_when_oracle_matches():
    report = run_case(make_case(), agent("ok"))
    assert report.result.outcome == "PASS"


def test_fail_when_oracle_mismatches():
    report = run_case(make_case(), agent("nope"))
    assert report.result.outcome == "FAIL"


def test_abstention_is_not_a_pass():
    case = make_case(oracle={"irrelevant": True})
    report = run_case(case, agent("ok"))
    assert report.result.outcome == "UNDETERMINED"
    assert report.result.needs_review() is True


def test_agent_exception_becomes_error_not_pass():
    def boom(case):
        raise RuntimeError("agent exploded")

    report = run_case(make_case(), boom)
    assert report.result.outcome == "ERROR"


def test_record_only_case_warns():
    report = run_case(make_case(mode="record-only"), agent("ok"))
    assert any("record-only" in w for w in report.warnings)


def test_aggregate_counts_flake():
    calls = {"n": 0}

    def flaky(case):
        calls["n"] += 1
        output = "ok" if calls["n"] % 2 else "bad"
        return RunResult(case_id=case.case_id, artifacts={"output": output})

    _, agg = run_suite([make_case()], flaky, repeats=2)
    assert agg.flake_rate == 1.0


def test_hard_slo_blocks():
    agg = aggregate([])
    slos = [SLO(metric="policy_violations", op="max", value=0, hard=True)]
    decision = decide(agg, slos)
    assert decision.decision == "allow"

    class FakeAgg:
        n = 1
        pass_rate = 0.0
        p95_latency_ms = 0
        p95_cost_usd = 0.0
        intervention_rate = 0.0
        unrecoverable_rate = 0.0
        policy_violations = 2
        flake_rate = 0.0
        needs_review_rate = 0.0

    decision = decide(FakeAgg(), slos)  # type: ignore[arg-type]
    assert decision.decision == "block"
    assert decision.exit_code == 1


def test_disagreement_flags_review():
    result = RunResult(case_id="c1", outcome="PASS")
    result.verdicts = [
        JudgeVerdict(judge="a", judge_version="1", score=1.0),
        JudgeVerdict(judge="b", judge_version="1", score=0.0),
    ]
    assert result.disagreement() == 1.0
    assert result.needs_review() is True
