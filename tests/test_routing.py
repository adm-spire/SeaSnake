from converter.agent.routing import (
    route_after_compile,
    route_after_validate,
    route_after_verify,
    route_test_mode,
)
from converter.agent.state import ConverterState


def make_state(**overrides) -> ConverterState:
    data = {
        "run_id": "run-1",
        "python_src": "def f(x):\n    return x\n",
        "test_mode": "generate",
    }
    data.update(overrides)
    return ConverterState(**data)


def test_route_test_mode_branches():
    assert route_test_mode(make_state(test_mode="user")) == "ingest_tests"
    assert route_test_mode(make_state(test_mode="augment")) == "ingest_tests"
    assert route_test_mode(make_state(test_mode="generate")) == "generate_tests"


def test_validate_routes_to_generation_when_gaps_remain():
    state = make_state(
        test_mode="generate",
        coverage_gaps=["missing edge case"],
        generation_round=0,
        max_generation_rounds=2,
    )
    assert route_after_validate(state) == "generate_tests"


def test_validate_routes_to_baseline_when_round_cap_hit():
    state = make_state(
        test_mode="generate",
        coverage_gaps=["missing edge case"],
        generation_round=2,
        max_generation_rounds=2,
    )
    assert route_after_validate(state) == "capture_baseline"


def test_user_mode_never_regenerates():
    state = make_state(
        test_mode="user",
        coverage_gaps=["missing edge case"],
        generation_round=0,
        max_generation_rounds=2,
    )
    assert route_after_validate(state) == "capture_baseline"


def test_compile_routes_to_verify_on_success():
    assert route_after_compile(make_state(compile_ok=True)) == "verify"


def test_compile_routes_to_repair_while_attempts_remain():
    state = make_state(compile_ok=False, attempt=0, max_attempts=3)
    assert route_after_compile(state) == "repair"


def test_compile_routes_to_report_when_attempts_exhausted():
    state = make_state(compile_ok=False, attempt=3, max_attempts=3)
    assert route_after_compile(state) == "report"


def test_verify_routes_to_report_when_passing():
    assert route_after_verify(make_state(pass_failures=[])) == "report"


def test_verify_routes_to_repair_while_attempts_remain():
    state = make_state(pass_failures=["edge_case below threshold"], attempt=1, max_attempts=3)
    assert route_after_verify(state) == "repair"


def test_verify_routes_to_report_when_attempts_exhausted():
    state = make_state(pass_failures=["edge_case below threshold"], attempt=3, max_attempts=3)
    assert route_after_verify(state) == "report"
