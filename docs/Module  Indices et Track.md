# Module Restream — Indices & Trackers

Ce document décrit l’architecture et le fonctionnement des modules **Indices** et **Trackers** (Restream), ainsi que la marche à suivre pour ajouter un nouveau tracker, et la roadmap.

---

## 1) Vue d’ensemble

Le système Restream gère deux “couches” indépendantes :

- **Indices** : affichage + édition d’indices, stockés dans un fichier JSON de session par restream (slug).
- **Trackers** : affichage + édition d’un tracker par restream (type configurable), stocké dans un fichier JSON de session par restream (id).

Les deux systèmes sont :
- **versionnés côté code** (catalog/preset/templates)  
- **persistés côté runtime** via fichiers JSON (sessions) dans `instance/…`.

---

## 2) Indices

### 2.1 Stockage

- **Templates indices** (sources) : `instance/indices/templates/<template>.json`
- **Sessions indices** (runtime) : `instance/indices/sessions/<slug>.json`

Le champ DB `restreams.indices_template` contrôle l’activation :
- `"none"` → aucun indice (pas de session attendue)
- sinon → un template existe et une session JSON est créée lors de la création/activation du restream

### 2.2 Affichage

- Page indices dédiée : `/<slug>/indices`
- Bloc indices inclus dans la page live : `templates/restream/_indices_block.html` (inclu par `live.html` seulement si `indices` est présent)

### 2.3 Édition & permissions

- Tout le monde peut **voir** les indices.
- Seuls les utilisateurs **éditeur+** peuvent **éditer** (bouton “Éditer”, formulaire).
- Certaines actions globales (ex: reset) sont réservées aux **restreamer+** (selon implémentation).

### 2.4 Temps réel (SSE)

- Un endpoint SSE pousse la session indices quand elle change (poll sur `mtime`).
- Les routes indices SSE ne dépendent pas du template : elles streament simplement la session JSON existante.

### 2.5 Registry indices (templates disponibles)

Objectif : ne plus hardcoder les templates indices dans les `<select>`.

Principe :
- scanner `instance/indices/templates/*.json`
- lire un `label` depuis le JSON (si présent), sinon fallback (nom de fichier)
- renvoyer une liste “clé + label” pour les templates

---

## 3) Trackers

### 3.1 Stockage

- **Sessions tracker** (runtime) : `instance/trackers/sessions/restream_<restream_id>.json`

Le champ DB `restreams.tracker_type` contrôle l’activation :
- `"none"` → aucun tracker
- sinon → tracker actif et session créée à la première visite de `/live` ou `/overlay` (lazy init)

### 3.2 Concepts

Un tracker est défini par :
- un **catalog** (structure des items/sections/règles d’affichage)
- un **preset par défaut** (état initial)
- une **couche frontend** (template bloc + css + js)

### 3.3 Registry tracker

Le registry tracker est la source de vérité pour :
- la liste des trackers disponibles (pour les `<select>`)
- la définition complète d’un tracker (catalog + preset + frontend)

aucun code “core” ne doit dépendre d’un jeu précis.

### 3.4 Runtime / base (moteur)

Le “core” tracker (base) gère :
- lecture/écriture de la session JSON
- initialisation de session si elle n’existe pas
- persistance “atomique” (write tmp + replace)

Important :
- la structure des participants/état est **spécifique au tracker** (shape du preset)
- le core ne doit pas imposer une structure unique (“state” etc.)
- le preset SSR doit produire la structure attendue par le macro SSR.

### 3.5 Affichage

#### Live
- Route : `/<slug>/live`
- Template : `templates/restream/live.html` (générique)
  - charge CSS/JS via `tracker.frontend`
  - inclut le bloc du tracker via `tracker.frontend.template_block`

#### Overlay OBS
- Route : `/<slug>/overlay` (OBS only, fond transparent)
- Template : `templates/restream/overlay.html` (générique)
  - charge CSS/JS via `tracker.frontend`
  - inclut le bloc du tracker via `tracker.frontend.template_block`
  - ajoute `overlay_obs.css`
  - `body.obs-overlay` sert de scope CSS (ex: masquer labels joueurs)

#### Bloc SSR (exemple)
- `templates/tracker/ssr_inventory/block.html`
  - boucle participants
  - affiche éventuellement le label
  - appelle le macro SSR (`restream/_tracker_ssr_macro.html`)

### 3.6 Édition & permissions

- Tout le monde peut **voir** (selon choix produit / OBS).
- Seuls les utilisateurs **éditeur+** peuvent **interagir** (update tracker).
- L’overlay OBS est **read-only** (`can_edit = False`).

