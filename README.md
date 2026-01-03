# Team Baguette

Team Baguette est une application web permettant de **gérer et suivre des compétitions**  
(tournois, phases, groupes, brackets, résultats) avec un **module de restream** intégré.

Le projet est aujourd’hui en **version 1**, considérée comme **stable et utilisable en conditions réelles**.

Ce dépôt contient le **code source** et la **documentation de référence**.

---

## Objectif du projet

Team Baguette vise à fournir un outil :
- fiable et maîtrisé,
- lisible dans son fonctionnement,
- orienté données plutôt qu’automatisation opaque.

La v1 privilégie la **clarté**, la **stabilité** et la **maîtrise manuelle** des compétitions.
Les automatisations avancées et nouveaux formats sont envisagés **post-v1**.

---

## Fonctionnalités principales (v1)

- Gestion des comptes et rôles
- Panel d’administration complet
- Gestion des joueurs, équipes et tournois
- Phases multiples par tournoi
- Groupes (round robin)
- Bracket simple élimination
  - gestion des byes
  - calcul des qualifiés
  - propagation automatique du vainqueur au round suivant (si existant)
- Séries et matchs avec résultats
- Calcul automatique du gagnant d’une série
- Module **Restream**
  - 1 restream ↔ 1 match
  - indices basés sur templates
  - activation / désactivation propre
- Conservation de l’historique (peu de suppressions destructrices)

➡️ Le périmètre exact de la v1 est détaillé dans la documentation dédiée.

---

## Hors périmètre v1 (exemples)

- Automatisation complète entre phases
- Double élimination / Swiss
- Statistiques avancées
- API publique
- Refonte graphique majeure

Ces points sont abordés dans la roadmap post-v1.

---

## Stack technique

- **Backend** : Python / Flask
- **Frontend** : Jinja, HTML, CSS
- **Base de données** : SQLite
- **Temps réel** : SSE (restream)
- **Déploiement** : environnement Linux (prod manuelle)

---

## Installation locale (développement)

Prérequis :
- Python 3.10+ recommandé
- Environnement virtuel (venv)

### 1. Cloner le dépôt
```bash
git clone <repo-url>
cd team-baguette
```

### 2. Créer un environnement virtuel
```bash
python -m venv venv
source venv/bin/activate   # Linux / macOS
venv\Scripts\activate    # Windows
```

### 3. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 4. Lancer l’application

Le projet est prévu pour être lancé via **Gunicorn**, avec l’application exposée dans `app.app:app`.

Exemple (développement ou production simple) :
```bash
gunicorn app.app:app
```

Selon la configuration, certaines données runtime sont créées dans le dossier `instance/`.

---

## Documentation

La documentation du projet est structurée et fait foi :

- `v1.md` — périmètre fonctionnel de la v1
- `structure.md` — structure du projet
- `database.md` — base de données et schéma
- `admin.md` — panel d’administration
- `conventions.md` — règles de développement
- `css-ux-validation.md` — décisions UX / CSS
- `git.md` — organisation Git et workflow
- `roadmap_post_v1.md` — évolutions envisagées post-v1

---

## Bugs et retours

Les retours et bugs peuvent être signalés via les **issues GitHub**.
Aucune promesse de support ou de contribution externe n’est faite à ce stade.

---

## Statut

- Version : **v1**
- État : **stable**
- Évolutions : prévues post-v1, voir roadmap

---

## Licence

Ce projet est publié **sans licence open-source**.

Le code est rendu public à des fins de lecture et de transparence.
Toute réutilisation, modification ou redistribution n’est pas autorisée sans accord explicite.
