#!/bin/sh
# Test de fumee de la pile de production, joue par scripts/deploy.sh apres `up --wait`.
# Passe par la passerelle (Traefik de la pile) depuis le conteneur front, sur le reseau interne :
# c'est le chemin reel d'une requete, sans rien publier. Utilise le contexte docker compose exporte
# par deploy.sh (COMPOSE_FILE, COMPOSE_PROJECT_NAME, COMPOSE_ENV_FILES).
set -eu

GATEWAY="${SMOKE_GATEWAY:-http://traefik:9080}"
failed=0

status() {
  docker compose exec -T front sh -c "wget -S -O /dev/null -T 5 '$GATEWAY$1' 2>&1 | awk '/^ *HTTP\//{c=\$2} END{print c}'"
}

check() {
  path="$1"
  expected="$2"
  got="$(status "$path" | tr -d '\r\n ')"
  if [ "$got" = "$expected" ]; then
    echo "smoke: OK   $path -> $got"
  else
    echo "smoke: ECHEC $path -> ${got:-aucune reponse} (attendu $expected)" >&2
    failed=1
  fi
}

check / 200
check /api/shop/health 200
check /api/auth/health 200
# Les routes internes d'auth ne doivent jamais etre exposees par la passerelle.
check /api/auth/internal/health 404

exit "$failed"
