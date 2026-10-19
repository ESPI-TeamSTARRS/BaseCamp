# Mise en route

## Prérequis

- Python 3.13 et [uv](https://docs.astral.sh/uv/)
- Node.js 20 et npm
- Docker

## Installation

```bash
uv sync                                                  # outils racine (poe, pre-commit)
uv sync --directory apps/backend/shop                    # un service backend
npm ci --prefix apps/frontend                            # front
uv run pre-commit install --install-hooks                # hooks Git
```

## Commandes courantes (depuis la racine)

| Commande | Effet |
|---|---|
| `uv run poe quality` | lint, format et types de tous les services |
| `uv run poe test` | tests et couverture (seuil 80 %) de tous les services |
| `uv run poe security` | audit des dépendances |
| `uv run poe ci` | tout ce que la CI exécute |

Pour un seul service : `uv run --directory apps/backend/<service> poe check`.

## Lancer un service

```bash
cd apps/backend/<service>
uv run uvicorn app.main:app --reload
```

La configuration se lit dans les variables d'environnement préfixées `APP_` (voir la page du service). Aucun secret n'est versionné.
