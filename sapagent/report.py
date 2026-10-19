"""Professional Excel report. KPI cells are live formulas over the 'Données' sheet, so every number is traceable."""

from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import xlsxwriter
from xlsxwriter.utility import xl_col_to_name

from .kpis import Analysis
from .schema import CATEGORIES, ORDER_TYPE_LABELS, PLANNED_KINDS

NAVY = "#1F3A5F"
BLUE = "#2A78D6"
LIGHT = "#EEF3F9"
GREY = "#6B7280"
FONT = "Arial"

DATA_COLUMNS = [
    # (header, source column or callable, width, kind)
    ("Ordre", "order_id", 11, "text"),
    ("Type d'ordre", "order_type", 8, "text"),
    ("Nature", lambda d: d["order_kind"].map(ORDER_TYPE_LABELS), 11, "text"),
    ("Panne (1/0)", lambda d: d["is_failure"].astype(int), 8, "int"),
    ("Équipement", "equipment_id", 12, "text"),
    ("Désignation", "equipment_desc", 30, "text"),
    ("Poste technique", "functional_location", 14, "text"),
    ("Description", "description", 38, "text"),
    ("Mode de défaillance", lambda d: d["category"].map(CATEGORIES).fillna(""), 22, "text"),
    ("Source classification", "category_source", 16, "text"),
    ("Date de création", "created_date", 12, "date"),
    ("Début panne", "malfunction_start", 15, "datetime"),
    ("Fin panne", "malfunction_end", 15, "datetime"),
    ("Arrêt (h)", "downtime_h", 9, "num"),
    ("Coût (USD)", "actual_cost", 12, "money"),
    ("Statut", "status", 11, "text"),
    ("Ouvert (1/0)", lambda d: d["is_open"].astype(int), 8, "int"),
    ("Priorité", "priority", 8, "text"),
    ("Code dommage", "damage_code", 10, "text"),
]
COL = {h: xl_col_to_name(i) for i, (h, *_rest) in enumerate(DATA_COLUMNS)}


