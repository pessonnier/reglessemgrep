# Méthode de rapprochement hybride

Version `hybrid-v3-semantic` lorsque des vecteurs courants sont disponibles pour la paire ; repli `deterministic-v2-owasp` sinon. Le score de 0 à 100 classe des **candidats** et ne mesure pas la couverture démontrée.

## Sélection

Pour chaque règle CAST, le programme réunit les règles Semgrep partageant un CWE, une référence OWASP ou des termes du titre et jusqu’à 30 voisins sémantiques admissibles. Les voisins sont recherchés dans les vecteurs locaux, sans nouvel appel à Ollama ou OpenAI. Les langages explicitement incompatibles excluent la paire ; quelques noms CAST sont rapprochés des noms de langage Semgrep par une table visible dans `matching.py` (par exemple `JEE → java`). L’absence d’information technique ne devient pas une compatibilité prouvée.

## Score

| Facteur | Maximum |
|---|---:|
| Langage commun | 15 |
| CWE / OWASP communs | 35 |
| Titre : termes et embedding | 20 |
| Description : termes et embedding | 20 |
| Catégorie compatible | 10 |

Le score est plafonné à 100. Une paire doit avoir un CWE commun, ou un OWASP commun accompagné d’un terme distinctif du titre et de deux termes descriptifs communs, ou au moins deux termes du titre communs, ou satisfaire le critère d’admission sémantique détaillé ci-dessous ; elle doit aussi atteindre le seuil configuré. Des termes génériques tels que « injection » ne suffisent pas, seuls, pour déclencher une piste OWASP. Seuls les `top_k` meilleurs candidats par règle CAST sont conservés à chaque calcul. Les paires déjà revues par un expert, associées manuellement ou accompagnées d’une proposition LLM restent conservées même si leur rang évolue.

### Contribution des embeddings

Pour chaque champ dont les deux vecteurs sont disponibles, le bloc de 20 points est remplacé par :

- `arrondi(points_lexicaux_historiques / 2)` : 0 à 10 points ;
- `arrondi(10 × max(0, min(1, (cosinus − 0,50) / 0,50)))` : 0 à 10 points.

La contribution sémantique est donc plafonnée à **20 points au total**, à l’intérieur des deux blocs textuels. Les cosinus sont calculés sur des vecteurs normalisés puis arrondis à six décimales. Un cosinus inférieur ou égal à 0,50 ne rapporte aucun point. Un champ sans deux vecteurs exploitables conserve son ancien score lexical sur 20 : aucune valeur absente n’est remplacée par zéro. La nouvelle pondération peut faire **baisser ou augmenter** un score ; elle n’ajoute pas un bonus uniforme. Les références CWE/OWASP, les langages et la catégorie gardent leurs poids.

L’API expose `baseline_score`, les anciens scores `lexical_title_similarity` et `lexical_description_similarity`, `semantic_points`, `lexical_points`, `semantic_similarity` et `semantic_details`. Ce dernier contient les deux cosinus, le fournisseur, le modèle, sa révision, sa dimension et les empreintes des textes comparés. L’écran de comparaison affiche ces éléments séparément des sources et de l’avis expert.

### Admission par la sémantique seule

Une paire sans les indices lexicaux ou de référence habituels peut être proposée si :

1. Les titres **et** descriptions des deux règles ont des vecteurs courants du même modèle, de la même révision et du même protocole.
2. Les cosinus titre et description sont chacun au moins **0,60**.
3. La moyenne `0,40 × cosinus_titre + 0,60 × cosinus_description` atteint **0,75**, seuil configurable.
4. Les langages connus sont compatibles, le score atteint `min_score`, et la paire figure dans le top-k final.

Les voisins sont filtrés par langue **avant** de retenir les 30 premiers. Les égalités sont départagées par `rule_key`. Les vecteurs partiels contribuent au score d’une candidature classique mais ne suffisent pas à créer une candidature purement sémantique. Les paires manuelles, revues ou associées à une proposition LLM restent conservées, même hors seuil ou top-k ; leurs scores et facteurs sont actualisés sans modifier leur historique. Les associations conservées malgré une incompatibilité de langage sont signalées comme telles.

Les seuils 0,50 / 0,60 / 0,75 sont des réglages initiaux prudents, **pas une calibration expérimentale**. Un cosinus de 0,75 n’est pas une probabilité de 75 % d’équivalence. Les conditions de détection et la convergence des préconditions restent à valider. Sur le corpus initial, abaisser le seuil révèle aussi des voisins discutables : proximité lexicale ou thématique ne signifie pas même principe.

### Modèle, fraîcheur et commandes

