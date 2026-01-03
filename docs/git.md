# Git / GitHub — Organisation et workflow (Team Baguette)

Ce document décrit **l’organisation Git mise en place**, **le rôle de GitHub**, et **les manipulations courantes** à effectuer au quotidien pour développer et déployer le site **sans casser la prod**.

---

## 1. Objectif de Git dans le projet

Git est utilisé pour :
- séparer clairement **développement** et **production**
- éviter toute modification directe en prod
- garder un historique clair et pouvoir revenir en arrière
- remplacer les copier/coller manuels par un flux fiable

Git **ne gère pas** :
- les bases de données
- les secrets (`.env`)
- les fichiers runtime

---

## 2. Organisation générale

### 2.1 Dépôt distant (GitHub)

- GitHub est la **source de vérité du code**
- Deux branches seulement sont utilisées :

| Branche | Rôle |
|-------|------|
| `main` | Production (stable) |
| `dev` | Développement |

---

### 2.2 Dossiers sur le serveur

Deux copies du projet existent sur le serveur :

| Dossier | Rôle | Branche |
|-------|------|---------|
| `/home/adri/site_team_baguette` | Site PROD | `main` |
| `/home/adri/site_team_baguette_dev` | Site DEV | `dev` |

Chaque dossier :
- est un **clone du même dépôt GitHub**
- tourne avec son **service systemd**
- utilise sa **propre base de données** et son **propre `.env`**

---

## 3. Authentification GitHub (SSH)

Le serveur communique avec GitHub via **SSH**, sans mot de passe.

- Une clé dédiée existe : `~/.ssh/id_github`
- Elle est enregistrée dans **GitHub → Settings → SSH and GPG keys**

### Vérification rapide
```bash
ssh -T git@github.com
```
Résultat attendu :
```
Hi <username>! You've successfully authenticated
```

---

## 4. Ce qui est versionné / non versionné

### 4.1 Versionné (Git)
- code Python
- templates HTML
- CSS / JS
- documentation

### 4.2 NON versionné (via `.gitignore`)
- `.env`, `.env.*`
- `venv/`, `.venv/`
- bases SQLite (`*.db`, `*.sqlite*`)
- fichiers runtime (`instance/indices/sessions`, logs, cache)

👉 Les dossiers runtime sont créés automatiquement au démarrage de l’app.

---

## 5. Workflow quotidien (DEV → PROD)

### Règle principale

> **On ne modifie jamais le code directement en prod.**

Toute modification suit **exactement** ce chemin.

---

### 5.1 Travailler en DEV

```bash
cd /home/adri/site_team_baguette_dev
git checkout dev
git branch
```
(Vérifier que `dev` est bien actif)

Après modification du code :
```bash
git status
git add -A
git commit -m "Description claire de la modif"
git push origin dev
```

---

### 5.2 Publier vers la PROD (merge)

Quand la fonctionnalité est validée en DEV :

```bash
git checkout main
git merge dev
git push origin main
```

À ce stade :
- GitHub contient la version **prod-ready**
- `main` est à jour

---

### 5.3 Mettre à jour la PROD

Dans le dossier prod :

```bash
cd /home/adri/site_team_baguette
git checkout main
git pull origin main
sudo systemctl restart team-baguette
```

---

## 6. Commandes utiles (mémo)

### Vérifier l’état
```bash
git status
git branch
git log --oneline --max-count=10
```

### Mettre à jour depuis GitHub
```bash
git pull origin dev   # en DEV
git pull origin main  # en PROD
```

### Annuler des modifs locales non commit
```bash
git restore .
```

### Rollback à un commit précis
```bash
git log --oneline
git reset --hard <HASH>
sudo systemctl restart team-baguette
```

---

## 7. Bonnes pratiques importantes

- Toujours vérifier la branche avant d’éditer (`git branch`)
- Toujours commit en DEV, jamais en PROD
- Commits petits et explicites
- Toujours tester en DEV avant merge

---

## 8. Dépannage courant

### 8.1 Erreur SSH GitHub
```bash
ssh -T git@github.com
```
Si échec : vérifier `~/.ssh/config` et la clé `id_github`.

---

### 8.2 Erreur systemd `203/EXEC` (gunicorn)
Cause fréquente : venv copié.

Solution propre :
```bash
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
sudo systemctl restart team-baguette
```

---

## 9. Règle finale à retenir

> **DEV → commit → merge → push → pull → restart**

Si cette règle est respectée, la prod reste stable.

---

Fin du document.

