# Calcul des embeddings Ollama — 29 octobre 2026

Le serveur initialement indiqué sur `127.0.0.1:11436` ne répondait pas. Le serveur `http://127.0.0.1:11434` a été identifié, puis explicitement confirmé par l’utilisateur avant le calcul.

L’inventaire annonce 99 modèles, dont huit entrées avec la capacité `embedding` : `qwen3-embedding:8b-q8_0`, `qwen3-embedding:8b-fp16`, `embeddinggemma:300m-bf16`, `embeddinggemma:300m`, `nomic-embed-text-v2-moe:latest`, `nomic-embed-text:latest`, `bge-m3:567m-fp16`, `mxbai-embed-large:335m-v1-fp16`. Les deux entrées EmbeddingGemma partagent la même empreinte.

## Configuration retenue

- Modèle : **`bge-m3:567m-fp16`**, déjà installé, sans téléchargement supplémentaire.
- Fournisseur : `ollama`.
- Révision : `sha256:7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`.
- Dimension native : **1 024**.
- Protocole : `raw-text-v1`, titre et description séparés, sans préfixe ni troncature.
- Capacité `embedding` vérifiée par `/api/show` ; empreinte vérifiée avant et après chaque lot.
- Commande : `uv run comparator embed-ollama --base-url http://127.0.0.1:11434 --model bge-m3:567m-fp16`.

[BGE-M3](https://ollama.com/library/bge-m3) a été retenu pour sa prise en charge multilingue et son format de taille modérée parmi les modèles présents. Ce choix n’est pas une mesure comparative de qualité sur ce catalogue.

## Résultat observé

| Catalogue | Règles couvertes | Vecteurs de titre | Vecteurs de description |
|---|---:|---:|---:|
| CAST | 2 828 | 2 828 | 2 828 |
| Semgrep | 2 153 | 2 153 | 2 153 |
| **Total** | **4 981** | **4 981** | **4 981** |

**9 962 vecteurs calculés et enregistrés** dans la base locale : deux lors du premier essai, puis 9 960 en 312 lots. Les réponses annoncent 333 162 tokens au total, essai inclus. Aucun champ tronqué, aucun texte périmé, aucun lot en erreur. La vue `semantic_coverage` affiche 4 981 documents `complete` pour ce modèle.

La lecture de tous les vecteurs confirme leur dimension de 1 024, des composantes finies et des vecteurs non nuls. Les normes sont comprises entre 0,99999896 et 1,00000085. Une relance réelle après achèvement trouve **zéro champ manquant et effectue zéro appel d’inférence**.

Les 4 981 règles, 4 516 candidats, 38 482 preuves et les tables d’avis et d’incertitude sont inchangés par rapport à la sauvegarde précédant le calcul. Les embeddings sont disponibles via l’API sémantique existante. La similarité vectorielle n’est pas encore intégrée au score de correspondance et ne constitue pas une preuve d’équivalence des règles.

## Validation et conservation

- **60 tests passent**, couvrant les contrats Ollama, les changements d’empreinte, les vecteurs invalides, la reprise commune et la non-régression OpenAI.
- Paquet Python construit ; les deux connecteurs et le traitement commun sont inclus.
- Base SQLite et vecteurs conservés localement, exclus de la publication GitHub.
- [Guide d’exécution et de reprise](../semantic-database.md#calcul-avec-ollama-local).
