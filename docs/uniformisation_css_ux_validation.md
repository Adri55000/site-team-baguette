# 🎨 Uniformisation CSS & UX — Validation officielle

Ce document acte l’**uniformisation complète du CSS et de l’UX** du projet Team Baguette.
Il fait suite à l’audit et au nettoyage intégral des styles globaux et des features.

---

## ✅ État global

L’ensemble des fichiers CSS du projet respecte désormais les règles suivantes :

- ❌ aucune couleur codée en dur (`#fff`, `#000`, `rgba(...)`, etc.)
- ❌ aucune logique locale `dark-mode` dans les features
- ✅ toutes les couleurs, ombres et contrastes passent par des **variables CSS**
- ✅ compatibilité light / dark garantie par construction

---

## 🧱 Règles structurantes (désormais figées)

### 1️⃣ Variables obligatoires

Toute valeur visuelle doit être exprimée via une variable :

- couleurs (`--bg-*`, `--text-*`, `--primary`, etc.)
- bordures (`--border-color`)
- ombres (`--shadow-sm`, `--shadow-md`, `--shadow-lg`)
- overlays et dégradés (`--overlay-*`)

Même une couleur **utilisée par une seule page** (ex: indices) doit être une variable.

---

### 2️⃣ Aucune exception par colonne ou composant

- aucune colonne de tableau ne doit avoir un style différent sans raison métier
- l’alternance se fait **par ligne uniquement**
- pas de `nth-child()` pour des effets décoratifs

Objectif : lisibilité et stabilité visuelle.

---

### 3️⃣ Séparation claire des niveaux CSS

- `base/` : variables, reset, layout
- `components/` : boutons, formulaires, navbar
- `features/` : styles spécifiques **sans valeurs hardcodées**

Un composant global ne dépend **jamais** d’une variable de feature.

---

## 🎯 Cas particuliers assumés

### Indices

La page *indices* utilise une identité colorée spécifique.

Ces couleurs sont :
- **centralisées dans les variables**
- documentées
- indépendantes du thème light / dark

Cela permet une forte identité visuelle **sans casser le design system**.

---

## 🏁 Conclusion

Le projet dispose désormais d’un **design system stable, cohérent et extensible**.

Toute nouvelle feature doit :
- réutiliser les variables existantes
- en introduire de nouvelles uniquement si nécessaire
- ne jamais introduire de valeurs visuelles codées en dur

👉 Cette uniformisation est considérée comme **terminée et validée**.

