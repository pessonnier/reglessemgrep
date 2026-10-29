# Stockage sémantique des règles CAST et Semgrep

Le stockage sémantique est intégré à la base SQLite configurée par `COMPARATOR_DB`, normalement `data/comparator.sqlite3`. Il conserve les textes et vecteurs localement avec les règles, sans serveur supplémentaire. La migration v6 prépare les documents de toutes les règles présentes. Elle conserve les associations, avis et exemples existants.

## Structure multi-modèles

| Table | Contenu |
| --- | --- |
| `semantic_models` | Clé du modèle, fournisseur, nom, révision, dimension et protocole de préparation du texte. |
| `semantic_documents` | Versions exactes du titre et de la description, indicateurs de texte non vide et empreinte SHA-256 combinée. |
| `semantic_embeddings` | Vecteurs des deux champs, associés à une règle, une empreinte de texte et un modèle. |

Les colonnes `title_vector_json` et `description_vector_json` contiennent des tableaux JSON de nombres. Une ligne est identifiée par **`(rule_key, content_hash, model_key)`**. Une même règle possède donc autant de jeux de vecteurs que de modèles enregistrés, avec des dimensions différentes si nécessaire. Ajouter un modèle ne nécessite pas de modification du schéma. Les vecteurs de modèles distincts ne doivent pas être mélangés ou comparés comme s’ils appartenaient au même espace.

Les vues `semantic_current_documents` et `semantic_coverage` indiquent les versions actives et la couverture de chaque modèle : `pending`, `partial`, `complete`, `stale`, `not_applicable`.

Le schéma est disponible en [Mermaid](database-schema.mmd) et [Markdown](database-schema.md).

## Actualisation

Les imports CAST et Semgrep enregistrent automatiquement les textes nouveaux ou modifiés. Un changement de titre ou de description produit une nouvelle empreinte ; les vecteurs anciens restent consultables dans l’historique et ne sont plus présentés comme courants. Un changement de sévérité ou de version du catalogue sans modification des textes réutilise les vecteurs existants. Une règle retirée quitte les documents courants, mais conserve son historique.

Les champs vides ou composés uniquement d’espaces ne nécessitent pas de vecteur. Une modification de l’un des deux champs invalide le jeu combiné : les deux champs non vides sont à réencoder pour la nouvelle empreinte.

```bash
# Préparer ou resynchroniser les documents depuis les règles locales.
uv run comparator semantic-sync

# Compter les documents et les vecteurs, avec couverture par modèle.
uv run comparator semantic-status
```

`semantic-sync` est aussi utile après une modification directe des textes en SQL. Les écritures applicatives passent normalement par les importeurs. Ces commandes ne lancent aucun modèle et ne transmettent aucun contenu.

## API

Documentation interactive : `/docs#/Semantic`, contrat : `/openapi.json`.

| Méthode | Route | Usage |
| --- | --- | --- |
| GET | `/api/semantic/status` | Compteurs et couverture par modèle. Les compteurs de vecteurs incluent l’historique ; la couverture concerne les documents courants. |
| GET / POST | `/api/semantic/models` | Lister ou enregistrer un modèle. |
| GET | `/api/semantic/documents` | Lire les textes exacts à encoder et leur `content_hash`. |
| PUT | `/api/semantic/embeddings` | Ajouter le vecteur du titre, de la description ou les deux. |
| GET | `/api/semantic/embeddings?rule_key=…` | Lire les vecteurs courants d’une règle. Ajouter `model_key` pour choisir un modèle, `history=true` pour inclure les versions anciennes. |

Les listes de documents et de vecteurs acceptent `page` à partir de 1 et `page_size` de 1 à 100. Les documents peuvent être filtrés par `source=CAST|Semgrep`, `rule_key`, `model_key` et `status`. Le filtre `status` nécessite un modèle. Les modèles sont listés sans pagination.

