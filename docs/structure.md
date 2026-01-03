# Structure du projet — Team Baguette (v1)

Ce document décrit l’organisation des fichiers et dossiers du projet Team Baguette.
Il est **normatif** : toute évolution du projet doit respecter cette structure.

Le dossier `app/` constitue le **cœur du projet**.
Tout le code applicatif doit s’y trouver.

---

## Arborescence de référence (v1)

```text
projet/
├── README.md
├── requirements.txt
├── app/
│   ├── context.py
│   ├── database.py
│   ├── errors.py
│   ├── jinja_filters.py
│   ├── admin/
│   ├── auth/
│   ├── main/
│   ├── modules/
│   ├── permissions/
│   ├── restream/
│   ├── static/
│   └── templates/
└── instance/
    └── indices/
        ├── templates/
        └── sessions/
```

---

## Racine du projet

### README.md
Document principal du dépôt.
Présente le projet, son périmètre, les prérequis et les liens vers la documentation.

### requirements.txt
Liste des dépendances Python nécessaires au fonctionnement du projet.

---

## app/ — Cœur applicatif

Le dossier `app/` contient l’intégralité du code Flask :
- initialisation de l’application,
- configuration,
- logique applicative,
- blueprints,
- frontend.

Aucun code métier ne doit exister en dehors de ce dossier.

---

## Fichiers Python racine de app/

### context.py
Définition du contexte global injecté dans l’application (helpers globaux, données partagées).

### database.py
Fichier centralisé de gestion de la base de données.
Il contient uniquement des fonctions globales liées à l’accès et à la gestion de la BDD.
Aucune logique métier spécifique ne doit s’y trouver.

### errors.py
Gestion centralisée des erreurs (handlers Flask).

### jinja_filters.py
Définition des filtres Jinja personnalisés utilisés dans les templates.

---

## Blueprints

Chaque dossier suivant correspond à un Blueprint Flask distinct et doit rester séparé.

### admin/
Blueprint dédié au panel d’administration.
Contient les routes, templates et logique associée à la gestion interne.
Toutes les routes sont protégées par authentification et permissions.

### auth/
Blueprint dédié à l’authentification.
Centralise la gestion des comptes, connexions et déconnexions.

### main/
Blueprint public.
Contient les routes accessibles sans privilèges administratifs.

### restream/
Blueprint dédié aux fonctionnalités de restream.
Interagit avec les données stockées dans `instance/indices/`.

### permissions/
Gestion centralisée des rôles et permissions.
Utilisé transversalement par les autres blueprints.

---

## modules/

Dossier de modules Python réutilisables.
Peut contenir :
- de la logique métier partagée,
- des utilitaires transverses génériques.

Les modules ne doivent pas être couplés à un blueprint spécifique.

---

## Frontend

### templates/
Templates Jinja dédiés exclusivement à l’affichage.
Aucune logique métier ne doit s’y trouver.

### static/
Ressources statiques (CSS, images, icônes).
Les fichiers générés à runtime (ex : avatars utilisateurs) ne doivent pas être versionnés.

---

## instance/ — Données d’instance

Le dossier `instance/` contient les éléments liés à l’instance de déploiement.

### indices/
Dossier lié aux indices et au restream.

- templates/ : templates d’indices (versionnés).
- sessions/ : données runtime de session (non destinées à être versionnées).

---

## Règles générales

- Toute nouvelle fonctionnalité doit être intégrée dans `app/`.
- Les responsabilités doivent être clairement séparées.
- Les blueprints doivent rester distincts.
- Les données runtime ne doivent pas être versionnées par erreur.

---

## Références

- philosophie.md
- conventions.md
- database.md
