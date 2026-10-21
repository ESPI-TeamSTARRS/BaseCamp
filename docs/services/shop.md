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
| GET | `/products` | catalogue paginé, filtrable par catégorie (voir ci-dessous) |
| GET | `/products/{slug}` | fiche détaillée d'un produit |

Derrière la passerelle, ces routes sont exposées sous `/api/shop/` (ex. `/api/shop/health/ready`). Le healthcheck Docker utilise `/health` (un conteneur dont la base est arrêtée reste vivant); `/health/ready` sert aux sondes de disponibilité.

### `GET /products`
Paramètres : `category` (`tentes`, `couchage`, `sacs-a-dos`, `cuisine`, `securite`), `page` (≥ 1, défaut 1), `page_size` (1 à 100, défaut 12).

Réponse : `{items, page, page_size, total}`. Chaque produit expose `id`, `slug`, `name`, `category`, `price_cents` (entier, centimes d'euro), `compare_at_price_cents`, `short_description`, `description`, `thumbnail_url`, `image_urls`, `specs`, `rating_value`, `rating_count` et `availability` (`in_stock`, `low_stock` pour 1 à 5 pièces, `out_of_stock` à 0). Le stock exact n'est jamais exposé.

Une catégorie inconnue ou une pagination invalide renvoie **422** avec un message fixe : la valeur reçue n'est jamais reflétée. Les images (`/media/<fichier>`) sont servies en lecture seule par la passerelle depuis le bucket `product-images`.

### `GET /products/{slug}`
Renvoie la même représentation qu'un élément de la liste : `description`, `specs` (`weight_grams`, `waterproofing_mm`, `comfort_temp_c`, `seasons`, `capacity_liters`, `material`, chacune absente du produit = `null`), `image_urls` (galerie), `rating_value`, `rating_count`, prix en centimes et `availability`.

Un slug inconnu renvoie **404** avec le message fixe `{"detail": "Produit introuvable."}` : le slug demandé n'est jamais reflété. Il est transmis à la base comme paramètre lié (jamais concaténé).

Côté front, `/produits/[slug]` lit cette route, calcule la méta-description (140 à 160 caractères) et le JSON-LD `Product` (prix, disponibilité, note) à partir de la réponse, et `sitemap.xml` liste les produits de l'API (sans eux si l'API est arrêtée).

Les autres routes métier (commandes) s'ajoutent par tranche et se documentent ici.

## Invariants
- Les prix viennent toujours du catalogue serveur.
- Une commande payée correspond à exactement une transaction.
- Le stock ne devient jamais négatif (contrainte en base et dans l'entité).
- Les prix sont des entiers en centimes, jamais des flottants; le front convertit pour l'affichage.
- Un produit à stock 0 est « rupture » et ne peut pas être commandé.
- Le serveur seul décide des prix, de la livraison et de la disponibilité : le client n'envoie que `productId` et `quantity`.
- La liveness ne dépend jamais de la base; seule la readiness la teste.
- Le service n'utilise que son propre rôle Postgres, jamais le compte administrateur.

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
| `cart.quote_rejected` | denied | `invalid_cart` (nombre de lignes), `quantity_out_of_range`, `duplicate_product`, `product_not_found` | |
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

La migration `0002` crée la table `products` (contraintes : prix > 0, stock ≥ 0, note 0 à 5, catégorie connue) et y charge le jeu de données initial : 15 produits, 3 par catégorie, dont un en rupture et un aux dernières pièces.

## Images du catalogue
Les visuels (SVG originaux, sans droits) sont dans `infra/seed/images/`. Le service one-shot `seaweedfs-seed` les envoie dans le bucket `product-images` à chaque démarrage de la pile (envoi idempotent). Traefik les expose sous `/media/*` en lecture seule (GET et HEAD uniquement, pas de listage).
