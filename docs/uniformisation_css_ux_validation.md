# Validation CSS & UX — Team Baguette (v1)

Ce document recense les **décisions CSS & UX actées** pour la v1.
Il est **normatif** : toute évolution UI/CSS doit respecter ces règles, sauf décision explicitement documentée.

Objectif v1 : **cohérence, lisibilité, stabilité**.  
L’optimisation fine et les refontes lourdes sont hors périmètre v1.

---

## Principes généraux

- La lisibilité prime sur l’effet visuel.
- L’uniformité prime sur l’exception.
- Le backend reste la source de vérité ; l’UI s’y adapte.
- L’UX doit être prévisible (pas de comportements “magiques”).

---

## Système CSS

### Variables
- Toutes les couleurs, espacements, rayons, tailles et ombres sont définis via des **variables CSS**.
- Aucune valeur “en dur” ne doit être ajoutée hors variables.

### Interdictions
- ❌ CSS inline
- ❌ styles ad hoc non réutilisables
- ❌ duplication de règles existantes

### Composants
- Les composants partagés (cartes, tableaux, boutons, badges, listes) ont un style générique.
- Les variantes doivent être explicites (classes dédiées), pas implicites.

---

## Hiérarchie visuelle

- Les titres structurent la page (hiérarchie claire).
- Les informations critiques sont mises en évidence sans surcharge.
- Les séparations visuelles sont sobres (lignes fines, espacements cohérents).

---

## Tables & listes (admin et public)

- Les tableaux privilégient la lisibilité :
  - colonnes alignées,
  - en-têtes explicites,
  - pas d’icônes ambiguës.
- Les actions sont clairement identifiables (icône + texte si nécessaire).
- Les séparations “logiques” (ex : qualifiés / non qualifiés) restent discrètes.

---

## Formulaires

- Libellés explicites.
- Messages d’erreur clairs et proches du champ concerné.
- Pas de validation silencieuse.
- Les champs obligatoires sont clairement identifiés.

---

## États & feedback utilisateur

- États désactivés visibles (opacité, style dédié).
- États actifs/inactifs cohérents sur l’ensemble du site.
- Toute action impactante doit avoir un feedback visible.

---

## Brackets, groupes et affichages complexes

- L’affichage doit rester lisible avant d’être exhaustif.
- Les solutions choisies en v1 évitent la complexité excessive.
- Les cas particuliers (ex : byes) sont traités sans casser la structure existante.

L’amélioration de ces affichages est prévue **post-v1**.

---

## Responsive & compatibilité

- La v1 est pensée **desktop-first**.
- Le responsive existe mais n’est pas optimisé mobile-first.
- Aucun comportement mobile ne doit casser la lisibilité.

---

## Hors périmètre v1

- Refonte graphique globale
- Animations complexes
- Thèmes multiples avancés
- Optimisation mobile poussée

---

## Validation

Les règles ci-dessus sont considérées comme **validées v1**.
Toute dérogation doit être :
- justifiée,
- documentée,
- assumée comme exception.

---

## Références

- `philosophie.md`
- `conventions.md`
- `structure.md`
