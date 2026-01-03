# ✅ Checklist officielle — Validation V1 Team Baguette (état consolidé)

Ce document reflète **l’état réel de validation de la v1**, après audit du code,
de la base de données et de la documentation.

---

## 🧱 1. Architecture & fondations — ✅ VALIDÉ

- [X] Blueprints isolés et cohérents
- [X] Aucun import circulaire ou hack temporaire
- [X] `create_app()` sans logique métier
- [X] Context processors limités et justifiés
- [X] `SECRET_KEY` via variable d’environnement
- [X] Séparation dev / prod
- [X] Taille max d’upload définie (nginx + Flask)

👉 **Bloc validé v1**

---

## 🗄️ 2. Base de données — ✅ VALIDÉ

### Schéma
- [X] `matches.completed` supprimé
- [X] `match_index` conservé (usage UX uniquement)
- [X] Aucun champ ambigu ou obsolète
- [X] Nommage cohérent

### Anticipation brackets (présente mais inactive v1)
- [X] Séries sans équipes possibles
- [X] Champs `source_*` présents
- [X] `bracket_position` présent
- [X] Aucune logique v1 dépendante

### Phases extensibles
- [X] `tournament_phases.details` présent
- [X] Champ descriptif uniquement
- [X] Aucune logique critique liée

### Règles
- [X] Reset BDD assumé avant mise en prod
- [X] Règles de suppression implémentées
- [X] Champs dérivés identifiés

### Documentation
- [X] `database_v1.md` conforme au SQL réel
- [X] Limitations v1 documentées

👉 **Bloc validé v1**

---

## 🧠 3. Logique métier — ✅ VALIDÉ

### Tournois
- [X] Cycle `draft → active → finished`
- [X] Activation impossible sans phase
- [X] Tournoi terminé non réactivable

### Phases & séries
- [X] Phase non supprimable si utilisée
- [X] Série non supprimable si matchs
- [X] Séries créées manuellement (v1 assumé)

### Matchs & résultats
- [X] Parsing fiable
- [X] Gestion des égalités
- [X] Recalcul automatique des résultats
- [X] Tie-breaks isolés

👉 **Bloc validé v1**

---

## 👥 4. Utilisateurs, joueurs, équipes — ✅ VALIDÉ

### Utilisateurs
- [X] Authentification fonctionnelle
- [X] Rôles cohérents
- [X] Comptes inactifs bloqués
- [X] Routes sensibles protégées

### Joueurs
- [X] Équipe solo automatique
- [X] Suppression protégée
- [X] Séparation User / Player respectée

### Équipes
- [X] Équipes solo invisibles
- [X] Équipes multi gérées
- [X] Suppression protégée

👉 **Bloc validé v1**

---

## 🎥 5. Restream — ✅ VALIDÉ

- [X] 0 ou 1 restream par match
- [X] Pages publiques conditionnelles
- [X] Activation / désactivation OK
- [X] Indices cohérents
- [X] Permissions respectées

👉 **Bloc validé v1**

---

## 🌍 6. Partie publique — 🟡 VALIDÉ AVEC LIMITATIONS

- [X] Navigation cohérente
- [X] Statuts de tournois clairs
- [X] Restreams pertinents uniquement
- [X] Pages tournoi / résultats fonctionnelles
- [X] Groupes affichés correctement
- [X] Bracket basé sur séries existantes

⚠️ Limitation assumée :
- génération automatique complète de bracket hors v1

👉 **Bloc validé v1 (limité)**

---

## 🎨 7. UX / CSS — ✅ VALIDÉ

- [X] Aucune valeur hardcodée
- [X] Variables CSS partout
- [X] Light / dark fonctionnels
- [X] UX admin cohérente
- [X] Aucune régression connue

👉 **Bloc validé v1**

---

## 🔒 8. Sécurité minimale — ✅ VALIDÉ

- [X] Routes sensibles protégées
- [X] Backend toujours décisionnaire
- [X] Flash messages cohérents
- [X] Pas d’erreur silencieuse critique

👉 **Bloc validé v1**

---

## 📚 9. Documentation — 🟡 PRESQUE VALIDÉ

- [X] README_v1.md
- [X] `database_v1.md`
- [X] `roadmap_v1.md` à mettre à jour (dernier point restant)
- [X] `admin_v1.md`
- [X] `structure_v1.md`
- [X] Limitations v1 documentées

👉 **Bloc validable après mise à jour de la roadmap**

---

## 🧪 10. Tests manuels — 🟡 À FINALISER

- [X] Création tournoi complète
- [X] Ajout équipes / phases / séries
- [X] Saisie résultats
- [X] Restream création / désactivation
- [X] Navigation publique
- [ ] Repasser un test complet “from scratch” post-reset BDD

---

## 🏁 Statut global v1

🟢 **La v1 est techniquement prête.**

Il reste :
1. Reset BDD propre
2. Dernier run de tests manuels

👉 Après cela, **GO v1 officiel possible**.
