# Structure du monorepo

```
.
├── apps/
│   ├── backend/
│   │   ├── shop/       projet uv autonome (pyproject.toml, uv.lock, Dockerfile)
│   │   ├── auth/       idem
│   │   └── payment/    idem
│   └── frontend/       Next.js (package.json, Dockerfile)
├── docs/               cette documentation
├── scripts/hooks/      outils des hooks Git
├── .github/workflows/  CI
├── .pre-commit-config.yaml
└── pyproject.toml      orchestrateur racine (tâches poe)
```

## Contenu type d'un service backend

```
apps/backend/<service>/
├── app/
│   ├── core/              configuration (pydantic-settings)
│   ├── <fonctionnalité>/  domain/ application/ infrastructure/ presentation/ __tests__/
│   └── main.py            create_app()
├── tests/e2e/scenarios/   tests de bout en bout
├── conftest.py            marker pytest automatique selon le suffixe du fichier
├── pyproject.toml         dépendances, pytest, ruff, mypy, tâches poe
├── uv.lock
└── Dockerfile
```

## Ajouter un service

1. Copier la structure d'un service existant et renommer le projet.
2. Ajouter ses tâches dans le `pyproject.toml` racine, ses hooks dans `.pre-commit-config.yaml` et son nom dans la matrice de `.github/workflows/ci.yml`.
3. Documenter le service dans [services/](../services/README.md).
