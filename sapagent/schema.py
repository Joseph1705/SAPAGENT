"""Canonical data model and the column aliases used to recognise SAP PM exports.

SAP lets every user choose their own ALV layout and language, so the same field
can arrive as ``AUFNR``, ``Order``, ``Ordre`` or ``N° d'ordre``. Every alias is
normalised (lower-case, no accents, no punctuation) before matching.
"""

from __future__ import annotations

import re
import unicodedata

# canonical name -> (label shown to users, accepted aliases)
COLUMNS: dict[str, tuple[str, list[str]]] = {
    "order_id": ("N° d'ordre", ["aufnr", "order", "ordre", "n ordre", "no ordre", "numero ordre", "work order", "order number"]),
    "order_type": ("Type d'ordre", ["auart", "order type", "type ordre", "type d ordre", "type"]),
    "notification_id": ("N° d'avis", ["qmnum", "notification", "notif", "avis", "n avis", "no avis", "notification number"]),
    "notification_type": ("Type d'avis", ["qmart", "notification type", "notif type", "notifictn type", "type avis", "type d avis"]),
    "equipment_id": ("Équipement", ["equnr", "equipment", "equipement", "n equipement", "equipment number"]),
    "equipment_desc": ("Désignation équipement", ["eqktx", "equipment description", "description equipement", "designation equipement", "desig equipement", "equipment desc"]),
    "functional_location": ("Poste technique", ["tplnr", "functional location", "functional loc", "functional loc.", "poste technique", "func loc"]),
    "description": ("Description (texte libre)", ["ktext", "qmtxt", "description", "short text", "texte court", "designation", "desc", "texte", "libelle"]),
    "priority": ("Priorité", ["priok", "priority", "priorite", "prio"]),
    "created_date": ("Date de création", ["erdat", "qmdat", "created on", "date de creation", "cree le", "creation date", "notif date", "notification date", "date avis", "date"]),
    "basic_start": ("Date de début de base", ["gstrp", "bsc start", "bsc start date", "basic start", "basic start date", "bas start date",
                                               "debut base", "date de debut de base", "date debut de base", "debut au plus tot",
                                               "date debut au plus tot", "debut prevu"]),
    "malfunction_start": ("Début panne", ["ausvn", "malfunction start", "malfunct start", "start of malfunction", "debut panne", "debut de panne", "debut dysfonctionnement"]),
    "malfunction_end": ("Fin panne", ["ausbs", "malfunction end", "malfunct end", "end of malfunction", "fin panne", "fin de panne", "fin dysfonctionnement"]),
    "breakdown": ("Arrêt machine", ["msaus", "breakdown", "breakdown indicator", "breakdown ind", "arret", "arret machine", "panne"]),
    "status": ("Statut système", ["sttxt", "system status", "status", "statut", "statut systeme"]),
    "actual_cost": ("Coûts réels", ["gksti", "actual costs", "total actual costs", "tot act costs", "total act costs", "couts reels", "couts reels totaux", "cout", "cost"]),
    "work_center": ("Poste de travail principal", ["vaplz", "arbpl", "main work center", "main work centre", "main workctr", "main work ctr", "mn wk ctr",
                                                    "mnwkctr", "work center", "work centre", "poste de travail", "poste de travail principal", "poste trav princ"]),
    "damage_code": ("Code dommage", ["fecod", "damage code", "damage", "code dommage", "dommage"]),
    "cause_code": ("Code cause", ["urcod", "cause code", "cause", "code cause"]),
    "actual_hours": ("Heures réelles", ["ismnw", "actual work", "travail reel", "heures reelles", "actual hours"]),
}

# An export needs an identifier, an equipment and at least one date (checked in the loader).
KEY_COLUMNS = ["order_id", "notification_id"]
DATE_COLUMNS = ["created_date", "basic_start", "malfunction_start"]
RECOMMENDED = ["order_type", "description", "basic_start", "malfunction_start", "malfunction_end", "status",
               "actual_cost", "work_center"]

# Default SAP PM order-type meaning. Plants customise these; edit to match.
ORDER_TYPES = {
    "PM01": "corrective",
    "PM02": "preventive",
    "PM03": "inspection",
    "PM04": "emergency",
}
# Standard SAP PM notification types, used when the export has no order type (IW29 / ZGMT_IW29).
NOTIFICATION_TYPES = {
    "M1": "request",      # demande de maintenance
    "M2": "corrective",   # avis de panne / dysfonctionnement
    "M3": "activity",     # compte rendu d'activité
}
ORDER_TYPE_LABELS = {
    "corrective": "Correctif",
    "preventive": "Préventif",
    "inspection": "Inspection",
    "emergency": "Urgence",
    "request": "Demande",
    "activity": "Compte rendu",
    "unknown": "Inconnu",
}
FAILURE_KINDS = {"corrective", "emergency"}
PLANNED_KINDS = {"preventive", "inspection"}

CLOSED_STATUSES = ("TECO", "CLSD", "CLOT", "CLOS", "CLOSED", "DLFL", "NOCO", "ACCL")

CATEGORIES: dict[str, str] = {
    "bearing": "Roulements",
    "seal": "Étanchéité / Fuites",
    "belt": "Bande / Convoyeur",
    "electrical": "Électrique",
    "hydraulic": "Hydraulique",
    "overheating": "Surchauffe",
    "vibration": "Vibrations / Bruit",
    "wear": "Usure",
    "lubrication": "Lubrification",
    "instrumentation": "Instrumentation",
    "structural": "Structure / Fissures",
    "blockage": "Bourrage / Obstruction",
    "other": "Autre / Non classé",
}

# Example SAP damage-code catalogue. Replace with the plant's own catalogue.
DAMAGE_CODES = {
    "ROUL": "bearing",
    "FUIT": "seal",
    "BAND": "belt",
    "ELEC": "electrical",
    "HYDR": "hydraulic",
    "TEMP": "overheating",
    "VIBR": "vibration",
    "USUR": "wear",
    "LUBR": "lubrication",
    "INST": "instrumentation",
    "STRU": "structural",
    "BOUR": "blockage",
}


def normalise(text: str) -> str:
    """Lower-case, strip accents and punctuation: 'N° d'Équipement' -> 'n d equipement'."""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return text.strip()


ALIAS_INDEX: dict[str, str] = {
    normalise(alias): canonical
    for canonical, (label, aliases) in COLUMNS.items()
    for alias in [canonical, label, *aliases]
}
