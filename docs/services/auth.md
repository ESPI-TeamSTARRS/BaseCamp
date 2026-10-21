# Service `auth`

**Dossier** : `apps/backend/auth`

## Rôle
Comptes clients, jetons d'accès courts, rôle opérateur. Le service est isolé : conteneur, base Postgres, réseau et rôle de base de données propres.

## Structure
Tranches verticales Clean Architecture (`domain / application / infrastructure / presentation`), règle de dépendance vérifiée par `app/__tests__/unit/test_architecture.unit.py`.

| Tranche | Contenu actuel |
|---|---|
| `core` | configuration (`Settings`, variables `APP_*`), journalisation métier (`events`, `logging`), handlers d'erreur assainis |
| `health` | liveness (`GetHealthUseCase`) et readiness (`GetReadinessUseCase`, sonde `DatabaseProbe`) |
| `service_token` | jetons de service : émission (`IssueServiceTokenUseCase`), vérification (`VerifyTokenUseCase`), JWKS, amorçage des clients, limitation de débit par client |
| `registration` | inscription et vérification d'email : `RegisterAccountUseCase`, `VerifyEmailUseCase`, `PasswordPolicy`, `EmailAddress`, dépôts SQLAlchemy dans une unité de travail, hachage argon2id, envoi SMTP |

Les autres tranches métier (`session`) s'ajoutent à côté; leurs routes se documentent ici. Le câblage de `registration` est dans `app/registration/composition.py` (seul endroit qui importe l'infrastructure).

## API
| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | liveness : 200 tant que le processus répond |
| GET | `/health/ready` | readiness : 200 si la base répond, 503 sinon |
| POST | `/internal/token` | jeton de service (réseau interne seulement, voir plus bas) |
| GET | `/internal/jwks` | clé publique de signature (réseau interne seulement) |
| POST | `/register` | inscription `{email, password}` : 202 et message neutre, identique que l'adresse soit libre ou déjà inscrite; 422 assaini si la saisie est invalide |
| POST | `/verify-email` | confirmation `{token}` : 200, ou 400 « Lien de vérification invalide ou expiré. » (jeton inconnu, expiré ou déjà utilisé, même réponse) |

Via la passerelle : `/api/auth/health`, `/api/auth/health/ready`, `/api/auth/register` et `/api/auth/verify-email` (préfixe retiré par Traefik). `register` et `verify-email` ont un routeur dédié avec limitation de débit par IP (60 requêtes/minute, rafale de 30), car le hachage argon2id est coûteux.

