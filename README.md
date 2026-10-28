# CAST–Semgrep Rules Comparator

Application locale pour inventorier les règles CAST et Semgrep Community Edition, rechercher des candidats de rapprochement et consigner un avis expert. Les scores servent à ordonner les candidats : ils ne prouvent pas une équivalence technique.

## Démarrage sans conteneur

Prérequis : Python 3.12+, `uv` et Git. L’application utilise SQLite localement. Aucun service de base de données, Docker ou Docker Compose n’est nécessaire.

```bash
uv sync
cp .env.example .env
chmod 600 .env
uv run comparator init
uv run comparator sync-semgrep
uv run comparator sync-cast
uv run comparator match
uv run comparator serve
```

Ouvrir <http://127.0.0.1:8000>. Les commandes peuvent être relancées ; les données brutes déjà archivées sont réutilisées par défaut. `sync-cast --refresh` démarre une nouvelle collecte ; `sync-semgrep --refresh` récupère la révision distante actuelle. `import-cast`, `import-semgrep` et les options `--offline` utilisent les données locales sans réseau.

## Accès CAST

Renseigner `CAST_USERNAME` et `CAST_PASSWORD` dans `.env` à la racine du projet. Le fichier est ignoré par Git. Les variables d’environnement du processus prennent priorité sur `.env`.

Si l’un des deux paramètres manque ou si la connexion échoue, le collecteur utilise les informations publiquement accessibles et signale les limites dans le manifeste d’archive. Le mot de passe et la session ne sont ni journalisés ni archivés. L’API JSON actuelle de CAST est utilisée via HTTPS ; ses routes peuvent changer.

## Archives et base

- `data/raw/cast/<date>-authenticated/` ou `-public/` : index, détails JSON par règle, manifeste de complétude.
- `data/raw/semgrep/repo/` : dépôt Git Semgrep, conservé au commit importé ; `data/raw/semgrep/import-report.json` décrit les éventuels fichiers ignorés ou invalides.
- `data/comparator.sqlite3` : inventaires normalisés, candidats, preuves sourcées, propositions LLM éventuelles et avis experts.

Le dossier `data/raw/` et la base sont exclus de Git. En particulier, les définitions Semgrep sont soumises à la [Semgrep Rules License](https://semgrep.dev/legal/rules-license/) : ne pas publier l’archive. Les exports CSV de l’application contiennent des métadonnées et des liens, sans définition complète des règles.

## Commandes utiles

```bash
uv run comparator status
uv run comparator import-cast
uv run comparator import-semgrep
uv run comparator match --top-k 15 --min-score 18
uv run comparator serve --host 127.0.0.1 --port 8000
uv run python -m unittest discover -s tests -v
```

L’interface propose la recherche et des filtres combinables, les fiches des règles, les liens originaux, les comparaisons côte à côte, la création manuelle d’une paire et l’historique des avis experts. La section « Références sourcées » conserve les extraits et liens des catalogues ; la section « Propositions LLM » est distincte et reste vide tant que cette fonction facultative n’est pas ajoutée.

## Documentation

- [Architecture](docs/architecture.md)
- [Sources et limites de collecte](docs/data-sources.md)
- [Méthode de rapprochement](docs/matching-methodology.md)
- [Références et normes](docs/reference/README.md)
- [Spécification initiale](docs/specification-v1.md)

## Incertitude et validation des principes

Chaque règle Semgrep affiche l’incertitude de son évaluation, le risque estimé de faux positifs et le risque estimé de non-détection. Sans avis, l’incertitude est **élevée** et les deux risques **non évalués**. Il ne s’agit pas de probabilités mesurées. La confiance fournie dans les métadonnées Semgrep est affichée séparément.

Dans la fiche Semgrep, ouvrir **Enregistrer une évaluation experte de cette règle**, renseigner le périmètre et la justification, puis enregistrer. Les avis sont historisés et liés à la version/empreinte de la règle. Un changement rend l’avis « à réévaluer ». Le catalogue propose des filtres sur ces valeurs et les exports CSV les conservent.

Pour une installation P0 existante, arrêter le serveur, sauvegarder SQLite, puis lancer la réimportation locale et redémarrer :

```bash
uv run comparator import-semgrep
uv run comparator serve
```

La migration conserve les règles, rapprochements et avis existants. Aucune nouvelle collecte CAST ou Semgrep n’est nécessaire.

La [spécification v2 et son planning S6](docs/specification-v2-validation.md) prévoit les contrats de détection, **les exemples de code avec et sans vulnérabilité (S6.2)**, l’exécution des analyseurs et la mesure des faux positifs/non-détections. Un [modèle de dossier de validation](docs/templates/validation-case.md) est fourni. Les tests de détection et la confrontation au moteur CAST restent à implémenter ; les avis actuels sont qualitatifs.
