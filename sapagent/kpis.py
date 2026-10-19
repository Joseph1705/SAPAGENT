"""Deterministic maintenance KPIs. Every number shown to users comes from here, never from the LLM."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .schema import CATEGORIES, PLANNED_KINDS


@dataclass
class Analysis:
    orders: pd.DataFrame
    period_start: pd.Timestamp
    period_end: pd.Timestamp
    period_hours: float
    overview: dict
    equipment: pd.DataFrame
    categories: pd.DataFrame
    repeats: pd.DataFrame
    monthly: pd.DataFrame
    backlog: pd.DataFrame
    backlog_buckets: pd.DataFrame
    quality: dict


def _period(df: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    dates = pd.concat([df["created_date"], df["malfunction_start"], df["malfunction_end"]]).dropna()
    start, end = dates.min().normalize(), dates.max().normalize() + pd.Timedelta(days=1)
    return start, end


def equipment_kpis(df: pd.DataFrame, period_hours: float) -> pd.DataFrame:
    failures = df[df["is_failure"]]
    g = df.groupby("equipment_id", dropna=False)
    gf = failures.groupby("equipment_id", dropna=False)

    eq = pd.DataFrame({
        "equipment_desc": g["equipment_desc"].first(),
        "functional_location": g["functional_location"].first(),
        "orders": g.size(),
        "failures": gf.size(),
        "downtime_h": gf["downtime_h"].sum(),
        "cost": g["actual_cost"].sum(min_count=1),
        "open_orders": g["is_open"].sum(),
    }).fillna({"failures": 0, "downtime_h": 0.0, "cost": 0.0})
    eq["failures"] = eq["failures"].astype(int)

    stops = failures[failures["downtime_h"] > 0].groupby("equipment_id").size()
    eq["mttr_h"] = (eq["downtime_h"] / stops.reindex(eq.index)).replace([np.inf], np.nan)
    eq["mtbf_h"] = np.where(eq["failures"] > 0, (period_hours - eq["downtime_h"]) / eq["failures"].clip(lower=1), np.nan)
    eq["availability"] = (period_hours - eq["downtime_h"]).clip(lower=0) / period_hours

    top_mode = (
        failures.groupby(["equipment_id", "category"]).size().reset_index(name="n")
        .sort_values(["equipment_id", "n"], ascending=[True, False])
        .drop_duplicates("equipment_id").set_index("equipment_id")
    )
    eq["main_failure_mode"] = top_mode["category"].map(CATEGORIES).reindex(eq.index)

    # Criticality score: average share of downtime, failures and cost, scaled so the worst machine = 100.
    def share(col):
        total = eq[col].sum()
        return eq[col] / total if total else 0
    score = (share("downtime_h") + share("failures") + share("cost")) / 3
    eq["criticality"] = (score / score.max() * 100).round(0) if score.max() else 0

    eq = eq.sort_values(["downtime_h", "failures", "cost"], ascending=False)
    eq.index.name = "equipment_id"
    return eq.reset_index()


def category_kpis(df: pd.DataFrame) -> pd.DataFrame:
    failures = df[df["is_failure"]]
    cat = failures.groupby("category").agg(
        failures=("order_id", "size"),
        downtime_h=("downtime_h", "sum"),
        cost=("actual_cost", "sum"),
        equipment=("equipment_id", "nunique"),
    ).sort_values("failures", ascending=False)
    cat["label"] = cat.index.map(CATEGORIES)
    total = cat["failures"].sum()
    cat["share"] = cat["failures"] / total if total else 0
    cat["cumulative_share"] = cat["share"].cumsum()
    return cat.reset_index()


def repeat_failures(df: pd.DataFrame, window_days: int = 30, min_occurrences: int = 3, min_quick: int = 2) -> pd.DataFrame:
    """Same equipment + same failure mode, at least ``min_occurrences`` times, recurring within ``window_days`` at least ``min_quick`` times."""
    failures = df[df["is_failure"] & (df["category"] != "other")].sort_values("created_date")
    rows = []
    for (eq_id, cat), grp in failures.groupby(["equipment_id", "category"]):
        if len(grp) < min_occurrences:
            continue
        gaps = grp["created_date"].diff().dt.days.dropna()
        quick = int((gaps <= window_days).sum())
        if quick < min_quick:
            continue
        rows.append({
            "equipment_id": eq_id,
            "equipment_desc": grp["equipment_desc"].iloc[0],
            "category": cat,
            "failure_mode": CATEGORIES[cat],
            "occurrences": len(grp),
            "within_window": quick,
            "mean_interval_days": round(float(gaps.mean()), 1),
            "downtime_h": round(float(grp["downtime_h"].sum()), 1),
            "cost": float(grp["actual_cost"].sum()),
            "last_date": grp["created_date"].max(),
            "examples": " | ".join(grp["description"].dropna().astype(str).unique()[:3]),
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["equipment_id", "equipment_desc", "category", "failure_mode", "occurrences",
                                     "within_window", "mean_interval_days", "downtime_h", "cost", "last_date", "examples"])
    return out.sort_values(["occurrences", "downtime_h"], ascending=False).reset_index(drop=True)


def monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    d = df.dropna(subset=["created_date"]).copy()
    d["month"] = d["created_date"].dt.to_period("M").dt.to_timestamp()
    m = d.groupby("month").agg(
        orders=("order_id", "size"),
        failures=("is_failure", "sum"),
        planned=("order_kind", lambda s: s.isin(PLANNED_KINDS).sum()),
        downtime_h=("downtime_h", "sum"),
        cost=("actual_cost", "sum"),
    )
    m["planned_ratio"] = m["planned"] / m["orders"]
    return m.reset_index()


def backlog_view(df: pd.DataFrame, ref_date: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    open_ = df[df["is_open"]].copy()
    open_["age_days"] = (ref_date - open_["created_date"]).dt.days
    bins = [-1, 7, 30, 90, 10_000]
    labels = ["0–7 j", "8–30 j", "31–90 j", "> 90 j"]
    open_["age_bucket"] = pd.cut(open_["age_days"], bins=bins, labels=labels)
    buckets = open_.groupby("age_bucket", observed=False).size().reindex(labels, fill_value=0).reset_index(name="orders")
    cols = ["order_id", "order_type", "equipment_id", "equipment_desc", "description", "priority", "status",
            "created_date", "age_days", "age_bucket"]
    return open_.sort_values("age_days", ascending=False)[cols].reset_index(drop=True), buckets


def data_quality(df: pd.DataFrame, missing_recommended: list[str]) -> dict:
    failures = df[df["is_failure"]]
    n, nf = len(df), max(len(failures), 1)
    checks = {
        "orders": n,
        "duplicate_orders": int(df["order_id"].duplicated().sum()),
        "missing_dates": int(df["created_date"].isna().sum()),
        "failures_without_damage_code": int(failures["damage_code"].isna().sum()),
        "failures_without_end_date": int((failures["malfunction_start"].notna() & failures["malfunction_end"].isna()).sum()),
        "negative_durations": int(df["duration_invalid"].fillna(False).sum()),
        "unclassified_failures": int((failures["category"] == "other").sum()),
        "missing_recommended": missing_recommended,
    }
    penalty = (
        30 * checks["failures_without_damage_code"] / nf
        + 20 * checks["unclassified_failures"] / nf
        + 20 * checks["failures_without_end_date"] / nf
        + 10 * min(1, (checks["duplicate_orders"] + checks["negative_durations"] + checks["missing_dates"]) / max(n, 1) * 20)
        + 4 * len(missing_recommended)
    )
    checks["score"] = int(max(0, round(100 - penalty)))
    return checks


def analyse(df: pd.DataFrame, missing_recommended: list[str] | None = None,
            window_days: int = 30, min_occurrences: int = 3) -> Analysis:
    quality = data_quality(df, missing_recommended or [])
    df = df.drop_duplicates("order_id", keep="first")
    start, end = _period(df)
    period_hours = (end - start).total_seconds() / 3600

    equipment = equipment_kpis(df, period_hours)
    categories = category_kpis(df)
    repeats = repeat_failures(df, window_days, min_occurrences)
    monthly = monthly_trend(df)
    backlog, buckets = backlog_view(df, end)

    failures = df[df["is_failure"]]
    stops = failures[failures["downtime_h"] > 0]
    total_downtime = float(failures["downtime_h"].sum())
    n_eq = df["equipment_id"].nunique()
    overview = {
        "orders": len(df),
        "equipment": n_eq,
        "failures": len(failures),
        "downtime_h": total_downtime,
        "cost": float(df["actual_cost"].sum()),
        "mttr_h": total_downtime / len(stops) if len(stops) else None,
        "mtbf_h": (period_hours * n_eq - total_downtime) / len(failures) if len(failures) else None,
        "availability": 1 - total_downtime / (period_hours * n_eq) if n_eq else None,
        "planned_ratio": float(df["order_kind"].isin(PLANNED_KINDS).mean()),
        "emergency_ratio": float((df["order_kind"] == "emergency").mean()),
        "open_orders": int(df["is_open"].sum()),
        "backlog_over_30d": int((backlog["age_days"] > 30).sum()),
        "repeat_patterns": len(repeats),
    }
    return Analysis(
        orders=df,
        period_start=start,
        period_end=end,
        period_hours=period_hours,
        overview=overview,
        equipment=equipment,
        categories=categories,
        repeats=repeats,
        monthly=monthly,
        backlog=backlog,
        backlog_buckets=buckets,
        quality=quality,
    )
