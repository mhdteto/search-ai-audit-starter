# Démarrer un audit recherche web et IA

[English README](../README.md) · [Explorer les rapports dans le navigateur](https://mhdteto.github.io/authority-architecture-system/) · [Méthode complète](https://github.com/mhdteto/authority-architecture-system)

Ce guide permet de prendre en main les outils de Mohammed Teto, puis de préparer une observation de votre propre site. Il s'adresse aux responsables de l'identité, du contenu, de la communication et du référencement d'un dirigeant ou d'une organisation, quel que soit le marché étudié.

## 1. Créer votre espace de travail

Sur la page du [Starter](https://github.com/mhdteto/search-ai-audit-starter), choisissez **Use this template → Create a new repository**. Donnez un nom à votre copie et choisissez sa visibilité. Pour travailler uniquement sur votre ordinateur, utilisez **Code → Download ZIP**, puis décompressez l'archive.

Ouvrez un terminal dans le dossier qui contient `audit.py`. Python 3.10 ou plus récent est recommandé ; le workflow GitHub est vérifié avec Python 3.12. Vérifiez votre version :

```sh
python3 --version
```

Aucun paquet Python ni compte auprès d'un fournisseur d'IA n'est nécessaire. Sur Windows, si votre installation utilise `py -3`, remplacez `python3` dans les commandes locales. L'Action GitHub fournie est actuellement vérifiée sur un runner Linux.

## 2. Apprendre avec l'exemple fictif

Depuis la racine du dossier :

```sh
python3 audit.py demo
```

La commande rejoue cinq outils sur les données **entièrement fictives** d'Alex Rowan et Cedar Notes. Elle remplace les rapports de cette démonstration ; gardez vos propres observations ailleurs. Aucun site cible ni moteur d'IA n'est interrogé.

Les 17 fichiers générés se trouvent dans `examples/fictional-workflow/reports/`. Ouvrez l'un des rapports HTML dans votre navigateur. Sur Mac, vous pouvez par exemple utiliser :

```sh
open examples/fictional-workflow/reports/identity/report.html
```

Résultats pédagogiques attendus :

| Rapport | Ce que vous devez retrouver |
| :--- | :--- |
| Identité | 4 profils, 2 champs divergents et 3 champs manquants. Ce sont des comptes de champs, pas un score. |
| Preuves | 3 affirmations, dont une contradiction et une affirmation sans preuve fournie. |
| Citations | Anglais / Royaume-Uni : 2 réponses citées sur 4. Français / France : 1 sur 2. Les deux groupes restent séparés. |
| Découvrabilité | Des réponses HTTP inventées, dont une page 200, un canonical, robots.txt et un sitemap. |
| JSON-LD | 0 erreur et 0 avertissement dans un sous-ensemble structurel pédagogique. |

Les fractions de 50 % sont fabriquées pour l'exemple. Elles ne mesurent aucune visibilité réelle. Lisez les [commandes exactes et les versions figées](../examples/fictional-workflow/README.md) pour comprendre les entrées de chaque outil.

## 3. Observer une page réelle séparément

Remplacez l'URL d'exemple par une page publique que vous êtes autorisé à examiner :

```sh
python3 audit.py live https://example.org/ --output-dir reports/live
```

Ouvrez `reports/live/report.html` et conservez `report.json` avec sa date de collecte. Le rapport doit indiquer `live public HTTP(S)`. Ce parcours observe une page, robots.txt et au plus un sitemap candidat, avec un maximum de 12 requêtes HTTP en comptant les redirections.

Il ne collecte pas de réponses ChatGPT, Gemini, Claude ou Perplexity. Les profils et citations fictifs ne sont pas ajoutés à ce rapport réel. Un HTTP 200, un canonical ou du JSON-LD lisible ne prouve ni indexation, ni positionnement, ni citation par une IA. Un HTTP 404 peut être correctement enregistré dans un rapport : la réussite d'exécution signifie que les observations ont été produites.

## 4. Transformer l'observation en décision

Complétez la [fiche de cadrage](../notes/project-brief.md), le [registre d'observations](../notes/observation-register.csv) et le [registre de décisions](../notes/decision-register.csv). Notez l'entité, la source, la date, le marché, la langue, le responsable et ce qui reste inconnu.

Pour les autres outils, adaptez les commandes de la démonstration à des entrées approuvées et à un dossier `reports/` distinct. Suivez les [consignes sur les données](../inputs/README.md). `inputs/private/` et `reports/` sont ignorés par git ; vérifiez toujours les fichiers que vous vous apprêtez à publier. Une copie publique du dépôt ne convient pas aux données confidentielles.

Gardez séparés les moteurs, interfaces, versions de prompts, langues et marchés. Une traduction n'assure pas l'équivalence de deux observations. La vérification des affirmations et de la pertinence des sources reste humaine.

## 5. Utiliser GitHub sans installation locale

Dans votre copie : **Actions → Observe an authorized public page → Run workflow**. Remplacez l'URL d'exemple, lancez le workflow, puis téléchargez l'artefact `live-discoverability`. Décompressez-le et ouvrez `report.html`.

Ce déclenchement est manuel. L'artefact est conservé sept jours ; il peut être accessible à d'autres personnes selon la visibilité du dépôt. Le workflow de vérification par défaut utilise uniquement l'exemple fictif. L'[Action réutilisable](https://github.com/mhdteto/search-ai-audit-action) et le [protocole de mesure](measurement-protocol.md) expliquent les limites à préserver.

## Continuer

- [Étude de cas réelle sur trois pages de MohammedTeto.com](https://github.com/mhdteto/authority-architecture-system/tree/main/case-studies/mohammedteto-com), avec réponses publiques archivées et vérification hors ligne.
- [Trois tutoriels métier](https://github.com/mhdteto/authority-architecture-system/tree/main/tutorials), en anglais, avec exemples fictifs reproductibles.
- [Questions et FAQ](https://github.com/mhdteto/authority-architecture-system/discussions) et [propositions de contribution](https://github.com/mhdteto/search-ai-audit-starter/issues).

Créé par **Mohammed Teto — AI Reputation & Authority Strategist**, pour une pratique indépendante et internationale. [mohammedteto.com](https://mohammedteto.com/) · Documentation originale : CC BY 4.0 ; code : MIT, sous réserve des notices incluses.
