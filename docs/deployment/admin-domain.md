# Sous-domaine admin (`admin.<domaine>`)

Le back-office est public sur `admin.<BASECAMP_DOMAIN>` (HTTPS obligatoire : la caméra du navigateur l'exige), sans VPN. La protection repose sur la connexion en trois temps, les blocages de compte et un limiteur de débit renforcé.

## Ce qui est en place dans le dépôt
- Le Traefik du serveur route déjà `Host(<domaine>)` **et** `Host(admin.<domaine>)` vers la passerelle de la pile, avec certificat (labels de `deploy/docker-compose.prod.yml`, résolveur `TRAEFIK_CERTRESOLVER`).
- Passerelle de la pile (`infra/traefik/dynamic.yml`, copie de production `deploy/traefik/dynamic.prod.yml`, routeurs identiques vérifiés par `scripts/deploy/test_compose_prod.py`) :

| Routeur | Hôte | Chemin | Remarque |
|---|---|---|---|
| `backoffice` | `admin.*` seulement | tout sauf `/api` | page, `noindex` |
| `auth-backoffice` | `admin.*` seulement | `/api/auth/backoffice` | limiteur `backoffice-login-rate-limit` : 10 requêtes/min par adresse, rafale 5 (contre 60/30 pour `/login`) |
| `auth-backoffice-invitation` | `admin.*` seulement | `/api/auth/backoffice/invitation/complete` | même limiteur par adresse que la connexion; corps jusqu'à 15 Mio (10 images) ; priorité supérieure à `auth-backoffice` |
| `shop-admin` | `admin.*` seulement | `/api/shop/admin` | limiteur `admin-rate-limit` |

- Sur le domaine principal, `/api/auth/backoffice` et `/api/shop/admin` ne sont pas routés vers un service (le front répond 404); le back-office n'y est pas servi.
- En-têtes (voir [backoffice](../services/backoffice.md)) : CSP sans cadre, `nosniff`, pas de cadre, `noindex`; la caméra n'est autorisée que pour cette origine.
- Clé du limiteur en production : adresse du vrai client derrière Cloudflare (X-Forwarded-For, plages Docker et Cloudflare exclues), comme les autres limiteurs.

## Procédure (une fois, avec la personne qui gère le DNS)
1. Ajouter l'enregistrement `admin.<domaine>` (même cible que `<domaine>`, proxy Cloudflare actif).
2. Vérifier qu'`admin.<domaine>` est dans les règles du routeur `basecamp-gw` (déjà le cas) : le certificat est émis au premier accès.
3. Contrôles de fumée, depuis l'extérieur :
   - `curl -sI https://admin.<domaine>/` : 200, `X-Robots-Tag: noindex…`;
   - `curl -s -o /dev/null -w '%{http_code}' https://<domaine>/api/shop/admin/products` : 404 (idem `/api/auth/backoffice/…`);
   - `curl -s https://<domaine>/ | grep -c 'Back-office'` : 0.
4. Aucun lien du site client vers le back-office : vérifié par le test de bout en bout (hôte principal sans le texte du back-office).

## Repli si le DNS n'est pas prêt
Servir le back-office sous `/backoffice` du domaine principal demande un `basePath` Next.js (option de build, donc une image dédiée) et un routeur `PathPrefix(/backoffice)` : à n'engager que sur décision, car cela expose l'administration sur l'origine du site client (CSP et cookies partagés).

## Point d'attention : adresse du client côté auth
Le verrouillage de compte d'`auth` compte les échecs par adresse; le service lit l'adresse de la connexion (`request.client.host`). Derrière Traefik, tant qu'`auth` ne fait pas confiance au proxy pour lire `X-Forwarded-For` avec le même réglage que le limiteur (plages Docker et Cloudflare exclues), tous les clients partagent l'adresse du proxy. Ce réglage relève du service `auth` (ticket dédié) et doit être fait avant d'exposer la connexion du back-office.
