# Guide d'export SAP PM

Comment sortir de SAP PM les données que SAP PM Analyst sait lire.

## Quelle transaction utiliser ?

| Transaction | Usage dans SAP PM Analyst | Pris en charge |
|---|---|---|
| **IW39** / IW38 | Liste des ordres de travail : export principal (historique + backlog) | ✅ |
| **IW29** / IW28 | Liste des avis : arrêts machine (début / fin de panne) | ✅ |
| **ZGMT_IW29** | Interventions de J-1 (réunion opérationnelle) : onglet « Réunion J-1 » | ✅ |
| IW49N | Ordres et opérations : analyse de charge par poste de travail | Prochaine version |
| IK17 | Documents de mesure (compteurs, températures, vibrations) | Prochaine version |
| IP24 / ZGMT_IP24 | Dates d'entretien : respect du plan préventif | Prochaine version |
| IH08 / IE07 | Liste des équipements : criticité, données de référence | Prochaine version |

## Export IW39 pas à pas

1. Saisir `/nIW39` dans le champ de commande, ou suivre le menu
   *Logistique → Maintenance → Traitement de la maintenance → Ordre → Liste d'ordres → IW39 – Afficher*.
2. **Statut des ordres** :
   * backlog et ordres en retard : cocher **En instance** (*Outstanding*) et **En cours** (*In process*) ;
   * analyse de fiabilité (MTBF, MTTR, pannes récurrentes) : cocher aussi **Terminés** et **Historiques**, sur au moins 6 à 12 mois.
