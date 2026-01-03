# 🗂️ Organisation des dossiers — Team Baguette v1

Ce document décrit **l’organisation réelle et validée** des dossiers du projet Team Baguette
pour la **v1**.

Il fait foi pour toute lecture du code, maintenance ou évolution future.

---

## 🌳 Arborescence globale (v1)

```
project_root/
├── .gitignore
├── README_v1.md
├── requirements.txt
│
├── app/
│   ├── __init__.py          ← factory Flask, config, blueprints
│   ├── app.py               ← point d’entrée WSGI
│   ├── config.py            ← configuration applicative (transitoire)
│   ├── database.py          ← accès SQLite (get_db, helpers)
│   │
│   ├── admin/
│   │   ├── __init__.py
│   │   ├── routes.py        ← routes admin
│   │   └── domain.py        ← règles métier critiques
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   └── routes.py
│   │
│   ├── main/
│   │   ├── __init__.py
│   │   └── routes.py
│   │
│   ├── permissions/
│   │   ├── __init__.py
│   │   ├── roles.py         ← définition des rôles
│   │   └── decorators.py   ← décorateurs Flask
│   │
│   ├── restream/
│   │   ├── __init__.py
│   │   └── routes.py
│   │
│   ├── static/
│   │   ├── css/
│   │   ├── js/
│   │   ├── img/
│   │   └── avatars/
│   │
│   └── templates/
│       ├── base.html
│       ├── admin/
│       ├── auth/
│       ├── main/
│       └── restream/
│
├── instance/                ← hors versionnement
│   ├── database.db          ← base active
│   ├── indices/
│   │   ├── templates/
│   │   └── sessions/
│
└── __pycache__/
```

---

## 🧠 Dossier `app/`

Cœur applicatif Flask.

Responsabilités :
- configuration de l’application
- enregistrement des blueprints
- logique métier
- accès à la base de données

### Fichiers clés

- `__init__.py` : création de l’app Flask, config, blueprints, erreurs
- `app.py` : point d’entrée WSGI (Gunicorn)
- `config.py` : configuration applicative (données externes temporaires)
- `database.py` : helpers SQLite

⚠️ `config.py` est **transitoire** en v1 (migration future vers BDD).

---

## 🧩 Blueprints (modules fonctionnels)

Chaque sous-dossier correspond à un **domaine fonctionnel isolé**.

### `admin/`
Panel d’administration :
- utilisateurs
- joueurs
- équipes
- tournois
- phases
- confrontations
- matchs et résultats

### `auth/`
Authentification :
- inscription
- login / logout
- avatars

### `permissions/`
Gestion des permissions :
- rôles
- hiérarchie
- décorateurs Flask

### `main/`
Pages publiques :
- accueil
- profils
- pages tournois publiques

### `restream/`
Fonctionnalités de restream :
- création / gestion
- planning
- indices (templates + sessions)
- SSE

---

## 🎨 Dossier `static/`

Ressources statiques.

### CSS

Organisation normalisée (voir `conventions.md`) :

```
static/css/
├── base/
├── components/
├── features/
└── main.css
```

### Autres assets
- `js/` : scripts JavaScript
- `img/` : images globales
- `avatars/` : avatars utilisateurs

---

## 🖼️ Dossier `templates/`

Templates Jinja, organisés par blueprint.

Objectifs :
- correspondance directe routes ↔ templates
- lisibilité
- absence de collisions

---

## 🗄️ Dossier `instance/`

Dossier **hors versionnement**, contenant les données runtime.

Contenu v1 :
- `database.db` : base SQLite
- `indices/templates/` : templates d’indices
- `indices/sessions/` : sessions actives

⚠️ Aucun code applicatif ne doit dépendre d’un chemin absolu dans `instance/`.

---

## 🧭 Philosophie structurelle

- une responsabilité = un dossier
- isolation stricte des modules
- séparation code / données
- structure lisible sans exécuter le projet

---

📌 Ce document reflète **la structure validée pour la v1**.
Toute modification structurelle doit entraîner une mise à jour explicite.
