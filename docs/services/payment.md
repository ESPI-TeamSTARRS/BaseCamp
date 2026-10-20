# Service `payment`

**Dossier** : `apps/backend/payment`

## Rôle
Paiement interne, sans donnée bancaire réelle : intention de paiement, confirmation, remboursement, webhook signé vers la boutique, grand livre.

## API
| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | liveness (200 tant que le processus répond) |
| GET | `/health/ready` | readiness : 200 si la base répond, 503 sinon |

Les routes de paiement s'ajoutent par tranche (`payment_intent`, `refund`, `ledger`, `webhook`) et se documentent ici.

## Invariants
- Une même clé d'idempotence produit un même résultat, sans doublon.
- Montant et devise valides; montants en unités entières.
- Un remboursement ne dépasse jamais le montant capturé restant.
- Le grand livre est en double écriture et cohérent avec les transactions.
- Un webhook sortant est signé (HMAC et horodatage); un événement rejoué est ignoré à la réception.

## Intégration boutique
Le service `shop` utilise l'interface `PaymentProvider`. L'adaptateur interne est celui par défaut; un fournisseur externe reste branchable.

## Structure
Tranches verticales `app/<feature>/{domain,application,infrastructure,presentation}` (aujourd'hui `health`), configuration dans `app/core`. Migrations Alembic dans `alembic/` (révision initiale vide : le schéma arrive avec les tranches métier). Règle de dépendance vérifiée par `app/__tests__/unit/test_architecture.unit.py`.

## Isolation sur la pile
- **Base dédiée** : conteneur `payment-db` (Postgres) avec son seul rôle applicatif, sur le réseau interne `payment-data` où seul `payment` se trouve. `shop` ne voit pas cette base et `payment` ne voit pas la base du shop.
- **Réseau** : `payment` n'est que sur `payment-net` (partagé avec `shop`) et `payment-data`. Il n'est ni sur `app`, ni routé par Traefik, ni publié sur l'hôte : seul `shop` l'appelle (`http://payment:8000`).
- **Migrations** : le service one-shot `payment-migrate` exécute `alembic upgrade head` avant le démarrage (idempotent).
- **Vérification** : `sh scripts/check-payment-isolation.sh` (pile lancée) et le scénario e2e `tests/e2e/scenarios/test_payment_isolation.e2e.py`.

## Configuration
`APP_SERVICE_NAME`, `APP_ENVIRONMENT`, `APP_DB_HOST`, `APP_DB_PORT`, `APP_DB_NAME`, `APP_DB_USER`, `APP_DB_PASSWORD`. Sur la pile, les valeurs viennent de `PAYMENT_DB_NAME`, `PAYMENT_DB_USER` et `PAYMENT_DB_PASSWORD` (`.env`, modèle dans `.env.example`). Les secrets de signature arrivent aussi par variables d'environnement.
