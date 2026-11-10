from pathlib import Path
from types import SimpleNamespace

import pytest

from converter.agent.deepagent import (
    UsageCallbackHandler,
    _extract_usage,
    validate_user_code,
)
from converter.core.errors import LLMError
from converter.core.usage import UsageTracker
from converter.sandbox.rust_runner import (
    PLACEHOLDER_USER_CODE,
    prepare_workdir,
)
from converter.testing.analysis import analyze_public_functions
from converter.testing.models import (
    BaselineCase,
    Category,
    ExpectedKind,
    ExpectedOutcome,
    Source,
)
from converter.translation.prompts import build_deep_task_text


def make_baseline():
    return [
        BaselineCase(
            test_id="t1",
            name="test_add",
            function="add",
            args=[1, 2],
            kwargs={},
            category=Category.HAPPY_PATH,
            source=Source.USER,
            expected=ExpectedOutcome(kind=ExpectedKind.VALUE, value=3),
        )
    ]


def test_validate_user_code_accepts_dispatch():
    code = "pub fn dispatch(case: &crate::harness::Case) -> Result<(), ()> { Ok(()) }\n"
    assert validate_user_code(code, stage="translation").endswith("\n")


@pytest.mark.parametrize("code", ["", "   ", PLACEHOLDER_USER_CODE])
def test_validate_user_code_rejects_empty_or_placeholder(code):
    with pytest.raises(LLMError):
        validate_user_code(code, stage="translation")


def test_validate_user_code_requires_dispatch():
    with pytest.raises(LLMError, match="dispatch"):
        validate_user_code("pub fn add(a: i64) -> i64 { a }", stage="repair")


def test_prepare_workdir_keeps_existing_translation(tmp_path: Path):
    prepare_workdir(str(tmp_path))
    user_code = tmp_path / "src" / "user_code.rs"
    assert user_code.read_text() == PLACEHOLDER_USER_CODE

    user_code.write_text("// real translation\n", encoding="utf-8")
    prepare_workdir(str(tmp_path))
    assert user_code.read_text() == "// real translation\n"
    assert (tmp_path / "src" / "error_prelude.rs").is_file()


def test_build_deep_task_text_includes_translation_and_repair_context():
    src = "def add(a, b):\n    return a + b\n"
    message = build_deep_task_text(
        python_src=src,
        functions=analyze_public_functions(src),
        baseline=make_baseline(),
    )
    assert "Verified baseline" in message
    assert "/src/user_code.rs" in message

    repair = build_deep_task_text(
        python_src=src,
        functions=analyze_public_functions(src),
        baseline=make_baseline(),
        rust_code="fn dispatch() {}",
        diagnostics="mismatch",
        attempt=2,
    )
    assert repair.startswith("Repair attempt 2.")
    assert "fn dispatch() {}" in repair
    assert "mismatch" in repair


class _Message:
    usage_metadata = {"input_tokens": 11, "output_tokens": 4}


class _Generation:
    message = _Message()


class _Response:
    generations = [[_Generation()]]
    llm_output = None


def test_extract_usage_reads_message_metadata():
    assert _extract_usage(_Response()) == (11, 4)


class _LlamaResponse:
    generations: list = []
    llm_output = {"token_usage": {"prompt_tokens": 7, "completion_tokens": 3}}


def test_extract_usage_falls_back_to_llm_output():
    assert _extract_usage(_LlamaResponse()) == (7, 3)


def test_usage_callback_records_into_tracker():
    tracker = UsageTracker(prompt_cost_per_1k=1.0, completion_cost_per_1k=1.0)
    handler = UsageCallbackHandler(tracker)

    handler.on_llm_end(_Response(), run_id="run-1")

    snapshot = tracker.snapshot()
    assert snapshot.prompt_tokens == 11
    assert snapshot.completion_tokens == 4
    assert snapshot.total_tokens == 15
    assert snapshot.llm_calls == 1
    assert snapshot.cost_usd == pytest.approx(0.015)


def test_build_chat_model_requires_api_key():
    from converter.agent.deepagent import build_chat_model
    from converter.core.config import Settings

    with pytest.raises(LLMError):
        build_chat_model(Settings(llm_api_key=None))


class _ScriptedModel:
    """Minimal chat model that emits a write_file tool call, then finishes."""

    def __new__(cls, responses):
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.outputs import ChatGeneration, ChatResult
        from pydantic import PrivateAttr

        class _Model(BaseChatModel):
            responses: list
            _index: int = PrivateAttr(default=0)

            @property
            def _llm_type(self) -> str:
                return "scripted"

            def bind_tools(self, tools, **kwargs):
                return self

            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                message = self.responses[min(self._index, len(self.responses) - 1)]
                object.__setattr__(self, "_index", self._index + 1)
                return ChatResult(generations=[ChatGeneration(message=message)])

        return _Model(responses=responses)


def test_run_deep_agent_writes_reads_and_cleans_up(monkeypatch):
    from langchain_core.messages import AIMessage

    from converter.agent import deepagent
    from converter.core.config import Settings

    valid_code = (
        "pub fn dispatch(_case: &crate::harness::Case) "
        "-> Result<serde_json::Value, crate::error_prelude::ConvError> { "
        "Ok(serde_json::Value::Null) }\n"
    )
    write_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "write_file",
                "args": {"file_path": "/src/user_code.rs", "content": valid_code},
                "id": "call-1",
            }
        ],
    )
    captured = {}

    def fake_build_deep_coder(services, *, workdir, python_src, baseline):
        from deepagents import create_deep_agent
        from deepagents.backends.filesystem import FilesystemBackend

        captured["workdir"] = workdir
        return create_deep_agent(
            model=_ScriptedModel([write_call, AIMessage(content="done")]),
            tools=[],
            system_prompt="test",
            backend=FilesystemBackend(root_dir=workdir, virtual_mode=True),
        )

    monkeypatch.setattr(deepagent, "build_deep_coder", fake_build_deep_coder)

    src = "def add(a, b):\n    return a + b\n"
    services = SimpleNamespace(
        settings=Settings(llm_api_key="test", deep_agent_max_steps=10),
        tracker=UsageTracker(),
    )
    result = deepagent.run_deep_agent(
        services,
        python_src=src,
        functions=analyze_public_functions(src),
        baseline=make_baseline(),
    )

    assert "fn dispatch" in result
    assert not Path(captured["workdir"]).exists()
