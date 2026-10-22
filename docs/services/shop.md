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
| GET | `/me/orders` | **client connecté** : ses commandes (paginées), voir « Commandes du compte » |
| GET | `/me/orders/{id}` | **client connecté** : une de ses commandes, 404 identique pour une commande inconnue ou d'un autre compte |
| POST | `/orders/{id}/pay` | demande l'intention de paiement d'une commande en attente |
| POST | `/orders/{id}/pay/confirm` | confirme le paiement avec une méthode de test |
| GET | `/admin/products` | **administration** (origine admin seulement) : liste paginée, archivés optionnels, recherche `q` par nom (sous-chaîne, sans casse, 100 caractères au plus; `%` et `_` sont cherchés tels quels) |
| POST | `/admin/products` | **administration** : crée un produit (201) |
| GET / PATCH | `/admin/products/{id}` | **administration** : lit, modifie partiellement (version optimiste) |
| POST | `/admin/products/{id}/archive` | **administration** : archive (soft delete) |
| POST | `/admin/products/{id}/image` | **administration** : téléverse une image (JPEG, PNG, WebP, 2 Mo) |
| POST | `/webhooks/payment` | **interne** : webhook signé de `payment` (jamais routé par la passerelle, voir ci-dessous) |
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
Suivi d'une commande par son numéro et l'email de la commande. Corps strict : `{"orderNumber": "BC-XXXXXXXXXX", "email": "…"}` (le numéro doit avoir le format `BC-` + 10 caractères majuscules ou chiffres, sinon `422` assaini). Réponse `200` : `number`, `status` (`pending_payment`, `paid`, `expired`, `refunded`), `lines` (`name`, `unit_price_cents`, `quantity`, `line_total_cents`, tels que figés à la commande), `subtotal_cents`, `shipping_cents`, `total_cents`, `created_at`. Ni l'email ni l'adresse ne sont renvoyés. L'email est comparé sans tenir compte de la casse ni des espaces, en temps constant.

**Anti-énumération** : un numéro inconnu et un email erroné donnent exactement la même réponse, `404 {"detail": "Commande introuvable."}` (même corps, mêmes en-têtes), et le lecteur fait le même nombre de requêtes dans les deux cas. Seuls les logs internes distinguent `order_not_found` de `email_mismatch`, pour repérer une tentative d'énumération. La valeur reçue n'est jamais reflétée.

**Limitation de débit** : la route est sous la règle de la passerelle `/api/shop/orders` (10 requêtes par minute et par adresse, rafale de 5). Un palier plus strict propre au suivi viendra avec le ticket de limitation de débit de la passerelle (S11); il ne demande aucune modification de `shop`.

### `POST /pay`
Corps strict : `{"order_reference", "lines": [{"productId", "quantity"}]}` (aucun montant : le total est celui du devis serveur, livraison comprise) et en-tête `Idempotency-Key` (8 à 255 caractères, transmise à `payment`). Réponse `201` : `{payment_intent_id, status, amount_cents, currency}`. Panier invalide ou stock insuffisant : `422`; refus métier de `payment` : `409` (commande déjà payée) ou `422`, message fixe `{"detail": "Paiement refuse."}`.

L'appel à `payment` a des délais courts (connexion 1 s, lecture 3 s) et un pool borné. Si `payment` est arrêté, injoignable, saturé (429, 5xx) ou mal configuré (401), `shop` répond **`503 {"detail": "Paiement indisponible, reessayez plus tard."}`** avec `Retry-After: 5`, sans bloquer : le catalogue et `/cart/quote` continuent de répondre. Aucun détail technique (hôte, jeton) n'est renvoyé.

### `POST /orders/{id}/pay` et `POST /orders/{id}/pay/confirm`
Paiement d'une commande créée par `POST /orders` (`{id}` est l'identifiant renvoyé à la création, un UUID). Le montant est le total figé de la commande, jamais une valeur du client. `shop` passe par le port `PaymentGateway` (`app/pay`), dont l'adaptateur est choisi par `APP_PAYMENT_PROVIDER` : `http` (par défaut) appelle le service [payment](payment.md), `simulated` est un fournisseur sans réseau ni clé dont l'état est en base (tables `simulated_payment_intents`), utile hors de la pile. Aucune clé Stripe ni donnée bancaire n'existe nulle part.

