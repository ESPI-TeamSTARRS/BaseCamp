#!/usr/bin/env bash
# Demonstration du retour automatique, sur une pile JETABLE (projet `basecamp-demo`).
# Ne touche PAS a la production : autre projet compose, autre dossier d'etat, autres volumes,
# aucun routage (GATEWAY_EXPOSE=false), secrets aleatoires propres a la demonstration.
#
#   bash scripts/deploy/demo-rollback.sh            joue la demonstration puis supprime la pile jetable
#   bash scripts/deploy/demo-rollback.sh --cleanup  supprime seulement une pile jetable restee en place
#
# Deroule : (1) deploie le manifeste de main (sain) ; (2) tente un manifeste dont le front est une
# image qui plante (busybox, sans serveur) ; (3) montre le retour automatique a la version saine, que
# `current.json` n'a pas bouge et que le manifeste fautif est note comme refuse.
# Duree : 5 a 8 minutes (premier deploiement complet). Memoire : environ 0,5 Gio en plus.

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEMO_PROJECT="basecamp-demo"
PYTHON="${PYTHON:-python3}"
COMPOSE_FILE="$ROOT/deploy/docker-compose.prod.yml"
SECRETS_DIR="${SECRETS_DIR:-/opt/basecamp/secrets}"
# Image qui plante : busybox demarre puis s'arrete, sans rien ecouter sur le port 3000.
BROKEN_IMAGE="docker.io/library/busybox@sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e"

say() { printf '\n== %s\n' "$*"; }

demo_compose() { # demo_compose <fichier env> <args...>
  local envf="$1"; shift
  docker compose -p "$DEMO_PROJECT" -f "$COMPOSE_FILE" --env-file "$envf" "$@"
}

cleanup() {
  local envf="${WORK:-}/state/compose.env"
  if [[ -n "${WORK:-}" && -f "$envf" ]]; then
    say "Nettoyage : suppression de la pile jetable $DEMO_PROJECT (volumes compris)"
    demo_compose "$envf" down -v --remove-orphans > /dev/null 2>&1 || true
  fi
  if [[ -n "${WORK:-}" ]]; then rm -rf -- "${WORK:?}"; fi
}

if [[ "${1:-}" == "--cleanup" ]]; then
  # Pile restee en place apres une interruption : on la retrouve par son projet compose.
  ids="$(docker ps -aq --filter "label=com.docker.compose.project=$DEMO_PROJECT")"
  if [[ -n "$ids" ]]; then
    # shellcheck disable=SC2086
    docker rm -f $ids > /dev/null
  fi
  docker network ls -q --filter "label=com.docker.compose.project=$DEMO_PROJECT" | xargs -r docker network rm > /dev/null 2>&1 || true
  docker volume ls -q --filter "label=com.docker.compose.project=$DEMO_PROJECT" | xargs -r docker volume rm > /dev/null 2>&1 || true
  echo "Pile $DEMO_PROJECT supprimee (la production n'est pas concernee)."
  exit 0
fi

# Garde-fou : jamais sur la production.
if [[ -n "$(docker ps -aq --filter "label=com.docker.compose.project=$DEMO_PROJECT")" ]]; then
  echo "Une pile $DEMO_PROJECT existe deja : lancer d'abord --cleanup." >&2
  exit 1
fi
docker network inspect "${WEB_NETWORK:-web}" > /dev/null 2>&1 || { echo "Reseau docker '${WEB_NETWORK:-web}' introuvable." >&2; exit 1; }
[[ -s "$SECRETS_DIR/auth/jwt-private.pem" ]] || { echo "Cles d'auth absentes de $SECRETS_DIR (SECRETS_DIR=... pour en indiquer d'autres)." >&2; exit 1; }

WORK="$(mktemp -d)"
trap cleanup EXIT

# Fichier d'environnement jetable : secrets aleatoires propres a la demonstration.
ENVF="$WORK/demo.env"
{
  echo "BASECAMP_DOMAIN=demo.invalide"
  echo "GATEWAY_EXPOSE=false"
  echo "SECRETS_DIR=$SECRETS_DIR"
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ ^([A-Z][A-Z0-9_]*)=change-me$ ]]; then
      printf '%s=%s\n' "${BASH_REMATCH[1]}" "$(openssl rand -hex 24)"
    fi
  done < "$ROOT/deploy/prod.env.example"
} > "$ENVF"
chmod 600 "$ENVF"

export BASECAMP_PROJECT="$DEMO_PROJECT" BASECAMP_STATE_DIR="$WORK/state" BASECAMP_ENV_FILE="$ENVF"
export BASECAMP_COMPOSE_FILE="$COMPOSE_FILE" WAIT_TIMEOUT=60 PYTHON
# Sauvegardes inutiles sur une pile jetable.
export BACKUP_TARGETS=""

say "1/3 Deploiement du manifeste de main (version saine)"
"$ROOT/scripts/deploy.sh" "$ROOT/deploy/manifest.json"

GOOD_FRONT="$("$PYTHON" -c 'import json,sys;print(json.load(sys.stdin)["services"]["frontend"]["image"])' < "$ROOT/deploy/manifest.json")"

say "2/3 Tentative de deploiement d'un manifeste dont le front est une image qui plante"
"$PYTHON" - "$ROOT/deploy/manifest.json" "$BROKEN_IMAGE" > "$WORK/manifeste-casse.json" << 'PYEOF'
import json, sys
manifest = json.load(open(sys.argv[1], encoding="utf-8"))
manifest["services"]["frontend"] = {"version": "9.9.9", "image": sys.argv[2]}
print(json.dumps(manifest, indent=2, sort_keys=True))
PYEOF
set +e
"$ROOT/scripts/deploy.sh" "$WORK/manifeste-casse.json"
RC=$?
set -e

say "3/3 Resultat"
echo "Code de sortie du deploiement casse : $RC (1 = echec avec retour arriere reussi)"
RUNNING="$(demo_compose "$WORK/state/compose.env" ps --format '{{.Service}} {{.Image}}' front | head -1)"
echo "Image du front en service : ${RUNNING#front }"
echo "Image attendue (saine)    : $GOOD_FRONT"
if [[ "$RC" == 1 && "${RUNNING#front }" == "$GOOD_FRONT" ]] && grep -q "$GOOD_FRONT" "$WORK/state/current.json" && [[ -s "$WORK/state/rejected" ]]; then
  echo "OK : le deploiement casse a ete refuse, la version saine est revenue seule, current.json est intact."
else
  echo "ECHEC de la demonstration : le retour automatique n'a pas produit l'etat attendu." >&2
  exit 1
fi
