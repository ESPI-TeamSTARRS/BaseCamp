# Git, commits et hooks

## Branches

Développement sur trunk : `main` est toujours déployable, tout passe par une pull request. Branches courtes `feature/<description>`, correctifs `hotfix/<description>`. Revue obligatoire avant fusion.

## Commits

Format Conventional Commit, description en français :

```
<type>(<scope>)?!?: <description>
```

Types : `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `build`, `perf`, `style`, `revert`. Exemple : `feat(payment): ajoute le remboursement partiel`.

## Hooks Git

Installation : `uv run pre-commit install --install-hooks`. Les hooks vérifient, ils ne corrigent jamais les fichiers.

| Hook | Contrôles |
|---|---|
| `commit-msg` | format Conventional Commit |
| `pre-commit` | gitleaks (secrets), lint et format du service modifié |
| `pre-push` | types et tests unitaires du service modifié |

Les corrections automatiques se lancent à la demande : `uv run poe fix` dans un service.

## Secrets

Les fichiers `.env*` sont ignorés par Git. Un secret commité impose de le renouveler, la purge d'historique ne suffit pas.
