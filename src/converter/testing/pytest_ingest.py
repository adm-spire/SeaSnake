"""Parse a constrained subset of pytest into NormalizedTest objects.

Supported test shapes (Phase 1):

* ``assert f(...) == <literal or parametrized value>``
* ``assert <literal> == f(...)``
* ``with pytest.raises(SomeError): f(...)``
* ``with pytest.raises(SomeError, match="..."): f(...)``
* ``pytest.raises(SomeError, f, ...)``
* ``@pytest.mark.parametrize(...)`` with literal value lists
* multiple supported statements per test function

Anything else is reported as an InvalidUserTest with a reason. Nothing is
silently dropped.
"""

from __future__ import annotations

import ast
import itertools
import math
from dataclasses import dataclass
from typing import Any

from ..core.errors import InputValidationError
from .models import (
    Category,
    ExpectedKind,
    ExpectedOutcome,
    InvalidUserTest,
    NormalizedTest,
    Source,
)


class UnsupportedTest(Exception):
    """A test shape the Phase 1 ingester cannot normalize."""


@dataclass(frozen=True)
class IngestResult:
    tests: list[NormalizedTest]
    invalid: list[InvalidUserTest]


@dataclass(frozen=True)
class _CallSpec:
    function: str
    args: list[Any]
    kwargs: dict[str, Any]


@dataclass(frozen=True)
class _CaseSpec:
    name: str
    call: _CallSpec
    expected: ExpectedOutcome
    category: Category


def ingest_pytest_source(source: str, *, max_cases: int = 500) -> IngestResult:
    if not source.strip():
        return IngestResult(tests=[], invalid=[])

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise InputValidationError(f"user tests have a syntax error: {exc}") from exc

    tests: list[NormalizedTest] = []
    invalid: list[InvalidUserTest] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and _contains_test_method(node):
            invalid.append(
                InvalidUserTest(
                    name=node.name,
                    reason="class-based tests are not supported; use module-level test functions",
                    raw_source=ast.get_source_segment(source, node),
                )
            )
            continue
        if isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("test_"):
            invalid.append(
                InvalidUserTest(
                    name=node.name,
                    reason="async tests are not supported",
                    raw_source=ast.get_source_segment(source, node),
                )
            )
            continue
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        raw_source = ast.get_source_segment(source, node)
        try:
            case_specs = _extract_from_test(node)
        except UnsupportedTest as exc:
            invalid.append(
                InvalidUserTest(name=node.name, reason=str(exc), raw_source=raw_source)
            )
            continue

        for index, spec in enumerate(case_specs):
            if len(tests) >= max_cases:
                raise InputValidationError(
                    f"user tests expand to more than {max_cases} normalized cases"
                )
            display_name = (
                node.name if len(case_specs) == 1 else f"{node.name}[{index}]"
            )
            tests.append(
                NormalizedTest(
                    id=f"user-{len(tests) + 1}-{node.name}-{index}",
                    name=display_name,
                    function=spec.call.function,
                    args=spec.call.args,
                    kwargs=spec.call.kwargs,
                    category=spec.category,
                    source=Source.USER,
                    expected=spec.expected,
                    raw_source=raw_source,
                )
            )

    return IngestResult(tests=tests, invalid=invalid)


def _contains_test_method(node: ast.ClassDef) -> bool:
    return any(
        isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        and child.name.startswith("test_")
        for child in node.body
    )


def _extract_from_test(node: ast.FunctionDef) -> list[_CaseSpec]:
    if node.args.vararg is not None or node.args.kwarg is not None:
        raise UnsupportedTest("test functions with *args/**kwargs are not supported")

    declared = [
        argument.arg
        for argument in (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        )
    ]
    combinations = _parametrize_combinations(node)
    covered = set(combinations[0]) if combinations else set()
    unbound = [name for name in declared if name not in covered]
    if unbound:
        raise UnsupportedTest(
            "unbound test parameters (fixtures are not supported): "
            + ", ".join(unbound)
        )

    specs: list[_CaseSpec] = []

    body = list(node.body)
    if _is_docstring(body[0] if body else None):
        body = body[1:]

    for params in combinations:
        for statement in body:
            if isinstance(statement, ast.Pass):
                continue
            if isinstance(statement, ast.Assert):
                specs.append(_from_assert(statement, params, node.name))
            elif isinstance(statement, ast.With):
                specs.append(_from_with(statement, params, node.name))
            elif (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Call)
                and _is_named_call(statement.value.func, "raises")
            ):
                specs.append(_from_raises_call(statement.value, params, node.name))
            else:
                raise UnsupportedTest(
                    f"unsupported statement in test body: {type(statement).__name__}"
                )

    if not specs:
        raise UnsupportedTest("test contains no supported assertion")

    return specs


