"""Differential outcome comparison, per-category scoring, and pass criteria."""

from .differ import actual_from_raw, compare_outcome, describe_expected
from .models import ActualOutcome, FailureCase, MatchResult
from .scoring import ScoreSummary, evaluate_pass_criteria, score_results

__all__ = [
    "ActualOutcome",
    "FailureCase",
    "MatchResult",
    "ScoreSummary",
    "actual_from_raw",
    "compare_outcome",
    "describe_expected",
    "evaluate_pass_criteria",
    "score_results",
]
