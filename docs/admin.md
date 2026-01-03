# Panel d’administration — Team Baguette (v1)

Ce document décrit le fonctionnement du **panel d’administration**.
Il est **normatif** : toute évolution du panel doit respecter ces principes (sauf décision explicitement documentée).

Le panel admin sert à gérer **l’ensemble des données structurantes** du site (tournois, joueurs, équipes, phases, séries, matchs, restreams).

---

## Accès et rôles

- L’accès au panel admin est réservé aux comptes autorisés (contrôle par rôle).
- Toute route admin est protégée par authentification + permission.

Règle v1 : la sécurité est validée côté backend, l’UI n’est jamais considérée comme une protection suffisante.

---

## Organisation (Blueprint)

Le panel admin est implémenté comme un **Blueprint séparé** (`app/admin/`), indépendant des pages publiques.

Règle v1 : le panel admin reste séparé (pas de fusion avec le blueprint public).

---

## Philosophie d’usage

- Le panel admin doit permettre de **créer, modifier, désactiver** les objets.
- On évite les suppressions destructrices lorsque l’historique a un intérêt fonctionnel.
- Le panel admin est l’outil de référence pour “mettre les données au bon endroit”.
- L’affichage public s’adapte aux données : on ne “bricole” pas la base pour l’UI.

---

## Entités gérées (périmètre v1)

### Utilisateurs (comptes)
- Création / gestion de comptes
- Activation / désactivation (si prévu par le panel)
- Gestion des rôles (selon permissions)
- Avatar / description / liens sociaux (si exposés par l’UI)

Source de vérité : table `users`.

### Players (participants)
- Création / édition d’un player
- Liaison optionnelle à un user (si utilisé)
- Renommage possible (impact sur l’équipe solo via trigger)

Source de vérité : table `players`.

### Teams (équipes)
- Création / édition d’équipe
- Composition via association players ↔ team
- Gestion des équipes “solo” (créées automatiquement via triggers)

Source de vérité : tables `teams` + `team_players`.

### Jeux
- Référentiel des jeux (nom, icône, couleur)

Source de vérité : table `games`.

### Tournois
- Création / édition (nom, statut, jeu, slug, description)
- Gestion des inscriptions (teams au tournoi : seed / groupe / position)
- Gestion des phases

Source de vérité : tables `tournaments`, `tournament_teams`, `tournament_phases`.

### Phases
- Création / édition d’une phase
- Position (ordre d’affichage) + type + détails

Source de vérité : `tournament_phases`.

### Séries
- Création / édition de séries (team1/team2, best-of, phase, stage)
- Champs bracket (round, bracket_position, sources) : présents mais utilisés selon les besoins v1

Source de vérité : `series`.

### Matchs
- Création / édition des matchs d’une série (match_index, schedule)
- Gestion de la complétion (schéma actuel : `completed` et `is_completed`)
- Résultats par team via `match_teams`

Source de vérité : `matches`, `match_teams`.

### Restreams
- 1 restream ↔ 1 match (unicité sur `match_id`)
- Activation / désactivation
- Gestion du template d’indices, URL twitch, noms (restreamer/commentator/tracker)
- Slug unique

Source de vérité : `restreams`.

---

## Règles d’intégrité (admin)

- Toute création/édition doit préserver les liens entre entités (FK / associations).
- Toute action qui casserait un affichage public ou un restream doit être évitée ou explicitement signalée.
- Le panel admin doit rester utilisable sans “connaissance interne” du code.

---

## Règles UX (admin)

- L’admin doit être **fonctionnel** avant d’être “parfait UX”.
- Les écrans doivent privilégier :
  - clarté (titres, libellés explicites),
  - validation d’erreur lisible,
  - actions irréversibles limitées.

---

## Données d’instance

Le panel admin peut s’appuyer sur des éléments stockés dans `instance/` (ex : templates d’indices).
Règle v1 : les données runtime (sessions, cache) ne doivent pas être versionnées.

---

## Références

- `philosophie.md`
- `conventions.md`
- `structure.md`
- `database.md`
