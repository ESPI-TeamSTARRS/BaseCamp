#!/usr/bin/env bash
# Deploie un manifeste de release sur la pile de production, avec retour automatique.
#
#   scripts/deploy.sh <manifeste.json> [--force]
#
# Deroule :
#   1. valide le manifeste (une version de chaque composant, images par digest) ;
#   2. s'arrete si ce jeu de digests est deja en place, ou deja refuse (pas de boucle) ;
#   3. tire les images par digest (echec ici = rien n'a ete touche) ;
#   4. sauvegarde les bases (pg_dump) si elles tournent ;
#   5. applique les migrations avec les nouvelles images, puis demarre la pile (`up --wait`) ;
#   6. joue le test de fumee ;
#   7. succes : le manifeste devient `current` (l'ancien devient `previous`) ;
#      echec : retour automatique aux images precedentes, le manifeste est note comme refuse.
#
# Les migrations sont retro-compatibles (expand puis contract) : l'ancienne version continue a
# fonctionner sur le schema migre, donc le retour arriere ne restaure pas les bases (les sauvegardes
# servent aux incidents de donnees). Voir docs/deployment/runbook.md.
#
# Codes de sortie : 0 succes ou rien a faire, 1 echec avec retour arriere reussi (ou rien touche),
# 2 echec ET retour arriere en echec (intervention humaine), 3 usage ou manifeste invalide.
#
# Variables (valeurs par defaut = production sur la VM ; surchargees par le test de bascule) :
#   BASECAMP_COMPOSE_FILE, BASECAMP_PROJECT, BASECAMP_STATE_DIR, BASECAMP_ENV_FILE,
#   DEPLOY_SERVICES, DB_SERVICES, MIGRATE_SERVICES, BACKUP_TARGETS, SMOKE_CMD, WAIT_TIMEOUT,
#   BACKUP_KEEP

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${BASECAMP_COMPOSE_FILE:-$ROOT/deploy/docker-compose.prod.yml}"
PROJECT="${BASECAMP_PROJECT:-basecamp-prod}"
STATE_DIR="${BASECAMP_STATE_DIR:-/opt/basecamp/state}"
ENV_FILE="${BASECAMP_ENV_FILE-/opt/basecamp/.env}"
DB_SERVICES="${DB_SERVICES-postgres postgres-auth payment-db}"
MIGRATE_SERVICES="${MIGRATE_SERVICES-shop-migrate auth-migrate payment-migrate}"
# service:variable-utilisateur:variable-base (lues DANS le conteneur, donc sans secret ici).
BACKUP_TARGETS="${BACKUP_TARGETS-postgres:SHOP_DB_USER:SHOP_DB_NAME postgres-auth:POSTGRES_USER:POSTGRES_DB payment-db:POSTGRES_USER:POSTGRES_DB}"
SMOKE_CMD="${SMOKE_CMD:-$ROOT/scripts/deploy/smoke.sh}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-180}"
BACKUP_KEEP="${BACKUP_KEEP:-7}"
PYTHON="${PYTHON:-python3}"
MANIFEST_PY="$ROOT/scripts/deploy/manifest.py"

log() { printf '%s deploy: %s\n' "$(date -u +%FT%TZ)" "$*"; }
die() { log "ERREUR: $*"; exit "${2:-1}"; }

usage() {
  sed -n '2,3p' "${BASH_SOURCE[0]}" >&2
  exit 3
}

FORCE=0
MANIFEST=""
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    -*) usage ;;
    *) [ -z "$MANIFEST" ] && MANIFEST="$arg" || usage ;;
  esac
done
[ -n "$MANIFEST" ] || usage

"$PYTHON" "$MANIFEST_PY" validate "$MANIFEST" || exit 3
NEW_ID="$("$PYTHON" "$MANIFEST_PY" id "$MANIFEST")"

mkdir -p "$STATE_DIR/backups"
chmod 700 "$STATE_DIR"

# Un seul deploiement a la fois (minuteur, lancement manuel...).
exec 9>"$STATE_DIR/deploy.lock"
if command -v flock >/dev/null 2>&1; then
  flock -n 9 || die "un autre deploiement est en cours" 1
else
  log "flock absent : verrou ignore (poste de developpement ; la VM Ubuntu fournit flock)."
fi

CURRENT_JSON="$STATE_DIR/current.json"
PREVIOUS_JSON="$STATE_DIR/previous.json"
RELEASE_ENV="$STATE_DIR/release.env"
REJECTED="$STATE_DIR/rejected"
touch "$REJECTED"

CURRENT_ID=""
[ -f "$CURRENT_JSON" ] && CURRENT_ID="$("$PYTHON" "$MANIFEST_PY" id "$CURRENT_JSON")"

if [ "$FORCE" = 0 ]; then
  if [ "$NEW_ID" = "$CURRENT_ID" ]; then
    log "ce manifeste est deja en place, rien a faire."
    exit 0
  fi
  if grep -qx "$NEW_ID" "$REJECTED"; then
    log "ce manifeste a deja ete refuse (echec de deploiement), ignore. Corriger puis publier un nouveau manifeste, ou relancer avec --force."
    exit 0
  fi
fi

# Fichier d'environnement UNIQUE passe a compose : secrets de la VM (.env) + references d'images du
# manifeste (release.env, qui l'emporte). Un seul fichier evite toute ambiguite d'ordre.
COMPOSE_ENV="$STATE_DIR/compose.env"
build_env() { # build_env <release.env> <sortie>
  {
    if [ -n "$ENV_FILE" ] && [ -f "$ENV_FILE" ]; then cat "$ENV_FILE"; echo; fi
    cat "$1"
  } > "$2"
  chmod 600 "$2"
}

