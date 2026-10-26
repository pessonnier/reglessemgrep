# Méthode de rapprochement déterministe

Version `deterministic-v1`. Le score de 0 à 100 classe des **candidats** et ne mesure pas la couverture démontrée.

## Sélection

Pour chaque règle CAST, le programme recherche des règles Semgrep partageant un CWE, une référence OWASP ou des termes du titre. Les langages explicitement incompatibles excluent la paire ; quelques noms CAST sont rapprochés des noms de langage Semgrep par une table visible dans `matching.py` (par exemple `JEE → java`). L’absence d’information technique ne devient pas une compatibilité prouvée.

## Score

| Facteur | Maximum |
|---|---:|
| Langage commun | 15 |
| CWE / OWASP communs | 35 |
| Proximité des termes du titre | 20 |
| Proximité des termes de description | 20 |
| Catégorie compatible | 10 |

Le score est plafonné à 100. Une paire doit avoir un CWE commun, ou un OWASP commun accompagné d’au moins un terme du titre ou trois termes descriptifs communs, ou au moins deux termes du titre communs ; elle doit aussi atteindre le seuil configuré. Seuls les `top_k` meilleurs candidats par règle CAST sont conservés à chaque calcul. Les paires déjà revues par un expert restent conservées même si leur rang évolue.

La convergence des préconditions et la similarité sémantique restent « non établies / non calculées » à ce stade. Le niveau de preuve indique seulement si une référence de taxonomie est partagée ou si le candidat repose sur des termes communs.

Les éléments de preuve stockés dans `match_evidence` pointent vers les champs et URL des règles originales. Le partage d’un CWE, d’un terme ou d’un langage constitue une justification de **candidature**, pas une preuve d’équivalence des conditions de détection. Les modes de propagation, analyses inter-fichiers ou capacités interprocédurales ne sont jamais attribués à CAST sans documentation.

## Trois couches distinctes

1. **Références sourcées** : extraits et identifiants vérifiables des catalogues CAST/Semgrep ou d’un référentiel identifié.
2. **Proposition LLM** : résultat facultatif d’un modèle, avec son nom/version et sa justification. Aucune proposition LLM n’est produite par la version P0.
3. **Avis de l’expert** : décision et commentaire humains, ajoutés à un historique qui n’est pas effacé au recalcul.

Les statuts d’avis expert sont : équivalent, partiellement équivalent, complémentaire, apparenté, sans correspondance identifiée, indéterminé et non comparable. Le classement automatique garde le statut `indeterminate` jusqu’à la revue.

