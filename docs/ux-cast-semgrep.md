# Parcours CAST → Semgrep

Correction du 28 octobre 2026.

## Objectif principal

Montrer, pour chaque règle CAST, quelles règles Semgrep sont candidates ou ont été déclarées équivalentes par un expert. La consultation des catalogues et l’incertitude soutiennent ce parcours.

## Comportement livré

- L’accueil présente une liste paginée de règles CAST, chacune face à ses règles Semgrep candidates.
- Les règles CAST sans candidat restent présentes ; un filtre permet de les isoler.
- Les identifiants et titres des deux éditeurs sont visibles ensemble. Chaque paire ouvre sa comparaison avec sources, propositions LLM éventuelles et avis expert.
- Le score automatique est un classement. Un avis expert « équivalent » porte un libellé distinct. Aucun score ne valide automatiquement l’équivalence.
- Les règles avec avis d’équivalence sont placées en tête, puis les autres règles avec candidats, puis les règles sans candidat. Au sein des aperçus, les paires équivalentes et partielles précèdent les autres candidats ; les avis négatifs sont conservés et identifiés.
- Les compteurs et la pagination dénombrent des règles CAST. Un aperçu affiche au plus trois paires ; leur nombre total et l’accès à la fiche complète sont explicites.
- La recherche accepte un identifiant/intitulé CAST ou Semgrep. Le filtre langage et le filtre CWE portent sur CAST.
- L’explorateur ouvre CAST par défaut, avec accès direct à chaque catalogue et réinitialisation des filtres. Les filtres Semgrep sont masqués, désactivés et vidés quand cet éditeur n’est pas sélectionné.
- Après comparaison, le retour retrouve la liste d’origine et ses filtres.

## Recette

1. Ouvrir l’accueil et vérifier la présence simultanée des règles CAST et de leurs candidats Semgrep.
2. Isoler les règles CAST sans candidat, ouvrir une fiche, puis revenir à la liste filtrée.
3. Ouvrir directement une paire, consulter les sources et revenir aux correspondances.
4. Depuis les statistiques d’incertitude, ouvrir Semgrep puis choisir CAST : les règles CAST redeviennent visibles.
5. Rechercher un identifiant Semgrep et retrouver les règles CAST liées.
6. Les règles supprimées ne contribuent pas aux compteurs de paires actives ; seule la dernière décision experte détermine le filtre d’équivalence.
