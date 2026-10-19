# Service `payment`

**Dossier** : `apps/backend/payment`

## Rôle
Paiement interne, sans donnée bancaire réelle : intention de paiement, confirmation, remboursement, webhook signé vers la boutique, grand livre.

## API
| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | liveness |

Les routes de paiement s'ajoutent par tranche (`payment_intent`, `refund`, `ledger`, `webhook`) et se documentent ici.

## Invariants
- Une même clé d'idempotence produit un même résultat, sans doublon.
- Montant et devise valides; montants en unités entières.
- Un remboursement ne dépasse jamais le montant capturé restant.
- Le grand livre est en double écriture et cohérent avec les transactions.
- Un webhook sortant est signé (HMAC et horodatage); un événement rejoué est ignoré à la réception.

## Intégration boutique
Le service `api` utilise l'interface `PaymentProvider`. L'adaptateur interne est celui par défaut; un fournisseur externe reste branchable.

## Configuration
`APP_SERVICE_NAME`, `APP_ENVIRONMENT`. Les secrets de signature arrivent par variables d'environnement.
