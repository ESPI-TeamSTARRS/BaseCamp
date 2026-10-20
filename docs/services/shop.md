# Service `shop`

**Dossier** : `apps/backend/shop`

## Rôle
Catalogue, commandes et stock. Demande les paiements au service [payment](payment.md) via l'interface `PaymentProvider` et authentifie les appels grâce à [auth](auth.md).

## API
| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | liveness : le processus répond (toujours 200) |
| GET | `/health/ready` | readiness : 200 si la base répond, **503** sinon (corps `{"service", "status": "up" \| "down"}`) |

Derrière la passerelle, ces routes sont exposées sous `/api/shop/` (ex. `/api/shop/health/ready`). Le healthcheck Docker utilise `/health` (un conteneur dont la base est arrêtée reste vivant); `/health/ready` sert aux sondes de disponibilité.

Les routes métier s'ajoutent par tranche (`catalog`, `order`) et se documentent ici.

## Invariants
- Les prix viennent toujours du catalogue serveur.
- Une commande payée correspond à exactement une transaction.
- Le stock ne devient jamais négatif.
- La liveness ne dépend jamais de la base; seule la readiness la teste.
- Le service n'utilise que son propre rôle Postgres, jamais le compte administrateur.

## Configuration
Variables d'environnement préfixées `APP_` (voir `.env.example` à la racine) :

| Variable | Défaut | Rôle |
|---|---|---|
| `APP_SERVICE_NAME` | `basecamp-shop` | nom renvoyé par les endpoints de santé |
| `APP_ENVIRONMENT` | `dev` | environnement d'exécution |
| `APP_DB_HOST` / `APP_DB_PORT` | `localhost` / `5432` | serveur Postgres |
| `APP_DB_NAME` / `APP_DB_USER` | `shop` / `shop` | base et rôle propres à `shop` |
| `APP_DB_PASSWORD` | vide | mot de passe du rôle (fourni par l'environnement, jamais versionné) |

## Base de données et migrations
Postgres via SQLAlchemy (pilote `psycopg`). Les migrations sont gérées par Alembic (`apps/backend/shop/alembic/`, URL lue dans `APP_DB_*`).

```bash
cd apps/backend/shop
uv run alembic upgrade head                       # appliquer (idempotent)
uv run alembic revision -m "ajoute les produits"  # nouvelle migration
```

En Docker Compose, `shop-migrate` applique les migrations avant le démarrage de `shop`. La migration `0001` est vide : elle fixe le point de départ de l'historique.
