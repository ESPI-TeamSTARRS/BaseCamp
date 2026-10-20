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

Les clés d'idempotence sont propres à l'appelant. Les 422 de validation ne renvoient que `{"detail": "Invalid request", "errors": [{"field", "code"}]}` : jamais la valeur reçue.

### Lecture
`GET /payments/intents/{id}` et `GET /payments/intents?order_reference=…` renvoient `id`, `order_reference`, `amount`, `currency`, `status`, `refunded_amount`, `expires_at`, `created_at`. Identifiant ou référence inconnus (ou identifiant mal formé) : `404 {"detail": "Not found"}`.

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

Les événements des tranches à venir (confirmation, remboursement, webhook) s'ajoutent ici avec leur ticket.

## Intégration boutique
Le service `shop` utilise l'interface `PaymentProvider`. L'adaptateur interne est celui par défaut; un fournisseur externe reste branchable.

## Structure
Tranches verticales `app/<feature>/{domain,application,infrastructure,presentation}` (aujourd'hui `health` et `intent`), configuration dans `app/core`. Migrations Alembic dans `alembic/` (`0001` vide, `0002` : tables `payment_intents` et `idempotency_keys`; montants en `BIGINT` de centimes, aucune colonne flottante). Règle de dépendance vérifiée par `app/__tests__/unit/test_architecture.unit.py`.

## Isolation sur la pile
- **Base dédiée** : conteneur `payment-db` (Postgres) avec son seul rôle applicatif, sur le réseau interne `payment-data` où seul `payment` se trouve. `shop` ne voit pas cette base et `payment` ne voit pas la base du shop.
- **Réseau** : `payment` n'est que sur `payment-net` (partagé avec `shop`) et `payment-data`. Il n'est ni sur `app`, ni routé par Traefik, ni publié sur l'hôte : seul `shop` l'appelle (`http://payment:8000`).
- **Migrations** : le service one-shot `payment-migrate` exécute `alembic upgrade head` avant le démarrage (idempotent).
- **Vérification** : `sh scripts/check-payment-isolation.sh` (pile lancée) et les scénarios e2e `tests/e2e/scenarios/` (`test_payment_isolation`, et `test_payment_intents` qui appelle l'API depuis le conteneur `shop`).

## Configuration
`APP_SERVICE_NAME`, `APP_ENVIRONMENT`, `APP_LOG_PSEUDONYM_KEY` (clé HMAC des empreintes d'email dans les logs, obligatoire hors `dev` et `local`), `APP_DB_HOST`, `APP_DB_PORT`, `APP_DB_NAME`, `APP_DB_USER`, `APP_DB_PASSWORD`, `APP_SERVICE_TOKENS`, `APP_INTENT_TTL_MINUTES`, `APP_MAX_AMOUNT_CENTS`. Sur la pile, les valeurs viennent de `PAYMENT_DB_NAME`, `PAYMENT_DB_USER` `PAYMENT_DB_PASSWORD` et `PAYMENT_SERVICE_TOKEN_SHOP` (`.env`, modèle dans `.env.example`). Les secrets de signature arrivent aussi par variables d'environnement.
