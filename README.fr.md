# France 2027 Signal Lab

[English](README.md) · **Français**

**Des signaux sourcés sur l’élection présidentielle française.**

**France 2027 Signal Lab (FR27)** est un tableau de bord public et indépendant consacré au suivi et à l’analyse de l’élection présidentielle française de 2027.

Il réunit dans une même interface les sondages publiés, l’activité des candidats et des campagnes, les enjeux de fond, la couverture médiatique, les vérifications factuelles, les événements de campagne et les hypothèses de second tour publiées.

**Tableau de bord en ligne**

Français · https://france2027.app/

English · https://france2027.app/?lang=en

**Dépôt GitHub**

https://github.com/openeventbits/france-2027-signal-lab

![Espace Candidats de France 2027 Signal Lab](docs/assets/candidate-workspace.jpg)

*Capture de la version en production. Les données et la couverture des sources évoluent à mesure que de nouveaux éléments sont publiés.*

## Ce que fait France 2027 Signal Lab

FR27 suit une course présidentielle encore mouvante sans réduire des types de données différents à un score unique ou à une prévision.

Ses principaux espaces comprennent les éléments suivants.

* **Ce qui a changé.** Un relevé des évolutions récentes concernant la campagne, les sondages, le second tour, les vérifications factuelles et les développements judiciaires significatifs.

* **La course en un coup d'œil.** Des sondages de premier tour présentés individuellement avec leurs dates de terrain, leurs hypothèses, la configuration des candidatures, leurs sources et le contexte nécessaire à leur comparaison.

* **Couverture médiatique.** Un suivi sourcé de la couverture électorale avec la visibilité des candidats, les thèmes, les éditeurs et l’activité récente.

* **Candidats.** Des données sur les sondages, l’activité de campagne, les thèmes associés, la structure de la couverture médiatique, les éléments faisant l’objet d’un examen critique et des dossiers sourcés pour chaque candidat.

* **Agenda et enjeux.** Un suivi de l’évolution des stratégies de campagne et des principaux thèmes de fond.

* **Événements de campagne.** Les activités programmées, les dossiers documentés liés aux événements, le suivi du calendrier et les changements de programme.

* **Second tour.** Les tests publiés pour le second tour, les confrontations les plus fréquentes, les écarts et l’historique des scénarios comparables.

La couverture peut également être consultée dans le **Lecteur de couverture électorale** et dans **Analyse de la couverture**. L’espace **Réseau de sources** donne une vue sur l’univers de collecte configuré par FR27.

FR27 est descriptif. Il organise et présente les éléments disponibles sans chercher à prédire le résultat de l’élection.

## Comment lire FR27

Plusieurs principes encadrent la manière dont les données sont présentées.

**Des éléments sourcés.** Les signaux significatifs doivent pouvoir être reliés à leur source ou à leur provenance.

**Aucune couche prédictive.** FR27 ne publie ni moyenne de sondages, ni prévision électorale, ni probabilité de victoire, ni recommandation de vote, ni score propriétaire attribué aux candidats.

**Uniquement des éléments comparables.** Les scénarios de sondage reposant sur des configurations de candidatures différentes ne sont pas silencieusement fusionnés dans une même tendance.

**Aucune valeur manquante inventée.** Une information absente, indisponible, partielle ou non résolue n’est pas transformée en faux zéro ou en estimation.

**Des mesures limitées au corpus.** Les mesures concernant les médias et l’agenda décrivent les éléments observés dans le corpus de sources accepté par FR27. Elles ne sont pas présentées comme une mesure de l’ensemble des médias français ni comme une mesure de l’opinion publique.

Lorsqu’un élément ne peut pas être extrait, rapproché, classé, daté ou attribué avec un niveau de confiance suffisant, FR27 privilégie son omission ou l’affichage explicite d’un état non résolu plutôt qu’un résultat trompeur.

## Espaces d’analyse

| Enjeux et politiques publiques | Événements de campagne |
| --- | --- |
| ![Espace Enjeux et politiques publiques de France 2027 Signal Lab](docs/assets/policy-issues-workspace.jpg) | ![Espace Événements de campagne de France 2027 Signal Lab](docs/assets/campaign-events-workspace.jpg) |
| Évolution des thèmes, variations hebdomadaires, associations avec les candidats et éléments sourcés. | Calendrier vérifié, dossiers documentés, événements à venir et historique des changements de programme. |

## Précautions d’interprétation

Certaines mesures de FR27 demandent une attention particulière.

Les sondages de premier tour sont conservés comme des événements complets plutôt que comme une série de scores isolés par candidat. L’historique comparable exige des scénarios compatibles et les scénarios incomplets restent explicitement identifiés comme tels.

L’indicateur d’attention sur Wikipédia mesure la **consultation des articles de Wikipédia en français**. Il ne mesure ni le nombre de personnes uniques, ni le sentiment, ni l’approbation, ni le soutien électoral, ni l’intention de vote.

La couverture médiatique décrit les contenus acceptés dans l’univers de sources de FR27. La visibilité des candidats et la couverture des thèmes doivent donc être comprises comme des mesures du corpus et non comme des mesures du soutien électoral.

L’espace **Ce qui a changé** est un relevé dérivé des évolutions récentes et non un fil d’actualité généraliste. Sa logique de datation distingue le moment où un développement politique intervient du moment où le système le détecte ou régénère les données correspondantes.

