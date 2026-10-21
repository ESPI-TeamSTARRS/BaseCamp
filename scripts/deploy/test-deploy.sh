#!/usr/bin/env bash
# Test de bascule et de retour arriere de scripts/deploy.sh, avec une panne volontaire.
#
# Monte un registre local, y publie trois images minuscules (v1 et v2 saines, v3 qui plante), puis
# joue les scenarios de deploiement reels (docker compose, digests, etat) contre une pile de test.
# Aucun acces reseau externe en dehors de l'image busybox.
#
#   sh scripts/deploy/test-deploy.sh        (necessite docker)
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
WORK="$(mktemp -d)"
REG_NAME="deploytest-registry-$$"
REG_PORT="${TEST_REGISTRY_PORT:-5055}"
REPO="localhost:$REG_PORT/dt"
PASS=0
FAIL=0

export BASECAMP_COMPOSE_FILE="$HERE/testdata/docker-compose.test.yml"
export BASECAMP_PROJECT="deploytest"
export BASECAMP_ENV_FILE=""
export DEPLOY_SERVICES="shop"
export DB_SERVICES=""
export MIGRATE_SERVICES=""
export BACKUP_TARGETS=""
export WAIT_TIMEOUT=30
export SMOKE_CMD='docker compose exec -T shop wget -q -O /dev/null http://127.0.0.1:8080/health'

