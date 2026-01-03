# 🥖 Team Baguette — Plateforme de compétitions & restream SSR

**Team Baguette** est une plateforme communautaire dédiée à l’organisation,
au suivi et à la mise en valeur de compétitions de randomizer (SSR principalement,
mais pensée pour être extensible).

Le projet vise à centraliser :

- la gestion des compétitions
- les joueurs et équipes
- les matchs et résultats
- le restream et ses outils (indices, overlays, planning)

L’objectif est de fournir une base **cohérente, durable et maintenable**
pour remplacer progressivement les outils externes (Google Docs, feuilles manuelles, etc.).

---

## 🎯 Objectifs du projet

- Centraliser la gestion des compétitions SSR
- Uniformiser les concepts (équipes, matchs, résultats)
- Fournir un panel admin clair et robuste
- Faciliter le travail des restreamers (indices, visibilité, planning)
- Préserver **l’historique** des compétitions sur le long terme

Le projet privilégie :
- la clarté fonctionnelle
- la cohérence métier
- la stabilité avant l’automatisation avancée

---

## 🧱 Architecture générale

- **Backend** : Flask (Blueprints)
- **Base de données** : SQLite
- **Frontend** : HTML / Jinja + CSS modulaire
- **Déploiement cible** : Raspberry Pi (gunicorn + nginx)

### Organisation par modules

Chaque fonctionnalité est isolée dans son propre module :

- `auth` : authentification et comptes utilisateurs
- `admin` : panel d’administration
- `main` : pages publiques
- `restream` : restreams et indices
- `tournaments` : tournois internes
- `matches` : matchs, planning et résultats

---

## 🎥 Module Restream (V1-ready)

- Restream lié obligatoirement à un match
- Un match = 0 ou 1 restream
- Gestion par rôles (éditeur / restreamer / admin)
- Indices en temps réel basés sur templates
- Désactivation réversible (suppression logique)
- Navbar dynamique des restreams à venir

---

## 🎨 UX & CSS

- Variables CSS centralisées
- Light / dark mode natif
- Aucune valeur codée en dur
- Design system stable et documenté

---

## 📚 Documentation

La documentation détaillée est disponible dans le dossier `docs/` :

- `database.md`
- `roadmap.md`
- `v1.md`
- `structure.md`
- `conventions.md`
- `admin.md`
- `philosophie.md`

---

## 🗺️ État du projet

Le projet est en **pré-v1 avancée**.

- Fondations solides
- Module Restream terminé et validé
- Affichages groupes / bracket fonctionnels mais perfectibles
- Base de données proche d’un état figé

---

## 🧭 Philosophie

- Clarté > astuce
- Uniformité > exceptions
- Historique > suppression
- Lisibilité > optimisation prématurée
