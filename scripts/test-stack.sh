#!/usr/bin/env bash
# Met a jour un checkout de test de main et reconstruit la pile Basecamp en local.
#
# 1. Clone le depot dans --path si absent, sinon fetch + reset --hard sur origin/main
#    (le clone de test n'est jamais modifie a la main : tout travail local y est perdu).
#    Avec --in-place : git pull --ff-only sur un checkout existant de main, sans rien effacer.
# 2. Cree .env depuis .env.example au premier lancement (valeurs factices), y fixe
#    GATEWAY_PORT et ajoute les variables apparues depuis. Un .env existant n'est jamais ecrase.
# 3. Genere les cles de signature d'auth (ignorees par Git, idempotent).
# 4. Lance `docker compose -p basecamp-test up -d --build --wait`.
# 5. Affiche l'adresse a ouvrir et l'etat des services.
#
# Aucun secret : .env est ignore par Git.
#
# Exemples :
#   scripts/test-stack.sh
#   scripts/test-stack.sh --port 8181
#   scripts/test-stack.sh --in-place --path ~/Desktop/Projects/BaseCamp/BaseCamp
#   scripts/test-stack.sh --down [--purge]
set -euo pipefail

PROJECT_NAME="basecamp-test"
BRANCH="main"
TEST_PATH="${BASECAMP_TEST_DIR:-$HOME/Desktop/Projects/BaseCamp-test}"
PORT=8180
REPO_URL=""
DOWN=0
PURGE=0
IN_PLACE=0

usage() {
  sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --path) TEST_PATH="${2:?--path attend un dossier}"; shift 2 ;;
    --port) PORT="${2:?--port attend un numero}"; shift 2 ;;
    --repo-url) REPO_URL="${2:?--repo-url attend une URL}"; shift 2 ;;
    --down) DOWN=1; shift ;;
    --purge) PURGE=1; shift ;;
    --in-place) IN_PLACE=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "Option inconnue : $1" >&2; usage 1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_REPO="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || true)"

# Remplace ou ajoute CLE=valeur dans un fichier .env (LF, sans BOM).
set_env_value() {
  local file="$1" key="$2" value="$3" tmp
  tmp="$(mktemp)"
  if grep -Eq "^[[:space:]]*${key}=" "$file"; then
    sed -E "s|^[[:space:]]*${key}=.*|${key}=${value}|" "$file" >"$tmp"
  else
    cat "$file" >"$tmp"
    printf '%s=%s\n' "$key" "$value" >>"$tmp"
  fi
  cat "$tmp" >"$file"
  rm -f "$tmp"
}

