#!/usr/bin/env bash
# Deploiement par tirage, lance par le minuteur systemd (infra/systemd/basecamp-deploy.timer).
#
# Met a jour la copie locale du depot public (lecture seule, HTTPS, aucun identifiant), puis deploie
# deploy/manifest.json de main avec scripts/deploy.sh. La fusion de la PR qui modifie ce manifeste
# EST l'approbation : rien n'est deploye qui ne soit passe par la CI et la protection de `main`.
#
# Variables : BASECAMP_REPO_DIR, BASECAMP_BRANCH, BASECAMP_STATE_DIR, BASECAMP_ENV_FILE,
# BASECAMP_BLOCK_IF_RUNNING (projet compose de l'ancienne pile ; vide pour desactiver).
#
# Pause : `touch /opt/basecamp/state/PAUSE` suspend les deploiements, `rm` les reprend.

set -Eeuo pipefail

# Tout le corps est dans une fonction appelee sur la derniere ligne : bash lit un script au fil de
# l'execution, et le `git checkout` ci-dessous remplace ce fichier par une version plus recente.
main() {
  local repo_dir="${BASECAMP_REPO_DIR:-/opt/basecamp/repo}"
  local branch="${BASECAMP_BRANCH:-main}"
  local state_dir="${BASECAMP_STATE_DIR:-/opt/basecamp/state}"
  local env_file="${BASECAMP_ENV_FILE:-/opt/basecamp/.env}"
  local block_project="${BASECAMP_BLOCK_IF_RUNNING-basecamp-outdoor}"

  log() { printf 'pull-deploy: %s\n' "$*"; }

  if [[ -f "$state_dir/PAUSE" ]]; then
    log "deploiements en pause ($state_dir/PAUSE), rien a faire."
    return 0
  fi

  if [[ ! -s "$env_file" ]]; then
    log "ERREUR : $env_file absent ou vide. Lancer infra/install-vm.sh (voir docs/deployment/runbook.md)."
    return 1
  fi

  # Ancienne pile encore active et nouvelle pile jamais deployee : les deux routeraient le meme
  # domaine. On ne deploie pas tant que l'ancienne pile n'est pas arretee (bascule manuelle).
  if [[ -n "$block_project" && ! -f "$state_dir/current.json" ]]; then
    if [[ -n "$(docker ps -q --filter "label=com.docker.compose.project=$block_project")" ]]; then
      log "l'ancienne pile '$block_project' tourne encore : deploiement suspendu. Voir la section Bascule du runbook."
      return 0
    fi
  fi

  git -C "$repo_dir" fetch --quiet origin "$branch"
  git -C "$repo_dir" -c advice.detachedHead=false checkout --quiet --force --detach "origin/$branch"
  log "depot a $(git -C "$repo_dir" rev-parse --short HEAD) ($branch)"

  export BASECAMP_STATE_DIR="$state_dir" BASECAMP_ENV_FILE="$env_file"
  # `exec` : le deploiement s'execute avec la version du script qui vient d'etre recuperee.
  exec "$repo_dir/scripts/deploy.sh" "$repo_dir/deploy/manifest.json"
}

main "$@"
exit $?
