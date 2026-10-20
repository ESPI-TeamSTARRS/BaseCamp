# Service `auth`

**Dossier** : `apps/backend/auth`

## Rôle
Comptes clients, jetons d'accès courts, rôle opérateur. Le service est isolé : conteneur, base Postgres, réseau et rôle de base de données propres.

## Structure
Tranches verticales Clean Architecture (`domain / application / infrastructure / presentation`), règle de dépendance vérifiée par `app/__tests__/unit/test_architecture.unit.py`.

| Tranche | Contenu actuel |
|---|---|
| `core` | configuration (`Settings`, variables `APP_*`) |
| `health` | liveness (`GetHealthUseCase`) et readiness (`GetReadinessUseCase`, sonde `DatabaseProbe`) |

Les tranches métier (`account`, `session`) s'ajoutent à côté de `health`; leurs routes se documentent ici.

## API
| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | liveness : 200 tant que le processus répond |
| GET | `/health/ready` | readiness : 200 si la base répond, 503 sinon |

Via la passerelle : `/api/auth/health` et `/api/auth/health/ready` (préfixe retiré par Traefik). Les routes `/internal/*` (appels entre services) ne sont jamais routées par la passerelle : un appel externe reçoit 404 (couvert par le test e2e `test_auth_stack.e2e.py`).

## Isolation
- Postgres dédié (`postgres-auth`, volume propre) sur le réseau interne `auth-data`, que seuls `auth` et `auth-migrate` rejoignent : `shop` et `payment` ne peuvent pas l'atteindre, et `auth` ne rejoint aucune base des autres services.
- Le rôle `auth` est l'unique compte de cette instance.
- Migrations Alembic (`alembic/`) exécutées par le service one-shot `auth-migrate` avant le démarrage; `alembic upgrade head` est rejouable sans effet.

## Clés de signature
`sh scripts/init-auth-keys.sh` génère une paire Ed25519 dans `.secrets/auth/` (ignoré par Git), montée en secrets Docker dans le conteneur (`/run/secrets/auth_jwt_private_key`, `/run/secrets/auth_jwt_public_key`). Le script ne remplace jamais une clé existante sans `--force`. Les clés ne sont jamais versionnées; une clé commitée par erreur se renouvelle.

## Règles
- Mots de passe hachés avec un algorithme dédié, jamais journalisés.
- Cookies de session `HttpOnly`, `Secure`, `SameSite=Strict`.
- Limitation de débit contre le brute-force.
- Séparation des rôles : un client n'accède jamais aux routes opérateur.

## Configuration
| Variable | Rôle |
|---|---|
| `APP_SERVICE_NAME`, `APP_ENVIRONMENT` | identité et environnement |
| `APP_DB_HOST`, `APP_DB_PORT`, `APP_DB_NAME`, `APP_DB_USER`, `APP_DB_PASSWORD` | connexion à la base d'`auth` (le mot de passe vient de l'environnement) |

Côté compose : `AUTH_DB_NAME`, `AUTH_DB_USER`, `AUTH_DB_PASSWORD` (voir `.env.example`).

## Tests
`uv run poe test` (unit et integ, couverture ≥ 80 %); `uv run poe test:e2e` sur la pile lancée (`E2E_BASE_URL`, `http://127.0.0.1:8080` par défaut).
