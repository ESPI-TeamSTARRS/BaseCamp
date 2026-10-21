# Service `payment`

**Dossier** : `apps/backend/payment`

## Rôle
Paiement interne, sans donnée bancaire réelle : intention de paiement, confirmation, remboursement, webhook signé vers la boutique, grand livre.

## API
| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | liveness (200 tant que le processus répond) |
| GET | `/health/ready` | readiness : 200 si la base répond, 503 sinon |
| POST | `/payments/intents` | crée une intention (`requires_confirmation`) |
| GET | `/payments/intents/{id}` | lit une intention par identifiant |
| GET | `/payments/intents?order_reference=…` | lit l'intention d'une commande |
| POST | `/payments/intents/{id}/confirm` | confirme l'intention avec une méthode de test et l'inscrit au grand livre |
| POST | `/payments/intents/{id}/cancel` | annule une intention non confirmée (la boutique libère son stock) |

L'expiration n'est pas une route : c'est un traitement en ligne de commande (voir [Expiration](#expiration)). Les autres routes s'ajoutent par tranche (`refund`, `webhook`) et se documentent ici.

### Authentification
Les routes `/payments/*` exigent `Authorization: Bearer <jeton de service>`. Un jeton statique par appelant est lu dans `APP_SERVICE_TOKENS` (JSON `{"shop": "…"}`, alimenté par `PAYMENT_SERVICE_TOKEN_SHOP`). La comparaison est en temps constant. Jeton absent, mal formé ou invalide : même réponse `401 {"detail": "Unauthorized"}`, sans détail. `auth` remplacera ce mécanisme plus tard.

### `POST /payments/intents`
En-têtes : `Authorization`, `Idempotency-Key` (obligatoire, 8 à 255 caractères). Corps (champs en trop refusés) :

```json
{"order_reference": "CMD-2026-0001", "amount": 4990, "currency": "EUR"}
```

- `order_reference` : 1 à 64 caractères parmi `A-Za-z0-9._-`.
- `amount` : entier de centimes, > 0 et ≤ plafond (`APP_MAX_AMOUNT_CENTS`, 500000 soit 5 000 € par défaut). Décimal, texte ou booléen refusés.
- `currency` : `EUR` uniquement.

Réponse `201` (corps de lecture ci-dessous) avec une échéance à `APP_INTENT_TTL_MINUTES` (30 par défaut).

| Cas | Statut |
|---|---|
| Intention créée | 201 |
| Même clé + même corps (rejeu) | 200, même intention |
| Même clé + corps différent | 422 |
| Autre clé, `order_reference` déjà utilisée | 409 |
| Corps invalide, plafond dépassé, `Idempotency-Key` absente | 422 |
| Jeton absent ou invalide | 401 |
| Budget de débit de l'appelant épuisé pour la route | 429 + `Retry-After` |
| Corps au-delà de 16 Kio | 413 |

Les clés d'idempotence sont propres à l'appelant. Les 422 de validation ne renvoient que `{"detail": "Invalid request", "errors": [{"field", "code"}]}` : jamais la valeur reçue.

### Lecture
`GET /payments/intents/{id}` et `GET /payments/intents?order_reference=…` renvoient `id`, `order_reference`, `amount`, `currency`, `status`, `refunded_amount`, `expires_at`, `created_at`. Identifiant ou référence inconnus (ou identifiant mal formé) : `404 {"detail": "Not found"}`.

### États d'une intention
`requires_confirmation` (état initial) devient `succeeded` ou `failed` à la confirmation, `canceled` à l'annulation, `expired` au traitement d'expiration. **Tous les autres états sont terminaux** : une intention refusée ne se rejoue pas, la boutique en crée une autre. Une intention dont `expires_at` est dépassé n'est plus confirmable ni annulable, même si le traitement d'expiration n'a pas encore fait basculer son statut.

```
requires_confirmation ──confirmation──▶ succeeded | failed
        │──annulation (avant l'échéance)──▶ canceled
        └──échéance atteinte (traitement)──▶ expired
```

