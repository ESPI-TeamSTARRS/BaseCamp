#!/bin/sh
# Verifie l'isolation de payment sur la pile en cours (docker compose up deja lance).
# Usage : sh scripts/check-payment-isolation.sh
set -eu

fail() { echo "ECHEC : $1" >&2; exit 1; }

PROBE_READY="import urllib.request as u, urllib.error as e
try:
    print(u.urlopen('http://payment:8000/health/ready', timeout=3).status)
except e.HTTPError as err:
    print(err.code)"
RESOLVES="import socket, sys
try:
    socket.getaddrinfo(sys.argv[1], 80)
except socket.gaierror:
    sys.exit(1)"

# 1. payment n'est publie sur aucun port de l'hote
published=$(docker compose ps --format '{{.Publishers}}' payment payment-db)
case "$published" in *"->"*) fail "payment ou sa base est publie sur l'hote : $published" ;; esac

# 2. shop atteint payment (liveness et readiness)
[ "$(docker compose exec -T shop python -c "$PROBE_READY")" = "200" ] || fail "shop n'atteint pas payment"

# 3. les autres services ne l'atteignent pas (front, traefik, mailpit : reseau app seulement)
docker compose exec -T front wget -q -T 3 -O /dev/null http://payment:8000/health \
  && fail "front atteint payment"
docker compose exec -T front wget -q -T 3 -O /dev/null http://payment:8000/metrics \
  && fail "front atteint /metrics de payment"

# 4. etancheite des bases : shop ne voit pas payment-db, payment ne voit pas postgres
docker compose exec -T shop python -c "$RESOLVES" payment-db && fail "shop voit payment-db"
docker compose exec -T payment python -c "$RESOLVES" postgres && fail "payment voit la base du shop"

# 5. migrations idempotentes : un second passage reussit
docker compose run --rm --no-deps payment-migrate >/dev/null || fail "migration non idempotente"

# 6. base arretee : readiness 503, liveness 200
docker compose stop payment-db >/dev/null
trap 'docker compose start payment-db >/dev/null' EXIT
sleep 2
[ "$(docker compose exec -T shop python -c "$PROBE_READY")" = "503" ] || fail "readiness doit etre 503 base arretee"
docker compose exec -T shop python -c \
  "import urllib.request as u; u.urlopen('http://payment:8000/health', timeout=3)" \
  || fail "liveness doit rester 200 base arretee"

echo "OK : payment est isole et sain"
