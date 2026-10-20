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

## Pile complète en local (Docker Compose)

Le fichier `docker-compose.yml` (racine) démarre : Traefik, le front, `shop` (avec sa migration Alembic), Postgres, SeaweedFS (stockage objet compatible S3, bucket `product-images` créé au démarrage) et Mailpit.

```bash
cp .env.example .env          # valeurs factices, .env est ignoré par Git
docker compose up -d --build --wait
curl http://127.0.0.1:8080/api/shop/health        # 200, via Traefik
curl http://127.0.0.1:8080/api/shop/health/ready  # 200 si Postgres répond, 503 sinon
```

Le front est servi sur <http://127.0.0.1:8080/>. Arrêt : `docker compose down` (ajouter `-v` pour supprimer les données).

| Élément | Règle |
|---|---|
| Port publié | Traefik seul, sur `127.0.0.1:${GATEWAY_PORT}` (8080 par défaut). Postgres, SeaweedFS, Mailpit, `shop` et le front ne sont pas joignables depuis l'hôte. |
| Réseaux | `edge` (Traefik, hôte), `app` (Traefik, front, `shop`, Mailpit; interne), `data` (`shop`, Postgres, SeaweedFS; interne). |
| Routage | `/api/shop/*` vers `shop` (préfixe retiré), tout le reste vers le front. |
| Base | Postgres crée au premier démarrage un rôle et une base propres à `shop`; le compte administrateur n'est pas utilisé par les services. |
| Migrations | Le service one-shot `shop-migrate` exécute `alembic upgrade head` avant `shop`; il est rejouable sans erreur. |
| Conteneurs | Utilisateur non-root, `no-new-privileges`, capacités retirées, redémarrage `unless-stopped`, healthcheck sur chaque service. |

Les variables sont documentées dans `.env.example` (aucune valeur réelle). Les fins de ligne sont normalisées en LF par `.gitattributes` (Windows, WSL, Linux).

Mailpit, SeaweedFS et Postgres n'ont volontairement pas de port publié; pour les inspecter : `docker compose exec <service> ...` ou `docker compose logs <service>`.
