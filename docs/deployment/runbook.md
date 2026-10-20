# Runbook de déploiement

Exploitation de la pile de production sur la VM. Le déploiement est **par tirage** : la VM va chercher, d'elle-même, le manifeste de `main`. Rien ne se connecte à la VM depuis l'extérieur, et GitHub ne détient aucun secret de la VM.

## Le flux

1. Une PR est fusionnée dans `main` : la CI tourne, puis le workflow `Release` calcule les versions, construit les images, les scanne (Trivy) et les publie sur GHCR ([images.md](../development/images.md)).
2. Si au moins une image est publiée, le workflow ouvre (ou met à jour) la PR **`chore(release): déploie …`** qui modifie `deploy/manifest.json`. Elle est ouverte par la GitHub App `basecamp-release-bot`, ce qui lance la CI normalement. Si la CI, le build ou le scan échoue pour un composant, ce composant n'entre pas dans le manifeste.
3. **Fusionner cette PR est l'approbation du déploiement** (relecture : quels composants, quelles versions).
4. Sur la VM, le minuteur `basecamp-deploy.timer` (toutes les 3 minutes) récupère `main` et lance `scripts/deploy.sh deploy/manifest.json` ([deploy-script.md](deploy-script.md)) : tirage par digest, sauvegarde, migrations, démarrage, test de fumée, retour automatique si échec.

## Première installation

Prérequis sur la VM : Docker et Compose v2, `git`, `flock`, `python3`, `openssl`, systemd, le réseau Docker externe `web` du Traefik du serveur.

```bash
sudo BASECAMP_DOMAIN=basecamp.tempulse.fr bash infra/install-vm.sh
```

Depuis une copie du dépôt (`git clone https://github.com/ESPI-TeamSTARRS/BaseCamp.git`). Le script est idempotent. Il crée l'utilisateur `basecamp` (sans shell ni mot de passe, groupe `docker`, donc équivalent root sur la machine), les dossiers sous `/opt/basecamp`, une copie du dépôt public, le fichier `/opt/basecamp/.env` avec des secrets **aléatoires** (jamais affichés, jamais dans le dépôt), les clés de signature d'`auth` et les unités systemd. Il **n'active pas** le minuteur.

`sudo bash infra/install-vm.sh --check` vérifie l'état sans rien modifier.

Après installation : relire `/opt/basecamp/.env` (domaine, et les valeurs facultatives du front si besoin).

## Bascule depuis l'ancienne pile

L'ancienne pile (projet compose `basecamp-outdoor`, dossier `/home/anto/basecamp-outdoor`) et la nouvelle routent le même domaine : **ne jamais les laisser tourner ensemble**. Tant que l'ancienne tourne, le déploiement de la nouvelle est suspendu (le script le détecte et le journal le dit).

1. Noter l'état de départ : `docker ps --filter label=com.docker.compose.project=basecamp-outdoor`.
2. Arrêter l'ancienne pile : `cd /home/anto/basecamp-outdoor && docker compose down` (sans `-v`).
3. Activer les déploiements : `sudo bash /opt/basecamp/repo/infra/install-vm.sh --enable-timer`.
4. Suivre : `journalctl -u basecamp-deploy -f`. Le premier déploiement tire les images, migre, amorce le bucket d'images et joue le test de fumée.
5. Vérifier depuis l'extérieur : `https://basecamp.tempulse.fr` (page d'accueil, une fiche produit avec ses images, `/api/shop/health`).

**Revenir à l'ancienne pile** si besoin : `sudo systemctl disable --now basecamp-deploy.timer`, `docker compose -p basecamp-prod -f /opt/basecamp/repo/deploy/docker-compose.prod.yml --env-file /opt/basecamp/state/compose.env down`, puis `docker compose up -d` dans `/home/anto/basecamp-outdoor`.

## Au quotidien

| Besoin | Commande |
|---|---|
| Version en production | `cat /opt/basecamp/state/current.json` |
| Dernier déploiement | `journalctl -u basecamp-deploy -n 100` |
| Suivre en direct | `journalctl -u basecamp-deploy -f` |
| Prochain passage | `systemctl list-timers basecamp-deploy.timer` |
| Suspendre les déploiements | `sudo -u basecamp touch /opt/basecamp/state/PAUSE` (reprise : `rm`) |
| Lancer tout de suite | `sudo systemctl start basecamp-deploy.service` |
| Rejouer un manifeste déjà refusé | `sudo -u basecamp /opt/basecamp/repo/scripts/pull-deploy.sh` ne le rejoue pas : corriger puis fusionner un nouveau manifeste, ou `deploy.sh <manifeste> --force` à la main |
| État des conteneurs | `docker compose -p basecamp-prod -f /opt/basecamp/repo/deploy/docker-compose.prod.yml --env-file /opt/basecamp/state/compose.env ps` |

