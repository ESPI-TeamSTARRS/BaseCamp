# Runbook de déploiement

Exploitation de la pile de production sur la VM. Le déploiement est **par tirage** : la VM va chercher, d'elle-même, le manifeste de `main`. Rien ne se connecte à la VM depuis l'extérieur, et GitHub ne détient aucun secret de la VM.

## Le flux

1. Une PR est fusionnée dans `main` : la CI tourne, puis le workflow `Release` calcule les versions, construit les images, les scanne (Trivy) et les publie sur GHCR ([images.md](../development/images.md)).
2. À la fin du workflow, le job `manifeste-de-deploiement` recalcule le manifeste **depuis `main`** : pour chaque composant, la dernière version dont le tag git `<composant>-vX.Y.Z` existe ET dont l'image est publiée sur GHCR (`scripts/deploy/latest_images.py`). Si le manifeste change, il régénère la branche `release/manifest` à partir de `main` (écrasement contrôlé, branche du bot uniquement) et ouvre ou met à jour la PR **`chore(release): déploie …`**; la PR ne contient donc jamais de conflit et rattrape les versions manquées par une exécution précédente. Si le manifeste de `main` est déjà à jour, la PR ouverte est fermée. Elle est ouverte par la GitHub App `basecamp-release-bot` (permission « Pull requests: Read and write », à accepter par un propriétaire de l'organisation après toute modification), ce qui lance la CI normalement. Un composant dont le build ou le scan a échoué n'a pas d'image publiée : sa version précédente reste dans le manifeste.
3. **Fusionner cette PR est l'approbation du déploiement** (relecture : quels composants, quelles versions). Avant de fusionner, vérifier que le dernier run horaire du workflow `E2E` (`e2e.yml`, test de bout en bout de la pile, hors PR et hors release) est vert : `gh run list --workflow E2E --limit 3`. Le job `e2e` de `release.yml` est rouge si un scénario échoue; il ne bloque la publication que si la variable de dépôt `E2E_BLOQUANT` vaut `true` ([ci.md](../development/ci.md)).
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

**Tester avant de basculer.** Dans `/opt/basecamp/.env`, ajouter `GATEWAY_EXPOSE=false`, puis lancer un premier déploiement manuel (`scripts/deploy.sh deploy/manifest.json`, avec `BASECAMP_STATE_DIR` et `BASECAMP_ENV_FILE`) : la pile démarre, migre et joue son test de fumée **sans** que le Traefik du serveur la route (pas de routeur `basecamp-gw`, donc aucun conflit avec l'ancienne pile ni demande de certificat). Pour la voir dans un navigateur depuis son poste : `docker run --rm -d --name bc-preview -p 127.0.0.1:18080:9080 --network web alpine/socat tcp-listen:9080,fork,reuseaddr tcp-connect:basecamp-prod-traefik-1:9080`, puis un tunnel SSH `-L 8081:127.0.0.1:18080` ; supprimer l'aperçu avec `docker rm -f bc-preview`.

**Bascule** (prévenir Antony : la VM est partagée) :

1. Noter l'état de départ : `docker ps --filter label=com.docker.compose.project=basecamp-outdoor`.
2. **Arrêter** (pas supprimer) l'ancienne pile : `cd /home/anto/basecamp-outdoor && docker compose stop`. Ses conteneurs et ses volumes sont conservés.
3. Exposer la nouvelle pile : retirer `GATEWAY_EXPOSE` de `/opt/basecamp/.env` (`sudo sed -i '/^GATEWAY_EXPOSE=/d' /opt/basecamp/.env`) puis relancer le déploiement avec `--force` (les labels changent, le manifeste non).
4. Vérifier depuis l'extérieur : `https://basecamp.tempulse.fr` (page d'accueil, une fiche produit avec ses images, `/api/shop/health`).

**Origine d'administration.** L'API d'administration du catalogue (/api/shop/admin) ne répond que sur dmin.<domaine> (par exemple dmin.basecamp.tempulse.fr) : créer l'enregistrement DNS de cet hôte vers le même serveur. Les étiquettes du Traefik de la pile le déclarent à côté du domaine principal, et le Traefik du serveur y émet son certificat. Sur le domaine principal, /api/shop/admin reste un 404. Les clés S3 (S3_ACCESS_KEY, S3_SECRET_KEY) sont aussi lues par shop pour les images.
5. Activer le minuteur seulement après ce déploiement manuel réussi : `sudo bash /opt/basecamp/repo/infra/install-vm.sh --enable-timer`. Suivre : `journalctl -u basecamp-deploy -f`.

