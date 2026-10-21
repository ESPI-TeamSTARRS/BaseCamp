#!/bin/sh
# Verifie le raccordement a la supervision sur la pile en cours (deja lancee avec la surcouche).
# Usage :
#   docker network create --internal "$SUPERVISION_NETWORK"      # defaut : supervision
#   docker compose -f docker-compose.yml -f docker-compose.supervision.yml up -d --wait ...
#   COMPOSE_FILE=docker-compose.yml:docker-compose.supervision.yml sh scripts/check-supervision-stack.sh
set -eu

fail() { echo "ECHEC : $1" >&2; exit 1; }

SUPERVISION_NETWORK="${SUPERVISION_NETWORK:-supervision}"
SUPERVISION_PAYMENT_NETWORK="${SUPERVISION_PAYMENT_NETWORK:-supervision-payment}"
PROBE_IMAGE="${PROBE_IMAGE:-basecamp-shop}"   # image applicative deja construite : python present
PROBE=basecamp-supervision-probe

GET="import sys, urllib.request as u
print(u.urlopen(sys.argv[1], timeout=3).status)"

cleanup() { docker rm -f "$PROBE" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

# Sonde de test : sur le reseau `supervision` seulement, comme Prometheus / blackbox.
docker run -d --name "$PROBE" --network "$SUPERVISION_NETWORK" --entrypoint sleep \
  "$PROBE_IMAGE" 600 >/dev/null
probe() { docker exec "$PROBE" python -c "$GET" "$1"; }

# 1. shop et auth repondent aux sondes /health depuis le reseau de supervision
for svc in shop auth; do
  [ "$(probe "http://basecamp-$svc:8000/health")" = "200" ] || fail "sonde $svc"
done

# 2. payment n'est PAS joignable depuis le reseau de supervision general ...
probe "http://basecamp-payment:8000/health" >/dev/null 2>&1 && fail "payment joignable depuis supervision"
probe "http://payment:8000/health" >/dev/null 2>&1 && fail "payment joignable depuis supervision (nom court)"
# ... mais l'est depuis le reseau dedie, une fois la sonde rattachee aux deux
docker network connect "$SUPERVISION_PAYMENT_NETWORK" "$PROBE"
[ "$(probe "http://basecamp-payment:8000/health")" = "200" ] || fail "sonde payment via supervision-payment"

# 3. le front (reseau app) n'atteint toujours pas payment
docker compose exec -T front wget -q -T 3 -O /dev/null http://payment:8000/health \
  && fail "front atteint payment"

# 4. exporters Postgres : joignables, base accessible avec le role monitoring
for db in shop auth payment; do
  out=$(docker exec "$PROBE" python -c "import sys, urllib.request as u
print(u.urlopen(sys.argv[1], timeout=5).read().decode())" "http://basecamp-pg-exporter-$db:9187/metrics")
  echo "$out" | grep -q '^pg_up 1' || fail "exporter $db : pg_up != 1"
done

# 5. le role monitoring est en lecture seule et n'atteint pas les donnees applicatives
for entry in "postgres:shop" "postgres-auth:auth" "payment-db:payment"; do
  ctr=${entry%%:*}; app=${entry##*:}
  psql_mon() { docker compose exec -T "$ctr" sh -c \
    "PGPASSWORD=\"\$MONITORING_DB_PASSWORD\" psql -h 127.0.0.1 -U monitoring -d postgres -v ON_ERROR_STOP=1 -tA -c \"\$1\"" -- "$1"; }
  [ "$(psql_mon "SELECT pg_has_role('monitoring','pg_monitor','member')")" = "t" ] || fail "$ctr : pg_monitor manquant"
  psql_mon "CREATE TABLE ecriture_interdite(x int)" >/dev/null 2>&1 && fail "$ctr : le role monitoring peut ecrire"
  [ "$(psql_mon "SELECT rolsuper FROM pg_roles WHERE rolname='monitoring'")" = "f" ] || fail "$ctr : monitoring est superuser"
done

# 6. rien de plus n'est publie sur l'hote
published=$(docker compose ps --format '{{.Service}} {{.Publishers}}' | grep -- '->' || true)
[ "$(printf '%s' "$published" | grep -vc '^traefik ' || true)" = "0" ] || fail "ports publies en trop : $published"

echo "OK : la supervision est raccordee sans casser l'isolation"
