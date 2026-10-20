#!/usr/bin/env bash
# Installe le deploiement par tirage de Basecamp sur la VM Ubuntu. A lancer par Sam, en root.
# Idempotent : peut etre relance sans danger, ne remplace jamais un secret existant.
#
#   sudo BASECAMP_DOMAIN=basecamp.tempulse.fr bash infra/install-vm.sh            installe
#   sudo bash infra/install-vm.sh --check                                          verifie seulement
#   sudo bash infra/install-vm.sh --enable-timer                                   active les deploiements
#
# Ce que fait le script : utilisateur `basecamp`, dossiers sous /opt/basecamp, copie du depot public,
# fichier /opt/basecamp/.env (secrets ALEATOIRES generes ici, stockes seulement sur la VM), cles de
# signature d'auth, unites systemd. Il n'ACTIVE PAS le minuteur sans --enable-timer : la bascule depuis
# l'ancienne pile est une etape manuelle (docs/deployment/runbook.md).
#
# Il ne se connecte a rien d'autre que github.com (clone public) et n'ouvre aucun port.

set -Eeuo pipefail

BASE="${BASECAMP_BASE:-/opt/basecamp}"
REPO_URL="${BASECAMP_REPO_URL:-https://github.com/ESPI-TeamSTARRS/BaseCamp.git}"
APP_USER="basecamp"
WEB_NETWORK="${WEB_NETWORK:-web}"
OLD_PROJECT="${BASECAMP_BLOCK_IF_RUNNING-basecamp-outdoor}"
DOMAIN="${BASECAMP_DOMAIN:-}"

MODE="install"
for arg in "$@"; do
  case "$arg" in
    --check) MODE="check" ;;
    --enable-timer) MODE="enable" ;;
    *) echo "Option inconnue : $arg" >&2; exit 3 ;;
  esac
done

