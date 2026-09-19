import json
from pathlib import Path

import pytest
from vigil.envbase import CapabilityError
from vigil.models.case import CaseManifest
from vigil.models.result import RunResult

from vigil_env_docker import (
    DockerEnvironment,
    DockerUnavailable,
    build_run_args,
    docker_available,
)

HERE = Path(__file__).resolve().parent
EXAMPLE_CASE = str(HERE.parent / "examples" / "case.json")

needs_docker = pytest.mark.skipif(not docker_available(), reason="no Docker daemon available")


# ---- pure logic: no daemon required ---------------------------------------


def test_capabilities_are_declared():
    env = DockerEnvironment()
    assert "container" in env.capabilities
    assert "snapshot:image" in env.capabilities


def test_live_side_effects_are_refused_by_default():
    env = DockerEnvironment()
    with pytest.raises(CapabilityError):
        env.provision({"image": "python:3.11-slim", "side_effect_policy": "live"})


def test_live_is_possible_only_when_opted_in():
    env = DockerEnvironment(allow_live=True)
    assert "live-side-effects" in env.capabilities
    env.provision({"image": "python:3.11-slim", "side_effect_policy": "live"})


def test_allowlist_network_is_refused_because_we_cannot_enforce_it():
    env = DockerEnvironment()
    with pytest.raises(CapabilityError):
        env.provision({"image": "x", "network_policy": "allowlist", "allowlist": ["a.com"]})


def test_snapshot_requirement_is_enforced():
    env = DockerEnvironment()
    with pytest.raises(CapabilityError):
        env.provision({"image": "x", "init_snapshot": "snap"})


def test_run_args_default_to_read_only_and_no_network():
    args = build_run_args("img:1", "case.json", "agent.py", "/src")
    assert "--read-only" in args
    assert args[args.index("--network") + 1] == "none"


def test_run_args_open_network_opt_in():
    args = build_run_args("img:1", "c", "a", "/src", network_policy="open")
    assert args[args.index("--network") + 1] == "bridge"


def test_run_args_disable_read_only_for_live():
    args = build_run_args("img:1", "c", "a", "/src", read_only=False)
    assert "--read-only" not in args


def test_mounts_are_read_only():
    args = build_run_args("img:1", "case.json", "agent.py", "/src")
    mounts = [args[i + 1] for i, a in enumerate(args) if a == "-v"]
    assert all(m.endswith(":ro") for m in mounts), mounts
    assert any("/vigil/case/case.json:ro" in m for m in mounts)
    assert any("/vigil/case/agent.py:ro" in m for m in mounts)


def test_pythonpath_is_set_for_the_mounted_core():
    args = build_run_args("img:1", "c", "a", "/src")
    env_args = [args[i + 1] for i, a in enumerate(args) if a == "-e"]
    assert "PYTHONPATH=/vigil/pkg" in env_args


def test_no_new_privileges_and_pid_limit():
    args = build_run_args("img:1", "c", "a", "/src")
    assert "no-new-privileges" in args
    assert "--pids-limit" in args


def test_resource_limits_when_requested():
    args = build_run_args("img:1", "c", "a", "/src", memory="512m", cpus="1.0")
    assert args[args.index("--memory") + 1] == "512m"
    assert args[args.index("--cpus") + 1] == "1.0"


def test_harness_is_the_container_entrypoint():
    args = build_run_args("img:1", "c", "a", "/src")
    assert args[-4:] == ["--case", "/vigil/case/case.json", "--agent", "/vigil/case/agent.py"]
    assert "vigil.harness" in args


def test_execute_refuses_a_live_callable():
    env = DockerEnvironment()
    handle = env.provision({"image": "python:3.11-slim", "network_policy": "none"})
    with pytest.raises(DockerUnavailable, match="live Python callable"):
        handle.execute(CaseManifest(case_id="c1"), lambda case: RunResult(case_id="c1"))


def test_conformance_contract():
    from vigil.conformance import assert_environment_contract

    assert_environment_contract(DockerEnvironment)


# ---- integration: needs a daemon ------------------------------------------


@needs_docker
def test_restore_verifies_image_and_returns_digest(tmp_path):
    env = DockerEnvironment()
    handle = env.provision({"image": "python:3.11-slim", "network_policy": "none"})
    digest = handle.restore()
    assert digest


@needs_docker
def test_end_to_end_run_in_container():
    agent_path = str(HERE.parent.parent.parent / "examples" / "minimal-agent" / "agent.py")
    with open(EXAMPLE_CASE, encoding="utf-8") as fh:
        case = CaseManifest.from_dict(json.load(fh))

    from vigil.runner import run_case

    report = run_case(case, agent_path, env_name="docker", scorers=("exact",))
    assert report.env_restored, report.warnings
    assert report.result.outcome == "PASS", report.result.notes