cleanup() {
  COMPOSE_FILE="$BASECAMP_COMPOSE_FILE" COMPOSE_PROJECT_NAME="$BASECAMP_PROJECT" \
    COMPOSE_ENV_FILES="" SHOP_IMAGE="$REPO:v1" docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  docker rm -f "$REG_NAME" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

ok() { PASS=$((PASS + 1)); echo "  ok   $*"; }
ko() { FAIL=$((FAIL + 1)); echo "  ECHEC $*" >&2; tail -n 15 "$WORK/deploy.log" 2>/dev/null | sed "s/^/      | /" >&2; }

expect() { # expect <description> <commande...>
  local desc="$1"; shift
  if "$@"; then ok "$desc"; else ko "$desc"; fi
}

STATE_CUR=""

served_version() {
  COMPOSE_FILE="$BASECAMP_COMPOSE_FILE" COMPOSE_PROJECT_NAME="$BASECAMP_PROJECT" COMPOSE_ENV_FILES="$STATE_CUR/release.env" \
    docker compose exec -T shop sh -c 'cat /www/index.html' 2>/dev/null | tr -d '\r\n'
}

stack_running() {
  COMPOSE_FILE="$BASECAMP_COMPOSE_FILE" COMPOSE_PROJECT_NAME="$BASECAMP_PROJECT" COMPOSE_ENV_FILES="$STATE_CUR/release.env" \
    docker compose ps --status running -q shop 2>/dev/null | grep -q .
}

manifest() { # manifest <fichier> <digest-image>
  printf '{"schema":1,"services":{"shop":{"version":"0.1.0","image":"%s"}}}\n' "$2" > "$1"
}

deploy() { # deploy <etat> <manifeste> [options] -> code de sortie dans $RC
  set +e
  BASECAMP_STATE_DIR="$1" "$ROOT/scripts/deploy.sh" "${@:2}" >"$WORK/deploy.log" 2>&1
  RC=$?
  set -e
}

# --- Images de test ----------------------------------------------------------------------------
echo "== Preparation : registre local et images v1, v2 (saines), v3 (en panne)"
docker run -d --name "$REG_NAME" -p "$REG_PORT:5000" registry:2 >/dev/null

cat > "$WORK/Dockerfile" <<'DOCKERFILE'
FROM busybox:1.37
ARG VERSION
ARG BROKEN=0
RUN mkdir /www && echo "$VERSION" > /www/index.html && echo ok > /www/health
ENV BROKEN=$BROKEN
CMD ["sh", "-c", "if [ \"$BROKEN\" = 1 ]; then sleep 2; exit 1; fi; exec httpd -f -p 8080 -h /www"]
DOCKERFILE

build_push() { # build_push <version> <broken> -> imprime la reference par digest
  docker build -q -t "$REPO:$1" --build-arg "VERSION=$1" --build-arg "BROKEN=$2" "$WORK" >/dev/null
  docker push -q "$REPO:$1" >/dev/null
  docker inspect --format '{{index .RepoDigests 0}}' "$REPO:$1"
}
V1="$(build_push v1 0)"; V2="$(build_push v2 0)"; V3="$(build_push v3 1)"
# L'hote ne doit pas servir les images depuis son cache local : on force le tirage du registre.
docker rmi "$REPO:v1" "$REPO:v2" "$REPO:v3" >/dev/null 2>&1 || true

manifest "$WORK/m1.json" "$V1"
manifest "$WORK/m2.json" "$V2"
manifest "$WORK/m3.json" "$V3"
printf '{"schema":1,"services":{"shop":{"version":"0.1.0","image":"%s/dt@sha256:%064d"}}}\n' "localhost:$REG_PORT" 0 > "$WORK/m-absent.json"

# --- Scenario A : premier deploiement ----------------------------------------------------------
echo "== A. Premier deploiement sain"
S="$WORK/state-a"
STATE_CUR="$S"
deploy "$S" "$WORK/m1.json"
expect "sortie 0" test "$RC" = 0
expect "v1 en service" test "$(served_version)" = v1
expect "manifeste current ecrit" test -f "$S/current.json"
expect "pas de previous au premier deploiement" test ! -f "$S/previous.json"

echo "== B. Mise a jour saine v1 -> v2"
deploy "$S" "$WORK/m2.json"
expect "sortie 0" test "$RC" = 0
expect "v2 en service" test "$(served_version)" = v2
expect "previous = v1" grep -q "$V1" "$S/previous.json"
expect "current = v2" grep -q "$V2" "$S/current.json"

echo "== C. Panne volontaire : v3 plante, retour automatique a v2"
deploy "$S" "$WORK/m3.json"
expect "sortie 1 (echec avec retour arriere)" test "$RC" = 1
expect "retour a v2" test "$(served_version)" = v2
expect "la pile tourne" stack_running
expect "current reste v2" grep -q "$V2" "$S/current.json"
expect "v3 notee comme refusee" test -s "$S/rejected"
expect "le journal annonce le retour arriere" grep -q "RETOUR ARRIERE reussi" "$WORK/deploy.log"

echo "== D. Pas de boucle : v3 refusee n'est pas rejouee"
deploy "$S" "$WORK/m3.json"
expect "sortie 0 (ignore)" test "$RC" = 0
expect "toujours v2" test "$(served_version)" = v2
expect "message de refus precedent" grep -q "deja ete refuse" "$WORK/deploy.log"

echo "== E. Idempotence : redeployer v2 ne fait rien"
deploy "$S" "$WORK/m2.json"
expect "sortie 0" test "$RC" = 0
expect "message deja en place" grep -q "deja en place" "$WORK/deploy.log"

echo "== F. Image introuvable : rien n'est touche"
deploy "$S" "$WORK/m-absent.json"
expect "sortie 1" test "$RC" = 1
expect "toujours v2 en service" test "$(served_version)" = v2
expect "current reste v2" grep -q "$V2" "$S/current.json"

echo "== G. Manifeste invalide (tag a la place du digest)"
printf '{"schema":1,"services":{"shop":{"version":"0.1.0","image":"%s:v2"}}}\n' "$REPO" > "$WORK/m-tag.json"
deploy "$S" "$WORK/m-tag.json"
expect "sortie 3" test "$RC" = 3
expect "toujours v2 en service" test "$(served_version)" = v2

echo "== H. Premier deploiement en panne : la pile est arretee"
COMPOSE_FILE="$BASECAMP_COMPOSE_FILE" COMPOSE_PROJECT_NAME="$BASECAMP_PROJECT" COMPOSE_ENV_FILES="" SHOP_IMAGE="$V2" \
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
deploy "$WORK/state-h" "$WORK/m3.json"
expect "sortie 1" test "$RC" = 1
expect "aucun conteneur en service" bash -c '! docker ps -q --filter label=com.docker.compose.project=deploytest | grep -q .'
expect "pas de current" test ! -f "$WORK/state-h/current.json"

echo
echo "Resultat : $PASS verifications reussies, $FAIL en echec."
[[ "$FAIL" == 0 ]]
