# Projet : CAST–Semgrep Rules Comparator

## 1. Mission et objectif général

Tu es un ingénieur logiciel senior spécialisé en analyse statique de code (SAST), en ingénierie des données, en analyse sémantique et en développement d'applications web.

Ta mission est de concevoir et développer une application permettant de **collecter, inventorier, normaliser, comparer et présenter les règles d'analyse statique de code publiées par CAST Software et Semgrep**.

L'application doit permettre à un ingénieur chargé de la qualité et de la sécurité du code de comprendre les couvertures respectives des deux outils, de rechercher les règles qui traitent d'un même problème et d'identifier leurs spécificités.

Le projet doit produire une véritable application fonctionnelle, et non uniquement un prototype visuel ou une documentation d'architecture.

Nom provisoire : `cast-semgrep-comparator`.

## 2. Sources de données

### 2.1. CAST Software

Source principale :

https://technologies.castsoftware.com/

Source complémentaire historique :

https://technologiesv1.castsoftware.com/

Documentation de l'API historique :

https://technologiesv1.castsoftware.com/swagger-ui/

Le catalogue CAST expose des règles associées à des technologies, critères de qualité, standards et extensions.

Développer un connecteur permettant de :

- Découvrir et inventorier les technologies couvertes.
- Récupérer les règles et leurs identifiants CAST.
- Extraire les titres, descriptions, objectifs, recommandations, exemples et sévérités lorsqu'ils sont accessibles.
- Récupérer les critères techniques, critères métier, référentiels et classifications disponibles.
- Identifier les versions, extensions et éventuelles règles dépréciées.
- Conserver l'URL permettant d'accéder à la documentation originale de chaque règle.
- Détecter les règles utilisées dans plusieurs technologies et éviter les doublons artificiels.
- Identifier les informations indisponibles sans authentification.

Commencer par rechercher une API officiellement accessible sur le site actuel.

Examiner ensuite les possibilités de l'API REST historique, notamment :

- `GET /rest/AIP/technologies`
- `GET /rest/AIP/technologies/{TECHNO}/quality-rules`
- `GET /rest/AIP/quality-rules/{ID}`
- `GET /rest/AIP/business-criteria`
- `GET /rest/AIP/technical-criteria/{TCID}/quality-rules`

Ces routes sont documentées dans l'ancienne API et ne doivent pas être considérées comme fonctionnelles ou compatibles avec le site actuel sans vérification.

Si les API ne permettent pas une collecte satisfaisante, étudier une extraction HTML respectueuse des restrictions du site ou un import de fichiers exportés.

Ne contourner aucune authentification ni restriction d'accès. Prévoir, si nécessaire, une configuration facultative pour une authentification autorisée.

### 2.2. Semgrep

Source principale :

https://github.com/semgrep/semgrep-rules

Source documentaire :

https://semgrep.dev/docs/writing-rules/

Télécharger ou synchroniser le dépôt Git pour disposer de l'inventaire complet des règles présentes dans la révision sélectionnée.

Développer un analyseur des fichiers YAML et YML.

Attention : un fichier YAML peut contenir plusieurs règles. L'inventaire doit donc compter les objets `rules`, et non simplement les fichiers.

Extraire notamment :

- Identifiant unique de la règle (`id`).
- Message associé (`message`).
- Sévérité (`severity`).
- Langages (`languages`).
- Catégorie et technologie (`metadata`).
- Références CWE, OWASP et autres standards, lorsqu'elles existent.
- Modes d'analyse (`search`, `taint`, etc.).
- Patterns de détection et expressions associées.
- Sources, propagateurs, assainisseurs et points sensibles pour les règles de taint analysis, lorsqu'ils sont présents.
- Corrections proposées (`fix`, `fix-regex`).
- Références et liens documentaires.
- Chemin du fichier GitHub.
- Révision Git utilisée.

Conserver le YAML original localement lorsque sa conservation est autorisée, afin de permettre une analyse technique approfondie.

Vérifier la conformité des règles et distinguer les erreurs de parsing des règles valides.

Ne pas confondre les règles communautaires du dépôt GitHub avec les règles propriétaires Semgrep Pro. Le périmètre initial porte sur le dépôt public, avec une architecture autorisant l'ajout ultérieur d'autres sources.

## 3. Modèle de données commun

