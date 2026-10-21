# Git, commits et hooks

## Trunk-based development

- **`main` est la seule branche longue** et reste toujours déployable. Elle est protégée : aucune poussée directe, tout passe par une pull request.
- **Branches très courtes**, créées depuis `main` et fusionnées en moins d'un jour ou deux. Une branche qui vit plus longtemps se découpe.
- **Pull requests petites** (une intention, relisibles en quelques minutes), **fusion en squash** : un commit propre par PR.
- **La CI bloque la fusion** tant que lint, types, tests, couverture ≥ 80 %, scan de secrets et audit des dépendances ne passent pas.
- **Après fusion**, la livraison construit les images, les teste (démarrage et healthcheck), déploie, et revient automatiquement en arrière si le contrôle de santé échoue.
- **Une fonctionnalité inachevée est masquée par un feature flag** plutôt que par une branche ouverte.
- **Un correctif se fait en avant** (nouvelle PR courte depuis `main`); un revert se limite à un commit squash isolé.

## Nommage

L'identifiant de tâche Linear (`WORK-<n>`, équipe WORK) figure dans la branche, les commits et la PR.

| Élément | Format | Exemple |
|---|---|---|
| Branche | `<type>/WORK-<n>-<slug-court>` | `feat/WORK-<n>-remboursement-partiel` |
| Commit et titre de PR | `<type>(<scope>): <description en français> (WORK-<n>)` | `feat(payment): ajoute le remboursement partiel (WORK-<n>)` |

Types : `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `build`, `perf`, `style`, `revert`. Le scope est le service ou la zone (`shop`, `auth`, `payment`, `frontend`, `ci`, `docs`). Marque de rupture : `feat(payment)!: ...`.

## Déroulé d'un changement

1. Mettre `main` à jour, créer la branche.
2. Développer en TDD ([testing.md](testing.md)).
3. Vérifier en local : `uv run poe quality` et `uv run poe test` sur les services touchés.
4. Pousser, ouvrir la PR (brouillon tant que la CI n'est pas verte) avec : quoi, pourquoi, comment tester.
5. Relecture, CI verte (`ci-ok`) et titre de PR valide (`pr-title`), **squash and merge** avec le titre de la PR comme message, suppression de la branche. Le titre fixe la version publiée ([versioning.md](versioning.md)).

## Feature flags

Drapeau désactivé par défaut, lu depuis la configuration (`APP_FEATURE_<NOM>`), jamais en dur. Le code est testé dans les deux états. Le drapeau est retiré par une PR dédiée dès que la fonctionnalité est stable.

## Hooks Git

Installation : `uv run pre-commit install --install-hooks`. Les hooks vérifient, ils ne corrigent jamais les fichiers. Ils ne se contournent pas (`--no-verify` interdit).

| Hook | Contrôles |
|---|---|
| `commit-msg` | format Conventional Commit |
| `pre-commit` | gitleaks sur l'index, lint et format du service modifié |
| `pre-push` | gitleaks sur les commits poussés (`origin/main..HEAD`, même config que la CI; binaire `gitleaks` requis), types et tests unitaires du service modifié |

Les corrections automatiques se lancent à la demande : `uv run poe fix` dans un service.

## Secrets

Les fichiers `.env*` sont ignorés par Git. Un secret commité impose de le renouveler : retirer le fichier de l'historique ne suffit pas.
