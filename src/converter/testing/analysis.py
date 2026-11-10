"""Static analysis helpers for the supported Python subset."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from ..core.errors import InputValidationError


@dataclass(frozen=True)
class FunctionInfo:
    name: str
    signature: str
    params: tuple[str, ...]
    has_varargs: bool
    has_kwargs: bool
    line: int


def source_line_count(source: str) -> int:
    return len(source.splitlines())


def enforce_source_limit(source: str, max_lines: int) -> None:
    line_count = source_line_count(source)
    if line_count > max_lines:
        raise InputValidationError(
            f"Python source is {line_count} lines; the limit is {max_lines} lines"
        )


def analyze_public_functions(source: str) -> list[FunctionInfo]:
    """Return top-level public functions with their signatures.

    Lines that cannot be parsed as Python raise InputValidationError so the API
    can return a 4xx rather than starting a doomed conversion.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise InputValidationError(f"Python source has a syntax error: {exc}") from exc

    functions: list[FunctionInfo] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue
        arguments = node.args
        params = [arg.arg for arg in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)]
        signature = f"def {node.name}({ast.unparse(arguments)})"
        if node.returns is not None:
            signature += f" -> {ast.unparse(node.returns)}"
        functions.append(
            FunctionInfo(
                name=node.name,
                signature=signature,
                params=tuple(params),
                has_varargs=arguments.vararg is not None,
                has_kwargs=arguments.kwarg is not None,
                line=node.lineno,
            )
        )
    return functions


def function_signatures_text(source: str) -> str:
    return "\n".join(f"- `{info.signature}`" for info in analyze_public_functions(source))
