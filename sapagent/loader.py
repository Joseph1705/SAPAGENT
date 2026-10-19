"""Read a SAP PM export (CSV or Excel), map its columns and clean the values."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .schema import (
    ALIAS_INDEX,
    CLOSED_STATUSES,
    COLUMNS,
    FAILURE_KINDS,
    ORDER_TYPES,
    RECOMMENDED,
    REQUIRED,
    normalise,
)


class ExportError(ValueError):
    """The file cannot be analysed (wrong format or missing key columns)."""


@dataclass
class LoadResult:
    data: pd.DataFrame
    mapping: dict[str, str]  # canonical -> original column header
    unmapped: list[str]
    missing_recommended: list[str]
    warnings: list[str] = field(default_factory=list)


def read_table(source: str | Path | bytes | io.IOBase, filename: str | None = None) -> pd.DataFrame:
    """Read CSV/XLSX from a path, raw bytes or a file-like object (e.g. a Streamlit upload)."""
    name = (filename or getattr(source, "name", None) or str(source if isinstance(source, (str, Path)) else "")).lower()
    if isinstance(source, bytes):
        source = io.BytesIO(source)

    if name.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(source, dtype=str)
    # SAP CSV exports use ';' in French locales and ',' elsewhere; sniff it.
    return pd.read_csv(source, sep=None, engine="python", dtype=str, encoding_errors="replace")


def map_columns(columns: list[str]) -> tuple[dict[str, str], list[str]]:
    mapping: dict[str, str] = {}
    unmapped: list[str] = []
    for col in columns:
        canonical = ALIAS_INDEX.get(normalise(col))
        if canonical and canonical not in mapping:
            mapping[canonical] = col
        else:
            unmapped.append(col)
    return mapping, unmapped


def _parse_dates(series: pd.Series) -> pd.Series:
    # SAP writes dd.mm.yyyy (and sometimes a time); ISO strings also parse with dayfirst.
    return pd.to_datetime(series.str.strip(), errors="coerce", dayfirst=True, format="mixed")


def _parse_numbers(series: pd.Series) -> pd.Series:
    # Handle '1.234,56' (European) as well as '1,234.56' and plain numbers.
    s = series.astype(str).str.strip().str.replace(r"[^\d,.\-]", "", regex=True)
    euro = s.str.contains(r",\d{1,2}$", regex=True)
    s = s.where(~euro, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    s = s.str.replace(",", "", regex=False)
    return pd.to_numeric(s, errors="coerce")


def load_export(source, filename: str | None = None) -> LoadResult:
    raw = read_table(source, filename)
    raw = raw.dropna(how="all")
    if raw.empty:
        raise ExportError("Le fichier est vide.")

    mapping, unmapped = map_columns(list(raw.columns))
    missing = [c for c in REQUIRED if c not in mapping]
    if missing:
        labels = ", ".join(COLUMNS[c][0] for c in missing)
        raise ExportError(
            f"Colonnes obligatoires introuvables : {labels}. "
            f"Colonnes lues dans le fichier : {', '.join(map(str, raw.columns))}."
        )

    df = pd.DataFrame({canonical: raw[original] for canonical, original in mapping.items()})
    for col in COLUMNS:
        if col not in df:
            df[col] = pd.NA

    text_cols = ["order_id", "order_type", "notification_id", "equipment_id", "equipment_desc",
                 "functional_location", "description", "status", "work_center", "damage_code",
                 "cause_code", "breakdown", "priority"]
    for col in text_cols:
        df[col] = df[col].astype("string").str.strip().replace("", pd.NA)

    for col in ["created_date", "malfunction_start", "malfunction_end"]:
        df[col] = _parse_dates(df[col].astype("string"))
    for col in ["actual_cost", "actual_hours"]:
        df[col] = _parse_numbers(df[col])

    df["equipment_desc"] = df["equipment_desc"].fillna(df["equipment_id"])
    df["order_kind"] = df["order_type"].str.upper().map(ORDER_TYPES).fillna("unknown")
    if df["order_kind"].eq("unknown").all():
        # No usable order type: treat every order as a corrective intervention.
        df["order_kind"] = "corrective"

    df["is_failure"] = df["order_kind"].isin(FAILURE_KINDS)
    df["is_open"] = ~df["status"].fillna("").str.upper().str.contains("|".join(CLOSED_STATUSES))

    duration = (df["malfunction_end"] - df["malfunction_start"]).dt.total_seconds() / 3600
    has_breakdown_flag = df["breakdown"].notna().any()
    stopped = df["breakdown"].fillna("").str.upper().isin(["X", "1", "OUI", "YES", "TRUE"]) if has_breakdown_flag else df["is_failure"]
    df["downtime_h"] = duration.where(stopped & (duration >= 0)).fillna(0.0).round(2)
    df["duration_invalid"] = duration < 0

    warnings = []
    if not has_breakdown_flag and "malfunction_start" in mapping:
        warnings.append("Pas de colonne « Arrêt machine » : toutes les pannes avec dates sont comptées comme arrêts.")
    if "order_type" not in mapping:
        warnings.append("Pas de colonne « Type d'ordre » : tous les ordres sont traités comme correctifs.")

    return LoadResult(
        data=df.reset_index(drop=True),
        mapping=mapping,
        unmapped=unmapped,
        missing_recommended=[c for c in RECOMMENDED if c not in mapping],
        warnings=warnings,
    )
