import pytest

from converter.core.errors import InputValidationError
from converter.testing.models import Category, ExpectedKind
from converter.testing.pytest_ingest import ingest_pytest_source

SOURCE = """
import pytest

def test_add():
    assert add(1, 2) == 3

def test_reversed():
    assert 5 == add(2, 3)

def test_raises():
    with pytest.raises(ZeroDivisionError):
        divide(1, 0)

def test_message():
    with pytest.raises(ValueError, match="positive"):
        parse("-1")

def test_approx():
    assert mean([1, 2, 3, 4]) == pytest.approx(2.5)

def test_callable_raises():
    pytest.raises(ValueError, parse, "abc")

def test_unsupported():
    value = add(1, 2)
    assert value == 3

def test_nonliteral(x=1):
    assert add(x, 1) == 2
"""


def test_supported_assertions_are_normalized():
    result = ingest_pytest_source(SOURCE)
    names = {test.name for test in result.tests}
    assert "test_add" in names
    assert "test_reversed" in names

    add_test = next(test for test in result.tests if test.name == "test_add")
    assert add_test.function == "add"
    assert add_test.args == [1, 2]
    assert add_test.expected.kind == ExpectedKind.VALUE
    assert add_test.expected.value == 3
    assert add_test.category == Category.HAPPY_PATH


def test_raises_context_and_message_pattern():
    result = ingest_pytest_source(SOURCE)
    raises_test = next(test for test in result.tests if test.name == "test_raises")
    assert raises_test.expected.kind == ExpectedKind.ERROR
    assert raises_test.expected.exception_type == "ZeroDivisionError"
    assert raises_test.category == Category.ERROR_CONDITION

    message_test = next(test for test in result.tests if test.name == "test_message")
    assert message_test.expected.message_pattern == "positive"


def test_approx_is_recorded():
    result = ingest_pytest_source(SOURCE)
    approx_test = next(test for test in result.tests if test.name == "test_approx")
    assert approx_test.expected.approx is True
    assert approx_test.expected.value == 2.5


def test_callable_raises_form():
    result = ingest_pytest_source(SOURCE)
    callable_test = next(
        test for test in result.tests if test.name == "test_callable_raises"
    )
    assert callable_test.function == "parse"
    assert callable_test.args == ["abc"]
    assert callable_test.expected.exception_type == "ValueError"


def test_unsupported_tests_are_reported_not_dropped():
    result = ingest_pytest_source(SOURCE)
    invalid_names = {invalid.name for invalid in result.invalid}
    assert "test_unsupported" in invalid_names
    assert "test_nonliteral" in invalid_names
    assert all(invalid.reason for invalid in result.invalid)


def test_parametrize_expands_cases():
    source = """
import pytest

@pytest.mark.parametrize("x,y,expected", [(1, 2, 3), (3, 4, 7)])
def test_pair(x, y, expected):
    assert add(x, y) == expected
"""
    result = ingest_pytest_source(source)
    assert len(result.tests) == 2
    assert result.tests[0].args == [1, 2]
    assert result.tests[1].args == [3, 4]
    assert result.tests[0].expected.value == 3


def test_multiple_asserts_become_multiple_cases():
    source = """
def test_multi():
    assert f(1) == 1
    assert f(2) == 2
"""
    result = ingest_pytest_source(source)
    assert len(result.tests) == 2
    assert result.tests[0].name == "test_multi[0]"
    assert result.tests[1].name == "test_multi[1]"


def test_non_comparison_assert_is_unsupported():
    result = ingest_pytest_source("def test_truthy():\n    assert f(1)\n")
    assert not result.tests
    assert len(result.invalid) == 1


def test_syntax_error_raises_input_validation_error():
    with pytest.raises(InputValidationError):
        ingest_pytest_source("def broken(")


def test_fixture_parameters_are_reported_as_unsupported():
    source = """
def test_with_fixture(fixture):
    assert f(1) == 2
"""
    result = ingest_pytest_source(source)
    assert not result.tests
    assert "fixtures are not supported" in result.invalid[0].reason


def test_async_tests_are_reported_as_unsupported():
    source = """
async def test_async():
    assert f(1) == 2
"""
    result = ingest_pytest_source(source)
    assert not result.tests
    assert "async tests" in result.invalid[0].reason


def test_class_based_tests_are_reported_as_unsupported():
    source = """
class TestThing:
    def test_method(self):
        assert f(1) == 2
"""
    result = ingest_pytest_source(source)
    assert not result.tests
    assert "class-based tests" in result.invalid[0].reason
