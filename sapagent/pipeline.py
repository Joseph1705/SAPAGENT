"""One call from raw export to analysis + insights."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass

from . import ai
from .classifier import classify_orders
from .insights import rule_based_insights
from .kpis import Analysis, analyse
from .loader import ExportError, LoadResult, load_export


@dataclass
class RunResult:
    load: LoadResult
    analysis: Analysis
    insights: dict
    ai_error: str | None = None


def filter_work_centers(df, patterns: str | None):
    """Keep orders whose main work centre matches SAP-style patterns: 'HC*', 'HCNE*, HCSE*'."""
    pats = [p.upper() for p in re.split(r"[,;\s]+", patterns or "") if p]
    if not pats:
        return df
    wc = df["work_center"].fillna("").astype(str).str.upper()
    return df[wc.map(lambda v: any(fnmatch.fnmatchcase(v, p) for p in pats))]


def run(source, filename: str | None = None, ai_config: ai.AIConfig | None = None,
        window_days: int = 30, min_occurrences: int = 3, work_centers: str | None = None) -> RunResult:
    loaded = load_export(source, filename)
    data = filter_work_centers(loaded.data, work_centers)
    if data.empty:
        raise ExportError(f"Aucun ordre pour le poste de travail « {work_centers} ».")
    orders = classify_orders(data)
    ai_error = None

    if ai_config:
        try:
            orders = ai.classify_with_ai(orders, ai_config)
        except Exception as exc:  # the report must still come out if the API is unreachable
            ai_error = f"Classification IA indisponible : {exc}"

    analysis = analyse(orders, loaded.missing_recommended, window_days, min_occurrences)
    insights = rule_based_insights(analysis)
    if ai_config and ai_error is None:
        try:
            insights = ai.ai_insights(analysis, ai_config)
        except Exception as exc:
            ai_error = f"Analyse IA indisponible, analyse automatique utilisée : {exc}"
    return RunResult(loaded, analysis, insights, ai_error)
