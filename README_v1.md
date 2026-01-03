# 🥖 Team Baguette — Plateforme de compétitions & restream SSR (v1)

**Team Baguette** est une plateforme communautaire dédiée à l’organisation,
au suivi et à la mise en valeur de compétitions de randomizer (SSR principalement,
mais pensée pour être extensible).

La **v1** correspond à une **première version stable**, fonctionnelle et volontairement limitée,
servant de base saine pour les évolutions futures.

---

## 🎯 Objectifs du projet

- Centraliser la gestion des compétitions SSR
- Uniformiser les concepts (équipes, matchs, résultats)
- Fournir un panel admin clair et robuste
- Faciliter le travail des restreamers (indices, visibilité, planning)
- Préserver l’historique des compétitions **dans une logique de long terme**

Le projet privilégie :
- la clarté fonctionnelle
- la cohérence métier
- la stabilité avant l’automatisation avancée

---

## 🧱 Architecture générale

- **Backend** : Flask (Blueprints)
- **Base de données** : SQLite
- **Frontend** : HTML / Jinja + CSS modulaire
- **Déploiement** : Raspberry Pi (Gunicorn + Nginx)

### Organisation fonctionnelle

Les fonctionnalités sont organisées par domaines clairs :

- authentification et comptes utilisateurs
- panel d’administration
- pages publiques
- gestion des tournois et des matchs
- restreams et outils associés (indices, planning)

---

## 🎥 Module Restream (v1)

- Restream lié obligatoirement à un match
- Un match = 0 ou 1 restream
- Gestion par rôles (éditeur / restreamer / admin)
- Indices en temps réel basés sur templates
- Désactivation réversible (suppression logique)
- Planning public des restreams à venir

---

## 🎨 UX & CSS

- Variables CSS centralisées
- Light / dark mode natif
- Aucune valeur codée en dur
- Design system stable et documenté

---

## 📚 Documentation

La documentation détaillée est disponible dans le dossier `docs/` :

- `database_v1.md` — structure de la base de données
- `roadmap.md` — vision et évolutions prévues
- `checklist_v1.md` — périmètre validé de la v1
- `structure.md` — organisation du projet
- `conventions.md` — conventions de code et d’architecture
- `admin.md` — usage du panel d’administration
- `philosophie.md` — principes directeurs du projet

---

## 🗺️ État du projet

Le projet est en **v1** :  
une première version stable, fonctionnelle et assumée.

- Fondations solides
- Module Restream validé
- Gestion des tournois opérationnelle
- Affichages groupes / bracket fonctionnels mais perfectibles
- Base de données figée côté structure

---

## 🧭 Philosophie

- Clarté > astuce
- Uniformité > exceptions
- Historique > suppression
- Lisibilité > optimisation prématurée
