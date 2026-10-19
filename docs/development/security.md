# Sécurité

## Règles de développement

- Validation de toute entrée (Pydantic, `extra="forbid"`; Zod `.strict()` côté front).
- Secrets uniquement par variables d'environnement, validées au démarrage.
- Messages d'erreur assainis : aucune trace, aucun détail interne.
- Webhooks : signature cryptographique vérifiée, horodatage borné, identifiant d'événement unique.
- Montants recalculés côté serveur.
- Limitation de débit sur les routes publiques; l'adresse IP du client n'est fiable que derrière un proxy de confiance qui écrase `X-Forwarded-For`.
- Cookies de session `HttpOnly`, `Secure`, `SameSite=Strict`.

## Conteneurs

Utilisateur non-root, image minimale en plusieurs étapes, healthcheck, `no-new-privileges`, aucun port publié hors du reverse proxy.

## Contrôles automatiques

| Contrôle | Où |
|---|---|
| Règles de sécurité ruff (`S`) | lint de chaque service |
| `pip-audit` | `poe security` de chaque service |
| `npm audit` | `npm run security` du front |
| gitleaks | hook `pre-commit` et job `secrets-scan` |

## En-têtes HTTP

Le front applique CSP, HSTS, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` et `Permissions-Policy` (voir `apps/frontend/next.config.mjs`).
