from converter.testing.models import ExpectedKind, ExpectedOutcome
from converter.verification.differ import compare_outcome, rust_actual_from_raw
from converter.verification.models import RustActual


def value_expected(value):
    return ExpectedOutcome(kind=ExpectedKind.VALUE, value=value)


def error_expected(exception_type, mro=None, pattern=None):
    return ExpectedOutcome(
        kind=ExpectedKind.ERROR,
        exception_type=exception_type,
        exception_mro=mro or [],
        message_pattern=pattern,
    )


def test_equal_value_passes():
    result = compare_outcome(value_expected({"a": 1}), RustActual(kind="value", value={"a": 1}))
    assert result.ok


def test_dict_order_does_not_matter():
    result = compare_outcome(
        value_expected({"a": 1, "b": 2}),
        RustActual(kind="value", value={"b": 2, "a": 1}),
    )
    assert result.ok


def test_bool_is_not_equal_to_int():
    result = compare_outcome(value_expected(True), RustActual(kind="value", value=1))
    assert not result.ok


def test_float_tolerance():
    result = compare_outcome(value_expected(0.1 + 0.2), RustActual(kind="value", value=0.3))
    assert result.ok


def test_error_variant_must_match():
    result = compare_outcome(
        error_expected("ValueError"),
        RustActual(kind="error", error_variant="TypeError", message="bad"),
    )
    assert not result.ok


def test_error_mro_maps_subclass():
    result = compare_outcome(
        error_expected("ValueError", ["UnicodeDecodeError", "ValueError"]),
        RustActual(kind="error", error_variant="ValueError", message="bad"),
    )
    assert result.ok


def test_panic_never_satisfies_expected_error():
    result = compare_outcome(
        error_expected("ValueError"),
        RustActual(kind="panic"),
    )
    assert not result.ok
    assert "panicked" in result.reason


def test_message_pattern_is_checked():
    result = compare_outcome(
        error_expected("ValueError", pattern="must be positive"),
        RustActual(kind="error", error_variant="ValueError", message="value must be positive"),
    )
    assert result.ok

    result = compare_outcome(
        error_expected("ValueError", pattern="must be positive"),
        RustActual(kind="error", error_variant="ValueError", message="different"),
    )
    assert not result.ok


def test_timeout_fails_value_expectation():
    result = compare_outcome(value_expected(1), RustActual(kind="timeout"))
    assert not result.ok


def test_rust_actual_from_raw():
    actual = rust_actual_from_raw(
        {"test_id": "t", "kind": "error", "error_variant": "KeyError", "message": "x"}
    )
    assert actual.kind == "error"
    assert actual.error_variant == "KeyError"