# Toutes les commandes docker compose partagent ce contexte (smoke.sh aussi).
export COMPOSE_FILE COMPOSE_PROJECT_NAME="$PROJECT" COMPOSE_ENV_FILES="$COMPOSE_ENV"

compose() { docker compose "$@"; }

# --- 1. images : tirage par digest (avant toute modification) ---------------------------------
NEW_ENV="$STATE_DIR/release.env.new"
"$PYTHON" "$MANIFEST_PY" env "$MANIFEST" > "$NEW_ENV"
chmod 600 "$NEW_ENV"

log "tirage des images du manifeste $NEW_ID"
build_env "$NEW_ENV" "$COMPOSE_ENV.new"
if ! COMPOSE_ENV_FILES="$COMPOSE_ENV.new" docker compose pull --quiet; then
  rm -f "$NEW_ENV" "$COMPOSE_ENV.new"
  die "tirage des images impossible, aucune modification effectuee" 1
fi

# --- 2. sauvegarde des bases ------------------------------------------------------------------
backup_databases() {
  [ -n "$BACKUP_TARGETS" ] || return 0
  local stamp dir target service uservar dbvar
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  dir="$STATE_DIR/backups/$stamp"
  for target in $BACKUP_TARGETS; do
    IFS=: read -r service uservar dbvar <<<"$target"
    if [ -z "$(compose ps --status running -q "$service" 2>/dev/null)" ]; then
      log "sauvegarde ignoree : $service ne tourne pas (premier deploiement ?)"
      continue
    fi
    mkdir -p "$dir"
    chmod 700 "$dir"
    log "sauvegarde de $service"
    compose exec -T "$service" sh -c "pg_dump -U \"\$$uservar\" \"\$$dbvar\"" | gzip > "$dir/$service.sql.gz"
    chmod 600 "$dir/$service.sql.gz"
  done
  # Conserve les BACKUP_KEEP dernieres sauvegardes.
  find "$STATE_DIR/backups" -mindepth 1 -maxdepth 1 -type d | sort -r | tail -n +"$((BACKUP_KEEP + 1))" |
    while read -r old; do rm -rf "${old:?}"; done
}

# --- 3. bascule -------------------------------------------------------------------------------
# Appelee dans une condition (`if (apply_release)`) : `set -e` y est inactif, donc chaque etape
# porte son propre `|| return 1`.
apply_release() {
  local svc
  if [ -n "$DB_SERVICES" ]; then
    log "demarrage des bases"
    # shellcheck disable=SC2086
    compose up -d --wait --wait-timeout "$WAIT_TIMEOUT" $DB_SERVICES || return 1
  fi
  for svc in $MIGRATE_SERVICES; do
    log "migration : $svc"
    compose run --rm --no-deps "$svc" || return 1
  done
  log "demarrage de la pile"
  compose up -d --wait --wait-timeout "$WAIT_TIMEOUT" --remove-orphans || return 1
  if [ ! -f "$CURRENT_JSON" ] && compose --profile jobs config --services 2>/dev/null | grep -qx seaweedfs-seed; then
    log "premier deploiement : amorcage du bucket d'images"
    compose --profile jobs run --rm seaweedfs-seed || return 1
  fi
  log "test de fumee"
  sh -c "$SMOKE_CMD" || return 1
}

# Retour arriere : memes services SANS les taches de migration. L'ancienne image ne connait pas
# forcement la derniere revision de schema : relancer `alembic upgrade head` avec elle echouerait.
restore_previous() {
  local services
  services="$(compose config --services | grep -v -- '-migrate$' | tr '
' ' ')"
  # shellcheck disable=SC2086
  compose up -d --wait --wait-timeout "$WAIT_TIMEOUT" --no-deps --remove-orphans $services || return 1
  sh -c "$SMOKE_CMD" || return 1
}

backup_databases

[ -f "$RELEASE_ENV" ] && cp "$RELEASE_ENV" "$STATE_DIR/release.env.previous"
mv "$NEW_ENV" "$RELEASE_ENV"
mv "$COMPOSE_ENV.new" "$COMPOSE_ENV"

if (apply_release); then
  [ -f "$CURRENT_JSON" ] && cp "$CURRENT_JSON" "$PREVIOUS_JSON"
  cp "$MANIFEST" "$CURRENT_JSON"
  log "SUCCES : manifeste $NEW_ID en production."
  exit 0
fi

# --- 4. echec : retour automatique ------------------------------------------------------------
log "ECHEC du deploiement de $NEW_ID, retour arriere."
echo "$NEW_ID" >> "$REJECTED"

if [ -f "$CURRENT_JSON" ] && [ -f "$STATE_DIR/release.env.previous" ]; then
  cp "$STATE_DIR/release.env.previous" "$RELEASE_ENV"
  build_env "$RELEASE_ENV" "$COMPOSE_ENV"
  if (restore_previous); then
    log "RETOUR ARRIERE reussi : la version precedente est de nouveau en service."
    exit 1
  fi
  die "retour arriere EN ECHEC : intervention humaine necessaire (voir docs/deployment/runbook.md)" 2
fi

# Premier deploiement rate : rien a restaurer, on n'expose pas une pile cassee.
log "aucune version precedente : arret de la pile."
compose down --remove-orphans || true
rm -f "$RELEASE_ENV" "$COMPOSE_ENV"
exit 1