Par défaut, le moteur choisit une seule configuration ayant des embeddings courants dans les deux catalogues : priorité au minimum des nombres de règles entièrement couvertes dans chaque catalogue, puis à leur somme, puis à la clé du modèle. Le bilan indique toujours le modèle retenu et la couverture complète par éditeur. Un vecteur d’une ancienne version du texte ou d’une règle retirée est exclu. Les vecteurs invalides sont ignorés et comptés. Aucun mélange entre modèles ou dimensions n’est effectué.

```bash
# Classement hybride utilisant les vecteurs déjà calculés
uv run comparator match
# Comparaison de référence sans utiliser les embeddings
uv run comparator match --no-semantic
# Sélection reproductible d’une configuration : clé exacte de semantic-status
uv run comparator match --semantic-model CLE_DU_MODELE
# Seuil et nombre de voisins étudiés avant le top-k final
uv run comparator match --semantic-threshold 0.75 --semantic-top-k 30 --top-k 15
```

Une clé explicitement demandée mais inconnue provoque une erreur avant modification des candidats. Sans modèle utilisable, la méthode historique reste disponible. Le calcul utilise NumPy pour les matrices de cosinus et ne requiert pas de serveur vectoriel supplémentaire.

Les éléments de preuve stockés dans `match_evidence` pointent vers les champs et URL des règles originales. Le partage d’un CWE, d’un terme ou d’un langage constitue une justification de **candidature**, pas une preuve d’équivalence des conditions de détection. Les modes de propagation, analyses inter-fichiers ou capacités interprocédurales ne sont jamais attribués à CAST sans documentation.

## Trois couches distinctes

1. **Références sourcées** : extraits et identifiants vérifiables des catalogues CAST/Semgrep ou d’un référentiel identifié.
2. **Analyse automatique** : les facteurs sémantiques sont une hypothèse calculée à partir des embeddings, avec leur provenance. Ils restent dans `factors_json`, jamais dans les références sourcées ni dans les avis experts. Une proposition rédigée par un LLM, si elle existe, reste distincte dans `llm_proposals` ; aucun texte de justification LLM n’est inventé par le classement sémantique.
3. **Avis de l’expert** : décision et commentaire humains, ajoutés à un historique qui n’est pas effacé au recalcul.

Les statuts d’avis expert sont : équivalent, partiellement équivalent, complémentaire, apparenté, sans correspondance identifiée, indéterminé et non comparable. Le classement automatique garde le statut `indeterminate` jusqu’à la revue.

## Validation des principes et incertitude

La [spécification v2](specification-v2-validation.md) définit le protocole pour démontrer une correspondance sur un corpus de code vulnérable et sûr. Les tests de détection sont planifiés dans le lot S6 ; le moteur actuel ne produit pas de preuve expérimentale.

Chaque règle Semgrep dispose désormais d’une incertitude qualitative et de deux risques distincts (faux positifs, non-détection). Initialement, l’incertitude est élevée et les risques non évalués. Un expert peut enregistrer un avis motivé, borné à un périmètre et à une version. `metadata.confidence` reste une métadonnée de l’éditeur sans conversion en taux de précision. Un avis périmé reste dans l’historique et ne sert plus d’évaluation courante.

## Jointure OWASP et éditions

Un parseur commun aux deux importeurs et au moteur de score extrait une clé canonique `famille + numéro sur deux chiffres + : + année`. `A03-2021`, `A3 : 2021`, `A03–2021` et `A03:2021 - Injection` produisent `A03:2021`. Les libellés complets et graphies originales restent dans `owasp_raw`, et les preuves citent ces valeurs d’origine. Le recalcul normalise aussi les anciennes lignes locales et peut récupérer une référence présente seulement dans les valeurs brutes, sans nouvelle collecte ni modification des empreintes des définitions.

La jointure exige la même famille (`A`, `API`, `M`), le même numéro (1 à 10) et la même édition. Une référence incomplète, sans année ou invalide n’est pas jointe. Aucun rapprochement inter-éditions n’est déduit du seul numéro : la catégorie officielle [A03:2021 couvre l’injection](https://top10.owasp.org/2021/A03_2021-Injection/), tandis que les références du [Top 10 API ont leur propre nomenclature](https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/).

Au moins une clé OWASP commune apporte **10 points avant plafond**, quel que soit le nombre de références communes ; un CWE commun apporte 30 points. Le bloc CWE + OWASP reste plafonné à 35 : OWASP ajoute donc 5 points effectifs si CWE apporte déjà 30. Les doublons de graphie ou multiples éditions déclarées ne multiplient pas les points. `shared_owasp`, `owasp_reference_points`, `cwe_reference_points` et `reference_points_cap` rendent cette contribution explicite dans l’API ; la comparaison l’affiche également.

`comparator match` rapporte les nombres de paires actives avant/après, nouvelles et retirées, les scores modifiés et les règles de chaque éditeur nouvellement reliées. Ces nombres sont mesurés sur le résultat conservé après seuil et top-k ; ils ne représentent pas toutes les combinaisons partageant une catégorie OWASP.