### `POST /payments/intents/{id}/confirm`
En-têtes : `Authorization`, `Idempotency-Key` (obligatoire, 8 à 255 caractères, propre à l'appelant). Corps (champs en trop refusés) :

```json
{"payment_method": "pm_test_success"}
```

`payment_method` est l'une de `pm_test_success`, `pm_test_declined`, `pm_test_timeout`, rien d'autre : un numéro de carte ou toute autre valeur donne un 422 qui ne renvoie ni ne journalise la valeur. Le montant n'est jamais lu dans la demande : il vient de l'intention stockée.

| Méthode | Résultat |
|---|---|
| `pm_test_success` | `succeeded` + deux lignes de grand livre (débit `client_attente`, crédit `marchand`, même montant), dans la même transaction que le changement d'état |
| `pm_test_declined` | `failed`, aucune ligne de grand livre |
| `pm_test_timeout` | attente simulée bornée (`APP_PROVIDER_TIMEOUT_SECONDS`, 2 s par défaut, 10 s maximum) puis `failed`, aucune ligne |

Réponse `200` avec le corps de lecture de l'intention : un refus est un résultat métier (`status: "failed"`), pas une erreur HTTP.

| Cas | Statut |
|---|---|
| Confirmation traitée (succès ou refus) | 200 |
| Même clé + même demande (rejeu) | 200, même résultat, aucune nouvelle écriture |
| Même clé + autre méthode ou autre intention | 422 |
| Autre clé sur une intention déjà `succeeded`, `failed`, `canceled`, `expired` ou dont l'échéance est passée | 409 |
| Deux confirmations concurrentes de la même intention | une seule aboutit; l'autre reçoit 409 (ou le rejeu 200 si c'est la même clé) |
| Méthode hors liste, champ en trop, `Idempotency-Key` absente | 422 (assaini : champ et code seulement) |
| Intention inconnue ou identifiant mal formé | 404 |
| Jeton absent ou invalide | 401 |

Concurrence : le traitement lit l'intention avec un verrou de ligne (`SELECT … FOR UPDATE`) pendant toute la transaction, appel au fournisseur compris. La seconde demande attend, relit l'état validé, puis rejoue (même clé) ou reçoit 409. Deux instances de `payment` sont donc départagées par la base.

### `POST /payments/intents/{id}/cancel`
En-tête : `Authorization`. Aucun corps, aucune `Idempotency-Key` : l'opération est idempotente par nature (annuler deux fois rend le même résultat). Réponse `200` avec le corps de lecture de l'intention (`status: "canceled"`).

| Cas | Statut |
|---|---|
| Intention `requires_confirmation` dans son délai | 200, passe `canceled` |
| Déjà `canceled` (rejeu) | 200, même résultat, aucun nouvel événement |
| `succeeded`, `failed`, `expired`, ou échéance dépassée | 409 `{"detail": "Payment intent cannot be canceled"}` |
| Intention inconnue ou identifiant mal formé | 404 `{"detail": "Not found"}` |
| Jeton absent ou invalide | 401 |

