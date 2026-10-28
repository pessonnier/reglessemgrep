# Spécification v2 — Validation des principes et incertitude

Date : 28 octobre 2026. Complète la [spécification v1 historisée](specification-v1.md).

Cette évolution vise à établir, sur un périmètre explicite, si une règle Semgrep détecte le principe décrit par une règle CAST. Un corpus fini apporte une preuve expérimentale limitée aux cas exécutés ; il ne démontre pas une équivalence universelle. L’accès au catalogue CAST, même authentifié, ne constitue pas un accès à son moteur d’analyse.

## 1. Livraison actuelle et ordre de développement

La gestion de l’incertitude par règle Semgrep est implémentée : trois niveaux indépendants, avis expert historisé, périmètre, justification, références déclarées, filtres, exports et invalidation après changement de version/définition. Les évaluations sont stockées localement. Les résultats de détection, leur mesure statistique et l’exécution des analyseurs décrits ci-dessous restent à implémenter.

L’ordre proposé est : contractualiser le principe → créer des exemples contradictoires → exécuter Semgrep → confronter CAST si disponible → mesurer et réviser les conclusions. Cette étape complète le benchmark de rapprochement prévu en S3.4 du planning initial, avant de prioriser les embeddings et le LLM.

| ID | Priorité | Tâche / livrable | Dépendance | Critère d’acceptation | État |
|---|---|---|---|---|---|
| S6.0 | P1 | Évaluation de l’incertitude et des risques par règle Semgrep | P0 | Historique conservé, avis périmé invalidé, risques inconnus visibles, filtres et CSV cohérents | Implémenté |
| S6.1 | P1 | Dossier de principe et périmètre commun par paire | S6.0 | Champs du §2 renseignés, chaque affirmation sourcée ou explicitement hypothétique, revue experte tracée | À faire |
| **S6.2** | **P1** | **Implémenter des exemples de code avec et sans la vulnérabilité** | S6.1 | Pour chacun des 3 premiers principes : au moins 2 cas vulnérables, 2 corrigés/sûrs et 2 cas limites ; attentes et lignes revues avant exécution ; fichiers versionnés et manifeste conforme au §3 | **À faire** |
| S6.3 | P1 | Exécuteur local Semgrep et archivage des résultats | S6.2 | Version/configuration/empreintes capturées ; résultats par cas ; erreur, exclusion et timeout distincts d’une absence de détection ; aucun exemple vulnérable exécuté | À faire |
| S6.4 | P1 | Import des résultats CAST et confrontation sur les mêmes cas | S6.2 | Résultats CAST reliés aux empreintes des cas et à la configuration ; sans résultats, état « non exécuté » ; divergences affichées | À faire, selon accès moteur/export CAST |
| S6.5 | P1 | Matrices de confusion, limites de couverture et incertitude mesurée | S6.3 ; S6.4 pour comparaison expérimentale | TP/FP/FN/TN, dénominateurs, cas exclus et taille du corpus affichés ; aucun taux en l’absence d’échantillons ; conclusion bornée au périmètre | À faire |
| S6.6 | P1 | Campagne de non-régression et rapport de validation | S6.5 | Changement de règle/moteur/corpus déclenche une réévaluation ; rapport relie sources, propositions, résultats et avis sans les confondre | À faire |

Les priorités, le choix des trois principes, le responsable et la date cible restent modifiables. Le classeur initial conserve le planning P0–P2 précédent ; ce tableau constitue son complément pour le lot 6.

## 2. Dossier de principe par paire CAST–Semgrep

Conserver un dossier versionné, avec identifiants de règles et empreintes des sources archivées, portant sur :

- **Principe recherché** : défaut précis, conséquence attendue, unité d’analyse (instruction, fonction, fichier, application). Le CWE/OWASP sert d’index documentaire.
- **Préconditions** : langage/version, framework et API, entrées contrôlables, accès nécessaires, contexte d’appel, configuration.
- **Mécanisme de détection** : motif syntaxique, flux de données, sources/puits/assainisseurs s’ils s’appliquent ; portée intra/interprocédurale et intra/interfichiers seulement si documentée ou observée.
- **Frontières** : exceptions légitimes, code constant, validation et échappement contextuels, appels indirects, wrappers, alias, code mort, exclusions et suppressions.
- **Attentes indépendantes** : comportement attendu du principe, attente issue de la documentation CAST et attente issue de la règle Semgrep. Une divergence documentée n’est pas effacée pour obtenir un test vert.
- **Justifications** : URL, version/date, extrait et champ/page ; une déduction de l’expert ou une proposition LLM porte sa propre origine.
- **Conclusion** : principe commun documenté, correspondance expérimentale sur le corpus, couverture partielle, divergence, indéterminé ou non comparable ; périmètre, auteur/date et contre-exemples joints.

