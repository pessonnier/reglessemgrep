# CAST–Semgrep Rules Comparator

Application locale pour montrer quelles règles Semgrep correspondent aux règles CAST. L’accueil présente chaque règle CAST face à ses candidats Semgrep, avec accès à la comparaison des principes et aux avis experts. Les scores servent à ordonner les candidats : ils ne prouvent pas une équivalence technique.

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
## Parcours principal CAST → Semgrep

L’accueil affiche les règles CAST et leurs candidats Semgrep côte à côte. Toutes les règles CAST présentes sont incluses, même sans candidat. Les paires ayant un avis expert « équivalent » sont distinguées des propositions automatiques. Trois paires sont présentées par règle ; ouvrir la fiche CAST donne accès à toutes les paires, avec chargement de la suite si nécessaire.

La recherche porte sur l’identifiant/intitulé CAST ou Semgrep (et la description CAST). Les filtres permettent de consulter les règles avec candidats, sans candidat identifié ou avec un avis expert d’équivalence. Les compteurs dénombrent des règles CAST, pas des paires, et précèdent le filtre de correspondance. L’absence de candidat ne démontre pas une absence de couverture.

L’explorateur général s’ouvre sur CAST ; la liste déroulante « Éditeur » sélectionne CAST, Semgrep ou les deux catalogues. Les filtres d’incertitude sont visibles uniquement pour Semgrep et sont effacés lors d’un changement d’éditeur. Le bouton Réinitialiser permet de retrouver le catalogue complet de l’éditeur sélectionné.

## Pages et exemples de code des experts

Le menu et le lien de l’explorateur ouvrent la page [CAST → Semgrep](http://127.0.0.1:8000/correspondances). Les chemins `/correspondances`, `/regles` et `/statistiques` sont accessibles directement et peuvent être enregistrés dans les favoris (adapter le port au serveur lancé).

Dans un avis expert sur une paire, ou dans une évaluation d’incertitude Semgrep, cliquer sur **Ajouter un exemple de code**. Chaque exemple possède un titre facultatif, un langage, un type (vulnérable, corrigé, limite ou autre), le code et une explication du résultat attendu. Jusqu’à 10 exemples de 20 000 caractères chacun peuvent accompagner un avis. Les retours à la ligne et l’indentation sont conservés.

Le code est stocké dans SQLite avec l’avis et reste consultable dans l’historique. Il est affiché comme texte et n’est jamais exécuté. Ces illustrations ne constituent pas des résultats d’analyse ni le corpus de validation automatisé prévu en S6.2. La migration v5 ajoute ce stockage en conservant les avis existants.

## Association manuelle et API expert

La page `/correspondances` présente aussi les **règles Semgrep sans candidat CAST**, avec filtres et pagination indépendants. Le menu **Associer deux règles** ouvre `/association` : choisir une règle de chaque catalogue, afficher leurs fiches et archives complètes, puis enregistrer le lien et l’avis expert habituel. Les associations manuelles sont conservées lors du recalcul des candidats.

L’[API expert](docs/expert-api.md) permet le même parcours en lecture et écriture sous `/api/expert/`. Son contrat interactif est disponible dans `/docs#/Expert`. Les avis et exemples restent historisés ; le nom d’expert est déclaratif dans cette application locale sans authentification.

## Générer le modèle de la base en Mermaid

```bash
# Schéma de la base configurée par COMPARATOR_DB, ouvert en lecture seule.
uv run comparator schema-mermaid --output docs/database-schema.mmd

# Version Markdown rendue par GitHub et les lecteurs compatibles Mermaid.
uv run comparator schema-mermaid --format markdown --output docs/database-schema.md

# Sans données locales : reconstruire uniquement le schéma en mémoire.
uv run comparator schema-mermaid --from-migrations --output docs/database-schema.mmd
```

Le [modèle généré](docs/database-schema.md) représente les tables, colonnes, types, clés primaires/étrangères, unicités simples et relations composites. La vue `rule_uncertainty` est incluse et identifiée comme vue ; `--tables-only` l’exclut. `--database chemin.sqlite3` permet de choisir une autre base. Sans `--output`, le résultat est écrit sur la sortie standard.

Le générateur utilise uniquement les métadonnées SQLite et ne lit pas les enregistrements. Il ne migre ni ne modifie une base existante. Les dépendances des vues et les relations logiques sans contrainte SQL ne sont pas inventées. Les champs JSON restent des colonnes TEXT. La sortie est déterministe pour faciliter sa mise à jour et son historique dans Git.

## Critères de jointure CAST ↔ Semgrep et références OWASP

Les règles sont recherchées par CWE commun, référence OWASP commune ou termes communs du titre, puis écartées si leurs langages connus sont incompatibles (avec normalisation des alias, par exemple JEE → Java). La jointure OWASP utilise la même **famille, catégorie et édition** : `A03-2021` côté CAST et `A03:2021 - Injection` côté Semgrep deviennent tous deux `A03:2021` ; casse, espaces, zéros initiaux et tirets typographiques sont normalisés, sans confondre `A03:2017`, `A03:2021` et `API03:2023`. Les références sans année ne sont pas jointes et les valeurs originales restent conservées comme sources. Le score additionne langage (15 points), références (30 pour un CWE commun et 10 pour OWASP, plafonnés ensemble à 35), proximité du titre (20), de la description (20) et catégorie compatible (10). Les références OWASP multiples ne cumulent pas les bonus. Pour retenir une paire, il faut un CWE commun, ou OWASP accompagné d’un terme distinctif du titre et de deux termes descriptifs communs, ou deux termes du titre communs ; il faut aussi atteindre 18/100 et figurer parmi les 15 meilleurs candidats par règle CAST par défaut. Les paires manuelles, revues par un expert ou accompagnées d’une proposition LLM sont conservées. Une catégorie OWASP commune est un indice de similarité, jamais une preuve d’équivalence ; seul l’avis expert qualifie la correspondance. Voir la [méthode détaillée](docs/matching-methodology.md).

Pour recalculer à partir des données locales et obtenir le bilan des nouvelles paires et règles reliées :

```bash
uv run comparator match --top-k 15 --min-score 18
```

Bilan du recalcul du **29 octobre 2026** sur le même inventaire : **0 nouvelle paire, 0 règle CAST et 0 règle Semgrep nouvellement reliée** ; 4 516 paires sont conservées, dont 3 139 partagent une référence OWASP. La conversion tiret/deux-points et le bonus OWASP existaient déjà. Le renforcement normalise 172 fiches CAST Mobile sans créer de correspondance supplémentaire dans ce catalogue. Voir le [bilan avant/après](docs/reports/owasp-join-2026-10-29.md).

## Base sémantique multi-modèles

La migration v6 ajoute un stockage local des embeddings à SQLite. `semantic_documents` conserve les versions du titre et de la description ; `semantic_models` décrit chaque fournisseur, modèle, révision et dimension ; `semantic_embeddings` contient les colonnes **`title_vector_json`** et **`description_vector_json`**, avec une ligne par règle, version de texte et modèle. Plusieurs modèles peuvent coexister sans ajout de colonnes. Les imports actualisent les documents, les anciens vecteurs restent historisés et les écritures sur un texte périmé sont rejetées. `uv run comparator semantic-status` affiche la couverture ; `uv run comparator semantic-sync` prépare les documents sans calcul distant. L’API `/api/semantic/` permet de lire les textes et d’insérer les vecteurs. Aucun vecteur n’est encore calculé automatiquement et le score de rapprochement reste inchangé. Voir la [structure et les exemples d’insertion](docs/semantic-database.md).
