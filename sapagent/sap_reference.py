"""SAP PM transactions relevant to this tool, from the site's transaction-code list.

Only the transactions whose output can feed the analysis are listed here; the
full list (79 codes) is in docs/GUIDE_EXPORT_SAP.md.
"""

# (code, description, what to export / why it matters to the tool, supported today?)
EXPORT_TRANSACTIONS = [
    ("IW39", "Liste des ordres de travail (affichage)",
     "Export principal : historique des ordres (correctifs, préventifs). Cocher En cours, En instance, Terminés et "
     "Historiques pour calculer MTBF / MTTR ; En instance + En cours suffisent pour le backlog.", True),
    ("IW38", "Liste des ordres de travail (modification)", "Même liste que IW39, en mode modification.", True),
    ("IW29", "Liste des avis (affichage)",
     "Avis de panne (M2) avec début / fin de panne et arrêt machine : la meilleure source pour les arrêts.", True),
    ("IW28", "Liste des avis (modification)", "Même liste que IW29, en mode modification.", True),
    ("ZGMT_IW29", "Interventions de J-1 (réunion opérationnelle) — transaction spécifique du site",
     "Export de la veille : alimente l'onglet « Réunion J-1 ».", True),
    ("IW49N", "Liste des ordres de travail et opérations",
     "Détail par opération (heures, postes de travail) : prochaine étape pour l'analyse de charge.", False),
    ("IK17", "Liste des documents de mesure",
     "Relevés de compteurs et mesures (températures, vibrations, heures moteur) : base d'une future maintenance conditionnelle.", False),
    ("IP24 / ZGMT_IP24", "Liste des dates d'entretien",
     "Dates prévues du préventif : permettra de mesurer le respect du plan (réalisé à temps / en retard).", False),
    ("IH08 / IE07", "Liste des équipements",
     "Données de référence (criticité, fabricant, date de mise en service) pour enrichir l'analyse par équipement.", False),
]

IW39_STEPS = [
    "Saisir /nIW39 dans le champ de commande (ou Logistique → Maintenance → Traitement → Ordre → Liste d'ordres → Afficher).",
    "Statut des ordres : cocher « En instance » et « En cours » (backlog) — ajouter « Terminés » et « Historiques » pour l'analyse de fiabilité.",
    "Poste de travail principal : code du poste, ou un joker, ex. MECA* pour tous les postes commençant par MECA.",
    "Période : indiquer les dates de début et de fin.",
    "Exécuter (F8). Dans la liste, ajouter si besoin les colonnes utiles via « Choisir la mise en page ».",
    "Exporter : Liste → Exporter → Tableur (ou icône Excel), puis déposer le fichier dans SAP PM Analyst.",
]

USEFUL_COLUMNS = (
    "Ordre, Type d'ordre, Avis, Équipement, Désignation, Poste technique, Description, Priorité, Date de création, "
    "Date de début de base, Début / Fin de panne, Arrêt machine, Statut système, Coûts réels, Poste de travail "
    "principal, Code dommage."
)
