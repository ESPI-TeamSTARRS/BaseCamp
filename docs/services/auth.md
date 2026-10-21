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
| `service_token` | jetons de service : émission (`IssueServiceTokenUseCase`), vérification (`VerifyTokenUseCase`), amorçage des clients, limitation de débit par client, `Ed25519KeyStore` (lecture des clés montées) |
| `registration` | inscription et vérification d'email : `RegisterAccountUseCase`, `VerifyEmailUseCase`, `PasswordPolicy`, `EmailAddress`, dépôts SQLAlchemy dans une unité de travail, hachage argon2id, envoi SMTP |
| `password_reset` | réinitialisation du mot de passe : `RequestPasswordResetUseCase`, `ResetPasswordUseCase`, port `SessionRevoker` (supprime les jetons de rafraîchissement), limite par adresse en base; réutilise le domaine de `registration` (`PasswordPolicy`, `EmailAddress`, horloge, jetons, hachage) |
| `login` | connexion et jetons d'accès clients : `LoginAccountUseCase`, `GetCurrentAccountUseCase`, `GetPublicKeysUseCase`, trousseau Ed25519 (`Ed25519KeyRing`, `LazyEd25519KeyRing`), signature et vérification JWT (`JwtAccessTokenSigner`, `JwtAccessTokenVerifier`), vérificateur argon2id avec hachage factice, dépôts SQLAlchemy |

Les autres tranches métier (par exemple « déconnecter tous mes appareils ») s'ajoutent à côté; leurs routes se documentent ici. Le câblage de chaque tranche est dans son `composition.py` ou `wiring.py` (seul endroit qui importe l'infrastructure). `login` ne dépend d'aucune autre tranche : elle déclare ses propres modèles sur la table `users` (colonnes lues seulement) avec une base SQLAlchemy distincte; seul `app/login/composition.py` réutilise `Ed25519KeyStore` pour lire le secret de signature monté, afin que jetons clients et jetons de service partagent la même clé et le même `kid`.

## API
| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | liveness : 200 tant que le processus répond |
| GET | `/health/ready` | readiness : 200 si la base répond, 503 sinon |
| POST | `/internal/token` | jeton de service (réseau interne seulement, voir plus bas) |
| POST | `/register` | inscription `{email, password}` : 202 et message neutre, identique que l'adresse soit libre ou déjà inscrite; 422 assaini si la saisie est invalide |
| POST | `/verify-email` | confirmation `{token}` : 200, ou 400 « Lien de vérification invalide ou expiré. » (jeton inconnu, expiré ou déjà utilisé, même réponse) |
| POST | `/password/forgot` | demande de lien `{email}` : **toujours 202** et message neutre (compte existant ou non, adresse mal formée, limite atteinte); 422 assaini si le corps est mal formé |
| POST | `/password/reset` | nouveau mot de passe `{token, password}` : 200, 400 « Lien de réinitialisation invalide ou expiré. » (jeton inconnu, expiré, déjà utilisé ou remplacé, même réponse) ou 422 assaini si le mot de passe est refusé |

| POST | `/login` | connexion `{email, password}` : 200 `{access_token, token_type: "Bearer", expires_in}` et cookie de rafraîchissement; 401 « Identifiants invalides. » identique pour toute cause; 422 assaini |
| POST | `/refresh` | rotation de session : cookie `refresh_token` + en-tête `X-Requested-With` obligatoire (anti-CSRF, sinon 403 « Requête refusée. »); 200 `{access_token, token_type: "Bearer", expires_in}` et **nouveau** cookie; 401 « Session expirée. » identique pour jeton absent, inconnu, expiré, rejoué ou de compte désactivé, avec effacement du cookie |
| POST | `/logout` | révoque la session (famille du jeton) : 204 et cookie effacé; **idempotent** (jeton absent, inconnu ou déjà révoqué : même 204); `X-Requested-With` obligatoire |
| GET | `/me` | profil `{id, email, roles, email_verified}` du porteur d'un `Authorization: Bearer <jeton>` valide; 401 « Authentification requise. » (en-tête `WWW-Authenticate: Bearer`) pour tout jeton absent, expiré, falsifié, sans signature, d'une autre audience, de service ou d'un compte désactivé |
| GET | `/.well-known/jwks.json` | **unique route JWKS** (clés publiques de vérification, RFC 7517/8037), `Cache-Control: public, max-age=300`; lisible aussi sur le réseau interne par `http://auth:8000/.well-known/jwks.json` |

