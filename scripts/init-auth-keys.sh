#!/bin/sh
# Genere la paire de cles de signature (Ed25519) du service auth dans .secrets/auth/.
# Idempotent : ne remplace jamais une cle existante (utiliser --force pour la regenerer).
# Les cles ne sont jamais versionnees (.secrets/ est ignore par Git).
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="${AUTH_KEYS_DIR:-$ROOT/.secrets/auth}"
PRIVATE_KEY="$DIR/jwt-private.pem"
PUBLIC_KEY="$DIR/jwt-public.pem"

if [ "${1:-}" != "--force" ] && [ -s "$PRIVATE_KEY" ] && [ -s "$PUBLIC_KEY" ]; then
  echo "Cles de signature deja presentes dans $DIR (--force pour les regenerer)."
  exit 0
fi

command -v openssl >/dev/null 2>&1 || { echo "openssl est requis." >&2; exit 1; }

mkdir -p "$DIR"
umask 077
# Rotation : l'ancienne cle publique est conservee dans previous/ pour que les jetons deja emis
# restent verifiables jusqu'a leur expiration (APP_JWT_PREVIOUS_PUBLIC_KEYS_DIR, voir docs/services/auth.md).
if [ -s "$PUBLIC_KEY" ]; then
  mkdir -p "$DIR/previous"
  cp "$PUBLIC_KEY" "$DIR/previous/jwt-public-$(date -u +%Y%m%dT%H%M%SZ).pem"
fi
openssl genpkey -algorithm ED25519 -out "$PRIVATE_KEY"
openssl pkey -in "$PRIVATE_KEY" -pubout -out "$PUBLIC_KEY"
# Lisibles par l'utilisateur non privilegie du conteneur (cle de developpement locale uniquement).
chmod 644 "$PRIVATE_KEY" "$PUBLIC_KEY"
[ ! -d "$DIR/previous" ] || chmod 755 "$DIR/previous"
echo "Cles de signature generees dans $DIR"
