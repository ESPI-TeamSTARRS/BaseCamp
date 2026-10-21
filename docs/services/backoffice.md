# Back-office `apps/backoffice`

## Rôle
Application d'administration réservée à l'équipe, servie sur l'hôte admin (`admin.<domaine>`, en local `admin.localhost`). Ce squelette ne contient qu'une page d'accueil : les écrans métier (connexion, catalogue) arrivent dans les tickets suivants.

## Stack
Next.js 16 (App Router, React 19), TypeScript strict, ESLint 9 en configuration plate, Prettier, Vitest (couverture ≥ 80 %, seuil bloquant). Même chaîne et mêmes scripts npm que le [front](frontend.md) (`quality`, `test:coverage`, `security`, `build`). Image Docker multi-étapes, utilisateur sans privilèges, serveur autonome (`output: 'standalone'`).

## Structure
```
apps/backoffice/
├── Dockerfile · package.json · releaserc.toml   # semver propre : tags `backoffice-vX.Y.Z`
├── next.config.mjs                              # en-têtes de sécurité de l'origine admin
└── src/
    ├── app/        # layout (noindex), page d'accueil, robots.txt
    ├── lib/        # logique testée (journal métier)
    └── proxy.ts    # une ligne de journal par page, X-Correlation-ID
```

## Isolation et exposition
- Le site client n'a aucun lien ni route vers le back-office. Le routeur Traefik `backoffice` ne répond que sur l'hôte `admin.*` (`HostRegexp(^admin\..+$)`, hors `/api`); sur le domaine principal, c'est le front qui répond (404).
- `noindex` partout : balise `robots` de la page, `robots.txt` (`Disallow: /`) et en-tête `X-Robots-Tag`.
- En-têtes : CSP sans cadre (`frame-ancestors 'none'`), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`. `Permissions-Policy: camera=(self)` : la caméra n'est autorisée que pour cette origine.
- Aucune donnée ni secret côté serveur à ce stade : le conteneur n'a aucune variable d'environnement.

## Journaux
Une ligne JSON par page servie sur la sortie standard, au [contrat commun](../development/logging.md) : `service: basecamp-backoffice`, `event: backoffice.page_served`, `outcome`, `correlation_id` (celui du `X-Correlation-ID` reçu s'il est bien formé, sinon un UUID; renvoyé dans la réponse). Aucune donnée personnelle ni valeur reçue.

## Pile et CI
Service `backoffice` du `docker-compose.yml` (réseau `app`, healthcheck sur `/`), dont dépend Traefik. Job CI `backoffice` (qualité, tests, audit, build) dans `ci.yml`; le test de bout en bout de la pile construit l'image et vérifie 200 + `noindex` sur l'hôte admin et l'absence sur le domaine principal. L'image est construite, scannée (Trivy bloquant) et publiée par `release.yml` comme les autres composants.

## Reste à faire (hors de ce ticket)
Entrée du back-office dans `deploy/manifest.json` et `deploy/docker-compose.prod.yml` après la première image publiée (le manifeste est par digest), puis exposition publique, limiteur et DNS (sous-domaine admin).