Le score de classement existant et le statut d’équivalence de l’expert restent consultables. Ils ne suffisent pas à obtenir le statut « correspondance expérimentale sur le corpus ».

## 3. Corpus de code vulnérable, corrigé et limites — S6.2

Créer `validation/cases/<principe>/<langage>/` avec fichiers de code, manifeste et justification des attentes. Le [modèle de dossier](templates/validation-case.md) précise les champs à renseigner. La tâche comprend bien l’écriture des fichiers de code ; le modèle documentaire seul ne la termine pas.

Sélectionner d’abord trois principes parmi les paires du catalogue, sur des langages et API réellement communs. Pour chacun, écrire au minimum six cas indépendants : deux vulnérables, deux sûrs/corrigés et deux cas limites. Associer chaque variante vulnérable à une correction minimale conservant le contexte utile. Les cas limites doivent rechercher activement un faux positif ou une absence de détection (alias, wrapper, propagation, validation inadaptée, constante sûre selon le principe). Ajouter ensuite les variantes interprocédurales/interfichiers quand elles sont pertinentes.

Chaque cas doit comporter un identifiant stable, le principe et la paire ciblés, un SHA-256 des fichiers, le langage et ses dépendances, l’origine/licence du code, les lignes de détection attendues, et une étiquette indépendante `vulnerable`, `safe`, `out_of_scope` ou `unknown`. Un expert valide l’étiquette, sa justification et les préconditions **avant** de consulter le résultat du moteur. Le LLM peut proposer des exemples ; son étiquette reste non validée jusqu’à cette revue.

Pour les règles de qualité sans vulnérabilité de sécurité, employer les termes « non conforme / conforme » et documenter le principe concerné. Une correction d’une vulnérabilité ne garantit pas l’absence de tout autre défaut dans le fichier.

Les cas vulnérables sont des cibles d’analyse statique. Le runner ne les exécute pas et ne lance pas leurs scripts de construction ou dépendances arbitraires. Les besoins de compilation/préparation CAST sont décrits séparément avec commandes explicites. Aucun conteneur n’est requis.

## 4. Exécution, résultats et critères de preuve

Pour chaque campagne, enregistrer : identifiant/date, version exacte du moteur, édition/options, révision et empreinte de chaque règle, empreinte du corpus et du contrat, commande, durée, code retour, sortie brute et erreurs. Les règles proviennent de l’archive locale versionnée. Un changement de l’un de ces éléments rend la conclusion précédente à réévaluer sans supprimer son historique.