**Demande** (`POST /orders/{id}/pay`, sans corps) : `201` à la première demande, `200` si une intention attend déjà sa confirmation (rejeu sans nouvelle intention). Réponse : `payment_intent_id`, `status` (`requires_confirmation`), `amount_cents`, `currency`, `order_number`, `payment_methods` (`pm_test_success`, `pm_test_declined`). Après un refus, une nouvelle demande crée une nouvelle intention (référence `BC-…-2`, `-3`…) car une intention refusée est terminale.

**Confirmation** (`POST /orders/{id}/pay/confirm`, corps strict `{"payment_method": "pm_test_success" | "pm_test_declined"}`) : un numéro de carte ou tout autre champ donne un `422` qui ne renvoie pas la valeur. Réponse `200` : `order_number`, `order_status` (`paid` ou `pending_payment`), `payment_status` (`succeeded` ou `failed`). **Seul le résultat renvoyé par le fournisseur marque la commande payée**; un refus est un résultat métier (200), la commande reste en attente.

| Code | Cas |
|---|---|
| 201 / 200 | intention créée / déjà en attente |
| 404 | commande inconnue (message fixe) |
| 409 | commande déjà payée (`Commande deja payee.`), expirée (`Commande expiree.`) ou sans paiement en attente |
| 422 | identifiant mal formé, méthode hors liste, champ en trop, refus métier du fournisseur |
| 503 | fournisseur arrêté ou saturé, `Retry-After: 5` |

Concurrence : la commande est lue avec un verrou de ligne (`SELECT … FOR UPDATE`) pour toute la transaction, appel au fournisseur compris. Deux confirmations parallèles ne paient qu'une fois (l'autre reçoit 409), deux demandes parallèles ne créent qu'une tentative (test sur Postgres).

## Commandes du compte (WORK-40)
`shop` reconnaît un client connecté **sans appeler `auth` à chaque requête** : il vérifie localement son jeton d'accès, et ne rattache à son compte que des commandes dont l'adresse est **vérifiée**. Le parcours invité (WORK-11 à WORK-14) est inchangé.

**Vérification des jetons** (tranche `customer_identity`, contrat d'[auth](auth.md#contrat-de-vérification-pour-shop-et-payment-jeton-client)) : signature EdDSA par `kid` avec les clés publiques d'`auth` (`GET http://auth:8000/.well-known/jwks.json`, réseau `app`), `iss` = `basecamp-auth`, `aud` = `basecamp-client-api`, `token_use` = `client`, `exp` (tolérance de 30 s), `sub`, `jti`; `alg` autre qu'EdDSA refusé. Le cache des clés (publiques, relisibles à tout moment, ce n'est pas un état métier) :
- une clé reste valable 5 minutes (`APP_AUTH_JWKS_TTL_SECONDS`), puis est relue;
- un `kid` inconnu déclenche une relecture, **au plus une toutes les 10 s** : des `kid` tirés au hasard ne peuvent pas marteler `auth`;
- une lecture qui échoue **ne vide jamais le cache** : `auth` arrêté, les jetons déjà émis restent vérifiables avec les clés connues (même périmées). Sans aucune clé connue et `auth` injoignable, la route réservée répond **503** `Identification momentanément indisponible.` (avec `Retry-After: 5`), jamais 401; un achat reste possible en invité.

**Routes réservées (`/me/orders`)** : sans jeton, avec un jeton refusé (signature, émetteur, audience, expiré) : **401** `Authentification requise.` identique pour toute cause (le motif n'est que dans l'événement `customer.token_rejected`). Elles ne renvoient que les commandes du compte : le compte est une condition de chaque requête (`orders.user_id`). Réponse : `id`, `number`, `status`, `lines`, totaux en centimes, `created_at`; **jamais l'email ni l'adresse de livraison**. Liste : `limit` (1 à 50, 20 par défaut), `offset`, `total`, les plus récentes d'abord. Détail d'une commande inconnue, d'un invité ou d'un autre compte : le même **404** `Commande introuvable.`.

