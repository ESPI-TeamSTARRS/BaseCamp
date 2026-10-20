# Images de conteneur

Chaque composant (`shop`, `auth`, `payment`, `frontend`) est publié en image sur GitHub Container Registry par le workflow `Release` (`.github/workflows/release.yml`), dans le même job que le calcul de version ([versioning.md](versioning.md)).

## Nommage et tags

| Élément | Règle |
|---|---|
| Dépôt d'images | `ghcr.io/espi-teamstarrs/basecamp-<service>` (images publiques) |
| `:X.Y.Z` | version exacte, **immuable** : si le tag existe déjà, le workflow ne republie pas |
| `:X.Y` | dernière version du palier mineur |
| `:sha-<12 car.>` | tag provisoire posé au build, avant les contrôles |
| `latest` | **n'existe pas**, n'est jamais publié ni utilisé |
| Référence de déploiement | toujours le **digest** (`basecamp-<service>@sha256:…`), jamais un tag |

Le digest de chaque image publiée est écrit dans le résumé du job et dans l'artefact `image-<service>` (service, version, référence par digest). Ces fichiers alimentent le manifeste de déploiement.

## Attestations

Le build produit une attestation de **provenance** (`mode=max`) et un **SBOM**, attachés à l'image dans le registre. Pour les consulter :

```bash
docker buildx imagetools inspect ghcr.io/espi-teamstarrs/basecamp-shop:0.1.0 --format '{{json .Provenance}}'
docker buildx imagetools inspect ghcr.io/espi-teamstarrs/basecamp-shop:0.1.0 --format '{{json .SBOM}}'
```

## Aucun secret dans les images

Les images et le dépôt sont publics : tout ce qui entre dans une image est lisible par tous, y compris l'historique des couches et les arguments de build (visibles dans l'attestation de provenance).

- Aucun secret, clé, jeton ni mot de passe en `ARG`, `ENV` ou `COPY`. Les secrets arrivent **à l'exécution** (variables d'environnement ou secrets Docker du serveur).
- Les `build-args` publiés sont limités à des valeurs publiques. Aujourd'hui, un seul : `NEXT_PUBLIC_SITE_URL` du front.

## Front : variables `NEXT_PUBLIC_*`

Next.js remplace `process.env.NEXT_PUBLIC_SITE_URL` **au build**. Choix assumé : l'image du front est construite pour le site de production, avec `NEXT_PUBLIC_SITE_URL` = variable de dépôt ou d'organisation `SITE_URL` si elle existe, sinon `https://basecamp.tempulse.fr`. Une image du front n'est donc pas réutilisable sous un autre domaine : en changer impose une nouvelle version. `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` n'est pas fournie au build : le serveur la lit à l'exécution (`process.env` complet, validé par `lib/env.ts`).

## Publier une version déjà taguée

Les tags posés avant l'existence de ce mécanisme n'ont pas d'image. Lancer à la main le workflow `Release` (Actions → Release → Run workflow, branche `main`) : pour chaque composant sans nouvelle version, il republie la dernière version taguée si son image manque, construite depuis le commit du tag.

## Visibilité

Un package GHCR est privé à sa création. Après le premier push, passer chaque package `basecamp-<service>` en **public** dans ses paramètres (Package settings → Change visibility). Le libellé `org.opencontainers.image.source` relie le package au dépôt.