**Revenir à l'ancienne pile** (une commande) : `sudo systemctl disable --now basecamp-deploy.timer; docker compose -p basecamp-prod -f /opt/basecamp/repo/deploy/docker-compose.prod.yml --env-file /opt/basecamp/state/compose.env stop && (cd /home/anto/basecamp-outdoor && docker compose start)`. Rien n'est supprimé : la nouvelle pile est seulement arrêtée.

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
- **`AUTH_SMTP_*`** (emails d'inscription d'`auth`) : `AUTH_SMTP_HOST`, `AUTH_SMTP_PORT` (587), `AUTH_SMTP_USER`, `AUTH_SMTP_PASSWORD`, `AUTH_SMTP_FROM`, `AUTH_SMTP_STARTTLS` (`true`). **Facultatives** : jamais bloquantes pour Compose ni pour `deploy.sh`. Sans relais (`AUTH_SMTP_HOST` vide ou `localhost`), l'inscription répond normalement mais aucun email de vérification ne part (événement `auth.email_delivery_failed` dans les journaux). Le mot de passe SMTP ne vit que dans `.env`, jamais dans le dépôt. Les liens des emails utilisent `https://${BASECAMP_DOMAIN}`.
- **Envoi des mails par n8n** (WORK-65) : en production, il n'y a pas de relais SMTP ; les services envoient leurs mails par le workflow n8n universel (`POST` JSON `{to, subject, body}`, `body` en HTML, en-tête `X-Mail-Secret`). Variables de `/opt/basecamp/.env` : `MAIL_TRANSPORT=n8n`, `N8N_MAIL_URL` (l'URL du webhook `send-email`) et `N8N_MAIL_SECRET` (le secret de l'en-tête, **mis par Sam sur la VM, jamais dans le dépôt**). Avec `MAIL_TRANSPORT=n8n`, l'URL et le secret sont obligatoires : sans eux le service refuse de démarrer. Un échec d'envoi (refus 403, délai, réponse invalide) n'annule jamais l'action : elle est journalisée (`order.confirmation_email_failed` pour `shop`) avec un motif (`http_403`, `timeout`…), sans adresse ni secret. Sans variable, le transport reste `smtp` (Mailpit en développement et en CI).
- **`LOG_PSEUDONYM_KEY`** (journaux métier) : clé HMAC des empreintes d'email dans les journaux, **obligatoire** : sans elle Compose refuse de démarrer (`shop` aujourd'hui, `payment` et `auth` quand leurs journaux métier arriveront). `install-vm.sh` la crée à la première installation (`openssl rand -hex 32`), stockée uniquement dans `.env`. Sur une VM installée avant cette évolution, l'ajouter à la main **avant** de fusionner le manifeste qui déploie une image la requérant : `echo "LOG_PSEUDONYM_KEY=$(openssl rand -hex 32)" | sudo tee -a /opt/basecamp/.env`. Ne jamais la perdre ni la changer à la légère : changer la clé change toutes les empreintes, donc rompt le lien entre les anciens et les nouveaux journaux.

## Après la première mise en service

- **Limiteur de débit derrière Cloudflare** : dans les journaux d'accès, l'adresse cliente doit varier d'une requête à l'autre (voir [README](README.md)). Si toutes les requêtes montrent la même adresse, ajuster `PROXY_TRUSTED_IPS` et la liste `excludedIPs` de `deploy/traefik/dynamic.prod.yml`.
- **Mises à jour de sécurité de la VM** : hors périmètre de ce runbook (infra).

## Ajouter une variable obligatoire (ordre à respecter)

Quand une évolution du code rend une variable obligatoire (secret, clé), la VM doit l'avoir **avant** de déployer l'image qui la requiert :

1. Fusionner la PR qui ajoute la variable au compose de production et à `deploy/prod.env.example`. Sans effet immédiat : le manifeste n'a pas changé, le minuteur répond « ce manifeste est deja en place ».
2. Sur la VM, relancer l'installation : `sudo bash /opt/basecamp/repo/infra/install-vm.sh`. Elle met le dépôt à jour, ajoute avec une valeur aléatoire chaque variable obligatoire absente ou vide (sans modifier ni afficher les valeurs existantes) et vérifie le résultat (`verification : OK`).
3. Fusionner la PR de manifeste qui déploie la nouvelle version.

Si l'ordre n'est pas respecté, la production n'est pas touchée : Compose refuse l'environnement incomplet **au tirage** (« required variable … is missing a value »), le script s'arrête avec « aucune modification effectuee » (code 1), la version en service continue de tourner et le manifeste n'est pas noté refusé. Le minuteur réessaie toutes les 3 minutes (le journal le répète) : dès que la variable est ajoutée, le déploiement passe seul. Une valeur présente mais inutilisable fait échouer le démarrage ou le test de fumée : retour automatique à la version précédente et manifeste noté refusé.

### Webhook signé de payment (payment-worker)

