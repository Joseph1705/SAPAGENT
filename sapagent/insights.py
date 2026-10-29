"""Findings and recommendations built from the KPIs with explicit rules.

This works offline and is the fallback when no Claude API key is configured.
The AI layer (``ai.py``) returns the same structure, so the app and the Excel
report do not care which one produced it.
"""

from __future__ import annotations

from .kpis import Analysis
from .schema import CATEGORIES

PLANNED_TARGET = 0.80  # common benchmark: ~80 % of maintenance work planned


def fmt_h(hours: float) -> str:
    return f"{hours:,.0f} h".replace(",", " ")


def fmt_usd(value: float) -> str:
    return f"{value:,.0f} $".replace(",", " ")


def summary_payload(a: Analysis, top_n: int = 10) -> dict:
    """Compact, number-only view of the analysis. This is all the LLM gets to see."""
    eq_cols = ["equipment_id", "equipment_desc", "failures", "downtime_h", "mttr_h", "mtbf_h", "availability",
               "cost", "main_failure_mode", "open_orders"]
    rep_cols = ["equipment_desc", "failure_mode", "occurrences", "within_window", "mean_interval_days", "downtime_h", "examples"]
    cat = a.categories[["label", "failures", "downtime_h", "cost", "share"]]
    ov = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in a.overview.items()}
    return {
        "period": {"start": a.period_start.date().isoformat(), "end": a.period_end.date().isoformat(),
                   "days": round(a.period_hours / 24)},
        "overview": ov,
        "bad_actors": a.equipment[eq_cols].head(top_n).round(3).to_dict("records"),
        "failure_modes": cat.round(3).to_dict("records"),
        "repeat_failures": a.repeats[rep_cols].head(top_n).to_dict("records"),
        "backlog_age_buckets": a.backlog_buckets.astype({"age_bucket": str}).to_dict("records"),
        "open_and_overdue_by_work_center": a.workcenters.head(top_n).to_dict("records"),
        "data_quality": a.quality,
    }