Concurrence avec la confirmation : l'annulation lit l'intention avec le même verrou de ligne (`SELECT … FOR UPDATE`) que la confirmation. Une intention confirmée ne peut donc plus être annulée (409) et une intention annulée ne peut plus être confirmée (409), y compris entre deux instances; la base départage. Annuler ne touche jamais au grand livre (une intention non confirmée n'a rien écrit).

### Expiration
Une intention non confirmée à son échéance (`expires_at`, `APP_INTENT_TTL_MINUTES`, 30 minutes par défaut, alignées sur les commandes du shop) passe `expired`, sans écriture au grand livre. Le traitement est un **passage unique en ligne de commande**, à lancer périodiquement (planificateur, tâche cron, `docker compose exec`) :

```
python -m app.expiration.presentation.cli
```

- **Piloté par la base, sans état en mémoire** : la requête retient les lignes `requires_confirmation` dont `expires_at <= maintenant` (index partiel `ix_payment_intents_pending_expiry`, migration `0005`), par lots de `APP_EXPIRATION_BATCH_SIZE` (100) et une transaction par lot. L'horloge est injectée dans le cas d'usage (testé avec une horloge fixe).
- **Rejouable** : un second passage ne trouve plus rien, ne modifie rien et n'émet rien.
- **Concurrence** : les lignes sont prises avec `FOR UPDATE SKIP LOCKED`. Une intention qu'une confirmation ou une annulation tient déjà n'est pas écrasée (elle est sautée); une confirmation qui arrive pendant l'expiration attend le verrou, relit `expired` et reçoit 409. Plusieurs passages en parallèle expirent chaque intention une seule fois.
- Tant qu'aucun passage n'a eu lieu, `GET` renvoie encore `requires_confirmation` pour une intention échue, mais confirmation et annulation la refusent déjà (409). La boutique ne doit pas se fier au statut seul pour libérer le stock : elle utilise l'échéance (`expires_at`) ou l'état `expired`/`canceled`.

### Fournisseur de paiement
Le cas d'usage ne connaît que l'interface `PaymentProvider` (`authorize(méthode, montant)` : approuvé, refusé ou délai dépassé). L'adaptateur `InternalPaymentProvider` simule le résultat d'après la méthode de test; un fournisseur externe se branche en le remplaçant dans `app/confirmation/wiring.py`.

### Grand livre
Table `ledger_entries` (migration `0004`) : `id`, `transaction_id`, `intent_id`, `account` (`client_attente`, `marchand`), `direction` (`debit`, `credit`), `amount` (centimes, `BIGINT`, > 0), `created_at`. Garanties posées en base (Postgres), indépendantes de l'application :
- **ajout seul** : un déclencheur refuse tout `UPDATE`, `DELETE` et `TRUNCATE`, même pour le propriétaire de la table;
- **équilibre** : un déclencheur de contrainte différé vérifie, à la validation, que les débits égalent les crédits de chaque `transaction_id`.

La table `confirmation_keys` (même migration) retient les clés d'idempotence des confirmations (propres à l'appelant), distinctes de celles de la création.

## Tenue en charge et sous attaque
Le service se dégrade proprement au lieu de tomber, et ne coupe jamais `shop`. Tous les seuils sont des variables `APP_*` (voir Configuration); les valeurs ci-dessous sont les défauts, **par instance**.