def _is_docstring(node: ast.AST | None) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _parametrize_combinations(node: ast.FunctionDef) -> list[dict[str, Any]]:
    value_sets: list[list[dict[str, Any]]] = []
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        if not _is_named_call(decorator.func, "parametrize"):
            continue
        if len(decorator.args) != 2:
            raise UnsupportedTest("parametrize expects a name list and a value list")

        names = _parametrize_names(decorator.args[0])
        try:
            raw_values = ast.literal_eval(decorator.args[1])
        except (ValueError, SyntaxError, TypeError) as exc:
            raise UnsupportedTest("parametrize values must be literals") from exc
        if not isinstance(raw_values, (list, tuple)):
            raise UnsupportedTest("parametrize values must be a list or tuple")

        entries: list[dict[str, Any]] = []
        for raw_value in raw_values:
            if len(names) == 1:
                entries.append({names[0]: raw_value})
            else:
                if not isinstance(raw_value, (list, tuple)) or len(raw_value) != len(names):
                    raise UnsupportedTest(
                        "parametrize rows must be tuples matching the parameter names"
                    )
                entries.append(dict(zip(names, raw_value, strict=True)))
        value_sets.append(entries)

    if not value_sets:
        return [{}]

    combinations: list[dict[str, Any]] = []
    for parts in itertools.product(*value_sets):
        merged: dict[str, Any] = {}
        for part in parts:
            if set(merged) & set(part):
                raise UnsupportedTest("duplicate parametrize parameter name")
            merged.update(part)
        combinations.append(merged)
    return combinations


def _parametrize_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        names = [part.strip() for part in node.value.split(",") if part.strip()]
    elif isinstance(node, (ast.List, ast.Tuple)):
        names = []
        for element in node.elts:
            if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
                raise UnsupportedTest("parametrize names must be strings")
            names.append(element.value)
    else:
        raise UnsupportedTest("parametrize names must be a string or a list of strings")
    if not names:
        raise UnsupportedTest("parametrize names cannot be empty")
    return names


def _from_assert(statement: ast.Assert, params: dict[str, Any], test_name: str) -> _CaseSpec:
    test = statement.test
    if not (
        isinstance(test, ast.Compare)
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
    ):
        raise UnsupportedTest("only `assert f(...) == expected` comparisons are supported")

    left, right = test.left, test.comparators[0]

    left_is_approx = _is_approx_call(left)
    right_is_approx = _is_approx_call(right)

    if left_is_approx and right_is_approx:
        raise UnsupportedTest("assertion cannot compare two pytest.approx values")

    if left_is_approx or right_is_approx:
        call_node = right if left_is_approx else left
        expected_node = left if left_is_approx else right
    else:
        left_call = _try_call(left, params)
        right_call = _try_call(right, params)
        if (left_call is None) == (right_call is None):
            raise UnsupportedTest("expected exactly one function call in the assertion")
        if left_call is not None:
            call_node, expected_node = left, right
        else:
            call_node, expected_node = right, left

    call = _try_call(call_node, params)
    if call is None:
        raise UnsupportedTest("assertion does not call a target function")

    value, approx = _expected_value(expected_node, params)
    return _CaseSpec(
        name=test_name,
        call=call,
        expected=ExpectedOutcome(kind=ExpectedKind.VALUE, value=value, approx=approx),
        category=_category_for_name(test_name),
    )


def _from_with(statement: ast.With, params: dict[str, Any], test_name: str) -> _CaseSpec:
    if len(statement.items) != 1:
        raise UnsupportedTest("only single-context `with pytest.raises(...)` is supported")
    item = statement.items[0]
    context = item.context_expr
    if not isinstance(context, ast.Call) or not _is_named_call(context.func, "raises"):
        raise UnsupportedTest("only `with pytest.raises(...)` is supported")

    exception_type, message_pattern = _raises_arguments(context, params)

    body = [stmt for stmt in statement.body if not isinstance(stmt, ast.Pass)]
    if len(body) != 1 or not isinstance(body[0], ast.Expr) or not isinstance(body[0].value, ast.Call):
        raise UnsupportedTest(
            "pytest.raises block must contain exactly one function call"
        )

    call = _try_call(body[0].value, params)
    if call is None:
        raise UnsupportedTest("pytest.raises block does not call a target function")

    return _CaseSpec(
        name=test_name,
        call=call,
        expected=ExpectedOutcome(
            kind=ExpectedKind.ERROR,
            exception_type=exception_type,
            message_pattern=message_pattern,
        ),
        category=Category.ERROR_CONDITION,
    )


