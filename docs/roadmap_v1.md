# 🛣️ Roadmap v1 — Team Baguette

Ce document définit **le périmètre officiel de la v1** du projet Team Baguette.

Il ne s’agit pas d’une roadmap prospective, mais d’un **document de cadrage** :
- ce qui est inclus dans la v1
- ce qui est volontairement exclu
- ce qui est reporté après la v1

Toute évolution future devra respecter ce cadre.

---

## 🎯 Objectif de la v1

La v1 vise un produit :

- **stable**
- **cohérent**
- **documenté**
- **exploitable en conditions réelles**

Sans automatisation avancée ni fonctionnalités expérimentales.

La priorité est donnée à :
- la fiabilité métier
- la lisibilité du code
- la préservation de l’historique

---

## ✅ Périmètre fonctionnel inclus (V1)

### 🧱 Fondations techniques
- Architecture Flask modulaire (Blueprints)
- Séparation claire des responsabilités
- Configuration sécurisée (SECRET_KEY, uploads, erreurs)
- Déploiement cible : Raspberry Pi (gunicorn + nginx)

---

### 👤 Utilisateurs & rôles
- Authentification fonctionnelle
- Rôles :
  - invité
  - éditeur
  - restreamer
  - admin
- Comptes désactivables
- Séparation stricte :
  - utilisateur ≠ joueur

---

### 🎮 Joueurs & équipes
- Création de joueurs indépendants des comptes
- Création automatique d’équipes solo
- Équipes multi-joueurs administrables
- Suppressions strictement contrôlées
- Aucune logique spéciale “solo” dans le métier

---

### 🏆 Tournois
- Création et édition de tournois internes
- Statuts :
  - `draft`
  - `active`
  - `finished`
- Activation impossible sans phase
- Tournoi terminé non réactivable
- Données descriptives via `metadata` (non contraignantes)

---

### 🧱 Phases & confrontations
- Phases ordonnées par position
- Séries (confrontations) créées manuellement
- Séries pouvant exister sans équipes définies
- Suppression interdite si dépendances

⚠️ Anticipation bracket présente en base,
sans logique automatique en v1.

---

### 🎮 Matchs & résultats
- Création de matchs liés ou non à une série
- Support BO1 / BO3 / BO5
- Résultats saisis manuellement
- Calcul fiable des vainqueurs
- Gestion des égalités
- Tie-breaks isolés

---

### 🌍 Partie publique
- Page vitrine de tournoi
- Page résultats par phase
- Groupes fonctionnels
- Bracket lisible (limitations assumées)
- Navigation cohérente entre états

---

### 🎥 Restream
- Restream obligatoirement lié à un match
- 0 ou 1 restream par match
- Gestion des rôles (éditeur / restreamer / admin)
- Indices basés sur templates
- SSE fonctionnel
- Désactivation / réactivation propre
- Navbar dynamique des restreams à venir

---

### 🎨 UX & CSS
- Design system unifié
- Variables CSS obligatoires
- Light / dark mode natif
- UX admin homogène
- Aucune valeur hardcodée

---

### 📚 Documentation
- README v1
- database_v1.md
- admin_v1.md
- structure_v1.md
- conventions.md
- philosophie.md
- checklist_v1.md

---

## ❌ Hors périmètre v1 (assumé)

Les éléments suivants sont **volontairement exclus de la v1** :

- Génération automatique des brackets
- Avancement automatique des équipes
- Double élimination
- Bracket graphique continu
- Statistiques avancées
- Tests unitaires exhaustifs
- Internationalisation
- UX mobile avancée

Ces points sont reportés **après validation complète de la v1**.

---

## 🟢 Critère de validation v1

La v1 est considérée comme **officiellement validée** lorsque :

- la checklist v1 est entièrement cochée
- aucune refonte BDD n’est nécessaire
- les limitations sont documentées
- le site est utilisable :
  - par les admins
  - par les restreamers
  - par le public

---

## 🧭 Après la v1

Les évolutions post-v1 se feront :

- sans dette structurelle
- sans casser l’historique
- par couches successives

La roadmap post-v1 fera l’objet d’un document séparé.

---

📌 Ce document fait foi pour le périmètre de la **v1 officielle**.