Les définitions complètes des mesures et leurs limites sont présentées dans [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## Ingénierie et publication

FR27 est avant tout un produit public statique fondé sur des données et du code versionnés et consultables.

Son architecture combine les éléments suivants.

* Des pipelines Python pour la collecte, la normalisation, la classification et la génération des données.

* Des contrats de données explicites et des identifiants déterministes.

* Des fichiers JSON générés pour la publication.

* Des registres de sources et de provenance.

* Des validations automatisées et des tests de régression.

* Des workflows de production GitHub Actions.

* Des contrôles du manifeste de publication.

* Une interface JavaScript et CSS publiée avec GitHub Pages.

Les processus automatisés qui écrivent les données de production sont conçus pour échouer de manière sûre. Les sorties concernées sont générées et validées avant leur publication. La dernière version valide reste disponible lorsqu’une nouvelle version ne satisfait pas aux règles prévues.

Le dépôt contient actuellement des chaînes de publication distinctes pour les sondages, les données de second tour, le statut et les signaux des candidats, les événements de campagne, les vérifications factuelles, les actualités et la couverture médiatique, les changements récents, l’historique de l’agenda, l’attention portée aux candidats et l’état des sources.

## Documentation

La documentation est organisée selon sa fonction afin d’éviter de reproduire les mêmes informations dans le README.

* [`docs/PRODUCT_GUIDE.md`](docs/PRODUCT_GUIDE.md) présente la manière de lire le tableau de bord et ses différents espaces.

* [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) décrit le périmètre de recherche, la définition des mesures, les classifications, les règles de comparabilité et les limites.

* [`docs/DATA_AND_PROVENANCE.md`](docs/DATA_AND_PROVENANCE.md) décrit les jeux de données publics, les sources, la provenance, l’actualisation des données et les limites du corpus.

* [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) présente les pipelines, les contrats, les fichiers générés, l’interface, les workflows et l’architecture de publication.

* [`docs/OPERATIONS.md`](docs/OPERATIONS.md) décrit les validations, les mises à jour de production, la gestion des échecs, l’intégrité de la publication et la reproductibilité.

* [`CONTRACT.md`](CONTRACT.md) définit les invariants du dépôt et des données qui ne doivent pas être enfreints.

Le contrat du dépôt fait autorité pour les règles fondamentales concernant notamment l’intégrité des événements de sondage, l’identité déterministe, la comparabilité des scénarios, le traitement des données manquantes, l’autorité de l’univers des candidats et les mécanismes d’échec sécurisé.

## Transparence des sources et limites

FR27 dépend de sources externes parmi lesquelles des éditeurs de presse, des instituts de sondage, des organismes publics, des candidats et partis politiques, les services Wikimedia et d’autres sources d’information accessibles au public.

Certaines sources peuvent devenir indisponibles, modifier leur format, cesser de publier ou se trouver en dehors de l’univers de collecte configuré. Les dates de mise à jour, l’état des sources, les avertissements, la provenance et les situations non résolues sont affichés lorsqu’ils sont pertinents plutôt que masqués par le système.

L’intégration automatisée d’un contenu dans le corpus d’actualités électorales ne constitue pas une vérification éditoriale indépendante de chaque article ni de chaque affirmation d’origine. Les utilisateurs sont invités à consulter les sources originales lorsqu’ils évaluent les éléments présentés.

## Licences et réutilisation

Le dépôt est accessible au public et son code source peut être consulté, mais le logiciel n’est pas distribué sous une licence reconnue comme open source par l’OSI.

* Le logiciel original de France 2027 Signal Lab est placé sous **PolyForm Noncommercial License 1.0.0**.

* Les autres contenus originaux protégés sont placés sous **Creative Commons Attribution-NonCommercial 4.0 International Licence (CC BY-NC 4.0)** sauf indication contraire.

* Les contenus provenant de tiers restent soumis aux droits, licences, conditions des sources ou règles juridiques qui leur sont applicables.

Toute utilisation commerciale des contenus originaux protégés de France 2027 Signal Lab nécessite une autorisation distincte.

FR27 ne revendique aucun droit exclusif sur des faits pouvant être obtenus indépendamment au seul motif qu’ils apparaissent dans le projet.

Les conditions complètes figurent dans [`LICENSE`](LICENSE), [`NOTICE`](NOTICE), [`CONTENT_LICENSE.md`](CONTENT_LICENSE.md) et [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Contributions

Les signalements de bugs, les corrections factuelles, les corrections de sources, les problèmes de reproductibilité et les corrections de documentation sont les bienvenus.

FR27 n’accepte pas actuellement de contributions externes substantielles et non sollicitées portant sur du code ou d’autres contenus susceptibles d’être protégés par le droit d’auteur. Les modalités sont précisées dans [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Indépendance et statut

France 2027 Signal Lab est un projet public de recherche développé de manière indépendante. Il n’est affilié à aucun candidat, parti politique, institut de sondage, éditeur, organisme public ou autre organisation représentée dans ses données. Il n’est ni soutenu ni exploité pour le compte de l’une de ces entités.

FR27 suit activement une course présidentielle encore mouvante. Les jeux de données, le statut des candidats, la couverture des sources, les classifications, les interfaces et les méthodes de production peuvent évoluer à mesure que de nouveaux éléments deviennent disponibles.

Pour toute demande concernant les autorisations ou une licence commerciale

**contact@france2027.app**
