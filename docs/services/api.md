# Service `api`

**Dossier** : `apps/backend/api`

## Rôle
Catalogue, commandes et stock. Demande les paiements au service [payment](payment.md) via l'interface `PaymentProvider` et authentifie les appels grâce à [auth](auth.md).

## API
| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | liveness |

Les routes métier s'ajoutent par tranche (`catalog`, `order`) et se documentent ici.

## Invariants
- Les prix viennent toujours du catalogue serveur.
- Une commande payée correspond à exactement une transaction.
- Le stock ne devient jamais négatif.

## Configuration
`APP_SERVICE_NAME`, `APP_ENVIRONMENT`.
