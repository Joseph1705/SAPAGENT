"""SAP PM Analyst — web interface.  Run:  streamlit run app.py"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from sapagent import ai
from sapagent.insights import fmt_h, fmt_usd
from sapagent.pipeline import run
from sapagent.report import build_report
from sapagent.sample_data import generate
from sapagent.schema import CATEGORIES, COLUMNS, ORDER_TYPE_LABELS

BLUE, ORANGE, GREY = "#2A78D6", "#EB6834", "#9CA3AF"
SAMPLE = Path(__file__).parent / "data" / "exemple_export_sap_pm.xlsx"

st.set_page_config(page_title="SAP PM Analyst", page_icon="🛠️", layout="wide")
st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1400px;}
      [data-testid="stMetricValue"] {font-size: 1.7rem;}
      .hero h1 {font-size: 2.4rem; margin-bottom: .2rem;}
      .hero p {font-size: 1.1rem; opacity: .8;}
      .step {border-radius: 12px; padding: 1.1rem 1.2rem; height: 100%;
             background: rgba(42,120,214,.07); border: 1px solid rgba(42,120,214,.25);}
      .step b {font-size: 1.05rem;}
      .muted {opacity: .7; font-size: .9rem;}
      [data-testid="stHeaderActionElements"] {display: none;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------- data
@st.cache_data(show_spinner=False)
def analyse_cached(data: bytes, filename: str, use_ai: bool, key_hash: str, window: int, min_occ: int,
                   _api_key: str | None):
    return run(data, filename, use_ai=use_ai, api_key=_api_key, window_days=window, min_occurrences=min_occ)


@st.cache_data(show_spinner=False)
def report_cached(data: bytes, filename: str, use_ai: bool, key_hash: str, window: int, min_occ: int,
                  _result) -> bytes:
    return build_report(_result.analysis, _result.insights, filename)


@st.cache_data
def sample_bytes() -> bytes:
    if SAMPLE.exists():
        return SAMPLE.read_bytes()
    import io
    buf = io.BytesIO()
    generate().to_excel(buf, index=False, sheet_name="Export IW39")
    return buf.getvalue()


def compact_usd(v: float) -> str:
    if v >= 1e6:
        return f"{v / 1e6:.2f} M$".replace(".", ",")
    if v >= 1e4:
        return f"{v / 1e3:.0f} k$"
    return fmt_usd(v)


def bar(df, x, y, color=BLUE, height=380, orientation="h", **kw):
    fig = px.bar(df, x=x, y=y, orientation=orientation, height=height, **kw)
    fig.update_traces(marker_color=color, marker_line_width=0)
    fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), yaxis_title=None, xaxis_title=None, bargap=0.35)
    if orientation == "h":
        fig.update_yaxes(autorange="reversed")
    return fig


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("## 🛠️ SAP PM Analyst")
    st.caption("Analyse des exports de maintenance SAP PM en quelques secondes.")

    st.markdown("#### 1 · Données")
    upload = st.file_uploader("Export SAP PM (Excel ou CSV)", type=["xlsx", "xls", "csv"],
                              help="Export d'ordres IW38/IW39 ou d'avis IW28/IW29, avec ou sans mise en page personnalisée.")
    if st.button("Utiliser les données de démonstration", width="stretch", type="secondary"):
        st.session_state["demo"] = True
    if upload is not None:
        st.session_state["demo"] = False

    st.markdown("#### 2 · Intelligence artificielle")
    api_key = st.text_input("Clé API Anthropic (optionnel)", type="password",
                            help="Sans clé, l'outil fonctionne avec son analyse automatique par règles.") or None
    can_ai = ai.has_credentials(api_key)
    use_ai = st.toggle("Analyse rédigée par Claude", value=False, disabled=not can_ai,
                       help="Classe les descriptions ambiguës et rédige résumé + recommandations. "
                            "Les chiffres restent calculés par le code, jamais par l'IA.")
    if not can_ai:
        st.caption("Ajoutez une clé pour activer l'IA.")

    with st.expander("Paramètres d'analyse"):
        window = st.slider("Fenêtre de récidive (jours)", 7, 90, 30)
        min_occ = st.slider("Occurrences minimum pour une panne récurrente", 2, 10, 3)

    with st.expander("Comment exporter depuis SAP ?"):
        st.markdown(
            "1. Transaction **IW39** (ordres) ou **IW29** (avis)\n"
            "2. Sélectionnez la période et le site\n"
            "3. Ajoutez si possible les colonnes : équipement, type d'ordre, description, "
            "début / fin de panne, arrêt machine, statut, coûts réels, code dommage\n"
            "4. Menu **Liste → Exporter → Tableur** (ou icône Excel)\n\n"
            "Les noms de colonnes français, anglais ou techniques (AUFNR, EQUNR…) sont reconnus."
        )

# ---------------------------------------------------------------- source
if upload is not None:
    data, filename = upload.getvalue(), upload.name
elif st.session_state.get("demo"):
    data, filename = sample_bytes(), SAMPLE.name
else:
    data = None

if data is None:
    st.markdown(
        '<div class="hero"><h1>Des heures d\'interprétation SAP PM, en quelques secondes.</h1>'
        "<p>Déposez un export SAP PM : l'outil calcule les indicateurs de fiabilité, repère les équipements "
        "et les pannes qui coûtent le plus, et propose des actions priorisées. Le tout dans un rapport Excel prêt à partager.</p></div>",
        unsafe_allow_html=True,
    )
    st.write("")
    c1, c2, c3 = st.columns(3)
    for col, title, text in [
        (c1, "1 · Déposer l'export", "Fichier Excel ou CSV d'IW39 / IW29. Les colonnes sont reconnues automatiquement."),
        (c2, "2 · Lire l'analyse", "MTBF, MTTR, disponibilité, Pareto des pannes, pannes récurrentes, backlog, qualité des données."),
        (c3, "3 · Partager le rapport", "Un classeur Excel professionnel, avec des formules traçables jusqu'à chaque ordre."),
    ]:
        col.markdown(f'<div class="step"><b>{title}</b><br><span class="muted">{text}</span></div>', unsafe_allow_html=True)
    st.write("")
    if st.button("▶  Essayer avec les données de démonstration", type="primary"):
        st.session_state["demo"] = True
        st.rerun()
    st.caption("Les données de démonstration sont entièrement fictives (usine de traitement de minerai, 12 mois, 23 équipements).")
    st.stop()

key_hash = hashlib.sha256((api_key or "").encode()).hexdigest()[:12]
with st.spinner("Analyse en cours…" + (" (Claude rédige l'analyse, ~1 min)" if use_ai else "")):
    try:
        result = analyse_cached(data, filename, use_ai, key_hash, window, min_occ, api_key)
    except ValueError as exc:
        st.error(f"Impossible d'analyser ce fichier. {exc}")
        st.stop()

a, ins, load = result.analysis, result.insights, result.load
ov, orders = a.overview, a.orders

# ---------------------------------------------------------------- header
h1, h2 = st.columns([3, 1])
with h1:
    st.markdown("## Analyse maintenance")
    st.caption(f"**{filename}** · Période du {a.period_start:%d/%m/%Y} au {a.period_end - pd.Timedelta(days=1):%d/%m/%Y} · "
               f"{ov['orders']} ordres · {ov['equipment']} équipements")
with h2:
    st.write("")
    st.download_button("⬇  Télécharger le rapport Excel",
                       report_cached(data, filename, use_ai, key_hash, window, min_occ, result),
                       file_name=f"rapport_{Path(filename).stem}.xlsx", type="primary", width="stretch",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

if result.ai_error:
    st.warning(result.ai_error)
for w in load.warnings:
    st.info(w)

m = st.columns(6)
m[0].metric("Pannes", f"{ov['failures']}", border=True)
m[1].metric("Heures d'arrêt", fmt_h(ov["downtime_h"]), border=True)
m[2].metric("MTTR moyen", f"{ov['mttr_h'] or 0:.1f} h", border=True, help="Temps moyen de réparation par arrêt")
m[3].metric("Disponibilité", f"{(ov['availability'] or 0):.1%}", border=True, help="Moyenne sur tous les équipements")
m[4].metric("Travail planifié", f"{ov['planned_ratio']:.0%}", border=True,
            delta=f"{ov['planned_ratio'] - 0.8:+.0%} vs 80 %", delta_color="normal")
m[5].metric("Coût total", compact_usd(ov["cost"]), border=True, help=fmt_usd(ov["cost"]))

tabs = st.tabs(["Synthèse", "Équipements", "Modes de défaillance", "Pannes récurrentes", "Tendances",
                "Backlog", "Qualité des données", "Explorer les ordres"])

# ---------------------------------------------------------------- Synthèse
with tabs[0]:
    left, right = st.columns([1.15, 1])
    with left:
        badge = ":violet-badge[Analyse IA · Claude]" if ins.get("source") == "claude" else ":gray-badge[Analyse automatique · règles]"
        st.markdown(f"#### Résumé  {badge}")
        st.write(ins["executive_summary"])
        st.markdown("#### Constats clés")
        for k in ins["key_findings"]:
            st.markdown(f"- {k}")
    with right:
        st.markdown("#### Où se perdent les heures d'arrêt")
        top = a.equipment.head(8)
        st.plotly_chart(bar(top, "downtime_h", "equipment_desc", height=330,
                            labels={"downtime_h": "Heures d'arrêt", "equipment_desc": ""},
                            hover_data={"failures": True, "mttr_h": ":.1f"}),
                        width="stretch")

    st.markdown("#### Recommandations priorisées")
    colors = {"Haute": "red", "Moyenne": "orange", "Basse": "green"}
    cols = st.columns(2)
    for i, rec in enumerate(ins["recommendations"]):
        with cols[i % 2].container(border=True):
            st.markdown(f":{colors.get(rec['priority'], 'gray')}-badge[Priorité {rec['priority'].lower()}]  **{rec['equipment']}**")
            st.markdown(rec["action"])
            st.caption(f"📊 {rec['rationale']}")
    st.caption("Aide à la décision : chaque recommandation doit être validée par l'ingénieur maintenance.")

# ---------------------------------------------------------------- Équipements
with tabs[1]:
    eq = a.equipment
    c1, c2 = st.columns(2)
    c1.plotly_chart(bar(eq.head(10), "downtime_h", "equipment_desc", title="Top 10 — heures d'arrêt",
                        labels={"downtime_h": "h", "equipment_desc": ""}), width="stretch")
    c2.plotly_chart(bar(eq.sort_values("cost", ascending=False).head(10), "cost", "equipment_desc", color=ORANGE,
                        title="Top 10 — coût de maintenance (USD)", labels={"cost": "USD", "equipment_desc": ""}),
                    width="stretch")
    st.dataframe(
        eq[["equipment_id", "equipment_desc", "failures", "downtime_h", "mttr_h", "mtbf_h", "availability",
            "cost", "open_orders", "main_failure_mode", "criticality"]],
        hide_index=True, width="stretch", height=480,
        column_config={
            "equipment_id": "Équipement", "equipment_desc": st.column_config.TextColumn("Désignation", width="large"),
            "failures": "Pannes",
            "downtime_h": st.column_config.ProgressColumn("Arrêt (h)", format="%.0f", min_value=0, max_value=float(eq["downtime_h"].max() or 1)),
            "mttr_h": st.column_config.NumberColumn("MTTR (h)", format="%.1f"),
            "mtbf_h": st.column_config.NumberColumn("MTBF (h)", format="%.0f"),
            "availability": st.column_config.NumberColumn("Disponibilité", format="percent"),
            "cost": st.column_config.NumberColumn("Coût (USD)", format="dollar"),
            "open_orders": "Ouverts", "main_failure_mode": "Mode principal",
            "criticality": st.column_config.ProgressColumn("Criticité", format="%d", min_value=0, max_value=100),
        },
    )

# ---------------------------------------------------------------- Modes de défaillance
with tabs[2]:
    cat = a.categories
    c1, c2 = st.columns([1.2, 1])
    c1.plotly_chart(bar(cat, "failures", "label", title="Pannes par mode de défaillance", height=440,
                        labels={"failures": "Pannes", "label": ""}, text="failures"), width="stretch")
    with c2:
        st.dataframe(cat[["label", "failures", "share", "cumulative_share", "downtime_h", "cost"]], hide_index=True,
                     width="stretch", height=440,
                     column_config={"label": "Mode", "failures": "Pannes",
                                    "share": st.column_config.NumberColumn("Part", format="percent"),
                                    "cumulative_share": st.column_config.NumberColumn("Cumul", format="percent"),
                                    "downtime_h": st.column_config.NumberColumn("Arrêt (h)", format="%.0f"),
                                    "cost": st.column_config.NumberColumn("Coût", format="dollar")})
    src = orders[orders["is_failure"]]["category_source"].value_counts()
    st.caption("Origine de la classification : " + " · ".join(f"{k} : {v}" for k, v in src.items())
               + ("" if use_ai else "  —  activez Claude pour classer les descriptions restantes."))
    with st.expander("Voir comment chaque description a été classée"):
        f = orders[orders["is_failure"]][["order_id", "equipment_desc", "description", "category", "category_source"]].copy()
        f["category"] = f["category"].map(CATEGORIES)
        st.dataframe(f, hide_index=True, width="stretch",
                     column_config={"order_id": "Ordre", "equipment_desc": "Équipement", "description": "Texte saisi",
                                    "category": "Mode attribué", "category_source": "Source"})

# ---------------------------------------------------------------- Pannes récurrentes
with tabs[3]:
    rep = a.repeats
    if rep.empty:
        st.success("Aucune panne récurrente détectée avec ces paramètres.")
    else:
        st.markdown(f"**{len(rep)} pannes récurrentes** : même équipement, même mode, au moins {min_occ} fois, "
                    f"avec plusieurs récidives à moins de {window} jours.")
        st.dataframe(rep[["equipment_desc", "failure_mode", "occurrences", "within_window", "mean_interval_days",
                          "downtime_h", "cost", "last_date", "examples"]], hide_index=True, width="stretch",
                     column_config={"equipment_desc": "Équipement", "failure_mode": "Mode", "occurrences": "Occurrences",
                                    "within_window": f"Récidives < {window} j",
                                    "mean_interval_days": st.column_config.NumberColumn("Intervalle moyen (j)", format="%.0f"),
                                    "downtime_h": st.column_config.NumberColumn("Arrêt (h)", format="%.0f"),
                                    "cost": st.column_config.NumberColumn("Coût", format="dollar"),
                                    "last_date": st.column_config.DateColumn("Dernière", format="DD/MM/YYYY"),
                                    "examples": st.column_config.TextColumn("Exemples de textes", width="large")})
        choice = st.selectbox("Chronologie d'un cas", rep.index,
                              format_func=lambda i: f"{rep.at[i, 'equipment_desc']} — {rep.at[i, 'failure_mode']}")
        r = rep.loc[choice]
        hist = orders[(orders["equipment_id"] == r["equipment_id"]) & (orders["category"] == r["category"])]
        fig = px.scatter(hist, x="created_date", y="downtime_h", hover_data=["order_id", "description"], height=280,
                         labels={"created_date": "", "downtime_h": "Arrêt (h)"})
        fig.update_traces(marker=dict(size=13, color=ORANGE, line=dict(width=2, color="white")))
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------- Tendances
with tabs[4]:
    mo = a.monthly
    c1, c2 = st.columns(2)
    c1.plotly_chart(bar(mo, "month", "failures", orientation="v", height=340, title="Pannes par mois",
                        labels={"month": "", "failures": "Pannes"}), width="stretch")
    c2.plotly_chart(bar(mo, "month", "downtime_h", orientation="v", color=ORANGE, height=340, title="Heures d'arrêt par mois",
                        labels={"month": "", "downtime_h": "h"}), width="stretch")
    fig = px.line(mo, x="month", y="planned_ratio", markers=True, height=300, title="Part de travail planifié",
                  labels={"month": "", "planned_ratio": ""})
    fig.update_traces(line=dict(color=BLUE, width=2), marker=dict(size=8))
    fig.add_hline(y=0.8, line_dash="dot", line_color=GREY, annotation_text="Référence 80 %", annotation_position="bottom right")
    fig.update_layout(yaxis_tickformat=".0%", margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------- Backlog
with tabs[5]:
    c1, c2 = st.columns([1, 2])
    with c1:
        st.metric("Ordres ouverts", ov["open_orders"], border=True)
        st.metric("Ouverts depuis plus de 30 jours", ov["backlog_over_30d"], border=True)
        st.plotly_chart(bar(a.backlog_buckets, "age_bucket", "orders", orientation="v", height=260,
                            labels={"age_bucket": "", "orders": "Ordres"}), width="stretch")
    with c2:
        st.dataframe(a.backlog, hide_index=True, width="stretch", height=520,
                     column_config={"order_id": "Ordre", "order_type": "Type", "equipment_id": "Équipement",
                                    "equipment_desc": "Désignation", "description": "Description", "priority": "Prio",
                                    "status": "Statut", "created_date": st.column_config.DateColumn("Créé le", format="DD/MM/YYYY"),
                                    "age_days": "Âge (j)", "age_bucket": None})

# ---------------------------------------------------------------- Qualité
with tabs[6]:
    q = a.quality
    c1, c2 = st.columns([1, 2])
    with c1:
        label = "bonne" if q["score"] >= 80 else "moyenne" if q["score"] >= 60 else "faible"
        st.metric("Score de qualité des données", f"{q['score']} / 100", border=True)
        st.progress(q["score"] / 100, text=f"Qualité {label}")
        st.caption("Des données incomplètes donnent des analyses fausses mais convaincantes : vérifiez ces points avant de conclure.")
    with c2:
        nf = max(ov["failures"], 1)
        checks = pd.DataFrame([
            ("Ordres en double (retirés)", q["duplicate_orders"]),
            ("Ordres sans date de création", q["missing_dates"]),
            ("Pannes sans code dommage SAP", q["failures_without_damage_code"]),
            ("Pannes sans date de fin", q["failures_without_end_date"]),
            ("Durées négatives (ignorées)", q["negative_durations"]),
            ("Pannes au texte trop vague pour être classées", q["unclassified_failures"]),
        ], columns=["Contrôle", "Nombre"])
        st.dataframe(checks, hide_index=True, width="stretch")
    st.markdown("#### Colonnes reconnues dans le fichier")
    mapping = pd.DataFrame(
        [(COLUMNS[c][0], load.mapping.get(c, "—"), "✅" if c in load.mapping else "⚪") for c in COLUMNS],
        columns=["Champ attendu", "Colonne du fichier", ""])
    st.dataframe(mapping, hide_index=True, width="stretch")
    if load.unmapped:
        st.caption("Colonnes ignorées : " + ", ".join(map(str, load.unmapped)))

# ---------------------------------------------------------------- Explorer
with tabs[7]:
    c1, c2, c3 = st.columns([2, 1, 1])
    query = c1.text_input("Rechercher (équipement, description, n° d'ordre)", placeholder="ex. garniture, P-201, 4000123")
    kinds = c2.multiselect("Nature", sorted(orders["order_kind"].unique()), format_func=ORDER_TYPE_LABELS.get)
    only_open = c3.toggle("Ouverts uniquement")
    view = orders
    if query:
        hay = (view["order_id"].astype(str) + " " + view["equipment_id"].astype(str) + " "
               + view["equipment_desc"].astype(str) + " " + view["description"].fillna("").astype(str)).str.lower()
        view = view[hay.str.contains(query.lower(), regex=False)]
    if kinds:
        view = view[view["order_kind"].isin(kinds)]
    if only_open:
        view = view[view["is_open"]]
    view = view.assign(nature=view["order_kind"].map(ORDER_TYPE_LABELS), mode=view["category"].map(CATEGORIES))
    st.caption(f"{len(view)} ordres")
    st.dataframe(view[["order_id", "order_type", "nature", "equipment_desc", "description", "mode", "created_date",
                       "downtime_h", "actual_cost", "status"]],
                 hide_index=True, width="stretch", height=560,
                 column_config={"order_id": "Ordre", "order_type": "Type", "nature": "Nature", "equipment_desc": "Équipement",
                                "description": "Description", "mode": "Mode de défaillance",
                                "created_date": st.column_config.DateColumn("Créé le", format="DD/MM/YYYY"),
                                "downtime_h": st.column_config.NumberColumn("Arrêt (h)", format="%.1f"),
                                "actual_cost": st.column_config.NumberColumn("Coût", format="dollar"), "status": "Statut"})