def _clean(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    return v


def build_report(a: Analysis, insights: dict, source_name: str = "export SAP PM") -> bytes:
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "nan_inf_to_errors": True})
    wb.set_properties({"title": "Analyse maintenance SAP PM", "author": "SAP PM Analyst"})

    base = {"font_name": FONT, "font_size": 10, "valign": "vcenter"}

    def F(**kw):
        return wb.add_format({**base, **kw})

    f = {
        "title": F(font_size=20, bold=True, font_color=NAVY),
        "subtitle": F(font_size=10, font_color=GREY),
        "h2": F(font_size=13, bold=True, font_color=NAVY, bottom=2, bottom_color=BLUE),
        "header": F(bold=True, font_color="white", bg_color=NAVY, text_wrap=True, border=1, border_color="#D0D7E2"),
        "cell": F(border=1, border_color="#E3E8EF"),
        "wrap": F(border=1, border_color="#E3E8EF", text_wrap=True, valign="top"),
        "int": F(border=1, border_color="#E3E8EF", num_format="#,##0"),
        "num": F(border=1, border_color="#E3E8EF", num_format="#,##0.0"),
        "money": F(border=1, border_color="#E3E8EF", num_format='#,##0" $"'),
        "pct": F(border=1, border_color="#E3E8EF", num_format="0.0%"),
        "date": F(border=1, border_color="#E3E8EF", num_format="dd/mm/yyyy"),
        "datetime": F(border=1, border_color="#E3E8EF", num_format="dd/mm/yyyy hh:mm"),
        "text": F(border=1, border_color="#E3E8EF"),
        "kpi_label": F(font_size=9, font_color=GREY, bg_color=LIGHT, text_wrap=True, valign="top", left=4, left_color=BLUE, align="left", indent=1),
        "kpi_int": F(font_size=18, bold=True, font_color=NAVY, bg_color=LIGHT, num_format="#,##0", left=4, left_color=BLUE, align="left", indent=1),
        "kpi_num": F(font_size=18, bold=True, font_color=NAVY, bg_color=LIGHT, num_format='#,##0.0" h"', left=4, left_color=BLUE, align="left", indent=1),
        "kpi_hours": F(font_size=18, bold=True, font_color=NAVY, bg_color=LIGHT, num_format='#,##0" h"', left=4, left_color=BLUE, align="left", indent=1),
        "kpi_money": F(font_size=18, bold=True, font_color=NAVY, bg_color=LIGHT, num_format='#,##0" $"', left=4, left_color=BLUE, align="left", indent=1),
        "kpi_pct": F(font_size=18, bold=True, font_color=NAVY, bg_color=LIGHT, num_format="0.0%", left=4, left_color=BLUE, align="left", indent=1),
        "body": F(text_wrap=True, valign="top"),
        "bullet": F(text_wrap=True, valign="top"),
        "note": F(font_size=9, italic=True, font_color=GREY, text_wrap=True, valign="top"),
        "hint": F(font_size=9, italic=True, font_color=GREY),
        "param": F(bold=True, bg_color="#FFF4CC", border=1, num_format="#,##0"),
        "prio_Haute": F(bold=True, font_color="#9B1C1C", bg_color="#FDE2E1", border=1, border_color="#E3E8EF", align="center"),
        "prio_Moyenne": F(bold=True, font_color="#8A5300", bg_color="#FEF0C7", border=1, border_color="#E3E8EF", align="center"),
        "prio_Basse": F(bold=True, font_color="#1E5631", bg_color="#DCF2E3", border=1, border_color="#E3E8EF", align="center"),
    }

    df = a.orders
    n = len(df)
    last = n + 1  # last data row (1-based, header in row 1)

    def rng(header: str) -> str:
        return f"'Données'!${COL[header]}$2:${COL[header]}${last}"

    # ------------------------------------------------------------------ sheets (order = tab order)
    ws_sum = wb.add_worksheet("Synthèse")
    ws_eq = wb.add_worksheet("Équipements")
    ws_cat = wb.add_worksheet("Modes de défaillance")
    ws_rep = wb.add_worksheet("Pannes récurrentes")
    ws_tr = wb.add_worksheet("Tendance")
    ws_bl = wb.add_worksheet("Backlog")
    ws_q = wb.add_worksheet("Qualité données")
    ws_d = wb.add_worksheet("Données")
    ws_m = wb.add_worksheet("Méthode")
    for ws in wb.worksheets():
        ws.hide_gridlines(2)
        ws.set_zoom(90)
        ws.set_paper(9)  # A4
        ws.set_landscape()
        ws.fit_to_pages(1, 0)
        ws.set_margins(left=0.4, right=0.4, top=0.5, bottom=0.5)
        ws.set_footer("&L&8SAP PM Analyst&R&8Page &P / &N")

    # ------------------------------------------------------------------ Données
    ws_d.hide_gridlines(0)
    for c, (header, src, width, kind) in enumerate(DATA_COLUMNS):
        ws_d.write(0, c, header, f["header"])
        ws_d.set_column(c, c, width)
        values = src(df) if callable(src) else df[src]
        for r, v in enumerate(values, start=1):
            v = _clean(v)
            if v is None:
                ws_d.write_blank(r, c, None, f["cell"])
            elif kind in ("date", "datetime"):
                ws_d.write_datetime(r, c, pd.Timestamp(v).to_pydatetime(), f[kind])
            elif kind in ("int", "num", "money"):
                ws_d.write_number(r, c, float(v), f[kind])
            else:
                ws_d.write_string(r, c, str(v), f["text"])
    ws_d.freeze_panes(1, 1)
    ws_d.autofilter(0, 0, n, len(DATA_COLUMNS) - 1)
    ws_d.set_row(0, 30)

    # ------------------------------------------------------------------ Équipements (live formulas)
    eq = a.equipment
    ws_eq.write(0, 0, "Indicateurs par équipement", f["title"])
    ws_eq.write(1, 0, "Durée de la période analysée (h) :", f["subtitle"])
    ws_eq.write_number(1, 3, round(a.period_hours, 1), f["param"])
    ws_eq.write(1, 4, "← modifiable : MTBF et disponibilité se recalculent", f["hint"])
    period_ref = "'Équipements'!$D$2"
    headers = ["Équipement", "Désignation", "Poste technique", "Pannes", "Arrêt (h)", "MTTR (h)", "MTBF (h)",
               "Disponibilité", "Coût (USD)", "Ordres ouverts", "Mode principal", "Criticité (0-100)"]
    widths = [12, 32, 14, 9, 10, 10, 11, 12, 13, 10, 24, 11]
    hr = 3
    for c, (h, w) in enumerate(zip(headers, widths)):
        ws_eq.write(hr, c, h, f["header"])
        ws_eq.set_column(c, c, w)
    ws_eq.set_row(hr, 30)
    for i, row in enumerate(eq.itertuples(), start=hr + 1):
        x = i + 1  # excel row number
        ws_eq.write_string(i, 0, str(row.equipment_id), f["text"])
        ws_eq.write_string(i, 1, str(row.equipment_desc), f["text"])
        ws_eq.write_string(i, 2, str(_clean(row.functional_location) or ""), f["text"])
        ws_eq.write_formula(i, 3, f'=COUNTIFS({rng("Équipement")},$A{x},{rng("Panne (1/0)")},1)', f["int"], int(row.failures))
        ws_eq.write_formula(i, 4, f'=SUMIFS({rng("Arrêt (h)")},{rng("Équipement")},$A{x},{rng("Panne (1/0)")},1)', f["num"], float(row.downtime_h))
        ws_eq.write_formula(
            i, 5, f'=IFERROR(E{x}/COUNTIFS({rng("Équipement")},$A{x},{rng("Panne (1/0)")},1,{rng("Arrêt (h)")},">0"),"")',
            f["num"], "" if pd.isna(row.mttr_h) else float(row.mttr_h))
        ws_eq.write_formula(i, 6, f'=IF(D{x}>0,({period_ref}-E{x})/D{x},"")', f["num"],
                            "" if pd.isna(row.mtbf_h) else float(row.mtbf_h))
        ws_eq.write_formula(i, 7, f'=MAX(0,{period_ref}-E{x})/{period_ref}', f["pct"], float(row.availability))
        ws_eq.write_formula(i, 8, f'=SUMIFS({rng("Coût (USD)")},{rng("Équipement")},$A{x})', f["money"], float(row.cost))
        ws_eq.write_formula(i, 9, f'=COUNTIFS({rng("Équipement")},$A{x},{rng("Ouvert (1/0)")},1)', f["int"], int(row.open_orders))
        ws_eq.write_string(i, 10, str(_clean(row.main_failure_mode) or "—"), f["text"])
        ws_eq.write_number(i, 11, float(row.criticality), f["int"])
    eq_first, eq_last = hr + 1, hr + len(eq)
    ws_eq.conditional_format(eq_first, 4, eq_last, 4, {"type": "data_bar", "bar_color": BLUE, "bar_solid": True})
    ws_eq.conditional_format(eq_first, 8, eq_last, 8, {"type": "data_bar", "bar_color": "#9DB8DE", "bar_solid": True})
    ws_eq.conditional_format(eq_first, 7, eq_last, 7, {"type": "3_color_scale", "min_color": "#F8696B",
                                                       "mid_color": "#FFEB84", "max_color": "#63BE7B"})
    ws_eq.conditional_format(eq_first, 11, eq_last, 11, {"type": "3_color_scale", "min_color": "#FFFFFF",
                                                         "mid_color": "#FCD9B6", "max_color": "#F4A259"})
    ws_eq.freeze_panes(hr + 1, 2)
    ws_eq.autofilter(hr, 0, eq_last, len(headers) - 1)

    # ------------------------------------------------------------------ Modes de défaillance
    cat = a.categories
    ws_cat.write(0, 0, "Modes de défaillance (Pareto des pannes)", f["title"])
    ws_cat.write(1, 0, "Classement issu des codes dommage SAP, des règles mots-clés et, si activée, de l'IA.", f["subtitle"])
    ch = ["Mode de défaillance", "Pannes", "Part", "Part cumulée", "Arrêt (h)", "Coût (USD)", "Équipements touchés"]
    for c, (h, w) in enumerate(zip(ch, [26, 9, 9, 11, 10, 13, 12])):
        ws_cat.write(3, c, h, f["header"])
        ws_cat.set_column(c, c, w)
    c_first, c_last = 5, 4 + len(cat)  # excel rows
    for i, row in enumerate(cat.itertuples(), start=4):
        x = i + 1
        ws_cat.write_string(i, 0, row.label, f["text"])
        ws_cat.write_formula(i, 1, f'=COUNTIFS({rng("Mode de défaillance")},$A{x},{rng("Panne (1/0)")},1)', f["int"], int(row.failures))
        ws_cat.write_formula(i, 2, f"=IFERROR(B{x}/SUM($B${c_first}:$B${c_last}),0)", f["pct"], float(row.share))
        ws_cat.write_formula(i, 3, f"=SUM($C${c_first}:C{x})", f["pct"], float(row.cumulative_share))
        ws_cat.write_formula(i, 4, f'=SUMIFS({rng("Arrêt (h)")},{rng("Mode de défaillance")},$A{x},{rng("Panne (1/0)")},1)', f["num"], float(row.downtime_h))
        ws_cat.write_formula(i, 5, f'=SUMIFS({rng("Coût (USD)")},{rng("Mode de défaillance")},$A{x},{rng("Panne (1/0)")},1)', f["money"], float(row.cost))
        ws_cat.write_number(i, 6, int(row.equipment), f["int"])
    if len(cat):
        chart = wb.add_chart({"type": "bar"})
        chart.add_series({
            "name": "Pannes",
            "categories": ["Modes de défaillance", 4, 0, 3 + len(cat), 0],
            "values": ["Modes de défaillance", 4, 1, 3 + len(cat), 1],
            "fill": {"color": BLUE}, "gap": 60,
            "data_labels": {"value": True, "font": {"name": FONT, "size": 8, "color": GREY}},
        })
        chart.set_title({"name": "Nombre de pannes par mode", "name_font": {"name": FONT, "size": 12, "color": NAVY}})
        chart.set_y_axis({"reverse": True, "num_font": {"name": FONT, "size": 9}})
        chart.set_x_axis({"major_gridlines": {"visible": True, "line": {"color": "#E5E7EB"}}, "num_font": {"name": FONT, "size": 8}})
        chart.set_legend({"none": True})
        chart.set_size({"width": 620, "height": 30 * len(cat) + 90})
        ws_cat.insert_chart(3, 8, chart)

    # ------------------------------------------------------------------ Pannes récurrentes
    rep = a.repeats
    ws_rep.write(0, 0, "Pannes récurrentes", f["title"])
    ws_rep.write(1, 0, "Même équipement, même mode de défaillance, au moins 3 fois, avec plusieurs récidives à moins de 30 jours.", f["subtitle"])
    rh = ["Équipement", "Désignation", "Mode de défaillance", "Occurrences", "Récidives < 30 j", "Intervalle moyen (j)",
          "Arrêt (h)", "Coût (USD)", "Dernière panne", "Exemples de descriptions"]
    rk = ["text", "text", "text", "int", "int", "num", "num", "money", "date", "wrap"]
    rcols = ["equipment_id", "equipment_desc", "failure_mode", "occurrences", "within_window", "mean_interval_days",
             "downtime_h", "cost", "last_date", "examples"]
    for c, (h, w) in enumerate(zip(rh, [12, 30, 22, 11, 11, 12, 10, 12, 12, 60])):
        ws_rep.write(3, c, h, f["header"])
        ws_rep.set_column(c, c, w)
    ws_rep.set_row(3, 30)
    _write_rows(ws_rep, rep, rcols, rk, f, start_row=4)
    if rep.empty:
        ws_rep.write(4, 0, "Aucune panne récurrente détectée.", f["note"])

    # ------------------------------------------------------------------ Tendance
    m = a.monthly
    ws_tr.write(0, 0, "Tendance mensuelle", f["title"])
    th = ["Mois", "Ordres", "Pannes", "Ordres planifiés", "Part planifiée", "Arrêt (h)", "Coût (USD)"]
    for c, (h, w) in enumerate(zip(th, [12, 9, 9, 11, 11, 10, 13])):
        ws_tr.write(2, c, h, f["header"])
        ws_tr.set_column(c, c, w)
    ws_tr.set_row(2, 30)
    month_fmt = F(border=1, border_color="#E3E8EF", num_format="mmm yyyy")
    for i, row in enumerate(m.itertuples(), start=3):
        ws_tr.write_datetime(i, 0, row.month.to_pydatetime(), month_fmt)
        ws_tr.write_number(i, 1, row.orders, f["int"])
        ws_tr.write_number(i, 2, row.failures, f["int"])
        ws_tr.write_number(i, 3, row.planned, f["int"])
        ws_tr.write_formula(i, 4, f"=IFERROR(D{i + 1}/B{i + 1},0)", f["pct"], float(row.planned_ratio))
        ws_tr.write_number(i, 5, row.downtime_h, f["num"])
        ws_tr.write_number(i, 6, row.cost, f["money"])
    if len(m):
        last_m = 2 + len(m)
        for col, title, color, pos in [(2, "Pannes par mois", BLUE, (2, 8)), (5, "Heures d'arrêt par mois", "#EB6834", (20, 8))]:
            chart = wb.add_chart({"type": "column"})
            chart.add_series({"name": title, "categories": ["Tendance", 3, 0, last_m, 0],
                              "values": ["Tendance", 3, col, last_m, col], "fill": {"color": color}, "gap": 80})
            chart.set_title({"name": title, "name_font": {"name": FONT, "size": 12, "color": NAVY}})
            chart.set_legend({"none": True})
            chart.set_x_axis({"num_format": "mmm yy", "num_font": {"name": FONT, "size": 8}})
            chart.set_y_axis({"major_gridlines": {"visible": True, "line": {"color": "#E5E7EB"}}, "num_font": {"name": FONT, "size": 8}})
            chart.set_size({"width": 620, "height": 300})
            ws_tr.insert_chart(*pos, chart)

    # ------------------------------------------------------------------ Backlog
    bl = a.backlog
    ws_bl.write(0, 0, "Ordres ouverts (backlog)", f["title"])
    ws_bl.write(1, 0, f"Âge calculé au {a.period_end.date():%d/%m/%Y} (fin de la période).", f["subtitle"])
    ws_bl.write(3, 0, "Ancienneté", f["header"])
    ws_bl.write(3, 1, "Ordres", f["header"])
    for i, row in enumerate(a.backlog_buckets.itertuples(), start=4):
        ws_bl.write_string(i, 0, str(row.age_bucket), f["text"])
        ws_bl.write_number(i, 1, row.orders, f["int"])
    start = 6 + len(a.backlog_buckets)
    bh = ["Ordre", "Type", "Équipement", "Désignation", "Description", "Priorité", "Statut", "Créé le", "Âge (j)"]
    bcols = ["order_id", "order_type", "equipment_id", "equipment_desc", "description", "priority", "status", "created_date", "age_days"]
    bk = ["text", "text", "text", "text", "text", "text", "text", "date", "int"]
    for c, (h, w) in enumerate(zip(bh, [12, 8, 12, 30, 38, 8, 10, 12, 8])):
        ws_bl.write(start, c, h, f["header"])
        ws_bl.set_column(c, c, w)
    _write_rows(ws_bl, bl, bcols, bk, f, start_row=start + 1)
    if len(bl):
        ws_bl.conditional_format(start + 1, 8, start + len(bl), 8, {"type": "cell", "criteria": ">", "value": 30,
                                                                    "format": F(font_color="#9B1C1C", bold=True)})
        ws_bl.autofilter(start, 0, start + len(bl), len(bh) - 1)

    # ------------------------------------------------------------------ Qualité données
    q = a.quality
    ws_q.write(0, 0, "Qualité des données", f["title"])
    ws_q.write(1, 0, "Des données incomplètes produisent des analyses fausses mais convaincantes : à lire avant les conclusions.", f["subtitle"])
    ws_q.set_column(0, 0, 52)
    ws_q.set_column(1, 1, 14)
    ws_q.write(3, 0, "Score de qualité (0-100)", f["kpi_label"])
    ws_q.write_number(3, 1, q["score"], f["kpi_int"])
    checks = [
        ("Ordres lus", q["orders"]),
        ("Ordres en double (retirés de l'analyse)", q["duplicate_orders"]),
        ("Ordres sans date de création", q["missing_dates"]),
        ("Pannes sans code dommage SAP", q["failures_without_damage_code"]),
        ("Pannes sans date de fin de panne", q["failures_without_end_date"]),
        ("Durées négatives (fin avant début, ignorées)", q["negative_durations"]),
        ("Pannes non classées (texte trop vague)", q["unclassified_failures"]),
    ]
    ws_q.write(5, 0, "Contrôle", f["header"])
    ws_q.write(5, 1, "Nombre", f["header"])
    for i, (label, value) in enumerate(checks, start=6):
        ws_q.write(i, 0, label, f["text"])
        ws_q.write_number(i, 1, value, f["int"])
    if q["missing_recommended"]:
        from .schema import COLUMNS
        ws_q.write(7 + len(checks), 0, "Colonnes recommandées absentes : "
                   + ", ".join(COLUMNS[c][0] for c in q["missing_recommended"]), f["note"])

    # ------------------------------------------------------------------ Méthode
    ws_m.write(0, 0, "Méthode et définitions", f["title"])
    ws_m.set_column(0, 0, 26)
    ws_m.set_column(1, 1, 100)
    defs = [
        ("Panne", "Ordre de type correctif ou urgence (par défaut PM01 / PM04, paramétrable)."),
        ("Arrêt (h)", "Fin panne − début panne, pour les ordres marqués « Arrêt machine ». Les durées négatives sont ignorées."),
        ("MTTR", "Mean Time To Repair : heures d'arrêt / nombre de pannes ayant causé un arrêt."),
        ("MTBF", "Mean Time Between Failures : (durée de la période − heures d'arrêt) / nombre de pannes."),
        ("Disponibilité", "(Durée de la période − heures d'arrêt) / durée de la période."),
        ("Part planifiée", "Ordres préventifs + inspections / total des ordres. Référence courante : ~80 %."),
        ("Criticité", "Moyenne des parts de l'équipement dans le total des arrêts, des pannes et des coûts ; 100 = équipement le plus pénalisant."),
        ("Panne récurrente", "Même équipement et même mode de défaillance, au moins 3 occurrences, dont au moins 2 récidives à moins de 30 jours."),
        ("Classification", "1) code dommage SAP s'il est reconnu ; 2) règles mots-clés FR/EN sur le texte libre ; 3) IA (Claude) pour les textes restants, si activée."),
        ("Rôle de l'IA", "L'IA ne calcule aucun indicateur. Elle classe les textes et rédige l'analyse à partir des chiffres calculés ici. "
                         "Les recommandations doivent être validées par un ingénieur."),
        ("Source", f"{source_name} — période du {a.period_start:%d/%m/%Y} au {a.period_end - pd.Timedelta(days=1):%d/%m/%Y}."),
    ]
    for i, (k, v) in enumerate(defs, start=2):
        ws_m.write(i, 0, k, F(bold=True, valign="top", font_color=NAVY))
        ws_m.write(i, 1, v, f["body"])
        ws_m.set_row(i, 30)

    # ------------------------------------------------------------------ Synthèse (written last: references the others)
    ws = ws_sum
    ws.set_column(0, 0, 2)
    ws.set_column(1, 8, 17)
    ws.write(0, 1, "Analyse maintenance SAP PM", f["title"])
    ws.write(1, 1, f"Période du {a.period_start:%d/%m/%Y} au {a.period_end - pd.Timedelta(days=1):%d/%m/%Y}  ·  "
                   f"{source_name}  ·  généré le {datetime.now():%d/%m/%Y %H:%M}", f["subtitle"])
    ws.set_row(0, 30)

    ov = a.overview
    eq_rng = lambda col: f"'Équipements'!${col}${eq_first + 1}:${col}${eq_last + 1}"
    planned_formula = "+".join(f'COUNTIFS({rng("Nature")},"{ORDER_TYPE_LABELS[k]}")' for k in sorted(PLANNED_KINDS))
    tiles = [
        ("Ordres analysés", f'=COUNTA({rng("Ordre")})', "kpi_int", ov["orders"]),
        ("Pannes", f'=SUM({eq_rng("D")})', "kpi_int", ov["failures"]),
        ("Heures d'arrêt", f'=SUM({eq_rng("E")})', "kpi_hours", ov["downtime_h"]),
        ("Coût total (USD)", f'=SUM({rng("Coût (USD)")})', "kpi_money", ov["cost"]),
        ("MTTR moyen", f'=IFERROR(SUM({eq_rng("E")})/COUNTIFS({rng("Panne (1/0)")},1,{rng("Arrêt (h)")},">0"),0)', "kpi_num", ov["mttr_h"] or 0),
        ("Disponibilité moyenne", f'=1-SUM({eq_rng("E")})/({period_ref}*COUNTA({eq_rng("A")}))', "kpi_pct", ov["availability"] or 0),
        ("Part de travail planifié", f'=({planned_formula})/COUNTA({rng("Ordre")})', "kpi_pct", ov["planned_ratio"]),
        ("Ordres ouverts", f'=SUM({rng("Ouvert (1/0)")})', "kpi_int", ov["open_orders"]),
    ]
    for i, (label, formula, fmt, value) in enumerate(tiles):
        r, c = 3 + (i // 4) * 3, 1 + (i % 4) * 2
        ws.merge_range(r, c, r, c + 1, label, f["kpi_label"])
        ws.merge_range(r + 1, c, r + 1, c + 1, "", f[fmt])
        ws.write_formula(r + 1, c, formula, f[fmt], value)
        ws.set_row(r + 1, 30)

    row = 10
    src = "Analyse rédigée par l'IA (Claude) à partir des indicateurs calculés" if insights.get("source") == "claude" \
        else "Analyse automatique (règles) — activez l'IA pour une analyse rédigée"
    ws.merge_range(row, 1, row, 8, "Résumé", f["h2"])
    ws.merge_range(row + 1, 1, row + 1, 8, src, f["note"])
    ws.merge_range(row + 2, 1, row + 2, 8, insights["executive_summary"], f["body"])
    ws.set_row(row + 2, max(45, 15 * (len(insights["executive_summary"]) // 120 + 1)))
    row += 4
    ws.merge_range(row, 1, row, 8, "Constats clés", f["h2"])
    for k in insights["key_findings"]:
        row += 1
        ws.merge_range(row, 1, row, 8, f"•  {k}", f["bullet"])
        ws.set_row(row, max(18, 15 * (len(k) // 125 + 1)))
    row += 2
    ws.merge_range(row, 1, row, 8, "Recommandations priorisées", f["h2"])
    row += 1
    ws.write(row, 1, "Priorité", f["header"])
    ws.merge_range(row, 2, row, 3, "Équipement / périmètre", f["header"])
    ws.merge_range(row, 4, row, 6, "Action recommandée", f["header"])
    ws.merge_range(row, 7, row, 8, "Justification (données)", f["header"])
    for rec in insights["recommendations"]:
        row += 1
        ws.write(row, 1, rec["priority"], f.get(f"prio_{rec['priority']}", f["cell"]))
        ws.merge_range(row, 2, row, 3, rec["equipment"], f["wrap"])
        ws.merge_range(row, 4, row, 6, rec["action"], f["wrap"])
        ws.merge_range(row, 7, row, 8, rec["rationale"], f["wrap"])
        ws.set_row(row, max(30, 14 * (max(len(rec["action"]) // 55, len(rec["rationale"]) // 36) + 1)))
    row += 2
    ws.merge_range(row, 1, row, 8, "Les recommandations sont des aides à la décision : elles doivent être validées par "
                   "l'ingénieur maintenance avant toute action. Détails et définitions dans l'onglet « Méthode ».", f["note"])
    ws.set_row(row, 28)
    ws.activate()

    wb.close()
    return buf.getvalue()


def _write_rows(ws, frame: pd.DataFrame, cols: list[str], kinds: list[str], f: dict, start_row: int) -> None:
    for i, rec in enumerate(frame[cols].itertuples(index=False), start=start_row):
        for c, (v, kind) in enumerate(zip(rec, kinds)):
            v = _clean(v)
            if v is None:
                ws.write_blank(i, c, None, f["cell"])
            elif kind == "date":
                ws.write_datetime(i, c, pd.Timestamp(v).to_pydatetime(), f["date"])
            elif kind in ("int", "num", "money"):
                ws.write_number(i, c, float(v), f[kind])
            else:
                ws.write_string(i, c, str(v), f[kind] if kind in f else f["text"])
