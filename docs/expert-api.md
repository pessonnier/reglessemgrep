# API expert et association manuelle

L’API est disponible sur le serveur local de l’application. Remplacer le port 8765 ci-dessous si nécessaire. La documentation interactive est accessible à `/docs#/Expert` et le contrat OpenAPI à `/openapi.json`.

Cette version est destinée à un usage local sur `127.0.0.1`. Elle n’implémente pas d’authentification : `reviewer` est le nom déclaré de l’auteur, pas une identité vérifiée. Les identifiants `CAST_USERNAME` et `CAST_PASSWORD` servent uniquement à la collecte CAST, pas à cette API. Une exposition à d’autres utilisateurs nécessite une couche d’authentification et de contrôle d’accès.

## Ressources

| Méthode | Chemin | Usage |
| --- | --- | --- |
| GET | `/api/expert/rules` | Rechercher les règles présentes : `source=CAST` ou `Semgrep`, `q`, `language`, `category`, `cwe`, `severity`, pagination et filtres d’incertitude. |
| GET | `/api/expert/rule?key=…` | Lire toute la fiche, le contenu original archivé localement et l’historique d’incertitude. |
| GET | `/api/expert/correspondences` | Règles CAST avec candidats, compteurs et dernières décisions. Filtres `q`, `language`, `cwe`, `status`. |
| GET | `/api/expert/semgrep-unmatched` | Règles Semgrep sans paire liée à une règle CAST présente. Filtres `q`, `language`, `cwe`. |
| GET | `/api/expert/comparison?cast_key=…&semgrep_key=…` | Comparer deux fiches complètes sans écrire ; inclut association éventuelle, références sourcées, propositions LLM et historique des avis. |
| POST | `/api/expert/associations` | Créer ou conserver une association manuelle. Corps : `cast_key`, `semgrep_key`. |
| POST | `/api/expert/reviews` | Ajouter un avis expert à une paire existante, avec exemples de code facultatifs. |
| GET | `/api/expert/reviews` | Lire les avis du plus récent au plus ancien ; filtres exacts `cast_key`, `semgrep_key`, `reviewer`. |
| POST | `/api/expert/uncertainty-assessments` | Ajouter l’évaluation de l’incertitude et des risques d’une règle Semgrep. |

Les listes acceptent `page` (à partir de 1) et `page_size` (1 à 100), et renvoient `total`, `page`, `page_size`, `items`. La pagination des correspondances porte sur les règles CAST, avec au plus trois paires en aperçu par règle. `/api/matches?key=…&limit=…&offset=…` donne toutes ses paires.

`rule_key` est la clé opaque renvoyée par le catalogue : ne pas la reconstruire à partir de l’intitulé. Les paramètres URL doivent être encodés. Une règle retirée reste lisible pour l’historique mais ne peut plus faire l’objet d’une nouvelle association manuelle.

## Exemple de parcours

Rechercher puis copier les `rule_key` des deux règles choisies :

```bash
curl --get 'http://127.0.0.1:8765/api/expert/rules' \
  --data-urlencode 'source=CAST' --data-urlencode 'q=SQL injection'
curl --get 'http://127.0.0.1:8765/api/expert/rules' \
  --data-urlencode 'source=Semgrep' --data-urlencode 'q=sql-injection'

# Remplacer ces clés d’exemple par celles du catalogue.
curl --get 'http://127.0.0.1:8765/api/expert/comparison' \
  --data-urlencode 'cast_key=CAST:EXEMPLE' \
  --data-urlencode 'semgrep_key=Semgrep:EXEMPLE'
```

La lecture ne crée rien. Si la paire n’existe pas, `candidate` vaut `null`. Les contenus manquants restent indiqués comme tels ; la lecture ne déclenche pas une collecte distante.

Créer `association.json` :

```json
{"cast_key":"CAST:EXEMPLE","semgrep_key":"Semgrep:EXEMPLE"}
```

Puis :

```bash
curl 'http://127.0.0.1:8765/api/expert/associations' \
  -H 'Content-Type: application/json' --data-binary @association.json
```

Cette écriture est idempotente : une paire existante conserve son score, ses preuves et ses avis. Son origine manuelle est enregistrée dans `candidate.factors.manual_association` et `manually_associated_at`. Le recalcul automatique conserve le lien manuel, même sans avis. Une association n’est ni une preuve sourcée ni une décision d’équivalence.

Créer `avis.json` :

```json
{
  "cast_key": "CAST:EXEMPLE",
  "semgrep_key": "Semgrep:EXEMPLE",
  "reviewer": "Nom de l’expert",
  "decision": "partial",
  "comment": "Préciser le principe commun, le périmètre et les différences observées.",
  "code_examples": [{
    "title": "Cas à examiner",
    "language": "python",
    "kind": "boundary",
    "code": "def example(value):\n    return value\n",
    "explanation": "Illustration de format uniquement ; indiquer ici le comportement attendu."
  }]
}
```

```bash
curl 'http://127.0.0.1:8765/api/expert/reviews' \
  -H 'Content-Type: application/json' --data-binary @avis.json
curl --get 'http://127.0.0.1:8765/api/expert/reviews' \
  --data-urlencode 'cast_key=CAST:EXEMPLE' \
  --data-urlencode 'semgrep_key=Semgrep:EXEMPLE'
```

Décisions acceptées : `equivalent`, `partial`, `complementary`, `related`, `no_match`, `indeterminate`, `not_comparable`. Chaque POST ajoute un avis historisé ; il ne remplace pas les précédents. Un nouvel avis corrige le précédent et devient la décision courante. Réessayer un POST d’avis après un résultat réseau ambigu peut créer un doublon : consulter l’historique avant de répéter l’écriture.

Les exemples acceptent `kind=vulnerable|safe|boundary|other`, au plus 10 exemples de 20 000 caractères chacun. Les retours à la ligne sont conservés. Ils ne sont pas exécutés et ne constituent pas un résultat de scan.

Pour l’incertitude, transmettre `rule_key`, `source_version`, `definition_hash` obtenus dans la fiche, `reviewer`, `uncertainty_level`, `false_positive_risk`, `false_negative_risk`, `scope`, `rationale`, et éventuellement `evidence` et `code_examples`. Les trois niveaux acceptent `unknown|low|medium|high`. L’historique se relit dans `/api/expert/rule` ; un changement de version ou de définition rend l’ancien avis obsolète.

## Réponses et erreurs

- 200 : lecture ou association réussie ; 201 : nouvel avis ou nouvelle évaluation d’incertitude via l’API expert.
- 404 : règle ou paire inexistante. Associer avant de rédiger un avis de paire.
- 409 : règle retirée lors de l’association, ou version/empreinte d’incertitude périmée. Relire la fiche.
- 422 : corps, paramètres, sources ou décision invalides.

Les anciennes routes `/api/rules`, `/api/rule`, `/api/candidates`, `/api/reviews` et `/api/uncertainty-assessments` restent compatibles et utilisent les mêmes validations et données. L’API expert ne confond jamais avis, contenu des catalogues et analyses LLM.