`payment-worker` livre à la boutique les événements de paiement signés (même image que `payment`, aucun port, mémoire limitée à 128 Mio). Il exige `PAYMENT_WEBHOOK_SECRET` (au moins 32 caractères, généré par l'installation, uniquement sur la VM). Facultatives : `PAYMENT_WEBHOOK_SECRET_PREVIOUS` (rotation : l'ancien secret signe en parallèle le temps que la boutique bascule, puis on le vide), `PAYMENT_WEBHOOK_URL`, `PAYMENT_WEBHOOK_MAX_ATTEMPTS`, `PAYMENT_WEBHOOK_BACKOFF_BASE_SECONDS`.

- **Ordre** : le manifeste ne doit référencer une image `payment` qui embarque le worker qu'après la fusion et la release de cette évolution. Avec une image sans worker, le worker est malsain : le déploiement échoue, retour automatique, manifeste noté refusé, la production reste en service.
- **Retour arrière** : les services applicatifs reviennent aux images précédentes. Le worker est relancé avec elles ; s'il ne démarre pas (image sans worker), il est arrêté et le journal le dit. Les événements restent en base et partiront après le prochain déploiement réussi.
- **Relancer des événements en échec** (état `dead`) : `docker compose -p basecamp-prod -f /opt/basecamp/repo/deploy/docker-compose.prod.yml --env-file /opt/basecamp/state/compose.env run --rm --no-deps payment-worker python -m app.webhook.presentation.requeue_main --all` (ou `--event-id <uuid>`).
- **Vérifier le secret sans l'afficher** : `sudo awk -F= '/^PAYMENT_WEBHOOK_SECRET=/{print $1, length($2)}' /opt/basecamp/.env` doit afficher 48 ; de même pour `AUTH_SERVICE_CLIENT_SECRET_SHOP`.

### Jetons d'auth pour payment (WORK-41)
`payment` n'a plus de jeton statique : il vérifie les jetons signés par `auth`, et `shop` en demande un à `auth` avant d'appeler `payment`.
- **Variables** : retirer `PAYMENT_SERVICE_TOKEN_SHOP` du `.env` (ignoré désormais). `shop` réutilise `AUTH_SERVICE_CLIENT_SECRET_SHOP`, déjà présent pour `auth-bootstrap` : rien à ajouter.
- **Ordre** : l'image `auth` (scope `refunds:write`, réseau `payment-net`) doit être en service avant ou avec `payment` et `shop`; déployer les trois images dans le même manifeste. Avec une ancienne image `payment`, `shop` fonctionnerait encore mal (jeton refusé) : ne pas mélanger.
- **Contrôle sans afficher de secret** : `sudo awk -F= '/^AUTH_SERVICE_CLIENT_SECRET_SHOP=/{print $1, length($2)}' /opt/basecamp/.env` doit afficher la longueur attendue (au moins 32); `docker compose ... exec -T payment python -c "import urllib.request as u; print(u.urlopen('http://auth:8000/.well-known/jwks.json', timeout=3).status)"` doit afficher 200.
- **Symptôme** : `/pay` répond 503 si `auth` est injoignable et que `shop` n'a pas de jeton valide en mémoire; `payment` répond 503 s'il n'a jamais lu les clés d'`auth`. Relancer `auth`, le service repart seul.
- **Retour arrière** : revenir aux images précédentes réintroduit le jeton statique : y remettre `PAYMENT_SERVICE_TOKEN_SHOP` dans le `.env` avant de revenir (sinon `payment` refuse de démarrer).

### Activer le back-office en production (WORK-59 et WORK-63)
Le back-office est **éteint** par défaut (`APP_BACKOFFICE_ENABLED` absent) : le déploiement du code ne change rien tant qu'on ne l'active pas. Pour l'activer, dans l'ordre :
1. **Secret des gabarits** : créer `${SECRETS_DIR:-/opt/basecamp/secrets}/auth/face-template.key` (32 octets aléatoires en base64, `openssl rand -base64 32`, lisible par l'utilisateur du conteneur, droits 600 ou 640 selon l'hôte), puis déclarer le secret `auth_face_template_key` dans `deploy/docker-compose.prod.yml` pour le service `auth`. **Sauvegarder cette clé hors de la VM** : sans elle, les gabarits sont perdus (réenrôlement de tous les opérateurs).
2. **Variables** : `APP_BACKOFFICE_ENABLED=true`, `APP_FACE_VERIFIER=visage-id`, éventuellement `APP_FACE_THRESHOLD` (défaut `0.23`). Sans la clé ou sans le package dans l'image, `auth` refuse de démarrer (voulu : jamais de porte sans vérificateur) : le déploiement échoue puis revient en arrière.
3. **Enrôler chaque opérateur** : `create-operator` puis `enroll_face` (voir [auth](../services/auth.md#vérificateur-réel-enrôlement-et-gabarits-work-63)), photos montées en lecture seule et supprimées ensuite de la machine qui les a prises.
4. **Origine admin** : le back-office n'est servi que sur `admin.<domaine>` (voir [admin-domain.md](admin-domain.md)). Les routes `/admin/users` d'`auth` n'acceptent plus que le jeton de la connexion en trois temps.
