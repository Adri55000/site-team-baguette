# 📚 Base de données — Team Baguette v1 (structure validée)

> **Statut** : Structure validée v1  
> **Données** : données de développement (reset avant mise en production)

---

## 🎯 Objectif de la base de données

La base de données Team Baguette modélise de manière **cohérente, durable et extensible** :

- les utilisateurs du site
- les joueurs (participants aux compétitions)
- les équipes (abstraction unique pour tous les formats)
- les tournois, leurs phases et confrontations
- les matchs et résultats
- les restreams et leurs outils associés

La structure est considérée comme figée pour la v1.
Toute évolution future devra préserver l’historique et se faire par migration explicite.

---

## ⚠️ Note importante — Données v1

La v1 marque une **rupture nette avec les données de développement**.

> 🔄 **La base de données sera intégralement réinitialisée juste avant la mise en production v1.**

Les données actuellement présentes :
- servent uniquement aux tests et au développement
- ne sont **pas représentatives** de la production
- peuvent contenir des incohérences historiques

👉 **Seule la structure de la base est validée pour la v1.**

---

## 🧠 Principe fondamental : abstraction par les équipes

Tous les affrontements sont modélisés comme :

> **équipe vs équipe**

- un joueur solo est représenté par une **équipe solo**
- une équipe multi-joueurs représente un groupe réel
- aucune logique spéciale “solo” n’existe dans le code métier

Ce choix :
- simplifie toute la logique des matchs
- évite les cas particuliers
- rend le modèle extensible (double élimination, FFA, etc.)

---

## 👤 Utilisateurs vs Joueurs

### Utilisateurs (`users`)
Représentent les **comptes du site** :
- authentification
- rôles
- administration
- restream

Un utilisateur **peut exister sans être joueur**.

### Joueurs (`players`)
Représentent les **participants aux compétitions**.

- peuvent être liés à un utilisateur (`user_id`)
- peuvent être totalement indépendants (joueurs externes)

👉 **Séparation stricte et volontaire** entre comptes et participants.

---

## 👥 Équipes

### Table `teams`
Une équipe est l’unité de base de toute confrontation.

- `tournament_id` NULL → équipe solo globale
- `tournament_id` non NULL → équipe multi liée à un tournoi

### Équipes solo (règle v1)

À la création d’un joueur :
- une **équipe solo** est créée automatiquement via trigger SQL
- cette équipe :
  - est invisible côté UX
  - sert uniquement à l’uniformisation logique

---

## 🏆 Tournois

### Table `tournaments`

Champs notables :
- `status` : `upcoming`, `active`, `finished`
- `source` : `internal` ou externe
- `metadata` : données **strictement descriptives**

⚠️ **Règle v1**  
Aucune logique métier ne dépend de `metadata`.

---

## 🧱 Phases de tournoi

### Table `tournament_phases`

Une phase décrit la structure d’un tournoi :
- ordre (`position`)
- type (`custom`, `groups`, `bracket`, etc.)
- nom affiché

#### Champ `details`
- champ libre (TEXT / JSON)
- descriptif uniquement
- anticipant les formats futurs

⚠️ **Règle v1**  
Aucune logique critique ne dépend de `details`.

---

## 🧩 Confrontations (Series)

### Table `series`

Une **série** représente une confrontation logique dans un tournoi.

Caractéristiques :
- peut exister **sans équipes définies**
- peut recevoir ses équipes :
  - directement (`team1_id`, `team2_id`)
  - depuis le résultat d’une autre série

### Anticipation bracket (v1)

Champs dédiés :
- `source_team1_series_id`
- `source_team2_series_id`
- `source_team1_type` (`winner` / `loser`)
- `source_team2_type`
- `bracket_position` (UX uniquement)

⚠️ **Règle v1**
- champs présents mais non contraignants
- aucune logique métier v1 ne dépend d’eux

---

## 🎮 Matchs

### Table `matches`

- `series_id` nullable
- `match_index` :
  - optionnel
  - réservé à l’UX
  - **non structurant v1**
- `is_completed` : état réel du match

⚠️ Le champ `completed` a été **supprimé** avant la v1.

---

## 🧮 Résultats

### Table `match_teams`

Associe :
- un match
- une équipe

Avec :
- `final_time`
- `final_time_raw`
- `is_winner` (champ dérivé)

⚠️ En cas d’égalité :
- aucune équipe n’est marquée gagnante

---

## 🎥 Restreams

### Table `restreams`

- un match → **0 ou 1 restream**
- suppression logique (`is_active`)
- indices liés via template

---

## ❌ Règles de suppression (v1)

Pour préserver l’historique :
- joueur : suppression interdite si historique
- équipe : suppression interdite si utilisée
- série : suppression interdite si matchs existants
- phase : suppression interdite si séries liées

---

## 🏁 Statut v1 — Base de données

- ✅ structure validée
- 🔄 données reset avant mise en production
- 🚫 aucune dette structurelle connue

👉 **La base de données est conforme et figée pour la v1.**
