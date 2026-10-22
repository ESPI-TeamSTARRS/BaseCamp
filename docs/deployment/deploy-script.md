# Script de déploiement

`scripts/deploy.sh <manifeste.json> [--force]` déploie un manifeste de release sur la pile de production (`deploy/docker-compose.prod.yml`) et revient seul à la version précédente si le déploiement échoue. Il tourne **sur la VM**, lancé par le minuteur de déploiement ou à la main.

## Manifeste

Le manifeste est l'unité de déploiement et de retour arrière : une version de chaque composant, **par digest**.

```json
{
  "schema": 1,
  "services": {
    "shop":     { "version": "0.1.2", "image": "ghcr.io/espi-teamstarrs/basecamp-shop@sha256:…" },
    "auth":     { "version": "0.1.2", "image": "ghcr.io/espi-teamstarrs/basecamp-auth@sha256:…" },
    "payment":  { "version": "0.1.2", "image": "ghcr.io/espi-teamstarrs/basecamp-payment@sha256:…" },
    "frontend": { "version": "0.1.1", "image": "ghcr.io/espi-teamstarrs/basecamp-frontend@sha256:…" }
  }
}
```

`scripts/deploy/manifest.py` le valide (les quatre composants, plus le `backoffice` facultatif : absent des anciens manifestes, il n'est démarré que s'il figure dans le manifeste, via le profil compose `backoffice` posé par `manifest.py env` dans `COMPOSE_PROFILES`) ; version semver, image sous la forme `dépôt@sha256:<64 hex>`, jamais un tag). Son identifiant est l'empreinte des seules images : deux manifestes qui déploient les mêmes digests sont identiques, quelle que soit la version annoncée.

## Déroulé

1. **Validation** du manifeste (code 3 sinon), puis verrou : un seul déploiement à la fois.
2. **Rien à faire** si ce jeu de digests est déjà en production, ou s'il a déjà été refusé (fichier `rejected`) : le minuteur ne rejoue pas indéfiniment un manifeste cassé. `--force` passe outre.
3. **Tirage** des images par digest. Un échec ici ne modifie rien.
4. **Sauvegarde** `pg_dump` (compressée, droits 600) des trois bases si elles tournent, dans `backups/<horodatage>/`. Les 7 dernières sont conservées.
5. **Migrations** avec les nouvelles images (bases démarrées d'abord), puis `docker compose up -d --wait`.
6. **Premier déploiement seulement** : amorçage du bucket d'images (`seaweedfs-seed`).
7. **Test de fumée** (`scripts/deploy/smoke.sh`) par la passerelle de la pile : `/`, `/api/shop/health`, `/api/auth/health` répondent 200, et `/api/auth/internal/health` répond 404 (route interne jamais exposée).
8. **Succès** : le manifeste devient `current.json`, l'ancien devient `previous.json`.
9. **Échec** : le manifeste est ajouté à `rejected`, puis retour automatique aux images précédentes (sans rejouer les migrations, voir plus bas) et nouveau test de fumée. Sans version précédente (premier déploiement raté), la pile est arrêtée plutôt qu'exposée en mauvais état.

## Codes de sortie

| Code | Signification |
|---|---|
| 0 | succès, ou rien à faire |
| 1 | échec : retour arrière réussi (ou rien n'a été modifié) |
| 2 | échec **et** retour arrière en échec : intervention humaine ([runbook](runbook.md)) |
| 3 | usage ou manifeste invalide |

## Migrations et retour arrière

Les migrations sont **rétro-compatibles** (expand puis contract) : l'ancienne version doit fonctionner sur le schéma migré. C'est pourquoi le retour arrière ne restaure pas les bases et ne relance pas `alembic upgrade head` avec l'ancienne image (elle ne connaît pas la dernière révision). Les sauvegardes servent aux incidents de données, pas au retour arrière courant. Une migration destructive (contract) se fait dans une release **ultérieure**, une fois l'ancienne version définitivement abandonnée.

## État sur la VM

Dans `/opt/basecamp/state/` (hors dépôt, droits 700) : `current.json`, `previous.json`, `rejected`, `release.env` (+ `.previous`), `compose.env` (secrets de `/opt/basecamp/.env` + références d'images, droits 600), `backups/`, `deploy.lock`.

## Tester

Le test de bascule joue les scénarios réels avec `docker compose`, un registre local et trois images minuscules dont une qui plante volontairement :

```bash
uv run poe deploy-test        # nécessite docker ; joué par la CI (job deploy-rollback)
```

Scénarios : premier déploiement, mise à jour saine, **panne volontaire avec retour automatique**, manifeste refusé non rejoué, idempotence, image introuvable, manifeste invalide, premier déploiement raté. Les tests du manifeste sont dans `scripts/deploy/test_manifest.py` (`uv run poe tools-test`).

Sous Windows, `flock` est absent de Git Bash : le verrou est ignoré avec un avertissement, et il faut indiquer un Python réel avec `PYTHON=…`. Sur la VM Ubuntu et en CI, rien à régler.