Le mécanisme officiel `semgrep --test` utilise `ruleid` pour les détections attendues et `ok` pour les cas sans détection, avec des commentaires juste avant les lignes concernées. Les annotations `todoruleid` et `todook` peuvent masquer un échec dans le bilan global ; elles doivent donc être signalées comme limites connues et ne compter comme aucun succès démontré. Le format et les options seront vérifiés pour la version du moteur retenue. Source : [documentation Semgrep — Test rules](https://docs.semgrep.dev/writing-rules/testing-rules), consultée le 28/10/2026.

Le runner produit des états par cas : `detected`, `not_detected`, `error`, `timeout`, `skipped`, `unsupported`, `not_run`. Une absence de résultat ne vaut `not_detected` que si le fichier, la règle et le langage ont effectivement été analysés sans erreur. Exclusions, suppressions et erreurs de parsing sont explicites. Le rapprochement d’un résultat prend en compte l’identifiant de règle, le fichier et l’emplacement attendu ; une alerte étrangère dans le fichier ne valide pas le cas.

Les résultats CAST doivent porter sur les mêmes fichiers et être reliés à leur empreinte. À défaut d’exécution ou d’export CAST exploitable, afficher « Semgrep testé contre le principe documenté CAST ; comportement du moteur CAST non vérifié ». Le téléchargement de la documentation ne remplace jamais un résultat de scan.

Les origines sont affichées séparément : références documentaires, propositions LLM, résultats d’exécution bruts, interprétation et décision de l’expert. Des références saisies dans un avis restent des références **déclarées**, sans statut automatique de preuve vérifiée.

## 5. Mesure des faux positifs et des absences de détection

L’unité statistique est le cas de test revu, pour une règle, un principe et un périmètre déterminés. Plusieurs alertes du même cas ne gonflent pas le nombre de cas détectés. L’oracle expert détermine le vrai défaut ; un désaccord entre CAST et Semgrep ne suffit pas à désigner l’un comme correct.

| Étiquette validée | Résultat exploitable | Catégorie |
|---|---|---|
| Vulnérable / non conforme | Détection ciblée | TP — vrai positif |
| Vulnérable / non conforme | Absence de détection | FN — faux négatif |
| Sûr / conforme pour le principe | Détection ciblée | FP — faux positif |
| Sûr / conforme pour le principe | Absence de détection | TN — vrai négatif |

Afficher les effectifs et les taux sur le corpus : faux positifs `FP/(FP+TN)`, non-détection `FN/(TP+FN)`, précision `TP/(TP+FP)` et rappel `TP/(TP+FN)`. Un dénominateur nul donne « non mesurable ». Les cas non étiquetés, hors périmètre, non exécutés ou en erreur restent visibles séparément et sont exclus de ces dénominateurs. Afficher le nombre de cas exécutés/exploitables sur le nombre prévu pour éviter un bilan trompeur.

Prévoir des intervalles de confiance à 95 % (méthode et hypothèses documentées) avec les taux. Sur un corpus synthétique choisi, ils décrivent au mieux l’échantillon et ne constituent pas une probabilité de défaut sur un projet réel. L’absence d’échec sur quelques exemples ne vaut pas risque nul. Les familles de cas, la taille du corpus et les dimensions non testées restent visibles.

Pour qualifier une correspondance expérimentale : contrat revu, cas positifs/négatifs et limites présents, attentes indépendantes approuvées, exécutions des deux moteurs disponibles et exploitables pour les cas du périmètre revendiqué, divergences expliquées, résultats à jour et décision experte explicite. Si seul Semgrep a été exécuté, la conclusion reste une conformité au principe documenté, pas une validation du comportement CAST. Aucune approbation d’équivalence universelle automatique.

## 6. Incertitude par règle Semgrep — comportement implémenté

Chaque règle expose trois valeurs indépendantes :

| Champ | Sens | Valeur initiale |
|---|---|---|
| Incertitude de l’évaluation | Degré auquel les connaissances restent incomplètes | Élevée |
| Risque estimé de faux positifs | Possibilité d’alerter sur un cas conforme | Non évalué |
| Risque estimé de non-détection | Possibilité de manquer un cas non conforme | Non évalué |

Les niveaux qualitatifs sont faible, moyen, élevé et non évalué. Ils sont des avis, pas des pourcentages. Une règle peut présenter un risque élevé bien connu avec une incertitude faible : les trois axes ne doivent donc pas être fusionnés par un maximum arithmétique. La sévérité du défaut, le score de rapprochement et `metadata.confidence` de Semgrep sont des informations distinctes.

L’expert consigne son nom, le périmètre (langage, moteur et cas examinés), les trois valeurs, une justification non vide et des références éventuelles. Il explique ce qui étaye ou limite sa confiance, les faux positifs possibles et les variantes susceptibles d’échapper à la règle. Une incertitude faible reste explicitement un avis expert tant que le protocole expérimental n’est pas implémenté.

L’API enregistre la version source et le SHA-256 canonique de la définition. Le statut est `not_evaluated` (aucun avis), `expert_assessed` (avis sur la version courante) ou `stale` (avis ancien). Une réimportation identique conserve l’avis ; une nouvelle révision ou définition remet l’incertitude à élevée et les risques à non évalués, tout en conservant chaque avis. Un formulaire ouvert avant modification est refusé avec HTTP 409. Les anciennes règles sans empreinte doivent être réimportées localement avant évaluation.

La fiche, la comparaison, les filtres et les exports utilisent la même évaluation effective. Les règles CAST ne reçoivent pas artificiellement une évaluation Semgrep. Les futurs résultats quantifiés du §5 seront stockés séparément et cités par l’avis expert ; ils ne remplaceront pas son historique.

## 7. Critères de recette de cette livraison

- Toutes les règles Semgrep disposent d’un état d’incertitude, y compris après migration de la base v3.
- Une confiance éditeur `HIGH` ne devient ni un risque faible, ni une mesure de précision.
- L’auteur, le périmètre et la justification vides sont refusés ; une règle CAST, supprimée ou obsolète ne peut recevoir une évaluation Semgrep courante.
- Les avis sont ajoutés à l’historique ; un réimport ou un recalcul de candidats ne les efface pas.
- Les avis sur une ancienne définition ne sont plus utilisés par les filtres ou exports de la version actuelle.
- Les propositions LLM et les avis d’équivalence par paire restent séparés de l’incertitude par règle.
- La tâche S6.2 est explicitement planifiée et ne porte pas le statut « implémenté » tant que ses exemples de code et leur revue n’existent pas.
