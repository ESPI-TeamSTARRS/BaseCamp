# Back-office `apps/backoffice`

## Rôle
Application d'administration réservée à l'équipe, servie sur l'hôte admin (`admin.<domaine>`, en local `admin.localhost`). La session (garde de route, cookie de session, trois temps de connexion relayés vers `auth`, déconnexion) est en place (WORK-60) ; l'écran de connexion avec capture du visage et le catalogue arrivent dans les tickets suivants.

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
## Isolation et exposition
- Le site client n'a aucun lien ni route vers le back-office. Le routeur Traefik `backoffice` ne répond que sur l'hôte `admin.*` (`HostRegexp(^admin\..+$)`, hors `/api`); sur le domaine principal, c'est le front qui répond (404).
- `noindex` partout : balise `robots` de la page, `robots.txt` (`Disallow: /`) et en-tête `X-Robots-Tag`.
- En-têtes : CSP sans cadre (`frame-ancestors 'none'`), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`. `Permissions-Policy: camera=(self)` : la caméra n'est autorisée que pour cette origine.
- Le conteneur ne reçoit que AUTH_URL et LOG_PSEUDONYM_KEY (aucun secret d'API); le jeton ne vit que dans un cookie HttpOnly.

## Journaux
Une ligne JSON par page servie sur la sortie standard, au [contrat commun](../development/logging.md) : `service: basecamp-backoffice`, `event: backoffice.page_served`, `outcome`, `correlation_id` (celui du `X-Correlation-ID` reçu s'il est bien formé, sinon un UUID; renvoyé dans la réponse). Aucune donnée personnelle ni valeur reçue.

## Pile et CI
Service `backoffice` du `docker-compose.yml` (réseau `app`, healthcheck sur `/`), dont dépend Traefik. Job CI `backoffice` (qualité, tests, audit, build) dans `ci.yml`; le test de bout en bout de la pile construit l'image et vérifie 200 + `noindex` sur l'hôte admin et l'absence sur le domaine principal. L'image est construite, scannée (Trivy bloquant) et publiée par `release.yml` comme les autres composants.

## Reste à faire (hors de ce ticket)
Entrée du back-office dans `deploy/manifest.json` et `deploy/docker-compose.prod.yml` après la première image publiée (le manifeste est par digest), puis exposition publique, limiteur et DNS (sous-domaine admin).