Créer un modèle de données normalisé permettant de représenter les règles des deux éditeurs.

Prévoir les principaux champs suivants :

| Champ | Signification |
|---|---|
| `source` | CAST ou Semgrep |
| `rule_id` | Identifiant de la règle |
| `title` | Intitulé original |
| `description` | Description complète disponible |
| `language` | Langage informatique |
| `framework` | Framework concerné |
| `category` | Sécurité, fiabilité, performance, maintenabilité, etc. |
| `subcategory` | Famille précise de défauts |
| `severity` | Sévérité d'origine |
| `cwe` | Références CWE |
| `owasp` | Références OWASP |
| `standards` | Autres référentiels |
| `detection_method` | Mécanisme d'analyse, s'il est documenté |
| `analysis_scope` | Portée de l'analyse |
| `remediation` | Recommandations de correction |
| `source_url` | URL d'origine |
| `source_version` | Version ou commit |
| `status` | Actif, déprécié, inconnu |
| `collected_at` | Date de collecte |

Autoriser les relations plusieurs-à-plusieurs pour les langages, frameworks, standards et catégories.

Conserver les données brutes et les données normalisées séparément afin de permettre un retraitement sans réinterroger systématiquement les sources.

Tous les champs doivent pouvoir contenir une valeur « non renseignée ».

Ne jamais inventer une information technique absente du catalogue original.

## 4. Classification des règles

Établir une taxonomie technique commune permettant d'organiser les deux catalogues.

Distinguer notamment :

1. Sécurité applicative : injections SQL, XSS, SSRF, XXE, IDOR, désérialisation, contrôle d'accès, cryptographie, authentification, exposition de secrets.
2. Fiabilité : exceptions, gestion des ressources, valeurs nulles, concurrence, transactions, erreurs de traitement.
3. Performance : requêtes inefficientes, complexité algorithmique, traitements répétitifs, consommation mémoire.
4. Maintenabilité : duplication, complexité cyclomatique, longueur des méthodes, conventions, documentation, couplage.
5. Architecture : dépendances circulaires, organisation des composants, séparation des responsabilités, violations de couches.
6. Qualité des données et accès aux bases : SQL, transactions, intégrité, indexation.
7. Bonnes pratiques propres aux langages et frameworks.

Autoriser plusieurs catégories pour une même règle.

Exploiter les taxonomies CWE, OWASP, CISQ et ISO/IEC 5055 lorsque les correspondances sont effectivement établies.

Les classifications inférées automatiquement doivent être distinguées des classifications publiées par les éditeurs.

## 5. Moteur de comparaison et de rapprochement sémantique

C'est la fonctionnalité principale du projet.

Ne pas se limiter à la comparaison textuelle des intitulés.

Deux règles peuvent décrire un même défaut avec des termes très différents.

Inversement, deux règles ayant des titres similaires peuvent rechercher des comportements distincts.

### 5.1. Étape 1 — Correspondances déterministes

Rechercher d'abord les rapprochements fondés sur :

- Langage ou technologie compatible.
- Identifiants CWE communs.
- Références OWASP communes.
- Catégories techniques.
- API ou fonctions explicitement concernées.
- Termes techniques normalisés.
- Identité ou proximité des comportements recherchés.

Utiliser des mécanismes explicables et reproductibles.

### 5.2. Étape 2 — Similarité sémantique