## Retour arrière

- **Automatique** : si le test de fumée échoue, le script revient aux images précédentes ; le journal affiche `RETOUR ARRIERE reussi` et le manifeste fautif est noté dans `state/rejected`. Il faut ensuite corriger : le manifeste de `main` pointe encore vers la version refusée, la VM reste sur l'ancienne jusqu'à la fusion d'un nouveau manifeste.
- **Volontaire** (une version déployée avec succès mais jugée mauvaise) : ouvrir une PR qui rétablit l'ancien `deploy/manifest.json` (`git revert` du commit de manifeste) et la fusionner. Les migrations sont rétro-compatibles, l'ancienne version fonctionne sur le schéma migré.
- **Retour arrière en échec** (code de sortie 2, unité en échec) : la pile peut être dans un état mixte. Voir « Incidents ».

## Incidents

| Symptôme | Que faire |
|---|---|
| `tirage des images impossible` | Rien n'a été modifié. Vérifier que les packages GHCR sont publics et que le digest du manifeste existe (`docker pull <image>@sha256:…`). |
| `ECHEC du deploiement … retour arriere` | La version précédente tourne. Lire le journal (migration ? démarrage ? test de fumée ?), corriger par une PR. |
| `retour arriere EN ECHEC` | `docker compose … ps` et `logs` ; relancer le déploiement du `previous.json` : `sudo -u basecamp BASECAMP_STATE_DIR=/opt/basecamp/state BASECAMP_ENV_FILE=/opt/basecamp/.env /opt/basecamp/repo/scripts/deploy.sh /opt/basecamp/state/previous.json --force`. |
| Compose refuse de démarrer, variable `…:?voir deploy/prod.env.example` | Une variable requise manque dans `/opt/basecamp/.env` : l'ajouter (modèle : `deploy/prod.env.example`). |
| Données à restaurer | Sauvegardes dans `/opt/basecamp/state/backups/<date>/<base>.sql.gz` : `gunzip -c … \| docker compose … exec -T <service> psql -U <utilisateur> <base>` après avoir arrêté les services applicatifs. |
| `l'ancienne pile … tourne encore` | Normal avant la bascule : voir la section dédiée. |

## Secrets

- Tout est dans `/opt/basecamp/.env` (droits 600, propriétaire `basecamp`) et `/opt/basecamp/secrets/`. Rien dans le dépôt, rien dans GitHub côté VM.
- **Rotation d'un mot de passe de base** : modifier `.env`, puis modifier le mot de passe du rôle dans Postgres (`ALTER ROLE`), puis redéployer (`--force`). Changer seulement `.env` casserait la connexion.
- **Clés de signature d'`auth`** : les régénérer invalide tous les jetons émis ; à planifier.
- **`LOG_PSEUDONYM_KEY`** (journaux métier, chantier WORK-44 à 47) : `install-vm.sh` crée une valeur aléatoire longue à la première installation (`openssl rand -hex 32`), stockée uniquement dans `.env`. Elle devient **obligatoire** pour `shop`, `payment` et `auth` dès que ce chantier est déployé : sans elle, Compose refusera de démarrer. Sur une VM déjà installée avant cette évolution, l'ajouter à la main avant de fusionner le manifeste qui la requiert : `echo "LOG_PSEUDONYM_KEY=$(openssl rand -hex 32)" | sudo tee -a /opt/basecamp/.env`. Ne jamais la perdre ni la changer à la légère : elle relie les pseudonymes entre eux dans le temps.

## Après la première mise en service

- **Limiteur de débit derrière Cloudflare** : dans les journaux d'accès, l'adresse cliente doit varier d'une requête à l'autre (voir [README](README.md)). Si toutes les requêtes montrent la même adresse, ajuster `PROXY_TRUSTED_IPS` et la liste `excludedIPs` de `deploy/traefik/dynamic.prod.yml`.
- **Mises à jour de sécurité de la VM** : hors périmètre de ce runbook (infra).
