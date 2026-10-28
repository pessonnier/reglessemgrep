# Architecture

Le projet est une application locale en Python. `FastAPI` expose l’API et sert une interface HTML/CSS/JavaScript sans étape de compilation. SQLite conserve les inventaires et les décisions. Ce choix évite une dépendance à un serveur de base et convient à l’exploration de quelques milliers de règles sur un poste ; la volumétrie et la concurrence devront être mesurées avant un déploiement multi-utilisateur.

## Modules

- `config.py` : lit les variables d’environnement et `.env` local.
- `cast.py` : connexion CAST facultative, collecte JSON avec débit limité, archivage et normalisation.
- `semgrep.py` : dépôt Git local, parsing YAML, rapport d’import et normalisation.
- `db.py` : schéma relationnel et provenance des snapshots.
- `matching.py` : présélection et score déterministes, preuves sourcées.
- `api.py` et `static/` : consultation, exports de métadonnées, comparaison et revue humaine.
- `cli.py` : commandes d’import, de calcul et de lancement.

Les données brutes restent dans `data/raw/` ; `rules` contient des champs normalisés, des listes de catégories/langages/référentiels et un chemin vers chaque source brute. Les migrations SQL sont versionnées dans `src/cast_semgrep/migrations/`. `snapshots` enregistre les versions, dates et statistiques de collecte. Une réimportation partielle n’indique pas qu’une règle absente a été supprimée.

`match_candidates` stocke le classement automatique, `match_evidence` les références à CAST ou Semgrep, `llm_proposals` les propositions facultatives de modèles de langage et `expert_reviews` l’historique append-only des décisions humaines. Un recalcul des candidats conserve les paires revues par un expert.

## Sécurité des secrets et contenus

Le fichier `.env`, les archives, le dépôt Semgrep téléchargé et SQLite sont ignorés par Git. L’authentification CAST utilise HTTPS et garde le cookie uniquement en mémoire. Le serveur écoute `127.0.0.1` par défaut. L’application n’envoie aucune donnée à un fournisseur LLM.

## Incertitude des règles Semgrep (schéma v4)

`uncertainty_assessments` conserve les avis successifs par règle avec auteur, périmètre, justification, références déclarées, niveau d’incertitude et risques FP/FN. L’import calcule `definition_hash` (SHA-256 de l’objet YAML normalisé en JSON canonique) et conserve `source_confidence` séparément. La vue SQL `rule_uncertainty` sélectionne le dernier avis et vérifie sa version/empreinte ; les vues, filtres et exports partagent cette interprétation via `uncertainty.py`. Une révision différente invalide prudemment l’avis même si la définition reste identique.

`POST /api/uncertainty-assessments` ajoute un avis ; la vérification de version et l’insertion sont dans une transaction SQLite immédiate. Un avis obsolète reçoit HTTP 409. Les listes/fiches/comparaisons exposent `uncertainty`, les fiches ajoutent `uncertainty_history`. Les filtres supplémentaires sont `uncertainty_level`, `assessment_status`, `false_positive_risk` et `false_negative_risk`.

La migration v3→v4 conserve les données et produit un état initial non évalué. Après mise à jour, lancer `comparator import-semgrep` pour enrichir les règles existantes à partir de l’archive locale. Les migrations ont lieu à l’initialisation ; effectuer la migration avant de démarrer le serveur. Les avis reposent sur un nom saisi, sans authentification multi-utilisateur. Le service reste destiné à une utilisation locale.
## Vue principale des correspondances

`correspondences.py` et `GET /api/correspondences` regroupent les paires par règle CAST. Les règles sans candidat sont conservées. Seules les règles présentes des deux catalogues entrent dans les paires et compteurs ; la dernière décision experte détermine le filtre d’équivalence. La pagination porte sur les règles CAST, avec un aperçu de trois paires par règle. La fiche charge toutes les paires via `GET /api/matches?key=…&offset=…`.

La navigation distingue la vue CAST → Semgrep, l’explorateur et les statistiques. Le retour d’une comparaison conserve la liste et les filtres d’origine. Les filtres d’incertitude sont réservés au catalogue Semgrep côté interface ; l’API ignore ces filtres si `source=CAST`, pour ne pas masquer CAST avec un filtre incompatible.