def rule_based_insights(a: Analysis) -> dict:
    ov, eq, rep, q = a.overview, a.equipment, a.repeats, a.quality
    findings: list[str] = []
    recs: list[dict] = []

    total_dt = ov["downtime_h"] or 1
    top3 = eq.head(3)
    top3_share = top3["downtime_h"].sum() / total_dt
    findings.append(
        f"{len(top3)} équipements concentrent {top3_share:.0%} des heures d'arrêt : "
        + ", ".join(f"{r.equipment_desc} ({fmt_h(r.downtime_h)})" for r in top3.itertuples()) + "."
    )
    if not a.categories.empty:
        c = a.categories.iloc[0]
        findings.append(f"Premier mode de défaillance : {c['label']} ({c['failures']} pannes, {c['share']:.0%} du total).")
    if not rep.empty:
        r = rep.iloc[0]
        findings.append(
            f"Panne récurrente la plus marquée : {r.failure_mode} sur {r.equipment_desc}, "
            f"{r.occurrences} fois (intervalle moyen {r.mean_interval_days:.0f} jours)."
        )
    findings.append(
        f"Travail planifié (préventif + inspection) : {ov['planned_ratio']:.0%} des ordres "
        f"(référence courante : {PLANNED_TARGET:.0%})."
    )
    wc = a.workcenters
    if ov.get("overdue_orders"):
        worst = wc.iloc[0]
        findings.append(
            f"{ov['overdue_orders']} ordres ouverts sur {ov['open_orders']} sont en retard (date de début de base dépassée), "
            f"dont {int(worst.overdue)} au poste de travail {worst.work_center}."
        )
    elif ov["backlog_over_30d"]:
        findings.append(f"{ov['backlog_over_30d']} ordres ouverts depuis plus de 30 jours.")

    for r in top3.itertuples():
        recs.append({
            "priority": "Haute",
            "equipment": r.equipment_desc,
            "action": f"Lancer une analyse des causes racines (RCA) sur le mode « {r.main_failure_mode} ».",
            "rationale": f"{r.failures} pannes, {fmt_h(r.downtime_h)} d'arrêt, MTTR {r.mttr_h:.1f} h, coût {fmt_usd(r.cost)} sur la période.",
        })
    for r in rep.head(4).itertuples():
        if any(x["equipment"] == r.equipment_desc and r.failure_mode in x["action"] for x in recs):
            continue
        interval = max(7, int(r.mean_interval_days * 0.6))
        recs.append({
            "priority": "Haute" if r.occurrences >= 6 else "Moyenne",
            "equipment": r.equipment_desc,
            "action": f"Revoir le plan préventif pour « {r.failure_mode} » : inspection tous les {interval} jours environ, "
                      f"et vérifier la qualité des pièces / du montage.",
            "rationale": f"{r.occurrences} occurrences, dont {r.within_window} à moins de 30 jours d'écart "
                         f"(intervalle moyen {r.mean_interval_days:.0f} j).",
        })
    if ov["planned_ratio"] < PLANNED_TARGET:
        recs.append({
            "priority": "Moyenne",
            "equipment": "Ensemble du site",
            "action": "Augmenter la part de maintenance planifiée, en priorité sur les équipements critiques ci-dessus.",
            "rationale": f"{ov['planned_ratio']:.0%} de travail planifié contre une référence de {PLANNED_TARGET:.0%}.",
        })
    if ov.get("overdue_orders"):
        top_wc = ", ".join(f"{r.work_center} ({int(r.overdue)})" for r in wc[wc["overdue"] > 0].head(3).itertuples())
        recs.append({
            "priority": "Moyenne",
            "equipment": "Planification — postes " + ", ".join(wc[wc["overdue"] > 0].head(3)["work_center"]),
            "action": "Revue hebdomadaire des ordres en retard par poste de travail : réaliser, replanifier ou clôturer (TECO).",
            "rationale": f"{ov['overdue_orders']} ordres en retard, surtout : {top_wc}. "
                         f"{ov['backlog_over_30d']} ordres sont ouverts depuis plus de 30 jours.",
        })
    elif ov["backlog_over_30d"]:
        recs.append({
            "priority": "Moyenne",
            "equipment": "Planification",
            "action": "Passer en revue les ordres ouverts de plus de 30 jours : clôturer (TECO) ou replanifier.",
            "rationale": f"{ov['backlog_over_30d']} ordres en attente depuis plus de 30 jours faussent le carnet et les KPI.",
        })
    nf = max(ov["failures"], 1)
    if q["failures_without_damage_code"] / nf > 0.3:
        recs.append({
            "priority": "Basse",
            "equipment": "Saisie SAP",
            "action": "Rendre le code dommage obligatoire à la clôture des avis de panne.",
            "rationale": f"{q['failures_without_damage_code'] / nf:.0%} des pannes n'ont pas de code dommage : "
                         f"la classification repose sur le texte libre.",
        })

    summary = (
        f"Sur {round(a.period_hours / 24)} jours, {ov['failures']} pannes ont causé {fmt_h(ov['downtime_h'])} d'arrêt "
        f"sur {ov['equipment']} équipements (MTTR moyen {ov['mttr_h'] or 0:.1f} h). "
        f"Les pertes sont concentrées : les 3 premiers équipements représentent {top3_share:.0%} des arrêts. "
        + (f"{len(rep)} pannes récurrentes ont été détectées, en priorité {rep.iloc[0].failure_mode.lower()} sur "
           f"{rep.iloc[0].equipment_desc}." if not rep.empty else "Aucune panne récurrente marquée.")
    )
    return {
        "source": "rules",
        "executive_summary": summary,
        "key_findings": findings,
        "recommendations": recs,
    }


def category_label(key: str | None) -> str:
    return CATEGORIES.get(key or "", "—")