def _from_raises_call(
    expression: ast.Call, params: dict[str, Any], test_name: str
) -> _CaseSpec:
    if not expression.args:
        raise UnsupportedTest("pytest.raises needs an exception type")
    exception_type, message_pattern = _raises_arguments(expression, params)

    if len(expression.args) < 2:
        raise UnsupportedTest("pytest.raises callable form needs a target function")
    target = expression.args[1]
    target_name = _callable_name(target)
    if target_name is None:
        raise UnsupportedTest("pytest.raises target must be a plain function name")

    if expression.keywords:
        raise UnsupportedTest("pytest.raises callable form does not support keyword arguments")

    args = [_eval_expr(argument, params) for argument in expression.args[2:]]
    return _CaseSpec(
        name=test_name,
        call=_CallSpec(function=target_name, args=args, kwargs={}),
        expected=ExpectedOutcome(
            kind=ExpectedKind.ERROR,
            exception_type=exception_type,
            message_pattern=message_pattern,
        ),
        category=Category.ERROR_CONDITION,
    )


def _raises_arguments(
    call: ast.Call, params: dict[str, Any]
) -> tuple[str, str | None]:
    if not call.args:
        raise UnsupportedTest("pytest.raises needs an exception type")
    exception_type = _exception_name(call.args[0])

    message_pattern: str | None = None
    for keyword in call.keywords:
        if keyword.arg == "match":
            pattern = _eval_expr(keyword.value, params)
            if not isinstance(pattern, str):
                raise UnsupportedTest("pytest.raises match= must be a string literal")
            message_pattern = pattern
        elif keyword.arg is not None:
            raise UnsupportedTest(
                f"unsupported pytest.raises keyword: {keyword.arg}"
            )
    return exception_type, message_pattern


def _exception_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    raise UnsupportedTest("exception type must be a plain name")


def _try_call(node: ast.AST, params: dict[str, Any]) -> _CallSpec | None:
    if not isinstance(node, ast.Call):
        return None
    name = _callable_name(node.func)
    if name is None:
        return None
    if any(isinstance(argument, ast.Starred) for argument in node.args):
        raise UnsupportedTest("starred call arguments are not supported")
    if any(keyword.arg is None for keyword in node.keywords):
        raise UnsupportedTest("**kwargs call arguments are not supported")

    args = [_eval_expr(argument, params) for argument in node.args]
    kwargs: dict[str, Any] = {}
    for keyword in node.keywords:
        if keyword.arg is None:
            raise UnsupportedTest("**kwargs call arguments are not supported")
        kwargs[keyword.arg] = _eval_expr(keyword.value, params)
    return _CallSpec(function=name, args=args, kwargs=kwargs)


def _callable_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_named_call(node: ast.AST, name: str) -> bool:
    return _callable_name(node) == name


def _is_approx_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _is_named_call(node.func, "approx")


def _expected_value(node: ast.AST, params: dict[str, Any]) -> tuple[Any, bool]:
    if _is_approx_call(node):
        assert isinstance(node, ast.Call)
        if len(node.args) != 1 or node.keywords:
            raise UnsupportedTest("pytest.approx supports exactly one positional value")
        return _eval_expr(node.args[0], params), True
    return _eval_expr(node, params), False


class _ParamSubstituter(ast.NodeTransformer):
    def __init__(self, params: dict[str, Any]) -> None:
        self._params = params

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if node.id in self._params:
            return _literal_node(self._params[node.id])
        return node


def _literal_node(value: Any) -> ast.AST:
    return ast.parse(repr(value), mode="eval").body


def _eval_expr(node: ast.AST, params: dict[str, Any]) -> Any:
    transformed = _ParamSubstituter(params).visit(node)
    ast.fix_missing_locations(transformed)
    try:
        value = ast.literal_eval(transformed)
    except (ValueError, SyntaxError, TypeError) as exc:
        raise UnsupportedTest(
            f"expression is not a literal or parametrized value: {ast.unparse(node)}"
        ) from exc
    return _ensure_jsonable(value)


def _ensure_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise UnsupportedTest("non-finite floats are not supported")
        return value
    if isinstance(value, (list, tuple)):
        return [_ensure_jsonable(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise UnsupportedTest("dictionary keys must be strings")
        return {key: _ensure_jsonable(item) for key, item in value.items()}
    raise UnsupportedTest(f"value of type {type(value).__name__} is not JSON-serializable")


def _category_for_name(name: str) -> Category:
    lowered = name.lower()
    if any(
        word in lowered
        for word in ("edge", "empty", "boundary", "invalid", "zero", "negative", "unicode")
    ):
        return Category.EDGE_CASE
    return Category.HAPPY_PATH
