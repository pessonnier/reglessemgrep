# Sources de données et limites

Vérification effectuée le 26 octobre 2026.

## CAST

Le [site actuel CAST Rules](https://technologies.castsoftware.com/) propose un accès public et un formulaire de connexion CAST Extend. Son interface charge les données JSON depuis `/api/quality-rules`, `/api/quality-rules/{id}` et `/api/aip/technologies`. Le formulaire officiel transmet `uid`, `xtkn` et `xpwd` à `/api/sso/authenticate` ; son JavaScript encode le mot de passe en base64 avant l’envoi HTTPS. L’encodeur n’est pas une mesure de chiffrement : HTTPS protège le transport.

Lors de la vérification, l’index public contenait 2 828 identifiants. Un détail public était limité à quelques champs ; le même détail après connexion contenait aussi description, remédiation, critères et standards. Les routes actuelles sont observées depuis le site, sans engagement de stabilité d’une API publique documentée. L’[ancien Swagger CAST](https://technologiesv1.castsoftware.com/swagger-ui/) reste une référence historique distincte.

Le connecteur tente la connexion uniquement si `CAST_USERNAME` et `CAST_PASSWORD` sont fournis. Si elle n’ouvre pas les champs étendus, il poursuit avec les données publiques. Chaque réponse de règle est archivée séparément avec un manifeste de complétude ; une collecte interrompue peut reprendre. Une archive complète de même mode est réutilisée par défaut. Le programme ne contourne aucune restriction d’accès.

## Semgrep

L’inventaire provient du [dépôt officiel semgrep-rules](https://github.com/semgrep/semgrep-rules). Une révision Git précise est conservée dans le manifeste et sur chaque règle. Le parser compte les objets de `rules` dans les fichiers `.yaml` et `.yml`, y compris plusieurs règles par fichier. Les fixtures `*.test.yaml` et `*.test.yml` sont ignorées ; les erreurs de parsing ou de structure sont consignées dans le rapport d’import.

Ce dépôt contient les règles Community Edition. Les règles Semgrep Pro ne sont pas inventoriées. Le [contrat de licence Semgrep Rules](https://semgrep.dev/legal/rules-license/) limite la redistribution ; le dépôt téléchargé reste local et les exports ne contiennent que des métadonnées et liens.

La version P0 vérifie le parsing YAML et la présence des champs structurels requis (`id`, `message`, `severity`, `languages`). Elle ne remplace pas la validation complète par le moteur Semgrep pour chaque règle ; cette limite est visible dans le rapport d’import.

