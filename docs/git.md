# Git / GitHub — Organisation et workflow (Team Baguette)

Ce document décrit l’organisation Git et le workflow GitHub du projet Team Baguette.
Il est **normatif** : toute contribution au projet doit respecter ce fonctionnement,
afin de garantir la stabilité de la branche principale et de la production.

---

## Dépôt GitHub

Le projet est hébergé sur GitHub.
Le dépôt GitHub est considéré comme la **source de vérité** du code.

---

## Branches

Le projet utilise une organisation simple à deux branches principales :

- `main`  
  Branche stable.
  Elle correspond à l’état déployé (ou déployable) en production.

- `dev`  
  Branche de développement.
  Toute modification du code doit être effectuée sur cette branche.

Règle :
- on ne travaille **jamais directement sur `main`**.

---

## Workflow standard

Le workflow de développement est le suivant :

1. Se placer sur la branche `dev`
2. Effectuer les modifications
3. Committer les changements sur `dev`
4. Merger `dev` vers `main`
5. Pousser `main` sur GitHub
6. Mettre à jour la production en récupérant `main`

Si cette séquence est respectée, la production reste stable.

---

## Commandes usuelles

### Vérifier la branche active
```bash
git branch
```

### Se placer sur `dev`
```bash
git checkout dev
```

### Mettre à jour `dev`
```bash
git pull origin dev
```

### Committer les modifications
```bash
git status
git add .
git commit -m "description claire de la modification"
```

### Merger `dev` vers `main`
```bash
git checkout main
git merge dev
```

### Pousser `main` sur GitHub
```bash
git push origin main
```

### Mettre à jour la production
Sur la machine de production :
```bash
git pull origin main
```

---

## Cas d’erreurs courants

- Si `git pull` refuse de s’exécuter :
  - vérifier l’état du dépôt avec `git status`,
  - s’assurer qu’aucune modification locale non commitée n’est présente.

- Toujours vérifier la branche active avant de :
  - modifier du code,
  - faire un commit,
  - merger.

- En cas de doute :
  - ne pas forcer (`--force`),
  - revenir à un état propre avant de continuer.

---

## Principes à respecter

- Le dépôt distant GitHub est la référence.
- La branche `main` doit toujours rester stable.
- Toute modification passe par `dev`.
- Les opérations Git sont volontairement simples et manuelles.

---

Fin du document.
