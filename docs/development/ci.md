# Intégration continue

Workflow : `.github/workflows/ci.yml`, déclenché à chaque push et sur les pull requests vers `main`.

| Job | Contenu |
|---|---|
| `backend` (matrice par service) | `poe quality`, `poe test` (couverture ≥ 80 %), `poe security`, build de l'image Docker |
| `frontend` | lint, format, types, tests et couverture, audit des dépendances (bloquant dès une vulnérabilité élevée ou critique), build |
| `secrets-scan` | gitleaks sur l'historique complet |
| `outils-racine` | tests des scripts des hooks |
| `stack-e2e` | construit les images `shop`, `auth` et `front` (cache GitHub Actions), génère un `.env` factice depuis `.env.example`, démarre la pile minimale (`docker compose up --wait traefik` : Traefik, front, `shop`, `auth` et leurs bases), génère les clés de signature d'`auth` (`scripts/init-auth-keys.sh`), joue `poe test:e2e` de `shop` puis d'`auth` contre Traefik, publie les logs des conteneurs en artefact (`stack-e2e-logs`) en cas d'échec, puis supprime la pile |
| `ci-ok` | job final (attend aussi `stack-e2e`), seul check à rendre obligatoire dans la protection de branche |

Chaque job appelle les tâches `poe` ou `npm` du service, jamais un outil en direct. Les permissions du jeton sont réduites au strict nécessaire (`contents: read`).

## Ajouter un service

Ajouter son nom dans la liste `service` de la matrice du job `backend`.
