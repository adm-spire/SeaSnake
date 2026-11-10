"""Run the benchmark suite.

Usage:
    python -m converter.evals.runner
    python -m converter.evals.runner --program strings --max-attempts 2

Programs live in ``evals/programs``. A program may ship user tests in
``<name>_tests.py``. The runner never invokes pytest directly; test sources are
ingested through the same normalized pipeline as the API.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from ..agent.runner import ConversionRequest, run_conversion
from ..agent.services import build_services
from ..core.config import Settings
from ..core.errors import ConverterError, InputValidationError
from ..core.logging import configure_logging
from .metrics import ProgramResult, aggregate, result_from_state, results_as_dicts

PROGRAMS_DIR = Path(__file__).resolve().parent / "programs"


def discover_programs(names: list[str] | None = None) -> list[Path]:
    candidates = sorted(
        path
        for path in PROGRAMS_DIR.glob("*.py")
        if path.name != "__init__.py" and not path.name.endswith("_tests.py")
    )
    if not names:
        return candidates
    wanted = set(names)
    return [path for path in candidates if path.stem in wanted]


def run_suite(
    names: list[str] | None,
    *,
    settings: Settings,
    max_attempts: int | None,
) -> list[ProgramResult]:
    results: list[ProgramResult] = []
    for program in discover_programs(names):
        source = program.read_text(encoding="utf-8")
        tests_path = program.with_name(f"{program.stem}_tests.py")
        tests = tests_path.read_text(encoding="utf-8") if tests_path.is_file() else None

        services = build_services(settings)
        started = time.perf_counter()
        try:
            state = run_conversion(
                ConversionRequest(
                    python_src=source,
                    user_tests=tests,
                    max_attempts=max_attempts,
                ),
                services=services,
            )
            latency = time.perf_counter() - started
            results.append(
                result_from_state(program.stem, state, latency_s=latency)
            )
        except (InputValidationError, ConverterError) as exc:
            latency = time.perf_counter() - started
            results.append(
                ProgramResult(
                    name=program.stem,
                    status="error",
                    compile_ok=False,
                    overall_rate=0.0,
                    latency_s=latency,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
        except Exception as exc:  # keep the suite running across programs
            latency = time.perf_counter() - started
            results.append(
                ProgramResult(
                    name=program.stem,
                    status="error",
                    compile_ok=False,
                    overall_rate=0.0,
                    latency_s=latency,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Python-to-Rust converter evals")
    parser.add_argument(
        "--program",
        action="append",
        dest="programs",
        help="program stem to run (repeatable); default: all",
    )
    parser.add_argument("--max-attempts", type=int, default=None)
    parser.add_argument("--json", action="store_true", help="print JSON only")
    arguments = parser.parse_args(argv)

    settings = Settings()
    configure_logging(settings.log_level)
    results = run_suite(
        arguments.programs,
        settings=settings,
        max_attempts=arguments.max_attempts,
    )
    summary = aggregate(results)

    payload = {
        "summary": summary,
        "results": results_as_dicts(results),
    }
    if arguments.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        for result in results:
            print(
                f"{result.name:20s} {result.status:8s} "
                f"compile={result.compile_ok!s:5s} "
                f"match={result.overall_rate:6.1%} "
                f"repairs={result.repair_iterations} "
                f"cost=${result.cost_usd:.4f} "
                f"{result.error or ''}"
            )
        print("\nSummary")
        print(json.dumps(summary, indent=2, default=str))

    return 0 if all(result.status in {"passed", "failed"} for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
