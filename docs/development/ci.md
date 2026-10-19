# Intégration continue

Workflow : `.github/workflows/ci.yml`, déclenché à chaque push et sur les pull requests vers `main`.

| Job | Contenu |
|---|---|
| `backend` (matrice par service) | `poe quality`, `poe test` (couverture ≥ 80 %), `poe security`, build de l'image Docker |
| `frontend` | lint, format, types, tests et couverture, audit des dépendances, build |
| `secrets-scan` | gitleaks sur l'historique complet |
| `outils-racine` | tests des scripts des hooks |
| `ci-ok` | job final, seul check à rendre obligatoire dans la protection de branche |

Chaque job appelle les tâches `poe` ou `npm` du service, jamais un outil en direct. Les permissions du jeton sont réduites au strict nécessaire (`contents: read`).

## Ajouter un service

Ajouter son nom dans la liste `service` de la matrice du job `backend`.
