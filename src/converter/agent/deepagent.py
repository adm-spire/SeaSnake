"""Deep-agent translator.

The outer LangGraph owns correctness gates (compile, differential verification,
pass criteria). This module supplies an *inner* autonomous agent that owns only
``src/user_code.rs`` inside a temporary crate and iterates with real tools:

* filesystem tools (rooted at the temp crate, path traversal blocked)
* ``build_rust`` -> cargo via the sandbox executor
* ``run_differential`` -> the verified baseline through the built binary

Keeping the harness files out of the agent's control means the JSON I/O contract
and panic handling cannot drift. The node still feeds the final file back through
the deterministic compile/verify nodes, so the agent never certifies itself.

Dependencies on ``deepagents``/``langchain_openai`` are imported lazily so the
rest of the converter works if the optional stack is unavailable.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from pydantic import SecretStr

from ..core.config import Settings
from ..core.errors import LLMError
from ..core.usage import UsageTracker
from ..sandbox.rust_runner import (
    PLACEHOLDER_USER_CODE,
    build_existing,
    cleanup_workdir,
    create_workdir,
    prepare_workdir,
    run_cases,
)
from ..testing.models import BaselineCase
from ..translation.prompts import (
    DEEP_AGENT_SYSTEM_PROMPT,
    build_deep_task_text,
    format_baseline_text,
)
from ..verification.differ import (
    describe_actual,
    describe_expected,
    rust_actual_from_raw,
)
from ..verification.models import FailureCase
from ..verification.scoring import score_results

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

    from ..testing.analysis import FunctionInfo
    from .services import Services

try:  # langchain-core is a langgraph dependency, so this import is always safe.
    from langchain_core.callbacks import BaseCallbackHandler
except ImportError:  # pragma: no cover - defensive for minimal installs
    BaseCallbackHandler = object  # type: ignore[assignment,misc]


class UsageCallbackHandler(BaseCallbackHandler):
    """Record LangChain LLM calls into the project's per-run UsageTracker.

    Deep agents bypass ``TrackedLLM``, so token/latency accounting has to come
    from callbacks instead. Each ``on_llm_end`` is one model call.
    """

    def __init__(self, tracker: UsageTracker) -> None:
        super().__init__()
        self._tracker = tracker
        self._started: dict[Any, float] = {}

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        **kwargs: Any,
    ) -> None:
        self._mark(kwargs.get("run_id"))

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        **kwargs: Any,
    ) -> None:
        self._mark(kwargs.get("run_id"))

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        run_id = kwargs.get("run_id")
        started = self._started.pop(run_id, None) if run_id is not None else None
        latency_ms = int((time.perf_counter() - started) * 1000) if started else 0
        prompt_tokens, completion_tokens = _extract_usage(response)
        self._tracker.record(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )

    def _mark(self, run_id: Any) -> None:
        if run_id is not None:
            self._started[run_id] = time.perf_counter()


def _extract_usage(response: Any) -> tuple[int, int]:
    prompt = 0
    completion = 0
    for generations in getattr(response, "generations", []) or []:
        for generation in generations:
            message = getattr(generation, "message", None)
            usage = getattr(message, "usage_metadata", None)
            if usage:
                prompt += int(usage.get("input_tokens", 0) or 0)
                completion += int(usage.get("output_tokens", 0) or 0)

    if prompt == 0 and completion == 0:
        llm_output = getattr(response, "llm_output", None) or {}
        token_usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
        prompt = int(token_usage.get("prompt_tokens", token_usage.get("input_tokens", 0)) or 0)
        completion = int(
            token_usage.get("completion_tokens", token_usage.get("output_tokens", 0)) or 0
        )
    return prompt, completion


def build_chat_model(settings: Settings) -> BaseChatModel:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:  # pragma: no cover - dependency missing
        raise LLMError(
            "deep agents require `langchain-openai`; run `pip install -e .`"
        ) from exc

    if not settings.llm_api_key:
        raise LLMError("LLM_API_KEY is not configured")

    # DeepSeek speaks the OpenAI chat-completions dialect. Force chat completions
    # (not the Responses API) so the swap is purely configuration.
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=SecretStr(settings.llm_api_key),
        base_url=settings.llm_base_url,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
        use_responses_api=False,
    )


def _make_tools(
    services: Services,
    *,
    workdir: str,
    python_src: str,
    baseline: list[BaselineCase],
):
    from langchain_core.tools import tool

    settings = services.settings

    @tool
    def build_rust() -> str:
        """Compile the crate and return cargo diagnostics."""
        result = build_existing(
            services.executor,
            workdir=workdir,
            timeout_s=settings.compile_timeout_s,
        )
        if result.ok:
            return "Build succeeded."
        return "Build failed. Fix the diagnostics below.\n\n" + result.diagnostics[-12000:]

    @tool
    def run_differential() -> str:
        """Run every verified baseline case through the compiled binary."""
        if not baseline:
            return "No baseline cases are available."

        cases = [
            {
                "test_id": case.test_id,
                "function": case.function,
                "args": case.args,
                "kwargs": case.kwargs,
            }
            for case in baseline
        ]
        try:
            raw = run_cases(
                services.executor,
                workdir=workdir,
                cases=cases,
                timeout_s=settings.run_timeout_s,
            )
        except Exception as exc:  # noqa: BLE001 - report tool failure to the model
            return (
                f"Could not run the binary ({type(exc).__name__}: {exc}). "
                "Run build_rust first."
            )

        actuals = {test_id: rust_actual_from_raw(raw) for test_id, raw in raw.items()}
        summary = score_results(baseline, actuals)
        if not summary.failures:
            return (
                f"All {summary.overall_total} baseline case(s) passed. "
                "The translation is complete."
            )

        lines = [f"{summary.overall_passed}/{summary.overall_total} baseline case(s) passed."]
        lines.append("Failing cases (input, expected, actual, reason):")
        for failure in summary.failures[:40]:
            lines.append(_describe_failure(failure))
        if len(summary.failures) > 40:
            lines.append(f"... {len(summary.failures) - 40} more failures omitted")
        return "\n".join(lines)

    @tool
    def read_python_source() -> str:
        """Return the Python source whose behavior must be preserved."""
        return python_src

    @tool
    def read_baseline() -> str:
        """Return the verified input -> outcome baseline."""
        return format_baseline_text(baseline)

    return [build_rust, run_differential, read_python_source, read_baseline]


def _describe_failure(failure: FailureCase) -> str:
    return (
        f"- {failure.name}: {failure.function}("
        f"args={failure.args!r}, kwargs={failure.kwargs!r}) "
        f"[{failure.category.value}, {failure.source.value}]\n"
        f"  expected: {describe_expected(failure.expected)}\n"
        f"  actual:   {describe_actual(failure.actual)}\n"
        f"  reason:   {failure.reason}"
    )


def build_deep_coder(
    services: Services,
    *,
    workdir: str,
    python_src: str,
    baseline: list[BaselineCase],
) -> Any:
    try:
        from deepagents import create_deep_agent
        from deepagents.backends.filesystem import FilesystemBackend
    except ImportError as exc:  # pragma: no cover - dependency missing
        raise LLMError(
            "deep agents require the `deepagents` package; run `pip install -e .`"
        ) from exc

    # virtual_mode maps "/" to the temp crate and rejects "..", so the built-in
    # file tools cannot read or write outside the sandbox workdir.
    backend = FilesystemBackend(root_dir=workdir, virtual_mode=True)
    return create_deep_agent(
        model=build_chat_model(services.settings),
        tools=_make_tools(
            services, workdir=workdir, python_src=python_src, baseline=baseline
        ),
        system_prompt=DEEP_AGENT_SYSTEM_PROMPT,
        backend=backend,
        name="rust-translator",
    )


def run_deep_agent(
    services: Services,
    *,
    python_src: str,
    functions: list[FunctionInfo],
    baseline: list[BaselineCase],
    rust_code: str | None = None,
    diagnostics: str = "",
    failures: list[FailureCase] | None = None,
    attempt: int = 0,
) -> str:
    """Run the deep agent and return the final ``src/user_code.rs`` contents."""
    if not services.settings.llm_api_key:
        raise LLMError("LLM_API_KEY is not configured")

    from langchain_core.messages import HumanMessage

    workdir = create_workdir()
    try:
        prepare_workdir(workdir)
        if rust_code:
            from pathlib import Path

            Path(workdir, "src", "user_code.rs").write_text(rust_code, encoding="utf-8")

        agent = build_deep_coder(
            services, workdir=workdir, python_src=python_src, baseline=baseline
        )
        message = build_deep_task_text(
            python_src=python_src,
            functions=functions,
            baseline=baseline,
            rust_code=rust_code,
            diagnostics=diagnostics,
            failures=failures,
            attempt=attempt,
        )
        handler = UsageCallbackHandler(services.tracker)

        try:
            agent.invoke(
                {"messages": [HumanMessage(content=message)]},
                config={
                    "recursion_limit": services.settings.deep_agent_max_steps,
                    "callbacks": [handler],
                },
            )
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize agent failures
            raise LLMError(
                f"deep agent failed: {type(exc).__name__}: {exc}"
            ) from exc

        from pathlib import Path

        code = Path(workdir, "src", "user_code.rs").read_text(encoding="utf-8")
        return validate_user_code(code, stage="translation" if not rust_code else "repair")
    finally:
        cleanup_workdir(workdir)


def validate_user_code(code: str, *, stage: str) -> str:
    """Reject empty, placeholder, or non-conforming agent output."""
    stripped = code.strip()
    if not stripped or stripped == PLACEHOLDER_USER_CODE.strip():
        raise LLMError(f"deep agent ({stage}) produced no Rust code")
    if "fn dispatch" not in stripped:
        raise LLMError(f"deep agent ({stage}) output does not define `fn dispatch`")
    return stripped.rstrip() + "\n"


__all__ = [
    "UsageCallbackHandler",
    "build_chat_model",
    "build_deep_coder",
    "run_deep_agent",
    "validate_user_code",
]
