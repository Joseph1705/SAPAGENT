# Changelog

## v0.2.0 — OpenRouter, réunion J-1, ordres en retard

### Nouveautés
- **OpenRouter** : en plus de Claude (Anthropic), l'IA peut utiliser n'importe quel modèle OpenRouter
  (Claude, GPT, Gemini, Mistral, Llama…) avec une seule clé `OPENROUTER_API_KEY`. L'application liste les
  modèles compatibles avec les sorties JSON structurées ; repli automatique en mode JSON simple pour les autres.
- **Onglet « Réunion J-1 »** (cf. transaction `ZGMT_IW29`) : interventions de la veille, pannes, arrêts,
  équipements toujours à l'arrêt, récidives connues signalées. Fiche Excel d'une page à imprimer
  (`--j1` en ligne de commande).
- **Ordres en retard par poste de travail principal** (cf. IW39) : un ordre ouvert est en retard quand sa
  date de début de base (*Bsc start*) est dépassée. Nouveau tableau dans l'onglet « Backlog & retards »
  et dans le rapport Excel.
- **Filtre poste de travail avec joker**, comme dans SAP : `MECA*`, `HCNE*, HCSE*` (barre latérale ou
  `--work-centers`).
- **Exports d'avis** (IW29 / IW28 / ZGMT_IW29) acceptés sans n° d'ordre ; types d'avis `M1` / `M2` / `M3`
  reconnus. Nouveaux en-têtes reconnus : `GSTRP` / *Bsc start*, `QMART`, `QMNUM`, *Main WorkCtr*…
- **Guide d'export SAP** (`docs/GUIDE_EXPORT_SAP.md`) : IW39 pas à pas, transactions utiles,
  liste des 79 codes transaction SAP PM du site. Également résumé dans l'application.

### Améliorations
- Recommandation « revue hebdomadaire des ordres en retard » ciblée sur les postes de travail les plus en retard.
- Les données de démonstration incluent dates de début de base, postes de travail par zone et un scénario
  de la veille (pompe P-201 toujours à l'arrêt, bande CV-03 déchirée).
- 25 tests automatisés (contre 15), dont les appels OpenRouter simulés.

## v0.1.0 — Première version

- Lecture des exports SAP PM (IW39 / IW29, CSV ou Excel), reconnaissance des colonnes FR / EN / codes techniques.
- Indicateurs : pannes, heures d'arrêt, MTTR, MTBF, disponibilité, coûts, part de travail planifié, backlog.
- Classification des textes libres en modes de défaillance (code dommage SAP, mots-clés, IA Claude en option).
- Pareto, pannes récurrentes, tendances mensuelles, score de qualité des données.
- Recommandations priorisées (règles ou IA).
- Rapport Excel de 9 onglets avec formules traçables ; application web Streamlit ; ligne de commande.
