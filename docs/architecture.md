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

