# Modèle de dossier de validation d’un principe

Statut initial : à rédiger et à revoir. Ce fichier est un modèle ; il ne constitue ni un cas exécuté ni une preuve d’équivalence.

## Identité et sources

- Identifiant du principe et version du dossier : à renseigner.
- Règle CAST : ID, URL, version/date d’archive et empreinte du détail.
- Règle Semgrep : clé stable, ID, chemin, commit et SHA-256 de la définition.
- Références : CWE/norme, version, section, URL et extrait pertinent.
- Origine de chaque affirmation : source documentaire, proposition LLM ou interprétation experte.

## Contrat de détection

- Défaut recherché et conséquence : à renseigner.
- Langage/framework/API/versions et unité d’analyse : à renseigner.
- Préconditions, source et destination des données si pertinentes : à renseigner.
- Assainisseurs et exceptions : à renseigner.
- Portée de l’analyse étayée par les sources : à renseigner.
- Périmètre commun, différences, informations inconnues : à renseigner.

## Cas à créer (tâche S6.2)

| ID stable | Fichiers et SHA-256 | Nature | Attente du principe | Attente CAST documentée | Attente Semgrep documentée | Ligne/unité attendue | Justification | Auteur/relecteur |
|---|---|---|---|---|---|---|---|---|
| V1 | À créer | Vulnérable | À valider | Inconnue | Inconnue | À préciser | À rédiger | À désigner |
| V2 | À créer | Vulnérable, variante | À valider | Inconnue | Inconnue | À préciser | À rédiger | À désigner |
| S1 | À créer | Correction de V1 | À valider | Inconnue | Inconnue | À préciser | À rédiger | À désigner |
| S2 | À créer | Correction de V2 | À valider | Inconnue | Inconnue | À préciser | À rédiger | À désigner |
| L1 | À créer | Limite ciblant un faux positif | À valider | Inconnue | Inconnue | À préciser | À rédiger | À désigner |
| L2 | À créer | Limite ciblant une non-détection | À valider | Inconnue | Inconnue | À préciser | À rédiger | À désigner |

Pour chaque cas : origine/licence du code, dépendances requises, étiquette oracle (`vulnerable`, `safe`, `out_of_scope`, `unknown`), justification indépendante, date de revue et version gelée avant analyse. Ne jamais adapter l’oracle au seul résultat de l’analyseur.

## Campagne (après implémentation du runner)

- Identifiant, date, hash du manifeste/corpus : non exécuté.
- Semgrep : moteur/version/édition/options, empreinte de règle, sortie brute, code retour, erreurs, résultats par cas.
- CAST : moteur/version/extensions/configuration, règle activée, empreintes du corpus, export brut et résultats par cas. Sans export, indiquer « non exécuté ».
- Exclusions, suppressions, parsing, timeouts et cas non pris en charge : à relever.
- TP/FP/FN/TN et dénominateurs par moteur et périmètre : non mesurables avant exécution.
- Divergences, contre-exemples et dimensions non testées : à documenter.

## Conclusion experte

- Résultat : indéterminé.
- Type de soutien : documentaire / Semgrep exécuté seul / confrontation des deux moteurs.
- Périmètre exact de la conclusion : à renseigner.
- Incertitude, risques FP/FN, limites et actions restantes : non évalués.
- Auteur, date, version du dossier validée : à renseigner.
