"""Turn technicians' free text ("rlt chauffe palier") into failure categories.

Order of trust: a valid SAP damage code first, then keyword rules (French and
English, including common shop-floor abbreviations), then optionally Claude for
whatever the rules could not place.
"""

from __future__ import annotations

import re

import pandas as pd

from .schema import DAMAGE_CODES, normalise

# Keyword stems, matched on normalised text (no accents, lower-case) at word starts.
KEYWORDS: dict[str, list[str]] = {
    "bearing": ["roulement", "rlt", "roul", "bearing", "brg", "palier", "coussinet", "bushing"],
    "seal": ["fuite", "garniture", "etancheite", "joint", "presse etoupe", "leak", "seal", "gland", "suintement"],
    "belt": ["bande", "courroie", "belt", "jonction", "rouleau", "idler", "tambour", "pulley", "desalignement bande", "racleur"],
    "electrical": ["electrique", "moteur grille", "disjonct", "cable", "variateur", "court circuit", "contacteur", "trip",
                   "overload", "surcharge electrique", "isolement", "fusible", "vfd", "electrical", "phase"],
    "hydraulic": ["hydraul", "verin", "flexible", "pression huile", "hose", "cylinder", "accumulateur", "distributeur"],
    "overheating": ["surchauffe", "temperature", "chauffe", "echauffement", "overheat", "high temp", "hot"],
    "vibration": ["vibration", "vibre", "bruit", "noise", "claquement", "balourd", "cognement"],
    "wear": ["usure", "use", "blindage", "revetement", "liner", "wear", "worn", "impulseur", "impeller", "machoire", "dents"],
    "lubrication": ["graiss", "lubrif", "huile niveau", "niveau huile", "manque huile", "grease", "lube", "oil level", "low oil"],
    "instrumentation": ["capteur", "sonde", "transmetteur", "debitmetre", "sensor", "transmitter", "probe", "instrument",
                        "automate", "plc", "fin de course", "detecteur"],
    "structural": ["fissure", "soudure", "crack", "chassis", "boulon", "bolt", "structure", "cassure", "support casse", "frame"],
    "blockage": ["bourrage", "bouche", "obstru", "blocage tremie", "colmat", "blocked", "chute", "goulotte", "engorgement", "plugged"],
}

# Phrases that would otherwise hit a weaker category first.
PRIORITY_ORDER = ["seal", "bearing", "belt", "blockage", "hydraulic", "lubrication", "instrumentation",
                  "electrical", "overheating", "wear", "structural", "vibration"]

_PATTERNS = {
    cat: re.compile(r"\b(" + "|".join(re.escape(normalise(k)) for k in words) + r")")
    for cat, words in KEYWORDS.items()
}


def classify_text(text: str | None) -> tuple[str, float]:
    """Return (category, confidence) for one description using keyword rules."""
    if not text or pd.isna(text):
        return "other", 0.0
    norm = normalise(text)
    hits = {cat: len(_PATTERNS[cat].findall(norm)) for cat in PRIORITY_ORDER}
    hits = {c: n for c, n in hits.items() if n}
    if not hits:
        return "other", 0.0
    best = max(hits, key=lambda c: (hits[c], -PRIORITY_ORDER.index(c)))
    confidence = 0.85 if len(hits) == 1 else 0.6
    return best, confidence


def classify_orders(df: pd.DataFrame) -> pd.DataFrame:
    """Add category, category_confidence and category_source columns."""
    out = df.copy()
    categories, confidences, sources = [], [], []
    for code, text, failure in zip(out["damage_code"], out["description"], out["is_failure"]):
        if not failure:
            categories.append(None)
            confidences.append(None)
            sources.append("Ordre planifié")
            continue
        code_key = str(code).upper()[:4] if pd.notna(code) else None
        if code_key in DAMAGE_CODES:
            categories.append(DAMAGE_CODES[code_key])
            confidences.append(1.0)
            sources.append("Code SAP")
            continue
        cat, conf = classify_text(text)
        categories.append(cat)
        confidences.append(conf)
        sources.append("Règles mots-clés" if cat != "other" else "Non classé")
    out["category"] = categories
    out["category_confidence"] = confidences
    out["category_source"] = sources
    return out
