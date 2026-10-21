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

Les autres routes s'ajoutent par tranche (`refund`, `ledger`, `webhook`, confirmation, expiration) et se documentent ici.

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

### Mise à l'échelle (`--scale payment=2`)
- Aucune donnée n'est tenue en mémoire : idempotence, intentions et compteurs de débit sont en base. Le plafond de requêtes simultanées et le pool sont des bornes de ressources de l'instance, sans état métier.
- Deux instances qui reçoivent en parallèle la même demande (même clé) créent **une seule** intention : l'unicité en base (clé d'idempotence et `order_reference`) départage, et l'instance perdante rejoue le résultat du gagnant (200) au lieu de répondre 409. Le même mécanisme (écritures conditionnelles en base) doit protéger la future confirmation : une intention ne passe de `requires_confirmation` à `succeeded` que par un `UPDATE … WHERE status = 'requires_confirmation'`, de sorte que la seconde instance ne confirme pas une seconde fois.
- Chaque instance ouvre au plus 10 connexions (pool + débordement) : deux instances restent très en deçà de `max_connections` de Postgres.
- Sur la pile, `payment` est limité à 256 Mo, 1 CPU et 128 processus par instance.

### Arrêt de `payment` et boutique
`shop` appelle `payment` avec des délais courts (connexion 1 s, lecture 3 s, pool de connexions borné). Si `payment` est arrêté, injoignable ou saturé, `POST /pay` répond `503 {"detail": "Paiement indisponible, reessayez plus tard."}` avec `Retry-After: 5` sans attendre; le catalogue et le devis du panier continuent de fonctionner.

### Vérification
- Tests : `app/core/__tests__` (garde-fous HTTP, pool, filtre de journaux, charge de 200 requêtes parallèles en processus, erreurs et journaux capturés) et `app/ratelimit/__tests__`.
- Pile (job CI `stack-e2e`, lancé avec `--scale payment=2`) : `tests/e2e/scenarios/test_payment_resilience.e2e.py` génère la charge depuis le conteneur `shop` : 200 requêtes parallèles sur `/health` (200 attendus, p95 < 200 ms) pendant 200 requêtes d'attaque, 413, création concurrente répartie sur les deux instances (un seul 201, des rejeux 200 de la même intention), 429 avec `Retry-After`, puis arrêt de `payment` (503 propre sur `/pay`, catalogue et devis en 200) et redémarrage.

## Invariants
- Une même clé d'idempotence produit un même résultat, sans doublon.
- Montant et devise valides; montants en unités entières.
- Un remboursement ne dépasse jamais le montant capturé restant.
- Le grand livre est en double écriture et cohérent avec les transactions.
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

Les événements des tranches à venir (confirmation, remboursement, webhook) s'ajoutent ici avec leur ticket.

## Intégration boutique
Le service `shop` utilise l'interface `PaymentProvider`. L'adaptateur interne est celui par défaut; un fournisseur externe reste branchable.

## Structure
Tranches verticales `app/<feature>/{domain,application,infrastructure,presentation}` (aujourd'hui `health`, `intent` et `ratelimit`), configuration dans `app/core`. Migrations Alembic dans `alembic/` (`0001` vide, `0002` : tables `payment_intents` et `idempotency_keys`; montants en `BIGINT` de centimes, aucune colonne flottante; `0003` : table `rate_limit_windows`, ajout seul). Règle de dépendance vérifiée par `app/__tests__/unit/test_architecture.unit.py`.

## Isolation sur la pile
- **Base dédiée** : conteneur `payment-db` (Postgres) avec son seul rôle applicatif, sur le réseau interne `payment-data` où seul `payment` se trouve. `shop` ne voit pas cette base et `payment` ne voit pas la base du shop.
- **Réseau** : `payment` n'est que sur `payment-net` (partagé avec `shop`) et `payment-data`. Il n'est ni sur `app`, ni routé par Traefik, ni publié sur l'hôte : seul `shop` l'appelle (`http://payment:8000`).
- **Migrations** : le service one-shot `payment-migrate` exécute `alembic upgrade head` avant le démarrage (idempotent).
- **Vérification** : `sh scripts/check-payment-isolation.sh` (pile lancée) et les scénarios e2e `tests/e2e/scenarios/` (`test_payment_isolation`, et `test_payment_intents` qui appelle l'API depuis le conteneur `shop`).

## Configuration
`APP_SERVICE_NAME`, `APP_ENVIRONMENT`, `APP_LOG_PSEUDONYM_KEY` (clé HMAC des empreintes d'email dans les logs, obligatoire hors `dev` et `local`), `APP_DB_HOST`, `APP_DB_PORT`, `APP_DB_NAME`, `APP_DB_USER`, `APP_DB_PASSWORD`, `APP_SERVICE_TOKENS`, `APP_INTENT_TTL_MINUTES`, `APP_MAX_AMOUNT_CENTS`, puis les bornes de [Tenue en charge et sous attaque](#tenue-en-charge-et-sous-attaque) : `APP_DB_POOL_SIZE` (5), `APP_DB_MAX_OVERFLOW` (5), `APP_DB_POOL_TIMEOUT_SECONDS` (3), `APP_DB_CONNECT_TIMEOUT_SECONDS` (2), `APP_DB_STATEMENT_TIMEOUT_MS` (5000), `APP_MAX_BODY_BYTES` (16384), `APP_READ_TIMEOUT_SECONDS` (5), `APP_WRITE_TIMEOUT_SECONDS` (5), `APP_REQUEST_TIMEOUT_SECONDS` (10), `APP_MAX_CONCURRENT_REQUESTS` (64), `APP_RATE_LIMIT_WINDOW_SECONDS` (60), `APP_RATE_LIMIT_CREATE_PER_WINDOW` (60), `APP_RATE_LIMIT_READ_PER_WINDOW` (120). Sur la pile, les valeurs viennent de `PAYMENT_DB_NAME`, `PAYMENT_DB_USER` `PAYMENT_DB_PASSWORD` et `PAYMENT_SERVICE_TOKEN_SHOP` (`.env`, modèle dans `.env.example`). Les secrets de signature arrivent aussi par variables d'environnement.