### 1. Enregistrer un modèle

Exemple de **modèle fictif de démonstration**, à remplacer par les caractéristiques du modèle réellement utilisé. Aucun modèle n’est préenregistré automatiquement.

Fichier `modele.json` :

```json
{
  "model_key": "local-demo-v1",
  "provider": "local",
  "model_name": "demo-embedding",
  "model_revision": "v1",
  "dimensions": 3,
  "preprocessing": "raw-text-v1"
}
```

```bash
curl 'http://127.0.0.1:8765/api/semantic/models' \
  -H 'Content-Type: application/json' --data-binary @modele.json
```

La révision doit identifier le modèle effectivement utilisé : version immuable, révision de poids ou identifiant de déploiement. `raw-text-v1` signifie que les champs retournés sont transmis séparément, sans concaténation, préfixe, découpage, nettoyage ni troncature par le client. Si un modèle nécessite un autre protocole d’entrée, ajouter explicitement ce protocole à l’application avant son utilisation. La dimension et la configuration sont immuables ; enregistrer une nouvelle clé pour une configuration différente.

### 2. Lire les documents à encoder

```bash
curl --get 'http://127.0.0.1:8765/api/semantic/documents' \
  --data-urlencode 'model_key=local-demo-v1' \
  --data-urlencode 'status=pending' --data-urlencode 'page_size=30'
```

Le client utilise `title` et `description`, puis conserve `rule_key` et `content_hash` de cette réponse. Les vecteurs doivent provenir du même modèle enregistré. Les identifiants de fournisseur ou de modèle sont une provenance déclarative ; le serveur local ne peut pas vérifier quel modèle a réellement produit un tableau reçu.

### 3. Insérer les vecteurs

Fichier `vecteurs.json`, en remplaçant clé et empreinte par celles du document. Les tableaux ci-dessous illustrent seulement le format ; ce ne sont pas des embeddings calculés :

```json
{
  "rule_key": "CAST:EXEMPLE",
  "content_hash": "REMPLACER_PAR_LES_64_CARACTERES_DE_L_EMPREINTE",
  "model_key": "local-demo-v1",
  "title_vector": [0.1, 0.2, 0.3],
  "description_vector": [0.4, 0.5, 0.6]
}
```

```bash
curl -X PUT 'http://127.0.0.1:8765/api/semantic/embeddings' \
  -H 'Content-Type: application/json' --data-binary @vecteurs.json
```

Les deux vecteurs peuvent être envoyés séparément. Un champ absent ou `null` ne supprime pas le vecteur déjà enregistré. Une répétition à l’identique est idempotente ; remplacer un vecteur existant par une valeur différente sous la même clé est refusé. Une nouvelle révision de modèle permet de conserver les générations distinctes.

Contrôles : nombres finis, vecteur non nul, dimension exacte, modèle et règle existants, texte source non vide, empreinte encore courante. Réponses : 200 pour succès, 404 pour règle/modèle inconnu, 409 pour texte périmé/règle retirée/configuration ou vecteur en conflit, 422 pour entrée invalide. Les refus n’écrivent aucun vecteur partiel.

## Calcul avec OpenAI

Le script Python `src/cast_semgrep/openai_embeddings.py` calcule les vecteurs et les enregistre directement dans SQLite. Le serveur web n’a pas besoin de fonctionner. Dans le fichier `.env` à la racine du projet, ajouter :

```dotenv
OPENAI_API_KEY=votre-cle-api
```

La variable d’environnement du même nom est prioritaire. Ne pas publier le fichier `.env`. Le script transmet **uniquement les titres et descriptions** au point d’accès officiel `https://api.openai.com/v1/embeddings`. Les appels sont facturés sur le compte API associé ; les identifiants CAST restent locaux.

