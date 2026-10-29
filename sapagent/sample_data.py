"""Generate a realistic, entirely fictitious SAP PM order export (IW39-style layout).

The plant, equipment numbers and texts are invented. The data deliberately
contains what real exports contain: a few chronic "bad actors", recurring
failures, missing damage codes, abbreviations, an old open backlog and a handful
of data-entry errors, so the analysis has something real to find.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# id, description, functional location, failures/year, {failure mode: weight}, mean repair hours, cost scale (USD)
EQUIPMENT = [
    ("10001001", "Concasseur primaire giratoire", "KV-CON-010", 14, {"wear": 4, "hydraulic": 2, "bearing": 2, "lubrication": 1, "blockage": 3}, 9, 9000),
    ("10001002", "Concasseur secondaire à cône", "KV-CON-020", 10, {"wear": 4, "hydraulic": 2, "lubrication": 2, "overheating": 1}, 7, 6500),
    ("10001010", "Broyeur à boulets n°1", "KV-BRO-010", 12, {"bearing": 3, "overheating": 3, "lubrication": 2, "wear": 2, "electrical": 1}, 14, 15000),
    ("10001011", "Broyeur à boulets n°2", "KV-BRO-020", 7, {"wear": 3, "bearing": 2, "lubrication": 2}, 10, 12000),
    ("10001020", "Pompe à pulpe P-201", "KV-POM-201", 26, {"seal": 7, "wear": 2, "bearing": 2, "vibration": 2}, 4, 2200),
    ("10001021", "Pompe à pulpe P-202", "KV-POM-202", 9, {"seal": 3, "wear": 2, "vibration": 1}, 4, 2000),
    ("10001022", "Pompe d'eau de procédé P-301", "KV-POM-301", 5, {"seal": 2, "electrical": 1, "bearing": 1}, 3, 1200),
    ("10001030", "Convoyeur à bande CV-03", "KV-CNV-003", 19, {"belt": 7, "bearing": 2, "blockage": 2, "electrical": 1}, 5, 3500),
    ("10001031", "Convoyeur à bande CV-04", "KV-CNV-004", 8, {"belt": 4, "blockage": 2, "bearing": 1}, 4, 3000),
    ("10001032", "Convoyeur d'alimentation CV-01", "KV-CNV-001", 6, {"belt": 3, "blockage": 3}, 3, 2500),
    ("10001040", "Crible vibrant SC-01", "KV-CRI-001", 9, {"structural": 3, "vibration": 3, "bearing": 2, "wear": 2}, 6, 4000),
    ("10001041", "Crible vibrant SC-02", "KV-CRI-002", 6, {"structural": 2, "vibration": 2, "wear": 2}, 5, 3800),
    ("10001050", "Cellule de flottation FL-05", "KV-FLO-005", 5, {"electrical": 2, "wear": 2, "instrumentation": 2}, 4, 2500),
    ("10001051", "Cellule de flottation FL-06", "KV-FLO-006", 4, {"electrical": 1, "wear": 2, "instrumentation": 1}, 4, 2500),
    ("10001060", "Épaississeur TH-01", "KV-EPA-001", 4, {"hydraulic": 2, "instrumentation": 2, "structural": 1}, 8, 6000),
    ("10001070", "Filtre presse FP-01", "KV-FIL-001", 8, {"hydraulic": 4, "seal": 2, "instrumentation": 1}, 6, 4500),
    ("10001080", "Compresseur d'air CP-01", "KV-COM-001", 6, {"overheating": 3, "lubrication": 2, "electrical": 1}, 5, 3500),
    ("10001081", "Compresseur d'air CP-02", "KV-COM-002", 3, {"overheating": 1, "lubrication": 1, "electrical": 1}, 4, 3000),
    ("10001090", "Pont roulant 20 t", "KV-PON-001", 3, {"electrical": 2, "structural": 1}, 5, 3000),
    ("10001100", "Ventilateur de tirage VT-01", "KV-VEN-001", 4, {"vibration": 3, "bearing": 2}, 6, 3500),
    ("10001110", "Électrolyseur – redresseur RD-01", "KV-ELE-001", 5, {"electrical": 4, "overheating": 2, "instrumentation": 1}, 7, 8000),
    ("10001120", "Chargeuse sur pneus CAT 988", "KV-MOB-988", 11, {"hydraulic": 4, "wear": 2, "electrical": 2, "overheating": 1}, 8, 7000),
    ("10001121", "Tombereau CAT 777 n°12", "KV-MOB-777", 9, {"hydraulic": 2, "wear": 2, "overheating": 2, "electrical": 2}, 9, 8000),
]

TEXTS = {
    "bearing": ["Roulement HS côté accouplement", "bruit roulement palier moteur", "Bearing failure NDE", "rlt chauffe palier",
                "remplacement roulement palier", "Jeu excessif au palier", "chgt rlt côté opposé accouplement"],
    "seal": ["fuite garniture mécanique", "Fuite au niveau de la garniture", "mechanical seal leak", "fuite pulpe presse-étoupe",
             "chgt garniture", "Fuite importante côté refoulement", "joint HS fuite eau"],
    "belt": ["Bande déchirée", "désalignement bande", "belt misalignment", "jonction bande ouverte", "rouleau bloqué convoyeur",
             "racleur usé bande sale", "Bande patine sur tambour"],
    "electrical": ["Défaut moteur électrique", "disjoncteur déclenché", "motor tripped on overload", "câble endommagé",
                   "défaut variateur", "Contacteur HS", "défaut isolement moteur"],
    "hydraulic": ["fuite huile vérin", "pression hydraulique basse", "hydraulic hose burst", "flexible hydraulique éclaté",
                  "vérin de levage bloqué", "distributeur hydraulique HS"],
    "overheating": ["température élevée réducteur", "surchauffe moteur", "high temperature gearbox", "échauffement palier",
                    "Alarme température huile"],
    "vibration": ["vibrations anormales", "bruit anormal pompe", "excessive vibration", "machine fait du bruit",
                  "claquement au démarrage"],
    "wear": ["usure blindages", "remplacement revêtements usés", "liner wear", "usure impulseur", "usure mâchoires",
             "dents godet usées"],
    "lubrication": ["manque graisse", "défaut lubrification", "pompe graissage HS", "low oil level", "niveau huile bas réducteur"],
    "instrumentation": ["capteur de niveau défaillant", "sonde température HS", "faulty pressure transmitter",
                        "débitmètre erroné", "fin de course HS"],
    "structural": ["fissure châssis", "soudure cassée", "crack on support frame", "boulons desserrés", "support cassé"],
    "blockage": ["bourrage goulotte", "goulotte bouchée", "blocage trémie", "chute blocked", "engorgement alimentation"],
}
VAGUE = ["intervention suite appel", "voir chef de quart", "RAS après contrôle", "dépannage", "à vérifier", "problème machine"]
PREVENTIVE = ["PM 500h - inspection mensuelle", "Graissage hebdomadaire", "Inspection vibratoire", "Remplacement filtres huile - préventif",
              "Contrôle hebdomadaire bande", "Visite systématique", "Analyse d'huile trimestrielle"]
INSPECTION = ["Inspection thermographique", "Ronde d'inspection", "Contrôle ultrasons", "Inspection sécurité"]
CODE_FOR = {"bearing": "ROUL", "seal": "FUIT", "belt": "BAND", "electrical": "ELEC", "hydraulic": "HYDR", "overheating": "TEMP",
            "vibration": "VIBR", "wear": "USUR", "lubrication": "LUBR", "instrumentation": "INST", "structural": "STRU", "blockage": "BOUR"}
WORK_CENTERS = {"electrical": "ELEC-01", "instrumentation": "INST-01"}
# Preventive work centre by plant area (from the functional location code).
PREV_CENTERS = {"CON": "MECA-CON", "BRO": "MECA-BRO", "POM": "MECA-HYD", "CNV": "MECA-MAN", "CRI": "MECA-MAN",
                "FLO": "MECA-HYD", "EPA": "MECA-HYD", "FIL": "MECA-HYD", "COM": "MECA-UTI", "PON": "MECA-UTI",
                "VEN": "MECA-UTI", "ELE": "ELEC-01", "MOB": "MECA-MOB"}


def generate(start: str = "2025-09-01", months: int = 12, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t0 = pd.Timestamp(start)
    t1 = t0 + pd.DateOffset(months=months)
    span_days = (t1 - t0).days
    rows = []

    def add(eq, kind, created, text, mode=None, down_h=0.0, cost=0.0, hours=0.0, still_down=False, scripted=False):
        rows.append({"eq": eq, "kind": kind, "created": created, "text": text, "mode": mode, "down_h": down_h,
                     "cost": cost, "hours": hours, "still_down": still_down, "scripted": scripted})

    for eq in EQUIPMENT:
        eq_id, desc, floc, rate, modes, repair_h, cost_scale = eq
        n_fail = rng.poisson(rate * months / 12)
        names, weights = list(modes), np.array(list(modes.values()), float)
        for _ in range(n_fail):
            mode = rng.choice(names, p=weights / weights.sum())
            created = t0 + pd.Timedelta(minutes=int(rng.integers(0, span_days * 1440)))
            down = float(np.round(rng.lognormal(np.log(repair_h), 0.6), 1))
            emergency = rng.random() < 0.35
            text = rng.choice(VAGUE) if rng.random() < 0.06 else rng.choice(TEXTS[mode])
            add(eq, "PM04" if emergency else "PM01", created, text, mode, down,
                round(cost_scale * rng.lognormal(0, 0.5), 2), round(down * rng.uniform(1.5, 3), 1))

        # Preventive plan: roughly every 2-4 weeks per machine, inspections monthly.
        interval = int(rng.integers(14, 30))
        for day in range(int(rng.integers(0, interval)), span_days, interval):
            created = t0 + pd.Timedelta(days=day, hours=7)
            add(eq, "PM02", created, rng.choice(PREVENTIVE), cost=round(cost_scale * 0.12 * rng.lognormal(0, 0.3), 2),
                hours=round(rng.uniform(2, 6), 1))
        for day in range(int(rng.integers(0, 30)), span_days, 30):
            if rng.random() < 0.7:
                add(eq, "PM03", t0 + pd.Timedelta(days=day, hours=9), rng.choice(INSPECTION),
                    cost=round(cost_scale * 0.04, 2), hours=round(rng.uniform(1, 3), 1))

    # A textbook recurring failure: the P-201 seal every ~3 weeks over the last quarter.
    p201 = next(e for e in EQUIPMENT if e[0] == "10001020")
    for i in range(5):
        created = t1 - pd.Timedelta(days=100 - i * 21, hours=-3)
        add(p201, "PM04", created, "fuite garniture mécanique - récidive", "seal", 6.5, 3100.0, 14.0)

    # The last day of the export, as seen in the next morning's operations meeting (J-1).
    eq = {e[0]: e for e in EQUIPMENT}
    last_day = t1 - pd.Timedelta(days=1)
    add(p201, "PM04", last_day + pd.Timedelta(hours=6, minutes=40), "fuite garniture mécanique - récidive",
        "seal", still_down=True, scripted=True)
    add(eq["10001030"], "PM04", last_day + pd.Timedelta(hours=14, minutes=10), "Bande déchirée", "belt", 3.5, 4200.0, 9.0, scripted=True)
    add(eq["10001001"], "PM01", last_day + pd.Timedelta(hours=9, minutes=20), "bourrage goulotte", "blockage", 1.5, 600.0, 3.0, scripted=True)
    add(eq["10001080"], "PM01", last_day + pd.Timedelta(hours=16, minutes=5), "Alarme température huile", "overheating",
        0.0, 350.0, 2.0, scripted=True)

    rows.sort(key=lambda r: r["created"])
    records = []
    for i, r in enumerate(rows):
        eq_id, desc, floc, *_ = r["eq"]
        created = r["created"].floor("min")
        failure = r["kind"] in ("PM01", "PM04")
        age_days = (t1 - created).days
        # Recent orders are still open; a few old ones were forgotten (backlog aging).
        if age_days < 10:
            status = rng.choice(["CRTD", "REL", "REL MANC"])
        elif age_days < 45:
            status = rng.choice(["REL", "TECO", "TECO", "CLSD"], p=[0.25, 0.35, 0.2, 0.2])
        else:
            status = "REL" if rng.random() < 0.03 else rng.choice(["TECO", "CLSD"])
        # Basic start date: corrective work is planned within days; preventive orders are
        # called ~10 days ahead of their due date.
        days_ahead = int(rng.integers(0, 4)) if failure else 10
        basic = (created + pd.Timedelta(days=days_ahead)).normalize()
        start = created if failure else pd.NaT
        end = start + pd.Timedelta(hours=r["down_h"]) if failure else pd.NaT
        if r["scripted"]:
            status = "REL"
            end = pd.NaT if r["still_down"] else end
        elif failure and age_days < 10 and status in ("CRTD", "REL", "REL MANC") and rng.random() < 0.2:
            end = pd.NaT  # repair still running
        if r["scripted"]:
            stop = r["still_down"] or r["down_h"] > 0
        else:
            stop = failure and (r["kind"] == "PM04" or rng.random() < 0.6)
        code = CODE_FOR[r["mode"]] if failure and r["mode"] and rng.random() < 0.3 else ""
        records.append({
            "Ordre": str(4000000 + i),
            "Type d'ordre": r["kind"],
            "Avis": str(10000000 + i) if failure else "",
            "Équipement": eq_id,
            "Désignation équipement": desc,
            "Poste technique": floc,
            "Description": r["text"],
            "Priorité": str(rng.choice([1, 2]) if r["kind"] == "PM04" else rng.choice([2, 3, 4])),
            "Date de création": created.strftime("%d.%m.%Y"),
            "Date de début de base": basic.strftime("%d.%m.%Y"),
            "Début panne": start.strftime("%d.%m.%Y %H:%M") if failure else "",
            "Fin panne": end.strftime("%d.%m.%Y %H:%M") if pd.notna(end) else "",
            "Arrêt machine": "X" if stop else "",
            "Statut système": status,
            "Coûts réels totaux": round(r["cost"], 2),
            "Poste de travail principal": WORK_CENTERS.get(r["mode"], "MECA-01") if failure else PREV_CENTERS[r["eq"][2][3:6]],
            "Code dommage": code,
            "Travail réel": r["hours"],
        })

    df = pd.DataFrame(records)
    # Realistic data-entry errors.
    bad = df.index[df["Fin panne"] != ""][:2]
    df.loc[bad[0], ["Début panne", "Fin panne"]] = df.loc[bad[0], ["Fin panne", "Début panne"]].values  # inverted dates
    df = pd.concat([df, df.iloc[[len(df) // 2]]], ignore_index=True)  # duplicated line
    return df


def write_sample(path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = generate()
    if path.suffix.lower() == ".csv":
        df.to_csv(path, sep=";", index=False, encoding="utf-8-sig")
    else:
        df.to_excel(path, index=False, sheet_name="Export IW39")
    return path


if __name__ == "__main__":
    print(write_sample(Path(__file__).resolve().parent.parent / "data" / "exemple_export_sap_pm.xlsx"))
