# Basecamp

Boutique en ligne de matériel outdoor (tentes de bivouac, couchage, sacs de grande randonnée, cuisine de camp, sécurité) avec un service de paiement interne, sans donnée bancaire réelle.

Monorepo : un front Next.js et trois services FastAPI autonomes (`shop`, `auth`, `payment`), chacun dans son conteneur.

## Architecture en un coup d'œil

```
Internet
   │
Traefik (passerelle : TLS, limitation de débit, filtrage)
   ├── /               → frontend (Next.js)
   ├── /api/shop/*     → shop     ┐
   ├── /api/auth/*     → auth     ├ services FastAPI, réseau interne,
   └── /api/payment/*  → payment  ┘ chacun avec sa base de données
```

| Composant | Dossier | Rôle |
|---|---|---|
| Front | [apps/frontend](apps/frontend) | Vitrine : catalogue, panier, pages légales |
| `shop` | [apps/backend/shop](apps/backend/shop) | Catalogue, commandes, stock |
| `auth` | [apps/backend/auth](apps/backend/auth) | Comptes, jetons, rôles |
| `payment` | [apps/backend/payment](apps/backend/payment) | Intentions de paiement, remboursements, grand livre, webhooks signés |

Chaque service backend est un projet `uv` autonome (son `pyproject.toml`, son `uv.lock`, son `Dockerfile`) organisé en tranches Clean Architecture. La passerelle Traefik est la cible décrite dans [la documentation d'architecture](docs/architecture/services-and-gateway.md).

## Démarrage rapide

Prérequis : Python 3.13 et [uv](https://docs.astral.sh/uv/), Node.js 20, Docker.

```bash
uv sync                                       # outils racine (poe, pre-commit)
uv sync --directory apps/backend/shop         # dépendances d'un service (idem auth, payment)
npm ci --prefix apps/frontend                 # front
uv run pre-commit install --install-hooks     # hooks Git
```

Commandes depuis la racine :

| Commande | Effet |
|---|---|
| `uv run poe quality` | lint, format et types de tous les services |
| `uv run poe test` | tests et couverture (seuil 80 %) |
| `uv run poe security` | audit des dépendances |
| `uv run poe ci` | tout ce que la CI exécute |

Lancer un service : `cd apps/backend/<service> && uv run uvicorn app.main:app --reload`, puis `GET /health`. Image Docker : `docker build -t basecamp-<service> apps/backend/<service>`.

La configuration passe par des variables d'environnement (modèle : [apps/frontend/.env.example](apps/frontend/.env.example)). Aucun secret n'est versionné.

## Documentation

Point d'entrée : [docs/README.md](docs/README.md).

| Section | Contenu |
|---|---|
| [Architecture](docs/architecture/README.md) | [Vue d'ensemble](docs/architecture/overview.md), [principes](docs/architecture/principles.md), [monorepo](docs/architecture/monorepo.md), [Clean Architecture](docs/architecture/clean-architecture.md), [services et passerelle](docs/architecture/services-and-gateway.md) |
| [Développement](docs/development/README.md) | [Règles](docs/development/rules.md), [mise en route](docs/development/getting-started.md), [TDD et tests](docs/development/testing.md), [Git et hooks](docs/development/git-and-hooks.md), [CI](docs/development/ci.md), [sécurité](docs/development/security.md), [gestion de projet agile](docs/development/agile.md), [tickets](docs/development/tickets.md) |
| [Services](docs/services/README.md) | [shop](docs/services/shop.md), [auth](docs/services/auth.md), [payment](docs/services/payment.md), [frontend](docs/services/frontend.md) |

Skills de l'équipe pour Claude Code (dossier [.claude/skills](.claude/skills)) : [architecte](.claude/skills/architecte/SKILL.md), [clean-archi-fastapi](.claude/skills/clean-archi-fastapi/SKILL.md), [tdd-couverture](.claude/skills/tdd-couverture/SKILL.md), [git-trunk-based](.claude/skills/git-trunk-based/SKILL.md), [redaction-tickets](.claude/skills/redaction-tickets/SKILL.md). Règles pour les sessions Claude : [CLAUDE.md](CLAUDE.md).

## Contribuer

Développement en trunk-based : `main` toujours déployable, branches courtes `feat/WORK-<n>-<slug>`, PR petites fusionnées en squash, CI verte obligatoire. Détails : [Git et hooks](docs/development/git-and-hooks.md) et [règles de développement](docs/development/rules.md).
