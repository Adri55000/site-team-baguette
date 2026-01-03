# Conventions de développement — Team Baguette (v1)

Ce document définit les conventions techniques du projet Team Baguette.
Il est **normatif** : toute nouvelle modification du code doit respecter ces règles.

Ces conventions décrivent la **règle cible** du projet.
Des écarts peuvent exister dans du code plus ancien, mais **aucune nouvelle régression
ne doit être introduite**.

---

## Hiérarchie des règles

Les conventions sont classées selon leur importance :

- 🔴 **Règles bloquantes**  
  Non-respect = modification refusée.
- 🟡 **Règles fortes**  
  À respecter sauf raison claire et documentée.
- ⚪ **Bonnes pratiques**  
  Recommandées, mais non bloquantes.

---

## Backend (Flask / Python)

### Architecture générale
🔴 Chaque fonctionnalité est organisée en **module** clairement identifié.

🔴 Les routes, templates et logique métier sont séparés conceptuellement.

🟡 La logique métier principale appartient au module fonctionnel concerné.

⚪ Des fonctions utilitaires génériques peuvent être mutualisées dans des modules partagés,
à condition qu’elles soient transverses et sans dépendance métier forte.

---

### Routes
🔴 Les routes doivent rester lisibles et structurées  
*(contrôles → traitement → réponse)*.

🟡 En v1, une partie de la logique métier peut se trouver dans les routes
(héritage du projet). Toutefois :
- on évite d’y ajouter de la complexité inutile,
- on privilégie l’extraction progressive dès qu’une portion devient réutilisable,
- toute nouvelle fonctionnalité non triviale doit, si possible, être extraite
dans une fonction métier dédiée.

🟡 **Règle d’évolution** : lorsqu’on modifie une route existante,
on cherche à améliorer la situation (extraction, clarification),
sans refactor massif obligatoire.

🔴 Toute route sensible doit être protégée par :
- une authentification,
- un contrôle de rôle explicite.

⚪ Une route peut contenir de la logique d’orchestration,
mais les règles métier et algorithmes doivent tendre vers des fonctions dédiées.

---

## Données & base de données

🔴 La base de données est la **source de vérité** du projet.

🔴 Les données ne doivent jamais être modifiées pour satisfaire un besoin d’affichage.

🟡 Les suppressions destructrices sont évitées lorsque l’historique a une valeur fonctionnelle.

⚪ Toute modification impactant la structure des données doit être documentée.

---

## Templates (Jinja)

🔴 Les templates sont dédiés **uniquement à l’affichage**.

🔴 Aucune logique métier ne doit se trouver dans les templates.

🟡 Les templates doivent rester simples et lisibles,
même au prix d’un affichage moins optimisé.

⚪ Les templates peuvent contenir des conditions d’affichage mineures,
sans impact métier.

---

## CSS / UX

🔴 Le CSS suit une approche **systémique et unifiée**.

🔴 Aucune valeur de style ne doit être hardcodée hors des variables définies.

🔴 Le CSS inline est interdit.

🟡 Les composants partagés doivent être stylés de manière générique et réutilisable.

⚪ Les styles spécifiques à une page doivent rester limités
et clairement identifiés.

---

## Organisation du code

🟡 Le nommage doit être cohérent, explicite et homogène.

🟡 Les nouveaux fichiers doivent respecter la structure existante du projet.

⚪ Le code doit être commenté lorsque l’intention n’est pas évidente.

---

## Erreurs courantes à éviter

- Mettre de la logique métier dans un template “pour aller plus vite”.
- Ajouter du CSS spécifique sans vérifier l’existant.
- Dupliquer une logique au lieu de mutualiser proprement.
- Modifier des données pour corriger un problème d’affichage.

---

## Références

Ce document est complété par :
- `philosophie.md` — principes fondateurs du projet.
- `structure.md` — organisation concrète des fichiers.
- `css-ux-validation.md` — décisions CSS & UX actées en v1.

Ces documents font foi conjointement.
