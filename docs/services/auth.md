# Service `auth`

**Dossier** : `apps/backend/auth`

## Rôle
Comptes clients, jetons d'accès courts, rôle opérateur.

## API
| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | liveness |

Les routes d'authentification s'ajoutent par tranche (`account`, `session`) et se documentent ici.

## Règles
- Mots de passe hachés avec un algorithme dédié, jamais journalisés.
- Cookies de session `HttpOnly`, `Secure`, `SameSite=Strict`.
- Limitation de débit contre le brute-force.
- Séparation des rôles : un client n'accède jamais aux routes opérateur.

## Configuration
`APP_SERVICE_NAME`, `APP_ENVIRONMENT`.
