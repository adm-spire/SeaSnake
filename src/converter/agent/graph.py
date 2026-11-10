"""LangGraph StateGraph construction.

This is a cyclic graph with two loops:

* test regeneration: validate_tests -> generate_tests -> validate_tests
* repair: compile/verify -> repair -> compile

and one branch on ``test_mode`` at the entry point.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps

from langgraph.graph import END, START, StateGraph

from .nodes import (
    capture_baseline_node,
    compile_node,
    generate_tests_node,
    ingest_tests_node,
    repair_node,
    report_node,
    translate_node,
    validate_tests_node,
    verify_node,
)
from .routing import (
    route_after_compile,
    route_after_validate,
    route_after_verify,
    route_test_mode,
)
from .services import Services
from .state import ConverterState

NodeFn = Callable[[ConverterState, Services], dict]


def build_graph(services: Services):
    graph = StateGraph(ConverterState)

    def traced(name: str, node: NodeFn):
        @wraps(node)
        def wrapper(state: ConverterState) -> dict:
            metadata = {
                "run_id": state.run_id,
                "attempt": state.attempt,
                "generation_round": state.generation_round,
            }
            with services.tracer.span(
                name,
                input={"run_id": state.run_id},
                metadata=metadata,
            ) as span:
                result = node(state, services)
                services.tracer.set_outputs(
                    span,
                    {
                        "updated_keys": sorted(result.keys()),
                        "status": result.get("status", state.status),
                    },
                )
                return result

        return wrapper

    graph.add_node("ingest_tests", traced("ingest_tests", ingest_tests_node))
    graph.add_node("generate_tests", traced("generate_tests", generate_tests_node))
    graph.add_node("validate_tests", traced("validate_tests", validate_tests_node))
    graph.add_node("capture_baseline", traced("capture_baseline", capture_baseline_node))
    graph.add_node("translate", traced("translate", translate_node))
    graph.add_node("compile", traced("compile", compile_node))
    graph.add_node("verify", traced("verify", verify_node))
    graph.add_node("repair", traced("repair", repair_node))
    graph.add_node("report", traced("report", report_node))

    graph.add_conditional_edges(
        START,
        route_test_mode,
        {
            "ingest_tests": "ingest_tests",
            "generate_tests": "generate_tests",
        },
    )

    graph.add_edge("ingest_tests", "validate_tests")
    graph.add_edge("generate_tests", "validate_tests")

    graph.add_conditional_edges(
        "validate_tests",
        route_after_validate,
        {
            "generate_tests": "generate_tests",
            "capture_baseline": "capture_baseline",
        },
    )

    graph.add_edge("capture_baseline", "translate")
    graph.add_edge("translate", "compile")

    graph.add_conditional_edges(
        "compile",
        route_after_compile,
        {
            "verify": "verify",
            "repair": "repair",
            "report": "report",
        },
    )
    graph.add_conditional_edges(
        "verify",
        route_after_verify,
        {
            "repair": "repair",
            "report": "report",
        },
    )
    graph.add_edge("repair", "compile")
    graph.add_edge("report", END)

    return graph.compile()
