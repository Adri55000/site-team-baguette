# Roadmap post‑v1 — Team Baguette

Ce document définit la **roadmap unique post‑v1** du projet Team Baguette.
Il est orienté **évolutions fonctionnelles** et **n’inclut pas le périmètre v1**, déjà figé et documenté ailleurs.

La roadmap exprime des **intentions et priorités**, pas des engagements calendaires.
Elle peut évoluer, mais sert de cadre décisionnel.

---

## Vision post‑v1

Positionnement :
- approche **pragmatique** (entre outil interne et plateforme plus générique),
- priorité donnée aux **nouvelles fonctionnalités utiles**,
- automatisation ciblée, sans complexité excessive ni perte de maîtrise.

La v1 étant considérée comme stable, l’objectif post‑v1 est d’**enrichir les usages** plutôt que de refondre l’existant.

---

## Axes stratégiques

### 1. Automatisation des compétitions (axe prioritaire)

Objectif :
- réduire le travail manuel,
- fiabiliser les enchaînements,
- conserver la lisibilité des données.

Évolutions envisagées :
- automatisation complète groupes → bracket,
- génération automatique de brackets,
- propagation automatique des résultats entre phases.

Limites assumées :
- pas de planification automatique complexe,
- pas d’optimisation algorithmique avancée à court terme.

---

### 2. Nouveaux formats de compétition

Formats envisagés :
- bracket **double élimination**,
- format **Swiss** (à étudier et cadrer),
- ouverture à d’autres formats si un besoin réel apparaît.

Notes :
- le round robin avancé est déjà techniquement faisable avec l’existant,
- les tie‑breaks sont gérables (partiellement manuels),
- pas de système de formats custom généralisé prévu à ce stade.

---

### 3. Évolution du module Restream

Orientation :
- évolution progressive, sans refonte brutale.

Pistes identifiées :
- ajout d’un **module de tracking collaboratif**,
- tracking temps réel via **SSE**,
- permettre à plusieurs personnes distantes de contribuer au tracking,
- réduire la charge sur la personne en charge du restream.

Le restream reste un module central, mais maîtrisé.

---

### 4. Nouveaux modules fonctionnels

Pistes long terme identifiées :
- module **Tutoriels / Guides** :
  - installation d’outils (ex : randomizer),
  - stratégies, tricks, glitches,
  - contenu pédagogique structuré.

Ces modules sont indépendants du cœur “tournoi” et peuvent évoluer séparément.

---

### 5. Navigation & structure UI

Objectif :
- absorber de nouvelles fonctionnalités **sans complexifier la navigation**.

Évolutions possibles :
- refonte ciblée de la navbar,
- meilleure hiérarchisation des sections,
- support de nouveaux jeux sans surcharge visuelle.

Aucune refonte UX globale n’est prévue, uniquement du **polish progressif si nécessaire**.

---

## Hors périmètre explicite (post‑v1)

Ne sont pas prioritaires :
- statistiques avancées,
- API publique,
- exports de données,
- refonte graphique majeure,
- CI/CD avancé,
- monitoring ou infrastructure lourde.

Ces sujets pourront être réévalués ultérieurement si un besoin réel apparaît.

---

## Technique & qualité

Positionnement :
- pas d’objectif de couverture de tests exhaustive,
- ajout de tests automatisés **uniquement s’ils sont pertinents et utiles**,
- pas de migrations automatiques complexes prévues.

La stabilité et la lisibilité priment sur l’industrialisation.

---

## Priorité globale

Priorité absolue post‑v1 :
**développement de nouvelles fonctionnalités**, la base actuelle étant jugée stable.

La dette technique est surveillée, mais n’est pas un axe moteur à court terme.

---

## Conclusion

Cette roadmap :
- sert de **cadre de décision**,
- n’impose pas de planning,
- assume des évolutions progressives,
- laisse la place à l’expérimentation maîtrisée.

Toute évolution majeure devra rester cohérente avec :
- la philosophie du projet,
- la structure existante,
- la lisibilité globale du système.