### Inscription (`POST /register`)
- Corps strict (`extra="forbid"`). Email normalisé (minuscules, sans espace ni retour à la ligne). Mot de passe : 12 à 128 caractères, mots de passe courants refusés (liste embarquée `app/registration/infrastructure/data/common_passwords.txt`, insensible à la casse), **aucune règle de composition**.
- Entrée invalide : 422 `{"detail", "fields", "messages"}` avec des messages fixes; la valeur saisie n'est jamais renvoyée, un champ en trop n'est pas nommé.
- Compte créé : rôle `customer`, mot de passe haché **argon2id** (paramètres par défaut d'`argon2-cffi`), email non vérifié, jeton de vérification émis puis envoyé par email.
- **Anti-énumération** : le mot de passe est toujours haché avant de savoir si l'adresse existe; une adresse déjà inscrite reçoit la même réponse (statut, corps, en-têtes) et un email « un compte existe déjà » au titulaire. Une course entre deux inscriptions identiques est tranchée par la contrainte d'unicité.
- L'envoi d'email se fait après la transaction; un échec SMTP est journalisé (`auth.email_delivery_failed`) sans changer la réponse.

### Vérification d'email (`POST /verify-email`)
Jeton aléatoire de 256 bits (`secrets.token_urlsafe(32)`), **seul son SHA-256 est stocké**, valable **24 h**, à **usage unique** (un `UPDATE ... WHERE used_at IS NULL AND expires_at > now RETURNING` atomique). Le lien envoyé est `{APP_PUBLIC_BASE_URL}/compte/verification#token=...` : le jeton est dans le fragment, donc absent des journaux d'accès et du `Referer`.

## Tables
Migration `0004_users_et_verification` (down_revision `0003`).

| Table | Colonnes |
|---|---|
| `users` | `id` (uuid, clé primaire), `email` (unique, minuscules), `password_hash`, `role` (`customer` ou `operator`), `email_verified_at` (nullable), `created_at` |
| `email_verification_tokens` | `id`, `user_id` (clé étrangère, suppression en cascade), `token_hash` (SHA-256 hex, unique), `expires_at`, `used_at` (nullable) |

Les horodatages sont en UTC avec fuseau. Un test compare la migration aux modèles SQLAlchemy (aucune dérive possible sans échec). Les routes `/internal/*` (appels entre services) ne sont jamais routées par la passerelle : un appel externe reçoit 404 (couvert par le test e2e `test_auth_stack.e2e.py`).

## Isolation
- Postgres dédié (`postgres-auth`, volume propre) sur le réseau interne `auth-data`, que seuls `auth` et `auth-migrate` rejoignent : `shop` et `payment` ne peuvent pas l'atteindre, et `auth` ne rejoint aucune base des autres services.
- Le rôle `auth` est l'unique compte de cette instance.
- Migrations Alembic (`alembic/`) exécutées par le service one-shot `auth-migrate` avant le démarrage; `alembic upgrade head` est rejouable sans effet.

## Clés de signature
`sh scripts/init-auth-keys.sh` génère une paire Ed25519 dans `.secrets/auth/` (ignoré par Git), montée en secrets Docker dans le conteneur (`/run/secrets/auth_jwt_private_key`, `/run/secrets/auth_jwt_public_key`). Le script ne remplace jamais une clé existante sans `--force`. Les clés ne sont jamais versionnées; une clé commitée par erreur se renouvelle.

## Jetons de service (appels entre services)
Un service appelant (ex. `shop` vers `payment`) obtient un jeton court auprès d'`auth` avec ses identifiants de client (flux `client_credentials`). Les routes `/internal/*` ne sont joignables que depuis le réseau interne `app` (la passerelle ne les route pas : 404 depuis l'extérieur).

### `POST /internal/token`
Corps JSON (champs en trop refusés) :

```json
{"grant_type": "client_credentials", "client_id": "shop", "client_secret": "<secret>",
 "audience": "payment", "scope": "payments:write"}
```

- `grant_type` : uniquement `client_credentials`. `client_id` : `A-Za-z0-9._-`, 1 à 64 caractères. `client_secret` : 1 à 256 caractères. `audience` : service destinataire (`payment`). `scope` : un ou plusieurs scopes séparés par une espace (`payments:write`).

Réponse `200` (`Cache-Control: no-store`) :

```json
{"access_token": "<JWT>", "token_type": "Bearer", "expires_in": 300, "scope": "payments:write"}
```

| Cas | Statut | Corps |
|---|---|---|
| Jeton émis | 200 | ci-dessus |
| Client inconnu, secret invalide (courant ou précédent), scope non autorisé pour le client, scope inconnu, audience inconnue ou sans rapport avec le scope | 401 | `{"error": "invalid_client"}` (identique pour toutes les causes) |
| Corps mal formé, champ manquant ou en trop, `grant_type` autre | 422 | `{"detail": "Requete invalide.", "fields": [...]}` (noms de champs seulement, jamais la valeur reçue; gestionnaire commun) |
| Trop de demandes pour ce client | 429 | `{"error": "rate_limited"}` + en-tête `Retry-After` (secondes) |