log() { printf 'install: %s\n' "$*"; }
fail() { printf 'install: ERREUR : %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" == 0 ]] || fail "a lancer en root (sudo)."

# --- 1. prerequis -----------------------------------------------------------------------------
missing=0
for cmd in docker git flock python3 openssl systemctl runuser; do
  command -v "$cmd" > /dev/null 2>&1 || { log "outil manquant : $cmd"; missing=1; }
done
docker compose version > /dev/null 2>&1 || { log "plugin docker compose manquant"; missing=1; }
[[ "$missing" == 0 ]] || fail "installer les outils manquants puis relancer."
docker network inspect "$WEB_NETWORK" > /dev/null 2>&1 || fail "reseau Docker '$WEB_NETWORK' introuvable (celui du Traefik du serveur)."
log "prerequis OK (docker, compose, git, flock, python3, openssl, systemd, reseau $WEB_NETWORK)."

old_running() {
  [[ -n "$OLD_PROJECT" ]] && [[ -n "$(docker ps -q --filter "label=com.docker.compose.project=$OLD_PROJECT")" ]]
}

if [[ "$MODE" == "check" ]]; then
  [[ -d "$BASE/repo/.git" ]] && log "depot present dans $BASE/repo" || log "depot absent (sera clone a l'installation)"
  [[ -s "$BASE/.env" ]] && log "$BASE/.env present" || log "$BASE/.env absent (sera cree a l'installation)"
  systemctl is-enabled basecamp-deploy.timer > /dev/null 2>&1 && log "minuteur actif" || log "minuteur non active"
  if old_running; then log "l'ancienne pile '$OLD_PROJECT' tourne encore."; fi
  exit 0
fi

# --- 2. activation du minuteur (apres la bascule manuelle) -------------------------------------
if [[ "$MODE" == "enable" ]]; then
  [[ -f /etc/systemd/system/basecamp-deploy.timer ]] || fail "unites absentes : lancer d'abord l'installation."
  if old_running; then
    fail "l'ancienne pile '$OLD_PROJECT' tourne encore. L'arreter (bascule du runbook) avant d'activer les deploiements."
  fi
  systemctl enable --now basecamp-deploy.timer
  log "minuteur actif : le prochain deploiement a lieu dans quelques minutes (journalctl -u basecamp-deploy -f)."
  exit 0
fi

# --- 3. utilisateur et dossiers -----------------------------------------------------------------
if ! id "$APP_USER" > /dev/null 2>&1; then
  useradd --system --home-dir "$BASE" --shell /usr/sbin/nologin "$APP_USER"
  log "utilisateur $APP_USER cree."
fi
# Le groupe docker donne un acces equivalent a root sur la machine : l'utilisateur n'a ni mot de
# passe ni shell, et ne sert qu'a l'unite systemd.
usermod -aG docker "$APP_USER"

install -d -o "$APP_USER" -g "$APP_USER" -m 750 "$BASE"
install -d -o "$APP_USER" -g "$APP_USER" -m 700 "$BASE/state"
install -d -o "$APP_USER" -g "$APP_USER" -m 750 "$BASE/secrets"

# --- 4. depot (public, lecture seule) -----------------------------------------------------------
if [[ -d "$BASE/repo/.git" ]]; then
  runuser -u "$APP_USER" -- git -C "$BASE/repo" fetch --quiet origin main
  runuser -u "$APP_USER" -- git -C "$BASE/repo" -c advice.detachedHead=false checkout --quiet --force --detach origin/main
  log "depot mis a jour."
else
  runuser -u "$APP_USER" -- git clone --quiet "$REPO_URL" "$BASE/repo"
  runuser -u "$APP_USER" -- git -C "$BASE/repo" -c advice.detachedHead=false checkout --quiet --force --detach origin/main
  log "depot clone dans $BASE/repo."
fi

# --- 5. fichier d'environnement (secrets aleatoires, jamais dans le depot) -------------------------
ENV_FILE="$BASE/.env"
if [[ ! -s "$ENV_FILE" ]]; then
  [[ -n "$DOMAIN" ]] || fail "BASECAMP_DOMAIN manquant (ex. BASECAMP_DOMAIN=basecamp.tempulse.fr)."
  tmp="$(mktemp)"
  while IFS= read -r line; do
    case "$line" in
      BASECAMP_DOMAIN=*) printf 'BASECAMP_DOMAIN=%s\n' "$DOMAIN" ;;
      *=change-me) printf '%s=%s\n' "${line%%=*}" "$(openssl rand -hex 24)" ;;
      *) printf '%s\n' "$line" ;;
    esac
  done < "$BASE/repo/deploy/prod.env.example" > "$tmp"
  # Cle de pseudonymisation des journaux metier : requise des que ce chantier est deploye.
  grep -q '^LOG_PSEUDONYM_KEY=' "$tmp" || printf 'LOG_PSEUDONYM_KEY=%s\n' "$(openssl rand -hex 32)" >> "$tmp"
  install -o "$APP_USER" -g "$APP_USER" -m 600 "$tmp" "$ENV_FILE"
  rm -f "$tmp"
  log "$ENV_FILE cree avec des secrets aleatoires (visibles uniquement sur la VM)."
else
  log "$ENV_FILE existe deja : conserve tel quel."
fi
if grep -q 'change-me' "$ENV_FILE"; then
  log "ATTENTION : des valeurs 'change-me' subsistent dans $ENV_FILE, a remplacer avant d'activer les deploiements."
fi
if ! grep -q '^LOG_PSEUDONYM_KEY=' "$ENV_FILE"; then
  log "NOTE : LOG_PSEUDONYM_KEY absente de $ENV_FILE. Elle sera obligatoire des que les journaux metier seront deployes ; ajouter une valeur aleatoire longue (openssl rand -hex 32), voir le runbook."
fi

# --- 6. cles de signature d'auth ---------------------------------------------------------------
AUTH_KEYS_DIR="$BASE/secrets/auth" runuser -u "$APP_USER" -- sh "$BASE/repo/scripts/init-auth-keys.sh"

# --- 7. unites systemd ----------------------------------------------------------------------------
for unit in basecamp-deploy.service basecamp-deploy.timer; do
  install -m 644 "$BASE/repo/infra/systemd/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
log "unites systemd installees (minuteur NON active)."

echo
echo "Prochaines etapes (voir docs/deployment/runbook.md, section Bascule) :"
echo "  1. Verifier $ENV_FILE (domaine, valeurs facultatives du front)."
echo "  2. Arreter l'ancienne pile '$OLD_PROJECT' (docker compose down dans son dossier)."
echo "  3. sudo bash $BASE/repo/infra/install-vm.sh --enable-timer"
