# Back-office `apps/backoffice`

## Rôle
Application d'administration réservée à l'équipe, servie sur l'hôte admin (`admin.<domaine>`, en local `admin.localhost`). La session (garde de route, cookie de session, trois temps de connexion relayés vers `auth`, déconnexion) est en place (WORK-60) ; la gestion du catalogue (WORK-61) est le premier écran métier ; l'écran de connexion avec capture du visage arrive dans un ticket distinct.

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

## Session, connexion en trois temps et déconnexion (WORK-60)
La connexion du back-office se fait en trois temps (identifiant, visage, mot de passe) auprès d'`auth` (`/backoffice/*`, voir [auth](auth.md)). Le navigateur n'appelle jamais `auth` directement : il appelle des routes **serveur** du back-office, sous `/session` (et `/bff` pour les données), qui relaient sur le réseau interne (`AUTH_URL`). Ces chemins évitent le conflit avec les routes `/api/*` de l'hôte admin, qui vont aux services.

- **`POST /session/identify`** `{email}` → `{challenge_id, expires_in}` (défi à usage unique, toujours 200 côté `auth`, y compris pour un compte inconnu).
- **`POST /session/face`** `{challenge_id, images: [1 à 3 images base64]}` → `{face_ok: true}`; visage refusé ou défi invalide : **401** générique « Identifiants invalides. »; image invalide : 422.
- **`POST /session/password`** `{challenge_id, password}` → `{ok: true}` et le cookie de session; refus : même 401 générique. Le jeton d'accès reçu d'`auth` **n'est jamais renvoyé au navigateur** : il devient le cookie `bo_access`.
- **Cookie** `bo_access` : `HttpOnly`, `SameSite=Strict`, chemin `/`, `Secure` derrière HTTPS, durée = celle du jeton (15 min). Aucun jeton dans un stockage du navigateur, une URL ou une page. Le jeton du back-office n'a pas de jeton de rafraîchissement : à l'expiration, on se reconnecte.
- **Garde de route** (`proxy.ts`) : toute page sans session valide redirige vers `/login` (307) et efface le cookie; les appels `/bff/*` répondent `401 {"detail": "Authentification requise."}`; `auth` arrêté sans clé en cache : retour à `/login?erreur=2`, sans effacer le cookie. Accessibles sans session : `/login`, `/session/identify|face|password|logout`, `/robots.txt`. **La signature est vérifiée à chaque requête** (EdDSA par le JWKS d'`auth`, cache de 5 min, relecture limitée à une fois par 10 s pour un `kid` inconnu), avec émetteur, audience, expiration (tolérance 30 s), rôle `operator` et `amr` contenant `face` : un faux cookie n'ouvre rien.
- **`POST /session/logout`** : efface le cookie et renvoie à `/login`.
- **Anti-CSRF** : en plus de `SameSite=Strict`, les POST exigent une requête issue de la page elle-même (`Sec-Fetch-Site: same-origin`, ou `Origin` égale à l'hôte), sinon 403. Corps : 8 Kio (5 Mio pour les images), 413 au-delà. L'adresse source (`X-Forwarded-For` posé par Traefik) est transmise à `auth` pour son verrouillage par adresse.
- **Passerelle** : routeur Traefik `backoffice-login` (`/session/identify|face|password`) avec le limiteur strict de la connexion du back-office (10 requêtes par minute et par adresse, rafale de 5 en production; large en développement) et la limite de corps de 5 Mio : le serveur appelle `auth` en interne, le limiteur de `/api/auth/backoffice` ne verrait pas ces essais.
- **Journaux** (contrat commun) : `backoffice.login_identify` (attribut `email_hash`, HMAC de l'adresse avec `LOG_PSEUDONYM_KEY`), `backoffice.login_face`, `backoffice.login_password` (`success`, `denied` avec motif `face_refused`, `wrong_password`, `invalid_form`, `invalid_images`, `cross_origin`, `body_too_large`, ou `error` `auth_unavailable`), `backoffice.logout`, `backoffice.access_denied` (motifs `no_session`, `session_expired`, `bad_signature`, `not_operator`, `second_factor_missing`, `unknown_key`, `auth_unavailable`…). Jamais d'adresse en clair, de mot de passe, d'image, de jeton ni d'identifiant de défi.
- **Environnement** : `AUTH_URL` (défaut `http://auth:8000`), `AUTH_ISSUER` et `AUTH_AUDIENCE` (défauts `basecamp-auth`, `basecamp-client-api`), `LOG_PSEUDONYM_KEY` (obligatoire en production, clé éphémère en développement).
- **Lien avec shop** : le jeton de la session porte `operator` et `amr: ["face","pwd"]`, que l'API d'administration de `shop` exige. L'écran de connexion (capture caméra) est un ticket distinct : il appellera ces trois routes; aucune connexion par mot de passe seul n'existe, par construction.
## Gestion du catalogue (WORK-61)
Écrans, tous derrière la garde de route : `/produits` (liste paginée de 20, recherche par nom, filtre « Afficher les produits archivés », états de chargement, de liste vide, de recherche sans résultat et d'erreur avec « Réessayer »), `/produits/nouveau` (création) et `/produits/{id}` (modification, images, archivage). L'accueil `/` mène au catalogue.

Le navigateur n'appelle jamais `shop` : il appelle les routes serveur `/bff/products` du back-office, qui relaient à l'API d'administration de `shop` (`SHOP_URL`, réseau interne `app`) avec le jeton du cookie `bo_access` (jamais renvoyé au navigateur ni journalisé).

| Route du back-office | Rôle | API de shop |
|---|---|---|
| `GET /bff/products?limit&offset&include_archived&q` | liste (paramètres bornés avant tout appel) | `GET /admin/products` |
| `POST /bff/products` | création | `POST /admin/products` |
| `GET` / `PATCH /bff/products/{id}` | lecture, modification (corps avec `version`) | `GET` / `PATCH /admin/products/{id}` |
| `POST /bff/products/{id}/archive` | archivage | `POST …/archive` |
| `POST /bff/products/{id}/image` | octets de l'image (2 Mio au plus) | `POST …/image` |

- **Erreurs** : jamais le texte de shop. Chaque échec devient un code et un message français fixes : `unauthorized` 401 (le cookie est effacé, retour à la connexion), `forbidden` 403, `not_found` 404, `stale_version` 409 (« modifié ailleurs »), `archived` 409, `duplicate` 409, `too_many_images` 409, `invalid` 422 (message d'image dédié pour un téléversement), `unavailable` 503, `error` 502, plus `cross_origin` 403, `bad_request` 400 et `too_large` 413 décidés par le back-office. Corps JSON limité à 64 Kio, image à 2 Mio.
- **Formulaire** : mêmes bornes que l'API (nom 1 à 200, identifiant en minuscules et tirets, prix en euros avec 2 décimales au plus converti en centimes, stock 0 à 1 000 000, descriptions 300 et 5 000, caractéristiques bornées), erreurs par champ reliées au contrôle (`aria-describedby`, `aria-invalid`), focus sur le premier champ en erreur. Shop valide à nouveau.
- **Images** : aperçu avant envoi, contrôle du type (JPEG, PNG, WebP) et du poids (2 Mio) avec un refus explicite; le serveur relit le contenu réel. Dix images au plus.
- **Concurrence** : la modification envoie la `version` lue. Sur un 409 de version, la saisie est conservée, un message explique le conflit et « Recharger la dernière version » relit le produit.
- **Archivage** : confirmation explicite (`alertdialog`, focus sur « Annuler »); le produit disparaît du site client et devient en lecture seule, visible avec le filtre des archivés. Il n'y a pas de désarchivage.
- **Journaux** : `backoffice.catalog_list|get|create|update|archive|image` avec `outcome`, `reason` en cas d'échec, `duration_ms`; jamais de jeton ni de donnée de produit.
- **Tests** : composants avec Testing Library (jsdom), routes serveur et logique pure avec Vitest; e2e sur la pile (`apps/backend/shop/tests/e2e/scenarios/test_backoffice_catalog.e2e.py`) : prix, stock et image modifiés depuis le back-office visibles sur le site client, archivage, conflit de version, doublon, image refusée.

## Consultation des commandes (WORK-66)
Lecture seule, derrière la garde de route : `/commandes` (liste paginée de 20, filtre par statut : tous, en attente de paiement, payée, expirée, remboursée; recherche par numéro ou e-mail; tri de la plus récente à la plus ancienne; états de chargement, de liste vide, de recherche sans résultat avec « Effacer les filtres », et d'erreur avec « Réessayer ») et `/commandes/{id}` (numéro, statut, date en heure de Paris, client, articles, sous-total, livraison, total, adresse de livraison; aucune action ni champ modifiable). La navigation et l'accueil mènent aux commandes.

Le navigateur n'appelle jamais `shop` : il appelle les routes serveur `/bff/orders`, qui relaient à l'API d'administration de `shop` (voir [shop](shop.md)) avec le jeton du cookie `bo_access` (jamais renvoyé ni journalisé).

| Route du back-office | Rôle | API de shop |
|---|---|---|
| `GET /bff/orders?limit&offset&status&q` | liste (paramètres bornés avant tout appel) | `GET /admin/orders` |
| `GET /bff/orders/{id}` | détail | `GET /admin/orders/{id}` |

Aucune écriture n'existe : tout autre verbe répond 405.

- **Accès** : en plus de la garde de route (`proxy.ts`), chaque appel `/bff/orders` revérifie le jeton du cookie (signature, rôle `operator`, second facteur `face`) avant d'appeler `shop`. Sans cookie ou session périmée : 401 (cookie effacé); jeton sans le rôle ou sans le visage : 403; `auth` injoignable : 503. `shop` applique la même règle de son côté.
- **Erreurs** : jamais le texte de shop. Codes et messages français fixes : `unauthorized` 401, `forbidden` 403, `not_found` 404 (« Commande introuvable. »), `bad_request` 400, `invalid` 422, `unavailable` 503 (« Les commandes sont momentanément indisponibles. Réessayez dans un instant. »), `error` 502.
- **Données personnelles** : l'e-mail et l'adresse ne s'affichent que dans l'écran et ne sont **jamais** écrits dans les journaux (ni le texte recherché).
- **Audit** : chaque consultation de détail émet `backoffice.order_view` (contrat commun [log-event.schema.json](../development/log-event.schema.json)) : `resource_type` `order`, `resource_id` (identifiant de la commande), `actor_type` `user`, `actor_id` = empreinte HMAC (`LOG_PSEUDONYM_KEY`) de l'identifiant de l'opérateur lu dans son jeton, `duration_ms`; en cas d'échec `outcome` `denied` ou `error` avec `reason` (`not_found`, `forbidden`, `unavailable`…). La liste émet `backoffice.orders_list` (mêmes règles, sans ressource). Un test (`log-contract.unit.test.ts`) vérifie la conformité au schéma.
- **Tests** : composants (Testing Library), routes serveur et gestionnaire (Vitest, couverture ≥ 80 %), accès refusés; e2e sur la pile (`apps/backend/shop/tests/e2e/scenarios/test_backoffice_orders.e2e.py`) : commande passée sur le site, visible dans le back-office avec le bon statut et son détail, refus sans jeton double facteur ou avec le rôle `customer`, aucune écriture.

## Isolation et exposition
- Le site client n'a aucun lien ni route vers le back-office. Le routeur Traefik `backoffice` ne répond que sur l'hôte `admin.*` (`HostRegexp(^admin\..+$)`, hors `/api`); sur le domaine principal, c'est le front qui répond (404).
- `noindex` partout : balise `robots` de la page, `robots.txt` (`Disallow: /`) et en-tête `X-Robots-Tag`.
- En-têtes : CSP sans cadre (`frame-ancestors 'none'`), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`. `Permissions-Policy: camera=(self)` : la caméra n'est autorisée que pour cette origine.
- Le conteneur ne reçoit que `AUTH_URL`, `SHOP_URL` et `LOG_PSEUDONYM_KEY` (aucun secret d'API); le jeton ne vit que dans un cookie `HttpOnly`.

## Journaux
Une ligne JSON par page servie sur la sortie standard, au [contrat commun](../development/logging.md) : `service: basecamp-backoffice`, `event: backoffice.page_served`, `outcome`, `correlation_id` (celui du `X-Correlation-ID` reçu s'il est bien formé, sinon un UUID; renvoyé dans la réponse). Aucune donnée personnelle ni valeur reçue.

## Pile et CI
Service `backoffice` du `docker-compose.yml` (réseau `app`, healthcheck sur `/`), dont dépend Traefik. Job CI `backoffice` (qualité, tests, audit, build) dans `ci.yml`; le test de bout en bout de la pile construit l'image et vérifie 200 + `noindex` sur l'hôte admin et l'absence sur le domaine principal. L'image est construite, scannée (Trivy bloquant) et publiée par `release.yml` comme les autres composants.

## Reste à faire (hors de ce ticket)
Entrée du back-office dans `deploy/manifest.json` et `deploy/docker-compose.prod.yml` après la première image publiée (le manifeste est par digest), puis exposition publique, limiteur et DNS (sous-domaine admin).

## Connexion en trois temps (`/login`)
Écran client (`src/app/login/login-form.tsx`) : identifiant, puis aperçu de la caméra et capture de 3 images (JPEG réduit à 640 px), puis mot de passe, seulement après un visage accepté. Le navigateur appelle les routes serveur du back-office `/session/identify`, `/session/face` et `/session/password` (`src/lib/login-api.ts`), qui relaient vers `auth` (`/backoffice/*`). Aucun score n'est affiché : reconnu ou non.
- **Caméra** (`src/lib/camera.ts`) : arrêt de toutes les pistes (le voyant s'éteint) à chaque sortie d'étape, refus, expiration et démontage. Caméra refusée, absente ou non prise en charge : message clair, aucune étape suivante.
- **Refus** (visage refusé ou mot de passe faux) : retour à l'étape 1, identifiant vide, message générique unique.
- **Défi** : minuteur de `expires_in` (2 min) ; à l'échéance, retour à l'étape 1.
- **Blocage** (`src/lib/lockout.ts`) : `auth` répond le même 401 pendant un blocage, le navigateur compte donc lui-même (3 mots de passe faux ou 5 visages refusés en 10 min, compteurs séparés) et bloque 5 minutes : compte à rebours, champs désactivés, aucun appel. L'état est gardé dans le `localStorage` de l'appareil, indépendamment de l'identifiant ; le blocage serveur reste la référence.
