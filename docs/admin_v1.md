# 🛠️ Panel d’administration — Team Baguette v1

Ce document décrit **le fonctionnement réel et validé du panel d’administration** de Team Baguette
tel qu’il existe en **v1**.

Il s’adresse :
- aux administrateurs du site
- aux développeurs maintenant ou faisant évoluer le projet

Ce document est **normatif pour la v1** : il décrit ce qui existe et ce qui est garanti.

---

## 🎯 Rôle du panel admin (v1)

Le panel d’administration permet de gérer **l’ensemble des données structurantes** du site :

- utilisateurs et rôles
- joueurs (participants)
- équipes (abstraction unique)
- tournois
- phases de tournoi
- inscriptions des équipes
- confrontations (series)
- matchs et résultats

Le panel admin est volontairement :
- strict sur les règles métier
- explicite dans ses messages
- cohérent visuellement
- orienté stabilité plutôt que rapidité d’action

---

## 🔐 Accès & sécurité

### Accès

- URL : `/admin`
- Accès réservé aux utilisateurs ayant le rôle `admin`

### Sécurité backend

Toutes les routes admin sont protégées par :
- `@login_required`
- `@role_required("admin")`

⚠️ **Règle fondamentale**  
Aucune action critique n’est basée uniquement sur l’interface :
- toutes les règles sont validées côté serveur
- l’UI peut masquer une action, mais le backend décide toujours

---

## 🧭 Dashboard admin

Le dashboard est le **point d’entrée unique** du panel.

Il donne accès aux modules suivants :
- Utilisateurs
- Joueurs
- Équipes
- Tournois
- Matchs

Il n’existe **aucun module “fantôme” ou désactivé** en v1 :
tout ce qui est affiché est fonctionnel.

---

## 👤 Gestion des utilisateurs

### Fonctionnalités

- liste paginée des utilisateurs
- recherche serveur par nom
- filtre par rôle
- accès à la page d’édition

### Édition d’un utilisateur

Un administrateur peut :
- modifier le rôle
- activer / désactiver un compte
- réinitialiser l’avatar
- réinitialiser le mot de passe

⚠️ Le mot de passe réinitialisé est **fourni à l’administrateur**,
qui est responsable de sa transmission.

### Contraintes

- avatars stockés dans `static/avatars/`
- rôles centralisés (`invité`, `éditeur`, `restreamer`, `admin`)
- désactivation d’un compte immédiatement effective

---

## 🎮 Gestion des joueurs

### Concept

Un **joueur** représente un participant à une compétition.
Il est **indépendant de l’existence d’un compte utilisateur**.

### Fonctionnalités

- création d’un joueur
- modification du nom
- suppression conditionnelle

### Équipe solo (règle v1)

À la création d’un joueur :
- une **équipe solo** est automatiquement créée
- elle est invisible côté UX
- elle sert uniquement à uniformiser la logique

### Suppression d’un joueur

Un joueur **ne peut pas être supprimé** s’il :
- appartient à une équipe multi-joueurs
- ou si son équipe a participé à un match

Ces règles sont vérifiées :
- lors de l’affichage du formulaire
- lors de la requête de suppression

---

## 👥 Gestion des équipes

### Concept

Une **équipe** est l’unité de base de toute confrontation.

- équipe solo : interne, invisible
- équipe multi-joueurs : visible et administrable

### Fonctionnalités

- liste des équipes multi-joueurs
- affichage des joueurs
- création d’équipe multi
- édition du nom et des joueurs
- suppression conditionnelle

### Contraintes

- une équipe multi doit contenir **au moins 2 joueurs**
- une équipe ne peut pas être supprimée si elle est utilisée dans un match

---

## 🏆 Gestion des tournois

### Fonctionnalités

- création et édition de tournois
- sélection du jeu associé
- gestion du statut (`draft`, `active`, `finished`)
- métadonnées descriptives (non critiques)

### Règles métier

- un tournoi terminé ne peut pas être réactivé
- un tournoi ne peut pas être activé sans phase définie
- les équipes ne peuvent être modifiées que tant que le tournoi est en `draft`

---

## 🧱 Phases de tournoi

### Fonctionnalités

- création, édition et suppression de phases
- positionnement explicite des phases
- type de phase (`custom`, groupes, bracket…)

### Contraintes

- une phase ne peut pas être supprimée si des confrontations y sont rattachées
- l’ordre des phases est structurant pour l’affichage public

---

## ⚔️ Confrontations (Series)

### Concept

Une **confrontation** représente un affrontement logique entre deux équipes.

### Fonctionnalités

- création d’une confrontation
- association à une phase
- définition du format (best-of)
- édition limitée une fois des matchs créés

### Contraintes

- une confrontation ne peut pas être supprimée si des matchs existent
- les équipes sont verrouillées dès le premier match créé

---

## 🎮 Matchs & résultats

### Matchs

- création de matchs planifiés
- gestion des tie-breaks (matchs sans série)
- édition de la date tant que le tournoi n’est pas terminé

### Résultats

- saisie structurée des résultats
- gestion des égalités
- calcul automatique des scores de confrontation
- mise à jour du vainqueur de série

⚠️ Toute modification de résultat déclenche un **recalcul serveur**.

---

## 🎨 UX admin (règles communes)

Toutes les pages admin suivent le même pattern UX :

1. Titre de page (`<h1>`)
2. Toolbar (recherche, filtres, actions)
3. Carte contenant tableau ou formulaire
4. Pagination cohérente

Objectifs :
- cohérence visuelle
- compréhension immédiate
- maintenance facilitée

---

## 🏁 Statut v1 — Panel admin

- ✅ toutes les fonctionnalités décrites sont implémentées
- 🔒 règles métier strictes et explicites
- 📚 documentation alignée avec le code réel
- 🚫 aucune promesse hors périmètre v1

👉 **Le panel admin est considéré comme complet et validé pour la v1.**