3. **Poste de travail principal** (*Main work center*) : saisir le code du poste, ou utiliser le joker `*`.
   Exemple : `MECA*` affiche tous les postes commençant par MECA. Le même filtre existe dans SAP PM Analyst
   (*Paramètres d'analyse → Postes de travail*).
4. **Période** : indiquer les dates de début et de fin.
5. **Exécuter** (F8).
6. Dans la liste, ajouter si besoin les colonnes utiles via *Choisir la mise en page* :
   Ordre, Type d'ordre, Avis, Équipement, Désignation, Poste technique, Description, Priorité, Date de création,
   **Date de début de base** (*Bsc start*), Début / Fin de panne, Arrêt machine, Statut système, Coûts réels,
   **Poste de travail principal**, Code dommage.
7. **Exporter** : *Liste → Exporter → Tableur* (ou l'icône Excel), puis déposer le fichier dans SAP PM Analyst.

> **Ordres en retard** : comme dans IW39, un ordre ouvert est « en retard » quand sa **date de début de base**
> (*Bsc start date*) est dépassée. SAP PM Analyst les compte par poste de travail principal (onglet *Backlog*).

## Ce qui est obligatoire

Seuls trois éléments sont indispensables : un **n° d'ordre ou d'avis**, l'**équipement**, et **une date**
(création, début de base ou début de panne). Toutes les autres colonnes enrichissent l'analyse. Les en-têtes
en français, en anglais ou en codes techniques SAP (`AUFNR`, `EQUNR`, `GSTRP`, `AUSVN`…) sont reconnus.

## Référence : codes transaction SAP PM du site

### Données de référence

| Code | Transaction |
|---|---|
| `MM01` | Créer un article |
| `MM02` | Modifier un article |
| `MM03` | Afficher un article |
| `IE01` | Créer un équipement/sous-équipement |
| `IE02` | Modifier un équipement/sous-équipement |
| `IE03` | Afficher un équipement/sous-équipement |
| `IL01` | Créer un poste technique |
| `IL02` | Modifier un poste technique |
| `IL03` | Afficher un poste technique |
| `IR01` | Créer un poste de travail |
| `IR02` | Modifier un poste de travail |
| `IR03` | Afficher un poste de travail |
| `IK01` | Créer un point de mesure |
| `IK02` | Modifier un point de mesure |
| `IK03` | Afficher un point de mesure |
| `IK11` | Créer un document de mesure |
| `IK12` | Modifier un document de mesure |
| `IK13` | Afficher un document de mesure |
| `IB01` | Créer une nomenclature d’équipement |
| `IB02` | Modifier une nomenclature d’équipement |
| `IB03` | Afficher une nomenclature d’équipement |
| `CS01` | Créer une nomenclature d’article |
| `CS02` | Modifier une nomenclature d’article |
| `CS03` | Afficher une nomenclature d’article |
| `IA01` | Créer une gamme d’équipement |
| `IA02` | Modifier une gamme d’équipement |
| `IA03` | Afficher une gamme d’équipement |
| `IA05` | Créer une instruction de maintenance |
| `IA06` | Modifier une instruction de maintenance |
| `IA07` | Afficher une instruction de maintenance |

### Maintenance préventive

| Code | Transaction |
|---|---|
| `IP41` | Plan d’entretien avec cycle individuel |
| `IP02` | Plan d’entretien avec cycle individuel (modif.) |
| `IP03` | Plan d’entretien avec cycle individuel (affichage) |
| `IP42` | Plan d’entretien avec stratégie |
| `IP43` | Plan d’entretien avec plusieurs cycles |
| `IP10` | Ordonnancer un plan d’entretien |
| `IP11` | Gérer les stratégies d’entretien |

### Gestion de la maintenance

| Code | Transaction |
|---|---|
| `IW21` | Créer un avis |
| `IW22` | Modifier un avis |
| `IW23` | Afficher un avis |
| `IW31` | Créer un ordre de travail |
| `IW32` | Modification d’un ordre de travail |
| `IW33` | Afficher un ordre de travail |

### Reporting

| Code | Transaction |
|---|---|
| `IL07` | Liste des postes techniques |
| `IH08` | Liste des équipements |
| `IK07` | Liste des points de mesure (compteurs) |
| `IK17` | Liste des documents de mesure |
| `IP15` | Liste des plans d’entretien (modification) |
| `IP16` | Liste des plans d’entretien (affichage) |
| `IP24` | Liste des dates d’entretien |
| `IW28` | Liste des avis (modification) |
| `IW29` | Liste des avis (affichage) |
| `IW38` | Liste des ordres de travail (modification) |
| `IW39` | Liste des ordres de travail (affichage) |
| `IW49N` | Liste des ordres de travail et opérations |
| `IE07` | Liste des équipements |
| `IA10` | Liste des gammes |
| `CS12` | Liste des nomenclatures |
| `IW30` | Liste des avis |
| `IW40` | Liste des ordres de travail |

### Représentations et graphiques

| Code | Transaction |
|---|---|
| `IH01` | Représentation de structure (par poste technique) |
| `IH03` | Représentation de structure (par équipement) |
| `IP19` | Simulation des dates d’entretien |
| `CM33` | Répartition des charges de postes de travail |

### Menus et cas d’emploi

| Code | Transaction |
|---|---|
| `CS14` | Comparaison de nomenclatures |
| `CS15` | Cas d’emploi d’article dans une nomenclature |
| `IP62` | Cas d’emploi d’article dans une gamme |
| `IW13` | Cas d’emploi d’article dans ordre/avis |
| `CM01` | Analyse de la charge/capacité par poste de travail |
| `IW12` | Flux de documents |
| `IP00` | Menu de maintenance préventive |
| `IW00` | Menu de gestion de la maintenance |
| `IR00` | Menu de gestion des postes de travail |
| `IA00` | Menu de gestion des gammes |
| `IE00` | Menu de gestion des équipements |

### Transactions spécifiques

| Code | Transaction |
|---|---|
| `ZGMT_IW29` | Affichage des interventions pour J-1 (transaction pour la réunion opérationnelle) |
| `ZGMT_IP24` | Affichage des dates d’entretien (en traitement de liste) |
| `ZGMT_CM01` | Analyse de la charge/capacité par poste de travail |
| `ZGMT_IP15` | Liste des plans d’entretien (traitement de liste en modification) |
