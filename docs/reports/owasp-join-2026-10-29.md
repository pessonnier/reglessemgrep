# Bilan de la jointure OWASP — 29 octobre 2026

Comparaison avant/après sur le même inventaire local, sans nouvelle collecte : 2 828 règles CAST et 2 153 règles Semgrep. Paramètres inchangés : seuil 18/100, 15 candidats maximum par règle CAST. Versions sources : CAST `20261026T142558Z-authenticated`, Semgrep `16b9e6d45f10649f6a531ec4838ed9924372c3bc`. Moteur avant : `deterministic-v1` ; après : `deterministic-v2-owasp`.

| Mesure | Avant | Après | Évolution |
| --- | ---: | ---: | ---: |
| Paires CAST–Semgrep conservées | 4 516 | 4 516 | 0 |
| Règles CAST avec au moins une paire | 580 | 580 | 0 |
| Règles Semgrep avec au moins une paire | 785 | 785 | 0 |
| Paires partageant une référence OWASP | 3 139 | 3 139 | 0 |

**Nouvelles paires : 0. Paires retirées : 0. Scores modifiés : 0.** Aucun remplacement de paire n’est masqué par un total constant : les ensembles de clés sont identiques. Aucune règle CAST ou Semgrep précédemment sans candidat n’est nouvellement reliée.

La conversion `A03-2021` → `A03:2021` était déjà appliquée à l’import et le bonus OWASP de 10 points existait déjà. Le renforcement unifie désormais les parseurs, accepte les espaces, libellés et tirets typographiques, récupère les références brutes anciennes et normalise également au moment de la comparaison et de l’indexation. Les familles et éditions restent distinctes ; la sélection et les pondérations ne sont pas relâchées pour produire artificiellement davantage de paires.

172 fiches CAST voient leurs identifiants OWASP Mobile normalisés (`M7-2016` → `M07:2016`, etc.). Le catalogue Semgrep présent ne contient pas de référence Mobile commune : cette normalisation ne crée donc pas de paire. Les 172 fiches normalisées ne sont pas 172 règles nouvellement jointes.

Parmi les 3 139 paires avec OWASP commun, 239 n’ont aucun CWE commun. Ce nombre indique des paires bénéficiant du bonus OWASP sans CWE ; il ne mesure pas combien disparaîtraient si le critère OWASP était désactivé.

Les valeurs originales et les références sourcées sont conservées. Un score classe une candidature ; il ne prouve pas l’équivalence des principes de détection.