**Passage de commande** (`POST /orders`) : sans en-tête `Authorization`, comportement strictement inchangé. Avec un jeton valide, la commande porte l'identifiant du compte (`orders.user_id`, rien d'autre n'est copié du compte). Avec un jeton **présent mais invalide ou expiré** (ou sans clé lisible), l'appelant est traité en invité : **un achat n'est jamais bloqué par l'identification** (l'événement `customer.token_rejected` reste journalisé).

**Rattachement des commandes invitées** : le jeton ne contient pas l'adresse. Au premier appel connecté (liste des commandes, ou passage de commande), `shop` lit `GET /me` d'`auth` (réseau interne, avec le jeton du client) pour obtenir l'adresse et `email_verified`, puis exécute **un seul `UPDATE`** : les commandes sans compte dont l'adresse est identique (sans tenir compte de la casse) passent au compte. Garde-fous :
- **adresse non vérifiée : rien n'est rattaché** (ni d'après le jeton, ni d'après `auth`; sinon n'importe qui pourrait s'approprier les commandes d'une adresse qu'il ne possède pas);
- idempotent, et une commande déjà rattachée à un compte n'est **jamais reprise** par un autre;
- `auth` arrêté ou en erreur : rien n'est rattaché cette fois et la tentative suivante réessaie, sans effet sur la liste ni sur l'achat (le rattachement ne fait jamais échouer son appelant);
- le suivi par numéro et email (`POST /orders/lookup`) continue de fonctionner, avec ou sans compte.

Événements : `order.account_listed`, `order.account_view_denied`, `order.guest_orders_linked` (`count`, `email_hash`), `order.guest_link_skipped` (motifs `email_not_verified`, `profile_unavailable`, `link_failed`), `customer.token_rejected` (motifs internes `missing_key_id`, `unknown_key`, `bad_algorithm`, `expired`, `invalid`, `wrong_issuer`, `wrong_audience`, `not_a_client_token`) et `customer.keys_unavailable`. Ni jeton, ni adresse en clair.

Les autres routes métier s'ajoutent par tranche et se documentent ici.

## Invariants
- Les prix viennent toujours du catalogue serveur.
- Une commande payée correspond à exactement une transaction.
- Seul le résultat du fournisseur de paiement marque une commande payée; le client n'envoie qu'une méthode de test, jamais un montant ni une donnée de carte.
- Une commande payée ou expirée ne peut plus être payée (409).
- Une commande payée n'expire jamais; le stock d'une commande expirée est rendu une seule fois (réservation « libérée »), même si le traitement est rejoué ou lancé en parallèle.
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
- Une réservation (`stock_reservations.status = reserved`) est liée à une commande; sa libération est décrite plus bas (expiration) et le paiement la rend définitive (`committed`, voir la confirmation par webhook).

## Administration du catalogue (WORK-58)
API réservée aux opérateurs du back-office, **répondue uniquement sur l'origine admin** : la passerelle ne route `/api/shop/admin/*` vers `shop` que pour un hôte `admin.<domaine>` (routeur `shop-admin`, `infra/traefik/dynamic.yml` et `deploy/traefik/dynamic.prod.yml`). Sur le domaine principal ces chemins tombent sur le front (404). La passerelle applique un limiteur de débit propre (`admin-rate-limit` : 30 requêtes par minute et par adresse, rafale de 10) et une limite de corps de 3 Mio (`admin-body-limit`, 413 au-delà).

**Garde** (`app/customer_identity`, `AuthorizeOperatorUseCase`, dépendance `current_operator`) : même vérificateur JWKS que les routes client (EdDSA, `kid`, émetteur, audience, expiration; clé publique d'`auth`, cache 5 min). Sans jeton valide : **401**; jeton valide dont `roles` ne contient pas `operator`, ou dont `amr` ne contient pas la méthode exigée (`APP_ADMIN_REQUIRED_AMR`, `face` par défaut) : **403**; clés illisibles sans cache : **503**, jamais un accès par défaut. `roles` et `amr` doivent être de vraies listes de textes (sinon vides). Événements : `customer.token_rejected` (401), `operator.access_denied` (motifs `not_operator`, `second_factor_missing`).

| Code | Cas |
|---|---|
| 200 / 201 | succès (création : 201) |
| 401 / 403 / 503 | voir la garde |
| 404 | produit inconnu (`Produit introuvable.`) |
| 409 | version périmée (`Version perimee.`), produit archivé (`Produit archive.`), identifiant déjà pris (`Produit deja existant.`), 10 images déjà présentes |
| 413 | corps de plus de 3 Mio (passerelle) |
| 422 | données refusées (`Requete invalide.`, sans écho de la valeur ni de la clé reçue) ou image refusée (`Image invalide.`) |
| 503 | stockage d'images arrêté (`Stockage des images indisponible.`, `Retry-After: 5`) |

- **Création** (`POST /admin/products`) : `name` (1 à 200), `category` (une des catégories du catalogue), `price_cents` entier **≥ 0**, `short_description` (1 à 300), `description` (1 à 5000), `stock` entier **≥ 0**; optionnels `slug` (`a-z0-9` séparés par des tirets, dérivé du nom sinon; il sert d'identifiant), `compare_at_price_cents`, `specs` (poids, imperméabilité, température de confort, saisons, capacité, matériau). Entiers **stricts** (ni flottant, ni texte, ni booléen). `extra="forbid"` : tout autre champ (`id`, `version`, `rating_*`, `archived_at`…) est refusé en 422. Les notes partent de zéro.
- **Modification** (`PATCH /admin/products/{id}`) : `version` obligatoire (celle lue) et au moins un champ parmi `name`, `category`, `price_cents`, `compare_at_price_cents`, `short_description`, `description`, `specs`, `stock`. Le slug, l'identifiant et les images ne se modifient pas ici.
- **Concurrence** : `products.version` (défaut 1) est incrémentée à chaque modification d'administration, à chaque image ajoutée, à l'archivage **et à chaque variation de stock d'une commande ou d'une expiration**. La mise à jour est un `UPDATE … WHERE version = :lue` : une version périmée est un 409 sans aucun effet, y compris face à une commande arrivée entre-temps. Le stock ne devient jamais négatif (validation, puis contrainte `ck_products_stock_non_negative`).
- **Archivage** (`POST …/archive`) : soft delete, `archived_at` renseigné, **aucune ligne effacée**, idempotent. Un produit archivé disparaît du catalogue client (`GET /products`, fiche), du devis de panier et de la création de commande; il reste lisible dans les commandes passées (nom et prix figés dans `order_lines`) et dans l'administration (`?include_archived=true`). Il ne peut plus être modifié ni recevoir d'image.
- **Image** (`POST …/image`) : le corps de la requête est **les octets de l'image** (pas de formulaire). Types acceptés **vérifiés sur les premiers octets** (JPEG `FF D8 FF`, PNG, WebP `RIFF…WEBP`), jamais sur l'extension ni l'en-tête `Content-Type` annoncés; 2 Mio au plus, lus au plus jusqu'à la limite. Un fichier vide, trop gros, SVG, déguisé ou d'un autre type est refusé en 422 **avant** toute écriture (aucun effet de bord). Le nom est tiré au hasard (`<32 hex>.jpg|png|webp`), jamais dérivé du client. Le fichier part dans le bucket `product-images` par le port `ProductImageStorage` : adaptateur S3 (`S3ProductImageStorage`, signature SigV4 sur l'API S3 de SeaweedFS, clés `APP_S3_ACCESS_KEY` / `APP_S3_SECRET_KEY` de l'environnement, jamais versionnées) et adaptateur mémoire pour les tests. La clé est ajoutée à `images`; l'image est servie par `/media/<clé>` comme toutes les autres. 10 images au plus par produit.
- **Journal** : `catalog_admin.change` à chaque changement (`action` = `create`, `update`, `image` ou `archive`), acteur `user` pseudonymisé (empreinte HMAC de l'identifiant du compte, jamais l'identifiant), ressource `product`, attributs `old_price_cents`, `new_price_cents`, `new_stock`, `version`. Jamais de description, de jeton ni de donnée personnelle. Le schéma commun n'a pas changé (`actor_type` = `user`).
## Confirmation de paiement par webhook (WORK-13)
`payment` notifie la boutique de chaque règlement par un `POST /webhooks/payment` signé (contrat publié : [payment.md, « Webhook sortant vers la boutique »](payment.md)). La route n'est **pas** publique : seul `payment-worker` l'appelle, sur le réseau interne `payment-net`, et la passerelle ne route pas `/api/shop/webhooks` (le chemin tombe sur le front, 404).

**Authentification** (avant toute lecture d'état) : en-tête `X-Payment-Signature: t=<secondes>,v1=<hex>`, `v1 = HMAC-SHA256(secret, "<t>.<corps brut>")`, comparaison en temps constant (`hmac.compare_digest`), plusieurs `v1` acceptés pendant une rotation, horodatage à ± 300 s. Secret `APP_PAYMENT_WEBHOOK_SECRET` (et `APP_PAYMENT_WEBHOOK_SECRET_PREVIOUS` pour la rotation), alimentés par `PAYMENT_WEBHOOK_SECRET` : jamais dans le dépôt ni dans les journaux. Sans secret configuré, tout webhook est refusé. Le vecteur de test du contrat est rejoué par `test_webhook_signature_verifier.unit.py`.

| Code | Cas |
|---|---|
| 200 `{"status": "applied"}` | événement appliqué (commande payée, ou échec noté) |
| 200 `{"status": "replayed"}` | même identifiant d'événement déjà reçu : aucun effet, aucun second email |
| 200 `{"status": "ignored"}` | événement authentique mais sans effet (voir les motifs ci-dessous) |
| 401 `{"detail": "Signature invalide."}` | signature absente, mal formée, fausse, corps altéré ou horodatage hors fenêtre (le motif exact est dans le journal) |
| 400 `{"detail": "Evenement invalide."}` | corps signé mais illisible, ou `X-Payment-Event-Id` différent de l'`id` du corps |

**`payment.succeeded`** : la référence `data.order_reference` est celle de la **tentative** de paiement (`BC-…`, puis `BC-…-2` après un refus), résolue par `payment_attempts.reference`. Dans une seule transaction, avec la commande verrouillée (`FOR UPDATE`) : la commande passe « payée » (si elle ne l'est pas déjà par `/pay/confirm`), la tentative « succeeded », les réservations de stock `reserved` deviennent `committed` (le stock avait déjà été retiré à la commande : il devient définitif et ne sera plus rendu par l'expiration) et l'événement est enregistré. L'email de confirmation part **après** le commit et la réponse. Jamais payée par un événement dont le montant (centimes) ou la devise (`EUR`) diffère de la commande, ni une commande expirée (`ignored`, motifs `amount_mismatch`, `currency_mismatch`, `order_expired`; référence inconnue : `order_not_found`). **Paiement tardif** (WORK-30) : un `payment.succeeded` pour une commande expirée est enregistré `ignored` (`order_expired`) mais la route répond **409** `{"status": "rejected", "reason": "order_expired"}`, y compris au rejeu du même identifiant; `payment` rembourse alors le client (voir [payment.md](payment.md)). Un 200 lui ferait croire la commande payée.

**`payment.failed`** : la tentative passe « failed », la commande reste payable (un événement tardif ne rétrograde jamais une tentative réussie : `attempt_settled`). **`refund.succeeded`** (WORK-29) : le cumul remboursé (`data.amount_refunded`, en centimes) est enregistré dans `order_refunds`. Remboursement total : commande « remboursée » (`refunded`, non repayable); partiel : la commande reste « payée » avec son cumul. Le cumul ne fait que croître : un rejeu, un événement plus ancien (`refund_already_recorded`), un cumul au-delà du total (`refund_exceeds_total`), absent (`refund_amount_missing`) ou sur une commande non payée (`order_not_paid`) est acquitté en 200 sans effet. Les autres types sont acquittés en 200 sans effet (`unsupported_type`).

**Idempotence persistée** : table `payment_webhook_events` (clé primaire = identifiant d'événement de `payment`, constant à chaque relance). Elle survit à un redémarrage et départage les livraisons parallèles (la perdante est un rejeu). **Invariant** : `paid_order_id` est unique, donc une commande payée correspond à exactement un événement de paiement; un second événement pour la même commande est mémorisé mais n'a aucun effet (`order_already_confirmed`).

**Email de confirmation** : port `ConfirmationSender`, deux adaptateurs choisis par `APP_MAIL_TRANSPORT` : `smtp` (défaut ; Mailpit en développement et en CI, `APP_SMTP_HOST`, `APP_SMTP_PORT`, `APP_SMTP_FROM`) ou `n8n` (production sans relais SMTP : `POST` JSON `{to, subject, body}` vers le webhook `APP_N8N_MAIL_URL` avec l'en-tête `X-Mail-Secret` = `APP_N8N_MAIL_SECRET`, délai `APP_N8N_MAIL_TIMEOUT_SECONDS`). Une valeur inconnue du transport, ou `n8n` sans URL ni secret, empêche le démarrage. Le message reprend le numéro, les lignes et le total figés ; le corps est un **HTML** dérivé du texte (tout échappé, liens http(s) cliquables, paragraphes), et l'adaptateur SMTP envoie le texte brut avec l'alternative HTML. Redirections non suivies (le secret ne part jamais ailleurs). Un refus (401/403…), une réponse sans `{"ok": true}`, un délai dépassé ou un serveur injoignable sont des échecs d'envoi comme les autres. Une panne d'envoi ne fait jamais échouer le webhook : elle est journalisée (`order.confirmation_email_failed`, motif `http_<code>`, `timeout`, `connection_error`, `invalid_response`, `not_configured` ou `delivery_failed`, avec l'empreinte HMAC de l'adresse, jamais l'adresse, le corps ni le secret) et la commande reste payée. Avec `APP_PAYMENT_PROVIDER=simulated`, il n'y a pas de webhook : aucun email n'est envoyé.
## Expiration des commandes impayées
Une commande « en attente de paiement » depuis plus de `APP_ORDER_EXPIRATION_MINUTES` (30 par défaut) passe à « expirée » et ses réservations de stock sont libérées : le stock redevient disponible. Le délai est strict (exactement 30 minutes n'expire pas) et l'horloge est injectée dans le cas d'usage (`ExpireUnpaidOrdersUseCase`), ce qui rend le comportement testable sans attente.

- **Sans état en mémoire** : chaque passage relit la base. Un lot (100 commandes) est une transaction; les commandes sont lues avec `SELECT … FOR UPDATE SKIP LOCKED` : une commande en cours de paiement (verrou tenu par le paiement) est ignorée, une commande payée n'est jamais sélectionnée, et plusieurs instances se départagent sans double libération.
- **Rejouable** : seules les réservations « réservées » sont rendues puis marquées « libérées »; un second passage ne change rien.
- **Paiement tardif** : `POST /orders/{id}/pay` et `/pay/confirm` sur une commande expirée répondent `409 {"detail": "Commande expiree."}` et émettent `order.payment_rejected` (`order_expired`).
- **Déclenchement** : `python -m app.order_expiration --once` (un passage, code de sortie 1 en cas d'échec) ou `--every 60` (boucle sans état, un passage par minute; une panne est journalisée et n'arrête pas la boucle). Sur la pile de développement, le service `shop-expiration` de `docker-compose.yml` exécute la boucle. En production, le même service ou une tâche planifiée (cron, minuteur systemd) doit lancer cette commande dans l'image `shop` : le déploiement s'en charge (`deploy/`).

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
| `APP_ORDER_EXPIRATION_MINUTES` | `30` | délai au bout duquel une commande impayée expire et rend son stock |
| `APP_ADMIN_REQUIRED_AMR` | `face` | méthode d'authentification (`amr`) exigée en plus du rôle `operator` pour l'administration |
| `APP_S3_ENDPOINT` / `APP_S3_BUCKET` / `APP_S3_REGION` | `http://seaweedfs:8333` / `product-images` / `us-east-1` | stockage des images (API S3 de SeaweedFS) |
| `APP_S3_ACCESS_KEY` / `APP_S3_SECRET_KEY` | vides | clés S3 (alimentées par `S3_ACCESS_KEY` / `S3_SECRET_KEY`, jamais versionnées); sans clé, un téléversement répond 503 |
| `APP_PAYMENT_WEBHOOK_SECRET` / `APP_PAYMENT_WEBHOOK_SECRET_PREVIOUS` | vides | secrets du webhook signé de `payment` (alimentés par `PAYMENT_WEBHOOK_SECRET` / `_PREVIOUS`, jamais versionnés); sans secret tout webhook est refusé |
| `APP_PAYMENT_WEBHOOK_TOLERANCE_SECONDS` | `300` | fenêtre d'acceptation de l'horodatage de la signature |
| `APP_SMTP_HOST` / `APP_SMTP_PORT` | `mailpit` / `1025` | serveur d'envoi de l'email de confirmation (Mailpit en développement) |
| `APP_MAIL_TRANSPORT` | `smtp` | transport des emails : `smtp` ou `n8n` (autre valeur : démarrage refusé) |
| `APP_N8N_MAIL_URL` / `APP_N8N_MAIL_SECRET` | vides | webhook n8n et secret de l'en-tête `X-Mail-Secret` (obligatoires avec `n8n`, jamais versionnés) |
| `APP_N8N_MAIL_TIMEOUT_SECONDS` | `5` | délai d'appel du webhook n8n |
| `APP_SMTP_FROM` / `APP_SMTP_TIMEOUT_SECONDS` | `commandes@basecamp.local` / `3` | expéditeur et délai d'envoi |
| `APP_PAYMENT_PROVIDER` | `http` | fournisseur de paiement : `http` (service `payment`) ou `simulated` (sans réseau ni clé) |
| `APP_PAYMENT_URL` | `http://payment:8000` | adresse interne de `payment` |
| `APP_AUTH_ISSUE_URL` | `http://auth:8000/internal/token` | où `shop` demande son jeton de service (réseau interne, jamais routé par la passerelle) |
| `APP_AUTH_CLIENT_ID` / `APP_AUTH_CLIENT_SECRET` | `shop` / vide | identifiants du client de service `shop` (le secret est `AUTH_SERVICE_CLIENT_SECRET_SHOP`, jamais versionné) |
| `APP_PAYMENT_AUDIENCE` / `APP_PAYMENT_SCOPE` | `payment` / `payments:write` | audience et scope demandés (`shop` n'a pas `refunds:write`) |
| `APP_PAYMENT_RENEW_MARGIN_SECONDS` | `30` | le jeton est renouvelé 30 s avant son expiration (il vit 5 min, en mémoire seulement) |
| `APP_PAYMENT_CONNECT_TIMEOUT_SECONDS` / `APP_PAYMENT_READ_TIMEOUT_SECONDS` | `1` / `3` | délais des appels à `payment` |
| `APP_AUTH_JWKS_URL` | `http://auth:8000/.well-known/jwks.json` | clés publiques de vérification des jetons clients (réseau interne) |
| `APP_AUTH_PROFILE_URL` | `http://auth:8000/me` | profil du porteur du jeton (adresse, vérifiée ou non), pour le rattachement |
| `APP_AUTH_ISSUER` / `APP_AUTH_AUDIENCE` | `basecamp-auth` / `basecamp-client-api` | `iss` et `aud` exigés |
| `APP_AUTH_JWKS_TTL_SECONDS` / `APP_AUTH_JWKS_MIN_REFETCH_SECONDS` | `300` / `10` | durée de vie des clés en cache; intervalle minimal entre deux relectures |
| `APP_AUTH_CONNECT_TIMEOUT_SECONDS` / `APP_AUTH_READ_TIMEOUT_SECONDS` | `1` / `2` | délais des appels à `auth` |
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
| `order.payment_requested` | success | | ressource `order` (numéro); `amount_cents`, `currency`, `attempt` |
| `order.refunded` | success | | ressource `order` (numéro); `amount_refunded_cents` (cumul), `currency`, `source` = `webhook` |
| `order.paid` | success | | ressource `order` (numéro); `amount_cents`, `currency`, `attempt` (confirmation synchrone) ou `source` = `webhook` (webhook de paiement) |
| `order.payment_failed` | denied | `provider_declined` | ressource `order` (numéro); `attempt` |
| `order.payment_rejected` | denied | `order_not_found`, `order_already_paid`, `order_expired`, `no_pending_payment` | ressource `order` (numéro) sauf `order_not_found`; couvre aussi un paiement reçu après expiration |
| `order.payment_unavailable` | error | `payment_unavailable` | fournisseur arrêté, injoignable ou saturé |
| `payment.webhook_received` | success | | webhook authentifié et lu : `event_id`, `event_type` |
| `payment.webhook_rejected` | denied | `webhook_not_configured`, `signature_missing`, `signature_malformed`, `timestamp_out_of_window`, `signature_mismatch`, `payload_not_json`, `payload_not_object`, `event_id_invalid`, `event_type_invalid`, `data_invalid`, `amount_invalid`, `currency_invalid`, `reference_invalid`, `event_id_mismatch` | 401 ou 400; jamais le corps ni la signature reçus |
| `payment.webhook_replayed` | success | | identifiant déjà reçu : `event_id`, `event_type` |
| `payment.webhook_ignored` | denied | `order_not_found`, `amount_mismatch`, `currency_mismatch`, `order_expired`, `order_already_confirmed`, `attempt_settled`, `unsupported_type`, `order_not_paid`, `refund_exceeds_total`, `refund_already_recorded`, `refund_amount_missing` | acquitté en 200 sans effet (sauf `order_expired` sur `payment.succeeded` : 409); ressource `order` si connue |
| `order.confirmation_email_sent` | success | | ressource `order` (numéro) |
| `catalog_admin.change` | success | | acteur `user` (empreinte), ressource `product`; `action`, `old_price_cents`, `new_price_cents`, `new_stock`, `version` |
| `operator.access_denied` | denied | `not_operator`, `second_factor_missing` | jeton valide sans les droits d'administration (403) |
| `order.confirmation_email_failed` | error | `delivery_failed` | ressource `order`; `email_hash` (HMAC de l'adresse); le webhook reste en succès |
| `order.expired` | success | | ressource `order` (numéro); `released_units`, `line_count`, `age_minutes` |
| `order.expiration_completed` | success | | un par passage qui a expiré au moins une commande : `expired_orders`, `released_units` |
| `order.expiration_failed` | error | `expiration_error` | un passage a échoué (base arrêtée…); le traitement continue au passage suivant |
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

La migration `0004` ajoute les tables `payment_attempts` (une ligne par tentative de paiement : intention, référence unique, statut) et `simulated_payment_intents` (état du fournisseur simulé), et **élargit** la contrainte `ck_orders_status` à `pending_payment`, `paid`, `expired`. L'ancien code n'écrit que `pending_payment` et reste valide sur le schéma migré. Limite assumée : il ne sait pas relire une commande déjà payée ou expirée (uniquement en rejouant la clé d'idempotence de sa création). `test_migrations_additive.unit.py` n'autorise ce remplacement que pour les contraintes de statut listées.

La migration `0005` élargit `ck_stock_reservations_status` à `reserved`, `released` (libération du stock des commandes expirées). Aucune table ni colonne ajoutée; l'ancien code n'écrit que `reserved`.

La migration `0006` ajoute la table `payment_webhook_events` (identifiant d'événement en clé primaire, `outcome` `applied` ou `ignored`, `paid_order_id` unique et lié à `orders`) et élargit `ck_stock_reservations_status` à `reserved`, `released`, `committed`. L'ancien code n'écrit que `reserved` : il reste valide sur le schéma migré (test d'additivité).

La migration `0007` (WORK-29) élargit `ck_orders_status` à `refunded` et ajoute la table `order_refunds` (cumul remboursé par commande, une ligne dès le premier remboursement, liée à `orders`). Ajout seul : l'ancien code n'écrit que les anciens statuts et ignore la table.

La migration `0008` ajoute `orders.user_id` (identifiant du compte d'`auth`, **nullable**, indexé, sans clé étrangère : le compte vit dans une autre base). Les commandes existantes restent invitées (`user_id` nul); l'ancienne version, qui ignore la colonne, tourne sur le schéma migré (expand/contract; le test `test_migrations_additive` n'autorise l'ajout de colonne que si elle est nullable).

La migration `0009` ajoute `products.archived_at` (nullable : null = produit visible) et `products.version` (entier, défaut serveur 1), et élargit `ck_products_price_positive` à `price_cents >= 0`. L'ancien code n'écrit ni l'un ni l'autre : les défauts s'appliquent et il reste valide sur le schéma migré (test d'additivité : une colonne ajoutée doit être nullable ou avoir un défaut serveur).

La migration `0002` crée la table `products` (contraintes : prix > 0, stock ≥ 0, note 0 à 5, catégorie connue) et y charge le jeu de données initial : 15 produits, 3 par catégorie, dont un en rupture et un aux dernières pièces.

## Images du catalogue
Les visuels (SVG originaux, sans droits) sont dans `infra/seed/images/`. Le service one-shot `seaweedfs-seed` les envoie dans le bucket `product-images` à chaque démarrage de la pile (envoi idempotent). Traefik les expose sous `/media/*` en lecture seule (GET et HEAD uniquement, pas de listage).
