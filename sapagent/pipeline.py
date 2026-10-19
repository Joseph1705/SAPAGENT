"""One call from raw export to analysis + insights."""

from __future__ import annotations

from dataclasses import dataclass

from . import ai
from .classifier import classify_orders
from .insights import rule_based_insights
from .kpis import Analysis, analyse
from .loader import LoadResult, load_export


@dataclass
class RunResult:
    load: LoadResult
    analysis: Analysis
    insights: dict
    ai_error: str | None = None


def run(source, filename: str | None = None, use_ai: bool = False, api_key: str | None = None,
        window_days: int = 30, min_occurrences: int = 3) -> RunResult:
    loaded = load_export(source, filename)
    orders = classify_orders(loaded.data)
    ai_error = None

    if use_ai:
        try:
            orders = ai.classify_with_claude(orders, api_key)
        except Exception as exc:  # the report must still come out if the API is unreachable
            ai_error = f"Classification IA indisponible : {exc}"

    analysis = analyse(orders, loaded.missing_recommended, window_days, min_occurrences)
    insights = rule_based_insights(analysis)
    if use_ai and ai_error is None:
        try:
            insights = ai.ai_insights(analysis, api_key)
        except Exception as exc:
            ai_error = f"Analyse IA indisponible, analyse automatique utilisée : {exc}"
    return RunResult(loaded, analysis, insights, ai_error)