Implémenter une recherche sémantique utilisant des embeddings (représentations vectorielles du sens d'un texte).

Construire les représentations à partir des titres, descriptions, objectifs, défauts recherchés et éléments techniques.

Pour chaque règle CAST, rechercher les règles Semgrep les plus proches.

Effectuer également la recherche inverse pour détecter les règles Semgrep sans correspondance CAST.

Prévoir un moteur local d'embeddings, configurable et remplaçable.

Ne pas comparer toutes les règles deux à deux avec un LLM : utiliser une présélection efficace des candidats.

### 5.3. Étape 3 — Analyse approfondie avec LLM

Prévoir une analyse facultative par un modèle de langage.

Compatible avec :

- Une API de type OpenAI.
- Un serveur local Ollama.
- Un serveur local compatible OpenAI, par exemple llama-server.

Le LLM doit examiner les descriptions disponibles des règles, ainsi que les patterns Semgrep lorsqu'ils apportent des éléments utiles.

Il doit déterminer :

- Le problème effectivement recherché.
- Le contexte technique et les préconditions.
- Les comportements déclenchant une violation.
- Les différences de périmètre.
- Les éventuelles limitations techniques.
- Les éléments justifiant ou contredisant une équivalence.

Chaque conclusion doit être justifiée par des éléments identifiables dans les sources.

Utiliser une sortie JSON structurée, validée par schéma.

Le LLM propose des rapprochements mais ne les valide pas définitivement.

### 5.4. Étape 4 — Classification des correspondances

Attribuer à chaque paire candidate l'un des statuts suivants :

| Statut | Définition |
|---|---|
| Équivalent | Même objectif et conditions de détection substantiellement comparables |
| Partiellement équivalent | Une partie seulement des comportements est commune |
| Complémentaire | Même famille de problèmes, mais contrôles différents |
| Apparenté | Proximité thématique sans couverture comparable établie |
| Sans correspondance identifiée | Aucun rapprochement suffisamment étayé |
| Indéterminé | Documentation insuffisante pour conclure |
| Non comparable | Nature ou portée du contrôle fondamentalement différente |

Autoriser les correspondances 1–N, N–1 et N–N.

Éviter qu'une règle générale CAST soit artificiellement considérée comme équivalente à plusieurs règles Semgrep très spécialisées.

### 5.5. Score et justification

Produire un score de similarité entre 0 et 100, utilisé pour ordonner les candidats et non comme mesure de couverture démontrée.

Afficher séparément :

- Similarité sémantique.
- Compatibilité technique.
- Correspondance des défauts détectés.
- Convergence des préconditions.
- Niveau de preuve disponible.
- Statut de validation humaine.

Les scores doivent être calculés selon une méthode documentée et configurable.

Une équivalence ne peut être affirmée sur le seul fondement d'un score vectoriel élevé.

Si la documentation CAST ne précise pas le mécanisme de détection, ne pas lui attribuer de capacité d'analyse interprocédurale ou inter-fichiers sans preuve.

## 6. Différences de capacités entre les moteurs

Une règle ne doit jamais être évaluée uniquement en fonction de son intitulé.

Prévoir une représentation de la portée technique des contrôles :

- Recherche de motifs syntaxiques.
- Analyse AST (arbre syntaxique abstrait).
- Analyse des flux de données.
- Analyse de propagation de données non fiables (taint analysis).
- Analyse interprocédurale.
- Analyse inter-fichiers.
- Analyse des dépendances et de l'architecture.
- Calcul de métriques structurelles.
- Analyse des relations entre composants ou objets.

Ces capacités ne doivent être attribuées à un outil ou à une règle que lorsqu'elles sont documentées ou démontrées par un test.

Conserver un état « inconnu » lorsque les informations sont insuffisantes.

Identifier les cas dans lesquels un rapprochement sémantique est pertinent mais où les techniques d'analyse rendent l'équivalence incertaine.

## 7. Interface web

Créer une application web responsive, ergonomique et adaptée à l'exploration de plusieurs milliers de règles.

### 7.1. Tableau de bord général

Présenter :

- Nombre de règles CAST.
- Nombre de règles Semgrep.
- Répartition par langage.
- Répartition par catégorie.
- Répartition par sévérité.
- Nombre de rapprochements par statut.
- Nombre de règles sans correspondance identifiée.
- Niveau de complétude des collectes.
- Dates et versions des inventaires.

Afficher des graphiques interactifs permettant d'accéder directement aux règles concernées.

Ne pas assimiler le nombre de règles à une mesure de couverture fonctionnelle ou de qualité d'un moteur.

### 7.2. Explorateur de règles

Créer un tableau interactif avec :

- Recherche plein texte.
- Recherche par identifiant.
- Filtres multisélection.
- Tri sur les colonnes.
- Pagination côté serveur.
- Filtres par langage, framework, catégorie, CWE, sévérité et éditeur.
- Filtres par statut de rapprochement.
- Accès direct aux sources documentaires.

Les filtres doivent être combinables.

### 7.3. Fiche détaillée d'une règle

Afficher les métadonnées disponibles, la description du défaut, le contexte technique, la classification et les références.

Pour les règles Semgrep, présenter le YAML original avec coloration syntaxique.

Afficher les règles de l'autre éditeur proposées comme correspondances, triées par pertinence.

Pour chaque correspondance, présenter une justification des similitudes et différences.

### 7.4. Comparateur côte à côte

Créer une vue permettant de sélectionner une règle CAST et une ou plusieurs règles Semgrep.

Présenter dans deux colonnes :

- Objectif.
- Description.
- Conditions de détection.
- Langages et frameworks.
- Catégories de défauts.
- Références normatives.
- Limitations connues.
- Éléments communs et divergents.

Mettre visuellement en évidence les écarts significatifs.

Permettre une validation, une correction ou un rejet manuel de la correspondance.

### 7.5. Matrice de couverture

Afficher une matrice interactive croisant :

- Les langages.
- Les familles de défauts.
- Les deux catalogues.
- Les correspondances identifiées.

Permettre d'identifier les domaines documentés uniquement par CAST, uniquement par Semgrep ou par les deux.

Distinguer explicitement « aucune règle inventoriée », « collecte incomplète » et « capacité absente démontrée ».

### 7.6. Traçabilité et validation

Conserver l'historique des rapprochements validés et rejetés.

Permettre à un expert de saisir un commentaire et de modifier une classification.

Ne pas écraser automatiquement les décisions humaines lors d'une nouvelle synchronisation.

## 8. Exports et exploitation

Prévoir les exports suivants :

- CSV : inventaire complet CAST.
- CSV : inventaire complet Semgrep.
- CSV : correspondances entre règles.
- XLSX : comparaison avec filtres et onglets de synthèse.
- JSON : données structurées.
- HTML autonome : rapport consultable sans serveur.

Inclure les URL sources, les identifiants, les classifications, les statuts et les informations de traçabilité.

Respecter les droits de réutilisation et de redistribution des contenus des éditeurs. Lorsque nécessaire, exporter les métadonnées et des liens plutôt que les descriptions ou définitions complètes.

## 9. Architecture technique

Privilégier une architecture simple, modulaire et facilement maintenable.

Stack proposée :

**Backend**
- Python 3.12 ou ultérieur.
- FastAPI.
- Pydantic pour les modèles et validations.
- SQLAlchemy pour la persistance.
- PostgreSQL, avec recherche plein texte.
- Connecteurs de collecte indépendants.
- Traitements d'import et de comparaison exécutables en ligne de commande.

**Frontend**
- React et TypeScript.
- Composants graphiques adaptés aux grands tableaux.
- Visualisations interactives.
- Navigation par fiches, catégories et correspondances.

**Analyse sémantique**
- Similarité textuelle déterministe.
- Embeddings locaux ou configurables.
- Index vectoriel, activable sans dépendance obligatoire à un fournisseur distant.
- Fournisseur LLM interchangeable.
- Cache des analyses sémantiques.

**Exploitation**
- Docker Compose.
- Configuration par variables d'environnement.
- Mode hors ligne à partir de catalogues préalablement importés.
- Journalisation exploitable et messages d'erreur explicites.
- Absence d'envoi automatique de données vers des services d'IA externes.

Les connecteurs, la normalisation, le moteur de correspondance et l'interface doivent être clairement séparés.

Ne pas introduire une architecture microservices inutilement complexe.

## 10. Synchronisation et qualité des données

Créer des commandes permettant :

- L'import initial.
- La synchronisation de CAST.
- La synchronisation de Semgrep.
- La reconstruction des classifications.
- Le recalcul des correspondances.
- L'export des résultats.

Les traitements doivent être relançables, idempotents (sans créer de doublons à chaque exécution) et capables de reprendre après une interruption.

Conserver des snapshots datés avec les versions et commits sources.

Mesurer la complétude des imports : pages découvertes, règles analysées, objets ignorés et erreurs.

Mettre en place des contrôles de cohérence, des mécanismes de retry et une limitation du débit des requêtes.

Identifier les règles ajoutées, modifiées ou supprimées entre deux versions.

## 11. Tests et validation

Mettre en place des tests automatisés :

- Tests unitaires des connecteurs.
- Tests de parsing YAML.
- Tests de normalisation.
- Tests de dédoublonnage.
- Tests des correspondances déterministes.
- Tests du classement sémantique.
- Tests de validation JSON des réponses LLM.
- Tests des API.
- Tests de navigation et des principaux filtres.

Constituer un jeu de référence de correspondances revues manuellement pour mesurer précision et rappel.

Prévoir des exemples de :

- Correspondances exactes.
- Correspondances partielles.
- Règles complémentaires.
- Faux rapprochements lexicaux.
- Absence de correspondance.
- Informations insuffisantes.

Ne pas inventer de règles CAST ou Semgrep pour les résultats définitifs. Utiliser les vrais identifiants et liens lorsque les sources sont disponibles.

Les jeux de tests synthétiques sont autorisés à condition d'être explicitement identifiés comme tels.

## 12. Organisation du développement

Réaliser le projet progressivement.

**Phase 1 — Collecte et exploration**

1. Examiner les deux sources officielles.
2. Vérifier les possibilités réelles d'extraction CAST.
3. Implémenter le connecteur Git Semgrep.
4. Concevoir le modèle commun.
5. Collecter et stocker les inventaires.

**Phase 2 — Application consultable**

1. Créer l'API de consultation.
2. Développer le tableau de bord.
3. Développer l'explorateur de règles.
4. Ajouter les fiches détaillées.
5. Implémenter les exports.

**Phase 3 — Comparaison**

1. Implémenter la normalisation.
2. Développer les rapprochements déterministes.
3. Ajouter la recherche sémantique.
4. Introduire la comparaison facultative par LLM.
5. Développer les vues côte à côte.
6. Ajouter la validation humaine.

**Phase 4 — Industrialisation**

1. Optimiser les performances.
2. Compléter les tests.
3. Documenter les traitements.
4. Ajouter la synchronisation incrémentale.
5. Vérifier le fonctionnement hors ligne.
6. Préparer les déploiements reproductibles.

## 13. Critères d'acceptation

Le développement devra permettre au minimum :

1. D'importer toutes les règles YAML valides présentes dans une révision sélectionnée du dépôt officiel Semgrep, sans limite arbitraire sur le nombre de fichiers.
2. D'inventorier les règles CAST publiquement accessibles, en explicitant les éventuelles restrictions de collecte.
3. De rechercher et filtrer efficacement les inventaires.
4. De retrouver les règles pertinentes de l'autre éditeur pour une règle sélectionnée.
5. De produire une justification documentée pour chaque rapprochement proposé.
6. De distinguer les rapprochements automatiques des rapprochements validés.
7. De naviguer depuis une règle jusqu'à sa documentation originale.
8. D'exporter les inventaires et les correspondances.
9. De fonctionner sans service LLM distant.
10. De conserver les versions des sources et la provenance des informations.

L'application ne doit pas présenter les résultats d'une similarité automatique comme une preuve définitive d'équivalence technique.

## 14. Livrables attendus

Créer dans le dépôt :

- Le code source complet du backend et du frontend.
- Les connecteurs CAST et Semgrep.
- Le modèle de données et ses migrations.
- Le moteur de rapprochement.
- Les tests automatisés.
- Les fichiers de configuration.
- Les fichiers Docker Compose.
- Un `README.md` avec les commandes d'installation, d'import, d'exécution et de test.
- Un document `docs/architecture.md`.
- Un document `docs/matching-methodology.md` précisant les critères et limites de comparaison.
- Un document `docs/data-sources.md` décrivant les sources, restrictions et méthodes d'extraction.

## 15. Instructions pour commencer immédiatement

Commence par vérifier les sources officielles et documenter les modalités de récupération réellement utilisables.

Présente brièvement l'architecture retenue et la structure du dépôt.

Ensuite, produis directement le code de la première version fonctionnelle.

Cette première version doit permettre :

- D'importer les règles Semgrep depuis Git.
- D'importer les règles CAST accessibles ou depuis un export lorsque l'accès direct est limité.
- De conserver les données dans une base relationnelle.
- De consulter les deux inventaires depuis une interface web.
- De rechercher des correspondances candidates par des méthodes déterministes.
- D'afficher les règles et leurs liens documentaires.

Poursuis ensuite par l'analyse sémantique et les fonctions avancées.

Privilégie systématiquement du code exécutable et testé, des composants simples, une bonne séparation des responsabilités et des explications précises sur les limitations.

Ne remplace pas une fonctionnalité réalisable par une simulation ou des données fictives.

Lorsque l'accès à une source ne fonctionne pas, produis un diagnostic explicite et implémente un mode de repli exploitable, sans bloquer le reste du développement.