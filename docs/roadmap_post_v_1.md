# 🚀 Roadmap Post‑V1 — Team Baguette

Ce document décrit **les axes d’évolution après la sortie officielle de la v1** de Team Baguette.
Il ne conditionne **en aucun cas** la validation de la v1 et sert uniquement de **guide stratégique** pour le développement futur.

> 🎯 Objectif : permettre l’évolution du projet **sans remettre en cause les fondations v1**.

---

## 🧭 Principes directeurs Post‑V1

Toutes les évolutions post‑v1 doivent respecter :

- la structure BDD validée v1 (migrations uniquement)
- la séparation stricte User / Player / Team
- la logique universelle équipe vs équipe
- la préservation totale de l’historique

👉 **Aucune évolution post‑v1 ne justifie une refonte globale.**

---

## 🧩 1. Brackets avancés

### Objectif
Passer d’un affichage statique à un **arbre de compétition réellement structuré**.

### Évolutions prévues

- Exploitation complète des champs déjà présents :
  - `source_team1_series_id`
  - `source_team2_series_id`
  - `source_team1_type` (`winner` / `loser`)
  - `source_team2_type`
  - `bracket_position`

- Continuité graphique entre les matchs
- Arbre parent / enfant explicite

### Formats envisagés

- Simple élimination (complet)
- Double élimination
- Loser bracket
- Consolation bracket

⚠️ Ces évolutions **n’impliquent aucune suppression** de la logique actuelle.

---

## 🤖 2. Automatisation des tournois

### Objectif
Réduire la charge manuelle **sans supprimer le contrôle admin**.

### Pistes

- Génération automatique de phases
- Placement automatique des équipes
- Création automatique des séries
- Avancement automatique des vainqueurs

### Règle clé

> Toute automatisation doit rester **optionnelle et réversible**.

---

## 🎥 3. Restream — évolutions avancées

### Indices

- Historisation optionnelle des indices
- Comparaison avant / après
- Permissions plus fines par catégorie

### Live

- Statut `live`
- Mise en avant automatique
- Outils spécifiques pour casters

### Technique

- Optimisation SSE
- Rafraîchissement différentiel
- Fallback polling si nécessaire

---

## 📊 4. Statistiques & historique

### Objectif
Valoriser les données accumulées.

### Exemples

- Historique par joueur
- Historique par équipe
- Statistiques de tournois
- Résultats cumulés

⚠️ Ces fonctionnalités reposent **exclusivement sur les données existantes**.

---

## 🌍 5. UX & accessibilité

### Améliorations prévues

- Mobile first renforcé
- Accessibilité (ARIA, contrastes)
- Navigation clavier
- Optimisations de lisibilité des brackets

---

## 🧪 6. Qualité & robustesse

### Technique

- Tests unitaires ciblés (règles métier)
- Tests d’intégration admin
- Logs structurés
- Meilleure gestion des erreurs

### Déploiement

- Monitoring léger
- Backups automatisés
- Procédures de rollback documentées

---

## 🧠 7. Évolutions conceptuelles possibles

*(non prioritaires, à long terme)*

- Multi‑jeux avancé
- Saisons / circuits
- Classements globaux
- API publique (lecture seule)

---

## 🏁 Conclusion

La v1 pose une **base solide et assumée**.

Cette roadmap post‑v1 n’est pas une obligation,
mais un **cadre clair** pour évoluer :

- sans dette
- sans refonte
- sans précipitation

👉 **La stabilité v1 reste toujours prioritaire sur toute nouvelle feature.**

