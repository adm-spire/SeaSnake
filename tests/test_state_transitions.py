from types import SimpleNamespace

from converter.agent.nodes.capture_baseline import capture_baseline_node
from converter.agent.nodes.ingest_tests import ingest_tests_node
from converter.agent.nodes.report import build_error_report, report_node
from converter.agent.state import ConverterState
from converter.core.config import Settings
from converter.core.usage import UsageTracker
from converter.testing.models import (
    BaselineCase,
    Category,
    ExpectedKind,
    ExpectedOutcome,
    NormalizedTest,
    PythonOutcome,
    Source,
)
from converter.verification.models import RustActual


def make_state(**overrides) -> ConverterState:
    data = {
        "run_id": "run-1",
        "python_src": "def f(x):\n    return x + 1\n",
        "test_mode": "user",
    }
    data.update(overrides)
    return ConverterState(**data)


def test_ingest_node_populates_normalized_tests():
    state = make_state(
        user_tests="def test_f():\n    assert f(1) == 2\n",
    )
    services = SimpleNamespace(settings=Settings())
    updates = ingest_tests_node(state, services)

    assert len(updates["test_cases"]) == 1
    assert updates["test_cases"][0].function == "f"
    assert updates["invalid_user_tests"] == []


def test_ingest_node_records_invalid_tests():
    state = make_state(
        user_tests="def test_f():\n    value = f(1)\n    assert value == 2\n",
    )
    services = SimpleNamespace(settings=Settings())
    updates = ingest_tests_node(state, services)

    assert updates["test_cases"] == []
    assert len(updates["invalid_user_tests"]) == 1


def make_test(value=3):
    return NormalizedTest(
        id="t1",
        name="test_f",
        function="f",
        args=[2],
        kwargs={},
        category=Category.HAPPY_PATH,
        source=Source.USER,
        expected=ExpectedOutcome(kind=ExpectedKind.VALUE, value=value),
    )


def test_capture_baseline_uses_actual_python_outcome():
    test = make_test(value=999)
    state = make_state(
        test_cases=[test],
        python_outcomes={"t1": PythonOutcome(kind="value", value=3)},
    )
    updates = capture_baseline_node(state, SimpleNamespace())

    assert len(updates["baseline"]) == 1
    assert updates["baseline"][0].expected.value == 3


def make_baseline():
    return BaselineCase(
        test_id="t1",
        name="test_f",
        function="f",
        args=[2],
        kwargs={},
        category=Category.HAPPY_PATH,
        source=Source.USER,
        expected=ExpectedOutcome(kind=ExpectedKind.VALUE, value=3),
    )


def test_report_node_marks_passing_run_as_passed():
    state = make_state(
        baseline=[make_baseline()],
        rust_results={"t1": RustActual(kind="value", value=3)},
        status="verified",
    )
    services = SimpleNamespace(tracker=UsageTracker())
    updates = report_node(state, services)

    assert updates["status"] == "passed"
    assert updates["report"].status == "passed"
    assert updates["report"].total_tests == 1


def test_report_node_marks_missing_result_as_failed():
    state = make_state(
        baseline=[make_baseline()],
        rust_results={},
        status="verified",
    )
    services = SimpleNamespace(tracker=UsageTracker())
    updates = report_node(state, services)

    assert updates["status"] == "failed"
    assert len(updates["report"].failed_tests) == 1


def test_build_error_report_is_terminal_error():
    state = make_state(python_src="def broken(", test_mode="generate")
    report = build_error_report(state, ValueError("boom"), UsageTracker().snapshot())

    assert report.status == "error"
    assert report.last_error is not None
    assert "boom" in report.last_error