```bash
# Préparer et compter les champs manquants, sans appel ni clé API
uv run comparator embed-openai --dry-run
# Calculer tous les vecteurs manquants, ou reprendre après interruption
uv run comparator embed-openai
# Petit premier lot : la limite compte les champs, pas les règles
uv run comparator embed-openai --limit 20
# Autre modèle, conservé séparément
uv run comparator embed-openai --model text-embedding-3-large
# Exécution du script comme module Python
uv run python -m cast_semgrep.openai_embeddings --dry-run
uv run comparator semantic-status
```

Par défaut : `text-embedding-3-small`, 1 536 dimensions, lots de 64 textes. `--dimensions` permet de réduire la dimension ; `--batch-size` accepte 1 à 128 textes. `text-embedding-3-large` utilise par défaut 3 072 dimensions. Voir la [documentation officielle OpenAI](https://developers.openai.com/api/docs/guides/embeddings).

Le registre utilise une clé telle que `openai/text-embedding-3-small/alias-v1/1536`. `--revision alias-v2` ouvre une nouvelle génération sans écraser la précédente. Cette révision est une **étiquette locale**, pas une garantie de version immuable du modèle chez OpenAI. Une configuration déjà enregistrée sous une autre clé est réutilisée.

Les champs vides et les vecteurs déjà présents pour cette version de texte et de modèle sont ignorés. Les textes sont envoyés exactement tels qu’archivés, sans troncature ni remplacement des retours à la ligne. Une limite conservatrice de **8 191 octets UTF-8 par texte** évite de dépasser les 8 192 tokens d’entrée : certains textes admissibles en tokens peuvent ainsi être écartés. Les champs écartés sont explicitement listés dans `oversized_fields` ; le processus termine avec un code non nul et ne prétend pas avoir tout calculé. Chaque requête est également limitée à 200 000 octets de texte et 128 entrées, sous les plafonds documentés de 300 000 tokens et 2 048 entrées.

Les réponses sont contrôlées : modèle, indices uniques, nombre de vecteurs, dimensions, valeurs finies et non nulles. Chaque lot validé est enregistré dans une transaction. Si le texte a changé pendant l’appel, ses vecteurs sont rejetés et comptés dans `stale_vectors` ; relancer pour traiter la nouvelle version. Les vecteurs ajoutés simultanément par un autre client sont conservés. Les erreurs réseau, HTTP 429 et 5xx sont retentées au maximum trois fois, avec attente progressive. Les erreurs d’authentification arrêtent immédiatement le traitement. Les lots déjà enregistrés restent disponibles ; une interruption entre réponse distante et enregistrement peut néanmoins conduire à refaire un appel facturé.

La progression JSON est affichée sur la sortie d’erreur après chaque lot ; le bilan final est affiché sur la sortie standard. `total_tokens` compte les tokens des réponses validées de l’exécution, pas un relevé exhaustif de facturation ni un total historique. Éviter deux exécutions simultanées du même modèle pour ne pas payer des calculs redondants. La clé API et les corps des erreurs distantes ne sont jamais affichés par le script.

## Calcul avec Ollama local

Le script `src/cast_semgrep/ollama_embeddings.py` utilise le point d’accès natif [`POST /api/embed`](https://docs.ollama.com/api/embed). Aucune clé API OpenAI ou connexion Codex n’est nécessaire. Il partage avec le script OpenAI le traitement des versions de texte, des champs manquants et des sauvegardes par lots.

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

```bash
# Inventaire des modèles présents sur votre serveur
uv run comparator ollama-models
# Vérifier le modèle et compter les vecteurs manquants sans inférence
uv run comparator embed-ollama --dry-run
# Calcul complet, ou reprise des champs manquants
uv run comparator embed-ollama --model bge-m3:567m-fp16
# Autre port ou autre modèle déjà installé
uv run comparator embed-ollama --base-url http://127.0.0.1:11436 --model qwen3-embedding:8b-q8_0
# Exécution directe comme module Python
uv run python -m cast_semgrep.ollama_embeddings --limit 20
uv run comparator semantic-status
```

La priorité est `--base-url`, puis `OLLAMA_BASE_URL`, puis `http://127.0.0.1:11434`. Le script ne change jamais de port automatiquement : un serveur inaccessible provoque une erreur. Seules les adresses de boucle locale sont acceptées ; les proxys système et redirections HTTP sont désactivés. Aucun modèle n’est téléchargé automatiquement.

Le modèle par défaut est **`bge-m3:567m-fp16`**, déjà présent sur le serveur utilisé pour ce projet. [BGE-M3](https://ollama.com/library/bge-m3) prend en charge plusieurs langues et des textes de longueurs variées. Sa dimension native, lue dans `/api/show`, est de **1 024**. `--model` accepte un autre nom exact figurant dans l’inventaire ; sa capacité `embedding` et sa dimension sont vérifiées. Une dimension cachée de LLM conversationnel ne suffit pas : le modèle doit déclarer cette capacité. La qualité des rapprochements reste à évaluer sur des exemples validés par un expert.

Le registre conserve `provider=ollama`, le nom exact du modèle et sa **véritable empreinte SHA-256** dans `model_revision`. La clé technique contient une empreinte du nom, l’empreinte complète du modèle et la dimension. Chaque lot contrôle l’empreinte avant et après l’inférence : si le modèle a changé, le lot est rejeté. Une relance après mise à jour crée une nouvelle configuration en conservant les anciens vecteurs. Ce contrôle détecte les changements observables entre appels ; il ne remplace pas le gel administratif des modèles durant une exécution.

Les titres et descriptions sont traités séparément, exactement tels qu’archivés (`raw-text-v1`), sans préfixe ni troncature. Le paramètre **`truncate=false`** impose à Ollama de refuser un texte trop long. Le script s’arrête alors avec une erreur et conserve les lots précédents, plutôt que d’enregistrer un vecteur calculé sur un texte incomplet. Le protocole brut est destiné à la comparaison symétrique ; un modèle exigeant des préfixes spécifiques nécessitera un protocole de prétraitement distinct.

Les lots contiennent 32 champs par défaut (`--batch-size`, de 1 à 128) et au maximum 200 000 octets cumulés, sauf un champ unique plus long, soumis au contrôle du contexte par Ollama. `--limit` limite le nombre de champs, pas le nombre de règles. `--dry-run` consulte uniquement les métadonnées Ollama et prépare les documents SQLite, sans enregistrer de modèle ni calculer de vecteurs. Les réponses sont contrôlées avant écriture : modèle, nombre de vecteurs, dimensions et nombres finis non nuls. Un texte périmé est rejeté à l’enregistrement ; les vecteurs déjà présents ne sont pas écrasés.

La progression JSON est affichée après chaque lot. Les erreurs réseau, HTTP 429 et 5xx sont retentées au maximum deux fois. Une exécution terminée se relance sans refaire les embeddings déjà présents. Le compteur `total_tokens` cumule `prompt_eval_count` lorsque le serveur le fournit ; il vaut zéro pour les réponses qui n’incluent pas cette mesure.

## Portée de cette livraison

Le stockage, le versionnement, la préparation des textes, l’API d’ingestion et les scripts de calcul OpenAI et Ollama sont opérationnels. L’inférence a lieu uniquement lors d’une exécution explicite de `embed-openai` ou `embed-ollama`, jamais lors d’un import ou de l’affichage du site. Il n’y a pas encore d’index de recherche vectorielle ni de calcul de similarité intégré aux rapprochements CAST–Semgrep.

Comme l’API expert, cette API est destinée au serveur local `127.0.0.1` et ne dispose pas d’authentification. Les identifiants de connexion CAST ne sont pas utilisés pour les modèles. Un client externe envoyant les textes à un fournisseur devra disposer de sa propre configuration et des autorisations adéquates.