| Protection | Comportement | Réponse |
|---|---|---|
| Taille du corps | 16 Kio max, contrôlée sur `Content-Length` et sur le flux (corps découpé) | `413 {"detail": "Payload too large"}` |
| Lecture du corps | 5 s max entre deux morceaux (client lent) | `408` |
| Envoi de la réponse | 5 s max par morceau (client qui ne lit plus) : connexion abandonnée | rien |
| Durée d'une requête | 10 s max au total | `504 {"detail": "Request timeout"}` |
| Requêtes simultanées | 64 max par instance, sans file d'attente; `/health` n'est jamais compté ni refusé | `503` + `Retry-After: 1` |
| Pool de connexions BDD | 5 connexions + 5 de débordement, attente d'une connexion 3 s, `statement_timeout` 5 s, connexion 2 s | `503` générique si le pool est épuisé ou la base injoignable |
| Limitation de débit | par appelant (jeton de service) **et** par route, fenêtre fixe de 60 s : 60 créations et 120 lectures par fenêtre | `429` + `Retry-After` (secondes jusqu'à la fin de la fenêtre) |

Un `Retry-After` accompagne tous les `503` et `429`; chaque refus émet un événement métier (voir « Événements métier »). Le contrôle de débit passe **après** l'authentification : une requête au jeton absent ou invalide reçoit 401 sans toucher à la base ni au budget de personne, et épuiser le budget d'un appelant n'a aucun effet sur les autres (budget propre à chaque couple appelant et route). Les routes `/health` ne sont jamais limitées.

### Limitation de débit et instances multiples
Les compteurs sont **en base** (table `rate_limit_windows`, clé `(caller, route, window_start)`, migration `0003`), pas en mémoire : un seul `INSERT … ON CONFLICT DO UPDATE … RETURNING` atomique par requête, partagé par toutes les instances. Avec `--scale payment=2`, le budget d'un appelant est donc global et non doublé. Choix et coûts assumés :
- un aller-retour SQL de plus par requête authentifiée (index sur la clé primaire, ligne unique);
- fenêtre fixe : une rafale à cheval sur deux fenêtres peut atteindre jusqu'à deux fois la limite sur un court instant;
- les fenêtres de plus d'une période sont purgées à l'ouverture d'une nouvelle fenêtre de l'appelant et de la route;
- une requête refusée (429) compte aussi dans la fenêtre. Le flot brut d'un attaquant authentifié est borné en amont par le plafond de requêtes simultanées. La limitation à la passerelle (WORK-16) et le WAF sont hors périmètre.

### Erreurs et journaux assainis
- Les erreurs n'exposent jamais de SQL, de chemin, de pile ni de nom d'hôte : `422` (champ et code seulement), `404 {"detail": "Not found"}`, `500 {"detail": "Erreur interne."}`, `503 {"detail": "Service unavailable"}`. Les paramètres liés sont masqués dans les messages SQLAlchemy (`hide_parameters`).
- Les journaux techniques (uvicorn, bibliothèques, pile d'une exception) passent par un filtre qui masque les jetons de service, le mot de passe de la base, tout `Bearer …`, les numéros de carte (13 à 19 chiffres) et les valeurs de clés sensibles. Les événements métier passent par `BusinessEventLogger` (voir « Événements métier ») : jamais de jeton, de clé d'idempotence ni de numéro de carte.
- Le détail d'une erreur 500 n'existe que dans les journaux techniques du serveur, masqué; la réponse et l'événement `service.unhandled_error` n'en portent aucun.

### Migrations compatibles avec la version précédente
Un retour arrière en production ne restaure pas les bases : toute migration doit rester exécutable avec l'ancien code. La migration `0003` de ce ticket **ajoute seulement** la table `rate_limit_windows` : aucun renommage, aucune suppression, aucune colonne ni contrainte ajoutée à une table existante. L'ancienne version du service ignore cette table et continue de fonctionner, la nouvelle l'utilise. Règle pour les tickets suivants : ajouter (tables, colonnes nullables ou avec défaut), ne jamais renommer ni supprimer dans la même livraison que le code qui en dépend; un renommage ou une suppression se fait en plusieurs livraisons (ajout, bascule du code, puis nettoyage une fois l'ancienne version retirée).

La migration `0005` **ajoute seulement** un index partiel sur `payment_intents (expires_at) WHERE status = 'requires_confirmation'` : aucune colonne, contrainte ou table n'est ajoutée, modifiée ou supprimée. L'ancienne version l'ignore (seul le plan de requête change); retour arrière : `DROP INDEX`, sans toucher aux données. Les statuts `canceled` et `expired` existaient déjà dans l'énumération et la colonne (texte libre) : la nouvelle version les écrit, l'ancienne ne sait pas les relire (même limite que `succeeded` et `failed`), donc traiter les intentions déjà annulées ou expirées avant un retour arrière ou redéployer la nouvelle version.

La migration `0004` suit cette règle : elle **ajoute seulement** les tables `confirmation_keys` et `ledger_entries`, sans toucher à une table existante. Les déclencheurs (ajout seul, équilibre) et les contraintes ne portent que sur ces nouvelles tables; la clé étrangère part de la nouvelle table vers `payment_intents`, jamais l'inverse. L'ancienne version ignore ces tables. Limite assumée : les statuts `succeeded` et `failed` (colonne `payment_intents.status`, texte libre) sont écrits par la nouvelle version seulement; l'ancienne ne sait pas les relire. Un retour arrière de l'image n'exige donc aucune opération sur le schéma, mais les intentions déjà confirmées doivent être traitées avant de revenir en arrière (ou la nouvelle version redéployée).

### Mise à l'échelle (`--scale payment=2`)
- Aucune donnée n'est tenue en mémoire : idempotence, intentions et compteurs de débit sont en base. Le plafond de requêtes simultanées et le pool sont des bornes de ressources de l'instance, sans état métier.
- Deux instances qui reçoivent en parallèle la même demande (même clé) créent **une seule** intention : l'unicité en base (clé d'idempotence et `order_reference`) départage, et l'instance perdante rejoue le résultat du gagnant (200) au lieu de répondre 409. La confirmation s'appuie sur la base de la même façon : l'intention est lue avec un verrou de ligne (`SELECT … FOR UPDATE`) dans la transaction qui écrit l'état, la clé et le grand livre, de sorte que la seconde instance ne confirme pas une seconde fois.
- Chaque instance ouvre au plus 10 connexions (pool + débordement) : deux instances restent très en deçà de `max_connections` de Postgres.
- Sur la pile, `payment` est limité à 256 Mo, 1 CPU et 128 processus par instance.