Via la passerelle : `/api/auth/health`, `/api/auth/health/ready`, `/api/auth/register`, `/api/auth/verify-email`, `/api/auth/login`, `/api/auth/refresh`, `/api/auth/logout`, `/api/auth/me`, `/api/auth/password/forgot` et `/api/auth/password/reset` (préfixe retiré par Traefik). `register`, `verify-email` et `login` ont un routeur dédié avec limitation de débit par IP (60 requêtes/minute, rafale de 30), car le hachage argon2id est coûteux. `password/forgot` et `password/reset` ont le leur (`auth-password`, 20 requêtes/minute par IP, rafale de 10), en développement (`infra/traefik/dynamic.yml`) et en production (`deploy/traefik/dynamic.prod.yml`, clé IP réelle derrière Cloudflare). Le JWKS est servi à la racine de la passerelle, `/.well-known/jwks.json` (routeur `auth-jwks`, lecture seule, sans retrait de préfixe), et aussi à `/api/auth/.well-known/jwks.json`. L'ancienne route `/internal/jwks` n'existe plus : une seule route publie les clés.

### Inscription (`POST /register`)
- Corps strict (`extra="forbid"`). Email normalisé (minuscules, sans espace ni retour à la ligne). Mot de passe : 12 à 128 caractères, mots de passe courants refusés (liste embarquée `app/registration/infrastructure/data/common_passwords.txt`, insensible à la casse), **aucune règle de composition**.
- Entrée invalide : 422 `{"detail", "fields", "messages"}` avec des messages fixes; la valeur saisie n'est jamais renvoyée, un champ en trop n'est pas nommé.
- Compte créé : rôle `customer`, mot de passe haché **argon2id** (paramètres par défaut d'`argon2-cffi`), email non vérifié, jeton de vérification émis puis envoyé par email.
- **Anti-énumération** : le mot de passe est toujours haché avant de savoir si l'adresse existe; une adresse déjà inscrite reçoit la même réponse (statut, corps, en-têtes) et un email « un compte existe déjà » au titulaire. Une course entre deux inscriptions identiques est tranchée par la contrainte d'unicité.
- L'envoi d'email se fait après la transaction; un échec SMTP est journalisé (`auth.email_delivery_failed`) sans changer la réponse.

### Vérification d'email (`POST /verify-email`)
Jeton aléatoire de 256 bits (`secrets.token_urlsafe(32)`), **seul son SHA-256 est stocké**, valable **24 h**, à **usage unique** (un `UPDATE ... WHERE used_at IS NULL AND expires_at > now RETURNING` atomique). Le lien envoyé est `{APP_PUBLIC_BASE_URL}/compte/verification#token=...` : le jeton est dans le fragment, donc absent des journaux d'accès et du `Referer`.

### Réinitialisation du mot de passe (`/password/forgot`, `/password/reset`)
- **Demande** : réponse **toujours 202 avec le même corps et les mêmes en-têtes**, que le compte existe, que l'adresse soit inconnue ou mal formée, ou que la limite soit atteinte. Le travail en base est le même dans tous les cas (jeton généré, quota décompté); l'email part **après** la réponse (`BackgroundTasks`), donc le temps de réponse ne dépend ni de l'existence du compte ni d'une panne SMTP (comparé par un scénario e2e).
- **Jeton** : 256 bits (`secrets.token_urlsafe(32)`), **seul son SHA-256 est stocké**, valable **30 min**, à usage unique (`UPDATE ... WHERE used_at IS NULL AND expires_at > now RETURNING` atomique). Une nouvelle demande **invalide** les jetons encore valides du compte. Le lien est `{APP_PUBLIC_BASE_URL}/compte/reinitialiser#token=...` : jeton dans le fragment (absent des journaux d'accès et du `Referer`), aucune donnée personnelle dans le lien.
- **Limite par adresse** : 3 demandes par heure et par adresse, comptées en base (table `password_reset_attempts`, empreinte HMAC de l'adresse et non l'adresse), donc sans état en mémoire, partagées entre instances et conservées au redémarrage. Au-delà, même réponse 202 mais aucun email ni jeton. La limite par IP est celle de Traefik (voir ci-dessus); elle sera remplacée ou complétée par la limitation de débit applicative du ticket A6.
- **Remplacement** : le mot de passe suit la politique de l'inscription (`PasswordPolicy`, 12 à 128 caractères, mots courants refusés, aucune règle de composition) et est haché en **argon2id**. Un mot de passe refusé (422 assaini) **ne consomme pas** le jeton. Dans une seule transaction : jeton consommé, mot de passe remplacé, **toutes les sessions révoquées** (port `SessionRevoker`). Puis email de notification de changement, envoyé après la réponse comme le lien (un échec est journalisé, il n'annule pas le changement).
- Jeton inconnu, expiré, déjà utilisé ou remplacé : le même 400 générique.
- Panne d'email : réponse inchangée, événement `auth.email_delivery_failed` (`kind` = `password_reset` ou `password_changed`).

#### Sessions après un changement de mot de passe (`SessionRevoker`)
Le cas d'usage dépend du port `app/password_reset/domain/interfaces/session_revoker.py` (`revoke_all(user_id, now)`, qui renvoie le nombre de sessions révoquées), appelé **dans la transaction** du changement de mot de passe. L'adaptateur `SqlAlchemySessionRevoker` **supprime tous les jetons de rafraîchissement du compte** (`refresh_tokens`, la famille entière) : un jeton supprimé est inconnu au rafraîchissement, donc refusé; si la transaction échoue, rien n'est supprimé. Il ne dépend pas de la tranche `login` : il ne voit que la colonne `user_id` de la table.

Un jeton d'accès déjà émis n'est pas révoqué : il reste valide jusqu'à son expiration (15 minutes au plus), comme pour une désactivation de compte. Seul `/me` consulte l'état du compte.

Le cas d'usage journalise `auth.password_reset_completed` avec l'attribut `sessions_revoked` (nombre de jetons de rafraîchissement supprimés, jamais leur valeur).

Le futur changement de mot de passe depuis « mon compte » réutilisera le même port.

### Connexion (`POST /login`)
- Corps strict (`extra="forbid"`, mot de passe de 256 caractères au plus avant tout hachage). Email normalisé (minuscules, sans espace).
- **Succès** (compte actif, bon mot de passe, email vérifié ou non) : `access_token` (JWT, 15 minutes) dans le corps, jeton de rafraîchissement opaque (256 bits) dans le cookie `refresh_token; HttpOnly; Secure; SameSite=Strict; Path=/api/auth; Max-Age=604800`. Seul le SHA-256 du jeton de rafraîchissement est stocké (`refresh_tokens`). Chaque connexion ouvre une **famille** de jetons (voir « Rafraîchissement et déconnexion »). Réponse en `Cache-Control: no-store`.
- **Anti-énumération** : email inconnu, mauvais mot de passe et compte désactivé donnent la même réponse (statut, corps, en-têtes hors `X-Correlation-ID`) et coûtent chacun **exactement une vérification argon2id** (un hachage factice, calculé au démarrage avec les mêmes paramètres, sert à l'email inconnu; le compte désactivé est vérifié avec le vrai hachage avant d'être refusé). Le motif réel n'existe que dans le journal (`attributes.cause`).
- **Ré-hachage** : après une connexion réussie, si le hachage stocké a été produit avec d'autres paramètres argon2id que ceux en vigueur (`check_needs_rehash`), le mot de passe est ré-haché et remplacé dans la même transaction que le jeton de rafraîchissement.
- Compte « désactivé » : `users.disabled_at` non nul. Il refuse la connexion et invalide aussitôt `/me` (un jeton déjà émis reste valide chez `shop` et `payment` jusqu'à son expiration, 15 minutes au plus).
- Le verrouillage progressif (A6) n'est pas là : seule la limitation de débit de la passerelle protège du brute-force pour l'instant.

### Rafraîchissement et déconnexion (`POST /refresh`, `POST /logout`)
- **Rotation** : le jeton présenté est consommé par un seul `UPDATE ... WHERE used_at IS NULL AND expires_at > now RETURNING` atomique, puis un nouveau jeton (256 bits, durée de 7 jours neuve) est émis dans la même famille avec un nouveau jeton d'accès (15 minutes). L'ancien ne sert plus. Deux rafraîchissements simultanés avec le même jeton : **un seul réussit**, les autres reçoivent 401 (test d'intégration à threads et scénario e2e sur Postgres).
- **Détection de réutilisation** : un jeton déjà consommé qui revient (et non expiré) est un rejeu : **toute la famille est supprimée**, la réponse est 401 et l'événement `auth.refresh_reuse_detected` est journalisé. Conséquence assumée : le perdant d'une course légitime (deux onglets qui rafraîchissent en même temps sans le partager) déconnecte aussi le gagnant; le front limite ce risque avec un seul rafraîchissement à la fois par onglet.
- **Réponse unique** : jeton absent, inconnu, expiré, rejoué, compte désactivé ou disparu donnent le même 401 `{"detail": "Session expirée."}` et efface le cookie (le front ne reboucle pas). Le motif n'existe que dans le journal.
- **Anti-CSRF** : l'en-tête `X-Requested-With` (n'importe quelle valeur non vide) est exigé en plus de `SameSite=Strict`; une requête inter-sites ne peut pas le poser sans pré-vérification CORS, que le service n'autorise pas.
- **Déconnexion** : supprime la famille du jeton présenté (même si ce jeton a déjà été remplacé), efface le cookie, répond 204 dans tous les cas. Le jeton d'accès déjà émis reste valide jusqu'à son expiration (15 minutes au plus). Hors périmètre : « déconnecter tous mes appareils ».
- **Réinitialisation du mot de passe** : elle supprime tous les jetons de rafraîchissement du compte, toutes familles confondues.
- Les lignes antérieures à la rotation n'ont ni famille ni `used_at` : un tel jeton forme sa propre famille et est consommable normalement.

### Jetons d'accès clients
JWT signé **EdDSA (Ed25519)** avec la même clé que les jetons de service, en-tête `{"alg":"EdDSA","typ":"JWT","kid":"<empreinte RFC 7638 de la clé publique>"}`.

| Claim | Valeur |
|---|---|
| `iss` | `APP_JWT_ISSUER` (défaut `basecamp-auth`) |
| `aud` | `APP_JWT_AUDIENCE` (défaut `basecamp-client-api`) : audience **dédiée aux jetons clients**, jamais celle d'un service |
| `sub` | identifiant du compte (UUID) |
| `roles` | liste de rôles, aujourd'hui `["customer"]` ou `["operator"]` |
| `email_verified` | booléen |
| `token_use` | `"client"` (`TokenUse.CLIENT`) : un jeton de service porte `"service"` |
| `iat`, `exp` | émission et expiration (15 minutes) |
| `jti` | identifiant unique du jeton (UUID v4) |

L'adresse email n'est pas dans le jeton (donnée personnelle) : elle se lit par `GET /me`. Un jeton client n'est jamais accepté comme jeton de service (audience et `token_use` différents) et inversement; des tests (`test_login_composition.integ.py`) le prouvent avec la même clé.

### Contrat de vérification pour `shop` et `payment` (jeton client)
Un service vérifie un jeton **sans appeler `auth`** :

1. Récupérer le JWKS (`http://auth:8000/.well-known/jwks.json` sur le réseau `app`; `payment` n'est pas sur ce réseau, son accès aux clés relève du ticket qui lui branchera l'authentification) et le garder en cache au plus 5 minutes. Sur un `kid` inconnu, recharger **une** fois (au plus une fois par minute), puis refuser.
2. N'accepter que `alg` = `EdDSA` (jamais `none`, jamais `HS*`) et choisir la clé par `kid`; refuser un jeton sans `kid`.
3. Vérifier la signature, puis `iss`, `aud` (= `basecamp-client-api`), `token_use` (= `client`), `exp` (tolérance d'horloge de 30 secondes au plus) et la présence de `sub`, `roles`, `jti`.
4. Décider des droits d'après `roles` (jamais d'après une donnée envoyée par le client). `email_verified` conditionne les actions qui l'exigent.
5. Répondre **401 générique** (sans motif) pour tout échec, et journaliser le motif interne côté service.

Un jeton valide n'est pas révoqué avant `exp` chez le vérificateur (compromis assumé : durée courte de 15 minutes); seul `auth` (`/me`) consulte l'état du compte.

### Rotation des clés de signature
Les jetons de l'ancienne clé restent valides jusqu'à leur expiration (test d'intégration dédié) :
1. `sh scripts/init-auth-keys.sh --force` génère une nouvelle paire et **conserve l'ancienne clé publique** dans `.secrets/auth/previous/`.
2. Monter ce dossier dans le conteneur `auth` et définir `APP_JWT_PREVIOUS_PUBLIC_KEYS_DIR` : le JWKS publie alors les deux clés (courante en premier) et `auth` vérifie les jetons clients des deux, mais signe avec la nouvelle seule. Les jetons de service (5 minutes) ne sont vérifiés qu'avec la clé courante : redémarrer après la rotation suffit.
3. Après 15 minutes (durée d'un jeton d'accès) plus la durée de cache du JWKS, retirer l'ancienne clé publique.

## Tables
Migrations `0004_users_et_verification` (down_revision `0003`), `0006_reinitialisation_mot_de_passe` (down_revision `0004`) puis `0007_login` (down_revision `0006`) et `0008_refresh_rotation` (down_revision `0007`, deux colonnes nullables et un index, rien de supprimé ni renommé : l'ancienne version continue de fonctionner). La 0006 est additive : trois tables, rien de modifié ni supprimé. La 0007 l'est aussi (expand/contract) : une colonne nullable et une table, rien n'est supprimé ni renommé.

| Table | Colonnes |
|---|---|
| `users` | `id` (uuid, clé primaire), `email` (unique, minuscules), `password_hash`, `role` (`customer` ou `operator`), `email_verified_at` (nullable), `created_at`, `disabled_at` (nullable, ajouté par la 0007 : compte désactivé) |
| `email_verification_tokens` | `id`, `user_id` (clé étrangère, suppression en cascade), `token_hash` (SHA-256 hex, unique), `expires_at`, `used_at` (nullable) |
| `password_reset_tokens` | `id`, `user_id` (clé étrangère, suppression en cascade), `token_hash` (SHA-256 hex, unique), `expires_at`, `used_at` (nullable) |
| `password_reset_attempts` | `id`, `email_fingerprint` (HMAC de l'adresse, indexé), `requested_at` (indexé); purgée à chaque demande au-delà de la fenêtre d'une heure |
| `session_revocations` | **plus utilisée** (WORK-36 l'écrivait, la révocation passe désormais par la suppression des `refresh_tokens`); conservée par la migration 0006 le temps de l'ancienne version, une migration *contract* ultérieure la supprimera |
| `refresh_tokens` | `id`, `user_id` (clé étrangère, suppression en cascade, indexé), `token_hash` (SHA-256 hex, unique), `created_at`, `expires_at` (0007), `family_id` (uuid nullable, indexé : connexion d'origine; nul = sa propre famille) et `used_at` (nullable : consommé par un rafraîchissement) (0008) |

Les horodatages sont en UTC avec fuseau. Un test compare la migration aux modèles SQLAlchemy (aucune dérive possible sans échec). Les routes `/internal/*` (appels entre services) ne sont jamais routées par la passerelle : un appel externe reçoit 404 (couvert par le test e2e `test_auth_stack.e2e.py`).

## Isolation
- Postgres dédié (`postgres-auth`, volume propre) sur le réseau interne `auth-data`, que seuls `auth` et `auth-migrate` rejoignent : `shop` et `payment` ne peuvent pas l'atteindre, et `auth` ne rejoint aucune base des autres services.
- Le rôle `auth` est l'unique compte de cette instance.
- Migrations Alembic (`alembic/`) exécutées par le service one-shot `auth-migrate` avant le démarrage; `alembic upgrade head` est rejouable sans effet.

## Clés de signature
`sh scripts/init-auth-keys.sh` génère une paire Ed25519 dans `.secrets/auth/` (ignoré par Git), montée en secrets Docker dans le conteneur (`/run/secrets/auth_jwt_private_key`, `/run/secrets/auth_jwt_public_key`). Les clés sont lues au premier usage (le service démarre et répond sur `/health` sans elles). Le script ne remplace jamais une clé existante sans `--force` (voir la rotation ci-dessus). Les clés ne sont jamais versionnées; une clé commitée par erreur se renouvelle. La clé privée n'est jamais journalisée ni affichée (le `repr` du trousseau ne montre que le `kid`; une erreur de chargement ne cite pas le contenu du fichier).

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
4. Clé publique : `GET /.well-known/jwks.json` (JWKS, clés OKP Ed25519 avec leur `kid`, réseau interne) ou le secret Docker `auth_jwt_public_key` monté dans le conteneur récepteur. Rafraîchir le JWKS si le `kid` d'un jeton est inconnu.
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
- Cookie de rafraîchissement `HttpOnly`, `Secure`, `SameSite=Strict`, limité à `/api/auth`; le jeton d'accès n'est jamais un cookie, et le front ne le garde qu'en mémoire.
- Limitation de débit contre le brute-force (par client pour les jetons de service).
- Séparation des rôles : un client n'accède jamais aux routes opérateur.

## Configuration
| Variable | Rôle |
|---|---|
| `APP_SERVICE_NAME`, `APP_ENVIRONMENT` | identité et environnement |
| `APP_DB_HOST`, `APP_DB_PORT`, `APP_DB_NAME`, `APP_DB_USER`, `APP_DB_PASSWORD` | connexion à la base d'`auth` (le mot de passe vient de l'environnement) |
| `APP_JWT_PRIVATE_KEY_FILE`, `APP_JWT_PUBLIC_KEY_FILE` | chemins des clés Ed25519 (défaut : secrets Docker `/run/secrets/auth_jwt_*`) |
| `APP_JWT_ISSUER` | claim `iss` (défaut `basecamp-auth`) |
| `APP_JWT_AUDIENCE` | claim `aud` des jetons clients (défaut `basecamp-client-api`) |
| `APP_JWT_PREVIOUS_PUBLIC_KEYS_DIR` | dossier facultatif de clés publiques PEM précédentes, publiées et acceptées pendant une rotation |
| `APP_ACCESS_TOKEN_TTL_SECONDS` | durée du jeton d'accès client (défaut 900, strictement positive) |
| `APP_REFRESH_TOKEN_TTL_SECONDS` | durée du jeton de rafraîchissement et du cookie (défaut 604800, 7 jours) |
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

La tranche `registration` émet, via le port, les événements suivants (noms et motifs stables, jamais renommés). L'email n'apparaît que sous la forme `attributes.email_hash` (HMAC tronqué); jamais de mot de passe, de jeton ni d'adresse en clair, et la saisie invalide n'est pas journalisée.

| Événement | Outcome | Reason | Ressource et attributs |
|---|---|---|---|
| `auth.account_registered` | success | | `account` + id; `email_hash` |
| `auth.registration_rejected` | denied | `email_already_used` | `account`; `email_hash` |
| `auth.registration_rejected` | denied | `invalid_email`, `weak_password` | `account`; `rule` (`email_invalid`, `password_too_short`, `password_too_long`, `password_too_common`) |
| `auth.email_verified` | success | | `account` + id |
| `auth.email_verification_failed` | denied | `invalid_or_expired_token` | `email_verification` |
| `auth.email_delivery_failed` | error | `mail_delivery_failed` | `email_verification`, `password_reset` ou `account`; `kind` (`verification`, `account_exists`, `password_reset` ou `password_changed`) |
| `auth.password_reset_requested` | success | | `account` + id; `email_hash` (compte existant, lien émis) |
| `auth.password_reset_rejected` | denied | `unknown_account`, `rate_limited` | `account`; `email_hash` |
| `auth.password_reset_rejected` | denied | `invalid_email` | `account` |
| `auth.password_reset_rejected` | denied | `weak_password` | `account`; `rule` (`password_too_short`, `password_too_long`, `password_too_common`) |
| `auth.password_reset_rejected` | denied | `invalid_or_expired_token` | `password_reset` |
| `auth.password_reset_completed` | success | | `account` + id |

Ces distinctions ne sont visibles que dans les journaux : la réponse HTTP de `/password/forgot` ne les révèle jamais.

La tranche `login` émet (mêmes règles : email seulement en `email_hash`, jamais de mot de passe, de jeton, de cookie ni de clé) :

| Événement | Outcome | Reason | Ressource et attributs |
|---|---|---|---|
| `auth.login_succeeded` | success | | `account` + id, acteur `user` + id; `email_hash`, `hash_upgraded` (le hachage a été ré-haché) |
| `auth.login_failed` | denied | `invalid_credentials` | `account` (+ id si le compte existe); `client_ip`; `email_hash`; `cause` interne : `unknown_account`, `wrong_password` ou `account_disabled` |
| `auth.token_refreshed` | success | | `account` + id, acteur `user` + id; `client_ip` |
| `auth.refresh_rejected` | denied | `invalid_refresh_token` | `refresh_token`; `client_ip`; `cause` interne : `unknown_token`, `expired_token` ou `account_disabled`; `account_id` quand il est connu. Le jeton n'est jamais journalisé |
| `auth.refresh_reuse_detected` | denied | `refresh_token_reused` | `account` + id; `client_ip`. Toute la famille a été révoquée |
| `auth.logout_completed` | success | | `account` + id, acteur `user` + id; `sessions_revoked` (jetons supprimés). Rien n'est émis si le jeton est absent ou inconnu |
| `auth.token_rejected` | denied | `expired`, `invalid`, `revoked` | `access_token`; acteur `user` + id pour `revoked` (compte inconnu ou désactivé). Émis par `/me` : le jeton n'est jamais journalisé |

`client_ip` vient de `X-Forwarded-For` posé par la passerelle, accepté seulement s'il s'agit d'une adresse IP valide (sinon l'adresse de la connexion).

Catalogue cible des prochains tickets d'auth (même règles) :

| Événement | Outcome | Reason |
|---|---|---|
| `auth.login_failed` | denied | `account_locked` (A6, avec `client_ip`) |
| `auth.token_refreshed` | success | |
| `auth.logout` | success | |
| `auth.password_changed` | success | |


Avant l'authentification, l'acteur est inconnu : seul `email_hash` identifie la tentative.

## Tests
`uv run poe test` (unit et integ, couverture ≥ 80 %); `uv run poe test:e2e` sur la pile lancée (`E2E_BASE_URL`, `http://127.0.0.1:8080` par défaut); les scénarios de jetons de service appellent `auth` depuis le conteneur `shop` (réseau `app`, `docker compose exec`) et lisent le secret du client `shop` dans `AUTH_SERVICE_CLIENT_SECRET_SHOP` ou `.env`. Les scénarios d'inscription et de réinitialisation lisent les emails dans Mailpit via `E2E_MAILPIT_URL` (ignorés sans cette variable); `E2E_CHECK_LOGS=1` ajoute le contrôle des journaux des conteneurs (`docker compose logs`, lancé depuis la racine du dépôt) : ni mot de passe, ni jeton, ni adresse. Les scénarios de connexion (`test_login.e2e.py`) créent leur compte par `/register`, vérifient la signature des jetons avec le JWKS publié par la passerelle, les 401 génériques et un temps de réponse comparable; avec `E2E_CHECK_LOGS=1`, ils désactivent un compte par `docker compose exec postgres-auth psql` et contrôlent aussi les journaux (ni jeton d'accès, ni cookie de rafraîchissement, ni clé privée). Les scénarios de rafraîchissement (`test_refresh.e2e.py`) passent le cookie `Secure` à la main (pile en http) et couvrent la rotation, le rejeu, l'en-tête anti-CSRF, la déconnexion idempotente et huit rafraîchissements simultanés avec le même jeton (un seul réussit).
