# Principes

## Choix structurants

- **Backend en Python / FastAPI.** Un seul langage côté serveur; les types du front se génèrent depuis l'OpenAPI de chaque service.
- **Un projet `uv` par service.** Chaque service a son `pyproject.toml`, son `uv.lock` et son `Dockerfile`. Pas de workspace partagé ni de bibliothèque commune : un service se déplace dans son propre dépôt en copiant son dossier. La duplication de quelques helpers est acceptée. Le squelette d'un service (santé, configuration, migrations, scénarios e2e) est ainsi volontairement dupliqué d'un service à l'autre; il est exclu du calcul de duplication SonarCloud (`.sonarcloud.properties`).
- **Un `pyproject.toml` racine** qui pilote l'ensemble par délégation (`uv run poe quality | test | security | ci`) et ne contient aucune logique d'outil.
- **Clean Architecture en tranches verticales** dans chaque service : voir [clean-architecture.md](clean-architecture.md).
- **Paiement derrière une interface** `PaymentProvider` : l'adaptateur interne est utilisé par défaut, un fournisseur externe reste branchable.

## Règles non négociables

1. Toute entrée est validée (Pydantic, `extra="forbid"` sur les corps de requête) avant traitement.
2. Aucun secret dans le code ni dans le dépôt : variables d'environnement validées au démarrage.
3. Les montants sont toujours recalculés côté serveur, jamais fournis par le client.
4. Les opérations de paiement sont idempotentes (clé d'idempotence unique en base).
5. Les erreurs renvoyées au client sont assainies : jamais de trace ni de détail interne.
6. Les services n'importent pas le code les uns des autres : ils communiquent par HTTP.
7. Mobile first pour toute interface.
8. Tout code est écrit en TDD avec une couverture minimale de 80 % : voir [development/testing.md](../development/testing.md).
