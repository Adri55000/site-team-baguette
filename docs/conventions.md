# 📘 Conventions du projet Team Baguette

Ce document regroupe **l’ensemble des conventions adoptées** pour le projet Team Baguette.
Il sert de **référence commune** pour garantir :
- cohérence du code
- lisibilité
- maintenabilité à long terme

Il couvre :
- CSS / frontend
- structure du site
- conventions backend
- principes de données

---
L’uniformisation CSS et UX du projet est décrite et validée dans
`docs/Uniformisation CSS & UX — Validation officielle.`
Ce document fait foi pour toute évolution future du frontend.

## 🎨 1. Conventions CSS (officielles)

### 1.1 Approche générale : Component‑First + BEM léger

Le projet utilise une convention **simple, explicite et très adaptée à Flask**.

#### ✔ 1. Chaque page ou module = un namespace CSS

Exemples :
- `.profile-...`
- `.restream-...`
- `.admin-...`
- `.tournament-...`
- `.matches-...`

Cela évite les collisions et permet d’identifier immédiatement l’origine d’un style.

---

#### ✔ 2. Structure des classes

Format recommandé :

```
.feature-element
.feature-element-sub
.feature-element--modifier
```

Exemples :
- `.profile-header`
- `.profile-header-info`
- `.profile-section--highlight`

- `.restream-indices-table`
- `.restream-indices-table--compact`

- `.admin-card`
- `.admin-card-header`
- `.admin-card--inactive`

---

#### ✔ 3. Un fichier CSS par feature

Localisation :

```
static/css/features/<feature>.css
```

Chargement :
- via `main.css` pour les pages publiques
- ou directement dans les templates admin si nécessaire

---

#### ✔ 4. Pas d’ID pour le styling

- Les **ID sont réservés au JS**
- Le CSS doit se baser **uniquement sur des classes**

---

#### ✔ 5. Pas de styles génériques dans les features

Les fichiers `features/*.css` **ne doivent contenir que des styles spécifiques**.

Les styles globaux sont définis dans :

```
static/css/base/
static/css/components/
```

---

#### ✔ 6. Modifiers = double tiret `--`

Pour représenter un état ou une variation :

```
.admin-card--inactive
.restream-category--empty
.profile-actions--inline
```

---

#### ✔ 7. Imbrication limitée

Toujours préférer :

```
.feature-element-sub
```

Plutôt que :

```
.feature .element .subelement
```

Objectif : CSS lisible, stable et peu fragile.

---

#### ✔ 8. Variables CSS obligatoires

Toutes les couleurs, espacements et constantes doivent utiliser les variables définies dans :

```
static/css/base/variables.css
```

Aucune valeur « magique » en dur.

---

## 🧩 2. Organisation frontend

### 2.1 Structure CSS

```
static/css/
├── base/
├── components/
├── features/
└── main.css
```

- `base/` : reset, layout, variables
- `components/` : boutons, formulaires, navbar…
- `features/` : styles par page ou module

---

### 2.2 UX admin

Toutes les pages admin doivent suivre **le même pattern UX** :

- Titre `<h1>`
- Toolbar (recherche / actions)
- Carte contenant la table
- Pagination standardisée

Objectif : **uniformité totale** entre users / players / teams / etc.

---

## 🗂️ 3. Conventions backend (Flask)

### 3.1 Séparation claire des concepts

- **users** : comptes du site
- **players** : participants aux compétitions
- **teams** : abstraction unique pour tous les formats

Ne jamais mélanger ces notions.

---

### 3.2 Routes admin

- Toutes les routes admin doivent avoir :
  - `@login_required`
  - `@role_required("admin")`

- Les règles métier critiques doivent être **validées côté serveur**, même si l’UI les masque.

---

### 3.3 Règles de suppression

- Suppressions **jamais implicites**
- Toujours vérifier les dépendances (équipes, matchs, historique)
- Toujours protéger côté backend

---

## 🧠 4. Conventions de données / logique métier

### 4.1 Joueurs vs utilisateurs

- Un joueur peut exister sans utilisateur
- Un utilisateur peut ne pas être joueur

Cette séparation est **fondamentale**.

---

### 4.2 Équipes solo (règle structurante)

- Chaque joueur a automatiquement une équipe solo
- Cette équipe :
  - est invisible côté UX
  - sert uniquement à uniformiser la logique

Aucune logique spéciale ne doit être ajoutée dans le code pour gérer le solo.

---

### 4.3 Uniformisation des matchs

- Tous les matchs sont : **équipe vs équipe**
- Même un duel solo passe par des équipes
- Les tie-breaks utilisent des matchs multi-équipes

---

## 🧭 5. Philosophie générale du projet

- **Clarté > astuce**
- **Uniformité > exceptions**
- **Historique > facilité de suppression**
- **Lisibilité > micro-optimisation**

Le projet est pensé pour :
- évoluer sans dette technique
- rester compréhensible dans le temps
- être repris facilement

---

📌 Ce document doit être considéré comme **la référence officielle des conventions**.
Toute nouvelle feature doit s’y conformer.

