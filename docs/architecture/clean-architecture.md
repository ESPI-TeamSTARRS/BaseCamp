# Clean Architecture en tranches verticales

Chaque fonctionnalité d'un service est une tranche autonome avec ses quatre couches.

```
app/<fonctionnalité>/
├── domain/          entities/ value_objects/ enums/ interfaces/ exceptions/ factories/
├── application/     un fichier = un cas d'usage (méthode execute())
├── infrastructure/  models/ repositories/ mappers/ clients/
├── presentation/    router.py schemas/ dependencies.py
└── __tests__/       unit/ integration/
```

## Règle de dépendance

| Couche | Peut importer | Ne doit jamais importer |
|---|---|---|
| domain | rien (Python pur) | application, infrastructure, presentation |
| application | domain (interfaces) | infrastructure, presentation |
| infrastructure | domain (implémente ses interfaces) | application, presentation |
| presentation | application | domain directement, infrastructure |

Un test (`app/__tests__/unit/test_architecture.unit.py`) vérifie cette règle dans chaque service. Le câblage d'une implémentation d'infrastructure dans un cas d'usage se fait dans `presentation/dependencies.py` ou `main.py`.

## Contenu de chaque couche

- **domain** : dataclasses immuables avec garde-fous dans `__post_init__`; value objects pour tout type à validation métier; `StrEnum` pour les listes fermées; interfaces `ABC`; exceptions `DomainException` typées (code et message). Aucun import SQLAlchemy ni Pydantic.
- **application** : un cas d'usage par fichier, dépendances reçues par le constructeur sous forme d'interfaces. Aucun code HTTP.
- **infrastructure** : modèles SQLAlchemy, dépôts, mappers modèle ↔ entité, clients externes. Les dépôts retournent des entités. Les erreurs techniques sont converties en exceptions de domaine.
- **presentation** : routeur mince (valider, appeler le cas d'usage, répondre), schémas Pydantic, gestion des erreurs de domaine par un handler global.

## Conventions de code

Un fichier = une classe. Noms explicites, fonctions de 20 lignes au plus, retours anticipés, pas de valeur magique (enums), types explicites, exceptions typées.

## Frontend

| Backend | Frontend |
|---|---|
| presentation | pages et components |
| application | hooks |
| domain | types et modèles |
| infrastructure | services et mappers |
