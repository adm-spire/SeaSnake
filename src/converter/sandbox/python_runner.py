"""Run normalized test cases against the original Python code.

The runner is a small self-contained script written into a temp directory. It
imports the user's module, invokes each function, and emits JSON outcomes. User
prints are captured so they cannot corrupt the JSON channel. Per-case wall-clock
timeouts use SIGALRM inside the sandboxed process.

The returned outcomes are raw dicts; the testing package converts them into its
typed models. That keeps the sandbox free of testing-layer imports.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.errors import SandboxError
from ..core.logging import get_logger
from .executor import SandboxExecutor

logger = get_logger(__name__)


RUNNER_SCRIPT = r'''
import contextlib
import importlib.util
import io
import json
import math
import signal
import sys


class CaseTimeout(BaseException):
    pass


def _raise_timeout(signum, frame):
    raise CaseTimeout()


signal.signal(signal.SIGALRM, _raise_timeout)


def load_module(path):
    spec = importlib.util.spec_from_file_location("user_module", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not create an import spec for the user module")
    module = importlib.util.module_from_spec(spec)
    sys.modules["user_module"] = module
    spec.loader.exec_module(module)
    return module


def to_jsonable(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("non-finite floats are not supported")
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("dictionary keys must be strings")
            result[key] = to_jsonable(item)
        return result
    raise TypeError("value of type " + type(value).__name__ + " is not JSON-serializable")


def describe_exception(exc):
    cls = type(exc)
    return {
        "kind": "error",
        "exception_type": cls.__name__,
        "exception_mro": [c.__name__ for c in cls.__mro__],
        "message": str(exc),
    }


def timeout_for(case):
    return float(case.get("timeout_s", 5))


def run_case(module, case):
    try:
        function = getattr(module, case["function"])
        captured = io.StringIO()
        signal.setitimer(signal.ITIMER_REAL, timeout_for(case))
        try:
            with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                value = function(*case.get("args", []), **case.get("kwargs", {}))
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        try:
            return {"test_id": case["test_id"], "kind": "value", "value": to_jsonable(value)}
        except Exception as exc:
            return {
                "test_id": case["test_id"],
                "kind": "unsupported",
                "message": str(exc),
            }
    except CaseTimeout:
        return {"test_id": case["test_id"], "kind": "timeout"}
    except Exception as exc:
        return {"test_id": case["test_id"], **describe_exception(exc)}


def main():
    cases_path = sys.argv[1]
    module_path = sys.argv[2]
    with open(cases_path, "r", encoding="utf-8") as handle:
        cases = json.load(handle)

    real_stdout = sys.stdout
    sink = io.StringIO()
    try:
        signal.setitimer(signal.ITIMER_REAL, 10)
        try:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                module = load_module(module_path)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
    except BaseException as exc:
        payload = [{"test_id": case["test_id"], **describe_exception(exc)} for case in cases]
        real_stdout.write(json.dumps(payload, allow_nan=False))
        return

    results = [run_case(module, case) for case in cases]
    real_stdout.write(json.dumps(results, allow_nan=False))


if __name__ == "__main__":
    main()
'''


@dataclass(frozen=True)
class PythonRunResult:
    outcomes: dict[str, dict[str, Any]]
    duration_ms: int
    stdout: str
    stderr: str


def run_python_cases(
    executor: SandboxExecutor,
    *,
    python_src: str,
    cases: list[dict[str, Any]],
    per_case_timeout_s: int,
    batch_timeout_s: int,
) -> PythonRunResult:
    if not cases:
        return PythonRunResult(outcomes={}, duration_ms=0, stdout="", stderr="")

    workdir = Path(tempfile.mkdtemp(prefix="converter-py-"))
    try:
        (workdir / "user_module.py").write_text(python_src, encoding="utf-8")
        (workdir / "runner.py").write_text(RUNNER_SCRIPT, encoding="utf-8")
        enriched = [
            {**case, "timeout_s": per_case_timeout_s}
            for case in cases
        ]
        (workdir / "cases.json").write_text(json.dumps(enriched), encoding="utf-8")

        result = executor.run(
            [executor.python_executable, "runner.py", "cases.json", "user_module.py"],
            workdir=workdir,
            timeout_s=batch_timeout_s,
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    if result.timed_out:
        logger.warning("Python validation batch timed out")
        return PythonRunResult(
            outcomes={str(case["test_id"]): {"kind": "timeout"} for case in cases},
            duration_ms=result.duration_ms,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    try:
        raw = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        raise SandboxError(
            "Python runner produced invalid JSON "
            f"(returncode={result.returncode}): {result.stderr[:1000]}"
        ) from exc

    if not isinstance(raw, list):
        raise SandboxError("Python runner returned an unexpected payload")

    outcomes: dict[str, dict[str, Any]] = {}
    for row in raw:
        if isinstance(row, dict) and "test_id" in row:
            outcomes[str(row["test_id"])] = row

    missing = [case["test_id"] for case in cases if str(case["test_id"]) not in outcomes]
    for test_id in missing:
        outcomes[str(test_id)] = {"kind": "crash", "message": "no result returned"}

    return PythonRunResult(
        outcomes=outcomes,
        duration_ms=result.duration_ms,
        stdout=result.stdout,
        stderr=result.stderr,
    )


__all__ = ["PythonRunResult", "run_python_cases"]