### 3.7 Temps réel (SSE)

- Un endpoint SSE pousse la session tracker quand elle change (même mécanisme : polling sur `mtime`).
- Les endpoints update/stream doivent :
  - récupérer le restream + `tracker_type` depuis la DB
  - refuser si `tracker_type == "none"`
  - s’appuyer sur le registry pour init session si besoin (preset_factory)

---

## 4) Routes Restream — points importants

### 4.1 Create Restream
- Récupère `indices_template` + `tracker_type` depuis le formulaire.
- Valide via registry (`is_valid_indices_template`, `is_valid_tracker_type`).
- Crée la session indices **uniquement si** `indices_template != "none"`.
- Enregistre `tracker_type` en DB (la session tracker est lazy-initialisée plus tard).

### 4.2 Edit Restream
- Met à jour `indices_template` + `tracker_type` en DB.
- Si indices_template change :
  - supprime la session indices existante
  - recrée uniquement si `new != "none"`
- Si tracker_type change :
  - supprime la session tracker `instance/trackers/sessions/restream_<id>.json`
  - (lazy-init du nouveau tracker à la prochaine visite)

### 4.3 Boutons UI
- Bouton “Indices” : afficher uniquement si `indices_template != "none"`.
- Bouton “Live” : toujours affiché (même si tracker/indices sont “none” ; utile pour évolution future).

---

## 5) Marche à suivre — Ajouter un nouveau tracker

### Objectif
Ajouter un tracker “jeu X” sans modifier les templates génériques (`live.html`, `overlay.html`) ni le core.

### Étape A — Définir les fichiers du tracker
Créer un dossier dédié au jeu, par exemple :

- `app/modules/tracker/games/<jeu>/catalog.py`
- `app/modules/tracker/games/<jeu>/preset.py`

Créer les assets frontend :

- `templates/tracker/<tracker_type>/block.html`
- `static/css/tracker/<tracker_type>.css` (ou autre convention projet)
- `static/js/tracker/<tracker_type>.js`

### Étape B — Catalog
Dans `catalog.py`, exposer une fonction :

- `get_catalog() -> dict`

Le catalog doit être le “contrat” côté UI/JS (items, groupes, composites, etc.), propre au jeu.

### Étape C — Preset par défaut
Dans `preset.py`, exposer une factory :

- `build_default_preset(participants_count: int = 1) -> dict`

Le preset **doit** :
- générer la structure attendue par le template/macro de ce tracker
- initialiser tous les champs nécessaires (valeurs scalaires/int/bool selon besoin)
- inclure `participants` (liste) si c’est la structure retenue pour ce tracker

> Note : le preset est “en mémoire”, il n’est pas sauvegardé comme preset utilisateur. Il sert uniquement à créer une session si elle n’existe pas.

### Étape D — Bloc template (rendu)
Dans `templates/tracker/<tracker_type>/block.html` :
- boucle sur `tracker.session["participants"]` (ou autre structure si ton tracker diffère)
- appelle le composant/macro du tracker
- gère l’affichage des labels si souhaité (live vs overlay via CSS scoping)

### Étape E — JS tracker
Le JS doit :
- écouter le flux SSE (`window.TRACKER_STREAM_URL`)
- mettre à jour le DOM
- émettre les updates vers `update_url` (si `can_edit`)
- respecter `window.TRACKER_USE_STORAGE` (overlay OBS => false)

### Étape F — Déclarer le tracker dans le registry
Dans `app/modules/tracker/registry.py` :
- ajouter une définition pour `<tracker_type>` :
  - `label`
  - `catalog` (callable)
  - `default_preset` (callable)
  - `frontend` (template_block/css/js)

Puis il sera automatiquement :
- disponible dans les `<select>` create/edit via `get_available_trackers()`
- utilisable par live/overlay via `get_tracker_definition(tracker_type)`

### Étape G — DB / UI
- Aucune migration supplémentaire si `restreams.tracker_type` existe déjà.
- Tester :
  - création restream avec nouveau tracker
  - live / overlay
  - update + SSE

---

## 6) Roadmap (module Indices & Trackers)

### 6.1 Presets “utilisateur” (admin panel) DONE
- UI admin pour créer/sauvegarder plusieurs presets par tracker
- stockage DB (ou fichiers presets versionnés) + gestion de version

### 6.2 Chargement de preset existant
- permettre de sélectionner un preset enregistré 
- support “reset tracker” vers preset choisi

### 6.3 Multi-tracker avancé (optionnel)
- plusieurs trackers sur un même restream (ex: deux joueurs + deux jeux)
- ou plusieurs “panneaux” de tracker (inventaire + objectifs)

---
