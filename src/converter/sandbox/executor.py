"""Sandboxed command execution.

Security model
--------------
All user-supplied Python and all generated C is untrusted. The preferred
executor runs every command in a fresh Docker container with:

* no network (``--network none``)
* a read-only root filesystem
* a writable tmpfs for ``/tmp`` only
* dropped capabilities and ``no-new-privileges``
* CPU, memory, and PID limits
* the host's uid/gid so the bind-mounted work directory is writable
* a hard wall-clock timeout, after which the container is removed

The subprocess fallback is intentionally less isolated (no network namespace).
It is only used when Docker is unavailable and the config allows it; this is
documented in the README.
"""

from __future__ import annotations

import math
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..core.config import Settings
from ..core.errors import SandboxError
from ..core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ExecResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int


class SandboxExecutor:
    """Interface shared by the Docker and subprocess backends."""

    python_executable: str = "python3"

    def run(
        self,
        command: list[str],
        *,
        workdir: str | Path,
        timeout_s: int,
        env: dict[str, str] | None = None,
    ) -> ExecResult:
        raise NotImplementedError


class DockerSandboxExecutor(SandboxExecutor):
    python_executable = "python3"

    def __init__(
        self,
        *,
        image: str,
        memory_mb: int = 512,
        cpus: float = 1.0,
        pids_limit: int = 128,
    ) -> None:
        self._image = image
        self._memory_mb = memory_mb
        self._cpus = cpus
        self._pids_limit = pids_limit

    def ensure_available(self) -> None:
        if shutil.which("docker") is None:
            raise SandboxError("docker CLI not found")
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", self._image],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SandboxError(f"could not query docker: {exc}") from exc
        if result.returncode != 0:
            raise SandboxError(
                f"sandbox image {self._image!r} is not available; build it with "
                "docker build -f docker/Dockerfile.sandbox -t "
                f"{self._image} ."
            )

    def run(
        self,
        command: list[str],
        *,
        workdir: str | Path,
        timeout_s: int,
        env: dict[str, str] | None = None,
    ) -> ExecResult:
        workdir_path = Path(workdir).resolve()
        if not workdir_path.is_dir():
            raise SandboxError(f"workdir does not exist: {workdir_path}")

        container_name = f"converter-sandbox-{uuid.uuid4().hex[:12]}"
        docker_command = [
            "docker",
            "run",
            "--name",
            container_name,
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,exec,nosuid,nodev",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            f"{self._memory_mb}m",
            "--memory-swap",
            f"{self._memory_mb}m",
            "--cpus",
            str(self._cpus),
            "--pids-limit",
            str(self._pids_limit),
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-e",
            "HOME=/tmp",
        ]
        for key, value in (env or {}).items():
            docker_command.extend(["-e", f"{key}={value}"])
        docker_command.extend(
            [
                "-v",
                f"{workdir_path}:/workdir:rw",
                "-w",
                "/workdir",
                self._image,
                *command,
            ]
        )

        started = time.perf_counter()
        timed_out = False
        try:
            try:
                completed = subprocess.run(
                    docker_command,
                    capture_output=True,
                    text=True,
                    timeout=timeout_s + 10,
                    check=False,
                )
                stdout, stderr, returncode = (
                    completed.stdout,
                    completed.stderr,
                    completed.returncode,
                )
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                stdout = _decode(exc.stdout)
                stderr = _decode(exc.stderr)
                returncode = -1
            except OSError as exc:
                raise SandboxError(f"could not start docker: {exc}") from exc
        finally:
            # Containers are not started with --rm so a timeout can be cleaned up
            # reliably by name. Remove it in all cases.
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )

        duration_ms = int((time.perf_counter() - started) * 1000)
        if timed_out:
            logger.warning("sandbox command timed out after %ss: %s", timeout_s, command)
        return ExecResult(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            duration_ms=duration_ms,
        )


class SubprocessExecutor(SandboxExecutor):
    """Fallback executor: CPU/file-size limits, no network namespace.

    Memory and PID limits are deliberately Docker-only. RLIMIT_NPROC is
    per-user (it would throttle the developer's whole session), and RLIMIT_AS
    breaks compiler builds which reserve large thread stacks. The README is
    explicit that Docker is the secure path.
    """

    python_executable = sys.executable or "python3"

    def __init__(self, *, memory_mb: int = 512, pids_limit: int = 128) -> None:
        del memory_mb, pids_limit

    def run(
        self,
        command: list[str],
        *,
        workdir: str | Path,
        timeout_s: int,
        env: dict[str, str] | None = None,
    ) -> ExecResult:
        workdir_path = Path(workdir).resolve()
        if not workdir_path.is_dir():
            raise SandboxError(f"workdir does not exist: {workdir_path}")

        sanitized_env = _sanitized_env(workdir_path)
        sanitized_env.update(env or {})

        started = time.perf_counter()
        timed_out = False

        def apply_limits() -> None:
            os.setsid()
            _apply_rlimits(timeout_s=timeout_s)

        try:
            process = subprocess.Popen(
                command,
                cwd=str(workdir_path),
                env=sanitized_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=apply_limits,
            )
        except OSError as exc:
            raise SandboxError(f"could not start command {command!r}: {exc}") from exc
        try:
            stdout, stderr = process.communicate(timeout=timeout_s)
            returncode = process.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
            returncode = -1

        duration_ms = int((time.perf_counter() - started) * 1000)
        if timed_out:
            logger.warning("subprocess command timed out after %ss: %s", timeout_s, command)
        return ExecResult(
            returncode=returncode,
            stdout=stdout or "",
            stderr=stderr or "",
            timed_out=timed_out,
            duration_ms=duration_ms,
        )


def _decode(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _sanitized_env(workdir: Path) -> dict[str, str]:
    """Pass only variables needed to run tools, never application secrets."""
    allowed = {
        "PATH",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "SSL_CERT_FILE",
        "CC",
        "CFLAGS",
        "LDFLAGS",
    }
    env = {key: value for key, value in os.environ.items() if key in allowed}
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    env.setdefault("LANG", "C.UTF-8")

    env["HOME"] = str(workdir)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _apply_rlimits(*, timeout_s: int) -> None:
    try:
        import resource
    except ImportError:  # pragma: no cover - Windows
        return

    limits = [
        (resource.RLIMIT_CPU, (int(math.ceil(timeout_s)) + 1, int(math.ceil(timeout_s)) + 2)),
        (resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024)),
    ]
    for resource_name, values in limits:
        try:
            resource.setrlimit(resource_name, values)
        except (ValueError, OSError):
            continue


def build_executor(settings: Settings) -> SandboxExecutor:
    """Return a Docker executor when possible, otherwise the configured fallback."""
    if settings.sandbox_mode == "subprocess":
        return SubprocessExecutor(
            memory_mb=settings.sandbox_memory_mb,
            pids_limit=settings.sandbox_pids_limit,
        )

    docker = DockerSandboxExecutor(
        image=settings.sandbox_image,
        memory_mb=settings.sandbox_memory_mb,
        cpus=settings.sandbox_cpus,
        pids_limit=settings.sandbox_pids_limit,
    )
    try:
        docker.ensure_available()
    except SandboxError:
        if not settings.sandbox_fallback_to_subprocess:
            raise
        logger.warning("Docker sandbox unavailable; falling back to subprocess execution")
        return SubprocessExecutor(
            memory_mb=settings.sandbox_memory_mb,
            pids_limit=settings.sandbox_pids_limit,
        )
    return docker
