# Service `shop`

**Dossier** : `apps/backend/shop`

## Rôle
Catalogue, commandes et stock. Demande les paiements au service [payment](payment.md) via l'interface `PaymentProvider` et authentifie les appels grâce à [auth](auth.md).

## API
| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | liveness : le processus répond (toujours 200) |
| GET | `/health/ready` | readiness : 200 si la base répond, **503** sinon (corps `{"service", "status": "up" \| "down"}`) |
| POST | `/cart/quote` | devis d'un panier calculé par le serveur (voir ci-dessous) |
| POST | `/orders` | crée une commande « en attente de paiement » (voir ci-dessous) |
| POST | `/orders/lookup` | retrouve une commande par numéro et email (suivi, voir ci-dessous) |
| GET | `/products` | catalogue paginé, filtrable par catégorie (voir ci-dessous) |
| GET | `/products/{slug}` | fiche détaillée d'un produit |
| POST | `/pay` | démarre le paiement d'un panier : montant recalculé par le serveur, intention créée dans `payment` (voir ci-dessous) |

Derrière la passerelle, ces routes sont exposées sous `/api/shop/` (ex. `/api/shop/health/ready`). Le healthcheck Docker utilise `/health` (un conteneur dont la base est arrêtée reste vivant); `/health/ready` sert aux sondes de disponibilité.

### `GET /products`
Paramètres : `category` (`tentes`, `couchage`, `sacs-a-dos`, `cuisine`, `securite`), `page` (≥ 1, défaut 1), `page_size` (1 à 100, défaut 12).

Réponse : `{items, page, page_size, total}`. Chaque produit expose `id`, `slug`, `name`, `category`, `price_cents` (entier, centimes d'euro), `compare_at_price_cents`, `short_description`, `description`, `thumbnail_url`, `image_urls`, `specs`, `rating_value`, `rating_count` et `availability` (`in_stock`, `low_stock` pour 1 à 5 pièces, `out_of_stock` à 0). Le stock exact n'est jamais exposé.

Une catégorie inconnue ou une pagination invalide renvoie **422** avec un message fixe : la valeur reçue n'est jamais reflétée. Les images (`/media/<fichier>`) sont servies en lecture seule par la passerelle depuis le bucket `product-images`.

### `GET /products/{slug}`
Renvoie la même représentation qu'un élément de la liste : `description`, `specs` (`weight_grams`, `waterproofing_mm`, `comfort_temp_c`, `seasons`, `capacity_liters`, `material`, chacune absente du produit = `null`), `image_urls` (galerie), `rating_value`, `rating_count`, prix en centimes et `availability`.

Un slug inconnu renvoie **404** avec le message fixe `{"detail": "Produit introuvable."}` : le slug demandé n'est jamais reflété. Il est transmis à la base comme paramètre lié (jamais concaténé).

Côté front, `/produits/[slug]` lit cette route, calcule la méta-description (140 à 160 caractères) et le JSON-LD `Product` (prix, disponibilité, note) à partir de la réponse, et `sitemap.xml` liste les produits de l'API (sans eux si l'API est arrêtée).

### `POST /orders`
En-tête obligatoire `Idempotency-Key` (8 à 128 caractères `A-Za-z0-9_.-`). Le `X-Correlation-ID` suit la règle commune de la [journalisation](../development/logging.md).

Corps (`extra="forbid"`, aucun prix accepté) : `email`, `shippingAddress` (`fullName`, `line1`, `line2` facultatif, `postalCode`, `city`, `country`) et `lines` (`productId`, `quantity` de 1 à 10, 1 à 50 lignes sans doublon).

Réponse : `id`, `number` (`BC-` + 10 caractères, non séquentiel), `status` (`pending_payment`), `email`, `shipping_address`, `lines` (`product_id`, `name`, `unit_price_cents`, `quantity`, `line_total_cents`), `subtotal_cents`, `shipping_cents`, `total_cents`, `created_at`.

| Code | Cas |
|---|---|
| 201 | commande créée, prix figés, stock réservé |
| 200 | même clé rejouée avec le même contenu : même commande, aucune seconde réservation |
| 409 | stock devenu insuffisant (message fixe) : rien n'est réservé, même pour les lignes valides |
| 422 | corps invalide, produit inconnu, pays hors liste (`FR`, `BE`, `CH`, `LU`, `DE`, `ES`, `IT`), clé réutilisée avec un autre contenu |

Les prix sont relus en base sous verrou et la livraison suit la règle du devis (5,90 € sous 80 €). Les messages d'erreur sont fixes : aucune valeur reçue n'est reflétée. La passerelle limite `/api/shop/orders` à 10 requêtes par minute et par adresse.

