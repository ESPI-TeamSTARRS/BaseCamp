# Versionnement

Chaque composant a sa propre version semver : `shop`, `auth`, `payment` et `frontend`. Elle est calculée automatiquement par [python-semantic-release](https://python-semantic-release.readthedocs.io) (version épinglée dans `.github/workflows/release.yml`) à partir des messages de commit de `main`.

## Règles

| Élément | Règle |
|---|---|
| Source de vérité | le **tag Git** `<service>-vX.Y.Z` (`shop-v0.3.1`, `frontend-v0.2.0`…). `pyproject.toml` et `package.json` ne sont pas modifiés sur `main` (branche protégée) : leur champ `version` n'est qu'un repère de développement. Le workflow de release les met à jour dans son espace de travail pour construire l'artefact. |
| Calcul | `fix` = patch, `feat` = minor, `!` ou pied `BREAKING CHANGE:` = major. Les autres types (`docs`, `chore`, `ci`, `test`, `refactor`…) ne publient rien. |
| Version 0.x | `allow_zero_version = true` et `major_on_zero = false` : tant que le service est en 0.x, un changement cassant incrémente le minor. Le passage en 1.0.0 est un choix explicite (`feat!`). |
| Par service | seuls les commits qui touchent le dossier du service comptent (parseur `conventional-monorepo`, filtre de chemin `.`). Un `feat(auth)` qui ne modifie que `payment/` fait évoluer `payment`. |
| Première release | sans tag existant, le calcul part de 0.0.0 : le premier passage pose `<service>-v0.1.0`. |

La configuration est dans `[tool.semantic_release]` de chaque `apps/backend/<service>/pyproject.toml` et dans `apps/frontend/releaserc.toml`.

## Ce qui garantit la qualité des messages

1. Hook local `commit-msg` ([git-and-hooks.md](git-and-hooks.md)).
2. Workflow `pr-title` : le titre de la PR doit respecter le même format (même script, `scripts/hooks/check_commit_msg.py`). Le squash and merge doit reprendre ce titre comme message de commit, ce qui se règle dans les paramètres du dépôt (« Default to pull request title »).

## Déroulé après la fusion d'une PR

1. Le workflow `Release` rejoue la CI sur `main` (il appelle `ci.yml`).
2. Si elle est verte, il calcule, pour chacun des quatre composants, la prochaine version.
3. Si un composant a changé, il pose et pousse le tag `<service>-vX.Y.Z` sur le commit de `main`. Aucun commit n'est écrit sur `main`.

Le build et la publication des images se font dans ce même workflow (un tag poussé avec `GITHUB_TOKEN` ne déclenche pas d'autre workflow).

## Vérifier en local

```bash
cd apps/backend/shop
uvx --from python-semantic-release==10.5.3 semantic-release version --print
```

Affiche la version qui serait publiée (ou la version courante si rien ne change). Ne pas lancer sans `--print` ni `--noop` en local : la commande crée un tag.
