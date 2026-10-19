# CLAUDE.md — Basecamp

Règles pour les sessions Claude Code sur ce dépôt. La documentation de référence est dans [docs/](docs/README.md) : en cas de divergence, les docs font foi. Réponses, interface et commentaires de communication en **français**.

## Le projet

Boutique de matériel outdoor (bivouac, grande randonnée) avec un service de paiement interne, sans donnée bancaire réelle. Monorepo :

- `apps/frontend` : Next.js 14, TypeScript, Tailwind, Framer Motion (le front d'origine, rethémé Basecamp Outdoor).
- `apps/backend/{shop,auth,payment}` : services FastAPI (Python 3.13, `uv`), chacun un projet autonome avec son `pyproject.toml`, son `uv.lock` et son `Dockerfile`.
- `docs/` : documentation applicative. `.claude/skills/` : skills de l'équipe.

Identité visuelle : vert forêt `#1E3A2F`, orange bivouac `#E05638`, neutres pierre et sable `#F5F2EB`; badges techniques sur les produits (poids, imperméabilité, température de confort, matériau). Mobile first.

## Périmètre

Applicatif seulement : front, `shop`, `auth`, `payment`, puis remédiation. **ML et RAG sont hors périmètre** (équipe IA). Postgres, passerelle et observabilité relèvent de l'infra. Ne pas élargir le périmètre sans demander.

## Architecture (règles non négociables)

1. **Microservices** : un conteneur et une base par service. Passerelle Traefik seul point publié ([services-and-gateway.md](docs/architecture/services-and-gateway.md)).
2. **Fonctionnalité ou service** : par défaut une tranche dans un service existant; nouveau service seulement si au moins 2 critères sur 4 (données propres, cycle de vie indépendant, charge ou sécurité différente, propriétaire distinct).
3. **Un projet `uv` par service**, aucun import entre services, **aucune bibliothèque partagée** (duplication acceptée). Le `pyproject.toml` racine délègue uniquement.
4. **Clean Architecture en tranches verticales** : `domain / application / infrastructure / presentation`, un fichier = une classe, règle de dépendance vérifiée par `app/__tests__/unit/test_architecture.unit.py`.
5. **Paiement derrière l'interface `PaymentProvider`**; idempotence en base; montants recalculés côté serveur; webhooks signés.
6. Aucun état en mémoire dans un service; entrées validées (`extra="forbid"`); erreurs assainies.

Pour toute question d'architecture, utiliser le skill `architecte` avant de décider.

## Qualité

- **TDD strict** (Red, Green, Blue), tests colocalisés dans `__tests__/` (`.unit`, `.integ`, `.e2e`), **couverture ≥ 80 %** back et front. Skill `tdd-couverture`.
- Avant de proposer un changement : `uv run poe quality` et `uv run poe test` (ou `uv run poe ci`). Ne jamais baisser un seuil ni exclure du code pour passer.
- Hooks Git : `commit-msg`, `pre-commit`, `pre-push`. **Ne jamais contourner** (`--no-verify` interdit).

## Git (trunk-based)

`main` seule branche longue et toujours déployable; branches courtes `<type>/WORK-<n>-<slug>`; PR petites en squash; commits `<type>(<scope>): description en français (WORK-<n>)`. Détails : skill `git-trunk-based` et [git-and-hooks.md](docs/development/git-and-hooks.md).

## Interdits et garde-fous

- **Ne jamais pousser, forcer un push, créer ou fusionner une PR sans accord explicite de Sam.** Travailler sur une branche, jamais sur `main`.
- **Aucun secret dans le dépôt** : pas de `.env*`, clé, mot de passe ou jeton, ni dans le code, ni dans les docs, ni dans les messages de commit. Ne jamais afficher le contenu d'un `.env`. Un secret commité se renouvelle.
- **Aucun suivi d'avancement dans le dépôt** (journal, statuts, notes de progression) : il vit dans Linear (équipe WORK) et dans le vault personnel de Sam.
- Ne rien créer ni modifier dans Linear sans avoir montré le texte à Sam (skill `redaction-tickets`).
- Pas d'action destructrice ou sortante (suppression en masse, réécriture d'historique partagé, message externe) sans demande explicite.

## Skills du dépôt (`.claude/skills/`)

| Skill | Quand l'utiliser |
|---|---|
| [architecte](.claude/skills/architecte/SKILL.md) | question d'architecture, nouveau service ou tranche, communication entre services |
| [clean-archi-fastapi](.claude/skills/clean-archi-fastapi/SKILL.md) | placer du code dans un service, revue de couches |
| [tdd-couverture](.claude/skills/tdd-couverture/SKILL.md) | avant toute implémentation, tests et couverture |
| [git-trunk-based](.claude/skills/git-trunk-based/SKILL.md) | branches, commits, PR, correctifs, retours arrière |
| [redaction-tickets](.claude/skills/redaction-tickets/SKILL.md) | rédiger ou découper un ticket Linear |

Skills spécialisés complémentaires, à consulter selon le sujet : sécurité ([sec-code-owasp](.claude/skills/sec-code-owasp/SKILL.md), [sec-web-audit](.claude/skills/sec-web-audit/SKILL.md), [owasp-web-security-auditor](.claude/skills/owasp-web-security-auditor/SKILL.md), [sec-infra-hardening](.claude/skills/sec-infra-hardening/SKILL.md)), paiement ([stripe-checkout-billing](.claude/skills/stripe-checkout-billing/SKILL.md)), SEO et conversion ([seo-technical-geo](.claude/skills/seo-technical-geo/SKILL.md), [technical-seo-auditor](.claude/skills/technical-seo-auditor/SKILL.md), [cro-friction-audit](.claude/skills/cro-friction-audit/SKILL.md)), UX et design ([ux-heuristics-evaluator](.claude/skills/ux-heuristics-evaluator/SKILL.md), [design-system-tokens](.claude/skills/design-system-tokens/SKILL.md), [micro-interactions-motion](.claude/skills/micro-interactions-motion/SKILL.md)).

## Documentation

[Index](docs/README.md) · [Architecture](docs/architecture/README.md) · [Développement](docs/development/README.md) · [Services](docs/services/README.md) · [Règles de développement](docs/development/rules.md) · [Agile et tickets](docs/development/agile.md)

Quand une API, un invariant ou une règle change, mettre à jour la page de [docs/](docs/README.md) concernée dans la même PR.