### `POST /orders/lookup`
Suivi d'une commande par son numéro et l'email de la commande. Corps strict : `{"orderNumber": "BC-XXXXXXXXXX", "email": "…"}` (le numéro doit avoir le format `BC-` + 10 caractères majuscules ou chiffres, sinon `422` assaini). Réponse `200` : `number`, `status` (`pending_payment`, `paid`, `expired`), `lines` (`name`, `unit_price_cents`, `quantity`, `line_total_cents`, tels que figés à la commande), `subtotal_cents`, `shipping_cents`, `total_cents`, `created_at`. Ni l'email ni l'adresse ne sont renvoyés. L'email est comparé sans tenir compte de la casse ni des espaces, en temps constant.

**Anti-énumération** : un numéro inconnu et un email erroné donnent exactement la même réponse, `404 {"detail": "Commande introuvable."}` (même corps, mêmes en-têtes), et le lecteur fait le même nombre de requêtes dans les deux cas. Seuls les logs internes distinguent `order_not_found` de `email_mismatch`, pour repérer une tentative d'énumération. La valeur reçue n'est jamais reflétée.

**Limitation de débit** : la route est sous la règle de la passerelle `/api/shop/orders` (10 requêtes par minute et par adresse, rafale de 5). Un palier plus strict propre au suivi viendra avec le ticket de limitation de débit de la passerelle (S11); il ne demande aucune modification de `shop`.

### `POST /pay`
Corps strict : `{"order_reference", "lines": [{"productId", "quantity"}]}` (aucun montant : le total est celui du devis serveur, livraison comprise) et en-tête `Idempotency-Key` (8 à 255 caractères, transmise à `payment`). Réponse `201` : `{payment_intent_id, status, amount_cents, currency}`. Panier invalide ou stock insuffisant : `422`; refus métier de `payment` : `409` (commande déjà payée) ou `422`, message fixe `{"detail": "Paiement refuse."}`.

L'appel à `payment` a des délais courts (connexion 1 s, lecture 3 s) et un pool borné. Si `payment` est arrêté, injoignable, saturé (429, 5xx) ou mal configuré (401), `shop` répond **`503 {"detail": "Paiement indisponible, reessayez plus tard."}`** avec `Retry-After: 5`, sans bloquer : le catalogue et `/cart/quote` continuent de répondre. Aucun détail technique (hôte, jeton) n'est renvoyé.

Les autres routes métier s'ajoutent par tranche et se documentent ici.

