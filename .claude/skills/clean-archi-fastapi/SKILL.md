---
name: clean-archi-fastapi
description: Clean Architecture en tranches verticales pour les services FastAPI de Basecamp (apps/backend/*). A utiliser pour creer une fonctionnalite, placer un fichier, ou relire une PR (regle de dependance, 1 fichier = 1 classe, couches domain/application/infrastructure/presentation).
---

# Clean Architecture — tranches verticales FastAPI

Chaque service (`apps/backend/<service>/`) est un projet `uv` autonome. Son code vit dans `app/`, decoupe par **fonctionnalite** (tranche verticale). Chaque tranche a ses 4 couches.

```
app/
├── core/            # config (pydantic-settings), logs, wiring commun — aucune regle metier
├── <fonctionnalite>/
│   ├── domain/          entities/ value_objects/ enums/ interfaces/ exceptions/ factories/
│   ├── application/     un fichier = un cas d'usage (methode execute())
│   ├── infrastructure/  models/ repositories/ mappers/ clients/
│   ├── presentation/    router.py schemas/ dependencies.py
│   └── __tests__/       unit/ integration/   (colocalises)
├── main.py          # create_app() : assemble les routers
```

## Regle de dependance (verifiee par `app/__tests__/unit/test_architecture.unit.py`)

| Couche | Peut importer | Ne doit jamais importer |
|---|---|---|
| domain | rien (Python pur) | application, infrastructure, presentation |
| application | domain (interfaces) | infrastructure, presentation |
| infrastructure | domain (implemente ses interfaces) | application, presentation |
| presentation | application | domain directement, infrastructure |

Le cablage (injecter une implementation d'infrastructure dans un cas d'usage) se fait dans `presentation/dependencies.py` ou `main.py`.

## Ce qui va ou

- **domain** : `@dataclass(frozen=True)` avec garde-fous dans `__post_init__`; value objects pour tout type a validation metier (montant, email, cle d'idempotence); `StrEnum` pour les listes fermees; interfaces `ABC` (ex. `PaymentRepository`, `PaymentProvider`); exceptions `DomainException` typees avec `code` + message. Aucun import SQLAlchemy ni Pydantic.
- **application** : 1 fichier = 1 cas d'usage, 1 methode `execute()`. Recoit ses dependances par le constructeur (interfaces). Aucun code HTTP.
- **infrastructure** : modeles SQLAlchemy, depots, mappers modele <-> entite, clients externes. Les depots retournent des **entites**, jamais des modeles. Les erreurs techniques (reseau, BDD) sont converties en exceptions de domaine.
- **presentation** : routeur mince (valide -> appelle le cas d'usage -> repond), schemas Pydantic (`extra="forbid"` sur les entrees), gestion des erreurs via un handler global `DomainException` -> HTTP.

## Conventions

- **1 fichier = 1 classe.** Noms explicites, fonctions <= 20 lignes, retours anticipes, pas de valeur magique.
- Une tranche ne depend pas de l'infrastructure ni de la presentation d'une autre : on communique par interfaces du domaine ou par HTTP entre services.
- **Isolation des services** : aucun import entre services, aucune bibliotheque partagee. Un service doit pouvoir etre deplace dans son propre depot (son `pyproject.toml`, son `uv.lock`, son `Dockerfile`).
- Validation systematique des entrees (Pydantic), secrets uniquement via variables d'environnement.

## Creer une fonctionnalite

1. Ecrire d'abord le test (voir le skill `tdd-couverture`).
2. Creer `app/<fonctionnalite>/{domain,application,infrastructure,presentation,__tests__}/` avec des `__init__.py` (sauf dans `__tests__`).
3. Domaine -> cas d'usage -> infrastructure -> routeur, dans cet ordre.
4. Brancher le routeur dans `app/main.py`.
5. `uv run poe check` doit etre vert.

## Revue : points a verifier

1. Imports : aucune couche n'importe ce qu'elle ne doit pas (le test d'architecture le verifie).
2. Placement : la regle metier est dans le domaine ou un cas d'usage, jamais dans le routeur ni le depot.
3. Flux de donnees : schema Pydantic -> entite -> modele SQLAlchemy, avec mappers explicites.
4. Un cas d'usage depend d'interfaces, pas d'implementations.
5. Une classe par fichier, pas de logique HTTP dans `application`.

Pour chaque ecart : citer la regle, expliquer pourquoi elle existe, proposer la correction concrete. Signaler aussi ce qui est bien place.
