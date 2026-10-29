"""SAP PM Analyst — web interface.  Run:  streamlit run app.py"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from sapagent import __version__, ai
from sapagent.insights import fmt_h, fmt_usd
from sapagent.kpis import daily_brief, latest_day
from sapagent.pipeline import run
from sapagent.report import build_daily_brief, build_report
from sapagent.sample_data import generate
from sapagent.sap_reference import EXPORT_TRANSACTIONS, IW39_STEPS, USEFUL_COLUMNS
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
# Cache keys: the leading arguments. Underscored arguments (API key, result objects) are not hashed.
@st.cache_data(show_spinner=False)
def analyse_cached(data: bytes, filename: str, ai_sig: str, window: int, min_occ: int, work_centers: str,
                   _cfg: ai.AIConfig | None):
    return run(data, filename, ai_config=_cfg, window_days=window, min_occurrences=min_occ, work_centers=work_centers)


@st.cache_data(show_spinner=False)
def report_cached(data: bytes, filename: str, ai_sig: str, window: int, min_occ: int, work_centers: str,
                  _result) -> bytes:
    return build_report(_result.analysis, _result.insights, filename)


@st.cache_data(ttl=3600, show_spinner=False)
def openrouter_models() -> list[str]:
    try:
        return [m["id"] for m in ai.list_openrouter_models()]
    except Exception:
        return []


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
    st.caption(f"Analyse des exports de maintenance SAP PM en quelques secondes · v{__version__}")

    st.markdown("#### 1 · Données")
    upload = st.file_uploader("Export SAP PM (Excel ou CSV)", type=["xlsx", "xls", "csv"],
                              help="Export d'ordres IW38/IW39 ou d'avis IW28/IW29, avec ou sans mise en page personnalisée.")
    if st.button("Utiliser les données de démonstration", width="stretch", type="secondary"):
        st.session_state["demo"] = True
    if upload is not None:
        st.session_state["demo"] = False

    st.markdown("#### 2 · Intelligence artificielle (optionnel)")
    provider = st.radio("Fournisseur", list(ai.PROVIDERS), format_func=ai.PROVIDERS.get, horizontal=True,
                        help="Anthropic : Claude en direct. OpenRouter : une seule clé pour Claude, GPT, Gemini, Mistral, Llama…")
    cfg = ai.AIConfig(provider=provider)
    cfg.api_key = st.text_input(f"Clé API {ai.PROVIDERS[provider].split()[0]}", type="password",
                                help="Sans clé, l'outil fonctionne avec son analyse automatique par règles.") or None
    if provider == "openrouter":
        ids = openrouter_models()
        if ids:
            default = ai.pick_default_model(ids)
            cfg.model = st.selectbox("Modèle", ids, index=ids.index(default) if default in ids else 0,
                                     help="Modèles OpenRouter compatibles avec les sorties JSON structurées, du plus récent au plus ancien.")
        else:
            cfg.model = st.text_input("Modèle OpenRouter", placeholder="fournisseur/modèle, ex. anthropic/claude-sonnet-4.5",
                                      help="Liste des modèles indisponible : saisissez l'identifiant OpenRouter (openrouter.ai/models).") or None
    can_ai = ai.has_credentials(cfg) and (provider == "anthropic" or bool(cfg.model))
    use_ai = st.toggle("Analyse rédigée par l'IA", value=False, disabled=not can_ai,
                       help="Classe les descriptions ambiguës et rédige résumé + recommandations. "
                            "Les chiffres restent calculés par le code, jamais par l'IA.")
    if not can_ai:
        st.caption("Ajoutez une clé" + (" et un modèle" if provider == "openrouter" else "") + " pour activer l'IA.")

    with st.expander("Paramètres d'analyse"):
        window = st.slider("Fenêtre de récidive (jours)", 7, 90, 30)
        min_occ = st.slider("Occurrences minimum pour une panne récurrente", 2, 10, 3)
        work_centers = st.text_input("Postes de travail principaux", placeholder="ex. MECA*, ELEC-01",
                                     help="Comme dans IW39 : le joker * sélectionne tous les postes qui commencent "
                                          "par ce code. Plusieurs codes séparés par des virgules. Vide = tous.").strip()

    with st.expander("Comment exporter depuis SAP ?"):
        st.markdown("**Export IW39 pas à pas**\n\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(IW39_STEPS, 1)))
        st.caption(f"Colonnes utiles : {USEFUL_COLUMNS}")
        st.markdown("**Transactions utiles**")
        st.dataframe(pd.DataFrame([(c, d, "✅" if ok else "bientôt") for c, d, _, ok in EXPORT_TRANSACTIONS],
                                  columns=["Code", "Transaction", "Lu par l'outil"]), hide_index=True)

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
        (c1, "1 · Déposer l'export", "Fichier Excel ou CSV d'IW39, IW29 ou ZGMT_IW29. Les colonnes sont reconnues automatiquement."),
        (c2, "2 · Lire l'analyse", "MTBF, MTTR, Pareto des pannes, pannes récurrentes, ordres en retard par poste de travail, réunion J-1."),
        (c3, "3 · Partager le rapport", "Un classeur Excel professionnel, avec des formules traçables jusqu'à chaque ordre."),
    ]:
        col.markdown(f'<div class="step"><b>{title}</b><br><span class="muted">{text}</span></div>', unsafe_allow_html=True)
    st.write("")
    if st.button("▶  Essayer avec les données de démonstration", type="primary"):
        st.session_state["demo"] = True
        st.rerun()
    st.caption("Les données de démonstration sont entièrement fictives (usine de traitement de minerai, 12 mois, 23 équipements).")
    st.stop()

key_hash = hashlib.sha256((cfg.api_key or "").encode()).hexdigest()[:12]
ai_sig = f"{cfg.provider}|{cfg.model}|{key_hash}" if use_ai else ""
with st.spinner("Analyse en cours…" + (f" ({cfg.label} rédige l'analyse, ~1 min)" if use_ai else "")):
    try:
        result = analyse_cached(data, filename, ai_sig, window, min_occ, work_centers, cfg if use_ai else None)
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
               f"{ov['orders']} ordres · {ov['equipment']} équipements"
               + (f" · postes de travail : {work_centers}" if work_centers else ""))
with h2:
    st.write("")
    st.download_button("⬇  Télécharger le rapport Excel",
                       report_cached(data, filename, ai_sig, window, min_occ, work_centers, result),
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

(t_sum, t_j1, t_eq, t_cat, t_rep, t_trend, t_bl, t_q, t_x) = st.tabs(
    ["Synthèse", "Réunion J-1", "Équipements", "Modes de défaillance", "Pannes récurrentes", "Tendances",
     "Backlog & retards", "Qualité des données", "Explorer les ordres"])

# ---------------------------------------------------------------- Synthèse
with t_sum:
    left, right = st.columns([1.15, 1])
    with left:
        badge = (f":violet-badge[Analyse IA · {ins.get('model', 'IA')}]" if ins.get("source") == "ai"
                 else ":gray-badge[Analyse automatique · règles]")
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

# ---------------------------------------------------------------- Réunion J-1
with t_j1:
    last = latest_day(orders)
    c1, c2 = st.columns([1, 2])
    day = c1.date_input("Journée à passer en revue", value=last.date(), min_value=a.period_start.date(),
                        max_value=last.date(), format="DD/MM/YYYY",
                        help="Par défaut, le dernier jour de l'export : la veille de la réunion opérationnelle (cf. ZGMT_IW29).")
    brief = daily_brief(a, pd.Timestamp(day))
    with c2:
        st.write("")
        st.download_button("⬇  Fiche réunion J-1 (Excel)", build_daily_brief(brief, filename),
                           file_name=f"reunion_J-1_{pd.Timestamp(day):%Y-%m-%d}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    k = st.columns(6)
    k[0].metric("Interventions", brief["n_interventions"], border=True)
    k[1].metric("Pannes", brief["n_failures"], border=True)
    k[2].metric("Arrêts machine", brief["n_stops"], border=True)
    k[3].metric("Heures d'arrêt", f"{brief['downtime_h']:.1f} h", border=True, help="Arrêts terminés commencés ce jour-là")
    k[4].metric("Urgences", brief["n_emergencies"], border=True)
    k[5].metric("Récidives connues", brief["n_recurring"], border=True,
                help="Panne sur un équipement et un mode déjà identifiés comme récurrents")

    still = brief["still_down"]
    if still.empty:
        st.success("Aucun équipement à l'arrêt en fin de journée.")
    else:
        st.error(f"**{len(still)} équipement(s) toujours à l'arrêt en fin de journée** : "
                 + " · ".join(f"{r.equipment_desc} ({r.down_since_h:.0f} h)" for r in still.itertuples()))
    items = brief["interventions"].assign(
        nature=lambda d: d["order_kind"].map(ORDER_TYPE_LABELS),
        mode=lambda d: d["category"].map(CATEGORIES).fillna(""),
        start=lambda d: d["malfunction_start"].dt.strftime("%H:%M").fillna(""),
        arret=lambda d: [("en cours" if still else f"{h:.1f} h") if stop else ""
                         for h, stop, still in zip(d["downtime_h"], d["is_stop"], d["order_id"].isin(still["order_id"]))],
        recidive=lambda d: d["recurring"].map({True: "⚠️", False: ""}))
    if items.empty:
        st.info("Aucune intervention enregistrée ce jour-là.")
    else:
        st.dataframe(items[["order_id", "recidive", "nature", "equipment_desc", "description", "mode", "priority",
                            "start", "arret"]],
                     hide_index=True, width="stretch",
                     column_config={"order_id": "Ordre", "recidive": st.column_config.TextColumn("", width=40, help="Panne récurrente connue"), "nature": "Nature", "equipment_desc": "Équipement",
                                    "description": "Description", "mode": "Mode de défaillance", "priority": "Prio",
                                    "start": "Début panne", "arret": "Arrêt"})
    st.caption("⚠️ = panne récurrente connue (même équipement, même mode). "
               "Astuce : déposez directement l'export de la transaction ZGMT_IW29 pour préparer la réunion du matin.")

# ---------------------------------------------------------------- Équipements
with t_eq:
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
with t_cat:
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
with t_rep:
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
with t_trend:
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
with t_bl:
    k = st.columns(3)
    k[0].metric("Ordres ouverts", ov["open_orders"], border=True)
    k[1].metric("En retard", ov["overdue_orders"], border=True,
                help="Ordres ouverts dont la date de début de base (IW39 « Bsc start ») est dépassée")
    k[2].metric("Ouverts depuis plus de 30 jours", ov["backlog_over_30d"], border=True)
    c1, c2 = st.columns([1.3, 1])
    with c1:
        st.markdown("##### Par poste de travail principal")
        st.dataframe(a.workcenters, hide_index=True, width="stretch",
                     column_config={"work_center": "Poste de travail", "open_orders": "Ouverts",
                                    "overdue": st.column_config.ProgressColumn(
                                        "En retard", format="%d", min_value=0,
                                        max_value=int(a.workcenters["open_orders"].max() or 1) if len(a.workcenters) else 1),
                                    "high_priority_open": "Prio 1-2", "max_days_late": "Retard max (j)",
                                    "oldest_days": None})
    with c2:
        st.markdown("##### Ancienneté des ordres ouverts")
        st.plotly_chart(bar(a.backlog_buckets, "age_bucket", "orders", orientation="v", height=260,
                            labels={"age_bucket": "", "orders": "Ordres"}), width="stretch")
    only_late = st.toggle("Afficher uniquement les ordres en retard", value=True)
    bl = a.backlog[a.backlog["is_overdue"]] if only_late else a.backlog
    st.dataframe(bl.assign(days_late=bl["days_late"].clip(lower=0)), hide_index=True, width="stretch", height=480,
                 column_config={"order_id": "Ordre", "order_type": "Type", "work_center": "Poste de travail",
                                "equipment_id": "Équipement", "equipment_desc": "Désignation", "description": "Description",
                                "priority": "Prio", "status": "Statut",
                                "created_date": st.column_config.DateColumn("Créé le", format="DD/MM/YYYY"),
                                "basic_start": st.column_config.DateColumn("Début de base", format="DD/MM/YYYY"),
                                "days_late": st.column_config.NumberColumn("Retard (j)", format="%d"),
                                "is_overdue": None, "age_days": "Âge (j)", "age_bucket": None})

# ---------------------------------------------------------------- Qualité
with t_q:
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
with t_x:
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
