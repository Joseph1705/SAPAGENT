"""Optional Claude layer: classify the texts the rules could not place, and write the analysis.

Claude never computes KPIs. It receives the numbers produced by ``kpis.py`` and
is told to use only those numbers.
"""

from __future__ import annotations

import json
import os

import anthropic
import pandas as pd

from .insights import summary_payload
from .kpis import Analysis
from .schema import CATEGORIES

MODEL = os.environ.get("SAPAGENT_MODEL", "claude-opus-5-5")
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AIError(RuntimeError):
    pass


def has_credentials(api_key: str | None = None) -> bool:
    return bool(api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _client(api_key: str | None) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()


def _ask_json(client: anthropic.Anthropic, system: str, prompt: str, schema: dict, effort: str) -> dict:
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    if response.stop_reason == "refusal":
        raise AIError("Claude a refusé la requête.")
    if response.stop_reason == "max_tokens":
        raise AIError("Réponse de Claude tronquée (max_tokens).")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise AIError("Réponse de Claude vide.")
    return json.loads(text)


CLASSIFY_SYSTEM = (
    "Tu es ingénieur fiabilité dans une usine minière (concassage, broyage, flottation, engins). "
    "Tu classes les descriptions libres saisies par les techniciens dans SAP PM (français, anglais, abréviations "
    "d'atelier comme 'rlt' = roulement, 'HS' = hors service, 'chgt' = changement). "
    "Si le texte ne permet pas de savoir ce qui a cassé, réponds 'other' avec une confiance basse plutôt que de deviner."
)


def classify_with_claude(df: pd.DataFrame, api_key: str | None = None, batch_size: int = 150) -> pd.DataFrame:
    """Re-classify failures the keyword rules left unclassified or uncertain."""
    out = df.copy()
    todo = out["is_failure"] & out["category_source"].isin(["Non classé", "Règles mots-clés"]) & (out["category_confidence"] < 0.8)
    texts = sorted(out.loc[todo, "description"].dropna().astype(str).unique())
    if not texts:
        return out

    client = _client(api_key)
    schema = {
        "type": "object",
        "properties": {"items": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "category": {"type": "string", "enum": list(CATEGORIES)},
                "confidence": {"type": "number"},
            },
            "required": ["id", "category", "confidence"],
            "additionalProperties": False,
        }}},
        "required": ["items"],
        "additionalProperties": False,
    }
    legend = "\n".join(f"- {k} : {v}" for k, v in CATEGORIES.items())
    results: dict[str, tuple[str, float]] = {}
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        listing = "\n".join(f"{i}. {t}" for i, t in enumerate(batch))
        data = _ask_json(
            client, CLASSIFY_SYSTEM,
            f"Catégories possibles :\n{legend}\n\nClasse chaque description (id = numéro de ligne), "
            f"confiance entre 0 et 1 :\n{listing}",
            schema, effort="low",
        )
        for item in data["items"]:
            if 0 <= item["id"] < len(batch):
                results[batch[item["id"]]] = (item["category"], float(item["confidence"]))

    for idx in out.index[todo]:
        hit = results.get(str(out.at[idx, "description"]))
        if hit and hit[0] != "other" and hit[1] >= 0.5:
            out.at[idx, "category"], out.at[idx, "category_confidence"] = hit
            out.at[idx, "category_source"] = "IA (Claude)"
    return out


ANALYSIS_SYSTEM = (
    "Tu es ingénieur méthodes / fiabilité senior en maintenance industrielle minière. "
    "Tu rédiges pour l'ingénieur maintenance et son responsable une analyse claire et actionnable des données SAP PM. "
    "Règles : utilise uniquement les chiffres fournis, sans en inventer ni en recalculer ; cite l'équipement et le chiffre "
    "qui justifient chaque recommandation ; propose des actions concrètes de maintenance (RCA, ajustement d'intervalle "
    "préventif, surveillance conditionnelle, pièces, procédures, formation) ; signale quand la qualité des données limite "
    "une conclusion. Rédige en français, phrases courtes, sans jargon inutile."
)


def ai_insights(a: Analysis, api_key: str | None = None) -> dict:
    schema = {
        "type": "object",
        "properties": {
            "executive_summary": {"type": "string"},
            "key_findings": {"type": "array", "items": {"type": "string"}},
            "recommendations": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "priority": {"type": "string", "enum": ["Haute", "Moyenne", "Basse"]},
                    "equipment": {"type": "string"},
                    "action": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["priority", "equipment", "action", "rationale"],
                "additionalProperties": False,
            }},
        },
        "required": ["executive_summary", "key_findings", "recommendations"],
        "additionalProperties": False,
    }
    payload = json.dumps(summary_payload(a), ensure_ascii=False, default=str, indent=1)
    data = _ask_json(
        _client(api_key), ANALYSIS_SYSTEM,
        "Voici les indicateurs calculés à partir de l'export SAP PM (heures, USD, ratios entre 0 et 1) :\n"
        f"<donnees>\n{payload}\n</donnees>\n\n"
        "Rédige : un résumé exécutif (4 à 6 phrases), 4 à 7 constats clés, et 5 à 8 recommandations "
        "classées par priorité.",
        schema, effort="medium",
    )
    data["source"] = "claude"
    return data
