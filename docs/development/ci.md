# Intégration continue

Workflow : `.github/workflows/ci.yml`, déclenché à chaque push (hors `main`) et sur les pull requests vers `main`. Sur `main`, la CI est jouée par `release.yml`, qui appelle `ci.yml` avant de calculer les versions.

| Job | Contenu |
|---|---|
| `backend` (matrice par service) | `poe quality`, `poe test` (couverture ≥ 80 %), `poe security`, build de l'image Docker; un service Postgres jetable (valeurs factices) fournit `PAYMENT_TEST_DATABASE_URL` aux tests Postgres de `payment` |
| `frontend` | lint, format, types, tests et couverture, audit des dépendances (bloquant dès une vulnérabilité élevée ou critique), build |
| `backoffice` | mêmes contrôles que `frontend` sur `apps/backoffice` (lint, format, types, tests et couverture ≥ 80 %, audit des dépendances, build) |
| `secrets-scan` | gitleaks sur les seuls commits de la PR (`base..head`) ou, sur main via `release.yml`, du push (`before..after`); l'historique de `main` est scanné par `secrets-history.yml` (manuel et hebdomadaire) |
| `outils-racine` | tests des scripts des hooks |
| `deploy-rollback` | `bash scripts/deploy/test-deploy.sh` (`poe deploy-test`) : joue `scripts/deploy.sh` contre un registre local avec une panne volontaire, et vérifie le retour automatique ([deploy-script.md](../deployment/deploy-script.md)) |
| `stack-e2e` (workflow `e2e.yml`, **hors PR** : toutes les heures sur `main`, à la demande et dans `release.yml`) | construit les images `shop`, `auth`, `payment` et `front` (cache GitHub Actions), génère un `.env` factice depuis `.env.example`, démarre la pile minimale avec la surcharge `docker-compose.e2e.yml` (`docker compose up --wait --scale payment=2 traefik payment seaweedfs mailpit` : Traefik, front, `shop`, `auth`, `payment`, Mailpit publié sur 127.0.0.1:8025 et leurs bases), génère les clés de signature d'`auth` (`scripts/init-auth-keys.sh`), rejoue l'amorçage des clients de service (`auth-bootstrap`, idempotent), joue `poe test:e2e` de `shop` puis d'`auth` (dont les jetons de service, appelés depuis le conteneur `shop`, et l'inscription avec emails lus dans Mailpit et contrôle des journaux) contre Traefik, puis de `payment` (charge, attaque, 413, 429, deux instances, arrêt de payment), publie les logs des conteneurs en artefact (`stack-e2e-logs`) en cas d'échec, puis supprime la pile. Dans `release.yml` il tourne en parallèle de la CI, avant la publication; un échec rend le run rouge (voir ci-dessous pour le rendre bloquant). |
| `pr-title` (workflow séparé) | le titre de la PR respecte le format Conventional Commits (même script que le hook `commit-msg`); à rendre obligatoire avec `ci-ok` |
| `ci-ok` | job final, seul check à rendre obligatoire dans la protection de branche |

Le job `stack-e2e` (`e2e.yml`) tourne avec le nom de projet par défaut (`basecamp`) : les tags `basecamp-<service>` posés par les étapes de build correspondent aux images `${COMPOSE_PROJECT_NAME:-basecamp}-<service>` de `docker-compose.yml`.

Chaque job appelle les tâches `poe` ou `npm` du service, jamais un outil en direct. Les permissions du jeton sont réduites au strict nécessaire (`contents: read`).

## Ajouter un service

Ajouter son nom dans la liste `service` de la matrice du job `backend`.

## Release

Le workflow `.github/workflows/release.yml` se déclenche à chaque push sur `main`, rejoue la CI puis, si elle est verte, pose les tags de version par service, publie les images sur GHCR ([images.md](images.md)) et ouvre la PR qui met à jour `deploy/manifest.json` ([runbook](../deployment/runbook.md)). Détails dans [versioning.md](versioning.md).

## E2E et release : bloquant ou non

`release.yml` joue `e2e.yml` (job `e2e`, en parallèle de `ci`) avant de calculer les versions et de publier les images. **Par défaut il ne bloque pas** : un échec laisse le run rouge et visible, mais la publication continue (la variante actuelle, tant que le flux de remboursement est en cours de correction).

Pour le rendre **bloquant** (aucune image publiée ni manifeste proposé si l'e2e est rouge), une seule action : créer la variable de dépôt `E2E_BLOQUANT` à `true` (Settings → Secrets and variables → Actions → Variables, ou `gh variable set E2E_BLOQUANT --body true`). Pour revenir au mode non bloquant : la supprimer ou la mettre à `false`. Aucun changement de fichier. Une release dure alors environ 8 minutes (l'e2e, ≈ 7,5 min, est le chemin critique) au lieu de ≈ 4 min 20.
