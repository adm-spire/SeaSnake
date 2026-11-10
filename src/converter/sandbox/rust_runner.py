"""Build and run the generated Rust crate.

The crate layout is fixed:

    Cargo.toml
    src/main.rs          # converter-owned harness
    src/harness.rs       # converter-owned helpers
    src/error_prelude.rs # converter-owned error enum
    src/user_code.rs     # LLM-authored translation

The LLM only owns ``src/user_code.rs``, so the JSON I/O contract and panic
handling cannot be broken by translation mistakes.
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
from .executor import ExecResult, SandboxExecutor

logger = get_logger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent / "rust_harness"
PRELUDE_PATH = Path(__file__).resolve().parent.parent / "errors_map" / "rust_prelude.rs"
BINARY_NAME = "converter_sandbox"
BINARY_RELATIVE_PATH = Path("target") / "release" / BINARY_NAME

# Written only so the crate is buildable before the agent authors a translation.
# The deep-agent runner treats an unchanged placeholder as "no code produced".
PLACEHOLDER_USER_CODE = """\
//! Placeholder: the translation agent replaces this file.

use crate::error_prelude::ConvError;

pub fn dispatch(
    _case: &crate::harness::Case,
) -> Result<serde_json::Value, ConvError> {
    Err(ConvError::Other {
        python_type: "NotImplementedError".to_string(),
        message: "translation not written yet".to_string(),
    })
}
"""


@dataclass(frozen=True)
class BuildResult:
    ok: bool
    diagnostics: str
    workdir: str
    duration_ms: int
    stdout: str
    stderr: str


def create_workdir(prefix: str = "converter-rust-") -> str:
    return tempfile.mkdtemp(prefix=prefix)


def cleanup_workdir(workdir: str | None) -> None:
    if workdir:
        shutil.rmtree(workdir, ignore_errors=True)


def prepare_workdir(workdir: str) -> str:
    """Populate a workdir with the converter-owned harness and a stub user file.

    The deep agent edits ``src/user_code.rs`` in place, so this never overwrites
    an existing translation.
    """
    workdir_path = Path(workdir)
    workdir_path.mkdir(parents=True, exist_ok=True)
    shutil.copytree(TEMPLATE_DIR, workdir_path, dirs_exist_ok=True)
    (workdir_path / "src" / "error_prelude.rs").write_text(
        PRELUDE_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    user_code = workdir_path / "src" / "user_code.rs"
    if not user_code.exists():
        user_code.write_text(PLACEHOLDER_USER_CODE, encoding="utf-8")
    return str(workdir_path)


def build_existing(
    executor: SandboxExecutor,
    *,
    workdir: str,
    timeout_s: int,
) -> BuildResult:
    """Compile a workdir as-is, without rewriting ``user_code.rs``."""
    workdir_path = Path(workdir)
    result = executor.run(
        ["cargo", "build", "--offline", "--release"],
        workdir=workdir_path,
        timeout_s=timeout_s,
    )
    return _build_result(result, workdir_path, timeout_s)


def build(
    executor: SandboxExecutor,
    *,
    rust_code: str,
    workdir: str,
    timeout_s: int,
) -> BuildResult:
    workdir_path = Path(workdir)
    prepare_workdir(workdir)
    (workdir_path / "src" / "user_code.rs").write_text(rust_code, encoding="utf-8")
    return build_existing(executor, workdir=workdir, timeout_s=timeout_s)


def _build_result(
    result: ExecResult, workdir_path: Path, timeout_s: int
) -> BuildResult:
    binary = workdir_path / BINARY_RELATIVE_PATH
    ok = result.returncode == 0 and not result.timed_out and binary.is_file()
    diagnostics = (result.stdout + "\n" + result.stderr).strip()
    if result.timed_out:
        diagnostics = f"cargo build timed out after {timeout_s}s\n{diagnostics}"
    if not ok and not diagnostics:
        diagnostics = f"cargo build failed with return code {result.returncode}"

    return BuildResult(
        ok=ok,
        diagnostics=diagnostics[:20000],
        workdir=str(workdir_path),
        duration_ms=result.duration_ms,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def run_cases(
    executor: SandboxExecutor,
    *,
    workdir: str,
    cases: list[dict[str, Any]],
    timeout_s: int,
) -> dict[str, dict[str, Any]]:
    """Run cases through the built binary and return raw outcome dicts by test id."""
    if not cases:
        return {}

    workdir_path = Path(workdir)
    binary = workdir_path / BINARY_RELATIVE_PATH
    if not binary.is_file():
        raise SandboxError("Rust binary is missing; build did not succeed")

    (workdir_path / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    results_path = workdir_path / "results.json"
    results_path.unlink(missing_ok=True)

    result = executor.run(
        [f"./{BINARY_RELATIVE_PATH.as_posix()}", "cases.json", "results.json"],
        workdir=workdir_path,
        timeout_s=timeout_s,
    )

    if result.timed_out:
        logger.warning("Rust differential run timed out")
        return {str(case["test_id"]): {"kind": "timeout"} for case in cases}

    if result.returncode != 0 or not results_path.is_file():
        message = (result.stderr or result.stdout or "Rust runner crashed")[:2000]
        logger.warning("Rust runner failed: %s", message)
        return {
            str(case["test_id"]): {"kind": "crash", "message": message}
            for case in cases
        }

    try:
        raw = json.loads(results_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SandboxError(f"could not read Rust results: {exc}") from exc

    outcomes: dict[str, dict[str, Any]] = {}
    for row in raw:
        if isinstance(row, dict) and "test_id" in row:
            outcomes[str(row["test_id"])] = row

    for case in cases:
        outcomes.setdefault(
            str(case["test_id"]), {"kind": "crash", "message": "no result returned"}
        )
    return outcomes


__all__ = [
    "BINARY_RELATIVE_PATH",
    "BuildResult",
    "PLACEHOLDER_USER_CODE",
    "build",
    "build_existing",
    "cleanup_workdir",
    "create_workdir",
    "prepare_workdir",
    "run_cases",
]
