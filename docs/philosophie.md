# 🧭 Philosophie de conception — Team Baguette

Ce document présente la **philosophie globale de conception** du projet Team Baguette.
Il ne décrit pas le *comment* (implémentation), mais le *pourquoi* des choix structurants.

Il complète les documents :
- `database.md` (modèle de données)
- `conventions.md` (règles techniques)

---

## 🧱 Architecture générale

Le projet adopte une **architecture modulaire basée sur les Blueprints Flask**.

Chaque fonctionnalité majeure est isolée dans son propre module :

- `auth` : authentification, comptes utilisateurs
- `admin` : administration globale
- `main` : pages publiques, profils
- `restream` : restreams, indices

### Objectifs de cette architecture

- Ajouter ou modifier une fonctionnalité **sans impacter les autres**
- Maintenir un code **lisible et segmenté**
- Faciliter la contribution future (même après une longue pause)
- Éviter les fichiers monolithiques

👉 Chaque module possède :
- ses routes
- ses templates
- sa logique métier

---

## 🎨 Philosophie CSS — par fonctionnalités

Le CSS suit une **approche par responsabilité fonctionnelle**, non par type de composant global.

### Organisation

- `css/base/`
  - reset
  - variables
  - layout
  - dark / light mode

- `main.css`
  - point d’entrée
  - importe base, components et features

- `css/components/`
  - boutons
  - formulaires
  - navbar

- `css/features/`
  - un fichier par fonctionnalité :
    - `admin.css`
    - `profile.css`
    - `restream.css`
    - `tournament.css`

### Pourquoi ce choix

- Éviter les collisions de styles
- Limiter la taille des fichiers
- Identifier immédiatement l’origine d’un style
- Faciliter les refontes ciblées

👉 Un style appartient **à une feature**, pas à une page abstraite.

---

## 🧠 Simplicité conceptuelle avant tout

Le projet privilégie systématiquement :

- des **règles simples mais universelles**
- plutôt que des cas particuliers

### Exemple clé : les équipes

- Tous les matchs sont **équipe vs équipe**
- Un joueur solo est modélisé comme une **équipe solo**
- Cette équipe solo est **invisible côté UX**

👉 Ce choix évite :
- la duplication de logique
- les branches conditionnelles complexes
- les bugs liés aux cas “exceptionnels”

---

## 🧩 Séparation stricte des concepts

### Utilisateur ≠ Joueur

- **Utilisateur** : compte du site (authentification, rôles)
- **Joueur** : participant à une compétition

Ils peuvent être liés, mais ne sont **jamais confondus**.

Pourquoi ?
- permettre des joueurs externes
- ne pas forcer l’inscription au site
- garder une BDD flexible

---

## 🔒 Sécurité & permissions

La sécurité repose sur des **règles explicites et non implicites**.

### Principes

- Toute route sensible est protégée par :
  - `login_required`
  - `role_required(...)`

- L’UI peut masquer une action
  - mais **le backend valide toujours**

- Aucune action critique n’est basée uniquement sur le frontend

### Exemple

Même si le bouton "Supprimer" n’apparaît pas :
- la route vérifie toujours les dépendances
- la suppression peut être refusée côté serveur

---

## 🧭 Préservation de l’historique

L’historique des compétitions est considéré comme **prioritaire**.

Conséquences :

- un joueur ne peut pas être supprimé s’il a joué un match
- une équipe ne peut pas être supprimée si elle a participé
- les restreams restent toujours cohérents

👉 Le projet préfère **interdire une action** plutôt que casser l’historique.

---

## 🧠 Évolution progressive

Le projet est conçu pour évoluer **par couches** :

1. base solide (joueurs, équipes)
2. tournois
3. matchs
4. exploitation (restream, stats)

Chaque couche repose sur la précédente.

👉 On évite les implémentations prématurées.

---

## 🧘 Philosophie générale

- **Clarté > astuce**
- **Uniformité > exceptions**
- **Lisibilité > optimisation prématurée**
- **Historique > confort de suppression**

Le code doit rester :
- compréhensible
- modifiable
- durable

---

📌 Ce document sert de **boussole** pour toutes les décisions futures du projet à partir de la v1.
