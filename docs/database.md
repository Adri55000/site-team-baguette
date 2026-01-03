# Base de données — Team Baguette (v1)

Ce document décrit la base de données **réellement utilisée** par le projet (source de vérité : schéma SQL).
Il est **normatif** : toute évolution du schéma ou des accès BDD doit respecter les principes ci-dessous.

- SGBD : **SQLite**
- Emplacement : **`instance/`** (fichier SQLite utilisé en exécution)
- Accès : standardisé via le code (objectif : éviter les accès directs non maîtrisés)
- Migrations automatiques : **non**
- Reset : **non prévu** à ce stade

---

## Principes

### Historique et traçabilité
- La base sert de source de vérité.
- On évite les suppressions destructrices lorsque l’historique a une valeur fonctionnelle.

### Séparation des concepts
- **User** = compte (auth / rôle / profil).
- **Player** = participant en tournoi (peut être lié à un user ou non).
- **Team** = abstraction universelle (solo = team d’un seul player).

### Structure tournée “tournoi”
- Un tournoi a des phases, des équipes inscrites, des séries, des matchs, et éventuellement des restreams.
- L’affichage s’adapte aux données : on ne tord pas la BDD pour l’UI.

---

## Schéma (tables)

### `users`
Comptes applicatifs.
- `id` (PK)
- `username` (unique)
- `password_hash`
- `role` (par défaut `'invité'`)
- `is_active` (par défaut `1`)
- `description`
- `avatar_filename`
- `social_links` (texte sérialisé)
- `last_login`
- `created_at`

### `players`
Participants (indépendants des comptes).
- `id` (PK)
- `name`
- `user_id` (optionnel, lien vers `users.id`)
- `created_at`

### `teams`
Équipes (y compris équipes “solo”).
- `id` (PK)
- `name`
- `tournament_id` (optionnel)
- `created_at`

### `team_players`
Association team ↔ players (composition d’équipe).
- `team_id`
- `player_id`
- `position`

### `games`
Jeux supportés (référentiel).
- `id` (PK)
- `name`
- `short_name`
- `icon_path`
- `color`

### `tournaments`
Tournois.
- `id` (PK)
- `name`
- `description`
- `status`
- `created_at`
- `game_id` (FK → `games.id`)
- `source`
- `metadata`
- `slug`

### `tournament_phases`
Phases d’un tournoi (ex : groupes, bracket).
- `id` (PK)
- `tournament_id` (FK → `tournaments.id`)
- `position`
- `name`
- `type`
- `created_at`
- `details`

### `tournament_teams`
Inscriptions des teams à un tournoi (seed / groupe / position).
- `tournament_id`
- `team_id`
- `seed`
- `group_name`
- `position`
- `created_at`

### `series`
Séries (rencontres “match-up” : team1 vs team2), pouvant servir à représenter des brackets.
- `id` (PK)
- `tournament_id` (FK → `tournaments.id`)
- `team1_id` (FK → `teams.id`, optionnel)
- `team2_id` (FK → `teams.id`, optionnel)
- `stage` (texte)
- `best_of` (défaut `1`)
- `created_at`
- `winner_team_id` (optionnel)
- `phase_id` (FK → `tournament_phases.id`, optionnel)
- `source_team1_series_id` / `source_team2_series_id` (optionnels)
- `source_team1_type` / `source_team2_type` (optionnels)
- `bracket_position` (optionnel)
- `round` (optionnel)

### `matches`
Matchs (éléments joués à l’intérieur d’une série).
- `id` (PK)
- `series_id` (FK — voir note “intégrité”)
- `match_index`
- `scheduled_at`
- `tournament_id`
- `created_at`
- `completed` (flag présent)
- `is_completed` (flag présent)

**Note v1 :** deux colonnes de complétion existent (`completed` et `is_completed`).
La règle v1 est de **ne pas ajouter de troisième statut**. Toute clarification ultérieure devra choisir un champ canonique et documenter la transition.

### `match_teams`
Résultats d’un match pour chaque team.
- `match_id`
- `team_id`
- `position`
- `final_time`
- `final_time_raw`
- `is_winner`

### `restreams`
Restream lié à un match (1 restream ↔ 1 match).
- `id` (PK)
- `slug` (unique)
- `title`
- `created_at`
- `created_by` (FK → `users.id`)
- `match_id` (FK → `matches.id`, unique)
- `indices_template`
- `twitch_url`
- `is_active` (défaut `1`)
- `restreamer_name`
- `commentator_name`
- `tracker_name`

---

## Intégrité et points d’attention

### Clés étrangères
Le projet utilise des clés étrangères (FK) sur plusieurs tables (tournaments, phases, series, restreams, etc.).
Toute modification du schéma doit préserver ces liens.

### Anomalie à surveiller (schéma actuel)
Dans le schéma fourni, `matches.series_id` référence `series_old(id)` alors que la table `series_old` n’apparaît pas dans ce dump.
Cela doit être considéré comme **un point d’attention v1** :
- soit la table existe dans la DB réelle mais n’est pas dans le dump,
- soit une contrainte historique subsiste.
Toute correction doit être faite prudemment (et documentée).

---

## Triggers (automatisation BDD)

Deux triggers existent pour gérer automatiquement les équipes solo :

- `create_solo_team_after_player_insert`  
  À l’insertion d’un player :
  - création d’une team nommée `Solo - <player.name>` (tournament_id = NULL)
  - association dans `team_players`

- `update_solo_team_after_player_name_update`  
  À la modification du nom d’un player :
  - mise à jour du nom de la team “Solo - …” correspondante

Règle v1 : ces triggers font partie du fonctionnement normal et ne doivent pas être supprimés sans remplacement explicite.

---

## Règles d’évolution (v1)

- Toute évolution du schéma doit être :
  - explicitement documentée dans ce fichier,
  - compatible avec l’existant (pas de casse silencieuse),
  - appliquée avec une procédure manuelle contrôlée (pas de migration auto implicite).

- Les données runtime (fichier SQLite) vivent dans `instance/` et ne doivent pas être versionnées.

---

## Références

- `philosophie.md`
- `conventions.md`
- `structure.md`