### Arrêt de `payment` et boutique
`shop` appelle `payment` avec des délais courts (connexion 1 s, lecture 3 s, pool de connexions borné). Si `payment` est arrêté, injoignable ou saturé, `POST /pay` répond `503 {"detail": "Paiement indisponible, reessayez plus tard."}` avec `Retry-After: 5` sans attendre; le catalogue et le devis du panier continuent de fonctionner.

### Vérification
- Tests Postgres : le verrou de ligne, l'équilibre différé et l'ajout seul n'existent que sur Postgres. `test_confirmation_postgres.integ.py`, `test_cancellation_postgres.integ.py` (annulation contre confirmation, y compris en course) et `test_expiration_postgres.integ.py` (verrous sautés, passages concurrents, migration `0005`) s'exécutent si `PAYMENT_TEST_DATABASE_URL` désigne une base jetable (le schéma est créé par `alembic upgrade head`, puis supprimé) : le job CI `backend-payment` fournit ce Postgres; en local, sans la variable, ces tests sont ignorés.
- Tests : `app/core/__tests__` (garde-fous HTTP, pool, filtre de journaux, charge de 200 requêtes parallèles en processus, erreurs et journaux capturés) et `app/ratelimit/__tests__`.
- Annulation et expiration sur la pile : `tests/e2e/scenarios/test_payment_intents.e2e.py` (même job `stack-e2e`, rien de dupliqué) annule, confirme et annule en course, puis force l'échéance en base et lance le traitement `python -m app.expiration.presentation.cli` dans le conteneur `payment` (deux passages : le second n'a aucun effet).
- Pile (job CI `stack-e2e`, lancé avec `--scale payment=2`) : `tests/e2e/scenarios/test_payment_resilience.e2e.py` génère la charge depuis le conteneur `shop` : 200 requêtes parallèles sur `/health` (200 attendus, p95 < 200 ms) pendant 200 requêtes d'attaque, 413, création concurrente répartie sur les deux instances (un seul 201, des rejeux 200 de la même intention), 429 avec `Retry-After`, puis arrêt de `payment` (503 propre sur `/pay`, catalogue et devis en 200) et redémarrage.

## Invariants
- Une même clé d'idempotence produit un même résultat, sans doublon.
- Montant et devise valides; montants en unités entières.
- Un remboursement ne dépasse jamais le montant capturé restant.
- Une intention n'est confirmée qu'une fois; l'état et le grand livre sont écrits dans la même transaction.
- Le grand livre est en double écriture (débits = crédits par transaction), en ajout seul, et cohérent avec les transactions.
- Un webhook sortant est signé (HMAC et horodatage); un événement rejoué est ignoré à la réception.

## Événements métier
Format et règles communes : [journalisation métier](../development/logging.md). Chaque ligne JSON porte le `correlation_id` (en-tête `X-Correlation-ID` repris ou généré); l'appelant doit le transmettre (`outbound_headers()`) pour que la corrélation traverse les services. Ni jeton, ni clé d'idempotence, ni donnée de carte ne sont journalisés.

