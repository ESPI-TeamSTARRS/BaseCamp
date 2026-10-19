# Vue d'ensemble

Basecamp est une boutique de matériel outdoor (tentes, couchage, sacs de grande randonnée, cuisine de camp, sécurité) avec un service de paiement interne, sans donnée bancaire réelle.

## Composants applicatifs

| Composant | Dossier | Rôle |
|---|---|---|
| Front | `apps/frontend` | Vitrine Next.js : catalogue, panier, pages légales |
| `shop` | `apps/backend/shop` | Catalogue, commandes, stock |
| `auth` | `apps/backend/auth` | Comptes, jetons, rôles |
| `payment` | `apps/backend/payment` | Intentions de paiement, remboursements, grand livre, webhooks signés |

Détail par service : [services/](../services/README.md).

## Flux principal d'achat

1. Le front affiche le catalogue fourni par `shop`.
2. Le client s'authentifie auprès de `auth`.
3. `shop` crée une commande puis demande une intention de paiement à `payment` via l'interface `PaymentProvider`.
4. `payment` confirme et notifie `shop` par un webhook signé (HMAC et horodatage).
5. `shop` marque la commande payée. Invariant : une commande payée correspond à exactement une transaction.

## Exécution

Chaque service tourne dans son propre conteneur (utilisateur non-root, healthcheck sur `/health`) et peut être arrêté, relancé ou mis à l'échelle indépendamment. Aucun service ne conserve d'état en mémoire : état persistant en base, limitation de débit et idempotence dans un store partagé.

## Réseaux (cible)

- `edge` : reverse proxy et pare-feu applicatif, seul point publié.
- `app` : services applicatifs, interne.
- `data` : base de données et cache, interne, non publié.
