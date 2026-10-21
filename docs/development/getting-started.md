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

Le fichier `docker-compose.yml` (racine) démarre : Traefik, le front, `shop` (avec sa migration Alembic), Postgres, `auth` (avec sa migration et son Postgres dédié, isolé), `payment` (avec sa migration et son Postgres dédié, isolé : ni routé ni publié), SeaweedFS (stockage objet compatible S3, bucket `product-images` rempli au démarrage par `seaweedfs-seed` avec les visuels du catalogue) et Mailpit.

```bash
cp .env.example .env          # valeurs factices, .env est ignoré par Git
sh scripts/init-auth-keys.sh  # clés de signature d'auth dans .secrets/ (ignoré par Git, idempotent)
docker compose up -d --build --wait
curl http://127.0.0.1:8080/api/shop/health        # 200, via Traefik
curl http://127.0.0.1:8080/api/shop/health/ready  # 200 si Postgres répond, 503 sinon
curl http://127.0.0.1:8080/api/auth/health/ready  # 200 si la base d'auth répond, 503 sinon
```

Le front est servi sur <http://127.0.0.1:8080/>. Arrêt : `docker compose down` (ajouter `-v` pour supprimer les données).

| Élément | Règle |
|---|---|
| Port | `127.0.0.1:8180` (`--port` à la création du `.env`; ensuite modifier `GATEWAY_PORT` dans le `.env` du clone), pour ne pas entrer en conflit avec le 8080 des piles de développement. |
| Réseaux | `edge` (Traefik, hôte), `app` (Traefik, front, `shop`, `auth`, SeaweedFS, Mailpit; interne), `data` (`shop`, Postgres, SeaweedFS; interne), `auth-data` (`auth`, Postgres dédié; interne, inaccessible à `shop` et `payment`). |
| Routage | `/api/shop/*` vers `shop`, `/api/auth/*` vers `auth` (préfixe retiré), tout le reste vers le front. `/api/auth/internal/*` n'est jamais routé : réservé aux appels entre services. |
| Base | Postgres crée au premier démarrage un rôle et une base propres à `shop`; le compte administrateur n'est pas utilisé par les services. |
| Clés de signature | `scripts/init-auth-keys.sh` génère une paire Ed25519 dans `.secrets/auth/`, montée en secret Docker dans `auth`. Jamais versionnée; `--force` pour la renouveler. |
| Migrations | Les services one-shot `shop-migrate` et `auth-migrate` exécutent `alembic upgrade head` avant leur service; rejouables sans erreur. `auth-bootstrap` amorce ensuite les clients de service (secrets lus dans `.env`, hachés en base). |
| Images | Taguées `${COMPOSE_PROJECT_NAME:-basecamp}-<service>` (`basecamp-auth` par défaut) : deux piles aux noms de projet différents (`COMPOSE_PROJECT_NAME=basecamp-xyz`, avec un `GATEWAY_PORT` distinct) ne s'écrasent pas les images. |
| Conteneurs | Utilisateur non-root, `no-new-privileges`, capacités retirées, redémarrage `unless-stopped`, healthcheck sur chaque service. |

Les variables sont documentées dans `.env.example` (aucune valeur réelle). Les fins de ligne sont normalisées en LF par `.gitattributes` (Windows, WSL, Linux).

Mailpit, SeaweedFS et Postgres n'ont volontairement pas de port publié; pour les inspecter : `docker compose exec <service> ...` ou `docker compose logs <service>`.

## Tester `main` en local (pile de test)

Pour essayer l'application telle que `main` la livre, sans toucher aux branches de développement, un script met à jour un clone séparé de `main` et reconstruit la pile.

```bash
scripts/test-stack.sh
```

À lancer après chaque fusion sur `main` (Git Bash, WSL, macOS ou Linux, Docker démarré). Le script :

1. clone le dépôt au premier lancement, puis `git fetch` + `git reset --hard origin/main` + `git clean -fd` dans le clone de test (tout travail local y est perdu : ne jamais y développer);
2. crée `.env` depuis `.env.example` au premier lancement (valeurs factices, jamais versionné, jamais écrasé ensuite);
3. exécute `docker compose -p basecamp-test up -d --build --wait --remove-orphans`;
4. affiche l'état des services, l'adresse à ouvrir et le résultat de `/api/shop/health/ready`.

| Élément | Règle |
|---|---|
| Clone de test | `~/Desktop/Projects/BaseCamp-test` par défaut; autre emplacement via `--path` ou la variable `BASECAMP_TEST_DIR`. Il doit rester hors du dépôt de développement et de ses worktrees (le script refuse un chemin à l'intérieur). |
| Projet compose | `basecamp-test` : conteneurs, réseaux et volumes distincts de la pile de développement (`basecamp`). |
| Port | `127.0.0.1:8180` (`--port` à la création du `.env`; ensuite modifier `GATEWAY_PORT` dans le `.env` du clone), pour ne pas entrer en conflit avec le 8080 des piles de développement. |
| Dossier principal | `scripts/test-stack.sh --in-place --path <dossier>` lance la pile depuis un checkout existant de `main` (par exemple le dossier de travail) : `git pull --ff-only` au lieu de `reset --hard`, refus si la branche n'est pas `main` ou s'il y a des modifications suivies, `.env` existant requis et jamais modifié, port imposé par variable d'environnement. |
| Variables nouvelles | Hors `--in-place`, les variables apparues dans `.env.example` sont ajoutées au `.env` du clone (jamais écrasées) et les clés de signature d'auth sont générées. |
| Arrêt | `scripts/test-stack.sh --down` (garde les données), avec `--purge` pour les supprimer. |

Limite connue : les images locales `basecamp-shop`, `basecamp-auth`, `basecamp-payment` et `basecamp-front` portent le même nom dans toutes les piles; reconstruire la pile de test déplace ces étiquettes, sans effet sur les conteneurs de développement déjà démarrés (ils sont reconstruits au prochain `up --build`).
