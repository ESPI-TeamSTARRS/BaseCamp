# Tickets

Les tickets sont rédigés dans Linear (équipe **WORK**) selon le gabarit ci-dessous. Le cadre général est dans [agile.md](agile.md).

## Types

| Type | Quand | Exemples |
|---|---|---|
| Story | Valeur visible d'un utilisateur : page, composant, endpoint consommé par le front, parcours métier | Rembourser partiellement une commande |
| Tâche | Travail technique sans valeur utilisateur directe : scaffolding, migration, CI, infrastructure, outillage | Ajouter la migration de la table des transactions |

Un ticket mixte se découpe; à défaut, Story.

## Titre

`WORK-<n> <résultat attendu>`. Le titre décrit le résultat, pas la technique.

## Gabarit

1. **Contexte et valeur** : le problème, pour qui, le bénéfice.
2. **User story** : En tant que `<rôle>`, je veux `<action>` afin de `<bénéfice>` (pour une tâche : l'objectif et ce qu'il débloque).
3. **Critères d'acceptation** : Étant donné / Quand / Alors, vérifiables, avec au moins un cas d'erreur ou limite. Pour un cas d'usage métier, un critère de journalisation : « le cas d'usage émet les événements `<service>.<action>` (succès et refus) du catalogue, vérifiés par test, sans donnée sensible » ([logging.md](logging.md)).
4. **Périmètre** et **hors périmètre**.
5. **Découpage par service** : ce qui change dans `shop`, `auth`, `payment`, `frontend`.
6. **Exigences de qualité** : TDD, tests colocalisés, couverture ≥ 80 %, tests d'architecture, validation des entrées, documentation à jour.
7. **Tâches techniques** : liste cochable, tests d'abord.
8. **Risques et dépendances**.
9. **Définition de terminé** : renvoi vers [agile.md](agile.md) et, si besoin, précisions propres au ticket.

## Taille et découpage

Un ticket tient en une à deux journées et donne une PR petite. Estimation en points 1, 2, 3, 5; au-dessus de 5, on découpe. Une Story multi-services a un ticket parent (valeur, critères métier) et un sous-ticket par service.

## Lien avec Git

`WORK-<n>` figure dans la branche (`feat/WORK-<n>-<slug>`), les commits et le titre de PR (`feat(payment): ajoute le remboursement partiel (WORK-<n>)`). Voir [git-and-hooks.md](git-and-hooks.md).

## Étiquettes

Une étiquette par service concerné (`shop`, `auth`, `payment`, `frontend`) et une pour le type (`story`, `tâche`).
