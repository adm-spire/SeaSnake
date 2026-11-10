"""Differential outcome comparison, per-category scoring, and pass criteria."""

from .differ import compare_outcome, describe_expected
from .models import FailureCase, MatchResult, RustActual
from .scoring import ScoreSummary, evaluate_pass_criteria, score_results

__all__ = [
    "FailureCase",
    "MatchResult",
    "RustActual",
    "ScoreSummary",
    "compare_outcome",
    "describe_expected",
    "evaluate_pass_criteria",
    "score_results",
]
