# Service `auth`

**Dossier** : `apps/backend/auth`

## Rôle
Comptes clients, jetons d'accès courts, rôle opérateur. Le service est isolé : conteneur, base Postgres, réseau et rôle de base de données propres.

## Structure
Tranches verticales Clean Architecture (`domain / application / infrastructure / presentation`), règle de dépendance vérifiée par `app/__tests__/unit/test_architecture.unit.py`.

| Tranche | Contenu actuel |
|---|---|
| `core` | configuration (`Settings`, variables `APP_*`) |
| `health` | liveness (`GetHealthUseCase`) et readiness (`GetReadinessUseCase`, sonde `DatabaseProbe`) |
| `service_token` | jetons de service : émission (`IssueServiceTokenUseCase`), vérification (`VerifyTokenUseCase`), JWKS, amorçage des clients, limitation de débit par client |

Les tranches métier (`account`, `session`) s'ajoutent à côté de `health`; leurs routes se documentent ici.

## API
| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | liveness : 200 tant que le processus répond |
| GET | `/health/ready` | readiness : 200 si la base répond, 503 sinon |
| POST | `/internal/token` | jeton de service (réseau interne seulement, voir plus bas) |
| GET | `/internal/jwks` | clé publique de signature (réseau interne seulement) |

Via la passerelle : `/api/auth/health` et `/api/auth/health/ready` (préfixe retiré par Traefik). Les routes `/internal/*` (appels entre services) ne sont jamais routées par la passerelle : un appel externe reçoit 404 (couvert par le test e2e `test_auth_stack.e2e.py`).

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

Côté compose : `AUTH_DB_NAME`, `AUTH_DB_USER`, `AUTH_DB_PASSWORD` (voir `.env.example`).

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

Catalogue cible (à émettre par les tickets d'auth, sans mot de passe, jeton ni email en clair; l'email n'apparaît que sous la forme `attributes.email_hash`) :

| Événement | Outcome | Reason |
|---|---|---|
| `auth.account_registered` | success | |
| `auth.registration_rejected` | denied | `email_already_used`, `weak_password` |
| `auth.login_succeeded` | success | |
| `auth.login_failed` | denied | `invalid_credentials`, `account_locked` (avec `client_ip`) |
| `auth.token_refreshed` | success | |
| `auth.token_rejected` | denied | `expired`, `invalid`, `revoked` |
| `auth.logout` | success | |
| `auth.password_changed` | success | |

Avant l'authentification, l'acteur est inconnu : seul `email_hash` identifie la tentative.

## Tests
`uv run poe test` (unit et integ, couverture ≥ 80 %); `uv run poe test:e2e` sur la pile lancée (`E2E_BASE_URL`, `http://127.0.0.1:8080` par défaut); les scénarios de jetons appellent `auth` depuis le conteneur `shop` (réseau `app`, `docker compose exec`) et lisent le secret du client `shop` dans `AUTH_SERVICE_CLIENT_SECRET_SHOP` ou `.env`.