Client inconnu et mauvais secret reçoivent la même réponse (statut, corps, en-têtes) et un temps comparable : deux vérifications argon2id sont toujours exécutées (contre une empreinte factice si le client ou son secret précédent n'existe pas). Les causes distinctes ne figurent que dans les journaux internes.

### Le jeton (JWT, EdDSA)
En-tête : `{"alg": "EdDSA", "typ": "JWT", "kid": "<empreinte RFC 7638 de la clé publique>"}`. Durée de vie : **5 minutes**.

| Claim | Valeur |
|---|---|
| `iss` | `basecamp-auth` (`APP_JWT_ISSUER`) |
| `sub` | identifiant du client appelant (`shop`) |
| `aud` | service destinataire (`payment`), chaîne unique |
| `scope` | scopes accordés, séparés par une espace, triés |
| `iat`, `exp` | secondes Unix, `exp = iat + 300` |
| `jti` | identifiant unique du jeton |
| `token_use` | `service` (un jeton client porte `client`) |

Scopes connus : `payments:write` (audience `payment`). Ajouter un scope ou une audience se fait dans `app/service_token/domain/enums/`.

### Côté appelant (contrat pour `payment`, ticket A10)
1. Demander un jeton avec l'`audience` et le `scope` nécessaires; **le mettre en cache jusqu'à environ 30 s avant `exp`**, puis en redemander un (ne pas en redemander à chaque appel : la limitation de débit s'applique).
2. L'envoyer en `Authorization: Bearer <jeton>`.
3. Côté récepteur, accepter uniquement si : la signature EdDSA est valide (algorithme `EdDSA` seul, jamais `none` ni HMAC) avec la clé publique d'`auth`; `iss = basecamp-auth`; `exp` dans le futur; `aud` = le service récepteur; `token_use = service`; `scope` contient le scope requis par la route.
4. Clé publique : `GET /internal/jwks` (JWKS, une clé OKP Ed25519 avec son `kid`, réseau interne) ou le secret Docker `auth_jwt_public_key` monté dans le conteneur récepteur. Rafraîchir le JWKS si le `kid` d'un jeton est inconnu (la rotation des clés de signature est hors périmètre pour l'instant).
5. Un jeton de service n'est jamais accepté là où un jeton client est attendu, et inversement : `aud` et `token_use` sont contrôlés par `VerifyTokenUseCase` (`token_use` attendu fixé par le déploiement), ce que prouvent des tests avec un jeton forgé signé par la même clé.

Le jeton statique actuel de `payment` (`PAYMENT_SERVICE_TOKEN_SHOP`) est inchangé : `payment` adoptera ce contrat sans modification d'`auth`.

### Clients, secrets et rotation
- Un client = identifiant, scopes autorisés, deux empreintes argon2id (secret courant et secret précédent optionnel). Aucun secret en clair en base, ni dans une migration, ni dans les journaux.
- Amorçage : la commande one-shot `python -m app.service_token.bootstrap` (service compose `auth-bootstrap`, après `auth-migrate`) lit les clients dans `APP_SERVICE_CLIENTS` (JSON non secret, ex. `{"shop": ["payments:write"]}`) et leurs secrets dans `APP_SERVICE_CLIENT_SECRET_<CLIENT>` (courant) et `APP_SERVICE_CLIENT_SECRET_<CLIENT>_PREVIOUS` (précédent, optionnel). Idempotente : une empreinte qui vérifie toujours son secret est conservée. Secret de moins de 32 caractères refusé. Seul ce conteneur voit les secrets en clair; `auth` ne lit que les empreintes. Côté compose : `AUTH_SERVICE_CLIENT_SECRET_SHOP` et `AUTH_SERVICE_CLIENT_SECRET_SHOP_PREVIOUS` (voir `.env.example`).
- **Rotation sans coupure** : (1) mettre le nouveau secret dans `AUTH_SERVICE_CLIENT_SECRET_SHOP` et l'ancien dans `AUTH_SERVICE_CLIENT_SECRET_SHOP_PREVIOUS`; (2) `docker compose run --rm auth-bootstrap` (les deux secrets sont valides); (3) déployer le nouveau secret chez l'appelant; (4) vider `..._PREVIOUS` et rejouer l'amorçage : l'ancien secret est révoqué.
- Migration `0003_clients_de_service` : tables `service_clients` et `service_token_rate_limits`. Elle ne dépend que de `0001` et se renumérote sans autre changement si une autre migration s'insère avant.

### Limitation de débit par client
Fenêtre fixe d'une minute, `APP_SERVICE_TOKEN_RATE_LIMIT_PER_MINUTE` demandes (60 par défaut) par `client_id` présenté, succès comme échecs; au-delà : 429 sans effet sur les autres clients. Le compteur est une ligne par client et par fenêtre dans la base d'`auth`, incrémentée par un upsert atomique (`INSERT ... ON CONFLICT DO UPDATE ... RETURNING`) : aucun état en mémoire, plusieurs instances d'`auth` partagent le même compteur. Choix : pas de nouveau service (un Redis dédié ne remplirait pas deux critères sur quatre pour ce seul besoin, volume faible); la limite est contrôlée avant tout hachage pour protéger le CPU. Les identifiants inconnus sont comptés aussi, afin que la limite ne révèle pas l'existence d'un client; les fenêtres anciennes sont purgées à chaque appel.

Les émissions, refus et limitations sont journalisés via le port `BusinessEventLogger` (catalogue [ci-dessous](#événements-métier)); la corrélation (`X-Correlation-ID`) suit le contrat commun.

## Règles
- Mots de passe hachés avec un algorithme dédié, jamais journalisés.
- Cookies de session `HttpOnly`, `Secure`, `SameSite=Strict`.
- Limitation de débit contre le brute-force (par client pour les jetons de service).
- Séparation des rôles : un client n'accède jamais aux routes opérateur.

## Configuration
| Variable | Rôle |
|---|---|
| `APP_SERVICE_NAME`, `APP_ENVIRONMENT` | identité et environnement |
| `APP_DB_HOST`, `APP_DB_PORT`, `APP_DB_NAME`, `APP_DB_USER`, `APP_DB_PASSWORD` | connexion à la base d'`auth` (le mot de passe vient de l'environnement) |
| `APP_JWT_PRIVATE_KEY_FILE`, `APP_JWT_PUBLIC_KEY_FILE` | chemins des clés Ed25519 (défaut : secrets Docker `/run/secrets/auth_jwt_*`) |
| `APP_JWT_ISSUER` | claim `iss` (défaut `basecamp-auth`) |
| `APP_SERVICE_TOKEN_RATE_LIMIT_PER_MINUTE` | demandes de jeton par client et par minute (défaut 60) |
| `APP_SERVICE_CLIENTS`, `APP_SERVICE_CLIENT_SECRET_<CLIENT>[_PREVIOUS]` | lus par la commande d'amorçage uniquement |
| `APP_LOG_PSEUDONYM_KEY` | clé HMAC des empreintes d'email dans les logs; obligatoire hors `dev` et `local` |
| `APP_SMTP_HOST`, `APP_SMTP_PORT` | serveur SMTP (défaut `localhost:1025`; en compose : `mailpit:1025`) |
| `APP_SMTP_FROM` | expéditeur des emails (défaut `comptes@basecamp.local`) |
| `APP_SMTP_USERNAME`, `APP_SMTP_PASSWORD` | authentification SMTP facultative (le mot de passe est un `SecretStr`, jamais journalisé ni versionné) |
| `APP_SMTP_STARTTLS` | active STARTTLS (défaut `false`, à activer avec un relais réel) |
| `APP_SMTP_TIMEOUT_SECONDS` | délai de connexion SMTP (défaut 5) |
| `APP_PUBLIC_BASE_URL` | origine publique du site, base des liens des emails (défaut `http://localhost:8080`) |

Côté compose : `AUTH_DB_NAME`, `AUTH_DB_USER`, `AUTH_DB_PASSWORD`, `AUTH_SMTP_FROM`, `NEXT_PUBLIC_SITE_URL` (voir `.env.example`).

## Emails et Mailpit
En local et en CI, le service `mailpit` (réseau interne `app`, SMTP 1025, interface et API 8025) reçoit tous les emails d'`auth`. Il n'est ni publié ni routé par la passerelle. Pour le lire depuis l'hôte (scénarios e2e, vérification manuelle), ajouter la surcharge `docker-compose.e2e.yml`, qui le publie sur `127.0.0.1:${MAILPIT_PORT:-8025}` :

```bash
docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d --build --wait traefik mailpit
```

## Événements métier
Le module de journalisation (port `BusinessEventLogger`, adaptateur JSON, middleware `X-Correlation-ID`) est en place; format et règles : [journalisation métier](../development/logging.md). Chaque ticket d'auth émet ses événements et les ajoute à ce catalogue.

Déjà émis : `service.request_rejected` (denied, `invalid_request`, requête rejetée par la validation), `service.unhandled_error` (error, `internal_error`) et les événements de jetons de service ci-dessous.

Jetons de service (ressource `service_client` + identifiant du client; jamais de secret, de jeton ni d'identifiant de secret) :

| Événement | Outcome | Reason | Attributs |
|---|---|---|---|
| `auth.service_token_issued` | success | | `audience`, `scope`, `jti`, `expires_in`; acteur `service` = le client |
| `auth.service_token_denied` | denied | `unknown_client`, `invalid_secret`, `unknown_audience`, `scope_not_allowed` (priorité dans cet ordre; la réponse HTTP reste un 401 identique) | |
| `auth.service_rate_limited` | denied | `rate_limit_exceeded` | `retry_after_seconds` |
| `auth.token_verification_denied` | denied | `expired`, `issued_in_future`, `issuer`, `token_use`, `audience`, `scope` (ressource `service_token`) | |
| `auth.service_client_bootstrapped` | success | | commande d'amorçage |
Le module de journalisation (port `BusinessEventLogger`, adaptateur JSON, middleware `X-Correlation-ID`) est en place; format et règles : [journalisation métier](../development/logging.md). La tranche `registration` émet, via le port, les événements suivants (noms et motifs stables, jamais renommés). L'email n'apparaît que sous la forme `attributes.email_hash` (HMAC tronqué); jamais de mot de passe, de jeton ni d'adresse en clair, et la saisie invalide n'est pas journalisée.

Déjà émis hors tranche : `service.request_rejected` (denied, `invalid_request`, requête rejetée par la validation) et `service.unhandled_error` (error, `internal_error`).

| Événement | Outcome | Reason | Ressource et attributs |
|---|---|---|---|
| `auth.account_registered` | success | | `account` + id; `email_hash` |
| `auth.registration_rejected` | denied | `email_already_used` | `account`; `email_hash` |
| `auth.registration_rejected` | denied | `invalid_email`, `weak_password` | `account`; `rule` (`email_invalid`, `password_too_short`, `password_too_long`, `password_too_common`) |
| `auth.email_verified` | success | | `account` + id |
| `auth.email_verification_failed` | denied | `invalid_or_expired_token` | `email_verification` |
| `auth.email_delivery_failed` | error | `mail_delivery_failed` | `email_verification`; `kind` (`verification` ou `account_exists`) |

Catalogue cible des prochains tickets d'auth (même règles) :

| Événement | Outcome | Reason |
|---|---|---|
| `auth.login_succeeded` | success | |
| `auth.login_failed` | denied | `invalid_credentials`, `account_locked` (avec `client_ip`) |
| `auth.token_refreshed` | success | |
| `auth.token_rejected` | denied | `expired`, `invalid`, `revoked` |
| `auth.logout` | success | |
| `auth.password_changed` | success | |

Avant l'authentification, l'acteur est inconnu : seul `email_hash` identifie la tentative.

## Tests
`uv run poe test` (unit et integ, couverture ≥ 80 %); `uv run poe test:e2e` sur la pile lancée (`E2E_BASE_URL`, `http://127.0.0.1:8080` par défaut); les scénarios de jetons appellent `auth` depuis le conteneur `shop` (réseau `app`, `docker compose exec`) et lisent le secret du client `shop` dans `AUTH_SERVICE_CLIENT_SECRET_SHOP` ou `.env`.
`uv run poe test` (unit et integ, couverture ≥ 80 %); `uv run poe test:e2e` sur la pile lancée (`E2E_BASE_URL`, `http://127.0.0.1:8080` par défaut). Les scénarios d'inscription lisent les emails dans Mailpit via `E2E_MAILPIT_URL` (ignorés sans cette variable); `E2E_CHECK_LOGS=1` ajoute le contrôle des journaux des conteneurs (`docker compose logs`) : ni mot de passe, ni jeton, ni adresse.
