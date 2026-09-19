"""Environment plugin: run cases inside a container.

Tier: maintained. Distributed separately because it needs a Docker daemon
(HARD-1 / HARD-4: no SDK in core; we shell out to the `docker` CLI so this
package stays dependency-free in Python terms).

Design rules that matter more than the code:

1. **Default deny.** `--read-only` + `--network none` unless the contract
   explicitly asks for more AND this environment declares the capability.
2. **No privilege escalation from case YAML.** Refusal is decided by
   `vigil.envbase.enforce` against declared capabilities (HARD-8).
3. **Honest snapshots.** `restore()` verifies the image is present and returns
   its digest. If it cannot, it raises -- the runner then reports
   UNDETERMINED instead of a comforting PASS.
4. **Agents cross the boundary as files, not callables.** The case and the
   agent file are mounted read-only and executed by `vigil.harness`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Sequence
from typing import Any

from vigil.envbase import enforce, snapshot_digest
from vigil.models.case import CaseManifest
from vigil.models.result import RunResult

DOCKER = "docker"

# Capabilities this environment actually provides.
# `live-side-effects` is deliberately NOT declared by default: opt in per
# deployment with DockerEnvironment(allow_live=True).
BASE_CAPABILITIES: tuple[str, ...] = (
    "container",
    "snapshot:image",
    "network-isolation",
    "open-network",
    "tool-mock",
)


class DockerUnavailable(RuntimeError):
    """No usable Docker daemon. Degrades to UNDETERMINED, never to PASS."""


def docker_available() -> bool:
    if shutil.which(DOCKER) is None:
        return False
    try:
        probe = subprocess.run(
            [DOCKER, "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


def build_run_args(
    image: str,
    case_path: str,
    agent_path: str,
    pkg_path: str,
    *,
    network_policy: str = "none",
    read_only: bool = True,
    extra_env: dict[str, str] | None = None,
    memory: str | None = None,
    cpus: str | None = None,
) -> list[str]:
    """Assemble the `docker run` command.

    Kept pure and separately testable: no daemon needed to verify that the
    isolation flags are what we claim in the docs.
    """
    args = [DOCKER, "run", "--rm"]

    if read_only:
        args.append("--read-only")

    args.extend(["--network", "none" if network_policy == "none" else "bridge"])
    args.extend(["--pids-limit", "256"])
    args.extend(["--security-opt", "no-new-privileges"])

    if memory:
        args.extend(["--memory", memory])
    if cpus:
        args.extend(["--cpus", cpus])

    # Mounts are read-only: a case must not be able to rewrite its own oracle
    # or its own agent from inside the sandbox.
    args.extend(["-v", f"{os.path.abspath(case_path)}:/vigil/case/case.json:ro"])
    args.extend(["-v", f"{os.path.abspath(agent_path)}:/vigil/case/agent.py:ro"])
    args.extend(["-v", f"{os.path.abspath(pkg_path)}:/vigil/pkg:ro"])
    args.extend(["-w", "/vigil/case"])

    env = {"PYTHONPATH": "/vigil/pkg", "PYTHONDONTWRITEBYTECODE": "1"}
    env.update(extra_env or {})
    for key in sorted(env):
        args.extend(["-e", f"{key}={env[key]}"])

    args.append(image)
    args.extend(
        [
            "python",
            "-m",
            "vigil.harness",
            "--case",
            "/vigil/case/case.json",
            "--agent",
            "/vigil/case/agent.py",
        ]
    )
    return args


class DockerEnvHandle:
    def __init__(self, contract: dict[str, Any], capabilities: Sequence[str]) -> None:
        self.contract = contract
        self.capabilities = tuple(capabilities)
        self.image = contract.get("init_snapshot") or contract.get("image") or ""
        self._workspace: str | None = None
        self._pkg_path = _core_source_path()

    def restore(self) -> str:
        """Verify the image exists and return a digest of image + contract.

        Raises if the daemon or image is unavailable: an unverified world
        cannot support a replay claim.
        """
        if not self.image:
            raise DockerUnavailable("contract declares no image / init_snapshot")
        if not docker_available():
            raise DockerUnavailable("docker daemon is not reachable")

        inspect = subprocess.run(
            [DOCKER, "image", "inspect", "--format", "{{.Id}}", self.image],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if inspect.returncode != 0:
            if not self.contract.get("pull", True):
                raise DockerUnavailable(f"image not present: {self.image}")
            pulled = subprocess.run(
                [DOCKER, "pull", self.image],
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            if pulled.returncode != 0:
                raise DockerUnavailable(f"cannot pull image {self.image}: {pulled.stderr}")
            inspect = subprocess.run(
                [DOCKER, "image", "inspect", "--format", "{{.Id}}", self.image],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if inspect.returncode != 0:
                raise DockerUnavailable(f"image unavailable after pull: {self.image}")

        image_id = inspect.stdout.strip()
        return snapshot_digest({**self.contract, "image_id": image_id})

    def execute(self, case: CaseManifest, agent: Any) -> RunResult:
        enforce(self.contract, self.capabilities)

        agent_path = getattr(agent, "path", None)
        if not agent_path:
            raise DockerUnavailable(
                "docker environment cannot ship a live Python callable into a "
                "container; pass the agent as a file path"
            )

        workspace = tempfile.mkdtemp(prefix="vigil-docker-")
        self._workspace = workspace
        case_path = os.path.join(workspace, "case.json")
        with open(case_path, "w", encoding="utf-8") as fh:
            json.dump(case.to_dict(), fh, sort_keys=True, ensure_ascii=False)

        read_only = self.contract.get("side_effect_policy", "dry-run") != "live"
        args = build_run_args(
            self.image,
            case_path,
            agent_path,
            self._pkg_path,
            network_policy=self.contract.get("network_policy", "none"),
            read_only=read_only,
            extra_env=dict(self.contract.get("env_vars") or {}),
            memory=self.contract.get("memory"),
            cpus=self.contract.get("cpus"),
        )
        started = time.monotonic()
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=int(self.contract.get("timeout_s", 300)),
            check=False,
        )
        elapsed = int((time.monotonic() - started) * 1000)

        if completed.returncode != 0:
            return RunResult(
                case_id=case.case_id,
                outcome="ERROR",
                notes=(
                    f"container exited {completed.returncode}\n"
                    f"stdout: {completed.stdout[:2000]}\n"
                    f"stderr: {completed.stderr[:2000]}"
                ),
                latency_ms=elapsed,
            )

        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            return RunResult(
                case_id=case.case_id,
                outcome="ERROR",
                notes=f"harness output is not JSON: {exc}\n{completed.stdout[:1000]}",
                latency_ms=elapsed,
            )

        result = RunResult.from_dict(payload)
        if result.latency_ms == 0:
            result.latency_ms = elapsed
        return result

    def teardown(self) -> None:
        if self._workspace and os.path.isdir(self._workspace):
            shutil.rmtree(self._workspace, ignore_errors=True)
        self._workspace = None


class DockerEnvironment:
    name = "docker"
    version = "0.1.0"

    def __init__(self, allow_live: bool = False) -> None:
        self.allow_live = allow_live
        self.capabilities = BASE_CAPABILITIES + (("live-side-effects",) if allow_live else ())

    def provision(self, contract: dict[str, Any]) -> DockerEnvHandle:
        # Refuse before touching the daemon: a contract that asks for more
        # than this environment provides is a configuration error, not a
        # runtime surprise.
        enforce(contract, self.capabilities)
        return DockerEnvHandle(contract, self.capabilities)


def _core_source_path() -> str:
    """Locate the `vigil` package source so it can be mounted read-only.

    The sandbox gets PYTHONPATH=/vigil/pkg; mounting source rather than the
    installed package keeps the container dependency-free.
    """
    import vigil

    package_dir = os.path.dirname(os.path.abspath(vigil.__file__))
    return os.path.dirname(package_dir)  # .../src
