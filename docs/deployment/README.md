# Déploiement

Pile de production : `deploy/docker-compose.prod.yml`. Elle est distincte de `docker-compose.yml` (développement) et ne partage rien avec lui, pour qu'une commodité de développement ne puisse pas fuiter en production.

Exploitation (installation, bascule, incidents) : [runbook.md](runbook.md). Script de déploiement et retour arrière : [deploy-script.md](deploy-script.md).

## Principes

| Sujet | Règle |
|---|---|
| Images applicatives | uniquement par **digest** (`FRONT_IMAGE`, `SHOP_IMAGE`, `PAYMENT_IMAGE`, `AUTH_IMAGE`), jamais de `build:` ni de tag flottant ([images.md](../development/images.md)) |
| Images tierces | épinglées par tag **et** digest (Traefik, Postgres, SeaweedFS) |
| Ports | aucun port publié sur l'hôte : la VM est partagée avec d'autres projets |
| Entrée du trafic | le Traefik du serveur (80/443, TLS Let's Encrypt, derrière Cloudflare) route le domaine vers le Traefik **interne** de la pile, qui rejoint le réseau Docker externe `web` |
| Noms | projet `basecamp-prod`, routeurs `basecamp-gw` et `basecamp-gw-http` : aucun conflit avec l'ancienne pile (`basecamp`, `basecamp-http`) |
| Ressources | `mem_limit` sur chaque conteneur, `pids_limit`, `cap_drop: ALL`, `no-new-privileges`, systèmes de fichiers en lecture seule pour les services |
| Secrets | aucun dans le dépôt : valeurs lues dans `/opt/basecamp/.env` (modèle : `deploy/prod.env.example`) et clés de signature d'`auth` dans `/opt/basecamp/secrets/` |

## Paramètres du Traefik du serveur

Observés sur la VM, exposés en variables avec ces valeurs par défaut : entrypoints `web` (:80) et `websecure` (:443), résolveur de certificats `letsencrypt`, réseau `web`, fournisseur Docker avec `exposedByDefault=false` (seuls les conteneurs labellisés sont routés). Les labels sont portés par le service `traefik` de la pile.

## Limitation de débit derrière Cloudflare

Une requête arrive par Cloudflare, puis le Traefik du serveur, puis le Traefik de la pile. `X-Forwarded-For` vaut alors « client, Cloudflare, proxy Docker ». La clé du limiteur des commandes (`orders-rate-limit`) exclut les réseaux Docker et les plages Cloudflare pour retrouver l'adresse du vrai client (`deploy/traefik/dynamic.prod.yml`). Les plages Cloudflare sont publiques (cloudflare.com/ips) et à tenir à jour. À vérifier après la première mise en service : dans le journal d'accès, l'adresse cliente doit varier d'une requête à l'autre.

## Valider la pile

`scripts/deploy/test_compose_prod.py` (tâche `tools-test`, donc la CI) vérifie : aucun `build` ni port publié, images applicatives par variable, images tierces par digest, limites de mémoire, routeurs sans collision, réseaux de données internes, routage identique à celui du développement, et `docker compose config` avec un environnement minimal.

Lancer à la main :

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file /opt/basecamp/.env --env-file /opt/basecamp/release.env config -q
```

## Mettre à jour une image tierce

Choisir le nouveau tag, lire son digest (`docker buildx imagetools inspect <image>:<tag>`), remplacer `tag@sha256:…` dans le fichier, puis lancer le scan et les tests de la PR. Ne jamais passer par `latest`.