| Événement | Outcome | Reason | Détails |
|---|---|---|---|
| `payment.service_authenticated` | success | | acteur `service` = appelant |
| `payment.service_authenticated` | denied | `invalid_token` | `client_ip` (premier maillon valide de `X-Forwarded-For`, sinon adresse de la connexion) |
| `payment.intent_created` | success | | ressource `payment_intent`, `amount_cents`, `currency`, acteur `service` |
| `payment.intent_replayed` | success | | rejeu idempotent identique |
| `payment.intent_rejected` | denied | `amount_exceeds_limit`, `idempotency_key_reused`, `duplicate_order_reference` | acteur `service` |
| `payment.intent_read` | success | | ressource `payment_intent`, `lookup` = `id` ou `order` |
| `payment.intent_read` | denied | `not_found` | aucune valeur demandée n'est journalisée |
| `service.request_rejected` | denied | `invalid_request` | validation, sans la valeur reçue |
| `service.unhandled_error` | error | `internal_error` | |
| `service.payload_too_large` | denied | `payload_too_large` | `limit_bytes`, `method` (413) |
| `service.request_timeout` | error | `read_timeout`, `request_timeout` | `method` (408 ou 504) |
| `service.overloaded` | denied | `concurrency_limit` | `method` (503, plafond de requêtes simultanées) |
| `service.rate_limited` | denied | `rate_limit_exceeded` | ressource `route` (`intents.create`, `intents.read`), acteur `service` = appelant, `retry_after_seconds` (429) |
| `service.database_unavailable` | error | `database_unavailable` | base injoignable ou pool épuisé (503) |

