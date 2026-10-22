# Hôte du back-office (`BACKOFFICE_HOST`)

Le back-office est public sur l'hôte `BACKOFFICE_HOST` (HTTPS obligatoire : la caméra du navigateur l'exige), sans VPN. La protection repose sur la connexion en trois temps, les blocages de compte et un limiteur de débit renforcé.

## Nom de l'hôte et variable `BACKOFFICE_HOST` (WORK-69, WORK-70)
Le back-office est servi sur **un hôte complet**, donné par `BACKOFFICE_HOST` : `mercure-basecamp.tempulse.fr` en production (défaut de `deploy/docker-compose.prod.yml`, exemple dans `deploy/prod.env.example`), `mercure.localhost` en développement (défaut de `docker-compose.yml`). L'hôte est à **un seul niveau sous le domaine** `tempulse.fr`, donc couvert par le certificat gratuit de Cloudflare (un sous-domaine à deux niveaux sous `tempulse.fr`, comme le premier choix de WORK-69, ne l'est pas). Une seule variable pilote tout : les étiquettes Traefik de production (`Host(...)` des routeurs `basecamp-gw` et `basecamp-gw-http`), `APP_ADMIN_BASE_URL` (origine du lien d'invitation généré par `create_operator_invite`, `https://<BACKOFFICE_HOST>`) **et** les cinq règles `Host(...)` des fichiers de la passerelle (`infra/traefik/dynamic.yml`, `deploy/traefik/dynamic.prod.yml`), que Traefik résout par le modèle Go de son fournisseur de fichiers (`Host(`{{ env `BACKOFFICE_HOST` }}`)`; la variable est passée au conteneur Traefik dans les deux compose). C'est un `Host` **exact**, pas un motif : aucun autre nom ne passe. `scripts/deploy/test_compose_prod.py` vérifie que les deux fichiers, les deux compose et `deploy/prod.env.example` disent la même chose, qu'il y a bien cinq règles, et qu'aucun ancien nom (sous-domaine d'administration, sous-domaine à deux niveaux, ancienne variable de préfixe) n'est écrit dans le dépôt.

**Pas de repli** : les anciens noms (le sous-domaine d'administration, puis le premier choix de WORK-69 à deux niveaux) ne sont plus routés du tout, ni redirigés. Les routes `/admin/...` des API (`/api/shop/admin`, `/admin/users` d'`auth`) ne changent pas.

Un nom moins évident réduit le bruit des scanners, mais il devient public dans les journaux de transparence des certificats (crt.sh) à l'émission du certificat : la protection reste la connexion en trois temps, le limiteur de débit et le blocage de 5 minutes.

## Ce qui est en place dans le dépôt
- Le Traefik du serveur route déjà `Host(<domaine>)` **et** `Host(BACKOFFICE_HOST)` vers la passerelle de la pile, avec certificat (labels de `deploy/docker-compose.prod.yml`, résolveur `TRAEFIK_CERTRESOLVER`).
- Passerelle de la pile (`infra/traefik/dynamic.yml`, copie de production `deploy/traefik/dynamic.prod.yml`, routeurs identiques vérifiés par `scripts/deploy/test_compose_prod.py`) :

| Routeur | Hôte | Chemin | Remarque |
|---|---|---|---|
| `backoffice` | `BACKOFFICE_HOST` seulement | tout sauf `/api` | page, `noindex` |
| `auth-backoffice` | `BACKOFFICE_HOST` seulement | `/api/auth/backoffice` | limiteur `backoffice-login-rate-limit` : 10 requêtes/min par adresse, rafale 5 (contre 60/30 pour `/login`) |
| `auth-backoffice-invitation` | `BACKOFFICE_HOST` seulement | `/api/auth/backoffice/invitation/complete` | même limiteur par adresse que la connexion; corps jusqu'à 15 Mio (10 images) ; priorité supérieure à `auth-backoffice` |
| `shop-admin` | `BACKOFFICE_HOST` seulement | `/api/shop/admin` | limiteur `admin-rate-limit` |

- Sur le domaine principal, `/api/auth/backoffice` et `/api/shop/admin` ne sont pas routés vers un service (le front répond 404); le back-office n'y est pas servi.
- En-têtes (voir [backoffice](../services/backoffice.md)) : CSP sans cadre, `nosniff`, pas de cadre, `noindex`; la caméra n'est autorisée que pour cette origine.
- Clé du limiteur en production : adresse du vrai client derrière Cloudflare (X-Forwarded-For, plages Docker et Cloudflare exclues), comme les autres limiteurs.

## Procédure (une fois, avec la personne qui gère le DNS)
1. Créer l'enregistrement `BACKOFFICE_HOST` (même cible que `<domaine>`, proxy Cloudflare actif) à la place de l'ancien enregistrement d'administration, qu'on peut retirer : il n'est plus routé.
2. Vérifier que `BACKOFFICE_HOST` est dans les règles du routeur `basecamp-gw` (déjà le cas) : le certificat est émis au premier accès.
3. Contrôles de fumée, depuis l'extérieur :
   - `curl -sI https://<BACKOFFICE_HOST>/` : 200, `X-Robots-Tag: noindex…`;
   - `curl -s -o /dev/null -w '%{http_code}' https://<domaine>/api/shop/admin/products` : 404 (idem `/api/auth/backoffice/…`);
   - `curl -s https://<domaine>/ | grep -c 'Back-office'` : 0.
4. Aucun lien du site client vers le back-office : vérifié par le test de bout en bout (hôte principal sans le texte du back-office).

## Repli si le DNS n'est pas prêt
Servir le back-office sous `/backoffice` du domaine principal demande un `basePath` Next.js (option de build, donc une image dédiée) et un routeur `PathPrefix(/backoffice)` : à n'engager que sur décision, car cela expose l'administration sur l'origine du site client (CSP et cookies partagés).

## Point d'attention : adresse du client côté auth
Le verrouillage de compte d'`auth` compte les échecs par adresse; le service lit l'adresse de la connexion (`request.client.host`). Derrière Traefik, tant qu'`auth` ne fait pas confiance au proxy pour lire `X-Forwarded-For` avec le même réglage que le limiteur (plages Docker et Cloudflare exclues), tous les clients partagent l'adresse du proxy. Ce réglage relève du service `auth` (ticket dédié) et doit être fait avant d'exposer la connexion du back-office.
