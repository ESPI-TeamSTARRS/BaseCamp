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
| `observability` | signaux de détection : `RecordRequestUseCase` (une ligne de journal et les compteurs par requête), `RenderMetricsUseCase` (`/metrics`), `CountingEventLogger` (compte chaque événement métier en même temps qu'il le journalise), lecture des verrous actifs en base |
| `login` | connexion et jetons d'accès clients : `LoginAccountUseCase`, `GetCurrentAccountUseCase`, `GetPublicKeysUseCase`, trousseau Ed25519 (`Ed25519KeyRing`, `LazyEd25519KeyRing`), signature et vérification JWT (`JwtAccessTokenSigner`, `JwtAccessTokenVerifier`), vérificateur argon2id avec hachage factice, dépôts SQLAlchemy |

| `admin` | administration des comptes par un opérateur : `ListAccountsUseCase`, `ChangeAccountStatusUseCase` (désactiver, réactiver), `CreateOperatorUseCase` (commande d'exploitation seulement); lit et écrit un sous-ensemble de `users` avec sa propre base SQLAlchemy et supprime les `refresh_tokens` du compte désactivé; réutilise `PasswordPolicy`, le hachage et l'horloge de `registration` |
| `backoffice` | invitation d'un opérateur par lien à usage unique (`CreateOperatorInvitationUseCase`, `CompleteOperatorInvitationUseCase`, `RevokeOperatorInvitationUseCase`) et connexion du back-office en trois temps : `IdentifyOperatorUseCase`, `VerifyFaceUseCase`, `VerifyOperatorPasswordUseCase`, défis à usage unique, port `ReconnaissanceFaciale` (domaine) avec son faux adaptateur de développement, gabarits faciaux des opérateurs; consomme `lockout` et `login` |

Les autres tranches métier (par exemple « déconnecter tous mes appareils ») s'ajoutent à côté; leurs routes se documentent ici. Le câblage de chaque tranche est dans son `composition.py` ou `wiring.py` (seul endroit qui importe l'infrastructure). `login` ne dépend d'aucune autre tranche : elle déclare ses propres modèles sur la table `users` (colonnes lues seulement) avec une base SQLAlchemy distincte; seul `app/login/composition.py` réutilise `Ed25519KeyStore` pour lire le secret de signature monté, afin que jetons clients et jetons de service partagent la même clé et le même `kid`.

## API
| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | liveness : 200 tant que le processus répond |
| GET | `/metrics` | métriques Prometheus, **réseau interne seulement** (voir « Signaux de détection »); 404 derrière un proxy; absente d'OpenAPI |
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
| GET | `/admin/users` | **rôle `operator` requis** : liste paginée `{items: [{id, email, role, email_verified, disabled, created_at}], total, limit, offset}` (`limit` 1 à 100, 50 par défaut; `offset` ≥ 0), jamais de hachage; 401 sans jeton, 403 avec un jeton `customer` |
| POST | `/admin/users/{id}/disable` et `/enable` | **rôle `operator` requis** : désactive (révoque ses jetons de rafraîchissement) ou réactive le compte; renvoie le compte; idempotent; 404 compte inconnu, 409 `cannot_disable_self` ou `cannot_disable_last_operator` |
| POST | `/backoffice/identify` | **origine admin seulement**, monté seulement si `APP_BACKOFFICE_ENABLED` : `{email}` -> **toujours 200** `{challenge_id, expires_in: 120}` (défi à usage unique), que le compte existe ou non |
| POST | `/backoffice/face` | `{challenge_id, images: [1 à 3 images JPEG ou PNG en base64, 1 Mo chacune]}` -> 200 `{face_ok: true}`; visage refusé, défi inconnu, expiré, utilisé ou étape verrouillée : **même 401** « Identifiants invalides. »; image invalide : 422 (ne compte pas); gabarit inexploitable : 409 |
| POST | `/backoffice/password` | `{challenge_id, password}` -> 200 `{access_token, token_type, expires_in}` (jeton `operator` + `amr`, **sans cookie de rafraîchissement**); sans visage accepté au préalable ou mot de passe faux : même 401 |
| POST | `/backoffice/invitation/complete` | **origine admin seulement** : `{token, password, images: [3 à 10 images]}` -> 201 `{created: true}` (compte `operator` et gabarit créés, jeton consommé, en une transaction); jeton inconnu, expiré, utilisé, révoqué ou adresse bloquée : **même 401** « Invitation invalide ou expirée. »; mot de passe faible ou image invalide : 422 (le jeton survit) |
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

### Administration des comptes (rôle `operator`)
- **Création du rôle** : un compte `operator` ne naît que de la commande d'amorçage `create-operator` ou d'une [invitation par lien à usage unique](#invitation-dun-opérateur-par-lien-à-usage-unique-work-67) générée en ligne de commande (aucune route ne l'accorde sans jeton d'invitation). L'inscription publique ne produit jamais que `customer` : un champ `role` dans le corps est refusé (422, `extra="forbid"`). Commande : `docker compose exec -e OPERATOR_PASSWORD=... auth python -m app.admin.create_operator --email ops@example.com`. Le mot de passe est lu dans `OPERATOR_PASSWORD` ou saisi deux fois sans écho; il n'est jamais passé en argument, affiché ni journalisé. Il suit la politique de l'inscription (12 caractères minimum, mots courants refusés), est haché en argon2id, et l'adresse est tenue pour vérifiée. Adresse invalide, mot de passe faible ou adresse déjà prise : code de sortie 1 et message fixe.
- **Accès** : depuis WORK-59, un compte `operator` n'obtient plus ce rôle par `POST /login` : il passe par la [connexion du back-office en trois temps](#connexion-du-back-office-en-trois-temps-backoffice-work-59) (visage puis mot de passe) et son gabarit facial doit être enrôlé (ticket du package de reconnaissance).
- **Garde réutilisable `require_role`** (`app/login/presentation/require_role.py`) : `Depends(require_role("operator"))` sur n'importe quelle route d'administration ou de back-office (un ou plusieurs rôles acceptés). Les rôles sont ceux des **claims du jeton signé**, jamais d'un paramètre ou d'un en-tête du client. En plus, le compte doit exister, être actif et avoir toujours ce rôle en base : un opérateur désactivé ou rétrogradé perd l'accès aussitôt. Sans jeton valide : 401 générique « Authentification requise. »; jeton valide sans le rôle : 403 générique « Accès refusé. » (événement `auth.access_denied`). Le rôle reste une simple valeur de `roles` : aucun modèle de permissions n'est figé.
- **Règles** : un opérateur ne peut pas se désactiver lui-même; le dernier opérateur actif ne peut pas l'être (les opérateurs actifs sont verrouillés en lecture `FOR UPDATE` dans la transaction : deux désactivations simultanées se serialisent). Désactiver supprime les jetons de rafraîchissement; le jeton d'accès déjà émis est refusé tout de suite par `/me` et les routes d'administration, mais reste valide chez `shop` et `payment` jusqu'à son expiration (15 minutes au plus).
- **Journal d'audit** : chaque action produit une ligne (qui = acteur `operator` + id, quoi = nom de l'événement, cible = `resource_id`, quand = horodatage de la ligne), sans adresse en clair ni mot de passe : `auth.accounts_listed`, `auth.account_disabled`, `auth.account_enabled`, `auth.admin_action_refused` (motifs `cannot_disable_self`, `cannot_disable_last_operator`, `account_not_found`) et `auth.operator_created` (acteur `cli`).
- Hors périmètre : interface complète d'administration, permissions fines; ce ticket ne livre pas de page front.

### Connexion (`POST /login`)
- Corps strict (`extra="forbid"`, mot de passe de 256 caractères au plus avant tout hachage). Email normalisé (minuscules, sans espace).
- **Succès** (compte actif, bon mot de passe, email vérifié ou non) : `access_token` (JWT, 15 minutes) dans le corps, jeton de rafraîchissement opaque (256 bits) dans le cookie `refresh_token; HttpOnly; Secure; SameSite=Strict; Path=/api/auth; Max-Age=604800`. Seul le SHA-256 du jeton de rafraîchissement est stocké (`refresh_tokens`). Chaque connexion ouvre une **famille** de jetons (voir « Rafraîchissement et déconnexion »). Réponse en `Cache-Control: no-store`.
- **Anti-énumération** : email inconnu, mauvais mot de passe et compte désactivé donnent la même réponse (statut, corps, en-têtes hors `X-Correlation-ID`) et coûtent chacun **exactement une vérification argon2id** (un hachage factice, calculé au démarrage avec les mêmes paramètres, sert à l'email inconnu; le compte désactivé est vérifié avec le vrai hachage avant d'être refusé). Le motif réel n'existe que dans le journal (`attributes.cause`).
- **Ré-hachage** : après une connexion réussie, si le hachage stocké a été produit avec d'autres paramètres argon2id que ceux en vigueur (`check_needs_rehash`), le mot de passe est ré-haché et remplacé dans la même transaction que le jeton de rafraîchissement.
- Compte « désactivé » : `users.disabled_at` non nul. Il refuse la connexion et invalide aussitôt `/me` (un jeton déjà émis reste valide chez `shop` et `payment` jusqu'à son expiration, 15 minutes au plus).
- **Verrouillage progressif** : voir « Verrouillage progressif » ci-dessous (défaut : 5 échecs en 15 min verrouillent 15 min, puis 30 et 60 min en cas de récidive). La passerelle limite en plus le débit par IP.

### Rafraîchissement et déconnexion (`POST /refresh`, `POST /logout`)
- **Rotation** : le jeton présenté est consommé par un seul `UPDATE ... WHERE used_at IS NULL AND expires_at > now RETURNING` atomique, puis un nouveau jeton (256 bits, durée de 7 jours neuve) est émis dans la même famille avec un nouveau jeton d'accès (15 minutes). L'ancien ne sert plus. Deux rafraîchissements simultanés avec le même jeton : **un seul réussit**, les autres reçoivent 401 (test d'intégration à threads et scénario e2e sur Postgres).
- **Détection de réutilisation** : un jeton déjà consommé qui revient (et non expiré) est un rejeu : **toute la famille est supprimée**, la réponse est 401 et l'événement `auth.refresh_reuse_detected` est journalisé. Conséquence assumée : le perdant d'une course légitime (deux onglets qui rafraîchissent en même temps sans le partager) déconnecte aussi le gagnant; le front limite ce risque avec un seul rafraîchissement à la fois par onglet.
- **Réponse unique** : jeton absent, inconnu, expiré, rejoué, compte désactivé ou disparu donnent le même 401 `{"detail": "Session expirée."}` et efface le cookie (le front ne reboucle pas). Le motif n'existe que dans le journal.
- **Anti-CSRF** : l'en-tête `X-Requested-With` (n'importe quelle valeur non vide) est exigé en plus de `SameSite=Strict`; une requête inter-sites ne peut pas le poser sans pré-vérification CORS, que le service n'autorise pas.
- **Déconnexion** : supprime la famille du jeton présenté (même si ce jeton a déjà été remplacé), efface le cookie, répond 204 dans tous les cas. Le jeton d'accès déjà émis reste valide jusqu'à son expiration (15 minutes au plus). Hors périmètre : « déconnecter tous mes appareils ».
- **Réinitialisation du mot de passe** : elle supprime tous les jetons de rafraîchissement du compte, toutes familles confondues.
- Les lignes antérieures à la rotation n'ont ni famille ni `used_at` : un tel jeton forme sa propre famille et est consommable normalement.

### Verrouillage progressif (tranche `lockout`)
Composant **indépendant de la connexion** (domaine, port `LockoutRepository`, service `LockoutService`), appelable depuis n'importe quelle étape d'un parcours : `check(scope, subject, now)` avant de vérifier, `record_failure(...)` après un échec, `record_success(...)` après un succès. `scope` est un libellé libre (l'étape : `password` aujourd'hui; `identifier` ou `face` pour un futur parcours de connexion en plusieurs temps) et `subject` une empreinte opaque, jamais une adresse. Aucun seuil n'est codé dans la tranche `login`.

- **Politique** (`LockoutPolicy`, lue de la configuration) : `max_failures` échecs dans `window` verrouillent le sujet; la durée suit l'échelle `durations` (1er verrou, 2e en cas de récidive, …) et **la dernière durée est le plafond** : un attaquant ne peut jamais verrouiller plus longtemps. L'échelle est oubliée après `memory` sans nouveau verrou. Exemples : défaut `5 / 15 min / 15-30-60 min`; « un nouvel essai puis 5 minutes » = `APP_LOCKOUT_MAX_FAILURES=2`, `APP_LOCKOUT_DURATIONS_SECONDS=300`.
- **Réponse** : un sujet verrouillé reçoit **exactement la réponse générique 401** (statut, corps, en-têtes, sans `Retry-After` ni cookie), **même avec le bon mot de passe**, et paie la même vérification argon2id. Le verrou est clé sur l'empreinte de l'adresse : une adresse inconnue se verrouille comme une adresse connue (rien ne trahit l'existence d'un compte). Un échec pendant un verrou ne compte pas et ne le prolonge pas; un succès remet le compteur et l'échelle à zéro.
- **Stockage** : table `login_lockouts` (`scope`, `subject`, `failures`, `window_started_at`, `level`, `locked_until`, `updated_at`), donc il survit à un redémarrage et se partage entre instances. Chaque échec s'exécute dans une transaction qui verrouille la ligne du sujet (`SELECT ... FOR UPDATE` après un `INSERT ... ON CONFLICT DO NOTHING`) : des échecs simultanés ne se perdent pas. Les lignes inactives depuis plus de `memory` sont purgées à chaque échec (la table ne grossit pas indéfiniment sous un tir d'adresses inconnues).
- **Journaux** : `auth.lockout_triggered` (une fois, au moment du verrou) et les événements `login` portent l'attribut `step` (étape), sans changer le schéma pour de futures étapes.
#### Politique par étape et par adresse source (WORK-56)
`LockoutService` choisit la règle selon l'**étape** (`step`, nom libre) et le **type de sujet** : `account` (empreinte de l'identifiant) ou `address` (empreinte de l'adresse source, qui a ses propres seuils : un tiers ne peut pas verrouiller un opérateur depuis sa seule adresse sans être bloqué lui-même). Chaque couple (étape, type de sujet) a **son compteur** : un visage refusé ne compte jamais comme un mot de passe faux, et inversement. L'appelant fournit l'empreinte; une adresse bloquée ne dépend d'aucun compte et ne révèle donc rien sur son existence. Une étape non configurée garde la règle progressive d'avant (aucune régression du login client).

| Étape (`step`) | Sujet | Défaut | Variables |
|---|---|---|---|
| `password` (login client, existant) | compte | 5 échecs en 15 min, puis 15, 30, 60 min (palier plafonné, oubli après 24 h) | `APP_LOCKOUT_MAX_FAILURES`, `_WINDOW_SECONDS`, `_DURATIONS_SECONDS`, `_MEMORY_SECONDS` |
| `operator_password` (back-office) | compte | 3 échecs en 10 min, blocage **fixe de 5 min**, sans escalade | `APP_LOCKOUT_OPERATOR_PASSWORD_MAX_FAILURES`, `_WINDOW_SECONDS`, `_DURATION_SECONDS` |
| `face` (back-office) | compte | 5 refus en 10 min, blocage **fixe de 5 min**, sans escalade | `APP_LOCKOUT_FACE_MAX_FAILURES`, `_WINDOW_SECONDS`, `_DURATION_SECONDS` |
| toute étape | adresse source | 20 échecs en 15 min, blocage fixe de 15 min | `APP_LOCKOUT_ADDRESS_MAX_FAILURES`, `_WINDOW_SECONDS`, `_DURATION_SECONDS` |

- **Stockage** : même table `login_lockouts`, aucune migration. La clé `scope` est l'étape seule pour un compte (lignes existantes inchangées) et `étape@address` pour une adresse (par exemple `face@address`); les verrous survivent donc à un redémarrage.
- **Remise à zéro** : `LockoutService.clear([...])` supprime en une transaction les compteurs de la personne et de son adresse une fois la connexion réussie **de bout en bout** (la connexion en trois temps l'appelle à la dernière étape).
- **Journal** : `auth.lockout_triggered` porte `step`, `subject_type` (`account` ou `address`), `subject_hash` (empreinte, jamais l'identifiant) et `client_ip` **tronqué au réseau** (`/24` en IPv4, `/48` en IPv6) quand l'adresse est connue.
- **Métriques** : `auth_lockouts_triggered_total{step}` reste calculé sur `step`; `auth_active_lockouts{step}` lit `scope`, donc les adresses bloquées apparaissent sous `étape@address`.

- **Passerelle** : Traefik répond 429 avec `Retry-After` au-delà du débit par IP réelle (`/login` et `/register` partagent 60/min, rafale de 30; `/password/forgot` 20/min, rafale de 10); `X-Forwarded-For` est ignoré (clé = adresse de connexion); corps > 1 Mio : 413; délais d'expiration vers les services définis. Scénarios `test_zy_lockout.e2e.py` et `test_zz_gateway_protection.e2e.py` (placés en dernier : ils consomment le seuil par IP de la passerelle) (429, en-tête forgé, 413, 200 tentatives parallèles avec `/health` à 200 et p95 < 200 ms).

### Connexion du back-office en trois temps (`/backoffice/*`, WORK-59)
Parcours : **identifiant, visage, mot de passe**. Un mot de passe volé ne suffit plus, et c'est la **seule** porte qui délivre le rôle `operator`.

1. `POST /backoffice/identify {email}` : répond **toujours 200** avec un défi à usage unique (`challenge_id` opaque de 256 bits, 2 minutes). Un identifiant inconnu, un compte client ou désactivé reçoit un défi **leurre**, indiscernable (même forme, même durée, même travail en base, test de temps) : son visage sera refusé comme un visage faux.
2. `POST /backoffice/face {challenge_id, images}` : appelle le port `ReconnaissanceFaciale.verifier(capture, gabarit)`. Visage reconnu (l'une des images suffit) : le défi est remis avec `face_ok`. Visage refusé, défi inconnu, expiré ou déjà utilisé, étape verrouillée : **défi détruit** et même 401 générique. Une image hors limites ou illisible (`ImageInvalide`) donne un 422 et **ne compte pas** (le défi survit); un gabarit inexploitable (`GabaritInvalide`) donne un 409, journalisé, et ne compte pas.
3. `POST /backoffice/password {challenge_id, password}` : refusé sans défi `face_ok`, **même avec le bon mot de passe** (et sans compter comme un mot de passe faux). Mot de passe faux : défi détruit, échec compté. Succès : tous les compteurs de la personne et de son adresse sont remis à zéro en une transaction (`LockoutService.clear`) et le jeton est émis.

- **Verrouillage** par étape, via le composant [lockout](#politique-par-étape-et-par-adresse-source-work-56) : `face` (5 refus) et `operator_password` (3 échecs), blocage fixe de 5 minutes, par compte **et** par adresse source (20). Les compteurs sont séparés : un visage refusé ne compte jamais comme un mot de passe faux. Un identifiant inconnu compte comme un visage refusé.
- **Jeton émis** : JWT client habituel (`token_use` = `client`, JWKS inchangé) avec `roles=["operator"]` et la claim **`amr=["face","pwd"]`** (RFC 8176). `shop` (garde admin) exige `operator` dans `roles` ET `face` dans `amr`. Le **login classique** (`POST /login`) ne délivre plus **ni `operator` ni `amr`** (un compte opérateur y obtient `roles=[]`) : la garde est dans l'émission des jetons (`AccessTokenClaims.issue`). **Pas de jeton de rafraîchissement** pour le back-office : une session dure la vie du jeton d'accès (15 minutes), puis il faut repasser le visage.
- **Images** : 1 à 3, JPEG ou PNG (contrôlés sur la signature des octets), 1 Mo chacune, traitées en mémoire, jamais écrites sur disque ni journalisées.
- **Port `ReconnaissanceFaciale`** (`backoffice/domain/interfaces/reconnaissance_faciale.py`, interface de la team IA) : `enroler(photos) -> bytes` (gabarit de 2 069 octets) et `verifier(capture, gabarit) -> bool` (jamais le score). Le port est dans le **domaine** (pas dans `application/ports`) pour que la règle de dépendance vérifiée par le test d'architecture reste vraie : l'adaptateur d'infrastructure l'implémente. Le **faux adaptateur** (`FakeReconnaissanceFaciale`) ne reconnaît que la même image : tests et développement seulement.
- **Démarrage** : les routes ne sont montées que si `APP_BACKOFFICE_ENABLED=true`. Activé, il faut un vérificateur : `APP_FACE_VERIFIER=fake` n'est accepté qu'avec `APP_ENVIRONMENT` à `dev` ou `local`; sinon (`none`) le service **refuse de démarrer**. Tant que l'adaptateur réel n'est pas branché (ticket du package), la production garde `APP_BACKOFFICE_ENABLED` éteint.
- **Stockage** (migration `0010_connexion_backoffice`, tables nouvelles seulement) : `backoffice_challenges` (`digest` SHA-256 de l'identifiant, jamais l'identifiant, `account_id` nul pour un leurre, `email_hash`, `address_hash`, `expires_at`, `face_ok`) et `operator_face_templates` (`account_id`, `template`, `updated_at`; donnée biométrique, jamais journalisée). Le défi est retiré par un seul `DELETE ... RETURNING` : deux requêtes simultanées ne le reçoivent pas toutes les deux.
- **Passerelle** : ces routes ne sont servies **que sur l'origine admin** (`admin.<domaine>`, routeur `auth-backoffice`, limiteur strict `backoffice-login-rate-limit` en production (10 requêtes/min par IP, rafale de 5; large en développement pour les e2e), corps jusqu'à 5 Mio pour 3 images en base64); sur le domaine principal, `/api/auth/backoffice` n'existe pas (404).
- **Journal** : `auth.backoffice_identify`, `auth.backoffice_face_result`, `auth.backoffice_password_result` (success ou denied, motif `invalid_challenge`, `face_refused`, `face_required`, `wrong_password`, `step_locked`, `invalid_template`) et `auth.backoffice_lockout`; attributs `step`, `email_hash` (empreinte), `cause`; `client_ip` sur les refus. Jamais d'image, de gabarit, d'identifiant de défi, de mot de passe ni d'email en clair; le port ne renvoie aucun score.

### Invitation d'un opérateur par lien à usage unique (WORK-67)
Une personne devient opérateur **sans que son mot de passe ni son visage transitent par l'administrateur** : un administrateur IT génère un lien en ligne de commande, la personne y choisit son mot de passe et enregistre son visage, le tout dans **une seule transaction**. `create-operator` reste la commande d'amorçage du premier compte.

- **Création du lien** : `python -m app.backoffice.create_operator_invite --email <adresse>` (pile Docker : `docker compose exec -T auth python -m app.backoffice.create_operator_invite --email ops@example.com`), réservée à un administrateur IT avec accès à la VM : **aucune route** ne crée d'invitation. La commande affiche **un seul lien** `<APP_ADMIN_BASE_URL>/invitation#token=<jeton>` et l'heure d'expiration. Le jeton (256 bits aléatoires, dans le fragment : la navigation ne l'envoie pas au serveur et aucun journal d'accès ne le contient) n'est **ni envoyé par email, ni passé par n8n** : l'administrateur le remet lui-même. Seule l'**empreinte SHA-256** est stockée : le lien ne se retrouve plus après l'affichage. Adresse invalide ou compte déjà existant : code de sortie 1, message fixe. Créer une nouvelle invitation **révoque** les précédentes de la même adresse.
- **Propriétés du jeton** : lié à l'adresse invitée, **5 minutes au plus** (`APP_OPERATOR_INVITE_TTL_SECONDS`, 300 au maximum : une valeur plus grande est refusée au démarrage), **usage unique** (consommé dans la transaction de création du compte), révocable : `python -m app.backoffice.revoke_operator_invite --email <adresse>` (affiche le nombre d'invitations révoquées).
- **Route** `POST /backoffice/invitation/complete {token, password, images}` (**origine admin seulement**, montée avec le back-office; passerelle : `/api/auth/backoffice/invitation/complete`) : 201 `{created: true}` (`Cache-Control: no-store`, aucun jeton de session : la personne se connecte ensuite en [trois temps](#connexion-du-back-office-en-trois-temps-backoffice-work-59)).
  1. Verrou de l'adresse source (étape `invitation`) puis recherche du jeton. Jeton **inconnu, expiré, déjà utilisé ou révoqué**, ou adresse verrouillée : **même 401** « Invitation invalide ou expirée. », compté comme un échec.
  2. Mot de passe selon la politique de l'inscription (12 caractères minimum, 128 au plus, mots courants refusés), haché en argon2id : refus 422 (`password_too_short`, `password_too_long`, `password_too_common`).
  3. **3 à 10 images** JPEG ou PNG de 1 Mo au plus (signature des octets), en mémoire seulement; le gabarit facial est calculé **avant** d'ouvrir la transaction (le calcul n'y bloque pas la base). Hors limites : 422 `photo_count` ou `invalid_photo`; aucun visage : 422 `no_face`.
  4. **Une seule transaction** : prise du jeton (`SELECT ... FOR UPDATE`), création du compte `operator` (adresse tenue pour vérifiée), gabarit chiffré (AES-256-GCM lié au compte), jeton consommé. Tout ou rien : une panne en cours de route ne laisse ni compte sans visage, ni jeton consommé sans compte. Si un compte existe déjà pour l'adresse (créé entre-temps), c'est le même 401 générique.
- **Un échec d'enrôlement n'est pas une tentative de connexion** : mot de passe faible, photos hors limites, visage absent ou panne n'ont **aucun effet** sur les compteurs de verrouillage ni sur le jeton, qui reste utilisable jusqu'à son expiration. Seuls les jetons invalides comptent.
- **Verrouillage** (composant [lockout](#politique-par-étape-et-par-adresse-source-work-56)) : étape `invitation` **par adresse source** uniquement (le jeton n'identifie personne) : 5 échecs en 10 minutes, blocage fixe de 5 minutes (`APP_LOCKOUT_INVITATION_*`). Pendant le blocage, même le bon jeton est refusé; un succès remet le compteur de l'adresse à zéro.
- **Passerelle** : routeur `auth-backoffice-invitation` (origine admin seulement, priorité supérieure à `auth-backoffice`, même limiteur par adresse que la connexion) avec un corps jusqu'à **15 Mio** (`backoffice-invitation-body-limit` : dix images de 1 Mo en base64 tiennent en environ 14 Mo; 413 au-delà). Sur le domaine principal, la route n'existe pas (404).
- **Stockage** (migration `0011_invitations_operateur`, table nouvelle seulement) : `operator_invitations` (`digest` clé primaire, `email`, `created_at`, `expires_at`, `consumed_at`, `revoked_at`; index sur `email` et `expires_at`). Les invitations expirées depuis plus d'un jour sont purgées à la création suivante.
- **Journal** : `auth.operator_invite_created`, `auth.operator_invite_consumed`, `auth.operator_invite_revoked` (nombre d'invitations révoquées) et `auth.operator_invite_refused` (motifs `invalid_token`, `step_locked`, `weak_password`, `photo_count`, `invalid_photo`, `no_face`, `account_exists`, `invalid_email`; `client_ip` sur la route publique). L'adresse n'apparaît que sous forme d'empreinte (`email_hash`); jamais le jeton, une image, un gabarit ni un mot de passe. Acteur `cli` pour les commandes.

### Vérificateur réel, enrôlement et gabarits (WORK-63)
- **Adaptateur** : `VisageIdReconnaissance` (`backoffice/infrastructure/clients/visage_id_reconnaissance.py`) est le **seul** fichier qui importe le package `visage-id` de la team IA (dépôt public `ESPI-TeamSTARRS/ML-Reco`). Il implémente le port `ReconnaissanceFaciale`, crée **un seul** `Reconnaisseur` par processus (modèles ONNX embarqués dans le package, **aucun téléchargement à l'exécution**; échec de démarrage si les modèles manquent), traduit les erreurs du package (`ImageInvalide`, `AucunVisage`, `GabaritInvalide`) vers celles du domaine et ne laisse jamais sortir le score (booléen seulement). Les routes qui l'appellent sont synchrones (`def`) : un verrou interne du package sérialise les calculs (environ 26 ms par vérification, 110 Mo par processus).
- **Activation** : `APP_FACE_VERIFIER=visage-id` (production) ou `fake` (développement seulement). Le **seuil** de décision est `APP_FACE_THRESHOLD` (défaut `0.23`, valeur de la team IA mesurée sur le jeu public LFW : environ 0,1 % de faux accepts; **à recalibrer avec de vraies photos**, un seuil plus haut refuse davantage, un seuil plus bas accepte davantage). Tout changement du modèle du package rend les gabarits invalides (409) : réenrôler.
- **Test de contrat** commun (`test_reconnaissance_contract.integ.py`) : passé par le faux en permanence, et par l'adaptateur réel quand le package est installé et que `FACE_CONTRACT_PHOTOS` désigne un dossier de vraies photos de coéquipiers consentants (`personne_a/` : 4 photos ou plus, `personne_b/` : 1 photo ou plus), **jamais dans le dépôt**.
- **Enrôlement** : commande d'exploitation `python -m app.backoffice.enroll_face --email <adresse> --images <photo> <photo> <photo> ...` (3 à 10 photos JPEG ou PNG de 1 Mo au plus, variées : de face, léger tour de tête, expression), lues **uniquement dans le dossier des photos** (`--directory`, `/photos` par défaut; un nom qui en sort, par `..`, chemin absolu ailleurs ou lien symbolique, est refusé). Les photos sont lues en mémoire seulement : jamais copiées, écrites sur disque ni journalisées; seul le **gabarit** (2 069 octets) est conservé, **chiffré**. Compte inconnu, client ou désactivé, nombre de photos hors limites, photo illisible ou sans visage : refus à message fixe (code de sortie 1). Réenrôler remplace le gabarit. **Sans gabarit, la connexion du back-office est refusée.** Exemple (pile Docker, photos montées en lecture seule) : `docker compose run --rm --no-deps -v ./photos:/photos:ro auth python -m app.backoffice.enroll_face --email ops@example.com --images /photos/1.jpg /photos/2.jpg /photos/3.jpg`.
- **Chiffrement au repos** : AES-256-GCM (`AesGcmTemplateCipher`), format `version | nonce | chiffre + étiquette`, l'identifiant du compte est une donnée authentifiée (un gabarit recopié sur un autre compte ne se déchiffre pas). La clé (32 octets en base64) est le **secret monté** `auth_face_template_key` (`APP_FACE_TEMPLATE_KEY_FILE`, défaut `/run/secrets/auth_face_template_key`), hors dépôt; en développement `scripts/init-auth-keys.sh` la génère (`.secrets/auth/face-template.key`, jamais régénérée sans `--force`, sinon les gabarits existants ne se déchiffrent plus). Clé absente ou invalide : le service **refuse de démarrer** quand le back-office est activé. Un gabarit qui ne se déchiffre pas est traité comme un gabarit invalide (409, journalisé).
- **Désactivation** : désactiver un compte (`POST /admin/users/{id}/disable`) **supprime son gabarit** (donnée biométrique; événement `auth.account_disabled` avec `face_template_deleted`). Réactiver ne le rend pas : il faut réenrôler.
- **Journal** : `auth.backoffice_face_enrolled` (`email_hash`, `photos`) et `auth.backoffice_face_enrollment_refused` (motifs `unknown_operator`, `photo_count`, `invalid_photo`, `no_face`).
- **Image** : `visage-id` est une dépendance du seul service `auth`, **épinglée à un commit** du dépôt public de la team IA (`pyproject.toml` et `uv.lock`; aucun tag n'existe) : mettre à jour = changer le commit, relancer `uv lock`, rejouer le test de contrat. `git` n'est installé que dans l'étage de build du `Dockerfile`, jamais dans l'image finale; les deux modèles ONNX (environ 14 Mo) sont dans le package, **aucun téléchargement à l'exécution** (vérifié en conteneur `--read-only --network none`, utilisateur non privilégié). Mesures (Python 3.13, Linux, CPU) : image **235 Mo -> 481 Mo** (opencv-python-headless 74 Mo, numpy 43 Mo, package 14 Mo, pillow et dépendances), chargement des modèles environ 0,15 s au démarrage, enrôlement de 3 photos environ 0,1 s, vérification environ 20 ms; Trivy (HIGH et CRITICAL corrigeables) : 0 sur l'image; `pip-audit` ne peut pas auditer `visage-id` (hors PyPI) mais audite numpy, opencv et pillow.
- **Limites connues** : pas de détection de vivacité (une photo ou une vidéo de l'opérateur peut passer); poids ArcFace d'InsightFace **réservés à la recherche non commerciale** (`NOTICE.md` du package; repli SFace, Apache 2.0, environ 0,2 point de précision en moins) : acceptable pour un projet scolaire, à lever avant tout usage commercial de l'image publiée sur GHCR.

### Adresse réelle du client (`APP_TRUSTED_PROXIES`)
Le compteur par adresse source et les journaux lisent `ClientAddressResolver`. L'adresse du **pair TCP** est la seule donnée sûre; `X-Forwarded-For` n'est lu que si le pair est un proxy de confiance (plages CIDR de `APP_TRUSTED_PROXIES`, vide par défaut = personne). La liste est alors parcourue de **droite à gauche** en sautant les proxys de confiance : la première adresse restante est le client, jamais une adresse posée à gauche par le client. `CF-Connecting-IP` n'est pas lu (forgeable sans passer par Cloudflare). En développement, Traefik écrase `X-Forwarded-For` par l'adresse qu'il voit et le compose fait confiance aux réseaux Docker; en production, `X-Forwarded-For` vaut « client, Cloudflare, proxy Docker » : les plages Docker et Cloudflare (publiques, à tenir à jour avec `deploy/traefik/dynamic.prod.yml`) sont de confiance.

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

Premier consommateur : `shop` (WORK-40) vérifie ainsi les jetons des clients connectés (cache de 5 minutes, relecture sur `kid` inconnu au plus toutes les 10 s, clés conservées si `auth` est arrêté) et lit `GET /me` avec le jeton du client pour obtenir l'adresse et sa vérification avant de rattacher des commandes invitées.

### Rotation des clés de signature
Les jetons de l'ancienne clé restent valides jusqu'à leur expiration (test d'intégration dédié) :
1. `sh scripts/init-auth-keys.sh --force` génère une nouvelle paire et **conserve l'ancienne clé publique** dans `.secrets/auth/previous/`.
2. Monter ce dossier dans le conteneur `auth` et définir `APP_JWT_PREVIOUS_PUBLIC_KEYS_DIR` : le JWKS publie alors les deux clés (courante en premier) et `auth` vérifie les jetons clients des deux, mais signe avec la nouvelle seule. Les jetons de service (5 minutes) ne sont vérifiés qu'avec la clé courante : redémarrer après la rotation suffit.
3. Après 15 minutes (durée d'un jeton d'accès) plus la durée de cache du JWKS, retirer l'ancienne clé publique.

## Tables
Migrations `0004_users_et_verification` (down_revision `0003`), `0006_reinitialisation_mot_de_passe` (down_revision `0004`) puis `0007_login` (down_revision `0006`), `0009_login_lockouts` (down_revision `0008`, table nouvelle, rien de modifié) et `0008_refresh_rotation` (down_revision `0007`, deux colonnes nullables et un index, rien de supprimé ni renommé : l'ancienne version continue de fonctionner). La 0006 est additive : trois tables, rien de modifié ni supprimé. La 0007 l'est aussi (expand/contract) : une colonne nullable et une table, rien n'est supprimé ni renommé.

| Table | Colonnes |
|---|---|
| `users` | `id` (uuid, clé primaire), `email` (unique, minuscules), `password_hash`, `role` (`customer` ou `operator`), `email_verified_at` (nullable), `created_at`, `disabled_at` (nullable, ajouté par la 0007 : compte désactivé) |
| `email_verification_tokens` | `id`, `user_id` (clé étrangère, suppression en cascade), `token_hash` (SHA-256 hex, unique), `expires_at`, `used_at` (nullable) |
| `password_reset_tokens` | `id`, `user_id` (clé étrangère, suppression en cascade), `token_hash` (SHA-256 hex, unique), `expires_at`, `used_at` (nullable) |
| `password_reset_attempts` | `id`, `email_fingerprint` (HMAC de l'adresse, indexé), `requested_at` (indexé); purgée à chaque demande au-delà de la fenêtre d'une heure |
| `session_revocations` | **plus utilisée** (WORK-36 l'écrivait, la révocation passe désormais par la suppression des `refresh_tokens`); conservée par la migration 0006 le temps de l'ancienne version, une migration *contract* ultérieure la supprimera |
| `refresh_tokens` | `id`, `user_id` (clé étrangère, suppression en cascade, indexé), `token_hash` (SHA-256 hex, unique), `created_at`, `expires_at` (0007), `family_id` (uuid nullable, indexé : connexion d'origine; nul = sa propre famille) et `used_at` (nullable : consommé par un rafraîchissement) (0008) |
| `backoffice_challenges` | `digest` (clé primaire, SHA-256 de l'identifiant du défi), `account_id` (uuid nullable, clé étrangère `users`, nul pour un défi leurre), `email_hash`, `address_hash` (empreintes HMAC), `expires_at` (indexé), `face_ok` (migration `0010`) |
| `operator_face_templates` | `account_id` (clé primaire et étrangère `users`, suppression en cascade), `template` (gabarit biométrique sérialisé), `updated_at` (migration `0010`) |
| `operator_invitations` | `digest` (clé primaire, SHA-256 du jeton; le jeton n'est jamais stocké), `email`, `created_at`, `expires_at` (indexé), `consumed_at`, `revoked_at` (migration `0011`) |

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

Scopes connus (tous d'audience `payment`) : `payments:write` (créer, lire, confirmer, annuler un paiement) et `refunds:write` (rembourser; **jamais accordé à `shop`**, réservé à un futur appelant de confiance). Ajouter un scope ou une audience se fait dans `app/service_token/domain/enums/`.

### Côté appelant (contrat pour `payment`, ticket A10)
1. Demander un jeton avec l'`audience` et le `scope` nécessaires; **le mettre en cache jusqu'à environ 30 s avant `exp`**, puis en redemander un (ne pas en redemander à chaque appel : la limitation de débit s'applique).
2. L'envoyer en `Authorization: Bearer <jeton>`.
3. Côté récepteur, accepter uniquement si : la signature EdDSA est valide (algorithme `EdDSA` seul, jamais `none` ni HMAC) avec la clé publique d'`auth`; `iss = basecamp-auth`; `exp` dans le futur; `aud` = le service récepteur; `token_use = service`; `scope` contient le scope requis par la route.
4. Clé publique : `GET /.well-known/jwks.json` (JWKS, clés OKP Ed25519 avec leur `kid`, réseau interne) ou le secret Docker `auth_jwt_public_key` monté dans le conteneur récepteur. Rafraîchir le JWKS si le `kid` d'un jeton est inconnu.
5. Un jeton de service n'est jamais accepté là où un jeton client est attendu, et inversement : `aud` et `token_use` sont contrôlés par `VerifyTokenUseCase` (`token_use` attendu fixé par le déploiement), ce que prouvent des tests avec un jeton forgé signé par la même clé.

`payment` applique ce contrat (WORK-41) : plus aucun jeton statique, `shop` obtient son jeton de service auprès d'`auth` (voir [payment](payment.md#authentification)). Pour lire le JWKS, `auth` est aussi sur le réseau interne `payment-net` (en plus de `app`), sans autre accès à `payment`.

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
- Séparation des rôles : un client n'accède jamais aux routes opérateur (`require_role`, rôle lu dans le jeton signé).

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
| `APP_TRUSTED_PROXIES` | plages CIDR (virgules) des proxys dont on croit `X-Forwarded-For` (défaut vide : adresse du pair seule); compose : `AUTH_TRUSTED_PROXIES` |
| `APP_BACKOFFICE_ENABLED`, `APP_FACE_VERIFIER`, `APP_BACKOFFICE_CHALLENGE_TTL_SECONDS` | connexion du back-office : activation (défaut `false`), vérificateur de visage (`none` par défaut, `fake` en `dev`/`local` seulement, `visage-id` = package de la team IA; sans vérificateur, démarrage refusé si activé), durée du défi (défaut 120) |
| `APP_ADMIN_BASE_URL`, `APP_OPERATOR_INVITE_TTL_SECONDS` | origine du lien d'invitation affiché par `create-operator-invite` (défaut `http://admin.localhost:8080`; compose : `ADMIN_BASE_URL`, en production `https://admin.<domaine>`) et sa durée (défaut et maximum 300 secondes); voir [Invitation d'un opérateur](#invitation-dun-opérateur-par-lien-à-usage-unique-work-67) |
| `APP_FACE_THRESHOLD`, `APP_FACE_TEMPLATE_KEY_FILE` | seuil de décision du vérificateur réel (défaut `0.23`, entre 0 et 1 exclus) et chemin de la clé AES-256 des gabarits (secret monté); voir [Vérificateur réel, enrôlement et gabarits](#vérificateur-réel-enrôlement-et-gabarits-work-63) |
| `APP_LOCKOUT_MAX_FAILURES`, `APP_LOCKOUT_WINDOW_SECONDS` | échecs qui verrouillent et fenêtre de comptage (défaut 5 et 900) |
| `APP_LOCKOUT_OPERATOR_PASSWORD_*`, `APP_LOCKOUT_FACE_*`, `APP_LOCKOUT_INVITATION_*`, `APP_LOCKOUT_ADDRESS_*` | seuil (`MAX_FAILURES`), fenêtre (`WINDOW_SECONDS`) et durée fixe (`DURATION_SECONDS`) des étapes du back-office et des adresses sources (voir [Politique par étape](#politique-par-étape-et-par-adresse-source-work-56)) |
| `APP_LOCKOUT_DURATIONS_SECONDS` | échelle des durées de verrou en secondes, séparées par des virgules; la dernière est le plafond (défaut `900,1800,3600`) |
| `APP_LOCKOUT_MEMORY_SECONDS` | durée sans verrou après laquelle l'échelle repart du premier palier (défaut 86400) |
| `APP_SERVICE_TOKEN_RATE_LIMIT_PER_MINUTE` | demandes de jeton par client et par minute (défaut 60) |
| `APP_SERVICE_CLIENTS`, `APP_SERVICE_CLIENT_SECRET_<CLIENT>[_PREVIOUS]` | lus par la commande d'amorçage uniquement |
| `APP_LOG_PSEUDONYM_KEY` | clé HMAC des empreintes d'email dans les logs; obligatoire hors `dev` et `local` |
| `APP_SMTP_HOST`, `APP_SMTP_PORT` | serveur SMTP (défaut `localhost:1025`; en compose : `mailpit:1025`) |
| `APP_SMTP_FROM` | expéditeur des emails (défaut `comptes@basecamp.local`) |
| `APP_SMTP_USERNAME`, `APP_SMTP_PASSWORD` | authentification SMTP facultative (le mot de passe est un `SecretStr`, jamais journalisé ni versionné) |
| `APP_SMTP_STARTTLS` | active STARTTLS (défaut `false`, à activer avec un relais réel) |
| `APP_SMTP_TIMEOUT_SECONDS` | délai de connexion SMTP (défaut 5) |
| `APP_MAIL_TRANSPORT`, `APP_N8N_MAIL_URL`, `APP_N8N_MAIL_SECRET`, `APP_N8N_MAIL_TIMEOUT_SECONDS` | transport des emails `smtp` (défaut) ou `n8n` (webhook : URL et secret obligatoires, délai 5 s par défaut); voir [Transport des emails](#transport-des-emails-smtp-ou-n8n-work-65) |
| `APP_PUBLIC_BASE_URL` | origine publique du site, base des liens des emails (défaut `http://localhost:8080`) |

Côté compose : `AUTH_DB_NAME`, `AUTH_DB_USER`, `AUTH_DB_PASSWORD`, `AUTH_SMTP_FROM`, `NEXT_PUBLIC_SITE_URL` (voir `.env.example`).

## Emails et Mailpit
En local et en CI, le service `mailpit` (réseau interne `app`, SMTP 1025, interface et API 8025) reçoit tous les emails d'`auth`. Il n'est ni publié ni routé par la passerelle. Pour le lire depuis l'hôte (scénarios e2e, vérification manuelle), ajouter la surcharge `docker-compose.e2e.yml`, qui le publie sur `127.0.0.1:${MAILPIT_PORT:-8025}` :

```bash
docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d --build --wait traefik mailpit
```

### Transport des emails : SMTP ou n8n (WORK-65)
Les mailers (`EmailRegistrationMailer`, `EmailPasswordResetMailer`) écrivent un texte brut et le passent au port `EmailSender`; `APP_MAIL_TRANSPORT` choisit l'adaptateur (`EmailSenderFactory`) :
- `smtp` (défaut, Mailpit en développement et en CI) : `SmtpEmailSender`, texte brut.
- `n8n` (production, pas de relais SMTP) : `N8nEmailSender` envoie `POST {to, subject, body}` à `APP_N8N_MAIL_URL` (`body` en **HTML** : texte échappé, liens `http(s)` cliquables, paragraphes) avec l'en-tête `X-Mail-Secret` (`APP_N8N_MAIL_SECRET`, jamais versionné ni journalisé, `SecretStr`). Réponse attendue `{"ok": true}`; `403` sans le bon secret. Délai `APP_N8N_MAIL_TIMEOUT_SECONDS` (5 par défaut). Les redirections ne sont pas suivies (le secret ne part jamais ailleurs). URL et secret sont **obligatoires** avec `n8n` (démarrage refusé sinon). L'expéditeur est fixé côté n8n. n8n voit les liens à usage unique en clair (accepté).
- **Un échec n'annule jamais l'action** : l'envoi se fait après la réponse; refus (`http_401`, `http_403`), délai (`timeout`), connexion (`connection_error`), réponse invalide ou transport non configuré donnent le même événement `auth.email_delivery_failed` avec un motif fermé `cause` (`smtp_error`, `timeout`, `connection_error`, `http_<code>`, `invalid_response`, `not_configured`), **jamais** d'adresse, de lien ni de secret. Pas de file d'attente ni de réessai durable (hors périmètre).
- Variables de compose et de `.env` communes avec `shop` : `MAIL_TRANSPORT`, `N8N_MAIL_URL`, `N8N_MAIL_SECRET` (voir le [runbook](../deployment/runbook.md)).

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
| `auth.login_succeeded` | success | | `account` + id, acteur `user` + id; `email_hash`, `hash_upgraded` (le hachage a été ré-haché), `step` |
| `auth.login_failed` | denied | `invalid_credentials` | `account` (+ id si le compte existe); `client_ip`; `email_hash`; `cause` interne : `unknown_account`, `wrong_password`, `account_disabled` ou `account_locked`; `step` |
| `auth.token_refreshed` | success | | `account` + id, acteur `user` + id; `client_ip` |
| `auth.refresh_rejected` | denied | `invalid_refresh_token` | `refresh_token`; `client_ip`; `cause` interne : `unknown_token`, `expired_token` ou `account_disabled`; `account_id` quand il est connu. Le jeton n'est jamais journalisé |
| `auth.refresh_reuse_detected` | denied | `refresh_token_reused` | `account` + id; `client_ip`. Toute la famille a été révoquée |
| `auth.logout_completed` | success | | `account` + id, acteur `user` + id; `sessions_revoked` (jetons supprimés). Rien n'est émis si le jeton est absent ou inconnu |
| `auth.lockout_triggered` | denied | `too_many_failures` | `lockout_subject`; `step`, `subject_type` (`account` ou `address`), `subject_hash` (empreinte), `level` (rang du verrou), `locked_seconds`; `client_ip` tronqué au réseau si connu. Émis une fois, quand le verrou se pose |
| `auth.token_rejected` | denied | `expired`, `invalid`, `revoked` | `access_token`; acteur `user` + id pour `revoked` (compte inconnu ou désactivé). Émis par `/me` : le jeton n'est jamais journalisé |

`client_ip` vient de `X-Forwarded-For` posé par la passerelle, accepté seulement s'il s'agit d'une adresse IP valide (sinon l'adresse de la connexion).

La tranche `admin` et la garde `require_role` émettent :

| Événement | Outcome | Reason | Ressource et attributs |
|---|---|---|---|
| `auth.accounts_listed` | success | | acteur `operator` + id; `limit`, `offset`, `returned`; `client_ip` |
| `auth.account_disabled` | success | | cible `account` + id, acteur `operator` + id; `sessions_revoked`, `already_disabled` |
| `auth.account_enabled` | success | | cible `account` + id, acteur `operator` + id; `already_enabled` |
| `auth.admin_action_refused` | denied | `cannot_disable_self`, `cannot_disable_last_operator`, `account_not_found` | cible `account` + id, acteur `operator` + id |
| `auth.operator_created` | success ou denied | `weak_password` (attribut `rule`), `operator_exists` | cible `account` + id (succès), acteur `cli` |
| `auth.access_denied` | denied | `role_required` | acteur `user` + id; `required` (rôles exigés) |

Avant l'authentification, l'acteur est inconnu : seul `email_hash` identifie la tentative.

## Signaux de détection
Les autres équipes (remédiation, détection) lisent deux sources, sans rien configurer côté `auth` : le **journal JSON** (sortie standard) et `GET /metrics`. Collecte, agrégation et tableaux de bord sont hors périmètre.

### Journal
- Une ligne JSON par événement métier (schéma commun `docs/development/log-event.schema.json`) **et une ligne par requête terminée** : `service.request_completed` avec `attributes.route` (le **gabarit** de la route, par exemple `/admin/users/{account_id}/disable`, jamais le chemin réel), `attributes.method`, `attributes.status`, `duration_ms`, `outcome` (`success` sous 400, `denied` en 4xx, `error` en 5xx) et `reason` `http_<statut>` hors succès. Les sondes réussies (`/health`, `/health/ready`, `/metrics`) sont comptées mais pas journalisées.
- **`request_id`** : c'est le `correlation_id` de chaque ligne, repris de `X-Correlation-ID` (s'il est valide) ou généré, et renvoyé dans la réponse; il relie la ligne de requête et les événements qu'elle a produits.
- Ni adresse email (seulement `email_hash`, HMAC), ni mot de passe, ni jeton, ni cookie, ni secret, ni clé : le test `test_audit_log.integ.py` rejoue connexion, échec, rafraîchissement, réinitialisation et jeton de service puis cherche ces valeurs dans toute la sortie et dans `/metrics`.

Événements demandés par le ticket et leur nom publié (les noms déjà publiés ne sont pas renommés) :

| Signal attendu | Événement publié | Motif / attributs utiles |
|---|---|---|
| `login_succeeded` | `auth.login_succeeded` | `step` |
| `login_failed` | `auth.login_failed` (denied) | `cause` : `unknown_account`, `wrong_password`, `account_disabled`, `account_locked`; `step`; `client_ip` |
| `account_locked` | `auth.lockout_triggered` (denied, `too_many_failures`) | `step`, `level`, `locked_seconds`; un essai pendant le verrou donne `auth.login_failed` avec `cause=account_locked` |
| `refresh_reuse_detected` | `auth.refresh_reuse_detected` (denied) | acteur : compte; la famille entière est révoquée |
| `password_reset_requested` / `password_reset_completed` | `auth.password_reset_requested` / `auth.password_reset_completed` | `sessions_revoked` à la fin |
| `service_token_issued` / `service_token_denied` | `auth.service_token_issued` / `auth.service_token_denied` | `resource_id` : client; motif fermé; `auth.service_rate_limited` en plus |
| `admin_action` | `auth.account_disabled`, `auth.account_enabled`, `auth.accounts_listed`, `auth.admin_action_refused`, `auth.operator_created` | acteur (qui), cible (quoi), horodatage (quand) |

### `GET /metrics`
Format texte Prometheus 0.0.4, pour un collecteur placé sur le réseau interne (`http://auth:8000/metrics`). **Aucune authentification, aucune exposition publique** :
- Traefik exclut `/api/auth/metrics` du routeur `auth` (`infra/traefik/dynamic.yml` et `deploy/traefik/dynamic.prod.yml`, comme `/api/auth/internal`); le test `test_metrics_isolation.unit.py` fige cette règle et `test_metrics.e2e.py` vérifie sur la pile que la passerelle ne sert rien.
- Défense en profondeur : une demande qui porte un en-tête de proxy (`X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `Forwarded`, `X-Real-Ip`) reçoit 404 et journalise `service.metrics_refused`.

Les libellés sont une **liste fermée** : `route` (gabarit ou `unmatched`), `method` (liste fermée, sinon `OTHER`), `status`, `le`, `event`, `outcome`, `reason`, `cause`, `step`, `result` (`success`, `denied` ou `error`), `client` (client de service **connu** de la configuration, sinon `unknown` : un identifiant saisi par un attaquant ne devient jamais un libellé).

| Série | Type | Libellés | Origine |
|---|---|---|---|
| `auth_http_requests_total` | counter | `route`, `method`, `status` | processus |
| `auth_http_request_duration_seconds` | histogram | `route`, `method` (+ `le`) | processus; seaux 5 ms à 10 s |
| `auth_events_total` | counter | `event`, `outcome`, `reason` | processus : les mêmes événements que le journal |
| `auth_login_failures_total` | counter | `cause` | processus (`auth.login_failed`) |
| `auth_lockouts_triggered_total` | counter | `step` | processus (`auth.lockout_triggered`) |
| `auth_backoffice_attempts_total` | counter | `step`, `result` | processus : tentatives de connexion du back-office par temps (`identify`, `face`, `password`) et résultat (`auth.backoffice_identify`, `auth.backoffice_face_result`, `auth.backoffice_password_result`) |
| `auth_backoffice_lockouts_total` | counter | `step` | processus : blocages de la connexion du back-office par étape verrouillée (`face`, `operator_password`; `auth.backoffice_lockout`) |
| `auth_refresh_reuse_detected_total` | counter | | processus (`auth.refresh_reuse_detected`) |
| `auth_service_token_denied_total` | counter | `client` | processus (`auth.service_token_denied`) |
| `auth_service_token_rate_limited_total` | counter | `client` | processus (`auth.service_rate_limited`) |
| `auth_active_lockouts` | gauge | `step` | base : sujets verrouillés à cet instant (`login_lockouts.locked_until > now`) |
| `auth_state_up` | gauge | | 1 si l'état a pu être lu en base pendant cette collecte, 0 sinon (la série `auth_active_lockouts` est alors **absente**, pas à zéro) |

Les séries `auth_backoffice_*` n'ont **aucune étiquette d'identité** : ni e-mail ni empreinte d'e-mail (`email_hash` reste dans le journal, jamais dans `/metrics`); `test_metrics_endpoint.integ.py` le vérifie et `test_zz_backoffice_journey.e2e.py` relit la collecte réelle après un parcours complet.

Les compteurs sont **par processus** (aucun état partagé en mémoire entre instances) : la collecte additionne les instances et gère un compteur qui repart de zéro au redémarrage. Seuls les verrous actifs sont lus en base, donc partagés entre instances.

### Seuils conseillés
Valeurs de départ à ajuster avec les équipes de détection; elles supposent le défaut de verrouillage (5 échecs en 15 min) et le seuil par IP de la passerelle (60/min).

| Signal | Condition conseillée | Lecture |
|---|---|---|
| Bourrage d'identifiants | `increase(auth_login_failures_total{cause="unknown_account"}[10m])` > 100 | beaucoup d'adresses inconnues : essai de listes d'identifiants |
| Force brute sur un compte | `increase(auth_lockouts_triggered_total[15m])` ≥ 5, ou `auth_active_lockouts` > 10 | plusieurs comptes verrouillés en même temps (un verrou isolé est normal) |
| Réutilisation de jeton | `increase(auth_refresh_reuse_detected_total[1h])` ≥ 1 | jeton de rafraîchissement volé ou rejoué : **alerte immédiate**; plus de 3 par heure et par client = suspect (deux onglets simultanés en produisent rarement) |
| Jetons de service refusés | `increase(auth_service_token_denied_total{client!="unknown"}[5m])` ≥ 3, ou tout `client="unknown"` | un client connu avec un mauvais secret, ou un identifiant inconnu : secret périmé ou sondage |
| Limite de débit des clients de service | `increase(auth_service_token_rate_limited_total[5m])` > 0 | client en boucle |
| Rafale sur la passerelle | part de `auth_http_requests_total{status="429"}` > 5 % sur 5 min | débit par IP atteint (voir aussi les journaux de Traefik) |
| Erreurs serveur | `rate(auth_http_requests_total{status=~"5.."}[5m])` > 0 pendant 5 min | défaut du service ou de sa base |
| Latence | `histogram_quantile(0.95, rate(auth_http_request_duration_seconds_bucket[5m]))` > 0,5 s sur `/login` | le hachage argon2id est coûteux : au-delà, saturation |
| Base illisible | `auth_state_up == 0` pendant 2 min | les verrous actifs ne sont plus mesurables |
| Actions d'administration | toute ligne `auth.account_disabled` ou `auth.operator_created` hors changement planifié | audit : qui a désactivé quoi |
| Collecte détournée | toute ligne `service.metrics_refused` | quelqu'un a routé `auth` d'une façon qui expose `/metrics` |

## Tests
**Parcours de clôture du back-office** (`tests/e2e/scenarios/test_zz_backoffice_journey.e2e.py`, `E2E_CHECK_LOGS=1`) : connexion en trois temps par les routes serveur du back-office, catalogue, commande passée sur le site puis consultée (liste et détail), déconnexion; refus (mauvais visage, mauvais mot de passe, jeton sans second facteur, même 401 générique); blocage de 5 minutes après 3 mauvais mots de passe (le bon mot de passe est alors refusé, le verrou est lu en base); `/metrics` compte les tentatives et blocages sans e-mail; les événements de `backoffice`, `auth` et `shop` relus dans les journaux des conteneurs sont validés contre `log-event.schema.json`, et aucun secret ni donnée personnelle (e-mails, mot de passe, jeton, défi, adresse de livraison) n'y figure. **Visage accepté en e2e** : le faux vérificateur de développement (`APP_FACE_VERIFIER=fake`) avec la même image à l'enrôlement et à la connexion; la pile e2e n'embarque ni le modèle de `visage-id` ni de photos de personnes (le dépôt n'en contient aucune). La reconnaissance réelle est couverte par les tests de l'adaptateur.

**Invitation d'un opérateur** (`tests/e2e/scenarios/test_zx_operator_invitation.e2e.py`, `E2E_CHECK_LOGS=1`) : la commande `create-operator-invite` tourne dans le conteneur `auth`, le lien est consommé par la passerelle sur l'origine admin, puis la personne se connecte en trois temps; lien réutilisé, inconnu, expiré-équivalent et révoqué (même 401), mot de passe faible ou photos invalides (422, jeton conservé), 404 sur le domaine principal, dix images de 1 Mo acceptées et corps de 16 Mio refusé (413), blocage de l'adresse après 5 jetons faux, et ni jeton, ni mot de passe, ni adresse dans les journaux.

`uv run poe test` (unit et integ, couverture ≥ 80 %); `uv run poe test:e2e` sur la pile lancée (`E2E_BASE_URL`, `http://127.0.0.1:8080` par défaut); les scénarios de jetons de service appellent `auth` depuis le conteneur `shop` (réseau `app`, `docker compose exec`) et lisent le secret du client `shop` dans `AUTH_SERVICE_CLIENT_SECRET_SHOP` ou `.env`. Les scénarios d'inscription et de réinitialisation lisent les emails dans Mailpit via `E2E_MAILPIT_URL` (ignorés sans cette variable); `E2E_CHECK_LOGS=1` ajoute le contrôle des journaux des conteneurs (`docker compose logs`, lancé depuis la racine du dépôt) : ni mot de passe, ni jeton, ni adresse. Les scénarios de connexion (`test_login.e2e.py`) créent leur compte par `/register`, vérifient la signature des jetons avec le JWKS publié par la passerelle, les 401 génériques et un temps de réponse comparable; avec `E2E_CHECK_LOGS=1`, ils désactivent un compte par `docker compose exec postgres-auth psql` et contrôlent aussi les journaux (ni jeton d'accès, ni cookie de rafraîchissement, ni clé privée). Les scénarios de rafraîchissement (`test_refresh.e2e.py`) passent le cookie `Secure` à la main (pile en http) et couvrent la rotation, le rejeu, l'en-tête anti-CSRF, la déconnexion idempotente et huit rafraîchissements simultanés avec le même jeton (un seul réussit). Les scénarios d'administration (`test_admin.e2e.py`, `E2E_CHECK_LOGS=1`) créent l'opérateur par `docker compose exec auth python -m app.admin.create_operator` puis vérifient 401, 403, la liste, la désactivation (le compte ne peut plus se connecter) et le refus de l'auto-désactivation. `test_metrics.e2e.py` lit `/metrics` depuis le conteneur `auth` (`docker compose exec`), vérifie que la passerelle ne le sert pas (`/api/auth/metrics`, `/metrics`) et que les en-têtes de proxy donnent 404. Tests de signaux : `app/observability/__tests__` (compteurs, histogramme, format, journal de requête validé contre le schéma, absence de donnée sensible, refus derrière un proxy, état lu en base, isolation statique de la configuration Traefik). `test_account_orders.e2e.py` joue le parcours complet sur la pile (commande invitée, inscription, vérification par Mailpit, connexion, commande connectée, liste des commandes avec rattachement, adresse non vérifiée sans rattachement, 404 identique pour la commande d'un autre compte, parcours invité inchangé) et **arrête le conteneur `auth`** (`docker compose stop auth`, redémarré ensuite) pour prouver que `shop` continue d'accepter les jetons déjà émis.
