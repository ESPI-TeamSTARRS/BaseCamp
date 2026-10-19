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
| `/api/shop/*` | `shop` |
| `/api/auth/*` | `auth` |
| `/api/payment/*` | `payment` (accès restreint) |

La passerelle porte les préoccupations transverses : TLS, limitation de débit par IP réelle, taille maximale des corps de requête, délais d'expiration, en-têtes de sécurité et filtrage applicatif. Les services restent sur un réseau interne et ne sont jamais publiés directement. Les appels entre services (par exemple `shop` vers `payment`) passent par le réseau interne avec un jeton de service.
