# Classement sémantique CAST–Semgrep — 29 octobre 2026

## Méthode appliquée

Le classement `hybrid-v3-semantic` utilise les embeddings BGE-M3 déjà calculés localement, sans nouvel appel d’inférence. Configuration : `bge-m3:567m-fp16`, 1 024 dimensions, empreinte `sha256:7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`. Couverture complète des 2 828 règles CAST et 2 153 règles Semgrep ; aucun vecteur invalide ignoré.

Les blocs titre et description restent sur 20 points chacun : moitié du score lexical historique, plus au maximum 10 points fondés sur le cosinus au-dessus de 0,50. Les autres critères restent inchangés. Les candidatures uniquement sémantiques exigent un cosinus pondéré de 0,75, avec au moins 0,60 sur chaque champ et compatibilité des langages connus. Les 30 voisins sémantiques admissibles sont réunis aux candidats classiques ; le classement final conserve 15 candidats par règle CAST et un score minimum de 18. Les associations protégées par une décision manuelle, un avis ou une proposition LLM sont conservées hors seuil et top-k.

Ces seuils sont des réglages initiaux documentés, pas une mesure de précision. Voir la [méthode complète](../matching-methodology.md).

## Résultats mesurés

| Mesure | Avant | Après |
|---|---:|---:|
| Paires candidates | 4 516 | 4 504 |
| Règles CAST avec au moins un candidat | 580 | 577 |
| Règles Semgrep avec au moins un candidat | 785 | 793 |

- **437 paires entrantes** et **449 sortantes** du résultat après seuil et top-k.
- **3 025 scores modifiés** parmi les paires conservées : 900 augmentent, 2 125 baissent ; 1 042 restent identiques.
- **0 règle CAST nouvellement reliée**, 3 perdent leur dernier candidat automatique.
- **61 règles Semgrep nouvellement reliées**, 53 perdent leur dernier candidat, soit un gain net de 8.
- Sept paires retenues satisfont aussi le seuil sémantique de 0,75 ; elles disposaient déjà d’indices classiques. Aucune candidature retenue ne dépend uniquement de la sémantique à ce seuil.

L’apport mesuré est donc ici un **reclassement**, pas une hausse démontrée de la couverture CAST. Les nouveaux liens ne sont pas des équivalences validées. Une exploration diagnostique avec un seuil inférieur révèle des voisins intéressants mais aussi discutables : par exemple une règle sur `exec` voisine d’une règle sur `sys.exit`, ou des cookies voisins d’échappement HTML. Le seuil par défaut n’a pas été abaissé pour gonfler le nombre de correspondances.

Exemple vérifié dans l’interface : CAST `8420` (« Avoid second order SQL injection ») face à Semgrep `find-sql-string-concatenation` passe de **78 à 71/100**. Les cosinus titre et description sont respectivement environ 0,556 et 0,502 ; la contribution sémantique est de 1/20 point. La référence CWE-89 commune ne démontre toujours pas la détection du mécanisme en deux étapes décrit par CAST.

## Vérifications

- **66 tests passent**, dont découverte sans mots communs, seuil, langues incompatibles, vecteurs absents/périmés/invalides, exclusion des mélanges de modèles, conservation des avis et reprise du calcul.
- Seconde exécution sur la base locale : **0 paire ajoutée, 0 retirée, 0 score modifié**.
- Règles, embeddings, propositions LLM, avis et évaluations d’incertitude inchangés par comparaison avec la sauvegarde antérieure au calcul.
- Paquet Python construit et JavaScript vérifié ; comparaison contrôlée dans le navigateur avec contributions et provenance visibles.
- Les sources restent dans `match_evidence`, les facteurs sémantiques dans `factors_json`, les avis dans leur historique. Aucun avis ni texte d’analyse LLM n’est généré par le classement.

## Reproduire

```bash
uv run comparator match
uv run comparator match --no-semantic
uv run comparator match --semantic-threshold 0.75 --semantic-top-k 30 --top-k 15 --min-score 18
```

Ces commandes recalculent les candidats dans la base configurée. Pour comparer des réglages sans changer l’application en service, utiliser une copie SQLite cohérente et définir `COMPARATOR_DB` vers cette copie. Les vecteurs et la base locale ne sont pas publiés dans GitHub.
