# Règles de développement

Règles applicables à tout changement. Elles se vérifient automatiquement quand c'est possible (hooks, CI), sinon en relecture.

## Code

1. **TDD strict** : pas d'implémentation sans test en échec au préalable ([testing.md](testing.md)).
2. **Clean Architecture en tranches verticales** dans chaque service, un fichier = une classe ([architecture/clean-architecture.md](../architecture/clean-architecture.md)).
3. **Fonctions courtes** (20 lignes au plus), retours anticipés, noms explicites, pas de valeur magique (utiliser des enums ou des constantes), types explicites.
4. **Exceptions de domaine typées** (code et message); les erreurs techniques sont converties en infrastructure; le routeur n'attrape pas les erreurs de domaine, un handler global s'en charge.
5. **Validation de toute entrée** (Pydantic avec `extra="forbid"`; Zod `.strict()` côté front).
6. **Aucun secret dans le code** : variables d'environnement, validées au démarrage.
7. **Journaux structurés** (JSON), sans donnée sensible; erreurs renvoyées au client assainies. Chaque cas d'usage métier émet ses événements de succès et de refus ([logging.md](logging.md)).
8. **Un service n'importe jamais le code d'un autre** et aucune bibliothèque n'est partagée entre services ([architecture/principles.md](../architecture/principles.md)).
9. **Interface mobile first**.

## Tests

- Tests unitaires et d'intégration colocalisés dans `__tests__/`; end-to-end dans `tests/e2e/`.
- Couverture minimale de 80 %, 90 % visé sur la logique métier. On n'exclut jamais de code pour faire monter le chiffre.
- Un test de non-régression accompagne chaque bug corrigé.

## Qualité automatique

| Contrôle | Outil | Commande |
|---|---|---|
| Lint et sécurité du code | ruff (règles `S` incluses), ESLint sans warning | `uv run poe quality` |
| Format | ruff format, Prettier | `uv run poe quality` |
| Types | mypy strict, `tsc` | `uv run poe quality` |
| Tests et couverture | pytest, Vitest | `uv run poe test` |
| Dépendances | pip-audit, npm audit | `uv run poe security` |
| Secrets | gitleaks | hook `pre-commit`, job CI |

## Pull requests

- Une intention par PR, petite, au format de titre décrit dans [git-and-hooks.md](git-and-hooks.md).
- Description : quoi, pourquoi, comment tester.
- Fusion uniquement si la CI est verte et qu'une relecture a eu lieu; toute remarque bloquante est traitée avant fusion.

## Définition de terminé

Un changement est terminé quand : les tests écrits d'abord passent, la couverture reste au-dessus du seuil, lint et types sont à zéro, aucun secret n'est présent, le service concerné démarre et répond sur `/health`, et la documentation de [services/](../services/README.md) est à jour si une API ou un invariant change.

## Décisions d'architecture

Toute question qui touche la structure (nouveau service, communication entre services, données, passerelle) suit [architecture/services-and-gateway.md](../architecture/services-and-gateway.md). Si une règle doit changer, on modifie d'abord le document concerné dans la même PR que le code.
