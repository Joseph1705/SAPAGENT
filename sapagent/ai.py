"""Optional AI layer: classify the texts the rules could not place, and write the analysis.

Two providers are supported:

* ``anthropic``  — Claude through the official Anthropic SDK (``ANTHROPIC_API_KEY``).
* ``openrouter`` — any model on OpenRouter (``OPENROUTER_API_KEY``), e.g. Claude,
  GPT, Gemini, Mistral, Llama… through its OpenAI-compatible endpoint.

The model never computes KPIs. It receives the numbers produced by ``kpis.py``
and is told to use only those numbers.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import pandas as pd
import requests

from .insights import summary_payload
from .kpis import Analysis
from .schema import CATEGORIES

ANTHROPIC_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
OPENROUTER_URL = "https://openrouter.ai/api/v1"
PROVIDERS = {"anthropic": "Anthropic (Claude)", "openrouter": "OpenRouter"}


class AIError(RuntimeError):
    pass


@dataclass
class AIConfig:
    provider: str = "anthropic"
    api_key: str | None = None
    model: str | None = None

    @classmethod
    def from_env(cls, provider: str | None = None, model: str | None = None) -> AIConfig:
        provider = provider or os.environ.get("SAPAGENT_PROVIDER") or (
            "openrouter" if os.environ.get("OPENROUTER_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY") else "anthropic")
        return cls(provider=provider, model=model or os.environ.get("SAPAGENT_MODEL"))

    @property
    def key(self) -> str | None:
        if self.api_key:
            return self.api_key
        if self.provider == "openrouter":
            return os.environ.get("OPENROUTER_API_KEY")
        return os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")

    def resolved_model(self) -> str:
        if self.model:
            return self.model
        if self.provider == "openrouter":
            self.model = default_openrouter_model(self.key)
            return self.model
        return ANTHROPIC_MODEL

    @property
    def label(self) -> str:
        """Short name shown in the app and report, e.g. 'Claude' or 'openai/gpt-5'."""
        if self.provider == "anthropic":
            return "Claude"
        return self.model or "OpenRouter"


def has_credentials(cfg: AIConfig) -> bool:
    return bool(cfg.key)


# ---------------------------------------------------------------- transport
def _ask_json(cfg: AIConfig, system: str, prompt: str, schema: dict, effort: str, name: str) -> dict:
    if cfg.provider == "openrouter":
        return _ask_openrouter(cfg, system, prompt, schema, name)
    if cfg.provider == "anthropic":
        return _ask_anthropic(cfg, system, prompt, schema, effort)
    raise AIError(f"Fournisseur IA inconnu : {cfg.provider}")


def _ask_anthropic(cfg: AIConfig, system: str, prompt: str, schema: dict, effort: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=cfg.key) if cfg.key else anthropic.Anthropic()
    response = client.beta.messages.create(
        model=cfg.resolved_model(),
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


def _openrouter_headers(key: str | None) -> dict:
    if not key:
        raise AIError("Clé OpenRouter manquante (OPENROUTER_API_KEY).")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        # Optional attribution headers recommended by OpenRouter.
        "HTTP-Referer": "https://github.com/Joseph1705/SAPAGENT",
        "X-Title": "SAP PM Analyst",
    }


def _ask_openrouter(cfg: AIConfig, system: str, prompt: str, schema: dict, name: str) -> dict:
    """Strict JSON-schema output when the model supports it; plain JSON mode otherwise."""
    model = cfg.resolved_model()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    strict_body = {
        "model": model,
        "messages": messages,
        "max_tokens": 16000,
        "response_format": {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
        # Only route to providers that honour response_format.
        "provider": {"require_parameters": True},
    }
    status, data = _post_openrouter(cfg.key, strict_body)
    if status in (400, 404, 422) and _looks_unsupported(data):
        # The model has no endpoint with structured outputs: describe the schema in the prompt instead.
        loose = messages[:-1] + [{"role": "user", "content": (
            f"{prompt}\n\nRéponds uniquement avec un objet JSON valide conforme à ce schéma JSON, sans texte autour :\n"
            f"{json.dumps(schema, ensure_ascii=False)}")}]
        status, data = _post_openrouter(cfg.key, {"model": model, "messages": loose, "max_tokens": 16000,
                                                  "response_format": {"type": "json_object"}})
    if status != 200:
        raise AIError(f"OpenRouter ({model}) : {_error_message(data, status)}")

    choice = (data.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content")
    if choice.get("finish_reason") == "length":
        raise AIError(f"Réponse de {model} tronquée (max_tokens).")
    if not content:
        raise AIError(f"Réponse vide de {model}.")
    return parse_json(content)


def _post_openrouter(key: str | None, body: dict) -> tuple[int, dict]:
    try:
        r = requests.post(f"{OPENROUTER_URL}/chat/completions", headers=_openrouter_headers(key),
                          json=body, timeout=300)
    except requests.RequestException as exc:
        raise AIError(f"OpenRouter injoignable : {exc}") from exc
    try:
        data = r.json()
    except ValueError:
        data = {"error": {"message": r.text[:300]}}
    if r.status_code == 200 and "error" in data:  # errors can also arrive with HTTP 200
        code = (data.get("error") or {}).get("code")
        return (code if isinstance(code, int) else 500), data
    return r.status_code, data


def _error_message(data: dict, status: int) -> str:
    err = data.get("error") or {}
    return f"{err.get('message') or 'erreur inconnue'} (HTTP {status})"


def _looks_unsupported(data: dict) -> bool:
    msg = _error_message(data, 0).lower()
    return any(k in msg for k in ("no endpoints", "response_format", "structured", "json_schema", "not support"))


def parse_json(text: str) -> dict:
    """Parse model output that should be JSON, tolerating ```json fences or text around it."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise AIError("La réponse du modèle n'est pas du JSON.")
        return json.loads(text[start:end + 1])


def list_openrouter_models(key: str | None = None, structured_only: bool = True) -> list[dict]:
    """Models available on OpenRouter (public endpoint), newest first."""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    r = requests.get(f"{OPENROUTER_URL}/models", headers=headers, timeout=30)
    r.raise_for_status()
    models = r.json().get("data", [])
    if structured_only:
        models = [m for m in models if "structured_outputs" in (m.get("supported_parameters") or [])]
    return sorted(models, key=lambda m: m.get("created") or 0, reverse=True)


def pick_default_model(ids: list[str]) -> str | None:
    """Newest Claude Opus, else newest Claude Sonnet, else the first (newest) id."""
    for prefix in ("anthropic/claude-opus", "anthropic/claude-sonnet", ""):
        for model_id in ids:
            if model_id.startswith(prefix):
                return model_id
    return None


def default_openrouter_model(key: str | None = None) -> str:
    try:
        models = list_openrouter_models(key)
    except requests.RequestException as exc:
        raise AIError(f"Impossible de lister les modèles OpenRouter ({exc}). Indiquez le modèle avec SAPAGENT_MODEL.") from exc
    model = pick_default_model([m["id"] for m in models])
    if not model:
        raise AIError("Aucun modèle OpenRouter compatible trouvé. Indiquez le modèle avec SAPAGENT_MODEL.")
    return model


# ---------------------------------------------------------------- tasks
CLASSIFY_SYSTEM = (
    "Tu es ingénieur fiabilité dans une usine minière (concassage, broyage, flottation, engins). "
    "Tu classes les descriptions libres saisies par les techniciens dans SAP PM (français, anglais, abréviations "
    "d'atelier comme 'rlt' = roulement, 'HS' = hors service, 'chgt' = changement). "
    "Si le texte ne permet pas de savoir ce qui a cassé, réponds 'other' avec une confiance basse plutôt que de deviner."
)


def classify_with_ai(df: pd.DataFrame, cfg: AIConfig, batch_size: int = 150) -> pd.DataFrame:
    """Re-classify failures the keyword rules left unclassified or uncertain."""
    out = df.copy()
    todo = out["is_failure"] & out["category_source"].isin(["Non classé", "Règles mots-clés"]) & (out["category_confidence"] < 0.8)
    texts = sorted(out.loc[todo, "description"].dropna().astype(str).unique())
    if not texts:
        return out

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
            cfg, CLASSIFY_SYSTEM,
            f"Catégories possibles :\n{legend}\n\nClasse chaque description (id = numéro de ligne), "
            f"confiance entre 0 et 1 :\n{listing}",
            schema, effort="low", name="classification",
        )
        for item in data.get("items", []):
            cat = item.get("category")
            if isinstance(item.get("id"), int) and 0 <= item["id"] < len(batch) and cat in CATEGORIES:
                results[batch[item["id"]]] = (cat, float(item.get("confidence") or 0))

    for idx in out.index[todo]:
        hit = results.get(str(out.at[idx, "description"]))
        if hit and hit[0] != "other" and hit[1] >= 0.5:
            out.at[idx, "category"], out.at[idx, "category_confidence"] = hit
            out.at[idx, "category_source"] = f"IA ({cfg.label})"
    return out


ANALYSIS_SYSTEM = (
    "Tu es ingénieur méthodes / fiabilité senior en maintenance industrielle minière. "
    "Tu rédiges pour l'ingénieur maintenance et son responsable une analyse claire et actionnable des données SAP PM. "
    "Règles : utilise uniquement les chiffres fournis, sans en inventer ni en recalculer ; cite l'équipement et le chiffre "
    "qui justifient chaque recommandation ; propose des actions concrètes de maintenance (RCA, ajustement d'intervalle "
    "préventif, surveillance conditionnelle, pièces, procédures, formation) ; signale quand la qualité des données limite "
    "une conclusion. Rédige en français, phrases courtes, sans jargon inutile."
)

INSIGHTS_SCHEMA = {
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


def ai_insights(a: Analysis, cfg: AIConfig) -> dict:
    payload = json.dumps(summary_payload(a), ensure_ascii=False, default=str, indent=1)
    data = _ask_json(
        cfg, ANALYSIS_SYSTEM,
        "Voici les indicateurs calculés à partir de l'export SAP PM (heures, USD, ratios entre 0 et 1) :\n"
        f"<donnees>\n{payload}\n</donnees>\n\n"
        "Rédige : un résumé exécutif (4 à 6 phrases), 4 à 7 constats clés, et 5 à 8 recommandations "
        "classées par priorité.",
        INSIGHTS_SCHEMA, effort="medium", name="analyse_maintenance",
    )
    # Models without strict schema support may drift: keep only well-formed recommendations.
    if not isinstance(data.get("executive_summary"), str) or not isinstance(data.get("recommendations"), list):
        raise AIError("Réponse de l'IA incomplète.")
    data["key_findings"] = [str(k) for k in data.get("key_findings", [])]
    data["recommendations"] = [
        {**r, "priority": r["priority"] if r.get("priority") in ("Haute", "Moyenne", "Basse") else "Moyenne"}
        for r in data["recommendations"]
        if isinstance(r, dict) and all(k in r for k in ("equipment", "action", "rationale"))
    ]
    data["source"] = "ai"
    data["model"] = cfg.label
    return data
