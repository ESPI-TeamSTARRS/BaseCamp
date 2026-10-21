#!/usr/bin/env bash
# Complete un fichier d'environnement de production : ajoute, avec une valeur ALEATOIRE, chaque
# variable du modele marquee `=change-me` qui est absente ou vide. Ne modifie jamais une valeur
# deja renseignee et n'affiche jamais de valeur.
#
#   infra/complete-env.sh <modele.env.example> <fichier .env>
#
# Utilise par infra/install-vm.sh (relancer l'installation repare un .env incomplet).
# A ne pas utiliser si les bases existent deja avec d'autres mots de passe : voir le runbook.

set -Eeuo pipefail

[[ $# == 2 ]] || { echo "usage : $0 <modele> <env>" >&2; exit 3; }
example="$1"
env_file="$2"
[[ -f "$example" ]] || { echo "modele introuvable : $example" >&2; exit 1; }
touch "$env_file"

# Un fichier sans retour a la ligne final fusionnerait la derniere ligne avec la suivante.
if [[ -s "$env_file" && -n "$(tail -c1 "$env_file")" ]]; then
  echo >> "$env_file"
fi

added=0
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ "$line" =~ ^([A-Z][A-Z0-9_]*)=change-me$ ]] || continue
  name="${BASH_REMATCH[1]}"
  # Valeur deja renseignee (au moins un caractere) : on n'y touche pas.
  if grep -q "^${name}=." "$env_file"; then
    continue
  fi
  # Ligne vide ou doublon eventuel : retire avant d'ajouter.
  grep -v "^${name}=" "$env_file" > "$env_file.tmp" || true
  cat "$env_file.tmp" > "$env_file"
  rm -f "$env_file.tmp"
  if [[ "$name" == "LOG_PSEUDONYM_KEY" ]]; then
    value="$(openssl rand -hex 32)"
  else
    value="$(openssl rand -hex 24)"
  fi
  printf '%s=%s\n' "$name" "$value" >> "$env_file"
  echo "variable ajoutee : $name"
  added=$((added + 1))
done < "$example"

echo "complete-env : $added variable(s) ajoutee(s)."
