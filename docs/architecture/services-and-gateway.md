# Services, fonctionnalités et passerelle d'API

## Style d'architecture

Backend en **microservices** : `shop`, `auth` et `payment` sont des services déployables séparément, chacun dans son conteneur et avec sa propre base de données (ou son propre schéma, avec des identifiants distincts). Chaque service est lui-même organisé en tranches verticales Clean Architecture (voir [clean-architecture.md](clean-architecture.md)), ce qui garde l'option de regrouper ou de scinder plus tard.

## Fonctionnalité ou service ?

Par défaut, une nouvelle capacité est une **tranche dans un service existant**.

Elle devient un **nouveau service** si au moins deux de ces critères sont vrais :

1. **Données propres** : elle possède ses données et personne d'autre n'y accède directement.
2. **Cycle de vie indépendant** : elle se déploie, se met à l'échelle ou tombe sans les autres.
3. **Charge ou sécurité différente** : profil de trafic, exigences de sécurité ou de conformité distincts.
4. **Propriétaire distinct** : une équipe différente en est responsable.

Exemples : le paiement est un service (données financières, sécurité renforcée, doit rester disponible si la boutique est saturée). Le catalogue et les commandes restent des tranches du service `shop`.

## Passerelle d'API

Un reverse proxy (Traefik) est le seul point d'entrée publié. Il route les requêtes vers le bon service selon le chemin, par exemple :

| Préfixe | Service |
|---|---|
| `/api/shop/*` (sauf `/api/shop/admin` et `/api/shop/webhooks`) | `shop` |
| `/api/shop/admin/*` **sur l'hôte `mercure.<domaine>` seulement** | `shop` (administration du catalogue) |
| `/media/*` | images du catalogue (bucket `product-images`, lecture seule) |
| `/api/auth/*` (sauf `/api/auth/backoffice`, `/api/auth/internal` et `/api/auth/metrics`) | `auth` |
| `/api/auth/backoffice/*` **sur l'hôte `mercure.<domaine>` seulement** | `auth` (connexion du back-office en trois temps) |
| `/.well-known/jwks.json` | `auth` (clés publiques de vérification des jetons, lecture seule) |
| `/api/payment/*` | `payment` (accès restreint) |

La passerelle porte les préoccupations transverses : TLS, limitation de débit par IP réelle, taille maximale des corps de requête, délais d'expiration, en-têtes de sécurité et filtrage applicatif. Les services restent sur un réseau interne et ne sont jamais publiés directement. Les appels entre services (par exemple `shop` vers `payment`) passent par le réseau interne avec un jeton de service.

## Protections portées par la passerelle

Configuration versionnée, sans secret : `infra/traefik/dynamic.yml` (routeurs et middlewares) et les arguments de Traefik dans `docker-compose.yml` (entrypoint et délais).

| Protection | Réglage | Comportement |
|---|---|---|
| Limitation de débit | `/api/shop/orders*` : 10 requêtes/minute par IP, rafale de 5 | 429 avec `Retry-After` |
| Limitation de débit (administration) | `/api/shop/admin*` : 30 requêtes/minute par IP, rafale de 10 | 429 |
| IP réelle | clé = adresse de la connexion (`RemoteAddr`), pas d'`ipStrategy.depth`; l'entrypoint `web` ne fait confiance à aucun proxy (`forwardedHeaders.insecure=false`, sans `trustedIPs`) | un `X-Forwarded-For` forgé est ignoré et ne contourne pas la limite |
| Taille du corps | `buffering.maxRequestBodyBytes` = 1 Mio sur `/api/shop/*` | 413 au-delà |
| Taille du corps (téléversement d'image) | 3 Mio, tenus en mémoire, sur `/api/shop/admin*` | 413 au-delà |
| Taille du corps (connexion du back-office) | 5 Mio, tenus en mémoire, sur `/api/auth/backoffice*` (3 images de 1 Mo en base64) | 413 au-delà |
| Taille du corps (invitation d'un opérateur) | 15 Mio, tenus en mémoire, sur `/api/auth/backoffice/invitation/complete` seulement (jusqu'à 10 images de 1 Mo en base64) | 413 au-delà |
| Délais d'expiration | entrants : lecture 30 s, écriture 30 s, inactivité 60 s; vers les services : connexion 5 s, en-têtes de réponse 30 s | coupure de la connexion |
| En-têtes de sécurité | HSTS (2 ans, sous-domaines), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy` | posés sur toutes les réponses (API et front) |

Les compteurs de limitation sont tenus en mémoire par Traefik (bornés par IP active, sans Redis). Si un load balancer ou un CDN est placé devant Traefik, déclarer ses adresses dans `entrypoints.web.forwardedHeaders.trustedIPs` et utiliser `ipStrategy.depth`, sinon toutes les requêtes partageraient la même clé. Hors périmètre : filtrage applicatif (WAF) et limitation par client dans Redis. La limitation par client des jetons de service (`POST /internal/token`) est portée par `auth` dans sa propre base Postgres (voir [auth](../services/auth.md)), pas par la passerelle.

Les protections sont vérifiées par les scénarios `tests/e2e/scenarios/test_gateway_protection.e2e.py` (job CI `stack-e2e`). Ces scénarios consomment le seuil de l'IP locale : relancer un second passage immédiatement peut être limité pendant environ une minute.
