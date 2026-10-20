---
name: git-trunk-based
description: Workflow Git en trunk-based development pour Basecamp. A utiliser pour creer une branche, commiter, ouvrir ou relire une PR, fusionner, livrer un correctif, masquer une fonctionnalite inachevee ou decider d'un retour arriere. Reference : docs/development/git-and-hooks.md.
---

# Git — trunk-based development

Source de vérité : `docs/development/git-and-hooks.md` (et `docs/development/ci.md`). En cas de divergence, les docs font foi.

## Principes

- **`main` est la seule branche longue** et reste toujours déployable. Elle est protégée : aucune poussée directe, tout passe par une pull request.
- **Branches très courtes**, créées depuis `main`, fusionnées en moins d'un jour ou deux. Une branche qui vit plus longtemps se découpe.
- **PR petites** (une intention, relisible en quelques minutes), **fusion en squash** : un commit propre par PR sur `main`.
- **La CI bloque la fusion** tant que lint, types, tests, couverture ≥ 80 %, scan de secrets et audit des dépendances ne passent pas (job `ci-ok`).
- **Après fusion, la CD** construit les images, les teste (démarrage + healthcheck), déploie, et **revient automatiquement en arrière** si le contrôle de santé échoue.
- **Fonctionnalité inachevée = feature flag** : on fusionne le code, masqué par un drapeau désactivé par défaut, plutôt que de garder une branche ouverte.
- **Correctif en avant** : un bug en production se corrige par une nouvelle PR courte depuis `main`. Pas de revert d'une longue branche; un revert d'un seul commit squash reste possible si le correctif en avant est plus long que le retour arrière.

## Identifiant de tâche

Chaque branche, commit et PR mentionne l'identifiant de la tâche Linear `WORK-<n>` (équipe WORK).

| Élément | Format | Exemple |
|---|---|---|
| Branche | `<type>/WORK-<n>-<slug-court>` | `feat/WORK-<n>-remboursement-partiel` |
| Commit / titre de PR | `<type>(<scope>): <description en français> (WORK-<n>)` | `feat(payment): ajoute le remboursement partiel (WORK-<n>)` |

Types : `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `build`, `perf`, `style`, `revert`. Scope : le service ou la zone (`shop`, `auth`, `payment`, `frontend`, `ci`, `docs`). Le hook `commit-msg` valide le format Conventional Commit.

## Déroulé d'un changement

1. `git switch main && git pull --ff-only`, puis `git switch -c <type>/WORK-<n>-<slug>`.
2. Travailler en TDD (skill `tdd-couverture`) : un commit par phase est autorisé en local, ils sont écrasés au squash.
3. Avant de pousser : `uv run poe quality` et `uv run poe test` pour les services touchés. Les hooks `pre-commit` et `pre-push` doivent passer, sans jamais être contournés (`--no-verify` interdit).
4. Se resynchroniser avec `main` si besoin (`git fetch && git rebase origin/main`), puis pousser.
5. Ouvrir la PR : titre au format commit, description courte (quoi, pourquoi, comment tester), tâche Linear liée. PR en brouillon tant que la CI n'est pas verte.
6. Relecture, correctifs par commits supplémentaires, CI verte, titre de PR au format commit (check `pr-title`), **squash and merge** avec le titre de la PR comme message (il fixe la version, voir `docs/development/versioning.md`). Supprimer la branche.
7. La CD déploie `main`; surveiller le contrôle de santé.

## Feature flags

- Drapeau désactivé par défaut, lu dans la configuration (variable d'environnement `APP_FEATURE_<NOM>`), jamais en dur.
- Le code derrière le drapeau est testé dans les deux états (activé et désactivé).
- Le drapeau est retiré par une PR dédiée dès que la fonctionnalité est stable.

## Interdits

- Pousser sur `main`, forcer un push sur `main`, réécrire l'historique partagé.
- Brancher depuis une autre branche que `main` (pas de branches empilées).
- Fusionner avec une CI rouge ou en désactivant un contrôle.
- Commiter un secret ou un fichier `.env*`. Un secret commité se renouvelle, le retirer de l'historique ne suffit pas.
- Ajouter un suivi d'avancement dans le dépôt (journal, statut) : il vit dans Linear.