# --- Garde-fous sur le chemin -------------------------------------------------
mkdir -p "$(dirname "$TEST_PATH")"
TEST_PATH="$(cd "$(dirname "$TEST_PATH")" && pwd)/$(basename "$TEST_PATH")"
if [ "$IN_PLACE" -eq 0 ] && [ -n "$SCRIPT_REPO" ]; then
  case "$TEST_PATH/" in
    "$SCRIPT_REPO"/*) echo "Le clone de test ne doit pas etre dans un depot de developpement ($SCRIPT_REPO)." >&2; exit 1 ;;
  esac
fi

compose() { (cd "$TEST_PATH" && docker compose -p "$PROJECT_NAME" "$@"); }

if [ "$DOWN" -eq 1 ]; then
  [ -f "$TEST_PATH/docker-compose.yml" ] || { echo "Aucune pile de test dans $TEST_PATH." >&2; exit 1; }
  if [ "$PURGE" -eq 1 ]; then compose down -v; else compose down; fi
  exit 0
fi

# --- 1. Clone / mise a jour de main -------------------------------------------
if [ ! -d "$TEST_PATH/.git" ] && [ ! -f "$TEST_PATH/.git" ]; then
  [ "$IN_PLACE" -eq 0 ] || { echo "$TEST_PATH n'est pas un depot Git : --in-place exige un checkout existant." >&2; exit 1; }
  [ -n "$REPO_URL" ] || REPO_URL="$(git -C "$SCRIPT_DIR" remote get-url origin)"
  [ -n "$REPO_URL" ] || { echo "Depot introuvable : passer --repo-url." >&2; exit 1; }
  if [ -d "$TEST_PATH" ] && [ -n "$(ls -A "$TEST_PATH")" ]; then
    echo "$TEST_PATH existe et n'est pas un clone Git : le vider ou choisir un autre --path." >&2
    exit 1
  fi
  echo "Clonage de $REPO_URL dans $TEST_PATH"
  git clone --branch "$BRANCH" "$REPO_URL" "$TEST_PATH"
elif [ "$IN_PLACE" -eq 1 ]; then
  echo "Mise a jour (fast-forward) de $TEST_PATH sur origin/$BRANCH"
  current="$(git -C "$TEST_PATH" branch --show-current)"
  [ "$current" = "$BRANCH" ] || { echo "$TEST_PATH est sur '$current' : --in-place exige la branche $BRANCH." >&2; exit 1; }
  if [ -n "$(git -C "$TEST_PATH" status --porcelain --untracked-files=no)" ]; then
    echo "$TEST_PATH a des modifications locales : les valider ou les ranger avant." >&2
    exit 1
  fi
  git -C "$TEST_PATH" pull --ff-only origin "$BRANCH"
else
  echo "Mise a jour de $TEST_PATH sur origin/$BRANCH"
  git -C "$TEST_PATH" fetch --prune origin "$BRANCH"
  git -C "$TEST_PATH" checkout --force "$BRANCH"
  git -C "$TEST_PATH" reset --hard "origin/$BRANCH"
  # Supprime les fichiers non suivis ; les fichiers ignores (.env) sont conserves.
  git -C "$TEST_PATH" clean -fd
fi
echo "Version testee : $(git -C "$TEST_PATH" log -1 --format='%h %s')"

# --- 2. Configuration locale (.env factice, non versionne) --------------------
ENV_FILE="$TEST_PATH/.env"
if [ "$IN_PLACE" -eq 1 ]; then
  # Le .env du dossier principal n'est jamais modifie : le port est impose par l'environnement.
  [ -f "$ENV_FILE" ] || { echo "$ENV_FILE manquant : le creer depuis .env.example." >&2; exit 1; }
  export GATEWAY_PORT="$PORT"
  export NEXT_PUBLIC_SITE_URL="http://localhost:$PORT"
  CURRENT_PORT="$PORT"
else
  if [ ! -f "$ENV_FILE" ]; then
    cp "$TEST_PATH/.env.example" "$ENV_FILE"
    set_env_value "$ENV_FILE" GATEWAY_PORT "$PORT"
    set_env_value "$ENV_FILE" NEXT_PUBLIC_SITE_URL "http://localhost:$PORT"
    echo ".env cree depuis .env.example (valeurs factices)."
  else
    # .env existant : jamais ecrase, mais on y ajoute les variables apparues dans .env.example.
    added=0
    while IFS= read -r line; do
      key="$(printf '%s' "$line" | sed -nE 's/^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=.*/\1/p')"
      [ -n "$key" ] || continue
      if ! grep -Eq "^[[:space:]]*${key}=" "$ENV_FILE"; then
        [ -z "$(tail -c1 "$ENV_FILE")" ] || printf '\n' >>"$ENV_FILE"
        printf '%s\n' "$line" >>"$ENV_FILE"
        added=$((added + 1))
      fi
    done <"$TEST_PATH/.env.example"
    [ "$added" -eq 0 ] || echo "$added variable(s) ajoutee(s) au .env depuis .env.example."
  fi
  CURRENT_PORT="$(sed -nE 's/^GATEWAY_PORT=(.*)$/\1/p' "$ENV_FILE" | tr -d '[:space:]')"
  CURRENT_PORT="${CURRENT_PORT:-8080}"
fi

# --- 3. Cles de signature d'auth (ignorees par Git, idempotent) ---------------
if [ -f "$TEST_PATH/scripts/init-auth-keys.sh" ]; then
  (cd "$TEST_PATH" && sh scripts/init-auth-keys.sh)
fi

# --- 4. Reconstruction de la pile ---------------------------------------------
compose up -d --build --wait --remove-orphans

# --- 5. Resultat --------------------------------------------------------------
echo
compose ps --all
echo
echo "Application : http://127.0.0.1:${CURRENT_PORT}/"
if status="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:${CURRENT_PORT}/api/shop/health/ready")"; then
  echo "Sante shop (/api/shop/health/ready) : HTTP $status"
else
  echo "Sante shop injoignable." >&2
fi