Confirmation (acteur `service` = appelant, ressource `payment_intent`, jamais la clé d'idempotence ni la valeur reçue; les noms sont des constantes dans `app/confirmation/application/confirmation_event_names.py`) :

| Événement | Outcome | Reason | Détails |
|---|---|---|---|
| `payment.confirmed` | success | | `order_reference`, `amount_cents`, `currency`; émis après la validation de la transaction |
| `ledger.entries_written` | success | | `transaction_id`, `entry_count` (2), `amount_cents` |
| `payment.declined` | denied | `provider_declined` | méthode `pm_test_declined` |
| `payment.timeout` | error | `provider_timeout` | méthode `pm_test_timeout`, après le délai borné |
| `payment.confirmation_rejected` | denied | `invalid_payment_method`, `invalid_request` | refus à la validation (méthode hors liste ou numéro de carte, sans la valeur); `resource_id` seulement si l'identifiant est un UUID |
| `payment.confirmation_rejected` | denied | `status_succeeded`, `status_failed`, `status_canceled`, `status_expired`, `expired` | conflit 409; `order_reference`, `amount_cents`, `currency` |
| `payment.confirmation_rejected` | denied | `idempotency_key_reused`, `intent_not_found` | clé réutilisée pour une autre demande (422), intention inconnue (404) |

Un rejeu d'une confirmation déjà traitée n'émet rien de nouveau. Une validation refusée émet aussi le `service.request_rejected` générique.

Annulation (acteur `service` = appelant, ressource `payment_intent`; les noms sont des constantes dans `app/cancellation/application/cancellation_event_names.py`) :

| Événement | Outcome | Reason | Détails |
|---|---|---|---|
| `payment.canceled` | success | | `order_reference`, `amount_cents`, `currency`; émis après la validation de la transaction |
| `payment.cancellation_rejected` | denied | `status_succeeded`, `status_failed`, `status_expired`, `expired` | conflit 409; `order_reference`, `amount_cents`, `currency` |
| `payment.cancellation_rejected` | denied | `intent_not_found` | intention inconnue (404); `resource_id` seulement si l'identifiant est un UUID |

Un rejeu d'une annulation déjà faite n'émet rien de nouveau.

Expiration (pas d'acteur : traitement interne; une seule corrélation par passage; noms dans `app/expiration/application/expiration_event_names.py`) :

| Événement | Outcome | Reason | Détails |
|---|---|---|---|
| `payment.expired` | success | | ressource `payment_intent`, `order_reference`, `amount_cents`, `currency`; un par intention expirée |
| `payment.expiration_completed` | success | | `expired_count`; seulement si au moins une intention a expiré |

Un passage qui ne trouve rien n'émet rien.

Les événements des tranches à venir (remboursement, webhook) s'ajoutent ici avec leur ticket.

## Intégration boutique
Le service `shop` utilise l'interface `PaymentProvider`. L'adaptateur interne est celui par défaut; un fournisseur externe reste branchable.

## Structure
Tranches verticales `app/<feature>/{domain,application,infrastructure,presentation}` (aujourd'hui `health`, `intent`, `ratelimit`, `confirmation`, `cancellation`, `expiration` et `ledger`), configuration dans `app/core`. Migrations Alembic dans `alembic/` (`0001` vide, `0002` : tables `payment_intents` et `idempotency_keys`; montants en `BIGINT` de centimes, aucune colonne flottante; `0003` : table `rate_limit_windows`, ajout seul; `0004` : tables `confirmation_keys` et `ledger_entries` avec ses déclencheurs, ajout seul; `0005` : index partiel d'expiration, ajout seul). `confirmation` orchestre la confirmation (unité de travail transactionnelle, fournisseur, journal) et réutilise l'entité d'intention et le grand livre; elle ne partage que des modèles et des mappers avec `intent`. Règle de dépendance vérifiée par `app/__tests__/unit/test_architecture.unit.py`.

## Isolation sur la pile
- **Base dédiée** : conteneur `payment-db` (Postgres) avec son seul rôle applicatif, sur le réseau interne `payment-data` où seul `payment` se trouve. `shop` ne voit pas cette base et `payment` ne voit pas la base du shop.
- **Réseau** : `payment` n'est que sur `payment-net` (partagé avec `shop`) et `payment-data`. Il n'est ni sur `app`, ni routé par Traefik, ni publié sur l'hôte : seul `shop` l'appelle (`http://payment:8000`).
- **Migrations** : le service one-shot `payment-migrate` exécute `alembic upgrade head` avant le démarrage (idempotent).
- **Vérification** : `sh scripts/check-payment-isolation.sh` (pile lancée) et les scénarios e2e `tests/e2e/scenarios/` (`test_payment_isolation`, et `test_payment_intents` qui appelle l'API depuis le conteneur `shop`).

## Configuration
`APP_SERVICE_NAME`, `APP_ENVIRONMENT`, `APP_LOG_PSEUDONYM_KEY` (clé HMAC des empreintes d'email dans les logs, obligatoire hors `dev` et `local`), `APP_DB_HOST`, `APP_DB_PORT`, `APP_DB_NAME`, `APP_DB_USER`, `APP_DB_PASSWORD`, `APP_SERVICE_TOKENS`, `APP_INTENT_TTL_MINUTES`, `APP_MAX_AMOUNT_CENTS`, `APP_PROVIDER_TIMEOUT_SECONDS` (délai simulé de `pm_test_timeout`, 2 par défaut, 10 maximum), `APP_EXPIRATION_BATCH_SIZE` (intentions expirées par transaction, 100 par défaut, 1000 maximum), puis les bornes de [Tenue en charge et sous attaque](#tenue-en-charge-et-sous-attaque) : `APP_DB_POOL_SIZE` (5), `APP_DB_MAX_OVERFLOW` (5), `APP_DB_POOL_TIMEOUT_SECONDS` (3), `APP_DB_CONNECT_TIMEOUT_SECONDS` (2), `APP_DB_STATEMENT_TIMEOUT_MS` (5000), `APP_MAX_BODY_BYTES` (16384), `APP_READ_TIMEOUT_SECONDS` (5), `APP_WRITE_TIMEOUT_SECONDS` (5), `APP_REQUEST_TIMEOUT_SECONDS` (10), `APP_MAX_CONCURRENT_REQUESTS` (64), `APP_RATE_LIMIT_WINDOW_SECONDS` (60), `APP_RATE_LIMIT_CREATE_PER_WINDOW` (60), `APP_RATE_LIMIT_READ_PER_WINDOW` (120). Sur la pile, les valeurs viennent de `PAYMENT_DB_NAME`, `PAYMENT_DB_USER` `PAYMENT_DB_PASSWORD` et `PAYMENT_SERVICE_TOKEN_SHOP` (`.env`, modèle dans `.env.example`). Les secrets de signature arrivent aussi par variables d'environnement.
