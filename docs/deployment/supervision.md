# Raccordement à la supervision

La supervision (Prometheus, Loki, Grafana…) vit dans le dépôt **Supervision**. Ce dépôt n'en contient que le côté application : une surcouche compose qu'on ajoute avec `-f` **seulement quand on supervise**. Les piles principales (`docker-compose.yml`, `deploy/docker-compose.prod.yml`) ne sont pas modifiées par elle.

| Pile | Fichiers à passer à `docker compose -f …` |
|---|---|
| Développement | `docker-compose.yml` puis `docker-compose.supervision.yml` |
| Production | `deploy/docker-compose.prod.yml` puis `deploy/docker-compose.supervision.prod.yml` |

## Ce que la surcouche ajoute

| Élément | Rôle |
|---|---|
| Réseau externe `supervision` | rejoint par `traefik` (métriques sur `:9100`), `shop` et `auth` (sondes `/health`) et les trois exporters Postgres |
| Réseau `supervision-payment` (interne, créé par la pile) | rejoint par `payment` et par la sonde du dépôt Supervision, rien d'autre : `payment-net` reste fermé et le front n'atteint toujours pas `payment` |
| `pg-exporter-shop`, `-auth`, `-payment` | exporters Postgres (`:9187`) en lecture seule, chacun sur le réseau de données de sa base et sur `supervision` |
| Rôle Postgres `monitoring` | `pg_monitor` + `default_transaction_read_only`, 5 connexions max, connecté à la base `postgres` de l'instance : statistiques, aucune lecture des tables |

Cibles stables à utiliser côté Prometheus (alias réseau, indépendants du nom de projet compose) : `basecamp-traefik`, `basecamp-shop:8000`, `basecamp-auth:8000`, `basecamp-payment:8000`, `basecamp-pg-exporter-{shop,auth,payment}:9187`. Pour `payment`, le conteneur de sonde doit rejoindre **à la fois** `supervision` (pour être scrapé) et `supervision-payment` (pour atteindre `payment`).

Variables (modèles : `.env.example`, `deploy/prod.env.example`) : `MONITORING_DB_PASSWORD_SHOP`, `_AUTH`, `_PAYMENT` (un mot de passe distinct par base), et facultativement `SUPERVISION_NETWORK` et `SUPERVISION_PAYMENT_NETWORK`.

## Mise en route

1. Créer le réseau, de préférence **interne** pour que ni les services ni les exporters n'en tirent un accès sortant : `docker network create --internal supervision`.
2. Ajouter les trois mots de passe `MONITORING_DB_PASSWORD_*` au `.env` de la pile.
3. **Bases déjà en service** : créer le rôle `monitoring` (section suivante) avant ou juste après le démarrage.
4. Lancer la pile avec les deux fichiers (`up -d --wait`). Les exporters sont « healthy » même si le rôle manque encore : la santé de la base se lit dans la métrique `pg_up` (0 tant que le rôle n'existe pas).
5. Démarrer ensuite la pile Supervision, qui déclare `supervision` et `supervision-payment` en réseaux externes (la pile applicative doit donc être démarrée d'abord).

## Créer le rôle sur une base existante

Les scripts `infra/postgres/init-monitoring*.sh` ne s'exécutent qu'**au premier démarrage d'un volume vide**. Pour la VM et toute base déjà initialisée, deux possibilités équivalentes et rejouables sans risque.

**Avec les scripts (recommandé).** Après `up -d` avec la surcouche (qui monte les scripts et injecte `MONITORING_DB_PASSWORD` dans chaque base, sans toucher aux volumes) :

```bash
F="-f deploy/docker-compose.prod.yml -f deploy/docker-compose.supervision.prod.yml --env-file /opt/basecamp/.env --env-file /opt/basecamp/release.env"
for c in postgres postgres-auth payment-db; do
  docker compose $F exec -T "$c" sh /docker-entrypoint-initdb.d/20-init-monitoring.sh
done
```

**À la main**, sur chacune des trois instances (`postgres` pour shop, `postgres-auth`, `payment-db`), avec `<mot de passe>` pris dans le `.env` :

```bash
docker compose $F exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d postgres' <<'SQL'
CREATE ROLE monitoring LOGIN PASSWORD '<mot de passe>' CONNECTION LIMIT 5;
GRANT pg_monitor TO monitoring;
ALTER ROLE monitoring SET default_transaction_read_only = on;
SQL
```

Si le rôle existe déjà : remplacer le `CREATE ROLE` par `ALTER ROLE monitoring WITH LOGIN PASSWORD '<mot de passe>' CONNECTION LIMIT 5;`. Ne pas laisser le mot de passe dans l'historique du shell (le saisir depuis un fichier ou `read -s`).

Vérification : `pg_up 1` sur `basecamp-pg-exporter-<base>:9187/metrics`, et `docker compose $F exec -T postgres sh -c 'PGPASSWORD=$MONITORING_DB_PASSWORD psql -h 127.0.0.1 -U monitoring -d postgres -c "CREATE TABLE t(x int)"'` doit être refusé.

## Contrôle automatique

`scripts/check-supervision-stack.sh` (job `supervision-stack` de la CI) vérifie, pile démarrée avec la surcouche : sondes `/health` de `shop` et `auth` depuis `supervision`, `payment` injoignable depuis `supervision` mais joignable depuis `supervision-payment`, front toujours sans accès à `payment`, `pg_up 1` pour les trois exporters, rôle `monitoring` en lecture seule, aucun port publié en plus. Il se joue après `scripts/check-payment-isolation.sh`, qui doit rester vert avec la surcouche.

## Limites connues

- Les métriques et le journal d'accès de Traefik (`--metrics.prometheus`, point d'entrée `:9100`) sont ajoutés dans les compose principaux, pas ici : la surcouche ne fait que raccorder `traefik` au réseau.
- Dans `auth` et `payment`, le compte applicatif est le super-utilisateur de son instance dédiée; le rôle `monitoring` n'y change rien.