## Invariants
- Les prix viennent toujours du catalogue serveur.
- Une commande payée correspond à exactement une transaction.
- Le stock ne devient jamais négatif (contrainte en base et dans l'entité).
- Les prix sont des entiers en centimes, jamais des flottants; le front convertit pour l'affichage.
- Un produit à stock 0 est « rupture » et ne peut pas être commandé.
- Le serveur seul décide des prix, de la livraison et de la disponibilité : le client n'envoie que `productId` et `quantity`.
- La liveness ne dépend jamais de la base; seule la readiness la teste.
- Le service n'utilise que son propre rôle Postgres, jamais le compte administrateur.

## Invariants de stock et de commande
- **Une seule transaction** : verrou des produits (`SELECT … FOR UPDATE`, dans l'ordre des identifiants pour éviter les interblocages), relecture de la clé d'idempotence, contrôle du stock, insertion de la commande et de ses lignes, décrément du stock et lignes de `stock_reservations`, puis commit. Au moindre échec tout est annulé : jamais de réservation partielle.
- Le stock ne devient jamais négatif : contrôle applicatif sous verrou et contrainte `ck_products_stock_non_negative` en base. Deux commandes sur la dernière pièce : une seule réussit, l'autre reçoit 409 (test de concurrence sur Postgres).
- **Idempotence en base** : `orders.idempotency_key` est unique et `request_fingerprint` mémorise le contenu. Un rejeu, même en parallèle, renvoie la commande existante; une clé réutilisée avec un autre contenu est refusée (422).
- Nom et prix unitaire des lignes sont figés à la commande (`order_lines`) : un changement de catalogue ne modifie jamais une commande existante.
- Une réservation (`stock_reservations.status = reserved`) est liée à une commande; sa libération et le paiement relèvent du ticket de paiement.

## Configuration
Variables d'environnement préfixées `APP_` (voir `.env.example` à la racine) :

| Variable | Défaut | Rôle |
|---|---|---|
| `APP_SERVICE_NAME` | `basecamp-shop` | nom renvoyé par les endpoints de santé |
| `APP_ENVIRONMENT` | `dev` | environnement d'exécution |
| `APP_DB_HOST` / `APP_DB_PORT` | `localhost` / `5432` | serveur Postgres |
| `APP_DB_NAME` / `APP_DB_USER` | `shop` / `shop` | base et rôle propres à `shop` |
| `APP_DB_PASSWORD` | vide | mot de passe du rôle (fourni par l'environnement, jamais versionné) |
| `APP_MEDIA_BASE_URL` | `/media` | préfixe public des images du catalogue |
| `APP_PAYMENT_URL` | `http://payment:8000` | adresse interne de `payment` |
| `APP_PAYMENT_SERVICE_TOKEN` | vide | jeton de service de `shop` auprès de `payment` (alimenté par `PAYMENT_SERVICE_TOKEN_SHOP`, jamais versionné) |
| `APP_PAYMENT_CONNECT_TIMEOUT_SECONDS` / `APP_PAYMENT_READ_TIMEOUT_SECONDS` | `1` / `3` | délais des appels à `payment` |
| `APP_LOG_PSEUDONYM_KEY` | vide | clé HMAC des empreintes d'email dans les logs; obligatoire hors `dev` et `local` |

## Événements métier
Format et règles communes : [journalisation métier](../development/logging.md). Chaque ligne JSON porte le `correlation_id` (en-tête `X-Correlation-ID` repris ou généré).

| Événement | Outcome | Reason | Attributs |
|---|---|---|---|
| `catalog.products_listed` | success | | `category` (si filtre), `page`, `page_size`, `total` |
| `catalog.query_rejected` | denied | `invalid_query` | |
| `catalog.product_viewed` | success | | ressource `product` (id) |
| `catalog.product_not_found` | denied | `product_not_found` | ressource `product` (sans identifiant : le slug demandé n'est pas journalisé) |
| `cart.quoted` | success | | `line_count`, `total_cents` |
| `order.created` | success | | ressource `order` (numéro); `email_hash`, `line_count`, `total_cents`, `country` |
| `stock.reserved` | success | | ressource `order` (numéro), émis juste avant `order.created`; mêmes attributs |
| `order.replayed` | success | | ressource `order` (numéro); mêmes attributs (rejeu idempotent) |
| `stock.insufficient` | denied | `insufficient_stock` | ressource `product` (id); `email_hash` |
| `order.rejected` | denied | `country_not_supported`, `invalid_cart`, `quantity_out_of_range`, `duplicate_product`, `product_not_found`, `idempotency_key_reused` | `email_hash` (jamais la clé d'idempotence, l'email ni l'adresse) |
| `cart.quote_rejected` | denied | `invalid_cart` (nombre de lignes), `quantity_out_of_range`, `duplicate_product`, `product_not_found` | |
| `order.looked_up` | success | | ressource `order` (numéro); `status` |
| `order.lookup_denied` | denied | `order_not_found`, `email_mismatch` | `email_hash` du demandeur; ressource `order` seulement si le numéro existe (jamais l'email reçu) |
| `pay.payment_started` | success | | ressource `payment_intent` (id), `amount_cents`, `currency` |
| `pay.payment_rejected` | denied | `insufficient_stock`, `payment_conflict`, `payment_refused` | refus avant ou par `payment` |
| `pay.payment_unavailable` | error | `payment_unavailable` | `payment` arrêté, injoignable ou saturé (503 renvoyé) |
| `service.request_rejected` | denied | `invalid_request` | requête rejetée par la validation, sans la valeur reçue |
| `service.unhandled_error` | error | `internal_error` | |

## Base de données et migrations
Postgres via SQLAlchemy (pilote `psycopg`). Les migrations sont gérées par Alembic (`apps/backend/shop/alembic/`, URL lue dans `APP_DB_*`).

```bash
cd apps/backend/shop
uv run alembic upgrade head                       # appliquer (idempotent)
uv run alembic revision -m "ajoute les produits"  # nouvelle migration
```

En Docker Compose, `shop-migrate` applique les migrations avant le démarrage de `shop`. La migration `0001` est vide : elle fixe le point de départ de l'historique.

La migration `0003` crée `orders`, `order_lines` (prix figés en centimes) et `stock_reservations`, avec clés étrangères, unicité de la clé d'idempotence et contraintes de montants et de pays. Elle n'ajoute que des tables : l'ancienne version du code tourne sur le schéma migré, ce qui garde le retour arrière automatique sûr (voir `test_migrations_additive.unit.py`, qui impose la règle à toute migration après la 0002).

La migration `0002` crée la table `products` (contraintes : prix > 0, stock ≥ 0, note 0 à 5, catégorie connue) et y charge le jeu de données initial : 15 produits, 3 par catégorie, dont un en rupture et un aux dernières pièces.

## Images du catalogue
Les visuels (SVG originaux, sans droits) sont dans `infra/seed/images/`. Le service one-shot `seaweedfs-seed` les envoie dans le bucket `product-images` à chaque démarrage de la pile (envoi idempotent). Traefik les expose sous `/media/*` en lecture seule (GET et HEAD uniquement, pas de listage).
