# Philosophie du projet — Team Baguette (v1)

Ce document définit les principes fondateurs du projet Team Baguette.
Il est **normatif** : toute évolution du projet doit respecter ces règles,
sauf décision explicite documentée en post-v1.

---

## Objectif du projet

Team Baguette est une plateforme communautaire permettant :
- l’organisation de compétitions (joueurs, équipes, tournois, phases, séries),
- la publication de résultats lisibles,
- la gestion de restreams (planning, indices, activation/désactivation).

Le projet vise une **v1 stable, compréhensible et maîtrisée**, volontairement limitée.
La priorité est donnée à la clarté et à la fiabilité plutôt qu’à l’automatisation.

---

## Principes directeurs

### 1. Clarté avant sophistication
- Une solution simple et lisible est toujours préférée à une solution “maligne”.
- Toute logique doit pouvoir être comprise rapidement par un nouveau contributeur.
- Les effets implicites sont évités autant que possible.

### 2. Séparation stricte des responsabilités
- Les templates servent uniquement à l’affichage.
- Aucune logique métier ne doit se trouver dans les templates.
- Le backend est l’unique source de vérité.

### 3. Architecture modulaire
- Chaque module fonctionnel possède :
  - ses routes,
  - ses templates,
  - sa logique métier principale.
- Des fonctions **utilitaires transverses** peuvent exister dans des modules partagés,
  à condition qu’elles soient génériques, sans dépendance métier forte.

### 4. Sécurité par conception
- Toute route sensible est protégée par :
  - une authentification (`login_required`),
  - et un contrôle de rôle explicite.
- La sécurité backend prime toujours sur les protections UI.

### 5. Données avant interface
- La base de données est considérée comme le socle du projet.
- L’interface s’adapte aux données, jamais l’inverse.
- Les données ne doivent pas être altérées pour des raisons d’affichage.

### 6. Historique et traçabilité
- Les suppressions destructrices sont évitées.
- Lorsqu’un élément est désactivé, son historique est conservé.
- La traçabilité prime sur le “nettoyage” esthétique.

---

## Règles explicites (ce que le projet ne fait pas)

- ❌ Pas de logique métier dans les templates.
- ❌ Pas de CSS inline ou de styles isolés hors du système unifié.
- ❌ Pas de données “magiques” ou implicites non documentées.
- ❌ Pas d’automatisation opaque qui masque l’état réel des données.

---

## Références

Ce document est complété par :
- `conventions.md` — règles techniques et conventions de développement.
- `css-ux-validation.md` — décisions CSS & UX actées en v1.

Ces documents font foi dès lors qu’ils sont compatibles avec la présente philosophie.
